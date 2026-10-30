"""API somente leitura da ferramenta ALTOS LUCROS."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from trade_pro_auth import _get_session
from trade_pro_api import _ensure_connection, _load_assets
from altos_lucros_engine import analyze_targets

router = APIRouter(prefix="/api/altos-lucros", tags=["ALTOS LUCROS"])
logger = logging.getLogger("resolvei.altos_lucros")

CANDLE_COUNT = 1000
CANDLE_TIMEOUT_SECONDS = 12
STRIKE_TIMEOUT_SECONDS = 10
MINIMUM_PAYOUT_PERCENT = 200.0


class AltosLucrosAnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    horizon_minutes: int = Field(default=5, ge=5, le=15)


def _clear_strike_buffer(asset_client: Any, symbol: str, duration: int) -> None:
    """Remove qualquer grade anterior para só aceitar dados da nova assinatura."""
    api = getattr(asset_client, "api", None)
    store = getattr(api, "instrument_quites_generated_data", None)
    if isinstance(store, dict):
        try:
            store[symbol][duration * 60] = {}
        except Exception:
            pass
    raw_store = getattr(api, "instrument_quotes_generated_raw_data", None)
    if isinstance(raw_store, dict):
        try:
            raw_store[symbol][duration * 60] = {}
        except Exception:
            pass


def _wait_for_strikes(asset_client: Any, symbol: str, duration: int) -> dict[str, Any]:
    """Lê a grade que a iqoptionapi monta ao receber client-price-generated.

    A implementação atual da biblioteca assina price-splitter.client-price-generated.
    O WebSocket converte essa resposta no evento client-price-generated e grava a
    grade completa (preço, IDs e payouts CALL/PUT) em
    instrument_quites_generated_data[symbol][period]. Não se deve pedir
    get_strike_list() nem esperar instrument-quotes-generated: esse é outro
    protocolo e não corresponde à assinatura usada por subscribe_strike_list().
    """
    api = getattr(asset_client, "api", None)
    if api is None:
        return {}

    deadline = time.monotonic() + STRIKE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        store = getattr(api, "instrument_quites_generated_data", None)
        if isinstance(store, dict):
            by_symbol = store.get(symbol)
            if isinstance(by_symbol, dict):
                quotes = by_symbol.get(duration * 60)
                if isinstance(quotes, dict) and quotes:
                    # O evento também pode incluir o strike SPT (preço spot).
                    # O motor aceita apenas preços numéricos e descarta o SPT.
                    normalized: dict[str, Any] = {}
                    for raw_strike, sides in quotes.items():
                        try:
                            strike = float(raw_strike)
                        except (TypeError, ValueError):
                            continue
                        if strike <= 0 or not isinstance(sides, dict):
                            continue
                        call = sides.get("call") or {}
                        put = sides.get("put") or {}
                        normalized[f"{strike:.8f}"] = {
                            "call": {
                                "id": call.get("id"),
                                "profit": call.get("profit"),
                            },
                            "put": {
                                "id": put.get("id"),
                                "profit": put.get("profit"),
                            },
                        }
                    if normalized:
                        return normalized
        time.sleep(0.12)
    return {}


async def _digital_strikes(item: dict[str, Any], symbol: str, duration: int) -> dict[str, Any]:
    asset_client = item.get("asset_client")
    if asset_client is None:
        raise HTTPException(
            status_code=503,
            detail="A conexão auxiliar de dados da IQ Option não foi inicializada.",
        )
    subscribed = False
    try:
        # Evita ler um snapshot antigo de uma tentativa anterior.
        await asyncio.to_thread(_clear_strike_buffer, asset_client, symbol, duration)
        await asyncio.wait_for(
            asyncio.to_thread(asset_client.subscribe_strike_list, symbol, duration),
            timeout=5,
        )
        subscribed = True
        quotes = await asyncio.wait_for(
            asyncio.to_thread(_wait_for_strikes, asset_client, symbol, duration),
            timeout=STRIKE_TIMEOUT_SECONDS + 2,
        )
        if not quotes:
            raise HTTPException(
                status_code=504,
                detail=(
                    f"A IQ Option não enviou o evento client-price-generated com a grade digital "
                    f"de {duration} minutos para {symbol}. Verifique se esse ativo "
                    "tem opções digitais abertas nesse vencimento ou tente outro ativo."
                ),
            )
        return quotes
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="A consulta de strikes digitais da IQ Option excedeu o tempo limite.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar strikes digitais: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc
    finally:
        if subscribed:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(asset_client.unsubscribe_strike_list, symbol, duration),
                    timeout=4,
                )
            except Exception:
                logger.warning("Não foi possível cancelar a assinatura de strikes para %s/%s", symbol, duration)


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    return await _load_assets(_get_session(x_iq_session))


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
    available = {asset["symbol"] for asset in catalog["assets"]}
    if symbol not in available:
        raise HTTPException(
            status_code=400,
            detail=f"O ativo {symbol} não está no catálogo atual da IQ Option.",
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
    # Prefere o close da vela M1 ainda em formação, que é a melhor referência
    # disponível na resposta de candles para comparar os strikes ao preço atual.
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

    quotes = await _digital_strikes(item, symbol, horizon)
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
