from __future__ import annotations

import os
import time
from collections import deque
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

router = APIRouter(prefix="/api/guru-sinais", tags=["GURÚ DOS SINAIS"])

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
SIGNALS = deque(maxlen=200)
MARKET_CACHE: dict[str, tuple[float, list[dict[str, float]]]] = {}
CACHE_TTL_SECONDS = 20

INTERVALS = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}


class TradingViewSignal(BaseModel):
    secret: str = ""
    symbol: str = ""
    timeframe: str = ""
    price: float | None = None
    timestamp: str = ""
    trend: str = "NEUTRA"
    rsi: float | None = None
    macd: float | None = None
    macdSignal: float | None = None
    ema9: float | None = None
    ema21: float | None = None
    ema50: float | None = None
    bbPosition: float | None = None
    momentum: float | None = None
    volume: float | None = None
    volumeRatio: float | None = None
    candlePattern: str = ""
    support: bool = False
    resistance: bool = False
    breakoutUp: bool = False
    breakoutDown: bool = False
    source: str = "TradingView"


class MarketAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str = "automatica"


def normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if ":" in s:
        s = s.split(":")[-1]
    s = s.replace("-", "/").replace(" ", "")
    if "/" in s:
        return s
    if len(s) == 6 and s.isalpha():
        return f"{s[:3]}/{s[3:]}"
    raise HTTPException(status_code=400, detail="Informe um par de moedas válido, por exemplo EUR/USD.")


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for x in values[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains = []
    losses = []
    for i in range(len(values) - period, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd_values(values: list[float]) -> tuple[float, float]:
    fast = ema(values, 12)
    slow = ema(values, 26)
    line = [a - b for a, b in zip(fast, slow)]
    signal = ema(line, 9)
    return line[-1], signal[-1]


def bollinger_position(values: list[float], period: int = 20) -> float:
    if len(values) < period:
        return 0.5
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    sd = variance ** 0.5
    upper = mean + 2 * sd
    lower = mean - 2 * sd
    return 0.5 if upper == lower else max(0.0, min(1.0, (values[-1] - lower) / (upper - lower)))


def atr_pct(rows: list[dict[str, float]], period: int = 14) -> float:
    if len(rows) <= period:
        return 0.0
    tr = []
    for i in range(1, len(rows)):
        high, low = rows[i]["high"], rows[i]["low"]
        prev = rows[i - 1]["close"]
        tr.append(max(high - low, abs(high - prev), abs(low - prev)))
    atr = sum(tr[-period:]) / period
    return atr / rows[-1]["close"] if rows[-1]["close"] else 0.0


def candle_pattern(rows: list[dict[str, float]]) -> str:
    if len(rows) < 2:
        return "neutro"
    a, b = rows[-2], rows[-1]
    a_bull = a["close"] > a["open"]
    b_bull = b["close"] > b["open"]
    if not a_bull and b_bull and b["open"] <= a["close"] and b["close"] >= a["open"]:
        return "engolfo de alta"
    if a_bull and not b_bull and b["open"] >= a["close"] and b["close"] <= a["open"]:
        return "engolfo de baixa"
    return "bullish" if b_bull else "bearish"


def fetch_candles(symbol: str, timeframe: str, outputsize: int = 1000) -> list[dict[str, float]]:
    if not TWELVE_DATA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="O motor automático ainda não está configurado. Adicione TWELVE_DATA_API_KEY nas variáveis do Render."
        )
    interval = INTERVALS.get(timeframe)
    if not interval:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")

    cache_key = f"{symbol}|{timeframe}|{outputsize}"
    cached = MARKET_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "order": "asc",
                "apikey": TWELVE_DATA_API_KEY,
            },
            timeout=15,
        )
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After", "")
            wait = f" Aguarde {retry_after} segundos." if retry_after.isdigit() else " Aguarde alguns segundos."
            raise HTTPException(status_code=429, detail="Limite de consultas da fonte de mercado atingido." + wait)
        r.raise_for_status()
        data = r.json()
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar dados de mercado: {exc}") from exc

    if data.get("status") == "error" or not data.get("values"):
        raise HTTPException(status_code=502, detail=data.get("message", "A fonte de mercado não retornou candles."))

    rows = []
    for x in data["values"]:
        try:
            rows.append({
                "open": float(x["open"]),
                "high": float(x["high"]),
                "low": float(x["low"]),
                "close": float(x["close"]),
                "volume": float(x.get("volume") or 0),
                "datetime": x.get("datetime", ""),
            })
        except (TypeError, ValueError, KeyError):
            continue
    if len(rows) < 60:
        raise HTTPException(status_code=502, detail="Não foram recebidos candles suficientes para uma análise técnica confiável.")

    MARKET_CACHE[cache_key] = (time.time(), rows)
    return rows


def resample_rows(rows: list[dict[str, float]], source_minutes: int, target_minutes: int) -> list[dict[str, float]]:
    if target_minutes <= source_minutes or target_minutes % source_minutes != 0:
        return rows
    step = target_minutes // source_minutes
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


def timeframe_minutes(timeframe: str) -> int:
    return {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}.get(timeframe, 1)


def _last_sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    w = values[-period:] if len(values) >= period else values
    return sum(w) / len(w)


def _std(values: list[float], period: int = 20) -> float:
    w = values[-period:] if len(values) >= period else values
    if not w:
        return 0.0
    mean = sum(w) / len(w)
    return (sum((x - mean) ** 2 for x in w) / len(w)) ** 0.5


def _atr_value(rows: list[dict[str, float]], period: int = 14) -> float:
    if len(rows) < 2:
        return 0.0
    trs = []
    for i in range(1, len(rows)):
        h, l, prev = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
    return sum(trs[-period:]) / min(period, len(trs))


