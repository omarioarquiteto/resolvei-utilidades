"""API somente-leitura do VIBE LUCRO, com sessão IQ Option exclusiva."""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Literal

import requests

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import guru_sinais_iqoption_api as iq_marketdata
import vibe_lucro_auth as auth
from vibe_lucro_engine import analyze

router = APIRouter(prefix="/api/vibe-lucro", tags=["VIBE LUCRO"])

EXPIRIES = (1, 5, 15)
CANDLE_COUNTS = {"1m": 220, "5m": 160, "15m": 110}
VIBE_TRADING_API_URL = os.getenv("VIBE_TRADING_API_URL", "").strip().rstrip("/")
VIBE_TRADING_API_KEY = os.getenv("VIBE_TRADING_API_KEY", "").strip()
VIBE_TRADING_CONNECT_TIMEOUT = 90.0  # allow the Render Free instance to wake from sleep
VIBE_TRADING_REVIEW_TIMEOUT = 32.0


class AnalyzeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    symbol: str = Field(min_length=3, max_length=32)
    expiry_minutes: Literal[1, 5, 15] = 5



def _vibe_trading_configured() -> bool:
    return bool(VIBE_TRADING_API_URL and VIBE_TRADING_API_KEY)


def _call_vibe_trading_review(
    symbol: str,
    expiry_minutes: int,
    analysis: dict[str, Any],
    frames: dict[str, list[dict[str, float]]],
) -> dict[str, Any]:
    """Send bounded, sanitized market evidence to an optional Vibe-Trading review.

    IQ Option passwords, session tokens, user identity and account information
    are never part of this payload.
    """
    if not _vibe_trading_configured():
        return {
            "configured": False,
            "available": False,
            "message": "Servidor Vibe-Trading ainda não configurado; análise quantitativa local disponível.",
        }

    safe_candles: dict[str, list[dict[str, float]]] = {}
    for timeframe in ("1m", "5m", "15m"):
        safe_candles[timeframe] = [
            {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume") or 0),
                "timestamp": float(row.get("datetime", row.get("time", 0)) or 0),
            }
            for row in frames.get(timeframe, [])[-30:]
        ]

    payload = {
        "symbol": symbol,
        "expiry_minutes": expiry_minutes,
        "signal": analysis["signal"],
        "score": analysis["score"],
        "buy_score": analysis["buy_score"],
        "sell_score": analysis["sell_score"],
        "reasons": list(analysis.get("reasons") or [])[:8],
        "timeframes": analysis.get("timeframes") or {},
        "candles": safe_candles,
    }
    try:
        response = requests.post(
            VIBE_TRADING_API_URL + "/api/vibe-lucro/analyze",
            headers={"Authorization": "Bearer " + VIBE_TRADING_API_KEY},
            json=payload,
            timeout=(VIBE_TRADING_CONNECT_TIMEOUT, VIBE_TRADING_REVIEW_TIMEOUT),
        )
        response.raise_for_status()
        data = response.json()
        review = str(data.get("review") or "").strip()
        if not review:
            raise ValueError("Vibe-Trading retornou uma revisão vazia.")
        return {
            "configured": True,
            "available": True,
            "review": review[:6000],
            "provider": str(data.get("provider") or "Vibe-Trading"),
            "model": str(data.get("model") or ""),
            "direction_override": False,
            "message": "Revisão complementar; não altera o sinal quantitativo.",
        }
    except Exception as exc:
        return {
            "configured": True,
            "available": False,
            "message": "Revisão de IA indisponível: " + f"{type(exc).__name__}: {str(exc)[:180]}",
        }


def _resolve_session(session_id: str | None) -> dict[str, Any]:
    """Resolve only the VIBE LUCRO-owned session store."""
    return auth._get_session(session_id)


def _valid_symbol(symbol: str) -> str:
    clean = str(symbol or "").strip().upper()
    if not clean:
        raise HTTPException(status_code=400, detail="Selecione um ativo.")
    catalog = iq_marketdata._asset_list()
    symbols = {
        str(item.get("symbol") or "").upper()
        for group in (catalog.get("normal") or [], catalog.get("otc") or [])
        for item in group
    }
    if clean not in symbols:
        raise HTTPException(status_code=400, detail=f"O ativo {clean} não está no catálogo da IQ Option.")
    return clean


@router.get("/status")
async def status(x_iq_session: str | None = Header(default=None, alias="X-IQ-Session")) -> dict[str, Any]:
    item = _resolve_session(x_iq_session)
    return {
        "ok": True,
        "connected": True,
        "session_source": "VIBE LUCRO · sessão exclusiva",
        "exclusive": True,
        "expiries": list(EXPIRIES),
        "vibe_trading_agent": {
            "configured": _vibe_trading_configured(),
            "message": (
                "Servidor Vibe-Trading configurado para revisão complementar."
                if _vibe_trading_configured()
                else "Servidor Vibe-Trading ainda não configurado; análise quantitativa local disponível."
            ),
            "read_only": True,
        },
        "read_only": True,
    }


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None, alias="X-IQ-Session")) -> dict[str, Any]:
    _resolve_session(x_iq_session)
    return iq_marketdata._asset_list()


@router.post("/analyze")
async def run_analysis(
    request: AnalyzeRequest,
    x_iq_session: str | None = Header(default=None, alias="X-IQ-Session"),
) -> dict[str, Any]:
    sid = (x_iq_session or "").strip()
    item = _resolve_session(sid)
    symbol = _valid_symbol(request.symbol)
    client = item["client"]

    async def load(timeframe: str) -> tuple[str, list[dict[str, float]]]:
        rows = await iq_marketdata._candles(
            client,
            sid,
            symbol,
            timeframe,
            CANDLE_COUNTS[timeframe],
            include_forming=False,
            cache_ttl=1.5,
            request_timeout=10.0,
        )
        return timeframe, rows

    try:
        results = await asyncio.gather(*(load(tf) for tf in ("1m", "5m", "15m")))
        frames = {timeframe: rows for timeframe, rows in results}
        analysis = analyze(frames, symbol, request.expiry_minutes, now=time.time())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Não foi possível concluir a análise dos candles de {symbol}: {type(exc).__name__}: {str(exc)[:180]}",
        ) from exc

    analysis["source"] = "IQ Option · sessão exclusiva do VIBE LUCRO · motor quantitativo"
    analysis["connection_reused"] = False
    analysis["exclusive_session"] = True
    analysis["vibe_trading_review"] = await asyncio.to_thread(
        _call_vibe_trading_review,
        symbol,
        request.expiry_minutes,
        analysis,
        frames,
    )
    return {"ok": True, "analysis": analysis, "read_only": True}
