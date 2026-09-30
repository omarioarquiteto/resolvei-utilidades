from __future__ import annotations

import asyncio
import math
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/guru-sinais-binomo", tags=["GURÚ DOS SINAIS BINOMO"])

SESSION_TTL_SECONDS = 30 * 60
LOGIN_TIMEOUT_SECONDS = 40
REQUEST_TIMEOUT_SECONDS = 15
CANDLE_API = "https://api.binomo.com/candles/v1"

NATIVE_TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}
DERIVED_TIMEFRAMES = {"4h": ("30m", 14400)}
CHUNK_SECONDS = {
    60: 24 * 60 * 60,
    300: 4 * 24 * 60 * 60,
    900: 12 * 24 * 60 * 60,
    1800: 24 * 24 * 60 * 60,
    3600: 24 * 24 * 60 * 60,
}
SESSIONS: dict[str, dict[str, Any]] = {}


class LoginRequest(BaseModel):
    email: str
    password: str


class MarketAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str = "automatica"
    analyze_with_ai: bool = False


def _binomo_class():
    try:
        from BinomoAPI.api import BinomoAPI
        return BinomoAPI
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"BinomoAPI indisponível: {exc}") from exc


def _asset_payload(asset: Any) -> dict[str, Any]:
    return {
        "name": str(getattr(asset, "name", "")).strip(),
        "ric": str(getattr(asset, "ric", "")).strip(),
        "otc": bool(getattr(asset, "is_otc", False)),
        "active": bool(getattr(asset, "is_active", True)),
    }


def _cleanup_sessions() -> None:
    now = time.time()
    for sid, item in list(SESSIONS.items()):
        if now - float(item.get("last_used", 0)) <= SESSION_TTL_SECONDS:
            continue
        session = item.get("http_session")
        try:
            if session is not None:
                session.close()
        except Exception:
            pass
        SESSIONS.pop(sid, None)


def _session(x_binomo_session: str | None) -> dict[str, Any]:
    _cleanup_sessions()
    sid = (x_binomo_session or "").strip()
    item = SESSIONS.get(sid)
    if not item:
        raise HTTPException(status_code=401, detail="Sessão Binomo ausente ou expirada.")
    item["last_used"] = time.time()
    return item


def _login_sync(email: str, password: str):
    BinomoAPI = _binomo_class()
    response = BinomoAPI.login(email, password)
    token = getattr(response, "authtoken", "")
    if not token:
        raise RuntimeError("A Binomo não retornou um token de autenticação.")
    return response


@router.post("/login")
async def login(req: LoginRequest):
    email = req.email.strip()
    if not email or not req.password:
        raise HTTPException(status_code=400, detail="Informe e-mail e senha.")
    try:
        login_response = await asyncio.wait_for(
            asyncio.to_thread(_login_sync, email, req.password),
            timeout=LOGIN_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="A autenticação com a Binomo excedeu o tempo limite.") from exc
    except Exception as exc:
        text = str(exc)
        low = text.lower()
        code = 401 if ("401" in low or "invalid email" in low or "password" in low) else 502
        raise HTTPException(status_code=code, detail=text[:500]) from exc

    BinomoAPI = _binomo_class()
    assets = [_asset_payload(x) for x in BinomoAPI.get_assets()]
    sid = secrets.token_urlsafe(32)
    http_session = getattr(login_response, "_session", None)
    SESSIONS[sid] = {
        "email": email,
        "login": login_response,
        "http_session": http_session,
        "last_used": time.time(),
    }
    balance = getattr(login_response, "balance", None)
    return {
        "ok": True,
        "session_id": sid,
        "connected": True,
        "demo": True,
        "assets": assets,
        "balance": float(balance) / 100 if balance is not None else None,
    }


@router.get("/session")
async def session_status():
    return {"ok": True, "connected": True, "market_data": "Binomo candles API", "login_required": False}