def _adx(rows: list[dict[str, float]], period: int = 14) -> tuple[float, float]:
    if len(rows) < period + 2:
        return 0.0, 0.0
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(rows)):
        h, l, ph, pl, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["high"], rows[i - 1]["low"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, down = h - ph, pl - l
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr = sum(trs[-period:]) / period
    if atr <= 0:
        return 0.0, 0.0
    pdi = 100 * (sum(plus_dm[-period:]) / period) / atr
    mdi = 100 * (sum(minus_dm[-period:]) / period) / atr
    dx = 100 * abs(pdi - mdi) / max(pdi + mdi, 1e-12)
    return dx, pdi - mdi


def _stochastic(rows: list[dict[str, float]], period: int = 14, smooth: int = 3) -> tuple[float, float]:
    if len(rows) < period:
        return 50.0, 50.0
    ks = []
    for i in range(max(period - 1, 0), len(rows)):
        w = rows[max(0, i - period + 1):i + 1]
        hi, lo = max(x["high"] for x in w), min(x["low"] for x in w)
        ks.append(50.0 if hi == lo else 100 * (rows[i]["close"] - lo) / (hi - lo))
    k = ks[-1] if ks else 50.0
    d = sum(ks[-smooth:]) / min(smooth, len(ks)) if ks else 50.0
    return k, d


def _cci(rows: list[dict[str, float]], period: int = 20) -> float:
    if not rows:
        return 0.0
    tp = [(x["high"] + x["low"] + x["close"]) / 3 for x in rows]
    w = tp[-period:]
    mean = sum(w) / len(w)
    dev = sum(abs(x - mean) for x in w) / len(w)
    return 0.0 if dev == 0 else (tp[-1] - mean) / (0.015 * dev)


def _williams_r(rows: list[dict[str, float]], period: int = 14) -> float:
    w = rows[-period:]
    if not w:
        return -50.0
    hi, lo = max(x["high"] for x in w), min(x["low"] for x in w)
    return -50.0 if hi == lo else -100 * (hi - rows[-1]["close"]) / (hi - lo)


def _mfi(rows: list[dict[str, float]], period: int = 14) -> float:
    if len(rows) < period + 1:
        return 50.0
    pos = neg = 0.0
    for i in range(len(rows) - period, len(rows)):
        cur, prev = rows[i], rows[i - 1]
        tp = (cur["high"] + cur["low"] + cur["close"]) / 3
        ptp = (prev["high"] + prev["low"] + prev["close"]) / 3
        flow = tp * max(cur.get("volume", 0.0), 0.0)
        if tp > ptp:
            pos += flow
        elif tp < ptp:
            neg += flow
    if neg == 0:
        return 100.0 if pos else 50.0
    ratio = pos / neg
    return 100 - 100 / (1 + ratio)


def _roc(values: list[float], period: int = 5) -> float:
    if len(values) <= period or values[-period - 1] == 0:
        return 0.0
    return (values[-1] / values[-period - 1] - 1) * 100


def _obv_slope(rows: list[dict[str, float]], period: int = 10) -> float:
    if len(rows) < 2:
        return 0.0
    obv = [0.0]
    for i in range(1, len(rows)):
        v = rows[i].get("volume", 0.0)
        obv.append(obv[-1] + (v if rows[i]["close"] > rows[i - 1]["close"] else -v if rows[i]["close"] < rows[i - 1]["close"] else 0.0))
    w = obv[-period:]
    return (w[-1] - w[0]) / max(abs(sum(w) / len(w)), 1.0)


def _vwap(rows: list[dict[str, float]], period: int = 30) -> float:
    w = rows[-period:]
    pv = sum(((x["high"] + x["low"] + x["close"]) / 3) * max(x.get("volume", 0.0), 0.0) for x in w)
    vol = sum(max(x.get("volume", 0.0), 0.0) for x in w)
    if vol > 0:
        return pv / vol
    return _last_sma([x["close"] for x in w], len(w))


def _supertrend(rows: list[dict[str, float]], period: int = 10, multiplier: float = 3.0) -> tuple[str, float]:
    if len(rows) < period + 2:
        return "NEUTRA", 0.0
    atr = _atr_value(rows, period)
    hl2 = (rows[-1]["high"] + rows[-1]["low"]) / 2
    upper, lower = hl2 + multiplier * atr, hl2 - multiplier * atr
    close = rows[-1]["close"]
    if close > upper - multiplier * atr * 0.15:
        return "ALTA", upper
    if close < lower + multiplier * atr * 0.15:
        return "BAIXA", lower
    return ("ALTA" if close >= _last_sma([x["close"] for x in rows], period) else "BAIXA"), (upper if close >= _last_sma([x["close"] for x in rows], period) else lower)


def _ichimoku(rows: list[dict[str, float]]) -> tuple[float, float, str]:
    if len(rows) < 52:
        return rows[-1]["close"], rows[-1]["close"], "NEUTRA"
    def mid(n):
        w = rows[-n:]
        return (max(x["high"] for x in w) + min(x["low"] for x in w)) / 2
    tenkan, kijun = mid(9), mid(26)
    span_a, span_b = (tenkan + kijun) / 2, mid(52)
    cloud_top, cloud_bottom = max(span_a, span_b), min(span_a, span_b)
    close = rows[-1]["close"]
    trend = "ALTA" if close > cloud_top and tenkan > kijun else "BAIXA" if close < cloud_bottom and tenkan < kijun else "NEUTRA"
    return cloud_top, cloud_bottom, trend


def _score_signal(items: list[tuple[str, float, str]]) -> tuple[float, float, float]:
    buy = sum(w for _, w, d in items if d == "CALL")
    sell = sum(w for _, w, d in items if d == "PUT")
    total = sum(w for _, w, d in items if d in {"CALL", "PUT"})
    confidence = 50.0 + (abs(buy - sell) / total * 50.0) if total else 50.0
    return buy, sell, min(100.0, confidence)


def _strategy_pack(rows: list[dict[str, float]], strategy: str) -> dict[str, Any]:
    closes = [x["close"] for x in rows]
    e9, e21, e50, e200 = [ema(closes, p)[-1] for p in (9, 21, 50, 200)]
    r = rsi(closes)
    macd, macd_signal = macd_values(closes)
    hist = macd - macd_signal
    atr = _atr_value(rows, 14)
    atr_pct = (atr / closes[-1] * 100) if closes[-1] else 0.0
    atr_prev = _atr_value(rows[:-10], 14) if len(rows) > 30 else atr
    adx, di_diff = _adx(rows)
    st_k, st_d = _stochastic(rows)
    cci = _cci(rows)
    willr = _williams_r(rows)
    mfi = _mfi(rows)
    roc = _roc(closes, 5)
    vwap = _vwap(rows)
    vr = rows[-1].get("volume", 0.0) / max(_last_sma([x.get("volume", 0.0) for x in rows], 20), 1e-12)
    obv = _obv_slope(rows)
    bb_mid = _last_sma(closes, 20)
    bb_sd = _std(closes, 20)
    bb_upper, bb_lower = bb_mid + 2 * bb_sd, bb_mid - 2 * bb_sd
    bb_pos = 0.5 if bb_upper == bb_lower else max(0.0, min(1.0, (closes[-1] - bb_lower) / (bb_upper - bb_lower)))
    bb_width = ((bb_upper - bb_lower) / closes[-1] * 100) if closes[-1] else 0.0
    bb_width_prev = (((_last_sma(closes[:-10], 20) + 2 * _std(closes[:-10], 20)) - (_last_sma(closes[:-10], 20) - 2 * _std(closes[:-10], 20))) / closes[-11] * 100) if len(closes) > 40 and closes[-11] else bb_width
    high20 = max(x["high"] for x in rows[-20:])
    low20 = min(x["low"] for x in rows[-20:])
    prev_high20 = max(x["high"] for x in rows[-21:-1])
    prev_low20 = min(x["low"] for x in rows[-21:-1])
    donchian_up = closes[-1] > prev_high20
    donchian_down = closes[-1] < prev_low20
    near_support = (closes[-1] - low20) / max(high20 - low20, closes[-1] * 1e-8) < 0.16
    near_resistance = (high20 - closes[-1]) / max(high20 - low20, closes[-1] * 1e-8) < 0.16
    st_trend, st_level = _supertrend(rows)
    cloud_top, cloud_bottom, ichi = _ichimoku(rows)
    candle = candle_pattern(rows)
    structure = "CALL" if closes[-1] > closes[-3] > closes[-6] else "PUT" if closes[-1] < closes[-3] < closes[-6] else "NEUTRA"
    volume_dir = "CALL" if vr >= 1.15 and closes[-1] >= closes[-2] else "PUT" if vr >= 1.15 and closes[-1] < closes[-2] else "NEUTRA"
    items: list[tuple[str, float, str]] = []

    if strategy == "tendencia":
        items = [
            ("EMA 9/21/50/200", 1.4, "CALL" if e9 > e21 > e50 > e200 else "PUT" if e9 < e21 < e50 < e200 else "NEUTRA"),
            ("ADX + DI", 1.2, "CALL" if adx >= 20 and di_diff > 0 else "PUT" if adx >= 20 and di_diff < 0 else "NEUTRA"),
            ("MACD", 1.1, "CALL" if hist > 0 else "PUT" if hist < 0 else "NEUTRA"),
            ("RSI regime", 0.9, "CALL" if 52 <= r <= 68 else "PUT" if 32 <= r <= 48 else "NEUTRA"),
            ("Supertrend", 1.1, "CALL" if st_trend == "ALTA" else "PUT" if st_trend == "BAIXA" else "NEUTRA"),
            ("Ichimoku", 1.0, "CALL" if ichi == "ALTA" else "PUT" if ichi == "BAIXA" else "NEUTRA"),
            ("VWAP", 0.8, "CALL" if closes[-1] > vwap else "PUT" if closes[-1] < vwap else "NEUTRA"),
            ("Donchian", 0.8, "CALL" if donchian_up else "PUT" if donchian_down else "NEUTRA"),
            ("ROC", 0.7, "CALL" if roc > 0.03 else "PUT" if roc < -0.03 else "NEUTRA"),
            ("OBV", 0.7, "CALL" if obv > 0.02 else "PUT" if obv < -0.02 else "NEUTRA"),
            ("Volume", 0.6, volume_dir),
            ("Price structure", 0.7, structure),
        ]
    elif strategy == "reversao":
        items = [
            ("Bollinger position", 1.2, "CALL" if bb_pos <= 0.12 else "PUT" if bb_pos >= 0.88 else "NEUTRA"),
            ("RSI extreme", 1.1, "CALL" if r <= 30 else "PUT" if r >= 70 else "NEUTRA"),
            ("Stochastic", 1.0, "CALL" if st_k <= 20 and st_k >= st_d else "PUT" if st_k >= 80 and st_k <= st_d else "NEUTRA"),
            ("CCI", 0.9, "CALL" if cci <= -100 else "PUT" if cci >= 100 else "NEUTRA"),
            ("Williams %R", 0.8, "CALL" if willr <= -80 else "PUT" if willr >= -20 else "NEUTRA"),
            ("MFI", 0.8, "CALL" if mfi <= 20 else "PUT" if mfi >= 80 else "NEUTRA"),
            ("VWAP distance", 0.8, "CALL" if closes[-1] < vwap * 0.9995 else "PUT" if closes[-1] > vwap * 1.0005 else "NEUTRA"),
            ("Support/resistance", 1.0, "CALL" if near_support else "PUT" if near_resistance else "NEUTRA"),
            ("Candle reversal", 0.8, "CALL" if "alta" in candle or candle == "bullish" else "PUT" if "baixa" in candle or candle == "bearish" else "NEUTRA"),
            ("ATR regime", 0.6, "CALL" if atr_pct >= 0.02 and closes[-1] < vwap else "PUT" if atr_pct >= 0.02 and closes[-1] > vwap else "NEUTRA"),
            ("ADX range filter", 0.6, "CALL" if adx < 18 and bb_pos < 0.2 else "PUT" if adx < 18 and bb_pos > 0.8 else "NEUTRA"),
            ("Volume confirmation", 0.5, volume_dir),
        ]
    else:
        items = [
            ("Donchian breakout", 1.4, "CALL" if donchian_up else "PUT" if donchian_down else "NEUTRA"),
            ("Bollinger expansion", 1.0, "CALL" if bb_width > bb_width_prev and closes[-1] > bb_mid else "PUT" if bb_width > bb_width_prev and closes[-1] < bb_mid else "NEUTRA"),
            ("ATR expansion", 0.9, "CALL" if atr > atr_prev and closes[-1] > closes[-2] else "PUT" if atr > atr_prev and closes[-1] < closes[-2] else "NEUTRA"),
            ("ADX + DI", 1.1, "CALL" if adx >= 22 and di_diff > 0 else "PUT" if adx >= 22 and di_diff < 0 else "NEUTRA"),
            ("MACD histogram", 1.0, "CALL" if hist > 0 else "PUT" if hist < 0 else "NEUTRA"),
            ("EMA alignment", 1.0, "CALL" if e9 > e21 > e50 else "PUT" if e9 < e21 < e50 else "NEUTRA"),
            ("ROC", 0.8, "CALL" if roc > 0.05 else "PUT" if roc < -0.05 else "NEUTRA"),
            ("Volume expansion", 0.9, volume_dir),
            ("OBV", 0.8, "CALL" if obv > 0.02 else "PUT" if obv < -0.02 else "NEUTRA"),
            ("VWAP", 0.7, "CALL" if closes[-1] > vwap else "PUT" if closes[-1] < vwap else "NEUTRA"),
            ("Candle confirmation", 0.7, "CALL" if candle in {"bullish", "engolfo de alta"} else "PUT" if candle in {"bearish", "engolfo de baixa"} else "NEUTRA"),
            ("Price structure", 0.7, structure),
        ]

    buy, sell, confidence = _score_signal(items)
    direction = "CALL" if buy > sell else "PUT" if sell > buy else "NEUTRA"
    return {
        "strategy": strategy,
        "strategyLabel": {"tendencia": "Tendência + confluência", "reversao": "Reversão à média", "rompimento": "Rompimento + momentum"}[strategy],
        "buy": round(buy, 2),
        "sell": round(sell, 2),
        "confidence": round(confidence, 1),
        "direction": direction,
        "indicators": [
            {"name": n, "weight": w, "signal": d}
            for n, w, d in items
        ],
        "values": {
            "EMA9": e9, "EMA21": e21, "EMA50": e50, "EMA200": e200,
            "RSI": r, "MACD": macd, "MACDSignal": macd_signal, "MACDHistogram": hist,
            "BollingerPosition": bb_pos, "BollingerWidthPct": bb_width, "ATRpct": atr_pct,
            "ADX": adx, "DIplusMinus": di_diff, "StochasticK": st_k, "StochasticD": st_d,
            "CCI": cci, "WilliamsR": willr, "MFI": mfi, "ROC": roc, "VWAP": vwap,
            "VolumeRatio": vr, "OBVSlope": obv, "DonchianUp": donchian_up, "DonchianDown": donchian_down,
            "Supertrend": st_trend, "Ichimoku": ichi, "Support": near_support, "Resistance": near_resistance,
            "Candle": candle, "PriceStructure": structure,
        },
    }


def _gemini_review(symbol: str, timeframe: str, selected_strategy: str, strategies: list[dict[str, Any]], price: float, rows: list[dict[str, float]], authorization: str | None = None) -> dict[str, Any]:
    api_key = GEMINI_API_KEY
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    if authorization:
        try:
            from server import _resolve_ai_credentials
            provider, api_key, stored_model = _resolve_ai_credentials(authorization, "gemini")
            model = stored_model or model
        except Exception:
            if not api_key:
                raise
    if not api_key:
        return {"available": False, "reason": "Gemini não configurado."}

    selected = next((x for x in strategies if x["strategy"] == selected_strategy), strategies[0])
    recent = [{"o": round(x["open"], 6), "h": round(x["high"], 6), "l": round(x["low"], 6), "c": round(x["close"], 6), "v": round(x.get("volume", 0), 2)} for x in rows[-18:]]
    prompt = (
        "Você é o segundo motor de validação de um estudo técnico de opções binárias de curtíssimo prazo. "
        "Não invente dados e não use notícias. Avalie somente os indicadores e candles fornecidos. "
        "Há três estratégias independentes, cada uma com pelo menos 10 indicadores. "
        "Dê mais peso à confluência entre famílias diferentes (tendência, momentum, volatilidade, preço/estrutura e volume) "
        "e penalize sinais contraditórios. O objetivo é identificar a direção mais provável do próximo movimento no horizonte do timeframe, "
        "sem prometer acerto. Responda SOMENTE JSON válido no formato "
        "{\"signal\":\"CALL|PUT|AGUARDAR\",\"confidence\":0-100,\"reason\":\"texto curto\",\"risk\":\"baixo|medio|alto\"}. "
        f"Par={symbol}; timeframe={timeframe}; preço={price}; estratégia selecionada={selected_strategy}. "
        f"Dados das estratégias={json.dumps(strategies, ensure_ascii=False, separators=(',', ':'))}. "
        f"Candles recentes={json.dumps(recent, ensure_ascii=False, separators=(',', ':'))}. "
        "Se a confluência entre indicadores estiver claramente forte, escolha CALL ou PUT; se estiver dividida, use AGUARDAR."
    )
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 220},
        }
        resp = requests.post(url, headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=4.5)
        if not resp.ok:
            return {"available": False, "reason": f"Gemini HTTP {resp.status_code}"}
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        return {
            "available": True,
            "signal": parsed.get("signal", "AGUARDAR"),
            "confidence": float(parsed.get("confidence", 0)),
            "reason": str(parsed.get("reason", ""))[:300],
            "risk": str(parsed.get("risk", "alto")),
            "model": model,
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)[:220]}


