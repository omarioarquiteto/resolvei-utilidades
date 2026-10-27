from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import biquote_service
from consultor_senior_auth import get_session
from consultor_senior_prompt import prompt as CONSULTOR_PROMPT

router = APIRouter(prefix="/api/consultor-senior", tags=["CONSULTOR SÊNIOR"])

INTERVALS = {"1m": 60, "5m": 300, "15m": 900}
COUNTS = {"1m": 220, "5m": 180, "15m": 140}
MIN_CLOSED = {"1m": 100, "5m": 90, "15m": 70}


class ConsultRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=40)


LIVE_MARKET_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
LIVE_MARKET_CACHE_TTL = 4.0
LIVE_FRAMES_CACHE: dict[str, tuple[float, dict[str, list[dict[str, float]]]]] = {}
LIVE_FRAMES_CACHE_TTL = 8.0
FACTS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
FACTS_CACHE_TTL = 45.0
AI_PROVIDER_COOLDOWN: dict[str, float] = {}
AI_PROVIDER_COOLDOWN_SECONDS = 60.0
CONSULT_RESULT_CACHE: dict[str, tuple[str, float, dict[str, Any]]] = {}
CONSULT_RESULT_CACHE_TTL = 75.0

def _clean_symbol(symbol: str) -> str:
    s = symbol.strip().upper().replace(" ", "")
    if not s:
        raise HTTPException(status_code=400, detail="Informe o ativo.")
    return s


def _normalize_rows(raw: Any) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for candle in raw or []:
        try:
            rows.append({
                "time": float(candle.get("from", candle.get("to", 0))),
                "open": float(candle["open"]),
                "high": float(candle.get("max", candle.get("high"))),
                "low": float(candle.get("min", candle.get("low"))),
                "close": float(candle["close"]),
                "volume": float(candle.get("volume") or 0),
            })
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda x: x["time"])
    return rows


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for value in values[1:]:
        out.append((value * k) + (out[-1] * (1.0 - k)))
    return out


def _sma(values: list[float], period: int) -> list[float]:
    out: list[float] = []
    if len(values) < period:
        return [math.nan] * len(values)
    out.extend([math.nan] * (period - 1))
    total = sum(values[:period])
    out.append(total / period)
    for i in range(period, len(values)):
        total += values[i] - values[i - period]
        out.append(total / period)
    return out


def _rsi(values: list[float], period: int = 14) -> list[float]:
    if len(values) < 2:
        return [math.nan] * len(values)
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = _ema(gains, period)
    avg_loss = _ema(losses, period)
    out: list[float] = []
    for gain, loss in zip(avg_gain, avg_loss):
        if loss == 0:
            out.append(100.0 if gain > 0 else 50.0)
        else:
            rs = gain / loss
            out.append(100.0 - (100.0 / (1.0 + rs)))
    return out


def _true_ranges(rows: list[dict[str, float]]) -> list[float]:
    out: list[float] = []
    prev = None
    for row in rows:
        if prev is None:
            out.append(row["high"] - row["low"])
        else:
            out.append(max(
                row["high"] - row["low"],
                abs(row["high"] - prev),
                abs(row["low"] - prev),
            ))
        prev = row["close"]
    return out


def _atr(rows: list[dict[str, float]], period: int = 14) -> list[float]:
    return _ema(_true_ranges(rows), period)


def _macd(values: list[float]) -> tuple[list[float], list[float]]:
    ema12 = _ema(values, 12)
    ema26 = _ema(values, 26)
    line = [a - b for a, b in zip(ema12, ema26)]
    signal = _ema(line, 9)
    hist = [a - b for a, b in zip(line, signal)]
    return line, hist


def _bollinger(values: list[float], period: int = 20) -> tuple[list[float], list[float], list[float]]:
    mid = _sma(values, period)
    upper: list[float] = []
    lower: list[float] = []
    for i in range(len(values)):
        if i < period - 1:
            upper.append(math.nan)
            lower.append(math.nan)
            continue
        window = values[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        sd = math.sqrt(max(variance, 0.0))
        upper.append(mean + 2.0 * sd)
        lower.append(mean - 2.0 * sd)
    return mid, upper, lower


def _stoch(rows: list[dict[str, float]], period: int = 14) -> tuple[list[float], list[float]]:
    k = [math.nan] * len(rows)
    for i in range(period - 1, len(rows)):
        window = rows[i - period + 1:i + 1]
        hh = max(x["high"] for x in window)
        ll = min(x["low"] for x in window)
        k[i] = 50.0 if hh == ll else ((rows[i]["close"] - ll) / (hh - ll)) * 100.0

    valid = [x for x in k if not math.isnan(x)]
    d_valid = _sma(valid, 3)
    d = [math.nan] * len(rows)
    cursor = 0
    for i, value in enumerate(k):
        if not math.isnan(value):
            d[i] = d_valid[cursor]
            cursor += 1
    return k, d


def _adx(rows: list[dict[str, float]], period: int = 14) -> tuple[float, float, float]:
    if len(rows) < period + 2:
        return math.nan, math.nan, math.nan

    tr = _true_ranges(rows)
    plus = [0.0]
    minus = [0.0]

    for i in range(1, len(rows)):
        up = rows[i]["high"] - rows[i - 1]["high"]
        down = rows[i - 1]["low"] - rows[i]["low"]
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)

    atr_vals = _ema(tr, period)
    p_vals = _ema(plus, period)
    m_vals = _ema(minus, period)
    dx: list[float] = []

    for atr, p, m in zip(atr_vals, p_vals, m_vals):
        if atr <= 0:
            dx.append(0.0)
            continue
        pdi = 100.0 * p / atr
        mdi = 100.0 * m / atr
        dx.append(0.0 if pdi + mdi == 0 else 100.0 * abs(pdi - mdi) / (pdi + mdi))

    adx_vals = _ema(dx, period)
    pdi = 100.0 * p_vals[-1] / atr_vals[-1] if atr_vals[-1] > 0 else math.nan
    mdi = 100.0 * m_vals[-1] / atr_vals[-1] if atr_vals[-1] > 0 else math.nan
    return adx_vals[-1], pdi, mdi


