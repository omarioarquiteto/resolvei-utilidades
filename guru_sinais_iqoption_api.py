from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import guru_sinais_api as guru_base

router = APIRouter(prefix="/api/guru-sinais-iqoption", tags=["GURÚ DOS SINAIS IQOPTION"])

SESSION_TTL_SECONDS = 45 * 60
LOGIN_TIMEOUT_SECONDS = 25
REQUEST_TIMEOUT_SECONDS = 12
SESSIONS: dict[str, dict[str, Any]] = {}
ASSET_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CANDLE_CACHE: dict[str, tuple[float, list[dict[str, float]]]] = {}

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}


class IQLoginRequest(BaseModel):
    email: str
    password: str


class MarketAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str = "automatica"
    analyze_with_ai: bool = False


def _client_class() -> Any:
    try:
        from iqoptionapi.aio import AsyncIQOption
        return AsyncIQOption
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="O cliente assíncrono da iqoptionapi não está disponível no servidor.",
        ) from exc


def _cleanup() -> None:
    now = time.time()
    cutoff = now - SESSION_TTL_SECONDS

    expired: list[tuple[str, Any]] = []
    for sid, item in list(SESSIONS.items()):
        if item.get("last_used", 0) < cutoff:
            expired.append((sid, item))

    for sid, item in expired:
        SESSIONS.pop(sid, None)
        ASSET_CACHE.pop(sid, None)
        for key in list(CANDLE_CACHE):
            if key.startswith(sid + "|"):
                CANDLE_CACHE.pop(key, None)
        client = item.get("client")
        if client is not None:
            try:
                asyncio.create_task(client.close())
            except Exception:
                pass

    for cache, ttl in ((ASSET_CACHE, 120), (CANDLE_CACHE, 40)):
        for key, (ts, _) in list(cache.items()):
            if now - ts > ttl:
                cache.pop(key, None)


def _new_session(client: Any, email: str) -> str:
    _cleanup()
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = {
        "client": client,
        "email": email,
        "last_used": time.time(),
    }
    return sid


def _get_session(session_id: str | None) -> dict[str, Any]:
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=401, detail="Conecte sua conta da IQ Option primeiro.")

    _cleanup()
    item = SESSIONS.get(sid)
    if not item:
        raise HTTPException(
            status_code=401,
            detail="A sessão da IQ Option expirou. Faça login novamente.",
        )
    item["last_used"] = time.time()
    return item


