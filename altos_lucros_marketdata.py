"""Normalização dos eventos de cotações digitais da iqoptionapi.

Este módulo não depende de sessão, FastAPI ou conexão de rede; permite testar
replays de mensagens WebSocket e os dois protocolos suportados pela biblioteca.
"""
from __future__ import annotations

import re
from math import isfinite
from typing import Any

_DURATION_RE = re.compile(r"T(\d+)M", re.IGNORECASE)


def _duration_from_contract(value: Any) -> int | None:
    match = _DURATION_RE.search(str(value or ""))
    if not match:
        return None
    try:
        duration = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return duration if duration in {5, 15} else None


def payout_from_ask(value: Any) -> float | None:
    """Converte ask da Digital (0–100) para payout percentual."""
    try:
        ask = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(ask) or ask <= 0 or ask > 100:
        return None
    return round(((100.0 - ask) * 100.0) / ask, 6)


def _symbol_for_active(active_id: Any, active_to_symbol: dict[str, str]) -> str | None:
    if active_id is None:
        return None
    return active_to_symbol.get(str(active_id))


def normalize_client_price_event(
    message: dict[str, Any],
    active_to_symbol: dict[str, str],
) -> tuple[str, int, dict[str, Any]] | None:
    """Lê o evento client-price-generated antes do parser interno da biblioteca."""
    if not isinstance(message, dict) or message.get("name") != "client-price-generated":
        return None
    payload = message.get("msg") or {}
    symbol = _symbol_for_active(payload.get("asset_id"), active_to_symbol)
    prices = payload.get("prices") or []
    if not symbol or not isinstance(prices, list):
        return None

    duration = None
    normalized: dict[str, Any] = {}
    for row in prices:
        if not isinstance(row, dict):
            continue
        call = row.get("call") or {}
        put = row.get("put") or {}
        duration = duration or _duration_from_contract(call.get("symbol")) or _duration_from_contract(put.get("symbol"))
        raw_strike = row.get("strike")
        if str(raw_strike).strip().upper() == "SPT":
            continue
        try:
            strike = float(raw_strike)
        except (TypeError, ValueError):
            continue
        if not isfinite(strike) or strike <= 0:
            continue
        normalized[f"{strike:.8f}"] = {
            "call": {
                "id": call.get("symbol"),
                "profit": payout_from_ask(call.get("ask")),
            },
            "put": {
                "id": put.get("symbol"),
                "profit": payout_from_ask(put.get("ask")),
            },
        }

    # A API pode incluir o vencimento diretamente em alguns formatos.
    if duration is None:
        raw_period = payload.get("expiration_period", payload.get("period"))
        try:
            period = int(raw_period)
            duration = period // 60 if period > 15 else period
        except (TypeError, ValueError):
            duration = None
    if duration not in {5, 15} or not normalized:
        return None
    return symbol, duration, normalized


def normalize_legacy_quote_event(
    message: dict[str, Any],
    active_to_symbol: dict[str, str],
) -> tuple[str, int, dict[str, float | None]] | None:
    """Lê instrument-quotes-generated (payout por ID de contrato)."""
    if not isinstance(message, dict) or message.get("name") != "instrument-quotes-generated":
        return None
    payload = message.get("msg") or {}
    symbol = _symbol_for_active(payload.get("active", payload.get("active_id")), active_to_symbol)
    expiration = payload.get("expiration") or {}
    try:
        period = int(expiration.get("period", 0))
        duration = period // 60 if period > 15 else period
    except (TypeError, ValueError):
        return None
    if not symbol or duration not in {5, 15}:
        return None

    payouts: dict[str, float | None] = {}
    quotes = payload.get("quotes") or []
    if not isinstance(quotes, list):
        return None
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        price = quote.get("price") or {}
        payout = payout_from_ask(price.get("ask"))
        contract_ids = quote.get("symbols") or []
        if isinstance(contract_ids, str):
            contract_ids = [contract_ids]
        for contract_id in contract_ids:
            if contract_id:
                payouts[str(contract_id)] = payout
    return symbol, duration, payouts


def normalize_legacy_strike_list(
    message: dict[str, Any],
    payouts_by_contract: dict[str, float | None],
) -> dict[str, Any]:
    """Junta o preço do strike-list ao payout por ID do protocolo legado."""
    if not isinstance(message, dict):
        return {}
    rows = ((message.get("msg") or {}).get("strike")) or []
    result: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            # Conversão idêntica à usada por IQ_Option.get_strike_list().
            strike = float(row["value"]) * 1e-6
            call_id = str(row["call"]["id"])
            put_id = str(row["put"]["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if not isfinite(strike) or strike <= 0:
            continue
        call_payout = payouts_by_contract.get(call_id)
        put_payout = payouts_by_contract.get(put_id)
        result[f"{strike:.8f}"] = {
            "call": {"id": call_id, "profit": call_payout},
            "put": {"id": put_id, "profit": put_payout},
        }
    return result


def normalize_library_snapshot(snapshot: Any) -> dict[str, Any]:
    """Valida o snapshot já normalizado pela própria iqoptionapi."""
    if not isinstance(snapshot, dict):
        return {}
    result: dict[str, Any] = {}
    for raw_strike, sides in snapshot.items():
        try:
            strike = float(raw_strike)
        except (TypeError, ValueError):
            continue
        if not isfinite(strike) or strike <= 0 or not isinstance(sides, dict):
            continue
        call = sides.get("call") or {}
        put = sides.get("put") or {}
        if not isinstance(call, dict) or not isinstance(put, dict):
            continue
        result[f"{strike:.8f}"] = {
            "call": {
                "id": call.get("id"),
                "profit": call.get("profit"),
            },
            "put": {
                "id": put.get("id"),
                "profit": put.get("profit"),
            },
        }
    return result


def normalize_digital_underlyings(
    response: Any,
    now_epoch: float,
) -> dict[str, dict[str, Any]]:
    """Normaliza lista Digital e calcula se cada ativo está dentro do schedule."""
    if not isinstance(response, dict):
        return {}
    rows = response.get("underlying") or []
    if not isinstance(rows, list):
        return {}

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("underlying") or row.get("name") or "").strip()
        if not symbol:
            continue
        schedule = row.get("schedule")
        is_open: bool | None = None
        if isinstance(schedule, list):
            is_open = False
            for period in schedule:
                if not isinstance(period, dict):
                    continue
                try:
                    opened = float(period["open"])
                    closed = float(period["close"])
                except (KeyError, TypeError, ValueError):
                    continue
                if opened <= now_epoch < closed:
                    is_open = True
                    break
        result[symbol.upper()] = {
            "symbol": symbol,
            "active_id": row.get("active_id"),
            "digital_available": True,
            "digital_open": is_open,
            "schedule_count": len(schedule) if isinstance(schedule, list) else None,
        }
    return result
