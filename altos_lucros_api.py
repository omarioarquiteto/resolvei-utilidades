"""API somente leitura da ferramenta ALTOS LUCROS."""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from trade_pro_auth import _get_session
from trade_pro_api import _ensure_connection, _load_assets
from altos_lucros_engine import analyze_targets
from altos_lucros_marketdata import (
    normalize_client_price_event,
    normalize_digital_underlyings,
    normalize_legacy_quote_event,
    normalize_legacy_strike_list,
    normalize_library_snapshot,
)

router = APIRouter(prefix="/api/altos-lucros", tags=["ALTOS LUCROS"])
logger = logging.getLogger("resolvei.altos_lucros")

CANDLE_COUNT = 1000
CANDLE_TIMEOUT_SECONDS = 12
STRIKE_TIMEOUT_SECONDS = 6
LEGACY_STRIKE_TIMEOUT_SECONDS = 7
ASSET_RECONNECT_TIMEOUT_SECONDS = 20
DIGITAL_CATALOG_TIMEOUT_SECONDS = 7
DIGITAL_CATALOG_TTL_SECONDS = 45
MINIMUM_PAYOUT_PERCENT = 200.0


class AltosLucrosAnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    horizon_minutes: int = Field(default=5, ge=5, le=15)


def _asset_active_map(assets: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(asset.get("activeId")): str(asset.get("symbol"))
        for asset in assets
        if asset.get("activeId") is not None and asset.get("symbol")
    }


async def _ensure_asset_client_connected(item: dict[str, Any]) -> Any:
    """Reconecta a sessão auxiliar síncrona quando o WebSocket cai ou fica obsoleto."""
    asset_client = item.get("asset_client")
    if asset_client is None:
        await _load_assets(item)
        asset_client = item.get("asset_client")
    if asset_client is None:
        raise HTTPException(status_code=503, detail="A conexão de dados da IQ Option não foi inicializada.")

    api = getattr(asset_client, "api", None)
    connected = True
    timestamp = None
    try:
        alive_method = getattr(api, "websocket_alive", None)
        if callable(alive_method):
            connected = bool(alive_method())
        timestamp = getattr(getattr(api, "timesync", None), "server_timestamp", None)
    except Exception:
        connected = False

    stale = False
    try:
        stale = timestamp is None or time.time() - float(timestamp) > 90
    except (TypeError, ValueError):
        stale = True

    if not connected or stale:
        logger.warning(
            "[ALTOS LUCROS] WebSocket auxiliar inativo/obsoleto; tentando reconectar (ativo=%s).",
            connected,
        )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(asset_client.connect),
                timeout=ASSET_RECONNECT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail="A conexão auxiliar da IQ Option caiu e não conseguiu reconectar dentro do limite.",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao reabrir a conexão auxiliar da IQ Option: {type(exc).__name__}: {str(exc)[:160]}",
            ) from exc
        if isinstance(result, tuple) and result and result[0] is False:
            reason = result[1] if len(result) > 1 else "conexão recusada"
            raise HTTPException(status_code=502, detail=f"A IQ Option recusou a reconexão auxiliar: {str(reason)[:160]}")
        item["asset_client"] = asset_client
        item["asset_cache"] = {"at": 0.0, "data": None}
        item.pop("altos_digital_catalog_cache", None)
        logger.info("[ALTOS LUCROS] WebSocket auxiliar reconectado.")

    return asset_client