def analyze_market(symbol: str, timeframe: str, strategy: str = "automatica", authorization: str | None = None) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    if timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")
    rows = fetch_candles(symbol, timeframe, 1000)
    strategies = [_strategy_pack(rows, s) for s in ("tendencia", "reversao", "rompimento")]

    if strategy == "automatica":
        selected = max(strategies, key=lambda x: x["confidence"] if x["direction"] != "NEUTRA" else 0)
    else:
        selected = next((x for x in strategies if x["strategy"] == strategy), None)
        if not selected:
            raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    # A análise determinística já está pronta antes da chamada ao Gemini.
    gemini = _gemini_review(symbol, timeframe, selected["strategy"], strategies, rows[-1]["close"], rows, authorization)
    base_signal = selected["direction"]
    base_conf = selected["confidence"]
    gem_signal = gemini.get("signal") if gemini.get("available") else None
    gem_conf = float(gemini.get("confidence", 0)) if gem_signal else 0.0

    if gem_signal in {"CALL", "PUT"} and gem_signal == base_signal:
        signal = base_signal
        score = round(min(99.0, 0.65 * base_conf + 0.35 * gem_conf))
        quality = "MUITO FORTE" if score >= 82 else "FORTE" if score >= 72 else "MODERADA"
    elif gem_signal in {"CALL", "PUT"} and base_signal in {"CALL", "PUT"}:
        signal = gem_signal if gem_conf >= base_conf + 8 else base_signal
        score = round(min(90.0, 0.55 * base_conf + 0.25 * gem_conf + 20 * (1 if gem_signal == base_signal else 0)))
        quality = "CONFLUÊNCIA PARCIAL"
    else:
        signal = base_signal if base_signal in {"CALL", "PUT"} else "AGUARDAR"
        score = round(base_conf)
        quality = "FORTE" if score >= 75 else "MODERADA" if score >= 65 else "BAIXA"

    reasons = [
        f"{x['strategyLabel']}: {x['direction']} com {x['confidence']:.0f}% de confluência."
        for x in strategies
        if x["direction"] in {"CALL", "PUT"}
    ]
    if gemini.get("available"):
        reasons.append("Gemini: " + (gemini.get("reason") or "validação concluída."))
    warnings = []
    if len({x["direction"] for x in strategies if x["direction"] in {"CALL", "PUT"}}) > 1:
        warnings.append("As estratégias divergem; o sinal foi tratado com maior cautela.")
    if gemini.get("available") and gem_signal in {"CALL", "PUT"} and gem_signal != base_signal:
        warnings.append("O Gemini divergiu do motor técnico principal.")
    if gemini.get("available") and gemini.get("risk") == "alto":
        warnings.append("O Gemini classificou o contexto como risco alto.")

    SIGNALS.appendleft({
        "signal": signal, "score": score, "quality": quality, "symbol": symbol, "timeframe": timeframe,
        "price": rows[-1]["close"], "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "buyScore": selected["buy"], "sellScore": selected["sell"],
        "reasons": reasons[:8], "warnings": warnings[:6],
        "strategy": selected["strategy"], "strategyLabel": selected["strategyLabel"],
        "strategies": strategies,
        "gemini": gemini,
        "indicators": selected["values"],
        "source": "Twelve Data + motor técnico + Gemini",
    })
    return SIGNALS[0]