@router.get("/assets")
async def assets():
    BinomoAPI = _binomo_class()
    all_assets = [_asset_payload(x) for x in BinomoAPI.get_assets()]
    return {
        "ok": True,
        "normal": [x for x in all_assets if not x["otc"]],
        "otc": [x for x in all_assets if x["otc"]],
    }


def _format_api_timestamp(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chunk_seconds(seconds: int) -> int:
    return CHUNK_SECONDS.get(seconds, 24 * 60 * 60)


def _history_url(ric: str, seconds: int, cursor_ms: int) -> str:
    return f"{CANDLE_API}/{quote(ric, safe='')}/{_format_api_timestamp(cursor_ms)}/{seconds}?locale=en"


def _parse_history_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RuntimeError("A Binomo não retornou um conjunto de candles válido.")
    return [x for x in payload["data"] if isinstance(x, dict)]


def _normalize_candle(item: dict[str, Any], seconds: int) -> dict[str, float] | None:
    try:
        opening = float(item["open"])
        high = float(item["high"])
        low = float(item["low"])
        close = float(item["close"])
        created_at = str(item["created_at"])
        closing_ms = int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp() * 1000)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(x) for x in (opening, high, low, close)) or not math.isfinite(closing_ms):
        return None
    if high < max(opening, close) or low > min(opening, close):
        return None
    return {
        "open": opening,
        "high": high,
        "low": low,
        "close": close,
        "volume": 0.0,
        "datetime": str(closing_ms - seconds * 1000),
    }


def _request_history_chunk(ric: str, seconds: int, cursor_ms: int) -> list[dict[str, float]]:
    url = _history_url(ric, seconds, cursor_ms)
    last_status = 0
    last_text = ""
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Resolvei/3.0 (Binomo market study)",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            last_status = response.status_code
            last_text = response.text[:250]
            if response.ok:
                raw = _parse_history_payload(response.json())
                out = []
                for item in raw:
                    candle = _normalize_candle(item, seconds)
                    if candle is not None:
                        out.append(candle)
                return out
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
        except requests.RequestException as exc:
            last_text = str(exc)
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Binomo candle request failed with HTTP {last_status}: {last_text}")