def _obv(rows: list[dict[str, float]]) -> list[float]:
    out = [0.0]
    for i in range(1, len(rows)):
        volume = rows[i]["volume"]
        if rows[i]["close"] > rows[i - 1]["close"]:
            out.append(out[-1] + volume)
        elif rows[i]["close"] < rows[i - 1]["close"]:
            out.append(out[-1] - volume)
        else:
            out.append(out[-1])
    return out


def _swing_points(rows: list[dict[str, float]], width: int = 2):
    highs = []
    lows = []
    for i in range(width, len(rows) - width):
        h = rows[i]["high"]
        l = rows[i]["low"]
        if h >= max(rows[j]["high"] for j in range(i - width, i + width + 1)):
            highs.append((i, h))
        if l <= min(rows[j]["low"] for j in range(i - width, i + width + 1)):
            lows.append((i, l))
    return highs, lows


def _safe(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _nearest_level(levels: list[float], reference: float) -> dict[str, Any]:
    if not levels or not reference:
        return {"nearest": None, "distance_pct": None, "tests": 0}
    nearest = min(levels, key=lambda x: abs(x - reference))
    tolerance = max(reference * 0.0005, abs(reference) * 0.0008)
    tests = sum(1 for level in levels if abs(level - nearest) <= tolerance)
    return {
        "nearest": nearest,
        "distance_pct": abs(nearest - reference) / reference * 100,
        "tests": tests,
    }


def _summarize(rows: list[dict[str, float]], timeframe: str) -> dict[str, Any]:
    closes = [x["close"] for x in rows]
    highs = [x["high"] for x in rows]
    lows = [x["low"] for x in rows]
    current = closes[-1]

    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50)
    ema100 = _ema(closes, 100)
    rsi = _rsi(closes, 14)
    atr = _atr(rows, 14)
    macd_line, macd_hist = _macd(closes)
    bb_mid, bb_up, bb_low = _bollinger(closes, 20)
    st_k, st_d = _stoch(rows, 14)
    adx, pdi, mdi = _adx(rows, 14)
    obv = _obv(rows)

    swing_highs, swing_lows = _swing_points(rows[-100:], 2)
    recent_window = min(20, len(rows))
    recent_high = max(highs[-recent_window:])
    recent_low = min(lows[-recent_window:])

    resistance = _nearest_level(
        [recent_high] + [x[1] for x in swing_highs[-6:]],
        current,
    )
    support = _nearest_level(
        [recent_low] + [x[1] for x in swing_lows[-6:]],
        current,
    )

    atr_now = atr[-1]
    last = rows[-1]
    body = abs(last["close"] - last["open"])
    candle_range = max(last["high"] - last["low"], 1e-12)
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]

    ema_slope = (
        (ema21[-1] - ema21[-6]) / current * 100
        if len(ema21) > 6 and current else 0
    )

    if ema9[-1] > ema21[-1] > ema50[-1] and ema_slope > 0:
        trend = "ALTA"
    elif ema9[-1] < ema21[-1] < ema50[-1] and ema_slope < 0:
        trend = "BAIXA"
    else:
        trend = "LATERAL/TRANSIÇÃO"

    sh = [x[1] for x in swing_highs[-4:]]
    sl = [x[1] for x in swing_lows[-4:]]
    structure = "NEUTRA"
    if len(sh) >= 2 and len(sl) >= 2:
        if sh[-1] > sh[-2] and sl[-1] > sl[-2]:
            structure = "HH + HL (alta)"
        elif sh[-1] < sh[-2] and sl[-1] < sl[-2]:
            structure = "LH + LL (baixa)"
        elif sh[-1] > sh[-2] or sl[-1] > sl[-2]:
            structure = "MISTA, viés comprador"
        elif sh[-1] < sh[-2] or sl[-1] < sl[-2]:
            structure = "MISTA, viés vendedor"

    return {
        "timeframe": timeframe,
        "candles": len(rows),
        "current_price": current,
        "trend": trend,
        "structure": structure,
        "ema": {
            "ema9": _safe(ema9[-1]),
            "ema21": _safe(ema21[-1]),
            "ema50": _safe(ema50[-1]),
            "ema100": _safe(ema100[-1]),
            "slope_21_pct": _safe(ema_slope),
            "price_vs_ema21_pct": _safe((current - ema21[-1]) / current * 100 if current else 0),
            "price_vs_ema50_pct": _safe((current - ema50[-1]) / current * 100 if current else 0),
        },
        "support": support,
        "resistance": resistance,
        "momentum": {
            "rsi14": _safe(rsi[-1]),
            "rsi_change_5": _safe(rsi[-1] - rsi[-6] if len(rsi) > 6 else None),
            "macd": _safe(macd_line[-1]),
            "macd_hist": _safe(macd_hist[-1]),
            "macd_hist_change": _safe(macd_hist[-1] - macd_hist[-4] if len(macd_hist) > 4 else None),
            "roc10_pct": _safe((current / closes[-11] - 1.0) * 100 if len(closes) > 11 and closes[-11] else None),
        },
        "volatility": {
            "atr14": _safe(atr_now),
            "atr_pct_price": _safe(atr_now / current * 100 if current else None),
            "recent_range_pct": _safe((recent_high - recent_low) / current * 100 if current else None),
            "bollinger_width_pct": _safe((bb_up[-1] - bb_low[-1]) / bb_mid[-1] * 100 if bb_mid[-1] else None),
        },
        "stochastic": {
            "k14": _safe(st_k[-1]),
            "d3": _safe(st_d[-1]),
        },
        "adx": {
            "adx14": _safe(adx),
            "plus_di": _safe(pdi),
            "minus_di": _safe(mdi),
        },
        "obv_direction": (
            "alta" if len(obv) >= 8 and obv[-1] > obv[-8]
            else "baixa" if len(obv) >= 8 and obv[-1] < obv[-8]
            else "neutro"
        ),
        "last_candle": {
            "direction": (
                "alta" if last["close"] > last["open"]
                else "baixa" if last["close"] < last["open"]
                else "neutro"
            ),
            "body_pct": body / candle_range * 100,
            "upper_wick_pct": upper_wick / candle_range * 100,
            "lower_wick_pct": lower_wick / candle_range * 100,
            "range_pct_atr": (
                candle_range / atr_now
                if atr_now and not math.isnan(atr_now) else None
            ),
        },
        "recent_high": recent_high,
        "recent_low": recent_low,
    }


