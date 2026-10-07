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
    timeframe: str = "1m"
    expiry_minutes: int = 1


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


def _sanitize_analysis(data: dict[str, Any], expiry: int) -> dict[str, Any]:
    decision = str(data.get("decision", "SEM OPERACAO")).upper().replace("Ç", "C")
    status = str(data.get("status", "AGUARDAR")).upper().replace("Ó", "O")

    if decision not in {"CALL", "PUT", "SEM OPERACAO"}:
        decision = "SEM OPERACAO"
    if status not in {"AGORA", "PROXIMO", "AGUARDAR", "NAO OPERAR"}:
        status = "AGUARDAR"

    try:
        confidence = max(0.0, min(100.0, float(data.get("confidence", 0))))
    except Exception:
        confidence = 0.0

    try:
        exp = int(data.get("expiry_minutes", expiry))
    except Exception:
        exp = expiry
    if exp not in {1, 5, 15}:
        exp = expiry

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
        "expiry_minutes": exp,
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


async def _facts(symbol: str) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                biquote_service.get_facts,
                hours=24,
                importance="all",
                symbol=symbol,
            ),
            timeout=6,
        )
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
    try:
        opcode = await asyncio.wait_for(
            asyncio.to_thread(client.get_all_ACTIVES_OPCODE),
            timeout=6,
        )
    except Exception:
        return []

    if not isinstance(opcode, dict):
        return []

    return [
        {
            "symbol": str(symbol).strip(),
            "activeId": active_id,
        }
        for symbol, active_id in sorted(opcode.items(), key=lambda x: str(x[0]))
        if str(symbol).strip()
    ]


async def _call_gemini(
    symbol: str,
    timeframe: str,
    expiry: int,
    frames: dict[str, list[dict[str, float]]],
    facts: dict[str, Any],
) -> tuple[str, str]:
    from server import GEMINI_API_KEY, GEMINI_MODEL, _provider_call

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="O Gemini do Resolvei não está configurado no servidor (GEMINI_API_KEY).",
        )

    market = {
        "asset": symbol,
        "is_otc": symbol.endswith("-OTC"),
        "requested_timeframe": timeframe,
        "expiry_minutes": expiry,
        "timeframes": {
            tf: {
                "summary": _summarize(rows, tf),
                "candles": _compact_candles(
                    rows,
                    110 if tf == timeframe else 80,
                ),
            }
            for tf, rows in frames.items()
        },
        "facts": {
            "source": "Biquote",
            "available": bool(facts.get("available", False)),
            "warning": facts.get("warning"),
            "events": _filter_events(symbol, facts),
        },
        "rules": [
            "Não invente fatos, volume, preço, candle ou indicador.",
            "Use os dados fornecidos como base factual.",
            "Conflito entre timeframes reduz a confiança.",
            "Sem gatilho confirmado, não force entrada AGORA.",
            "Se a localização do preço for ruim, prefira AGUARDAR.",
            "A resposta final deve ser JSON válido sem markdown.",
        ],
    }

    message = (
        CONSULTOR_PROMPT
        + "\\n\\nDADOS DO MERCADO ATUAL:\\n"
        + json.dumps(
            market,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    raw = await asyncio.to_thread(
        _provider_call,
        "gemini",
        GEMINI_API_KEY,
        GEMINI_MODEL,
        message,
    )

    return raw, GEMINI_MODEL


@router.post("/consult")
async def consult(
    req: ConsultRequest,
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = get_session(x_iq_session)
    symbol = _clean_symbol(req.symbol)

    if req.timeframe not in INTERVALS:
        raise HTTPException(
            status_code=400,
            detail="Timeframe inválido. Use 1m, 5m ou 15m.",
        )

    if req.expiry_minutes not in {1, 5, 15}:
        raise HTTPException(
            status_code=400,
            detail="Expiração inválida. Use 1, 5 ou 15 minutos.",
        )

    started = time.perf_counter()
    client = item["client"]

    frame_results = await asyncio.gather(*(
        _fetch_candles(client, symbol, timeframe)
        for timeframe in INTERVALS
    ))

    frames = {
        timeframe: rows
        for timeframe, rows in zip(INTERVALS.keys(), frame_results)
    }

    facts = await _facts(symbol)
    raw_ai, model = await _call_gemini(
        symbol,
        req.timeframe,
        req.expiry_minutes,
        frames,
        facts,
    )

    analysis = _sanitize_analysis(
        _parse_ai_json(raw_ai),
        req.expiry_minutes,
    )

    analysis.update({
        "asset": symbol,
        "timeframe": req.timeframe,
        "is_otc": symbol.endswith("-OTC"),
        "current_price": frames[req.timeframe][-1]["close"],
        "timestamp": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        "gemini_model": model,
        "source": "IQ Option candles + Gemini + Biquote (quando disponível)",
        "automation": {
            "enabled": False,
            "orders": False,
            "execution": False,
        },
        "diagnostics": {
            "serverDurationMs": round(
                (time.perf_counter() - started) * 1000
            ),
            "candles": {
                timeframe: len(rows)
                for timeframe, rows in frames.items()
            },
            "factsAvailable": bool(facts.get("available", False)),
        },
    })

    return {"ok": True, "analysis": analysis}


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
