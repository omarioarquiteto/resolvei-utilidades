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



def _normalize_stream_candle(item: Any) -> dict[str, float] | None:
    try:
        row = {
            "open": float(item["open"]),
            "high": float(item.get("max", item.get("high"))),
            "low": float(item.get("min", item.get("low"))),
            "close": float(item["close"]),
            "volume": float(item.get("volume") or 0),
            "datetime": float(item.get("from", item.get("to", 0)) or 0),
        }
        if row["high"] < row["low"] or row["datetime"] <= 0:
            return None
        return row
    except (TypeError, ValueError, KeyError):
        return None


async def _latest_realtime_candle(
    client: Any,
    symbol: str,
    timeframe: str,
) -> dict[str, float] | None:
    size = INTERVALS.get(timeframe)
    if not size:
        return None

    async def _read_one() -> dict[str, float] | None:
        async for item in client.stream_candles(symbol, size):
            return _normalize_stream_candle(item)
        return None

    try:
        return await asyncio.wait_for(_read_one(), timeout=3.5)
    except Exception:
        # O streaming é um reforço de precisão do gatilho. Se ficar indisponível,
        # mantemos a análise histórica em vez de derrubar toda a operação.
        return None


def _closed_candle_rows(rows: list[dict[str, float]], size: int) -> list[dict[str, float]]:
    now = time.time()
    closed = [
        row for row in rows
        if not row.get("datetime") or row["datetime"] + size <= now - 1
    ]
    if len(closed) >= 60:
        return closed
    # Evita perder a análise inteira em caso de relógio do servidor ligeiramente
    # desalinhado com a origem dos candles.
    return rows[:-1] if len(rows) > 60 else rows


async def _mtf_for_symbol(
    client: Any,
    session_id: str,
    symbol: str,
    timeframe: str,
) -> tuple[dict[str, list[dict[str, float]]], tuple[str, str, str], bool]:
    plan = guru_base._mtf_plan(timeframe)
    rows: dict[str, list[dict[str, float]]] = {}

    unique_tfs = list(dict.fromkeys(plan))
    results = await asyncio.gather(
        *[_candles(client, session_id, symbol, tf, 1000) for tf in unique_tfs]
    )

    for tf, data in zip(unique_tfs, results):
        rows[tf] = data

    context_tf, setup_tf, trigger_tf = plan
    live_trigger = await _latest_realtime_candle(client, symbol, trigger_tf)

    # O histórico é calculado somente com candles fechados. O candle em formação
    # entra apenas no timeframe de gatilho, para que o sinal reflita o preço atual.
    live_used = False
    if live_trigger:
        trigger_rows = rows.get(trigger_tf) or []
        last_ts = trigger_rows[-1]["datetime"] if trigger_rows else 0.0
        if live_trigger["datetime"] > last_ts:
            rows[trigger_tf] = trigger_rows + [live_trigger]
            live_used = True

    return rows, plan, live_used

def _candle_metrics(candle: dict[str, float]) -> dict[str, float]:
    rng = max(candle["high"] - candle["low"], 1e-12)
    body = abs(candle["close"] - candle["open"])
    upper = candle["high"] - max(candle["open"], candle["close"])
    lower = min(candle["open"], candle["close"]) - candle["low"]
    location = (candle["close"] - candle["low"]) / rng
    return {
        "range": rng,
        "body": body,
        "body_ratio": body / rng,
        "upper_wick": upper / rng,
        "lower_wick": lower / rng,
        "close_location": location,
    }