def _install_digital_quote_callback(
    item: dict[str, Any],
    asset_client: Any,
    assets: list[dict[str, Any]],
) -> None:
    """Captura os eventos brutos antes do parser interno da iqoptionapi.

    A biblioteca chama global_value.client_callback antes de processar a
    mensagem. Esse hook nos permite normalizar o evento mesmo se o parser
    interno falhar ao mapear um active_id ou sofrer alteração de formato.
    """
    api = getattr(asset_client, "api", None)
    object_id = getattr(api, "object_id", None)
    if api is None or object_id is None:
        return

    active_to_symbol = _asset_active_map(assets)
    cache = item.setdefault("altos_digital_quote_cache", {})
    payouts_cache = item.setdefault("altos_legacy_payout_cache", {})
    lock = item.setdefault("altos_digital_quote_lock", threading.RLock())

    try:
        from iqoptionapi import global_value
        callbacks = global_value.client_callback
    except Exception:
        logger.warning("[ALTOS LUCROS] Callback bruto da iqoptionapi indisponível; usando o buffer nativo.")
        return

    current_id = item.get("altos_callback_object_id")
    if current_id == object_id and item.get("altos_callback_fn") is not None:
        item["altos_active_to_symbol"] = active_to_symbol
        return

    previous_callback = callbacks.get(object_id)

    def on_message(message: dict[str, Any]) -> None:
        if callable(previous_callback):
            try:
                previous_callback(message)
            except Exception:
                logger.exception("[ALTOS LUCROS] Callback anterior da sessão IQ Option falhou.")

        try:
            parsed = normalize_client_price_event(message, active_to_symbol)
            if parsed:
                symbol, duration, quotes = parsed
                key = (symbol, duration)
                with lock:
                    cache[key] = {
                        "quotes": quotes,
                        "received_at": time.time(),
                        "source": "client-price-generated",
                    }
                return

            legacy = normalize_legacy_quote_event(message, active_to_symbol)
            if legacy:
                symbol, duration, payouts = legacy
                with lock:
                    payouts_cache[(symbol, duration)] = {
                        "payouts": payouts,
                        "received_at": time.time(),
                        "source": "instrument-quotes-generated",
                    }
        except Exception:
            logger.exception("[ALTOS LUCROS] Não foi possível normalizar um evento de cotação digital.")

    callbacks[object_id] = on_message
    item["altos_callback_object_id"] = object_id
    item["altos_callback_fn"] = on_message
    item["altos_active_to_symbol"] = active_to_symbol


def _clear_strike_buffer(
    item: dict[str, Any],
    asset_client: Any,
    symbol: str,
    duration: int,
) -> None:
    """Remove snapshots anteriores para impedir que uma consulta use dados velhos."""
    key = (symbol, duration)
    lock = item.setdefault("altos_digital_quote_lock", threading.RLock())
    with lock:
        item.setdefault("altos_digital_quote_cache", {}).pop(key, None)
        item.setdefault("altos_legacy_payout_cache", {}).pop(key, None)

    api = getattr(asset_client, "api", None)
    if api is None:
        return
    for attribute in ("instrument_quites_generated_data", "instrument_quotes_generated_raw_data"):
        store = getattr(api, attribute, None)
        if isinstance(store, dict):
            try:
                store[symbol][duration * 60] = {}
            except Exception:
                pass
    try:
        api.strike_list = None
    except Exception:
        pass


def _wait_for_strikes(
    item: dict[str, Any],
    asset_client: Any,
    symbol: str,
    duration: int,
    request_started: float,
) -> dict[str, Any]:
    """Espera o callback bruto ou o snapshot equivalente da iqoptionapi."""
    api = getattr(asset_client, "api", None)
    lock = item.setdefault("altos_digital_quote_lock", threading.RLock())
    deadline = time.monotonic() + STRIKE_TIMEOUT_SECONDS
    key = (symbol, duration)

    while time.monotonic() < deadline:
        with lock:
            entry = item.setdefault("altos_digital_quote_cache", {}).get(key)
            if entry and float(entry.get("received_at", 0)) >= request_started:
                quotes = entry.get("quotes")
                if isinstance(quotes, dict) and quotes:
                    item["altos_last_quote_source"] = entry.get("source", "callback")
                    return quotes

        store = getattr(api, "instrument_quites_generated_data", None)
        if isinstance(store, dict):
            by_symbol = store.get(symbol)
            if isinstance(by_symbol, dict):
                quotes = normalize_library_snapshot(by_symbol.get(duration * 60))
                if quotes:
                    item["altos_last_quote_source"] = "iqoptionapi-buffer"
                    return quotes
        time.sleep(0.1)
    return {}


