from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/guru-sinais-binomo", tags=["GURÚ DOS SINAIS BINOMO"])

SESSION_TTL_SECONDS = 30 * 60
LOGIN_TIMEOUT_SECONDS = 40
MARKET_TIMEOUT_SECONDS = 12
SESSIONS: dict[str, dict[str, Any]] = {}

TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}


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


def _cleanup_sessions():
    now = time.time()
    for sid, item in list(SESSIONS.items()):
        if now - float(item.get("last_used", 0)) > SESSION_TTL_SECONDS:
            SESSIONS.pop(sid, None)
            try:
                asyncio.create_task(item["client"].close())
            except Exception:
                pass


def _session(x_binomo_session: str | None):
    _cleanup_sessions()
    sid = (x_binomo_session or "").strip()
    item = SESSIONS.get(sid)
    if not item:
        raise HTTPException(status_code=401, detail="Sessão Binomo ausente ou expirada.")
    item["last_used"] = time.time()
    return item


def _asset(a: Any) -> dict[str, Any]:
    return {
        "name": str(getattr(a, "name", "")).strip(),
        "ric": str(getattr(a, "ric", "")).strip(),
        "otc": bool(getattr(a, "is_otc", False)),
        "active": bool(getattr(a, "is_active", True)),
    }


def _login_sync(email: str, password: str):
    BinomoAPI = _binomo_class()
    response = BinomoAPI.login(email, password)
    token = getattr(response, "authtoken", "")
    if not token:
        raise RuntimeError("A Binomo não retornou um token de autenticação.")
    client = BinomoAPI.create_from_login(
        login_response=response,
        demo=True,
        enable_logging=False,
    )
    return response, client