@router.post("/market-analysis")
def market_analysis(req: MarketAnalysisRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return {"ok": True, "analysis": analyze_market(req.symbol, req.timeframe, req.strategy, authorization)}

rom __future__ import annotations

import os
import time
from collections import deque
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/guru-sinais", tags=["GURÚ DOS SINAIS"])

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
SIGNALS = deque(maxlen=200)
MARKET_CACHE: dict[str, tuple[float, list[dict[str, float]]]] = {}
CACHE_TTL_SECONDS = 20

INTERVALS = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}


class TradingViewSignal(BaseModel):
    secret: str = ""
    symbol: str = ""
    timeframe: str = ""
    price: float | None = None
    timestamp: str = ""
    trend: str = "NEUTRA"
    rsi: float | None = None
    macd: float | None = None
    macdSignal: float | None = None
    ema9: float | None = None
    ema21: float | None = None
    ema50: float | None = None
    bbPosition: float | None = None
    momentum: float | None = None
    volume: float | None = None
    volumeRatio: float | None = None
    candlePattern: str = ""
    support: bool = False
    resistance: bool = False
    breakoutUp: bool = False
    breakoutDown: bool = False
    source: str = "TradingView"


class MarketAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str


def normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if ":" in s:
        s = s.split(":")[-1]
    s = s.replace("-", "/").replace(" ", "")
    if "/" in s:
        return s
    if len(s) == 6 and s.isalpha():
        return f"{s[:3]}/{s[3:]}"
    raise HTTPException(status_code=400, detail="Informe um par de moedas válido, por exemplo EUR/USD.")


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for x in values[1:]:
        out.append(x * k + out[-1] * (1 - k))
    return out


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains = []
    losses = []
    for i in range(len(values) - period, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd_values(values: list[float]) -> tuple[float, float]:
    fast = ema(values, 12)
    slow = ema(values, 26)
    line = [a - b for a, b in zip(fast, slow)]
    signal = ema(line, 9)
    return line[-1], signal[-1]


def bollinger_position(values: list[float], period: int = 20) -> float:
    if len(values) < period:
        return 0.5
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    sd = variance ** 0.5
    upper = mean + 2 * sd
    lower = mean - 2 * sd
    return 0.5 if upper == lower else max(0.0, min(1.0, (values[-1] - lower) / (upper - lower)))


def atr_pct(rows: list[dict[str, float]], period: int = 14) -> float:
    if len(rows) <= period:
        return 0.0
    tr = []
    for i in range(1, len(rows)):
        high, low = rows[i]["high"], rows[i]["low"]
        prev = rows[i - 1]["close"]
        tr.append(max(high - low, abs(high - prev), abs(low - prev)))
    atr = sum(tr[-period:]) / period
    return atr / rows[-1]["close"] if rows[-1]["close"] else 0.0


def candle_pattern(rows: list[dict[str, float]]) -> str:
    if len(rows) < 2:
        return "neutro"
    a, b = rows[-2], rows[-1]
    a_bull = a["close"] > a["open"]
    b_bull = b["close"] > b["open"]
    if not a_bull and b_bull and b["open"] <= a["close"] and b["close"] >= a["open"]:
        return "engolfo de alta"
    if a_bull and not b_bull and b["open"] >= a["close"] and b["close"] <= a["open"]:
        return "engolfo de baixa"
    return "bullish" if b_bull else "bearish"


def fetch_candles(symbol: str, timeframe: str, outputsize: int = 1000) -> list[dict[str, float]]:
    if not TWELVE_DATA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="O motor automático ainda não está configurado. Adicione TWELVE_DATA_API_KEY nas variáveis do Render."
        )
    interval = INTERVALS.get(timeframe)
    if not interval:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")

    cache_key = f"{symbol}|{timeframe}|{outputsize}"
    cached = MARKET_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        r = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "order": "asc",
                "apikey": TWELVE_DATA_API_KEY,
            },
            timeout=15,
        )
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After", "")
            wait = f" Aguarde {retry_after} segundos." if retry_after.isdigit() else " Aguarde alguns segundos."
            raise HTTPException(status_code=429, detail="Limite de consultas da fonte de mercado atingido." + wait)
        r.raise_for_status()
        data = r.json()
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar dados de mercado: {exc}") from exc

    if data.get("status") == "error" or not data.get("values"):
        raise HTTPException(status_code=502, detail=data.get("message", "A fonte de mercado não retornou candles."))

    rows = []
    for x in data["values"]:
        try:
            rows.append({
                "open": float(x["open"]),
                "high": float(x["high"]),
                "low": float(x["low"]),
                "close": float(x["close"]),
                "volume": float(x.get("volume") or 0),
                "datetime": x.get("datetime", ""),
            })
        except (TypeError, ValueError, KeyError):
            continue
    if len(rows) < 60:
        raise HTTPException(status_code=502, detail="Não foram recebidos candles suficientes para uma análise técnica confiável.")

    MARKET_CACHE[cache_key] = (time.time(), rows)
    return rows