async def _legacy_digital_strikes(
    item: dict[str, Any],
    asset_client: Any,
    symbol: str,
    duration: int,
    request_started: float,
) -> dict[str, Any]:
    """Fallback para builds da IQ Option que ainda publicam instrument-quotes-generated."""
    api = getattr(asset_client, "api", None)
    if api is None:
        return {}

    subscribed = False
    try:
        from iqoptionapi.ws.chanels.subscribe import Subscribe_Instrument_Quites_Generated
        from iqoptionapi.ws.chanels.unsubscribe import Unsubscribe_Instrument_Quites_Generated

        api.strike_list = None
        await asyncio.wait_for(
            asyncio.to_thread(api.get_strike_list, symbol, duration),
            timeout=4,
        )
        subscribe = Subscribe_Instrument_Quites_Generated(api)
        await asyncio.wait_for(
            asyncio.to_thread(subscribe, symbol, duration),
            timeout=4,
        )
        subscribed = True

        lock = item.setdefault("altos_digital_quote_lock", threading.RLock())
        key = (symbol, duration)
        deadline = time.monotonic() + LEGACY_STRIKE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            strike_response = getattr(api, "strike_list", None)
            with lock:
                entry = item.setdefault("altos_legacy_payout_cache", {}).get(key)
                payouts = entry.get("payouts") if entry and float(entry.get("received_at", 0)) >= request_started else None

            if isinstance(strike_response, dict) and isinstance(payouts, dict) and payouts:
                grid = normalize_legacy_strike_list(strike_response, payouts)
                if grid and any(
                    side.get("profit") is not None
                    for sides in grid.values()
                    for side in (sides.get("call", {}), sides.get("put", {}))
                ):
                    item["altos_last_quote_source"] = "instrument-quotes-generated-fallback"
                    return grid
            await asyncio.sleep(0.1)
    except Exception as exc:
        logger.warning(
            "[ALTOS LUCROS] Fallback legado indisponível para %s M%s: %s: %s",
            symbol, duration, type(exc).__name__, str(exc)[:140],
        )
    finally:
        if subscribed:
            try:
                from iqoptionapi.ws.chanels.unsubscribe import Unsubscribe_Instrument_Quites_Generated
                unsubscribe = Unsubscribe_Instrument_Quites_Generated(api)
                await asyncio.wait_for(
                    asyncio.to_thread(unsubscribe, symbol, duration),
                    timeout=3,
                )
            except Exception:
                logger.debug("[ALTOS LUCROS] Não foi possível encerrar a assinatura legada.")

    return {}