def _iq_score_signal(items: list[tuple[str, float, str, str]]) -> tuple[float, float, float, int]:
    """
    Pontua grupos independentes em vez de somar indiscriminadamente indicadores
    correlacionados. Dentro de um grupo, somente o sinal dominante conta.
    """
    groups: dict[str, list[tuple[float, str]]] = {}
    for _, weight, direction, group in items:
        groups.setdefault(group, []).append((weight, direction))

    buy = sell = 0.0
    active_groups = 0
    total_groups = len(groups)

    for values in groups.values():
        call_weight = sum(w for w, d in values if d == "CALL")
        put_weight = sum(w for w, d in values if d == "PUT")
        if not call_weight and not put_weight:
            continue
        strongest = max(call_weight, put_weight)
        weakest = min(call_weight, put_weight)
        # Se o grupo estiver dividido, ele não aumenta a confiança.
        if strongest <= weakest * 1.35:
            continue
        side = "CALL" if call_weight > put_weight else "PUT"
        group_weight = max([w for w, d in values if d == side] or [0.0])
        if group_weight <= 0:
            continue
        active_groups += 1
        if side == "CALL":
            buy += group_weight
        else:
            sell += group_weight

    active_weight = buy + sell
    if not active_weight:
        return 0.0, 0.0, 50.0, 0

    dominance = abs(buy - sell) / active_weight
    coverage = active_groups / max(total_groups, 1)
    agreement = max(buy, sell) / active_weight
    confidence = 50.0 + 50.0 * (
        0.55 * dominance + 0.30 * coverage + 0.15 * agreement
    )
    return buy, sell, min(99.0, confidence), active_groups