def _asset_list() -> dict[str, Any]:
    try:
        import iqoptionapi.constants as iq_constants
        active_map = dict(iq_constants.ACTIVES)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível carregar a tabela de ativos da iqoptionapi.",
        ) from exc

    normal: list[dict[str, Any]] = []
    otc: list[dict[str, Any]] = []

    for symbol, active_id in active_map.items():
        name = str(symbol or "").upper()
        is_otc = name.endswith("-OTC")
        base = name[:-4] if is_otc else name

        if not (len(base) == 6 and base.isalpha()):
            continue

        item = {
            "symbol": name,
            "market": "OTC" if is_otc else "normal",
            "type": "binary",
            "open": None,
            "active_id": int(active_id),
        }
        (otc if is_otc else normal).append(item)

    normal.sort(key=lambda x: x["symbol"])
    otc.sort(key=lambda x: x["symbol"])

    return {
        "normal": normal,
        "otc": otc,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def _candles(client: Any, session_id: str, symbol: str, timeframe: str, count: int = 1000) -> list[dict[str, float]]:
    size = INTERVALS.get(timeframe)
    if not size:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")

    symbol = str(symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Informe o ativo da IQ Option.")

    key = f"{session_id}|{symbol}|{timeframe}|{count}"
    cached = CANDLE_CACHE.get(key)
    if cached and time.time() - cached[0] < 8:
        return cached[1]

    try:
        raw = await asyncio.wait_for(
            client.get_candles(symbol, size, count, int(time.time())),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"A IQ Option não respondeu aos candles de {symbol} dentro do tempo limite.",
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"O ativo {symbol} não está mapeado na versão atual da iqoptionapi.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar candles da IQ Option: {str(exc)[:180]}",
        ) from exc

    rows: list[dict[str, float]] = []
    for item in raw or []:
        try:
            rows.append(
                {
                    "open": float(item["open"]),
                    "high": float(item.get("max", item.get("high"))),
                    "low": float(item.get("min", item.get("low"))),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume") or 0),
                    "datetime": float(item.get("from", item.get("to", 0)) or 0),
                }
            )
        except (TypeError, ValueError, KeyError):
            continue

    rows.sort(key=lambda x: x["datetime"])
    if len(rows) < 60:
        raise HTTPException(
            status_code=502,
            detail=f"A IQ Option retornou somente {len(rows)} candles para {symbol}; são necessários pelo menos 60.",
        )

    CANDLE_CACHE[key] = (time.time(), rows)
    return rows


async def _mtf_for_symbol(client: Any, session_id: str, symbol: str, timeframe: str) -> tuple[dict[str, list[dict[str, float]]], tuple[str, str, str]]:
    plan = guru_base._mtf_plan(timeframe)
    rows: dict[str, list[dict[str, float]]] = {}

    unique_tfs = list(dict.fromkeys(plan))
    results = await asyncio.gather(
        *[_candles(client, session_id, symbol, tf, 1000) for tf in unique_tfs]
    )

    for tf, data in zip(unique_tfs, results):
        rows[tf] = data

    return rows, plan



def _iq_strategy_pack(rows: list[dict[str, float]], strategy: str) -> dict[str, Any]:
    """Estratégias exclusivas do GURÚ IQ Option; famílias não são combinadas."""
    closes = [x["close"] for x in rows]
    e9, e21, e50 = [guru_base.ema(closes, p)[-1] for p in (9, 21, 50)]
    r = guru_base.rsi(closes)
    macd, macd_signal = guru_base.macd_values(closes)
    hist = macd - macd_signal
    prev_macd, prev_signal = guru_base.macd_values(closes[:-1]) if len(closes) >= 30 else (macd, macd_signal)
    prev_hist = prev_macd - prev_signal
    e9_prev = guru_base.ema(closes[:-1], 9)[-1] if len(closes) >= 3 else e9
    roc = guru_base._roc(closes)
    adx, di_diff = guru_base._adx(rows)
    atr = guru_base._atr_value(rows, 14)
    atr_prev = guru_base._atr_value(rows[:-10], 14) if len(rows) > 30 else atr
    atr_pct = atr / closes[-1] * 100 if closes[-1] else 0.0
    volume_avg = guru_base._last_sma([x.get("volume", 0.0) for x in rows], 20)
    vr = rows[-1].get("volume", 0.0) / max(volume_avg, 1e-12)
    candle = guru_base.candle_pattern(rows)
    structure = "CALL" if closes[-1] > closes[-3] > closes[-6] else "PUT" if closes[-1] < closes[-3] < closes[-6] else "NEUTRA"
    prev_high20 = max(x["high"] for x in rows[-21:-1])
    prev_low20 = min(x["low"] for x in rows[-21:-1])
    breakout_up = closes[-1] > prev_high20
    breakout_down = closes[-1] < prev_low20
    breakout_distance = (
        "CALL" if breakout_up and atr > 0 and (closes[-1] - prev_high20) >= atr * 0.20
        else "PUT" if breakout_down and atr > 0 and (prev_low20 - closes[-1]) >= atr * 0.20
        else "NEUTRA"
    )
    bb_mid = guru_base._last_sma(closes, 20)
    bb_sd = guru_base._std(closes, 20)
    bb_width = (4 * bb_sd / closes[-1] * 100) if closes[-1] else 0.0
    prev_closes = closes[:-10]
    prev_sd = guru_base._std(prev_closes, 20)
    bb_width_prev = (4 * prev_sd / closes[-11] * 100) if len(closes) > 40 and closes[-11] else bb_width
    volume_dir = "CALL" if vr >= 1.20 and closes[-1] > closes[-2] else "PUT" if vr >= 1.20 and closes[-1] < closes[-2] else "NEUTRA"

    if strategy in {"tendencia", "reversao"}:
        result = guru_base._strategy_pack(rows, strategy)
        result["strategyLabel"] = "Tendência" if strategy == "tendencia" else "Reversão"
        return result

    if strategy == "rompimento":
        items = [
            ("Rompimento Donchian",2.0,"CALL" if breakout_up else "PUT" if breakout_down else "NEUTRA"),
            ("Distância do rompimento",1.5,breakout_distance),
            ("Expansão ATR",1.1,"CALL" if atr>atr_prev and closes[-1]>closes[-2] else "PUT" if atr>atr_prev and closes[-1]<closes[-2] else "NEUTRA"),
            ("Expansão Bollinger",0.9,"CALL" if bb_width>bb_width_prev and closes[-1]>bb_mid else "PUT" if bb_width>bb_width_prev and closes[-1]<bb_mid else "NEUTRA"),
            ("ADX + DI",1.0,"CALL" if adx>=22 and di_diff>0 else "PUT" if adx>=22 and di_diff<0 else "NEUTRA"),
            ("Volume no rompimento",1.2,volume_dir),
            ("Candle de confirmação",1.0,"CALL" if candle in {"bullish","engolfo de alta"} and breakout_up else "PUT" if candle in {"bearish","engolfo de baixa"} and breakout_down else "NEUTRA"),
            ("Estrutura pós-rompimento",0.8,"CALL" if closes[-1]>closes[-2]>closes[-3] and breakout_up else "PUT" if closes[-1]<closes[-2]<closes[-3] and breakout_down else "NEUTRA"),
            ("EMA como filtro",0.7,"CALL" if e9>e21>e50 else "PUT" if e9<e21<e50 else "NEUTRA")
        ]
        min_confidence = 78.0
        label = "Rompimento"
        extra = {"BreakoutUp": breakout_up, "BreakoutDown": breakout_down, "BreakoutDistance": breakout_distance}
    elif strategy == "momentum":
        items = [
            ("MACD histograma",1.4,"CALL" if hist>0 else "PUT" if hist<0 else "NEUTRA"),
            ("Aceleração MACD",1.1,"CALL" if hist>prev_hist and hist>0 else "PUT" if hist<prev_hist and hist<0 else "NEUTRA"),
            ("ROC",1.2,"CALL" if roc>.04 else "PUT" if roc<-.04 else "NEUTRA"),
            ("Inclinação EMA 9",1.0,"CALL" if e9>e9_prev else "PUT" if e9<e9_prev else "NEUTRA"),
            ("Alinhamento EMA",0.9,"CALL" if e9>e21>e50 else "PUT" if e9<e21<e50 else "NEUTRA"),
            ("ADX + DI",1.0,"CALL" if adx>=20 and di_diff>0 else "PUT" if adx>=20 and di_diff<0 else "NEUTRA"),
            ("RSI momentum",0.9,"CALL" if 55<=r<=72 else "PUT" if 28<=r<=45 else "NEUTRA"),
            ("Estrutura de preço",1.0,structure),
            ("Volume",0.8,volume_dir),
            ("Candle continuação",0.7,"CALL" if candle in {"bullish","engolfo de alta"} and structure=="CALL" else "PUT" if candle in {"bearish","engolfo de baixa"} and structure=="PUT" else "NEUTRA")
        ]
        min_confidence = 76.0
        label = "Momentum"
        extra = {}
    else:
        raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    buy, sell, confidence = guru_base._score_signal(items)
    direction = "CALL" if buy > sell else "PUT" if sell > buy else "NEUTRA"
    eligible = direction in {"CALL","PUT"} and confidence >= min_confidence
    values = {
        "EMA9": e9, "EMA21": e21, "EMA50": e50, "RSI": r,
        "MACD": macd, "MACDSignal": macd_signal, "MACDHistogram": hist,
        "ATRpct": atr_pct, "ADX": adx, "DIplusMinus": di_diff, "ROC": roc,
        "VolumeRatio": vr, "Candle": candle, "PriceStructure": structure
    }
    values.update(extra)
    return {
        "strategy": strategy, "strategyLabel": label,
        "buy": round(buy,2), "sell": round(sell,2), "confidence": round(confidence,1),
        "direction": direction if eligible else "NEUTRA",
        "signalEligible": eligible, "minConfidence": min_confidence,
        "indicators": [{"name":n,"weight":w,"signal":d} for n,w,d in items],
        "values": values,
    }

async def _analyze(
    client: Any,
    session_id: str,
    symbol: str,
    timeframe: str,
    strategy: str,
    authorization: str | None,
    analyze_with_ai: bool,
) -> dict[str, Any]:
    if timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")

    symbol = str(symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Informe um ativo.")

    mtf, plan = await _mtf_for_symbol(client, session_id, symbol, timeframe)
    context_tf, setup_tf, trigger_tf = plan
    setup_rows = mtf[setup_tf]

    if min(len(mtf[context_tf]), len(setup_rows), len(mtf[trigger_tf])) < 60:
        raise HTTPException(
            status_code=502,
            detail="Não foram recebidos candles suficientes para a análise em múltiplos timeframes.",
        )

    families = ("tendencia", "reversao", "rompimento", "momentum")
    context_strategies = [
        _iq_strategy_pack(mtf[context_tf], strategy_name) for strategy_name in families
    ]
    setup_strategies = [
        _iq_strategy_pack(setup_rows, strategy_name) for strategy_name in families
    ]
    trigger_strategies = [
        _iq_strategy_pack(mtf[trigger_tf], strategy_name) for strategy_name in families
    ]

    if strategy == "automatica":
        candidates = []
        for setup in setup_strategies:
            context = next(
                x for x in context_strategies if x["strategy"] == setup["strategy"]
            )
            trigger = next(
                x for x in trigger_strategies if x["strategy"] == setup["strategy"]
            )
            signal, score, _ = guru_base._mtf_score(context, setup, trigger)
            candidates.append((score if signal != "AGUARDAR" else 0, setup))
        selected = max(candidates, key=lambda x: x[0])[1]
    else:
        selected = next(
            (x for x in setup_strategies if x["strategy"] == strategy),
            None,
        )
        if not selected:
            raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    context = next(
        x for x in context_strategies if x["strategy"] == selected["strategy"]
    )
    trigger = next(
        x for x in trigger_strategies if x["strategy"] == selected["strategy"]
    )

    base_signal, base_score, notes = guru_base._mtf_score(
        context, selected, trigger
    )

    gemini = (
        guru_base._gemini_review(
            symbol,
            f"{context_tf} → {setup_tf} → {trigger_tf}",
            selected["strategy"],
            [selected],
            setup_rows[-1]["close"],
            setup_rows,
            authorization,
        )
        if analyze_with_ai
        else {"available": False, "reason": "Análise com IA desativada."}
    )

    gem_signal = gemini.get("signal")
    gem_conf = float(gemini.get("confidence", 0)) if gem_signal else 0.0

    if base_signal in {"CALL", "PUT"} and gem_signal == base_signal:
        signal = base_signal
        score = round(min(99, 0.72 * base_score + 0.28 * gem_conf))
        quality = (
            "MUITO FORTE" if score >= 82 else "FORTE" if score >= 72 else "MODERADA"
        )
    elif base_signal in {"CALL", "PUT"} and gem_signal in {"CALL", "PUT"}:
        signal = base_signal
        score = round(max(50, min(90, 0.82 * base_score + 0.18 * gem_conf - 8)))
        quality = "CONFLUÊNCIA PARCIAL"
    else:
        signal = base_signal
        score = round(base_score)
        quality = (
            "FORTE" if score >= 75 else "MODERADA" if score >= 65 else "BAIXA"
        )

    reasons = [
        f"Contexto {context_tf}: {context['direction']} com {context['confidence']:.0f}% de confluência.",
        f"Setup {setup_tf}: {selected['direction']} com {selected['confidence']:.0f}% de confluência.",
        f"Gatilho {trigger_tf}: {trigger['direction']} com {trigger['confidence']:.0f}% de confluência.",
    ] + notes

    if gemini.get("available"):
        reasons.append("Gemini: " + (gemini.get("reason") or "validação concluída."))

    warnings: list[str] = []
    if (
        context["direction"] in {"CALL", "PUT"}
        and selected["direction"] in {"CALL", "PUT"}
        and context["direction"] != selected["direction"]
    ):
        warnings.append("Contexto e setup estão em direções opostas.")
    if (
        trigger["direction"] in {"CALL", "PUT"}
        and selected["direction"] in {"CALL", "PUT"}
        and trigger["direction"] != selected["direction"]
    ):
        warnings.append("O gatilho de entrada ainda diverge do setup.")
    if (
        gemini.get("available")
        and gem_signal in {"CALL", "PUT"}
        and gem_signal != base_signal
    ):
        warnings.append("O Gemini divergiu da leitura técnica em múltiplos timeframes.")
    if gemini.get("available") and gemini.get("risk") == "alto":
        warnings.append("O Gemini classificou o contexto como risco alto.")
    if signal == "AGUARDAR":
        warnings.append("Sem alinhamento suficiente entre contexto, setup e gatilho.")

    return {
        "signal": signal,
        "score": score,
        "quality": quality,
        "symbol": symbol,
        "timeframe": timeframe,
        "analysisTimeframes": {
            "context": context_tf,
            "setup": setup_tf,
            "trigger": trigger_tf,
        },
        "price": setup_rows[-1]["close"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "buyScore": selected["buy"],
        "sellScore": selected["sell"],
        "reasons": reasons[:10],
        "warnings": warnings[:8],
        "strategy": selected["strategy"],
        "strategyLabel": selected["strategyLabel"],
        "strategies": setup_strategies,
        "mtf": {
            "context": {
                "timeframe": context_tf,
                "direction": context["direction"],
                "confidence": context["confidence"],
            },
            "setup": {
                "timeframe": setup_tf,
                "direction": selected["direction"],
                "confidence": selected["confidence"],
            },
            "trigger": {
                "timeframe": trigger_tf,
                "direction": trigger["direction"],
                "confidence": trigger["confidence"],
            },
            "score": base_score,
            "notes": notes,
        },
        "gemini": gemini,
        "indicators": selected["values"],
        "source": "IQ Option + motor técnico MTF + Gemini",
    }


@router.post("/login")
async def iq_login(req: IQLoginRequest) -> dict[str, Any]:
    email = req.email.strip()
    password = req.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="Informe e-mail e senha da IQ Option.")

    AsyncIQOption = _client_class()
    client = AsyncIQOption(email, password)
    sid = secrets.token_urlsafe(32)

    try:
        await asyncio.wait_for(client.connect(), timeout=LOGIN_TIMEOUT_SECONDS)
        # O cliente assíncrono considera a autenticação concluída quando
        # recebe "authenticated=true" no WebSocket. Não exigimos um broadcast
        # de perfil aqui, pois ele não é enviado automaticamente pela plataforma.
    except asyncio.TimeoutError as exc:
        try:
            await client.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=504,
            detail="A conexão com a IQ Option excedeu o tempo limite. Isso indica falha na autenticação ou no WebSocket, não erro de senha.",
        ) from exc
    except Exception as exc:
        try:
            await client.close()
        except Exception:
            pass
        detail = str(exc)[:320] or "A IQ Option recusou a conexão."
        raise HTTPException(
            status_code=401 if "login" in detail.lower() or "auth" in detail.lower() else 502,
            detail=f"Falha ao conectar à IQ Option: {detail}",
        ) from exc

    SESSIONS[sid] = {"client": client, "email": email, "last_used": time.time()}
    _cleanup()

    return {
        "ok": True,
        "session_id": sid,
        "connected": True,
        "requires_2fa": False,
    }


@router.get("/session")
async def iq_session(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    client = item["client"]
    ws = getattr(client, "_ws", None)
    connected = ws is not None and not bool(getattr(ws, "_closed", False))
    if not connected:
        raise HTTPException(status_code=401, detail="A conexão com a IQ Option foi encerrada. Faça login novamente.")

    return {
        "ok": True,
        "connected": True,
    }


@router.get("/assets")
async def iq_assets(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    _get_session(x_iq_session)
    return _asset_list()


@router.post("/logout")
async def iq_logout(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    sid = (x_iq_session or "").strip()
    item = SESSIONS.pop(sid, None)
    ASSET_CACHE.pop(sid, None)

    for key in list(CANDLE_CACHE):
        if key.startswith(sid + "|"):
            CANDLE_CACHE.pop(key, None)

    if item:
        try:
            await item["client"].close()
        except Exception:
            pass

    return {"ok": True}


@router.post("/market-analysis")
async def iq_market_analysis(
    req: MarketAnalysisRequest,
    x_iq_session: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    try:
        analysis = await _analyze(
            item["client"],
            x_iq_session or "",
            req.symbol,
            req.timeframe,
            req.strategy,
            authorization,
            req.analyze_with_ai,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha durante a análise pela IQ Option: {str(exc)[:220]}",
        ) from exc

    return {"ok": True, "analysis": analysis}
