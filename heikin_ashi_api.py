from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from heikin_ashi_auth import _get_session
from heikin_ashi_engine import INTERVALS, MIN_CANDLES, analyze

router = APIRouter(prefix="/api/heikin-ashi", tags=["HEIKIN-ASHI DIGITAL"])
CANDLE_COUNT = 320
CANDLE_REQUEST_TIMEOUT = 12
ASSET_CACHE_TTL = 60


class AnalyzeRequest(BaseModel):
    symbol: str
    timeframe: str = "1m"
    strategy: str = "auto"


def _asset_cache(item: dict) -> dict:
    return item.setdefault("asset_cache", {"at": 0.0, "data": None})


async def _ensure_connection(item: dict) -> None:
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


async def _load_assets(item: dict) -> dict:
    cache = _asset_cache(item)
    now = time.time()
    if cache["data"] is not None and now - cache["at"] < ASSET_CACHE_TTL:
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
            connect_result = await asyncio.wait_for(asyncio.to_thread(asset_client.connect), 12)
            if isinstance(connect_result, tuple) and connect_result and connect_result[0] is False:
                reason = connect_result[1] if len(connect_result) > 1 else "conexão recusada"
                raise RuntimeError(str(reason))
            item["asset_client"] = asset_client
        opcode = await asyncio.wait_for(asyncio.to_thread(asset_client.get_all_ACTIVES_OPCODE), 5)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="A IQ Option demorou para disponibilizar o catálogo de ativos.") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar o catálogo da IQ Option: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc
    if not isinstance(opcode, dict) or not opcode:
        raise HTTPException(status_code=502, detail="A IQ Option não retornou ativos para esta sessão.")
    assets = []
    for symbol, active_id in opcode.items():
        normalized = str(symbol).strip()
        if normalized:
            assets.append({"symbol": normalized, "open": True, "activeId": active_id})
    assets.sort(key=lambda asset: asset["symbol"])
    data = {"groups": {"all": assets}, "updatedAt": int(now), "total": len(assets)}
    cache["at"] = now
    cache["data"] = data
    return data


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None)):
    return await _load_assets(_get_session(x_iq_session))


@router.post("/analyze")
async def run(req: AnalyzeRequest, x_iq_session: str | None = Header(default=None)):
    item = _get_session(x_iq_session)
    if req.timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Expiração deve ser 1m, 5m ou 15m.")
    if req.strategy not in ("auto", "trend", "reversal"):
        raise HTTPException(status_code=400, detail="Estratégia inválida.")
    symbol = req.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Selecione um ativo.")

    catalog = await _load_assets(item)
    known = {
        asset["symbol"]
        for group in catalog["groups"].values()
        for asset in group
    }
    if symbol not in known:
        raise HTTPException(status_code=400, detail=f"O ativo {symbol} não está no catálogo atual da IQ Option.")

    interval = INTERVALS[req.timeframe]
    try:
        await _ensure_connection(item)
        raw = await asyncio.wait_for(
            item["client"].get_candles(symbol, interval, CANDLE_COUNT, int(time.time())),
            CANDLE_REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"A IQ Option não respondeu aos candles de {symbol} dentro de {CANDLE_REQUEST_TIMEOUT}s.",
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=502, detail=f"O par {symbol} não está disponível na IQ Option.") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao obter candles da IQ Option: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc

    rows: list[dict[str, Any]] = []
    for candle in raw or []:
        try:
            volume_value = candle.get("volume")
            rows.append({
                "time": float(candle.get("from", candle.get("to", 0))),
                "open": float(candle["open"]),
                "high": float(candle.get("max", candle.get("high"))),
                "low": float(candle.get("min", candle.get("low"))),
                "close": float(candle["close"]),
                "volume": float(volume_value) if volume_value is not None else None,
            })
        except (TypeError, ValueError, KeyError):
            continue

    rows.sort(key=lambda row: row["time"])
    now = time.time()
    closed = [row for row in rows if row["time"] + interval <= now + 0.2]
    if len(closed) < MIN_CANDLES:
        raise HTTPException(
            status_code=502,
            detail=(
                f"A IQ Option retornou {len(closed)} candles fechados para {symbol}; "
                f"são necessários pelo menos {MIN_CANDLES}. A vela em formação não será usada."
            ),
        )
    try:
        result = await asyncio.to_thread(analyze, closed[-CANDLE_COUNT:], req.timeframe, req.strategy, now)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha no motor Heikin-Ashi: {type(exc).__name__}: {str(exc)[:200]}",
        ) from exc
    result.update({
        "symbol": symbol,
        "candleTime": int(closed[-1]["time"]),
        "serverTime": int(now),
    })
    return result