def _compact_candles(rows: list[dict[str, float]], limit: int = 100):
    return [[
        round(x["time"]),
        x["open"],
        x["high"],
        x["low"],
        x["close"],
        x["volume"],
    ] for x in rows[-limit:]]


def _parse_ai_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = text.strip(chr(96))
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise HTTPException(
                status_code=502,
                detail="O Gemini não retornou um JSON de análise válido.",
            )
        try:
            data = json.loads(text[start:end + 1])
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Não foi possível interpretar a resposta do Gemini.",
            ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail="A resposta do Gemini está em formato inválido.",
        )
    return data


def _token(value: Any) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value or "")).upper()
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _sanitize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    decision = _token(data.get("decision", "SEM OPERACAO"))
    status = _token(data.get("status", "AGUARDAR"))

    if decision not in {"CALL", "PUT", "SEM OPERACAO"}:
        decision = "SEM OPERACAO"
    if status not in {"AGORA", "PROXIMO", "AGUARDAR", "NAO OPERAR"}:
        status = "AGUARDAR"

    try:
        confidence = max(0.0, min(100.0, float(data.get("confidence", 0))))
    except Exception:
        confidence = 0.0

    # A entrada é sempre avaliada no candle de 1 minuto; a expiração é fixa em 5 minutos.
    timeframe = str(data.get("timeframe", "1m") or "1m").strip().lower()
    if timeframe != "1m":
        timeframe = "1m"

    def text_value(key: str, size: int) -> str:
        return str(data.get(key, "") or "").strip()[:size]

    def list_value(key: str) -> list[str]:
        value = data.get(key, [])
        if not isinstance(value, list):
            value = [value]
        return [str(x).strip() for x in value if str(x).strip()][:6]

    return {
        "decision": decision,
        "status": status,
        "confidence": round(confidence, 1),
        "timeframe": timeframe,
        "expiry_minutes": 5,
        "summary": text_value("summary", 500),
        "structure": text_value("structure", 1200),
        "trend": text_value("trend", 700),
        "zone": text_value("zone", 1000),
        "trigger": text_value("trigger", 1000),
        "momentum": text_value("momentum", 1000),
        "volatility": text_value("volatility", 700),
        "price_action": text_value("price_action", 1200),
        "confluences": list_value("confluences"),
        "risks": list_value("risks"),
        "why_now": text_value("why_now", 1400),
        "facts_warning": text_value("facts_warning", 800),
        "data_quality": text_value("data_quality", 30),
    }


def _directional_score(summary: dict[str, Any]) -> int:
    """
    Lightweight directional score from independent technical dimensions.
    It intentionally uses the underlying indicators instead of requiring the
    strict EMA9/21/50 trend label to say ALTA/BAIXA.
    """
    score = 0
    ema = summary.get("ema") or {}
    momentum = summary.get("momentum") or {}
    adx = summary.get("adx") or {}

    e9, e21, e50 = ema.get("ema9"), ema.get("ema21"), ema.get("ema50")
    if e9 is not None and e21 is not None:
        score += 1 if e9 > e21 else -1 if e9 < e21 else 0
    if e21 is not None and e50 is not None:
        score += 1 if e21 > e50 else -1 if e21 < e50 else 0

    slope = ema.get("slope_21_pct")
    if slope is not None:
        score += 1 if slope > 0 else -1 if slope < 0 else 0

    macd_hist = momentum.get("macd_hist")
    if macd_hist is not None:
        score += 1 if macd_hist > 0 else -1 if macd_hist < 0 else 0

    rsi = momentum.get("rsi14")
    if rsi is not None:
        score += 1 if rsi >= 52 else -1 if rsi <= 48 else 0

    pdi, mdi = adx.get("plus_di"), adx.get("minus_di")
    if pdi is not None and mdi is not None:
        score += 1 if pdi > mdi else -1 if pdi < mdi else 0

    return score


