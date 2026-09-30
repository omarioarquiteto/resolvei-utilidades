from __future__ import annotations

import json
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
    for i in range(period - 1, len(rows)):
        w = rows[i - period + 1:i + 1]
        hi, lo = max(x["high"] for x in w), min(x["low"] for x in w)
        ks.append(50.0 if hi == lo else 100 * (rows[i]["close"] - lo) / (hi - lo))
    k = ks[-1]
    d = sum(ks[-smooth:]) / min(smooth, len(ks))
    return k, d


def _cci(rows: list[dict[str, float]], period: int = 20) -> float:
    tp = [(x["high"] + x["low"] + x["close"]) / 3 for x in rows]
    w = tp[-period:]
    mean = sum(w) / len(w)
    dev = sum(abs(x - mean) for x in w) / len(w)
    return 0.0 if dev == 0 else (tp[-1] - mean) / (0.015 * dev)


def _williams_r(rows: list[dict[str, float]], period: int = 14) -> float:
    w = rows[-period:]
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
        if tp > ptp: pos += flow
        elif tp < ptp: neg += flow
    if neg == 0: return 100.0 if pos else 50.0
    ratio = pos / neg
    return 100 - 100 / (1 + ratio)


def _roc(values: list[float], period: int = 5) -> float:
    if len(values) <= period or values[-period - 1] == 0:
        return 0.0
    return (values[-1] / values[-period - 1] - 1) * 100


def _obv_slope(rows: list[dict[str, float]], period: int = 10) -> float:
    if len(rows) < 2: return 0.0
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
    return pv / vol if vol > 0 else _last_sma([x["close"] for x in w], len(w))


def _supertrend(rows: list[dict[str, float]], period: int = 10, multiplier: float = 3.0) -> tuple[str, float]:
    atr = _atr_value(rows, period)
    if atr <= 0: return "NEUTRA", 0.0
    close = rows[-1]["close"]
    baseline = _last_sma([x["close"] for x in rows], period)
    return ("ALTA" if close >= baseline else "BAIXA"), baseline