async def _load_digital_catalog(item: dict[str, Any]) -> dict[str, Any]:
    """Carrega o catálogo próprio de opções Digital e seus horários de negociação."""
    cached = item.get("altos_digital_catalog_cache")
    now = time.time()
    if cached and now - float(cached.get("at", 0)) < DIGITAL_CATALOG_TTL_SECONDS:
        return cached.get("data") or {"available": False, "assets": {}}

    asset_client = await _ensure_asset_client_connected(item)
    api = getattr(asset_client, "api", None)
    if api is None or not callable(getattr(api, "get_digital_underlying", None)):
        data = {"available": False, "assets": {}, "reason": "A biblioteca não expõe o catálogo Digital."}
        item["altos_digital_catalog_cache"] = {"at": now, "data": data}
        return data

    try:
        api.underlying_list_data = None
        await asyncio.wait_for(
            asyncio.to_thread(api.get_digital_underlying),
            timeout=4,
        )
        deadline = time.monotonic() + DIGITAL_CATALOG_TIMEOUT_SECONDS
        raw = None
        while time.monotonic() < deadline:
            raw = getattr(api, "underlying_list_data", None)
            if raw is not None:
                break
            await asyncio.sleep(0.1)
        if raw is None:
            data = {"available": False, "assets": {}, "reason": "A IQ Option não respondeu ao catálogo Digital."}
        else:
            digital_assets = normalize_digital_underlyings(raw, time.time())
            data = {
                "available": bool(digital_assets),
                "assets": digital_assets,
                "reason": None if digital_assets else "A IQ Option retornou o catálogo Digital vazio.",
            }
    except Exception as exc:
        logger.warning("[ALTOS LUCROS] Catálogo Digital indisponível: %s: %s", type(exc).__name__, str(exc)[:160])
        data = {"available": False, "assets": {}, "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}

    item["altos_digital_catalog_cache"] = {"at": now, "data": data}
    return data


async def _digital_strikes(
    item: dict[str, Any],
    symbol: str,
    duration: int,
    catalog_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    asset_client = await _ensure_asset_client_connected(item)
    _install_digital_quote_callback(item, asset_client, catalog_assets)
    _clear_strike_buffer(item, asset_client, symbol, duration)
    request_started = time.time()
    subscribed = False

    try:
        await asyncio.wait_for(
            asyncio.to_thread(asset_client.subscribe_strike_list, symbol, duration),
            timeout=5,
        )
        subscribed = True

        quotes = await asyncio.wait_for(
            asyncio.to_thread(
                _wait_for_strikes,
                item,
                asset_client,
                symbol,
                duration,
                request_started,
            ),
            timeout=STRIKE_TIMEOUT_SECONDS + 2,
        )
        if quotes:
            return quotes

        logger.warning(
            "[ALTOS LUCROS] Canal Digital principal sem snapshot para %s M%s; acionando fallback legado.",
            symbol, duration,
        )
        quotes = await _legacy_digital_strikes(
            item, asset_client, symbol, duration, request_started
        )
        if quotes:
            return quotes

        api = getattr(asset_client, "api", None)
        alive = False
        try:
            alive = bool(api.websocket_alive())
        except Exception:
            pass
        raise HTTPException(
            status_code=409,
            detail=(
                f"A IQ Option não publicou strikes digitais para {symbol} no vencimento de "
                f"{duration} minutos. Conexão auxiliar: {'ativa' if alive else 'reconectando'}. "
                "A ferramenta tentou os dois protocolos de cotações. Verifique se o ativo "
                "está marcado como ABERTO no catálogo Digital ou selecione outro ativo/vencimento."
            ),
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="A consulta dos dados digitais da IQ Option excedeu o tempo limite. A conexão foi preservada; tente novamente.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar dados digitais: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc
    finally:
        if subscribed:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(asset_client.unsubscribe_strike_list, symbol, duration),
                    timeout=4,
                )
            except Exception:
                logger.warning("[ALTOS LUCROS] Não foi possível encerrar a assinatura principal para %s M%s.", symbol, duration)


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    catalog = await _load_assets(item)
    _install_digital_quote_callback(item, item.get("asset_client"), catalog.get("assets", []))
    digital = await _load_digital_catalog(item)

    if digital.get("available"):
        digital_by_name = digital.get("assets") or {}
        enriched = []
        used: set[str] = set()
        for asset in catalog.get("assets", []):
            symbol = str(asset.get("symbol") or "").strip()
            detail = digital_by_name.get(symbol.upper())
            if detail:
                enriched.append({**asset, **detail, "digital_available": True})
                used.add(symbol.upper())
        for name, detail in digital_by_name.items():
            if name in used:
                continue
            active_id = detail.get("active_id")
            if active_id is not None:
                enriched.append({
                    "symbol": detail.get("symbol") or name,
                    "activeId": active_id,
                    **detail,
                    "digital_available": True,
                })
        enriched.sort(key=lambda row: row["symbol"])
        return {
            "assets": enriched,
            "total": len(enriched),
            "updatedAt": int(time.time()),
            "digital_catalog_available": True,
            "digital_catalog_reason": None,
        }

    # Não esconde a ferramenta quando a IQ Option falha ao responder ao catálogo.
    fallback_assets = [
        {**asset, "digital_available": None, "digital_open": None}
        for asset in catalog.get("assets", [])
    ]
    return {
        **catalog,
        "assets": fallback_assets,
        "digital_catalog_available": False,
        "digital_catalog_reason": digital.get("reason"),
    }


@router.get("/diagnostics")
async def diagnostics(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    catalog = await _load_assets(item)
    asset_client = await _ensure_asset_client_connected(item)
    digital = await _load_digital_catalog(item)
    api = getattr(asset_client, "api", None)
    try:
        websocket_connected = bool(api.websocket_alive())
    except Exception:
        websocket_connected = False
    return {
        "ok": True,
        "iq_session": True,
        "asset_websocket_connected": websocket_connected,
        "assets_total": catalog.get("total", 0),
        "digital_catalog_available": digital.get("available", False),
        "digital_assets_total": len(digital.get("assets", {})),
        "digital_catalog_reason": digital.get("reason"),
        "execution_enabled": False,
    }


@router.post("/analyze")
async def run(
    req: AltosLucrosAnalyzeRequest,
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    symbol = req.symbol.strip()
    horizon = req.horizon_minutes
    if horizon not in {5, 15}:
        raise HTTPException(status_code=400, detail="Selecione um vencimento de 5 ou 15 minutos.")
    if not symbol:
        raise HTTPException(status_code=400, detail="Selecione um ativo.")

    catalog = await _load_assets(item)
    available_assets = {asset["symbol"]: asset for asset in catalog.get("assets", [])}
    if symbol not in available_assets:
        raise HTTPException(
            status_code=400,
            detail=f"O ativo {symbol} não está no catálogo geral da IQ Option.",
        )

    digital = await _load_digital_catalog(item)
    digital_assets = digital.get("assets") or {}
    digital_detail = digital_assets.get(symbol.upper())
    if digital.get("available") and digital_detail is None:
        raise HTTPException(
            status_code=409,
            detail=f"{symbol} não está listado pela IQ Option como ativo de opções Digital. Selecione um ativo disponível no catálogo Digital.",
        )
    if digital_detail and digital_detail.get("digital_open") is False:
        raise HTTPException(
            status_code=409,
            detail=f"O mercado Digital de {symbol} está fechado neste horário. Selecione um ativo marcado como ABERTO ou tente mais tarde.",
        )

    try:
        await _ensure_connection(item)
        raw = await asyncio.wait_for(
            item["client"].get_candles(symbol, 60, CANDLE_COUNT, int(time.time())),
            timeout=CANDLE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"A IQ Option não respondeu aos candles M1 de {symbol} em {CANDLE_TIMEOUT_SECONDS}s.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao obter candles M1: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc

    now = time.time()
    rows: list[dict[str, Any]] = []
    for candle in raw or []:
        try:
            timestamp = float(candle.get("from", candle.get("to", 0)))
            rows.append({
                "time": timestamp,
                "open": float(candle["open"]),
                "high": float(candle.get("max", candle.get("high"))),
                "low": float(candle.get("min", candle.get("low"))),
                "close": float(candle["close"]),
            })
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda row: row["time"])
    closed = [
        row for row in rows
        if row["time"] + 60 <= now + 0.2
    ]
    closed = list({int(row["time"]): row for row in closed}.values())
    closed.sort(key=lambda row: row["time"])

    if not closed:
        raise HTTPException(status_code=502, detail="A IQ Option não retornou candles M1 fechados.")
    latest_raw = rows[-1] if rows else None
    live_reference = (
        float(latest_raw["close"])
        if latest_raw
        and latest_raw["time"] + 60 > now + 0.2
        and now - latest_raw["time"] <= 90
        else None
    )
    reference_price = live_reference if live_reference and live_reference > 0 else float(closed[-1]["close"])
    candle_close_epoch = float(closed[-1]["time"]) + 60
    data_age = round(max(0.0, now - candle_close_epoch), 1)
    if data_age > 90:
        raise HTTPException(
            status_code=409,
            detail=f"Candles desatualizados: último fechamento há {data_age:.0f}s. A análise foi bloqueada.",
        )

    asset_client = await _ensure_asset_client_connected(item)
    _install_digital_quote_callback(item, asset_client, catalog.get("assets", []))

    quotes = await _digital_strikes(item, symbol, horizon, catalog.get("assets", []))
    try:
        result = await asyncio.to_thread(
            analyze_targets,
            closed[-CANDLE_COUNT:],
            quotes,
            horizon,
            MINIMUM_PAYOUT_PERCENT,
            reference_price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha no motor ALTOS LUCROS para %s", symbol)
        raise HTTPException(
            status_code=500,
            detail=f"Falha no motor estatístico: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc

    result.update({
        "ok": True,
        "symbol": symbol,
        "reference_price": round(reference_price, 8),
        "digital_quote_source": item.get("altos_last_quote_source", "unknown"),
        "reference_price_source": "live_m1" if live_reference is not None else "last_closed_m1",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "data_quality": {
            "returned_candles": len(raw or []),
            "valid_closed_candles": len(closed),
            "last_candle_close_time": datetime.fromtimestamp(
                candle_close_epoch, timezone.utc
            ).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "last_candle_age_seconds": data_age,
            "stale": False,
        },
        "execution_enabled": False,
    })
    logger.info(
        "[ALTOS LUCROS] symbol=%s horizon=%s status=%s price=%s candidates=%s",
        symbol,
        horizon,
        result.get("status"),
        result.get("symbol_price"),
        len(result.get("candidates", [])),
    )
    return result
