from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from analista_bin_engine import STRATEGIES, analyze
from analista_bin_auth import _get_session

router = APIRouter(prefix="/api/analista-bin", tags=["ANALISTA BIN"])

INTERVALS = {"1m": 60, "5m": 300}
CANDLE_COUNT = 260
MIN_CLOSED_CANDLES = 220
CANDLE_REQUEST_TIMEOUT = 12
ASSET_CACHE_TTL = 30


class Req(BaseModel):
    symbol: str
    timeframe: str = "1m"
    strategy: str = "trend"


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

    await _ensure_connection(item)
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(item["client"].get_all_open_time),
            15,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="A IQ Option demorou para atualizar a lista de ativos.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar os ativos da IQ Option: {str(exc)[:180]}") from exc

    groups = {}
    for kind, values in (raw or {}).items():
        if not isinstance(values, dict):
            continue
        assets = []
        for symbol, info in values.items():
            if not isinstance(info, dict):
                continue
            symbol = str(symbol).strip()
            if symbol:
                assets.append({"symbol": symbol, "open": bool(info.get("open", False))})
        assets.sort(key=lambda x: (not x["open"], x["symbol"]))
        if assets:
            groups[str(kind)] = assets

    if not groups:
        raise HTTPException(status_code=502, detail="A IQ Option não retornou nenhum ativo disponível nesta sessão.")

    data = {
        "groups": groups,
        "updatedAt": int(now),
        "total": sum(len(v) for v in groups.values()),
    }
    cache["at"] = now
    cache["data"] = data
    return data


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None)):
    return await _load_assets(_get_session(x_iq_session))


@router.get("/config")
async def config(x_iq_session: str | None = Header(default=None)):
    _get_session(x_iq_session)
    return {
        "strategies": {k: v["name"] for k, v in STRATEGIES.items()},
        "weights": {k: v["weights"] for k, v in STRATEGIES.items()},
    }


@router.post("/analyze")
async def run(req: Req, x_iq_session: str | None = Header(default=None)):
    item = _get_session(x_iq_session)

    if req.timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Timeframe deve ser 1m ou 5m.")
    if req.strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail="Estratégia inválida.")

    symbol = req.symbol.upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Informe o par para análise.")

    interval = INTERVALS[req.timeframe]

    catalog = await _load_assets(item)
    known = {a["symbol"] for values in catalog["groups"].values() for a in values}
    if symbol not in known:
        raise HTTPException(status_code=400, detail=f"O ativo {symbol} não está presente no catálogo atual da IQ Option.")

    try:
        await _ensure_connection(item)
        raw = await asyncio.wait_for(
            item["client"].get_candles(symbol, interval, CANDLE_COUNT, int(time.time())),
            CANDLE_REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"A IQ Option não respondeu aos candles de {symbol} dentro de {CANDLE_REQUEST_TIMEOUT}s.") from exc
    except KeyError as exc:
        raise HTTPException(status_code=502, detail=f"O par {symbol} não está disponível na tabela de ativos da IQ Option.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao obter candles da IQ Option: {str(exc)[:180]}") from exc

    rows = []
    for candle in raw or []:
        try:
            rows.append({
                "time": float(candle.get("from", candle.get("to", 0))),
                "open": float(candle["open"]),
                "high": float(candle.get("max", candle.get("high"))),
                "low": float(candle.get("min", candle.get("low"))),
                "close": float(candle["close"]),
                "volume": float(candle.get("volume") or 1),
            })
        except (TypeError, ValueError, KeyError):
            continue

    rows.sort(key=lambda x: x["time"])
    now = time.time()
    closed = [row for row in rows if row["time"] + interval <= now + 0.2]

    if len(closed) < MIN_CLOSED_CANDLES and len(rows) >= MIN_CLOSED_CANDLES:
        closed = rows[:-1]

    if len(closed) < MIN_CLOSED_CANDLES:
        raise HTTPException(
            status_code=502,
            detail=f"A IQ Option retornou {len(closed)} candles fechados para {symbol}; são necessários pelo menos {MIN_CLOSED_CANDLES}.",
        )

    try:
        result = await asyncio.to_thread(analyze, closed[-CANDLE_COUNT:], req.strategy)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha no motor de análise: {type(exc).__name__}: {str(exc)[:220]}") from exc

    result.update({
        "ok": True,
        "symbol": symbol,
        "timeframe": req.timeframe,
        "candleTime": closed[-1]["time"],
        "nextCandleAt": ((int(now) // interval) + 1) * interval,
    })
    return result