@router.post("/login")
async def login(req: LoginRequest):
    email = req.email.strip()
    if not email or not req.password:
        raise HTTPException(status_code=400, detail="Informe e-mail e senha.")
    try:
        login_response, client = await asyncio.wait_for(
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

    sid = secrets.token_urlsafe(32)
    assets = [_asset(x) for x in client.get_assets()]
    SESSIONS[sid] = {"client": client, "email": email, "last_used": time.time()}
    return {
        "ok": True,
        "session_id": sid,
        "connected": True,
        "demo": True,
        "assets": assets,
        "balance": (
            float(getattr(login_response, "balance")) / 100
            if getattr(login_response, "balance", None) is not None
            else None
        ),
    }


@router.get("/session")
async def session_status(x_binomo_session: str | None = Header(default=None)):
    item = _session(x_binomo_session)
    client = item["client"]
    ws = getattr(client, "_ws_client", None)
    return {
        "ok": True,
        "connected": True,
        "market_socket": bool(ws and getattr(ws, "_connected", False)),
    }


@router.get("/assets")
async def assets(x_binomo_session: str | None = Header(default=None)):
    item = _session(x_binomo_session)
    all_assets = [_asset(x) for x in item["client"].get_assets()]
    return {
        "ok": True,
        "normal": [x for x in all_assets if not x["otc"]],
        "otc": [x for x in all_assets if x["otc"]],
    }


async def _open_stream(client: Any, ric: str):
    if not ric:
        raise RuntimeError("O ativo selecionado não possui RIC.")
    await asyncio.wait_for(client._ensure_websocket_connection(), timeout=MARKET_TIMEOUT_SECONDS)
    ws = getattr(client, "_ws_client", None)
    if ws is None or not getattr(ws, "_connected", False):
        raise RuntimeError("A conexão de mercado da Binomo não está disponível.")
    messages = getattr(ws, "_last_messages", None)
    if isinstance(messages, list):
        messages.clear()
    refs = getattr(client, "_binomo_stream_refs", None)
    if refs is None:
        refs = {}
        setattr(client, "_binomo_stream_refs", refs)
    ref = str(getattr(client, "_ref_counter", 1))
    payload = {
        "topic": f"asset:{ric}",
        "event": "phx_join",
        "payload": {},
        "ref": ref,
        "join_ref": ref,
    }
    await client._send_websocket_message_async(json.dumps(payload))
    refs[ric] = ref


def _ts(value: Any):
    if isinstance(value, (int, float)):
        n = float(value)
        if n > 10_000_000_000:
            n /= 1000
        return n if n > 0 else None
    if isinstance(value, str):
        s = value.strip()
        try:
            return _ts(float(s))
        except ValueError:
            pass
        try:
            from datetime import datetime
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _ticks(obj: Any, inherited: float | None = None):
    out = []
    if isinstance(obj, dict):
        stamp = inherited
        for key, value in obj.items():
            if str(key).lower() in {"timestamp", "time", "created_at", "createdat", "ts", "t"}:
                parsed = _ts(value)
                if parsed is not None:
                    stamp = parsed
        price = None
        for key, value in obj.items():
            if str(key).lower() in {"price", "close", "last", "value", "rate", "quote", "ask", "bid"}:
                try:
                    n = float(value)
                    if n > 0:
                        price = n
                        break
                except (TypeError, ValueError):
                    pass
        if price is not None and stamp is not None:
            out.append((stamp, price))
        for value in obj.values():
            out.extend(_ticks(value, stamp))
    elif isinstance(obj, list):
        for value in obj:
            out.extend(_ticks(value, inherited))
    return out


def _collect(messages):
    data = []
    for message in list(messages or []):
        if isinstance(message, (dict, list)):
            data.extend(_ticks(message))
        elif isinstance(message, str):
            try:
                data.extend(_ticks(json.loads(message)))
            except Exception:
                pass
    return sorted(set((round(t, 3), p) for t, p in data))


def _aggregate(ticks, seconds):
    buckets = {}
    for stamp, price in ticks:
        buckets.setdefault(int(stamp // seconds) * seconds, []).append(price)
    rows = []
    for stamp in sorted(buckets):
        prices = buckets[stamp]
        rows.append({
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": float(len(prices)),
            "datetime": str(stamp),
        })
    return rows


async def _binomo_rows(client: Any, ric: str, timeframe: str):
    await _open_stream(client, ric)
    ws = getattr(client, "_ws_client", None)
    messages = getattr(ws, "_last_messages", [])
    seconds = TIMEFRAMES[timeframe]
    deadline = time.monotonic() + MARKET_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        rows = _aggregate(_collect(messages), seconds)
        if len(rows) >= 60:
            return rows[-1000:]
        await asyncio.sleep(0.25)
    rows = _aggregate(_collect(messages), seconds)
    if len(rows) < 60:
        raise RuntimeError(
            f"O fluxo da Binomo retornou apenas {len(rows)} candles de {timeframe}. "
            "O histórico insuficiente foi preservado em vez de completar com outra fonte."
        )
    return rows[-1000:]


def _resample(rows, source_seconds, target_seconds):
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
            "volume": sum(x.get("volume", 0) for x in chunk),
            "datetime": chunk[-1].get("datetime", ""),
        })
    return out


def _engine(symbol, timeframe, strategy, rows, analyze_with_ai, authorization):
    from guru_sinais_api import _gemini_review, _mtf_plan, _mtf_score, _strategy_pack

    context_tf, setup_tf, trigger_tf = _mtf_plan(timeframe)
    base_seconds = TIMEFRAMES[timeframe]
    mtf = {timeframe: rows}
    for tf in (context_tf, setup_tf, trigger_tf):
        if tf not in mtf and TIMEFRAMES[tf] >= base_seconds and TIMEFRAMES[tf] % base_seconds == 0:
            mtf[tf] = _resample(rows, base_seconds, TIMEFRAMES[tf])
    missing = [tf for tf in (context_tf, setup_tf, trigger_tf) if len(mtf.get(tf, [])) < 60]
    if missing:
        raise RuntimeError("Dados reais da Binomo insuficientes para os timeframes: " + ", ".join(missing) + ".")

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
        symbol, f"{context_tf} → {setup_tf} → {trigger_tf}", selected["strategy"],
        setup, mtf[setup_tf][-1]["close"], mtf[setup_tf], authorization
    ) if analyze_with_ai else {"available": False, "reason": "Análise com IA desativada."}

    gem_signal = gemini.get("signal")
    gem_conf = float(gemini.get("confidence", 0)) if gem_signal else 0
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
    if signal == "AGUARDAR":
        warnings.append("Sem alinhamento suficiente entre contexto, setup e gatilho.")

    return {
        "signal": signal, "score": score, "quality": quality, "symbol": symbol,
        "timeframe": timeframe,
        "analysisTimeframes": {"context": context_tf, "setup": setup_tf, "trigger": trigger_tf},
        "price": mtf[setup_tf][-1]["close"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "buyScore": selected["buy"], "sellScore": selected["sell"],
        "reasons": reasons[:10], "warnings": warnings[:8],
        "strategy": selected["strategy"], "strategyLabel": selected["strategyLabel"],
        "strategies": setup, "mtf": {
            "context": {"timeframe": context_tf, "direction": ctx["direction"], "confidence": ctx["confidence"]},
            "setup": {"timeframe": setup_tf, "direction": selected["direction"], "confidence": selected["confidence"]},
            "trigger": {"timeframe": trigger_tf, "direction": trg["direction"], "confidence": trg["confidence"]},
            "score": base_conf, "notes": mtf_notes,
        },
        "gemini": gemini, "indicators": selected["values"],
        "source": "Binomo + stream de mercado + motor técnico MTF + Gemini",
    }


@router.post("/market-analysis")
async def market_analysis(
    req: MarketAnalysisRequest,
    x_binomo_session: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    item = _session(x_binomo_session)
    if req.timeframe not in TIMEFRAMES:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")
    assets = item["client"].get_assets()
    target = next(
        (a for a in assets if str(getattr(a, "name", "")).strip().lower() == req.symbol.strip().lower()),
        None,
    )
    if target is None:
        raise HTTPException(status_code=400, detail="Ativo Binomo não encontrado.")
    try:
        rows = await _binomo_rows(item["client"], str(getattr(target, "ric", "")).strip(), req.timeframe)
        return {"ok": True, "analysis": _engine(req.symbol.strip(), req.timeframe, req.strategy, rows, req.analyze_with_ai, authorization)}
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="A conexão de mercado da Binomo excedeu o tempo limite.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:500]) from exc


@router.post("/logout")
async def logout(x_binomo_session: str | None = Header(default=None)):
    sid = (x_binomo_session or "").strip()
    item = SESSIONS.pop(sid, None)
    if item:
        try:
            await item["client"].close()
        except Exception:
            pass
    return {"ok": True}