def resample_rows(rows: list[dict[str, float]], source_minutes: int, target_minutes: int) -> list[dict[str, float]]:
    if target_minutes <= source_minutes or target_minutes % source_minutes != 0:
        return rows
    step = target_minutes // source_minutes
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


def timeframe_minutes(timeframe: str) -> int:
    return {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}.get(timeframe, 1)


def _last_sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    w = values[-period:] if len(values) >= period else values
    return sum(w) / len(w)


def _std(values: list[float], period: int = 20) -> float:
    w = values[-period:] if len(values) >= period else values
    if not w:
        return 0.0
    mean = sum(w) / len(w)
    return (sum((x - mean) ** 2 for x in w) / len(w)) ** 0.5


def _atr_value(rows: list[dict[str, float]], period: int = 14) -> float:
    if len(rows) < 2:
        return 0.0
    trs = []
    for i in range(1, len(rows)):
        h, l, prev = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
    return sum(trs[-period:]) / min(period, len(trs))


def _adx(rows: list[dict[str, float]], period: int = 14) -> tuple[float, float]:
    if len(rows) < period + 2:
        return 0.0, 0.0
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(rows)):
        h, l, ph, pl, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["high"], rows[i - 1]["low"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, down = h - ph, pl - l
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr = sum(trs[-period:]) / period
    if atr <= 0:
        return 0.0, 0.0
    pdi = 100 * (sum(plus_dm[-period:]) / period) / atr
    mdi = 100 * (sum(minus_dm[-period:]) / period) / atr
    dx = 100 * abs(pdi - mdi) / max(pdi + mdi, 1e-12)
    return dx, pdi - mdi


def _stochastic(rows: list[dict[str, float]], period: int = 14, smooth: int = 3) -> tuple[float, float]:
    if len(rows) < period:
        return 50.0, 50.0
    ks = []
    for i in range(max(period - 1, 0), len(rows)):
        w = rows[max(0, i - period + 1):i + 1]
        hi, lo = max(x["high"] for x in w), min(x["low"] for x in w)
        ks.append(50.0 if hi == lo else 100 * (rows[i]["close"] - lo) / (hi - lo))
    k = ks[-1] if ks else 50.0
    d = sum(ks[-smooth:]) / min(smooth, len(ks)) if ks else 50.0
    return k, d


def _cci(rows: list[dict[str, float]], period: int = 20) -> float:
    if not rows:
        return 0.0
    tp = [(x["high"] + x["low"] + x["close"]) / 3 for x in rows]
    w = tp[-period:]
    mean = sum(w) / len(w)
    dev = sum(abs(x - mean) for x in w) / len(w)
    return 0.0 if dev == 0 else (tp[-1] - mean) / (0.015 * dev)


def _williams_r(rows: list[dict[str, float]], period: int = 14) -> float:
    w = rows[-period:]
    if not w:
        return -50.0
    hi, lo = max(x["high"] for x in w), min(x["low"] for x in w)
    return -50.0 if hi == lo else -100 * (hi - rows[-1]["close"]) / (hi - lo)


def _mfi(rows: list[dict[str, float]], period: int = 14) -> float:
    if len(rows) < period + 1:
        return 50.0
    pos = neg = 0.0
    for i in range(len(rows) - period, len(rows)):
        cur, prev = rows[i], rows[i - 1]
        tp = (cur["high"] + cur["low"] + cur["close"]) / 3
        ptp = (prev["high"] + prev["low"] + prev["close"]) / 3
        flow = tp * max(cur.get("volume", 0.0), 0.0)
        if tp > ptp:
            pos += flow
        elif tp < ptp:
            neg += flow
    if neg == 0:
        return 100.0 if pos else 50.0
    ratio = pos / neg
    return 100 - 100 / (1 + ratio)


def _roc(values: list[float], period: int = 5) -> float:
    if len(values) <= period or values[-period - 1] == 0:
        return 0.0
    return (values[-1] / values[-period - 1] - 1) * 100


def _obv_slope(rows: list[dict[str, float]], period: int = 10) -> float:
    if len(rows) < 2:
        return 0.0
    obv = [0.0]
    for i in range(1, len(rows)):
        v = rows[i].get("volume", 0.0)
        obv.append(obv[-1] + (v if rows[i]["close"] > rows[i - 1]["close"] else -v if rows[i]["close"] < rows[i - 1]["close"] else 0.0))
    w = obv[-period:]
    return (w[-1] - w[0]) / max(abs(sum(w) / len(w)), 1.0)


def _vwap(rows: list[dict[str, float]], period: int = 30) -> float:
    w = rows[-period:]
    pv = sum(((x["high"] + x["low"] + x["close"]) / 3) * max(x.get("volume", 0.0), 0.0) for x in w)
    vol = sum(max(x.get("volume", 0.0), 0.0) for x in w)
    if vol > 0:
        return pv / vol
    return _last_sma([x["close"] for x in w], len(w))


def _supertrend(rows: list[dict[str, float]], period: int = 10, multiplier: float = 3.0) -> tuple[str, float]:
    if len(rows) < period + 2:
        return "NEUTRA", 0.0
    atr = _atr_value(rows, period)
    hl2 = (rows[-1]["high"] + rows[-1]["low"]) / 2
    upper, lower = hl2 + multiplier * atr, hl2 - multiplier * atr
    close = rows[-1]["close"]
    if close > upper - multiplier * atr * 0.15:
        return "ALTA", upper
    if close < lower + multiplier * atr * 0.15:
        return "BAIXA", lower
    return ("ALTA" if close >= _last_sma([x["close"] for x in rows], period) else "BAIXA"), (upper if close >= _last_sma([x["close"] for x in rows], period) else lower)


def _ichimoku(rows: list[dict[str, float]]) -> tuple[float, float, str]:
    if len(rows) < 52:
        return rows[-1]["close"], rows[-1]["close"], "NEUTRA"
    def mid(n):
        w = rows[-n:]
        return (max(x["high"] for x in w) + min(x["low"] for x in w)) / 2
    tenkan, kijun = mid(9), mid(26)
    span_a, span_b = (tenkan + kijun) / 2, mid(52)
    cloud_top, cloud_bottom = max(span_a, span_b), min(span_a, span_b)
    close = rows[-1]["close"]
    trend = "ALTA" if close > cloud_top and tenkan > kijun else "BAIXA" if close < cloud_bottom and tenkan < kijun else "NEUTRA"
    return cloud_top, cloud_bottom, trend


def _score_signal(items: list[tuple[str, float, str]]) -> tuple[float, float, float]:
    buy = sum(w for _, w, d in items if d == "CALL")
    sell = sum(w for _, w, d in items if d == "PUT")
    total = sum(w for _, w, d in items if d in {"CALL", "PUT"})
    confidence = 50.0 + (abs(buy - sell) / total * 50.0) if total else 50.0
    return buy, sell, min(100.0, confidence)


def _strategy_pack(rows: list[dict[str, float]], strategy: str) -> dict[str, Any]:
    closes = [x["close"] for x in rows]
    e9, e21, e50, e200 = [ema(closes, p)[-1] for p in (9, 21, 50, 200)]
    r = rsi(closes)
    macd, macd_signal = macd_values(closes)
    hist = macd - macd_signal
    atr = _atr_value(rows, 14)
    atr_pct = (atr / closes[-1] * 100) if closes[-1] else 0.0
    atr_prev = _atr_value(rows[:-10], 14) if len(rows) > 30 else atr
    adx, di_diff = _adx(rows)
    st_k, st_d = _stochastic(rows)
    cci = _cci(rows)
    willr = _williams_r(rows)
    mfi = _mfi(rows)
    roc = _roc(closes, 5)
    vwap = _vwap(rows)
    vr = rows[-1].get("volume", 0.0) / max(_last_sma([x.get("volume", 0.0) for x in rows], 20), 1e-12)
    obv = _obv_slope(rows)
    bb_mid = _last_sma(closes, 20)
    bb_sd = _std(closes, 20)
    bb_upper, bb_lower = bb_mid + 2 * bb_sd, bb_mid - 2 * bb_sd
    bb_pos = 0.5 if bb_upper == bb_lower else max(0.0, min(1.0, (closes[-1] - bb_lower) / (bb_upper - bb_lower)))
    bb_width = ((bb_upper - bb_lower) / closes[-1] * 100) if closes[-1] else 0.0
    bb_width_prev = (((_last_sma(closes[:-10], 20) + 2 * _std(closes[:-10], 20)) - (_last_sma(closes[:-10], 20) - 2 * _std(closes[:-10], 20))) / closes[-11] * 100) if len(closes) > 40 and closes[-11] else bb_width
    high20 = max(x["high"] for x in rows[-20:])
    low20 = min(x["low"] for x in rows[-20:])
    prev_high20 = max(x["high"] for x in rows[-21:-1])
    prev_low20 = min(x["low"] for x in rows[-21:-1])
    donchian_up = closes[-1] > prev_high20
    donchian_down = closes[-1] < prev_low20
    near_support = (closes[-1] - low20) / max(high20 - low20, closes[-1] * 1e-8) < 0.16
    near_resistance = (high20 - closes[-1]) / max(high20 - low20, closes[-1] * 1e-8) < 0.16
    st_trend, st_level = _supertrend(rows)
    cloud_top, cloud_bottom, ichi = _ichimoku(rows)
    candle = candle_pattern(rows)
    structure = "CALL" if closes[-1] > closes[-3] > closes[-6] else "PUT" if closes[-1] < closes[-3] < closes[-6] else "NEUTRA"
    volume_dir = "CALL" if vr >= 1.15 and closes[-1] >= closes[-2] else "PUT" if vr >= 1.15 and closes[-1] < closes[-2] else "NEUTRA"
    items: list[tuple[str, float, str]] = []

    if strategy == "tendencia":
        items = [
            ("EMA 9/21/50/200", 1.4, "CALL" if e9 > e21 > e50 > e200 else "PUT" if e9 < e21 < e50 < e200 else "NEUTRA"),
            ("ADX + DI", 1.2, "CALL" if adx >= 20 and di_diff > 0 else "PUT" if adx >= 20 and di_diff < 0 else "NEUTRA"),
            ("MACD", 1.1, "CALL" if hist > 0 else "PUT" if hist < 0 else "NEUTRA"),
            ("RSI regime", 0.9, "CALL" if 52 <= r <= 68 else "PUT" if 32 <= r <= 48 else "NEUTRA"),
            ("Supertrend", 1.1, "CALL" if st_trend == "ALTA" else "PUT" if st_trend == "BAIXA" else "NEUTRA"),
            ("Ichimoku", 1.0, "CALL" if ichi == "ALTA" else "PUT" if ichi == "BAIXA" else "NEUTRA"),
            ("VWAP", 0.8, "CALL" if closes[-1] > vwap else "PUT" if closes[-1] < vwap else "NEUTRA"),
            ("Donchian", 0.8, "CALL" if donchian_up else "PUT" if donchian_down else "NEUTRA"),
            ("ROC", 0.7, "CALL" if roc > 0.03 else "PUT" if roc < -0.03 else "NEUTRA"),
            ("OBV", 0.7, "CALL" if obv > 0.02 else "PUT" if obv < -0.02 else "NEUTRA"),
            ("Volume", 0.6, volume_dir),
            ("Price structure", 0.7, structure),
        ]
    elif strategy == "reversao":
        items = [
            ("Bollinger position", 1.2, "CALL" if bb_pos <= 0.12 else "PUT" if bb_pos >= 0.88 else "NEUTRA"),
            ("RSI extreme", 1.1, "CALL" if r <= 30 else "PUT" if r >= 70 else "NEUTRA"),
            ("Stochastic", 1.0, "CALL" if st_k <= 20 and st_k >= st_d else "PUT" if st_k >= 80 and st_k <= st_d else "NEUTRA"),
            ("CCI", 0.9, "CALL" if cci <= -100 else "PUT" if cci >= 100 else "NEUTRA"),
            ("Williams %R", 0.8, "CALL" if willr <= -80 else "PUT" if willr >= -20 else "NEUTRA"),
            ("MFI", 0.8, "CALL" if mfi <= 20 else "PUT" if mfi >= 80 else "NEUTRA"),
            ("VWAP distance", 0.8, "CALL" if closes[-1] < vwap * 0.9995 else "PUT" if closes[-1] > vwap * 1.0005 else "NEUTRA"),
            ("Support/resistance", 1.0, "CALL" if near_support else "PUT" if near_resistance else "NEUTRA"),
            ("Candle reversal", 0.8, "CALL" if "alta" in candle or candle == "bullish" else "PUT" if "baixa" in candle or candle == "bearish" else "NEUTRA"),
            ("ATR regime", 0.6, "CALL" if atr_pct >= 0.02 and closes[-1] < vwap else "PUT" if atr_pct >= 0.02 and closes[-1] > vwap else "NEUTRA"),
            ("ADX range filter", 0.6, "CALL" if adx < 18 and bb_pos < 0.2 else "PUT" if adx < 18 and bb_pos > 0.8 else "NEUTRA"),
            ("Volume confirmation", 0.5, volume_dir),
        ]
    else:
        items = [
            ("Donchian breakout", 1.4, "CALL" if donchian_up else "PUT" if donchian_down else "NEUTRA"),
            ("Bollinger expansion", 1.0, "CALL" if bb_width > bb_width_prev and closes[-1] > bb_mid else "PUT" if bb_width > bb_width_prev and closes[-1] < bb_mid else "NEUTRA"),
            ("ATR expansion", 0.9, "CALL" if atr > atr_prev and closes[-1] > closes[-2] else "PUT" if atr > atr_prev and closes[-1] < closes[-2] else "NEUTRA"),
            ("ADX + DI", 1.1, "CALL" if adx >= 22 and di_diff > 0 else "PUT" if adx >= 22 and di_diff < 0 else "NEUTRA"),
            ("MACD histogram", 1.0, "CALL" if hist > 0 else "PUT" if hist < 0 else "NEUTRA"),
            ("EMA alignment", 1.0, "CALL" if e9 > e21 > e50 else "PUT" if e9 < e21 < e50 else "NEUTRA"),
            ("ROC", 0.8, "CALL" if roc > 0.05 else "PUT" if roc < -0.05 else "NEUTRA"),
            ("Volume expansion", 0.9, volume_dir),
            ("OBV", 0.8, "CALL" if obv > 0.02 else "PUT" if obv < -0.02 else "NEUTRA"),
            ("VWAP", 0.7, "CALL" if closes[-1] > vwap else "PUT" if closes[-1] < vwap else "NEUTRA"),
            ("Candle confirmation", 0.7, "CALL" if candle in {"bullish", "engolfo de alta"} else "PUT" if candle in {"bearish", "engolfo de baixa"} else "NEUTRA"),
            ("Price structure", 0.7, structure),
        ]

    buy, sell, confidence = _score_signal(items)
    direction = "CALL" if buy > sell else "PUT" if sell > buy else "NEUTRA"
    return {
        "strategy": strategy,
        "strategyLabel": {"tendencia": "Tendência + confluência", "reversao": "Reversão à média", "rompimento": "Rompimento + momentum"}[strategy],
        "buy": round(buy, 2),
        "sell": round(sell, 2),
        "confidence": round(confidence, 1),
        "direction": direction,
        "indicators": [
            {"name": n, "weight": w, "signal": d}
            for n, w, d in items
        ],
        "values": {
            "EMA9": e9, "EMA21": e21, "EMA50": e50, "EMA200": e200,
            "RSI": r, "MACD": macd, "MACDSignal": macd_signal, "MACDHistogram": hist,
            "BollingerPosition": bb_pos, "BollingerWidthPct": bb_width, "ATRpct": atr_pct,
            "ADX": adx, "DIplusMinus": di_diff, "StochasticK": st_k, "StochasticD": st_d,
            "CCI": cci, "WilliamsR": willr, "MFI": mfi, "ROC": roc, "VWAP": vwap,
            "VolumeRatio": vr, "OBVSlope": obv, "DonchianUp": donchian_up, "DonchianDown": donchian_down,
            "Supertrend": st_trend, "Ichimoku": ichi, "Support": near_support, "Resistance": near_resistance,
            "Candle": candle, "PriceStructure": structure,
        },
    }


def _gemini_review(symbol: str, timeframe: str, selected_strategy: str, strategies: list[dict[str, Any]], price: float, rows: list[dict[str, float]], authorization: str | None = None) -> dict[str, Any]:
    api_key = GEMINI_API_KEY
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    if authorization:
        try:
            from server import _resolve_ai_credentials
            provider, api_key, stored_model = _resolve_ai_credentials(authorization, "gemini")
            model = stored_model or model
        except Exception:
            if not api_key:
                raise
    if not api_key:
        return {"available": False, "reason": "Gemini não configurado."}

    selected = next((x for x in strategies if x["strategy"] == selected_strategy), strategies[0])
    recent = [{"o": round(x["open"], 6), "h": round(x["high"], 6), "l": round(x["low"], 6), "c": round(x["close"], 6), "v": round(x.get("volume", 0), 2)} for x in rows[-18:]]
    prompt = (
        "Você é o segundo motor de validação de um estudo técnico de opções binárias de curtíssimo prazo. "
        "Não invente dados e não use notícias. Avalie somente os indicadores e candles fornecidos. "
        "Há três estratégias independentes, cada uma com pelo menos 10 indicadores. "
        "Dê mais peso à confluência entre famílias diferentes (tendência, momentum, volatilidade, preço/estrutura e volume) "
        "e penalize sinais contraditórios. O objetivo é identificar a direção mais provável do próximo movimento no horizonte do timeframe, "
        "sem prometer acerto. Responda SOMENTE JSON válido no formato "
        "{\"signal\":\"CALL|PUT|AGUARDAR\",\"confidence\":0-100,\"reason\":\"texto curto\",\"risk\":\"baixo|medio|alto\"}. "
        f"Par={symbol}; timeframe={timeframe}; preço={price}; estratégia selecionada={selected_strategy}. "
        f"Dados das estratégias={json.dumps(strategies, ensure_ascii=False, separators=(',', ':'))}. "
        f"Candles recentes={json.dumps(recent, ensure_ascii=False, separators=(',', ':'))}. "
        "Se a confluência entre indicadores estiver claramente forte, escolha CALL ou PUT; se estiver dividida, use AGUARDAR."
    )
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 220},
        }
        resp = requests.post(url, headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=4.5)
        if not resp.ok:
            return {"available": False, "reason": f"Gemini HTTP {resp.status_code}"}
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        return {
            "available": True,
            "signal": parsed.get("signal", "AGUARDAR"),
            "confidence": float(parsed.get("confidence", 0)),
            "reason": str(parsed.get("reason", ""))[:300],
            "risk": str(parsed.get("risk", "alto")),
            "model": model,
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)[:220]}