def _iq_strategy_pack(rows: list[dict[str, float]], strategy: str) -> dict[str, Any]:
    """
    Estratégias exclusivas do GURÚ IQ Option.
    As famílias continuam isoladas; o motor não mistura sinais de estratégias
    diferentes. A pontuação usa grupos independentes para reduzir dupla contagem.
    """
    closes = [x["close"] for x in rows]
    if len(closes) < 60:
        raise HTTPException(status_code=502, detail="Candles insuficientes para a estratégia.")

    e9, e21, e50 = [guru_base.ema(closes, p)[-1] for p in (9, 21, 50)]
    e9_prev = guru_base.ema(closes[:-1], 9)[-1]
    e9_prev2 = guru_base.ema(closes[:-2], 9)[-1] if len(closes) > 2 else e9_prev
    r = guru_base.rsi(closes)
    macd, macd_signal = guru_base.macd_values(closes)
    hist = macd - macd_signal
    prev_macd, prev_signal = guru_base.macd_values(closes[:-1])
    prev_hist = prev_macd - prev_signal
    roc = guru_base._roc(closes)
    adx, di_diff = guru_base._adx(rows)
    atr = guru_base._atr_value(rows, 14)
    atr_prev = guru_base._atr_value(rows[:-8], 14) if len(rows) > 40 else atr
    atr_pct = atr / closes[-1] * 100 if closes[-1] else 0.0

    st_k, st_d = guru_base._stochastic(rows)
    cci = guru_base._cci(rows)
    willr = guru_base._williams_r(rows)
    candle = guru_base.candle_pattern(rows)

    current_cm = _candle_metrics(rows[-1])
    prev_cm = _candle_metrics(rows[-2])
    current_range = current_cm["range"]
    current_body_ratio = current_cm["body_ratio"]
    close_location = current_cm["close_location"]

    high20 = max(x["high"] for x in rows[-20:])
    low20 = min(x["low"] for x in rows[-20:])
    prev_high20 = max(x["high"] for x in rows[-21:-1])
    prev_low20 = min(x["low"] for x in rows[-21:-1])

    close = closes[-1]
    extension_from_e21 = abs(close - e21) / max(atr, close * 1e-8)
    ema_slope_atr = (e9 - e9_prev2) / max(atr, close * 1e-8)

    bull_trend = e9 > e21 > e50
    bear_trend = e9 < e21 < e50
    strong_bull_context = bull_trend and adx >= 24 and di_diff > 4
    strong_bear_context = bear_trend and adx >= 24 and di_diff < -4

    structure = (
        "CALL"
        if closes[-1] > closes[-3] > closes[-6]
        else "PUT"
        if closes[-1] < closes[-3] < closes[-6]
        else "NEUTRA"
    )

    breakout_up = close > prev_high20
    breakout_down = close < prev_low20
    breakout_up_distance = (close - prev_high20) / max(atr, 1e-12)
    breakout_down_distance = (prev_low20 - close) / max(atr, 1e-12)
    atr_expanding = atr > atr_prev * 1.04

    # Evita transformar uma vela já esticada em entrada atrasada.
    extension_ok_call = e21 <= close <= e21 + max(0.95 * atr, close * 0.00005)
    extension_ok_put = e21 - max(0.95 * atr, close * 0.00005) <= close <= e21

    # Candle de rejeição: útil sobretudo na reversão e no reteste.
    rejection_call = (
        current_cm["lower_wick"] >= 0.32
        and current_cm["lower_wick"] > current_cm["upper_wick"] * 1.25
        and close_location >= 0.62
    )
    rejection_put = (
        current_cm["upper_wick"] >= 0.32
        and current_cm["upper_wick"] > current_cm["lower_wick"] * 1.25
        and close_location <= 0.38
    )

    sweep_support = rows[-1]["low"] < prev_low20 and close > prev_low20
    sweep_resistance = rows[-1]["high"] > prev_high20 and close < prev_high20

    if strategy == "tendencia":
        items = [
            ("Alinhamento EMA", 2.0, "CALL" if bull_trend else "PUT" if bear_trend else "NEUTRA", "regime"),
            ("ADX + DI", 1.5, "CALL" if adx >= 20 and di_diff >= 3 else "PUT" if adx >= 20 and di_diff <= -3 else "NEUTRA", "regime"),
            ("Estrutura", 1.3, structure, "estrutura"),
            ("MACD + aceleração", 1.2, "CALL" if hist > 0 and hist >= prev_hist else "PUT" if hist < 0 and hist <= prev_hist else "NEUTRA", "momentum"),
            ("Inclinação EMA 9", 1.0, "CALL" if ema_slope_atr > 0.02 else "PUT" if ema_slope_atr < -0.02 else "NEUTRA", "momentum"),
            ("Pullback/reclaim EMA21", 1.4, "CALL" if bull_trend and rows[-1]["low"] <= e21 + 0.25 * atr and close > e21 and close_location >= 0.58 else "PUT" if bear_trend and rows[-1]["high"] >= e21 - 0.25 * atr and close < e21 and close_location <= 0.42 else "NEUTRA", "entrada"),
            ("Candle de continuidade", 1.1, "CALL" if close > rows[-2]["close"] and current_body_ratio >= 0.55 and close_location >= 0.70 else "PUT" if close < rows[-2]["close"] and current_body_ratio >= 0.55 and close_location <= 0.30 else "NEUTRA", "entrada"),
            ("RSI de regime", 0.8, "CALL" if 52 <= r <= 68 else "PUT" if 32 <= r <= 48 else "NEUTRA", "momentum"),
        ]
        min_confidence, required_groups, label = 76.0, 4, "Tendência"

    elif strategy == "reversao":
        range_regime = adx < 20 and abs(e9 - e21) <= max(0.55 * atr, close * 0.00004)
        near_support = (close - low20) <= max(0.35 * atr, close * 0.00005)
        near_resistance = (high20 - close) <= max(0.35 * atr, close * 0.00005)

        items = [
            ("Regime lateral", 1.2, "CALL" if range_regime and near_support else "PUT" if range_regime and near_resistance else "NEUTRA", "regime"),
            ("Extremo de RSI", 1.4, "CALL" if r <= 28 else "PUT" if r >= 72 else "NEUTRA", "oscilador"),
            ("Stochastic", 1.1, "CALL" if st_k <= 25 and st_k >= st_d else "PUT" if st_k >= 75 and st_k <= st_d else "NEUTRA", "oscilador"),
            ("CCI/Williams extremo", 0.8, "CALL" if cci <= -100 or willr <= -80 else "PUT" if cci >= 100 or willr >= -20 else "NEUTRA", "oscilador"),
            ("Rejeição de suporte/resistência", 1.7, "CALL" if near_support and rejection_call else "PUT" if near_resistance and rejection_put else "NEUTRA", "entrada"),
            ("Sweep/falso rompimento", 1.5, "CALL" if sweep_support and rejection_call else "PUT" if sweep_resistance and rejection_put else "NEUTRA", "entrada"),
            ("Candle de reversão", 0.9, "CALL" if candle == "engolfo de alta" or (current_body_ratio >= 0.45 and close > rows[-2]["close"] and close_location >= 0.68) else "PUT" if candle == "engolfo de baixa" or (current_body_ratio >= 0.45 and close < rows[-2]["close"] and close_location <= 0.32) else "NEUTRA", "entrada"),
        ]
        blocked = strong_bull_context or strong_bear_context
        min_confidence, required_groups, label = 77.0, 4, "Reversão"
        if blocked:
            for idx, item in enumerate(items):
                items[idx] = (item[0], item[1], "NEUTRA", item[3])

    elif strategy == "rompimento":
        clean_breakout_call = (
            breakout_up
            and 0.08 <= breakout_up_distance <= 0.90
            and current_body_ratio >= 0.55
            and close_location >= 0.72
        )
        clean_breakout_put = (
            breakout_down
            and 0.08 <= breakout_down_distance <= 0.90
            and current_body_ratio >= 0.55
            and close_location <= 0.28
        )
        retest_call = (
            rows[-2]["close"] <= prev_high20
            and rows[-1]["low"] <= prev_high20 + 0.18 * atr
            and close > prev_high20
            and close_location >= 0.58
        )
        retest_put = (
            rows[-2]["close"] >= prev_low20
            and rows[-1]["high"] >= prev_low20 - 0.18 * atr
            and close < prev_low20
            and close_location <= 0.42
        )
        items = [
            ("Rompimento limpo", 2.0, "CALL" if clean_breakout_call else "PUT" if clean_breakout_put else "NEUTRA", "breakout"),
            ("Reteste da zona", 1.7, "CALL" if retest_call else "PUT" if retest_put else "NEUTRA", "breakout"),
            ("ADX + DI", 1.4, "CALL" if adx >= 20 and di_diff >= 3 else "PUT" if adx >= 20 and di_diff <= -3 else "NEUTRA", "regime"),
            ("Expansão ATR", 1.0, "CALL" if atr_expanding and close > rows[-2]["close"] else "PUT" if atr_expanding and close < rows[-2]["close"] else "NEUTRA", "volatilidade"),
            ("MACD", 0.9, "CALL" if hist > 0 else "PUT" if hist < 0 else "NEUTRA", "momentum"),
            ("Estrutura", 0.9, structure, "estrutura"),
            ("Candle de força", 1.0, "CALL" if current_body_ratio >= 0.60 and close_location >= 0.74 else "PUT" if current_body_ratio >= 0.60 and close_location <= 0.26 else "NEUTRA", "entrada"),
        ]
        min_confidence, required_groups, label = 77.0, 4, "Rompimento"

    elif strategy == "momentum":
        impulse_call = close > rows[-2]["close"] and current_body_ratio >= 0.58 and close_location >= 0.72
        impulse_put = close < rows[-2]["close"] and current_body_ratio >= 0.58 and close_location <= 0.28
        items = [
            ("Regime EMA", 1.6, "CALL" if e9 > e21 > e50 else "PUT" if e9 < e21 < e50 else "NEUTRA", "regime"),
            ("ADX + DI", 1.2, "CALL" if adx >= 19 and di_diff >= 3 else "PUT" if adx >= 19 and di_diff <= -3 else "NEUTRA", "regime"),
            ("MACD + aceleração", 1.6, "CALL" if hist > 0 and hist > prev_hist else "PUT" if hist < 0 and hist < prev_hist else "NEUTRA", "momentum"),
            ("Inclinação EMA 9", 1.1, "CALL" if ema_slope_atr > 0.025 else "PUT" if ema_slope_atr < -0.025 else "NEUTRA", "momentum"),
            ("ROC", 1.0, "CALL" if roc > 0.05 else "PUT" if roc < -0.05 else "NEUTRA", "momentum"),
            ("RSI de impulso", 0.9, "CALL" if 53 <= r <= 68 else "PUT" if 32 <= r <= 47 else "NEUTRA", "oscilador"),
            ("Estrutura", 1.1, structure, "estrutura"),
            ("Candle de impulso", 1.1, "CALL" if impulse_call else "PUT" if impulse_put else "NEUTRA", "entrada"),
            ("Filtro anti-extensão", 1.0, "CALL" if extension_ok_call else "PUT" if extension_ok_put else "NEUTRA", "risco"),
        ]
        min_confidence, required_groups, label = 76.0, 5, "Momentum"

    else:
        raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    buy, sell, confidence, active_groups = _iq_score_signal(items)
    direction = "CALL" if buy > sell else "PUT" if sell > buy else "NEUTRA"
    signal_eligible = (
        direction in {"CALL", "PUT"}
        and confidence >= min_confidence
        and active_groups >= required_groups
        and max(buy, sell) >= min(1.25 * min(buy, sell) if min(buy, sell) > 0 else 0, max(buy, sell))
    )

    # O filtro acima não deve substituir uma checagem de dominância mínima.
    if min(buy, sell) > 0 and max(buy, sell) / min(buy, sell) < 1.25:
        signal_eligible = False

    values = {
        "EMA9": e9,
        "EMA21": e21,
        "EMA50": e50,
        "RSI": r,
        "MACD": macd,
        "MACDSignal": macd_signal,
        "MACDHistogram": hist,
        "ATRpct": atr_pct,
        "ADX": adx,
        "DIplusMinus": di_diff,
        "ROC": roc,
        "StochasticK": st_k,
        "StochasticD": st_d,
        "CCI": cci,
        "WilliamsR": willr,
        "Candle": candle,
        "PriceStructure": structure,
        "BodyRatio": current_body_ratio,
        "CloseLocation": close_location,
        "EMASlopeATR": ema_slope_atr,
        "ExtensionATR": extension_from_e21,
        "BreakoutDistanceATR": max(breakout_up_distance, breakout_down_distance, 0.0),
        "ATRExpanding": atr_expanding,
    }

    return {
        "strategy": strategy,
        "strategyLabel": label,
        "buy": round(buy, 2),
        "sell": round(sell, 2),
        "confidence": round(confidence, 1),
        "direction": direction if signal_eligible else "NEUTRA",
        "signalEligible": signal_eligible,
        "minConfidence": min_confidence,
        "requiredGroups": required_groups,
        "activeGroups": active_groups,
        "indicators": [
            {"name": n, "weight": w, "signal": d}
            for n, w, d, _ in items
        ],
        "values": values,
    }