def _frames_fingerprint(frames: dict[str, list[dict[str, float]]]) -> str:
    # All frames contain closed candles only; an unchanged fingerprint means
    # an identical technical snapshot, so a new AI request cannot add information.
    return "|".join(
        f"{tf}:{int(rows[-1]['time']) if rows else 0}"
        for tf, rows in sorted(frames.items())
    )


def _cached_consult_response(symbol: str, fingerprint: str, started: float) -> dict[str, Any] | None:
    cached = CONSULT_RESULT_CACHE.get(symbol)
    if not cached or cached[0] != fingerprint:
        return None
    if time.monotonic() - cached[1] >= CONSULT_RESULT_CACHE_TTL:
        return None

    payload = dict(cached[2])
    analysis = dict(payload.get("analysis") or {})
    diagnostics = dict(analysis.get("diagnostics") or {})
    diagnostics["serverDurationMs"] = round((time.perf_counter() - started) * 1000)
    diagnostics["cachedSnapshot"] = True
    analysis["diagnostics"] = diagnostics
    payload["analysis"] = analysis
    return payload


def _save_consult_response(symbol: str, fingerprint: str, response: dict[str, Any]) -> None:
    CONSULT_RESULT_CACHE[symbol] = (fingerprint, time.monotonic(), response)


def _entry_trigger(
    rows: list[dict[str, float]],
    direction: str,
) -> str | None:
    """Procura um gatilho objetivo no último candle de 1m já fechado."""
    if direction not in {"CALL", "PUT"} or len(rows) < 30:
        return None

    last = rows[-1]
    previous = rows[-2]
    candle_range = last["high"] - last["low"]
    if candle_range <= 0:
        return None

    atr_values = _atr(rows, 14)
    atr_now = atr_values[-1] if atr_values else 0.0
    if atr_now and not math.isnan(atr_now) and candle_range / atr_now >= 2.8:
        return None

    body = abs(last["close"] - last["open"])
    body_ratio = body / candle_range
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]
    bullish = last["close"] > last["open"]
    bearish = last["close"] < last["open"]

    if direction == "CALL":
        engulfing = (
            bullish
            and previous["close"] < previous["open"]
            and last["open"] <= previous["close"]
            and last["close"] >= previous["open"]
        )
        breakout = (
            bullish
            and body_ratio >= 0.35
            and last["close"] > max(row["high"] for row in rows[-3:-1])
        )
        rejection = (
            bullish
            and lower_wick >= max(body * 1.3, candle_range * 0.30)
            and (last["close"] - last["low"]) / candle_range >= 0.65
        )
        if engulfing:
            return "engolfo comprador no candle fechado de 1m"
        if breakout:
            return "rompimento comprador da máxima dos dois candles anteriores em 1m"
        if rejection:
            return "rejeição compradora com sombra inferior em 1m"
    else:
        engulfing = (
            bearish
            and previous["close"] > previous["open"]
            and last["open"] >= previous["close"]
            and last["close"] <= previous["open"]
        )
        breakout = (
            bearish
            and body_ratio >= 0.35
            and last["close"] < min(row["low"] for row in rows[-3:-1])
        )
        rejection = (
            bearish
            and upper_wick >= max(body * 1.3, candle_range * 0.30)
            and (last["high"] - last["close"]) / candle_range >= 0.65
        )
        if engulfing:
            return "engolfo vendedor no candle fechado de 1m"
        if breakout:
            return "rompimento vendedor da mínima dos dois candles anteriores em 1m"
        if rejection:
            return "rejeição vendedora com sombra superior em 1m"

    return None


def _entry_confirmed(
    analysis: dict[str, Any],
    frames: dict[str, list[dict[str, float]]],
    symbol: str,
) -> bool:
    """
    Validação independente para expiração de 5m: tendência alinhada em 15m/5m,
    confirmação de curto prazo e gatilho observável no último candle fechado de 1m.
    """
    decision = analysis.get("decision")
    if (
        decision not in {"CALL", "PUT"}
        or analysis.get("status") != "AGORA"
        or int(analysis.get("expiry_minutes") or 0) != 5
        or analysis.get("timeframe") != "1m"
        or not str(analysis.get("trigger") or "").strip()
        or str(analysis.get("data_quality") or "").strip().lower() not in {"boa", "moderada"}
    ):
        return False

    minimum_confidence = 75 if symbol.endswith("-OTC") else 70
    if float(analysis.get("confidence") or 0) < minimum_confidence:
        return False

    try:
        rows_1m = frames["1m"]
        if not rows_1m:
            return False
        # Candle muito antigo não pode servir como sinal de entrada "agora".
        age_seconds = time.time() - rows_1m[-1]["time"]
        if age_seconds < -5 or age_seconds > 150:
            return False

        score_15m = _directional_score(_summarize(frames["15m"], "15m"))
        score_5m = _directional_score(_summarize(frames["5m"], "5m"))
        score_1m = _directional_score(_summarize(rows_1m, "1m"))
        local_trigger = _entry_trigger(rows_1m, decision)
    except (KeyError, IndexError, TypeError, ValueError):
        return False

    expected_sign = 1 if decision == "CALL" else -1
    return (
        score_15m * expected_sign >= 2
        and score_5m * expected_sign >= 2
        and score_1m * expected_sign >= 1
        and local_trigger is not None
    )


