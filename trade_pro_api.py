"""API da ferramenta TRADE-PRÓ.

Somente lê candles e publica análise. Não contém endpoints de compra/venda de ordens.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from trade_pro_auth import _get_session
from trade_pro_engine import TIMEFRAMES, analyze

router = APIRouter(prefix="/api/trade-pro", tags=["TRADE-PRÓ"])
logger = logging.getLogger("resolvei.trade_pro")

CANDLE_COUNT = 180
MIN_CLOSED_CANDLES = 80
CANDLE_TIMEOUT_SECONDS = 12
ASSET_CACHE_TTL_SECONDS = 60


class TradeProAnalyzeRequest(BaseModel):
    symbol: str
    timeframe: str = "1m"


def _asset_cache(item: dict[str, Any]) -> dict[str, Any]:
    return item.setdefault("asset_cache", {"at": 0.0, "data": None})


async def _ensure_connection(item: dict[str, Any]) -> None:
    client = item["client"]
    ws = getattr(client, "_ws", None)
    if ws is None:
        await client.connect()
        return
    if bool(getattr(ws, "_closed", False)):
        try:
            await client.close()
        except Exception:
            pass
        await client.connect()


async def _load_assets(item: dict[str, Any]) -> dict[str, Any]:
    cache = _asset_cache(item)
    now = time.time()
    if cache["data"] is not None and now - cache["at"] < ASSET_CACHE_TTL_SECONDS:
        return cache["data"]

    try:
        asset_client = item.get("asset_client")
        if asset_client is None:
            from iqoptionapi.stable_api import IQ_Option

            ws = getattr(item["client"], "_ws", None)
            ssid = getattr(ws, "_ssid", None)
            if not ssid:
                raise RuntimeError("SSID da sessão IQ Option não está disponível.")

            asset_client = IQ_Option(
                getattr(item["client"], "_email", ""),
                getattr(item["client"], "_password", ""),
                set_ssid=ssid,
                auto_logout=False,
            )
            connected = await asyncio.wait_for(
                asyncio.to_thread(asset_client.connect), timeout=12
            )
            if isinstance(connected, tuple) and connected and connected[0] is False:
                reason = connected[1] if len(connected) > 1 else "conexão recusada"
                raise RuntimeError(str(reason))
            item["asset_client"] = asset_client

        opcode = await asyncio.wait_for(
            asyncio.to_thread(asset_client.get_all_ACTIVES_OPCODE), timeout=5
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="A IQ Option demorou para disponibilizar o catálogo de ativos.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar ativos da IQ Option: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc

    if not isinstance(opcode, dict) or not opcode:
        raise HTTPException(status_code=502, detail="A IQ Option não retornou ativos.")

    assets = []
    for name, active_id in opcode.items():
        symbol = str(name).strip()
        if symbol:
            assets.append({"symbol": symbol, "activeId": active_id})

    assets.sort(key=lambda asset: asset["symbol"])
    data = {"assets": assets, "total": len(assets), "updatedAt": int(now)}
    cache["at"] = now
    cache["data"] = data
    return data


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    return await _load_assets(_get_session(x_iq_session))


@router.get("/config")
async def config(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    _get_session(x_iq_session)
    return {
        "timeframes": [
            {"id": "1m", "label": "M1", "seconds": 60},
            {"id": "5m", "label": "M5", "seconds": 300},
            {"id": "15m", "label": "M15", "seconds": 900},
        ],
        "expirations": [1, 5, 15],
        "minimumConfluence": 72,
        "executionEnabled": False,
    }


@router.post("/analyze")
async def run(
    req: TradeProAnalyzeRequest,
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    symbol = req.symbol.strip()
    timeframe = req.timeframe

    if timeframe not in TIMEFRAMES:
        raise HTTPException(status_code=400, detail="Timeframe deve ser 1m, 5m ou 15m.")
    if not symbol:
        raise HTTPException(status_code=400, detail="Selecione um ativo.")

    catalog = await _load_assets(item)
    available = {asset["symbol"] for asset in catalog["assets"]}
    if symbol not in available:
        raise HTTPException(
            status_code=400,
            detail=f"O ativo {symbol} não está no catálogo atual da IQ Option.",
        )

    interval_seconds = TIMEFRAMES[timeframe]
    try:
        await _ensure_connection(item)
        raw = await asyncio.wait_for(
            item["client"].get_candles(
                symbol, interval_seconds, CANDLE_COUNT, int(time.time())
            ),
            timeout=CANDLE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"A IQ Option não respondeu aos candles de {symbol} em {CANDLE_TIMEOUT_SECONDS}s.",
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"O ativo {symbol} não está disponível para candles nessa sessão.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao obter candles da IQ Option: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc

    rows: list[dict[str, Any]] = []
    for candle in raw or []:
        try:
            timestamp = float(candle.get("from", candle.get("to", 0)))
            volume_raw = candle.get("volume")
            volume = float(volume_raw) if volume_raw is not None else None
            rows.append(
                {
                    "time": timestamp,
                    "open": float(candle["open"]),
                    "high": float(candle.get("max", candle.get("high"))),
                    "low": float(candle.get("min", candle.get("low"))),
                    "close": float(candle["close"]),
                    "volume": volume,
                }
            )
        except (TypeError, ValueError, KeyError):
            continue

    rows.sort(key=lambda row: row["time"])
    now = time.time()
    closed = [
        row for row in rows
        if row["time"] + interval_seconds <= now + 0.2
    ]
    closed = list({row["time"]: row for row in closed}.values())
    closed.sort(key=lambda row: row["time"])

    if len(closed) < MIN_CLOSED_CANDLES:
        raise HTTPException(
            status_code=502,
            detail=(
                f"A IQ Option retornou {len(closed)} candles fechados para {symbol}; "
                f"são necessários pelo menos {MIN_CLOSED_CANDLES}."
            ),
        )

    try:
        result = await asyncio.to_thread(analyze, closed[-CANDLE_COUNT:], timeframe)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Erro no motor TRADE-PRÓ para %s", symbol)
        raise HTTPException(
            status_code=502,
            detail=f"Falha no motor de análise: {type(exc).__name__}: {str(exc)[:200]}",
        ) from exc

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    result.update(
        {
            "ok": True,
            "symbol": symbol,
            "timestamp": timestamp,
            "candle_time": int(closed[-1]["time"]),
            "timeframe": timeframe,
            "execution_enabled": False,
        }
    )

    # Um sinal é registrado no máximo uma vez por candle, mesmo no modo automático.
    if result["signal"] in {"COMPRA", "VENDA"}:
        log_key = f"{symbol}|{timeframe}"
        last_logged = item.setdefault("last_logged_candle", {})
        candle_key = int(closed[-1]["time"])
        if last_logged.get(log_key) != candle_key:
            logger.info(
                "[%s] | %s | SINAL: %s | EXPIRAÇÃO: %s MINUTOS | MOTIVO: %s | CONFLUÊNCIA: %s%%",
                timestamp,
                symbol,
                result["signal"],
                result["expiration_minutes"],
                result["reason"],
                result["confluence"],
            )
            last_logged[log_key] = candle_key

    return result