def analyze_market(symbol: str, timeframe: str, strategy: str = "automatica", authorization: str | None = None) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    if timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")
    rows = fetch_candles(symbol, timeframe, 1000)
    strategies = [_strategy_pack(rows, s) for s in ("tendencia", "reversao", "rompimento")]

    if strategy == "automatica":
        selected = max(strategies, key=lambda x: x["confidence"] if x["direction"] != "NEUTRA" else 0)
    else:
        selected = next((x for x in strategies if x["strategy"] == strategy), None)
        if not selected:
            raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    # A análise determinística já está pronta antes da chamada ao Gemini.
    gemini = _gemini_review(symbol, timeframe, selected["strategy"], strategies, rows[-1]["close"], rows, authorization)
    base_signal = selected["direction"]
    base_conf = selected["confidence"]
    gem_signal = gemini.get("signal") if gemini.get("available") else None
    gem_conf = float(gemini.get("confidence", 0)) if gem_signal else 0.0

    if gem_signal in {"CALL", "PUT"} and gem_signal == base_signal:
        signal = base_signal
        score = round(min(99.0, 0.65 * base_conf + 0.35 * gem_conf))
        quality = "MUITO FORTE" if score >= 82 else "FORTE" if score >= 72 else "MODERADA"
    elif gem_signal in {"CALL", "PUT"} and base_signal in {"CALL", "PUT"}:
        signal = gem_signal if gem_conf >= base_conf + 8 else base_signal
        score = round(min(90.0, 0.55 * base_conf + 0.25 * gem_conf + 20 * (1 if gem_signal == base_signal else 0)))
        quality = "CONFLUÊNCIA PARCIAL"
    else:
        signal = base_signal if base_signal in {"CALL", "PUT"} else "AGUARDAR"
        score = round(base_conf)
        quality = "FORTE" if score >= 75 else "MODERADA" if score >= 65 else "BAIXA"

    reasons = [
        f"{x['strategyLabel']}: {x['direction']} com {x['confidence']:.0f}% de confluência."
        for x in strategies
        if x["direction"] in {"CALL", "PUT"}
    ]
    if gemini.get("available"):
        reasons.append("Gemini: " + (gemini.get("reason") or "validação concluída."))
    warnings = []
    if len({x["direction"] for x in strategies if x["direction"] in {"CALL", "PUT"}}) > 1:
        warnings.append("As estratégias divergem; o sinal foi tratado com maior cautela.")
    if gemini.get("available") and gem_signal in {"CALL", "PUT"} and gem_signal != base_signal:
        warnings.append("O Gemini divergiu do motor técnico principal.")
    if gemini.get("available") and gemini.get("risk") == "alto":
        warnings.append("O Gemini classificou o contexto como risco alto.")

    SIGNALS.appendleft({
        "signal": signal, "score": score, "quality": quality, "symbol": symbol, "timeframe": timeframe,
        "price": rows[-1]["close"], "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "buyScore": selected["buy"], "sellScore": selected["sell"],
        "reasons": reasons[:8], "warnings": warnings[:6],
        "strategy": selected["strategy"], "strategyLabel": selected["strategyLabel"],
        "strategies": strategies,
        "gemini": gemini,
        "indicators": selected["values"],
        "source": "Twelve Data + motor técnico + Gemini",
    })
    return SIGNALS[0]