async def _fetch_candles(client: Any, symbol: str, timeframe: str) -> list[dict[str, float]]:
    interval = INTERVALS[timeframe]
    try:
        raw = await asyncio.wait_for(
            client.get_candles(
                symbol,
                interval,
                COUNTS[timeframe],
                int(time.time()),
            ),
            timeout=12,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"A IQ Option demorou para responder os candles de {symbol} ({timeframe}).",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao obter candles de {symbol} ({timeframe}) na IQ Option: {str(exc)[:180]}",
        ) from exc

    rows = _normalize_rows(raw)
    now = time.time()
    closed = [
        row for row in rows
        if row["time"] + interval <= now + 0.5
    ]

    if len(closed) < MIN_CLOSED[timeframe] and len(rows) > 1:
        closed = rows[:-1]

    if len(closed) < MIN_CLOSED[timeframe]:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Candles fechados insuficientes para {symbol} em {timeframe}: "
                f"{len(closed)} disponíveis, {MIN_CLOSED[timeframe]} necessários."
            ),
        )

    return closed


async def _load_frames(
    client: Any,
    symbol: str,
) -> dict[str, list[dict[str, float]]]:
    now = time.monotonic()
    cached = LIVE_FRAMES_CACHE.get(symbol)
    if cached and now - cached[0] < LIVE_FRAMES_CACHE_TTL:
        return cached[1]

    frame_results = await asyncio.gather(*(
        _fetch_candles(client, symbol, timeframe)
        for timeframe in INTERVALS
    ))
    frames = {
        timeframe: rows
        for timeframe, rows in zip(INTERVALS.keys(), frame_results)
    }
    LIVE_FRAMES_CACHE[symbol] = (time.monotonic(), frames)
    return frames


def _fast_screen(
    frames: dict[str, list[dict[str, float]]],
) -> tuple[bool, str, dict[str, dict[str, Any]]]:
    # A triagem local usa o contexto de 15m e a estrutura de 5m.
    # O gatilho de entrada será verificado separadamente nos candles fechados de 1m.
    summaries = {
        timeframe: _summarize(frames[timeframe], timeframe)
        for timeframe in ("15m", "5m", "1m")
    }
    s15, s5, s1 = summaries["15m"], summaries["5m"], summaries["1m"]
    score_15m = _directional_score(s15)
    score_5m = _directional_score(s5)
    score_1m = _directional_score(s1)
    s15["directional_score"] = score_15m
    s5["directional_score"] = score_5m
    s1["directional_score"] = score_1m

    if score_15m * score_5m <= 0 or abs(score_15m) < 2 or abs(score_5m) < 2:
        reason = (
            "Diagnóstico rápido: sem alinhamento direcional suficiente entre 15m "
            f"(pontuação {score_15m:+d}, tendência {s15['trend']}) e 5m "
            f"(pontuação {score_5m:+d}, tendência {s5['trend']}). "
            "Aguardar nova confirmação; esta leitura foi calculada sem IA."
        )
        return False, reason, summaries

    candle_atr_5m = s5.get("last_candle", {}).get("range_pct_atr")
    candle_atr_1m = s1.get("last_candle", {}).get("range_pct_atr")
    if (
        (candle_atr_5m is not None and candle_atr_5m >= 2.8)
        or (candle_atr_1m is not None and candle_atr_1m >= 2.8)
    ):
        reason = (
            "Diagnóstico rápido: viés direcional identificado, mas foi detectado "
            "um candle de amplitude extrema em 5m ou 1m. Aguardar estabilização; "
            "nenhum sinal de entrada."
        )
        return False, reason, summaries

    direction = "comprador" if score_15m > 0 else "vendedor"
    reason = (
        f"Triagem aprovada: viés {direction} alinhado em 15m ({score_15m:+d}) "
        f"e 5m ({score_5m:+d}); viés de curto prazo em 1m ({score_1m:+d}). "
        "Avaliando gatilho objetivo para expiração de 5 minutos."
    )
    return True, reason, summaries