def _ichimoku(rows: list[dict[str, float]]) -> tuple[float, float, str]:
    if len(rows) < 52: return rows[-1]["close"], rows[-1]["close"], "NEUTRA"
    def mid(n):
        w = rows[-n:]
        return (max(x["high"] for x in w) + min(x["low"] for x in w)) / 2
    tenkan, kijun = mid(9), mid(26)
    span_a, span_b = (tenkan + kijun) / 2, mid(52)
    top, bottom = max(span_a, span_b), min(span_a, span_b)
    close = rows[-1]["close"]
    trend = "ALTA" if close > top and tenkan > kijun else "BAIXA" if close < bottom and tenkan < kijun else "NEUTRA"
    return top, bottom, trend


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
    atr_pct = atr / closes[-1] * 100 if closes[-1] else 0.0
    atr_prev = _atr_value(rows[:-10], 14) if len(rows) > 30 else atr
    adx, di_diff = _adx(rows)
    st_k, st_d = _stochastic(rows)
    cci, willr, mfi = _cci(rows), _williams_r(rows), _mfi(rows)
    roc, vwap = _roc(closes), _vwap(rows)
    vr = rows[-1].get("volume", 0.0) / max(_last_sma([x.get("volume", 0.0) for x in rows], 20), 1e-12)
    obv = _obv_slope(rows)
    bb_mid, bb_sd = _last_sma(closes, 20), _std(closes, 20)
    bb_upper, bb_lower = bb_mid + 2 * bb_sd, bb_mid - 2 * bb_sd
    bb_pos = 0.5 if bb_upper == bb_lower else max(0.0, min(1.0, (closes[-1] - bb_lower) / (bb_upper - bb_lower)))
    bb_width = (bb_upper - bb_lower) / closes[-1] * 100 if closes[-1] else 0.0
    prev_closes = closes[:-10]
    prev_mid, prev_sd = _last_sma(prev_closes, 20), _std(prev_closes, 20)
    bb_width_prev = (4 * prev_sd / closes[-11] * 100) if len(closes) > 40 and closes[-11] else bb_width
    high20, low20 = max(x["high"] for x in rows[-20:]), min(x["low"] for x in rows[-20:])
    prev_high20, prev_low20 = max(x["high"] for x in rows[-21:-1]), min(x["low"] for x in rows[-21:-1])
    donchian_up, donchian_down = closes[-1] > prev_high20, closes[-1] < prev_low20
    span = max(high20 - low20, closes[-1] * 1e-8)
    near_support, near_resistance = (closes[-1] - low20) / span < .16, (high20 - closes[-1]) / span < .16
    st_trend, _ = _supertrend(rows)
    _, _, ichi = _ichimoku(rows)
    candle = candle_pattern(rows)
    structure = "CALL" if closes[-1] > closes[-3] > closes[-6] else "PUT" if closes[-1] < closes[-3] < closes[-6] else "NEUTRA"
    volume_dir = "CALL" if vr >= 1.15 and closes[-1] >= closes[-2] else "PUT" if vr >= 1.15 and closes[-1] < closes[-2] else "NEUTRA"

    if strategy == "tendencia":
        items = [
            ("EMA 9/21/50/200",1.4,"CALL" if e9>e21>e50>e200 else "PUT" if e9<e21<e50<e200 else "NEUTRA"),
            ("ADX + DI",1.2,"CALL" if adx>=20 and di_diff>0 else "PUT" if adx>=20 and di_diff<0 else "NEUTRA"),
            ("MACD",1.1,"CALL" if hist>0 else "PUT" if hist<0 else "NEUTRA"),
            ("RSI regime",.9,"CALL" if 52<=r<=68 else "PUT" if 32<=r<=48 else "NEUTRA"),
            ("Supertrend",1.1,"CALL" if st_trend=="ALTA" else "PUT" if st_trend=="BAIXA" else "NEUTRA"),
            ("Ichimoku",1.0,"CALL" if ichi=="ALTA" else "PUT" if ichi=="BAIXA" else "NEUTRA"),
            ("VWAP",.8,"CALL" if closes[-1]>vwap else "PUT" if closes[-1]<vwap else "NEUTRA"),
            ("Donchian",.8,"CALL" if donchian_up else "PUT" if donchian_down else "NEUTRA"),
            ("ROC",.7,"CALL" if roc>.03 else "PUT" if roc<-.03 else "NEUTRA"),
            ("OBV",.7,"CALL" if obv>.02 else "PUT" if obv<-.02 else "NEUTRA"),
            ("Volume",.6,volume_dir),("Price structure",.7,structure)
        ]
    elif strategy == "reversao":
        items = [
            ("Bollinger position",1.2,"CALL" if bb_pos<=.12 else "PUT" if bb_pos>=.88 else "NEUTRA"),
            ("RSI extreme",1.1,"CALL" if r<=30 else "PUT" if r>=70 else "NEUTRA"),
            ("Stochastic",1.0,"CALL" if st_k<=20 and st_k>=st_d else "PUT" if st_k>=80 and st_k<=st_d else "NEUTRA"),
            ("CCI",.9,"CALL" if cci<=-100 else "PUT" if cci>=100 else "NEUTRA"),
            ("Williams %R",.8,"CALL" if willr<=-80 else "PUT" if willr>=-20 else "NEUTRA"),
            ("MFI",.8,"CALL" if mfi<=20 else "PUT" if mfi>=80 else "NEUTRA"),
            ("VWAP distance",.8,"CALL" if closes[-1]<vwap*.9995 else "PUT" if closes[-1]>vwap*1.0005 else "NEUTRA"),
            ("Support/resistance",1.0,"CALL" if near_support else "PUT" if near_resistance else "NEUTRA"),
            ("Candle reversal",.8,"CALL" if "alta" in candle or candle=="bullish" else "PUT" if "baixa" in candle or candle=="bearish" else "NEUTRA"),
            ("ATR regime",.6,"CALL" if atr_pct>=.02 and closes[-1]<vwap else "PUT" if atr_pct>=.02 and closes[-1]>vwap else "NEUTRA"),
            ("ADX range filter",.6,"CALL" if adx<18 and bb_pos<.2 else "PUT" if adx<18 and bb_pos>.8 else "NEUTRA"),
            ("Volume confirmation",.5,volume_dir)
        ]
    else:
        items = [
            ("Donchian breakout",1.4,"CALL" if donchian_up else "PUT" if donchian_down else "NEUTRA"),
            ("Bollinger expansion",1.0,"CALL" if bb_width>bb_width_prev and closes[-1]>bb_mid else "PUT" if bb_width>bb_width_prev and closes[-1]<bb_mid else "NEUTRA"),
            ("ATR expansion",.9,"CALL" if atr>atr_prev and closes[-1]>closes[-2] else "PUT" if atr>atr_prev and closes[-1]<closes[-2] else "NEUTRA"),
            ("ADX + DI",1.1,"CALL" if adx>=22 and di_diff>0 else "PUT" if adx>=22 and di_diff<0 else "NEUTRA"),
            ("MACD histogram",1.0,"CALL" if hist>0 else "PUT" if hist<0 else "NEUTRA"),
            ("EMA alignment",1.0,"CALL" if e9>e21>e50 else "PUT" if e9<e21<e50 else "NEUTRA"),
            ("ROC",.8,"CALL" if roc>.05 else "PUT" if roc<-.05 else "NEUTRA"),
            ("Volume expansion",.9,volume_dir),("OBV",.8,"CALL" if obv>.02 else "PUT" if obv<-.02 else "NEUTRA"),
            ("VWAP",.7,"CALL" if closes[-1]>vwap else "PUT" if closes[-1]<vwap else "NEUTRA"),
            ("Candle confirmation",.7,"CALL" if candle in {"bullish","engolfo de alta"} else "PUT" if candle in {"bearish","engolfo de baixa"} else "NEUTRA"),
            ("Price structure",.7,structure)
        ]

    buy, sell, confidence = _score_signal(items)
    direction = "CALL" if buy > sell else "PUT" if sell > buy else "NEUTRA"
    return {
        "strategy": strategy,
        "strategyLabel": {"tendencia":"Tendência + confluência","reversao":"Reversão à média","rompimento":"Rompimento + momentum"}[strategy],
        "buy": round(buy,2), "sell": round(sell,2), "confidence": round(confidence,1), "direction": direction,
        "indicators": [{"name":n,"weight":w,"signal":d} for n,w,d in items],
        "values": {
            "EMA9":e9,"EMA21":e21,"EMA50":e50,"EMA200":e200,"RSI":r,"MACD":macd,"MACDSignal":macd_signal,
            "MACDHistogram":hist,"BollingerPosition":bb_pos,"BollingerWidthPct":bb_width,"ATRpct":atr_pct,
            "ADX":adx,"DIplusMinus":di_diff,"StochasticK":st_k,"StochasticD":st_d,"CCI":cci,"WilliamsR":willr,
            "MFI":mfi,"ROC":roc,"VWAP":vwap,"VolumeRatio":vr,"OBVSlope":obv,"DonchianUp":donchian_up,
            "DonchianDown":donchian_down,"Supertrend":st_trend,"Ichimoku":ichi,"Support":near_support,
            "Resistance":near_resistance,"Candle":candle,"PriceStructure":structure
        }
    }