@router.post("/market-analysis")
def market_analysis(req: MarketAnalysisRequest) -> dict[str, Any]:
    return {"ok": True, "analysis": analyze_market(req.symbol, req.timeframe)}


@router.post("/webhook")
def receive_webhook(data: TradingViewSignal) -> dict[str, Any]:
    if WEBHOOK_SECRET and data.secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Webhook não autorizado.")
    result = analyze_signal(data)
    return {"ok": True, "analysis": result}


def analyze_signal(data: TradingViewSignal) -> dict[str, Any]:
    buy = 0.0
    sell = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    if (data.trend or "").upper() == "ALTA":
        buy += 2
        reasons.append("Tendência de curto prazo favorável à alta.")
    elif (data.trend or "").upper() == "BAIXA":
        sell += 2
        reasons.append("Tendência de curto prazo favorável à baixa.")
    if data.ema9 is not None and data.ema21 is not None:
        if data.ema9 > data.ema21:
            buy += 1.5
        elif data.ema9 < data.ema21:
            sell += 1.5
    if data.macd is not None and data.macdSignal is not None:
        if data.macd > data.macdSignal:
            buy += 1.5
        elif data.macd < data.macdSignal:
            sell += 1.5
    if data.momentum is not None:
        if data.momentum > 0:
            buy += 1
        elif data.momentum < 0:
            sell += 1
    if data.support:
        buy += 1
        reasons.append("Suporte detectado.")
    if data.resistance:
        sell += 1
        reasons.append("Resistência detectada.")
    if data.breakoutUp:
        buy += 1.5
    if data.breakoutDown:
        sell += 1.5
    base = buy + sell
    dominance = abs(buy - sell) / base if base else 0
    score = round(min(100, 45 + dominance * 55)) if base else 0
    signal = "AGUARDAR" if dominance < 0.22 or score < 60 else ("CALL" if buy > sell else "PUT")
    quality = "MUITO FORTE" if score >= 82 else "FORTE" if score >= 72 else "MODERADA" if score >= 60 else "SEM CONFLUÊNCIA"
    result = {
        "signal": signal, "score": score, "quality": quality,
        "buyScore": round(buy, 2), "sellScore": round(sell, 2),
        "symbol": data.symbol or "—", "timeframe": data.timeframe or "—",
        "price": data.price, "timestamp": data.timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reasons": reasons[:8], "warnings": warnings[:6], "source": "TradingView webhook",
        "raw": data.model_dump(),
    }
    SIGNALS.appendleft(result)
    return result


@router.get("/latest")
def latest_signal() -> dict[str, Any]:
    return {"ok": True, "signal": SIGNALS[0] if SIGNALS else None}


@router.get("/history")
def signal_history(limit: int = 30) -> dict[str, Any]:
    limit = max(1, min(int(limit or 30), 200))
    return {"ok": True, "signals": list(SIGNALS)[:limit]}