def _fetch_native_history(ric: str, timeframe: str, limit: int = 1000) -> list[dict[str, float]]:
    seconds = NATIVE_TIMEFRAMES[timeframe]
    now_ms = int(time.time() * 1000)
    chunk_ms = _chunk_seconds(seconds) * 1000
    cursor_ms = (now_ms // chunk_ms) * chunk_ms
    from_ms = max(0, now_ms - limit * seconds * 1000)
    candles: dict[str, dict[str, float]] = {}

    for _ in range(12):
        batch = _request_history_chunk(ric, seconds, cursor_ms)
        if not batch:
            break

        oldest_ms = None
        for candle in batch:
            open_ms = int(float(candle["datetime"]))
            candles[str(open_ms)] = candle
            oldest_ms = open_ms if oldest_ms is None else min(oldest_ms, open_ms)

        if oldest_ms is None or oldest_ms <= from_ms or len(candles) >= limit:
            break

        next_cursor = ((oldest_ms // chunk_ms) * chunk_ms) - chunk_ms
        if next_cursor >= cursor_ms:
            break
        cursor_ms = next_cursor

    rows = []
    for key, candle in candles.items():
        if from_ms <= int(key) <= now_ms:
            rows.append(candle)
    rows.sort(key=lambda x: int(float(x["datetime"])))
    return rows[-limit:]


def _resample(rows: list[dict[str, float]], source_seconds: int, target_seconds: int) -> list[dict[str, float]]:
    if target_seconds <= source_seconds or target_seconds % source_seconds:
        return rows
    step = target_seconds // source_seconds
    out = []
    for i in range(0, len(rows), step):
        chunk = rows[i:i + step]
        if len(chunk) < step:
            continue
        out.append({
            "open": chunk[0]["open"],
            "high": max(x["high"] for x in chunk),
            "low": min(x["low"] for x in chunk),
            "close": chunk[-1]["close"],
            "volume": sum(x.get("volume", 0.0) for x in chunk),
            "datetime": chunk[-1].get("datetime", ""),
        })
    return out


def _fetch_timeframe(ric: str, timeframe: str) -> list[dict[str, float]]:
    if timeframe in NATIVE_TIMEFRAMES:
        return _fetch_native_history(ric, timeframe, 1000)
    base_tf, target_seconds = DERIVED_TIMEFRAMES[timeframe]
    base_rows = _fetch_native_history(ric, base_tf, 1000)
    return _resample(base_rows, NATIVE_TIMEFRAMES[base_tf], target_seconds)


async def _fetch_mtf(ric: str, timeframe: str) -> tuple[dict[str, list[dict[str, float]]], tuple[str, str, str]]:
    from guru_sinais_api import _mtf_plan
    context_tf, setup_tf, trigger_tf = _mtf_plan(timeframe)
    needed = []
    for tf in (context_tf, setup_tf, trigger_tf):
        if tf not in needed:
            needed.append(tf)
    results = await asyncio.gather(*(asyncio.to_thread(_fetch_timeframe, ric, tf) for tf in needed))
    rows = dict(zip(needed, results))
    missing = [tf for tf in needed if len(rows.get(tf, [])) < 60]
    if missing:
        raise RuntimeError("A Binomo retornou histórico insuficiente para: " + ", ".join(missing) + ".")
    return rows, (context_tf, setup_tf, trigger_tf)


def _engine(symbol, timeframe, strategy, mtf, plan, analyze_with_ai, authorization):
    from guru_sinais_api import _gemini_review, _mtf_score, _strategy_pack

    context_tf, setup_tf, trigger_tf = plan
    families = ("tendencia", "reversao", "rompimento")
    context = [_strategy_pack(mtf[context_tf], s) for s in families]
    setup = [_strategy_pack(mtf[setup_tf], s) for s in families]
    trigger = [_strategy_pack(mtf[trigger_tf], s) for s in families]

    if strategy == "automatica":
        candidates = []
        for s in setup:
            c = next(x for x in context if x["strategy"] == s["strategy"])
            t = next(x for x in trigger if x["strategy"] == s["strategy"])
            signal, score, _ = _mtf_score(c, s, t)
            candidates.append((score if signal != "AGUARDAR" else 0, s))
        selected = max(candidates, key=lambda x: x[0])[1]
    else:
        selected = next((x for x in setup if x["strategy"] == strategy), None)
        if not selected:
            raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    ctx = next(x for x in context if x["strategy"] == selected["strategy"])
    trg = next(x for x in trigger if x["strategy"] == selected["strategy"])
    base_signal, base_conf, mtf_notes = _mtf_score(ctx, selected, trg)

    gemini = _gemini_review(
        symbol,
        f"{context_tf} → {setup_tf} → {trigger_tf}",
        selected["strategy"],
        setup,
        mtf[setup_tf][-1]["close"],
        mtf[setup_tf],
        authorization,
    ) if analyze_with_ai else {"available": False, "reason": "Análise com IA desativada."}

    gem_signal = gemini.get("signal")
    gem_conf = float(gemini.get("confidence", 0)) if gem_signal else 0.0

    if base_signal in {"CALL", "PUT"} and gem_signal == base_signal:
        signal = base_signal
        score = round(min(99, .72 * base_conf + .28 * gem_conf))
        quality = "MUITO FORTE" if score >= 82 else "FORTE" if score >= 72 else "MODERADA"
    elif base_signal in {"CALL", "PUT"} and gem_signal in {"CALL", "PUT"}:
        signal = base_signal
        score = round(max(50, min(90, .82 * base_conf + .18 * gem_conf - 8)))
        quality = "CONFLUÊNCIA PARCIAL"
    else:
        signal = base_signal
        score = round(base_conf)
        quality = "FORTE" if score >= 75 else "MODERADA" if score >= 65 else "BAIXA"

    reasons = [
        f"Contexto {context_tf}: {ctx['direction']} com {ctx['confidence']:.0f}% de confluência.",
        f"Setup {setup_tf}: {selected['direction']} com {selected['confidence']:.0f}% de confluência.",
        f"Gatilho {trigger_tf}: {trg['direction']} com {trg['confidence']:.0f}% de confluência.",
    ] + mtf_notes
    if gemini.get("available"):
        reasons.append("Gemini: " + (gemini.get("reason") or "validação concluída."))

    warnings = []
    if ctx["direction"] in {"CALL", "PUT"} and selected["direction"] in {"CALL", "PUT"} and ctx["direction"] != selected["direction"]:
        warnings.append("Contexto e setup estão em direções opostas.")
    if trg["direction"] in {"CALL", "PUT"} and selected["direction"] in {"CALL", "PUT"} and trg["direction"] != selected["direction"]:
        warnings.append("O gatilho e o setup estão em direções diferentes.")
    if signal == "AGUARDAR":
        warnings.append("Sem alinhamento suficiente entre contexto, setup e gatilho.")

    return {
        "signal": signal,
        "score": score,
        "quality": quality,
        "symbol": symbol,
        "timeframe": timeframe,
        "analysisTimeframes": {"context": context_tf, "setup": setup_tf, "trigger": trigger_tf},
        "price": mtf[setup_tf][-1]["close"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "buyScore": selected["buy"],
        "sellScore": selected["sell"],
        "reasons": reasons[:10],
        "warnings": warnings[:8],
        "strategy": selected["strategy"],
        "strategyLabel": selected["strategyLabel"],
        "strategies": setup,
        "mtf": {
            "context": {"timeframe": context_tf, "direction": ctx["direction"], "confidence": ctx["confidence"]},
            "setup": {"timeframe": setup_tf, "direction": selected["direction"], "confidence": selected["confidence"]},
            "trigger": {"timeframe": trigger_tf, "direction": trg["direction"], "confidence": trg["confidence"]},
            "score": base_conf,
            "notes": mtf_notes,
        },
        "gemini": gemini,
        "indicators": selected["values"],
        "source": "Binomo Candles API + motor técnico MTF + Gemini",
    }


@router.post("/market-analysis")
async def market_analysis(
    req: MarketAnalysisRequest,
    authorization: str | None = Header(default=None),
):
    if req.timeframe not in NATIVE_TIMEFRAMES and req.timeframe not in DERIVED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")

    BinomoAPI = _binomo_class()
    assets = BinomoAPI.get_assets()
    target = next(
        (a for a in assets if str(getattr(a, "name", "")).strip().lower() == req.symbol.strip().lower()),
        None,
    )
    if target is None:
        target = next(
            (a for a in assets if str(getattr(a, "ric", "")).strip().lower() == req.symbol.strip().lower()),
            None,
        )
    if target is None:
        raise HTTPException(status_code=400, detail="Ativo Binomo não encontrado.")

    ric = str(getattr(target, "ric", "")).strip()
    try:
        mtf, plan = await _fetch_mtf(ric, req.timeframe)
        analysis = _engine(req.symbol.strip(), req.timeframe, req.strategy, mtf, plan, req.analyze_with_ai, authorization)
        return {"ok": True, "analysis": analysis}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:600]) from exc


@router.post("/logout")
async def logout(x_binomo_session: str | None = Header(default=None)):
    sid = (x_binomo_session or "").strip()
    item = SESSIONS.pop(sid, None)
    if item:
        try:
            session = item.get("http_session")
            if session is not None:
                session.close()
        except Exception:
            pass
    return {"ok": True}