def _iq_mtf_score(
    context: dict[str, Any],
    setup: dict[str, Any],
    trigger: dict[str, Any],
) -> tuple[str, float, list[str]]:
    """
    Contexto filtra, setup decide e gatilho temporiza.
    A família de estratégia permanece isolada.
    """
    strategy = setup["strategy"]
    s = setup["direction"]
    c = context["direction"]
    t = trigger["direction"]
    score = float(setup["confidence"])
    notes: list[str] = []

    if not setup.get("signalEligible"):
        return "AGUARDAR", max(0.0, score - 8), ["O setup não atingiu os filtros mínimos da estratégia."]

    if strategy == "reversao":
        if c == s:
            score += 9
            notes.append(f"Contexto confirma a reversão em {s}.")
        elif c == "NEUTRA":
            score += 2
            notes.append("Contexto maior está neutro, sem tendência forte contra a reversão.")
        elif c in {"CALL", "PUT"} and c != s:
            if context["confidence"] >= 70:
                score -= 20
                notes.append("Existe tendência maior forte contra a reversão.")
            else:
                score -= 8
                notes.append("Contexto maior ainda é contrário, mas sem força máxima.")
    else:
        if c == s and context.get("signalEligible", context["confidence"] >= 65):
            score += 11
            notes.append(f"Contexto confirma {s}.")
        elif c == s:
            score += 5
            notes.append(f"Contexto acompanha {s}, porém ainda sem força suficiente.")
        elif c in {"CALL", "PUT"} and c != s:
            score -= 20
            notes.append("Contexto maior está contra a direção do setup.")
        else:
            score -= 5
            notes.append("Contexto maior está neutro.")

    if t == s and trigger.get("signalEligible", trigger["confidence"] >= 68):
        score += 12
        notes.append(f"Gatilho em tempo real confirma {s}.")
    elif t == s:
        score += 6
        notes.append(f"Gatilho acompanha {s}, mas a confirmação ainda é moderada.")
    elif t in {"CALL", "PUT"} and t != s:
        score -= 18
        notes.append("Gatilho atual está contra o setup.")
    else:
        score -= 7
        notes.append("Gatilho atual ainda não confirmou o setup.")

    if strategy == "reversao":
        eligible_mtf = (
            s in {"CALL", "PUT"}
            and t == s
            and score >= 78
            and not (
                c in {"CALL", "PUT"}
                and c != s
                and context["confidence"] >= 78
            )
        )
    else:
        eligible_mtf = (
            s in {"CALL", "PUT"}
            and c == s
            and t == s
            and score >= 79
        )

    return (s if eligible_mtf else "AGUARDAR"), round(max(0.0, min(99.0, score)), 1), notes


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

    mtf, plan, live_trigger_used = await _mtf_for_symbol(
        client, session_id, symbol, timeframe
    )
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

    candidates: list[tuple[float, dict[str, Any], str, list[str]]] = []
    for setup in setup_strategies:
        context = next(
            x for x in context_strategies if x["strategy"] == setup["strategy"]
        )
        trigger = next(
            x for x in trigger_strategies if x["strategy"] == setup["strategy"]
        )
        signal, score, notes = _iq_mtf_score(context, setup, trigger)
        candidates.append((score if signal != "AGUARDAR" else 0.0, setup, signal, notes))

    if strategy == "automatica":
        valid = [x for x in candidates if x[2] in {"CALL", "PUT"}]
        if valid:
            valid.sort(key=lambda x: x[0], reverse=True)
            top = valid[0]
            # Se duas famílias diferentes estão praticamente empatadas, o automático
            # não inventa uma vantagem estatística onde não existe.
            if (
                len(valid) >= 2
                and abs(valid[0][0] - valid[1][0]) < 3.0
                and valid[0][2] != valid[1][2]
            ):
                selected = valid[0][1]
            else:
                selected = top[1]
        else:
            selected = max(setup_strategies, key=lambda x: x["confidence"])
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

    base_signal, base_score, notes = _iq_mtf_score(context, selected, trigger)

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
        score = round(min(99, 0.78 * base_score + 0.22 * gem_conf))
        quality = (
            "MUITO FORTE" if score >= 84 else "FORTE" if score >= 76 else "MODERADA"
        )
    elif base_signal in {"CALL", "PUT"} and gem_signal in {"CALL", "PUT"}:
        signal = base_signal
        score = round(max(50, min(88, 0.88 * base_score + 0.12 * gem_conf - 8)))
        quality = "CONFLUÊNCIA PARCIAL"
    else:
        signal = base_signal
        score = round(base_score)
        quality = (
            "FORTE" if score >= 78 else "MODERADA" if score >= 68 else "BAIXA"
        )

    reasons = [
        f"Contexto {context_tf}: {context['direction']} com {context['confidence']:.0f}% de confluência.",
        f"Setup {setup_tf}: {selected['direction']} com {selected['confidence']:.0f}% de confluência.",
        f"Gatilho {trigger_tf}: {trigger['direction']} com {trigger['confidence']:.0f}% de confluência.",
    ] + notes

    if live_trigger_used:
        reasons.append("O gatilho foi atualizado por candle em tempo real da sessão da IQ Option.")

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
        warnings.append("O gatilho atual diverge do setup.")
    if selected["values"].get("ExtensionATR", 0) > 0.95:
        warnings.append("Preço está esticado em relação à EMA21; o motor evita perseguir a entrada.")
    if gemini.get("available") and gem_signal in {"CALL", "PUT"} and gem_signal != base_signal:
        warnings.append("O Gemini divergiu da leitura técnica em múltiplos timeframes.")
    if gemini.get("available") and gemini.get("risk") == "alto":
        warnings.append("O Gemini classificou o contexto como risco alto.")
    if signal == "AGUARDAR":
        warnings.append("Nenhuma combinação dentro da estratégia isolada atingiu os filtros mínimos de entrada.")

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
            "liveTrigger": live_trigger_used,
        },
        "gemini": gemini,
        "indicators": selected["values"],
        "source": "IQ Option + motor técnico MTF + gatilho em tempo real",
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