def _screen_wait_analysis(
    symbol: str,
    frames: dict[str, list[dict[str, float]]],
    summaries: dict[str, dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    s15 = summaries["15m"]
    s5 = summaries["5m"]
    s1 = summaries["1m"]
    support = s5.get("support", {}).get("nearest")
    resistance = s5.get("resistance", {}).get("nearest")
    momentum = s1.get("momentum", {})
    volatility = s1.get("volatility", {})
    candle = s1.get("last_candle", {})
    return {
        "decision": "SEM OPERACAO",
        "status": "AGUARDAR",
        "confidence": 0,
        "timeframe": "1m",
        "expiry_minutes": 5,
        "summary": reason,
        "structure": str(s5.get("structure") or "Estrutura indisponível"),
        "trend": (
            f"15m: {s15.get('trend', '—')} (viés {s15.get('directional_score', 0):+d}) · "
            f"5m: {s5.get('trend', '—')} (viés {s5.get('directional_score', 0):+d}) · "
            f"1m: {s1.get('trend', '—')} (viés {s1.get('directional_score', 0):+d})"
        ),
        "zone": f"Suporte 5m próximo: {support if support is not None else '—'} · resistência 5m próxima: {resistance if resistance is not None else '—'}",
        "trigger": reason,
        "momentum": f"RSI 1m: {momentum.get('rsi14') if momentum.get('rsi14') is not None else '—'} · MACD histograma: {momentum.get('macd_hist') if momentum.get('macd_hist') is not None else '—'}",
        "volatility": f"ATR% 1m: {volatility.get('atr_pct_price') if volatility.get('atr_pct_price') is not None else '—'} · faixa candle/ATR: {candle.get('range_pct_atr') if candle.get('range_pct_atr') is not None else '—'}",
        "price_action": f"Último candle fechado 1m: {candle.get('direction', '—')} · corpo {round(float(candle.get('body_pct') or 0), 1)}%",
        "confluences": [],
        "risks": [reason],
        "why_now": "Nenhuma entrada será sinalizada enquanto a tendência de 15m/5m e o gatilho de 1m não apresentarem condições suficientemente coerentes.",
        "facts_warning": "",
        "data_quality": "moderada",
        "asset": symbol,
        "is_otc": symbol.endswith("-OTC"),
        "current_price": frames["1m"][-1]["close"],
        "source": "Triagem técnica local · sem chamada de IA",
        "automation": {"enabled": False, "orders": False, "execution": False},
    }


async def _facts(symbol: str) -> dict[str, Any]:
    cached = FACTS_CACHE.get(symbol)
    now = time.monotonic()
    if cached and now - cached[0] < FACTS_CACHE_TTL:
        return cached[1]

    try:
        facts = await asyncio.wait_for(
            asyncio.to_thread(
                biquote_service.get_facts,
                hours=24,
                importance="all",
                symbol=symbol,
            ),
            timeout=4,
        )
        if facts.get("available"):
            FACTS_CACHE[symbol] = (time.monotonic(), facts)
        return facts
    except Exception as exc:
        return {
            "available": False,
            "events": [],
            "warning": str(exc)[:180],
        }


def _filter_events(symbol: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    events = facts.get("events", []) if isinstance(facts, dict) else []
    base = symbol.replace("-OTC", "").replace("/", "")
    currencies = {base[:3], base[3:]} if len(base) == 6 else set()
    selected = []

    for event in events:
        currency = str(event.get("currency", "")).upper()
        if not currencies or not currency or currency in currencies:
            selected.append(event)

    return selected[:20]


async def _assets(client: Any) -> list[dict[str, Any]]:
    # O catálogo é estático na iqoptionapi e não depende de uma chamada
    # adicional ao websocket. Isso evita catálogo vazio quando a IQ Option
    # está conectada mas get_all_ACTIVES_OPCODE não responde.
    try:
        import iqoptionapi.constants as iq_constants
        active_map = dict(iq_constants.ACTIVES)
    except Exception:
        return []

    values: list[dict[str, Any]] = []
    for symbol, active_id in active_map.items():
        name = str(symbol or "").strip().upper()
        is_otc = name.endswith("-OTC")
        base = name[:-4] if is_otc else name

        if not (len(base) == 6 and base.isalpha()):
            continue

        values.append({
            "symbol": name,
            "activeId": int(active_id),
            "market": "OTC" if is_otc else "normal",
        })

    values.sort(key=lambda item: str(item["symbol"]))
    return values


def _ai_market_payload(
    symbol: str,
    frames: dict[str, list[dict[str, float]]],
    facts: dict[str, Any],
) -> dict[str, Any]:
    # A IA vê mais candles de 1m para avaliar o gatilho e usa 5m/15m como contexto.
    candle_limits = {"1m": 8, "5m": 5, "15m": 4}

    def compact_summary(rows: list[dict[str, float]], timeframe: str) -> dict[str, Any]:
        full = _summarize(rows, timeframe)
        return {
            "timeframe": timeframe,
            "candles_available": full["candles"],
            "price": full["current_price"],
            "trend": full["trend"],
            "structure": full["structure"],
            "ema": full["ema"],
            "support": full["support"],
            "resistance": full["resistance"],
            "momentum": full["momentum"],
            "volatility": full["volatility"],
            "stochastic": full["stochastic"],
            "adx": full["adx"],
            "obv_direction": full["obv_direction"],
            "last_candle": full["last_candle"],
            "recent_high": full["recent_high"],
            "recent_low": full["recent_low"],
        }

    return {
        "asset": symbol,
        "is_otc": symbol.endswith("-OTC"),
        "selection": {
            "timeframe_options": ["1m"],
            "expiry_options_minutes": [5],
            "instruction": "Entrada avaliada em candle fechado de 1m; 15m define o contexto, 5m confirma a estrutura e o gatilho deve ser objetivo no 1m. Expiração fixa de 5 minutos. Só indique CALL/PUT quando os períodos maiores estiverem alinhados e houver gatilho confirmado.",
        },
        "timeframes": {
            tf: {
                "summary": compact_summary(rows, tf),
                "recent_candles": _compact_candles(rows, candle_limits.get(tf, 4)),
            }
            for tf, rows in frames.items()
        },
        "facts": {
            "source": "Biquote",
            "available": bool(facts.get("available", False)),
            "warning": facts.get("warning"),
            "events": _filter_events(symbol, facts),
        },
    }


def _ai_message(
    symbol: str,
    frames: dict[str, list[dict[str, float]]],
    facts: dict[str, Any],
) -> str:
    market = _ai_market_payload(symbol, frames, facts)
    return (
        CONSULTOR_PROMPT
        + "\n\nDADOS DO MERCADO ATUAL:\n"
        + json.dumps(market, ensure_ascii=False, separators=(",", ":"))
    )


def _extract_chat_content(payload: dict[str, Any], provider: str) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"{provider}: resposta sem choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        text = "".join(parts).strip()
        if text:
            return text
    raise RuntimeError(f"{provider}: resposta sem conteúdo utilizável.")


def _call_openai_compatible(
    provider: str,
    api_url: str,
    api_key: str,
    model: str,
    message: str,
) -> str:
    import requests

    if not api_key:
        raise RuntimeError(f"{provider}: chave não configurada.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "OpenRouter":
        headers["HTTP-Referer"] = "https://resolvei-utilidades.onrender.com"
        headers["X-Title"] = "Resolvei Consultor Sênior"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Retorne somente o JSON exigido pelo usuário. Não use markdown."},
            {"role": "user", "content": message},
        ],
        "temperature": 0.1,
        # O Consultor devolve JSON compacto; 1200 tokens são suficientes e
        # reduzem o consumo de TPM nos planos gratuitos.
        "max_completion_tokens": 700,
    }

    # Groq suporta JSON mode neste endpoint. No OpenRouter/free alguns
    # endpoints gratuitos não expõem response_format; o parser do Consultor
    # valida o JSON depois da resposta.
    if provider == "Groq":
        payload["response_format"] = {"type": "json_object"}

    if provider == "Groq" and model.startswith("openai/gpt-oss"):
        # Mantém a capacidade de raciocínio sem reservar tanto orçamento de
        # tokens quanto "medium", importante para o limite gratuito de TPM.
        payload["reasoning_effort"] = "low"

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=15,
    )

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code >= 400:
        detail = ""
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message") or "")
            elif error:
                detail = str(error)
        raise RuntimeError(
            f"{provider}: HTTP {response.status_code}"
            + (f" — {detail[:220]}" if detail else "")
        )

    return _extract_chat_content(data, provider)


async def _call_gemini(
    symbol: str,
    frames: dict[str, list[dict[str, float]]],
    facts: dict[str, Any],
) -> tuple[str, str]:
    from server import GEMINI_API_KEY, GEMINI_MODEL, _provider_call

    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini: chave não configurada.")

    message = _ai_message(symbol, frames, facts)
    raw = await asyncio.to_thread(
        _provider_call,
        "gemini",
        GEMINI_API_KEY,
        GEMINI_MODEL,
        message,
    )
    return raw, GEMINI_MODEL


def _provider_is_ready(provider: str) -> bool:
    return time.monotonic() >= AI_PROVIDER_COOLDOWN.get(provider, 0.0)


def _mark_provider_failure(provider: str, exc: Exception) -> None:
    message = str(exc).lower()
    if "429" in message or "rate limit" in message or "too many requests" in message or "quota" in message:
        AI_PROVIDER_COOLDOWN[provider] = time.monotonic() + AI_PROVIDER_COOLDOWN_SECONDS


async def _call_ai_with_fallback(
    symbol: str,
    frames: dict[str, list[dict[str, float]]],
    facts: dict[str, Any],
) -> tuple[str, str, str]:
    import os

    message = _ai_message(symbol, frames, facts)
    attempts: list[str] = []

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
    if groq_key:
        if not _provider_is_ready("Groq"):
            attempts.append("Groq: pausa temporária após limite de requisições")
        else:
            try:
                raw = await asyncio.to_thread(
                    _call_openai_compatible,
                    "Groq",
                    "https://api.groq.com/openai/v1/chat/completions",
                    groq_key,
                    groq_model,
                    message,
                )
                return raw, "Groq", groq_model
            except Exception as exc:
                _mark_provider_failure("Groq", exc)
                attempts.append(str(exc)[:260])

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openrouter_model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
    if openrouter_key:
        if not _provider_is_ready("OpenRouter"):
            attempts.append("OpenRouter: pausa temporária após limite de requisições")
        else:
            try:
                raw = await asyncio.to_thread(
                    _call_openai_compatible,
                    "OpenRouter",
                    "https://openrouter.ai/api/v1/chat/completions",
                    openrouter_key,
                    openrouter_model,
                    message,
                )
                return raw, "OpenRouter", openrouter_model
            except Exception as exc:
                _mark_provider_failure("OpenRouter", exc)
                attempts.append(str(exc)[:260])

    from server import GEMINI_API_KEY

    if GEMINI_API_KEY:
        if not _provider_is_ready("Gemini"):
            attempts.append("Gemini: pausa temporária após limite de requisições")
        else:
            try:
                raw, model = await asyncio.wait_for(
                    _call_gemini(symbol, frames, facts),
                    timeout=15,
                )
                return raw, "Gemini", model
            except Exception as exc:
                _mark_provider_failure("Gemini", exc)
                attempts.append(str(exc)[:260])

    detail = "Nenhum provedor de IA conseguiu concluir a análise."
    if attempts:
        detail += " | " + " | ".join(attempts[:3])
    else:
        detail += " | Configure GROQ_API_KEY, OPENROUTER_API_KEY ou GEMINI_API_KEY."
    raise HTTPException(status_code=503, detail=detail)


@router.get("/market")
async def market_snapshot(
    symbol: str,
    timeframe: str = "1m",
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = get_session(x_iq_session)
    cleaned = _clean_symbol(symbol)
    selected_tf = str(timeframe or "1m").strip().lower()
    if selected_tf not in INTERVALS:
        selected_tf = "1m"

    cache_key = cleaned
    now = time.monotonic()
    cached = LIVE_MARKET_CACHE.get(cache_key)
    if cached and now - cached[0] < LIVE_MARKET_CACHE_TTL:
        snapshot = cached[1]
    else:
        client = item["client"]
        frames = await _load_frames(client, cleaned)

        snapshot = {
            "asset": cleaned,
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
            "frames": {
                tf: {
                    "summary": _summarize(rows, tf),
                    "candles": _compact_candles(
                        rows,
                        110 if tf == "1m" else 90 if tf == "5m" else 70,
                    ),
                }
                for tf, rows in frames.items()
            },
        }
        LIVE_MARKET_CACHE[cache_key] = (now, snapshot)

    selected = snapshot["frames"][selected_tf]
    return {
        "ok": True,
        "asset": snapshot["asset"],
        "timestamp": snapshot["timestamp"],
        "timeframe": selected_tf,
        "summary": selected["summary"],
        "candles": selected["candles"],
        "frames": {
            tf: {"summary": payload["summary"]}
            for tf, payload in snapshot["frames"].items()
        },
    }

@router.post("/consult")
async def consult(
    req: ConsultRequest,
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = get_session(x_iq_session)
    symbol = _clean_symbol(req.symbol)

    started = time.perf_counter()
    frames = await _load_frames(item["client"], symbol)
    fingerprint = _frames_fingerprint(frames)

    cached_response = _cached_consult_response(symbol, fingerprint, started)
    if cached_response is not None:
        return cached_response

    # Quick local screen. It returns a complete diagnostic immediately when
    # the technical context is mixed; the frontend displays it rather than
    # holding the whole page in a spinner for a trade that may never appear.
    eligible, reason, summaries = _fast_screen(frames)
    if not eligible:
        analysis = _screen_wait_analysis(symbol, frames, summaries, reason)
        analysis["diagnostics"] = {
            "serverDurationMs": round((time.perf_counter() - started) * 1000),
            "screening": "local",
            "aiCalled": False,
            "directionalScores": {
                "15m": summaries["15m"].get("directional_score", 0),
                "5m": summaries["5m"].get("directional_score", 0),
            },
            "cachedSnapshot": False,
        }
        response = {
            "ok": True,
            "found": False,
            "analysis": analysis,
            "next_check_seconds": 8,
        }
        _save_consult_response(symbol, fingerprint, response)
        return response

    facts = await _facts(symbol)
    raw_ai, provider, model = await _call_ai_with_fallback(symbol, frames, facts)
    analysis = _sanitize_analysis(_parse_ai_json(raw_ai))
    found = _entry_confirmed(analysis, frames, symbol)

    selected_tf = analysis["timeframe"]
    selected_rows = frames.get(selected_tf) or frames["5m"]
    analysis.update({
        "asset": symbol,
        "is_otc": symbol.endswith("-OTC"),
        "current_price": selected_rows[-1]["close"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gemini_model": model if provider == "Gemini" else "",
        "ai_provider": provider,
        "ai_model": model,
        "source": f"IQ Option candles + {provider} + Biquote (quando disponível)",
        "automation": {"enabled": False, "orders": False, "execution": False},
        "diagnostics": {
            "serverDurationMs": round((time.perf_counter() - started) * 1000),
            "candles": {timeframe: len(rows) for timeframe, rows in frames.items()},
            "factsAvailable": bool(facts.get("available", False)),
            "screening": "aprovada",
            "aiCalled": True,
            "directionalScores": {
                "15m": _directional_score(summaries["15m"]),
                "5m": _directional_score(summaries["5m"]),
            },
            "cachedSnapshot": False,
        },
    })

    if not found:
        candidate = analysis["decision"] if analysis["decision"] in {"CALL", "PUT"} else ""
        candidate_trigger = str(analysis.get("trigger") or "").strip()
        analysis["candidate_direction"] = candidate
        analysis["decision"] = "SEM OPERACAO"
        analysis["status"] = "AGUARDAR"
        analysis["confidence"] = 0
        if candidate:
            reason_text = (
                f"A IA avaliou um cenário {candidate}, mas a validação técnica independente "
                "não confirmou todos os requisitos. Sem entrada; aguardar novo candle/confirmacão."
            )
            analysis["summary"] = reason_text
            analysis["risks"] = (analysis.get("risks") or [])[:5] + ["Cenário direcional não passou na validação final."]
        elif not analysis.get("summary"):
            analysis["summary"] = (
                "Nenhum gatilho confirmado neste ciclo. A análise técnica foi atualizada "
                "e o monitoramento continua."
            )
        if not candidate_trigger:
            analysis["trigger"] = "Nenhum gatilho objetivo confirmado neste ciclo."

    response = {
        "ok": True,
        "found": found,
        "analysis": analysis,
        "next_check_seconds": 8 if not found else 0,
    }
    _save_consult_response(symbol, fingerprint, response)
    return response

@router.get("/assets")
async def assets(
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = get_session(x_iq_session)
    values = await _assets(item["client"])
    return {
        "ok": True,
        "assets": values,
        "total": len(values),
    }