def _gemini_review(symbol: str, timeframe: str, selected_strategy: str, strategies: list[dict[str, Any]], price: float, rows: list[dict[str, float]], authorization: str | None = None) -> dict[str, Any]:
    api_key = GEMINI_API_KEY
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
    if authorization:
        try:
            from server import _resolve_ai_credentials
            _, api_key, stored_model = _resolve_ai_credentials(authorization, "gemini")
            model = stored_model or model
        except Exception:
            if not api_key: raise
    if not api_key:
        return {"available":False,"reason":"Gemini não configurado."}
    selected = next((x for x in strategies if x["strategy"] == selected_strategy), strategies[0])
    compact = [{"strategy":x["strategyLabel"],"direction":x["direction"],"confidence":x["confidence"],"indicators":x["indicators"]} for x in strategies]
    recent = [{"o":round(x["open"],6),"h":round(x["high"],6),"l":round(x["low"],6),"c":round(x["close"],6)} for x in rows[-12:]]
    prompt = (
        "Valide um estudo técnico de opções binárias de curtíssimo prazo. Não invente dados. "
        "Use apenas os indicadores, confluências e candles fornecidos. Cada estratégia tem 12 indicadores. "
        "Compare famílias diferentes e penalize contradições. Responda SOMENTE JSON: "
        "{\"signal\":\"CALL|PUT|AGUARDAR\",\"confidence\":0-100,\"reason\":\"texto curto\",\"risk\":\"baixo|medio|alto\"}. "
        f"Par={symbol}; timeframe={timeframe}; preço={price}; estratégia={selected_strategy}. "
        f"Estratégias={json.dumps(compact,ensure_ascii=False,separators=(',',':'))}. "
        f"Valores da estratégia selecionada={json.dumps(selected['values'],ensure_ascii=False,separators=(',',':'))}. "
        f"Candles={json.dumps(recent,separators=(',',':'))}. "
        "Só use CALL/PUT quando houver confluência clara; caso contrário AGUARDAR."
    )
    try:
        url="https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent"
        payload={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseMimeType":"application/json","temperature":0.1,"maxOutputTokens":180}}
        resp=requests.post(url,headers={"x-goog-api-key":api_key,"Content-Type":"application/json"},json=payload,timeout=3.5)
        if not resp.ok: return {"available":False,"reason":f"Gemini HTTP {resp.status_code}"}
        parsed=json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
        return {"available":True,"signal":parsed.get("signal","AGUARDAR"),"confidence":float(parsed.get("confidence",0)),"reason":str(parsed.get("reason",""))[:300],"risk":str(parsed.get("risk","alto")),"model":model}
    except Exception as exc:
        return {"available":False,"reason":str(exc)[:220]}



def _mtf_plan(timeframe: str) -> tuple[str, str, str]:
    # Contexto = TF maior, setup = TF escolhido, gatilho = TF menor.
    plans = {
        "1m": ("15m", "5m", "1m"),
        "5m": ("15m", "5m", "1m"),
        "15m": ("1h", "15m", "5m"),
        "30m": ("4h", "30m", "15m"),
        "1h": ("4h", "1h", "15m"),
    }
    return plans.get(timeframe, ("15m", timeframe, "5m"))


def _mtf_rows(symbol: str, timeframe: str) -> tuple[dict[str, list[dict[str, float]]], tuple[str, str, str]]:
    context_tf, setup_tf, trigger_tf = _mtf_plan(timeframe)
    base_tf = min((context_tf, setup_tf, trigger_tf), key=timeframe_minutes)

    # Uma chamada é suficiente quando o TF escolhido é a menor granularidade:
    # os TFs maiores são agregados localmente, reduzindo latência e consumo da API.
    base_rows = fetch_candles(symbol, base_tf, 1000)
    rows: dict[str, list[dict[str, float]]] = {base_tf: base_rows}

    for tf in {context_tf, setup_tf, trigger_tf}:
        if tf in rows:
            continue
        rows[tf] = resample_rows(
            base_rows,
            timeframe_minutes(base_tf),
            timeframe_minutes(tf),
        )

    # Para 15m/30m/1h, o gatilho é menor que o TF escolhido.
    # Nesse caso buscamos somente esse TF menor e mantemos o contexto/setup
    # derivados do mesmo conjunto temporal quando possível.
    if not rows.get(trigger_tf) or len(rows[trigger_tf]) < 60:
        trigger_rows = fetch_candles(symbol, trigger_tf, 1000)
        rows[trigger_tf] = trigger_rows
        if setup_tf == timeframe:
            rows[setup_tf] = fetch_candles(symbol, setup_tf, 1000)
        else:
            rows[setup_tf] = resample_rows(
                trigger_rows,
                timeframe_minutes(trigger_tf),
                timeframe_minutes(setup_tf),
            )
        if len(rows.get(context_tf, [])) < 60:
            rows[context_tf] = resample_rows(
                rows[setup_tf],
                timeframe_minutes(setup_tf),
                timeframe_minutes(context_tf),
            )

    return rows, (context_tf, setup_tf, trigger_tf)


def _mtf_score(context: dict[str, Any], setup: dict[str, Any], trigger: dict[str, Any]) -> tuple[str, float, list[str]]:
    # O TF maior filtra a direção; o escolhido confirma o setup; o menor
    # apenas temporiza a entrada. Não fazemos "votação" simples dos indicadores.
    c, s, t = context["direction"], setup["direction"], trigger["direction"]
    score = float(setup["confidence"])
    notes: list[str] = []

    if c == s and c in {"CALL", "PUT"}:
        score += 12
        notes.append(f"Contexto {context['strategyLabel']} confirma {c}.")
    elif c in {"CALL", "PUT"} and s in {"CALL", "PUT"} and c != s:
        score -= 14
        notes.append("O timeframe de contexto diverge do setup.")
    else:
        score -= 4

    if t == s and t in {"CALL", "PUT"}:
        score += 8
        notes.append(f"Gatilho {trigger['strategyLabel']} acompanha {t}.")
    elif t in {"CALL", "PUT"} and s in {"CALL", "PUT"} and t != s:
        score -= 10
        notes.append("O timeframe de gatilho ainda não confirma o setup.")
    else:
        score -= 3

    score = max(0.0, min(99.0, score))
    signal = s if s in {"CALL", "PUT"} and score >= 65 else "AGUARDAR"
    return signal, round(score, 1), notes

def analyze_market(symbol: str, timeframe: str, strategy: str = "automatica", authorization: str | None = None) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    if timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")

    mtf, plan = _mtf_rows(symbol, timeframe)
    context_tf, setup_tf, trigger_tf = plan
    setup_rows = mtf[setup_tf]
    if len(setup_rows) < 60 or len(mtf[context_tf]) < 60 or len(mtf[trigger_tf]) < 60:
        raise HTTPException(status_code=502, detail="Não foram recebidos candles suficientes para a análise em múltiplos timeframes.")

    # Cada timeframe usa a mesma família de estratégia, evitando misturar
    # indicadores incompatíveis. O contexto filtra, o setup decide e o gatilho temporiza.
    context_strategies = [_strategy_pack(mtf[context_tf], s) for s in ("tendencia", "reversao", "rompimento")]
    setup_strategies = [_strategy_pack(setup_rows, s) for s in ("tendencia", "reversao", "rompimento")]
    trigger_strategies = [_strategy_pack(mtf[trigger_tf], s) for s in ("tendencia", "reversao", "rompimento")]

    if strategy == "automatica":
        candidates = []
        for s in setup_strategies:
            c = next(x for x in context_strategies if x["strategy"] == s["strategy"])
            t = next(x for x in trigger_strategies if x["strategy"] == s["strategy"])
            sig, sc, _ = _mtf_score(c, s, t)
            candidates.append((sc if sig != "AGUARDAR" else 0, s))
        selected = max(candidates, key=lambda x: x[0])[1]
    else:
        selected = next((x for x in setup_strategies if x["strategy"] == strategy), None)
        if not selected:
            raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    ctx = next(x for x in context_strategies if x["strategy"] == selected["strategy"])
    trg = next(x for x in trigger_strategies if x["strategy"] == selected["strategy"])
    mtf_signal, mtf_score, mtf_notes = _mtf_score(ctx, selected, trg)

    # Gemini recebe somente o resumo MTF + candles do setup/gatilho para continuar rápido.
    gemini = _gemini_review(
        symbol,
        f"{context_tf} → {setup_tf} → {trigger_tf}",
        selected["strategy"],
        setup_strategies,
        setup_rows[-1]["close"],
        setup_rows,
        authorization,
    )

    gem_signal = gemini.get("signal") if gemini.get("available") else None
    gem_conf = float(gemini.get("confidence", 0)) if gem_signal else 0.0
    base_signal = mtf_signal
    base_conf = mtf_score

    if base_signal in {"CALL", "PUT"} and gem_signal == base_signal:
        signal = base_signal
        score = round(min(99.0, .72 * base_conf + .28 * gem_conf))
        quality = "MUITO FORTE" if score >= 82 else "FORTE" if score >= 72 else "MODERADA"
    elif base_signal in {"CALL", "PUT"} and gem_signal in {"CALL", "PUT"}:
        signal = base_signal
        score = round(max(50.0, min(90.0, .82 * base_conf + .18 * gem_conf - 8)))
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
        warnings.append("O gatilho de entrada ainda diverge do setup.")
    if gemini.get("available") and gem_signal in {"CALL", "PUT"} and gem_signal != base_signal:
        warnings.append("O Gemini divergiu da leitura técnica em múltiplos timeframes.")
    if gemini.get("available") and gemini.get("risk") == "alto":
        warnings.append("O Gemini classificou o contexto como risco alto.")
    if signal == "AGUARDAR":
        warnings.append("Sem alinhamento suficiente entre contexto, setup e gatilho.")

    result = {
        "signal": signal,
        "score": score,
        "quality": quality,
        "symbol": symbol,
        "timeframe": timeframe,
        "analysisTimeframes": {"context": context_tf, "setup": setup_tf, "trigger": trigger_tf},
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
            "context": {"timeframe": context_tf, "direction": ctx["direction"], "confidence": ctx["confidence"]},
            "setup": {"timeframe": setup_tf, "direction": selected["direction"], "confidence": selected["confidence"]},
            "trigger": {"timeframe": trigger_tf, "direction": trg["direction"], "confidence": trg["confidence"]},
            "score": mtf_score,
            "notes": mtf_notes,
        },
        "gemini": gemini,
        "indicators": selected["values"],
        "source": "Twelve Data + motor técnico MTF + Gemini",
    }
    SIGNALS.appendleft(result)
    return result


@router.post("/market-analysis")
def market_analysis(req: MarketAnalysisRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return {"ok": True, "analysis": analyze_market(req.symbol, req.timeframe, req.strategy, authorization)}

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
