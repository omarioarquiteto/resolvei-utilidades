from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import guru_sinais_iqoption_api as iq
import guru_sinais_api as base

router = APIRouter(prefix="/api/laboratorio-iqoption", tags=["LABORATÓRIO ESTATÍSTICO IQOPTION"])

LAB_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
LAB_BACKTEST_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class LoginRequest(BaseModel):
    email: str
    password: str


def _session(x_iq_session: str | None) -> dict[str, Any]:
    return iq._get_session(x_iq_session)


async def _login(req: LoginRequest) -> dict[str, Any]:
    # Reutiliza a mesma implementação de autenticação do GURÚ IQ Option.
    # Nenhuma senha é persistida pelo Laboratório.
    return await iq.iq_login(iq.IQLoginRequest(email=req.email, password=req.password))


async def _candles(item: dict[str, Any], sid: str, symbol: str, count: int = 1000) -> list[dict[str, float]]:
    return await iq._candles(
        item["client"],
        sid,
        symbol,
        "1m",
        min(max(int(count), 120), 1000),
        include_forming=False,
        cache_ttl=8.0,
        request_timeout=12.0,
    )


def _signal_from_pack(pack: dict[str, Any]) -> tuple[str, float]:
    direction = str(pack.get("direction") or "NEUTRA")
    confidence = float(pack.get("confidence") or 0)
    eligible = bool(pack.get("signalEligible", False))
    if direction not in {"CALL", "PUT"} or not eligible:
        return "AGUARDAR", confidence
    return direction, confidence


def _historical(rows: list[dict[str, float]], expiry: int, strategy: str = "automatica") -> dict[str, Any]:
    expiry = 1 if int(expiry) == 1 else 5
    step = expiry
    occurrences: list[dict[str, Any]] = []

    # 1m candles: entrada hipotética no candle seguinte ao sinal.
    for idx in range(60, len(rows) - expiry - 1, step):
        cut = rows[:idx + 1]
        selected = base_strategy = (
            iq._select_auto_strategy(cut)
            if strategy == "automatica"
            else strategy
        )
        try:
            pack = iq._iq_strategy_pack(cut, selected)
        except Exception:
            continue

        signal, confidence = _signal_from_pack(pack)
        if signal not in {"CALL", "PUT"} or confidence < 64:
            continue

        entry = rows[idx + 1]
        exit_row = rows[idx + expiry]
        entry_price = float(entry["open"])
        exit_price = float(exit_row["close"])
        if signal == "CALL":
            win = exit_price > entry_price
        else:
            win = exit_price < entry_price
        tie = abs(exit_price - entry_price) <= max(abs(entry_price) * 1e-10, 1e-12)

        occurrences.append({
            "signal": signal,
            "confidence": round(confidence, 1),
            "strategy": selected,
            "entryPrice": entry_price,
            "exitPrice": exit_price,
            "win": bool(win and not tie),
            "tie": bool(tie),
            "time": float(entry.get("datetime") or 0),
        })
        if len(occurrences) >= 200:
            break

    decisive = [x for x in occurrences if not x["tie"]]
    wins = sum(1 for x in decisive if x["win"])
    losses = max(0, len(decisive) - wins)
    accuracy = wins / len(decisive) * 100 if decisive else 0.0

    half = len(decisive) // 2
    older = decisive[:half]
    recent = decisive[half:]
    older_rate = sum(x["win"] for x in older) / len(older) * 100 if older else 0.0
    recent_rate = sum(x["win"] for x in recent) / len(recent) * 100 if recent else 0.0

    return {
        "available": True,
        "sample_size": len(decisive),
        "wins": wins,
        "losses": losses,
        "ties": len(occurrences) - len(decisive),
        "accuracy": round(accuracy, 1),
        "olderAccuracy": round(older_rate, 1),
        "recentAccuracy": round(recent_rate, 1),
        "consistent": len(older) >= 15 and len(recent) >= 15 and older_rate >= 50 and recent_rate >= 50,
        "expiry": expiry,
        "strategy": strategy,
        "history": ["OK" if x["win"] else "LOSS" for x in decisive[-40:]],
        "occurrences": occurrences[-20:],
        "note": "Backtest direcional sobre candles da IQ Option; não envia ordens.",
    }


@router.post("/login")
async def lab_login(req: LoginRequest) -> dict[str, Any]:
    return await _login(req)


@router.get("/session")
async def lab_session(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _session(x_iq_session)
    client = item["client"]
    ws = getattr(client, "_ws", None)
    connected = ws is not None and not bool(getattr(ws, "_closed", False))
    if not connected:
        raise HTTPException(401, "A conexão da IQ Option foi encerrada. Faça login novamente.")
    return {"ok": True, "connected": True}


@router.get("/assets")
async def lab_assets(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    _session(x_iq_session)
    assets = iq._asset_list()
    symbols = [x["symbol"] for group in (assets.get("normal", []), assets.get("otc", [])) for x in group]
    return {"ok": True, "assets": symbols, "normal": assets.get("normal", []), "otc": assets.get("otc", [])}


@router.post("/logout")
async def lab_logout(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    sid = (x_iq_session or "").strip()
    item = iq.SESSIONS.pop(sid, None)
    iq.ASSET_CACHE.pop(sid, None)
    for cache in (iq.CANDLE_CACHE, iq.BACKTEST_CACHE, LAB_CACHE, LAB_BACKTEST_CACHE):
        for key in list(cache):
            if key.startswith(sid + "|"):
                cache.pop(key, None)
    if item:
        try:
            await item["client"].close()
        except Exception:
            pass
    return {"ok": True}


@router.get("/analyze/{symbol}")
async def lab_analyze(symbol: str, expiry: str = "1min", x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _session(x_iq_session)
    sid = (x_iq_session or "").strip()
    expiry_minutes = 5 if expiry == "5min" else 1
    key = f"{sid}|{symbol.upper()}|{expiry_minutes}"
    cached = LAB_CACHE.get(key)
    if cached and time.time() - cached[0] < 8:
        return cached[1]

    rows = await _candles(item, sid, symbol, 300)
    selected = iq._select_auto_strategy(rows)
    pack = iq._iq_strategy_pack(rows, selected)
    direction, confidence = _signal_from_pack(pack)

    result = {
        "ok": True,
        "symbol": symbol.upper(),
        "expiry": f"{expiry_minutes}min",
        "payout": 85,
        "strategy": selected,
        "direction": direction,
        "confidence": round(confidence, 1),
        "price": rows[-1]["close"],
        "candles": len(rows),
        "indicators": pack.get("values", {}),
        "note": "Leitura atual dos indicadores. O Laboratório não executa ordens.",
    }
    LAB_CACHE[key] = (time.time(), result)
    return result


@router.get("/backtest/{symbol}")
async def lab_backtest(symbol: str, expiry: str = "1min", count: int = 1000, x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _session(x_iq_session)
    sid = (x_iq_session or "").strip()
    expiry_minutes = 5 if expiry == "5min" else 1
    count = min(max(int(count), 200), 1000)
    key = f"{sid}|{symbol.upper()}|{expiry_minutes}|{count}"
    cached = LAB_BACKTEST_CACHE.get(key)
    if cached and time.time() - cached[0] < 180:
        return cached[1]

    rows = await _candles(item, sid, symbol, count)
    result = _historical(rows, expiry_minutes)
    result["symbol"] = symbol.upper()
    result["candles"] = len(rows)
    result["payout"] = 85
    LAB_BACKTEST_CACHE[key] = (time.time(), result)
    return result
