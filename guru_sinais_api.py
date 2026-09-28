from __future__ import annotations

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


def fetch_candles(symbol: str, timeframe: str, outputsize: int = 250) -> list[dict[str, float]]:
    if not TWELVE_DATA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="O motor automático ainda não está configurado. Adicione TWELVE_DATA_API_KEY nas variáveis do Render."
        )
    interval = INTERVALS.get(timeframe)
    if not interval:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")
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
        r.raise_for_status()
        data = r.json()
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
            })
        except (TypeError, ValueError, KeyError):
            continue
    if len(rows) < 60:
        raise HTTPException(status_code=502, detail="Não foram recebidos candles suficientes para uma análise técnica confiável.")
    return rows


def analyze_market(symbol: str, timeframe: str) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    rows = fetch_candles(symbol, timeframe)
    context_map = {"1m": ["5m", "15m"], "5m": ["15m", "30m"], "15m": ["30m", "1h"], "30m": ["1h"], "1h": ["4h"]}
    context_rows = [(tf, fetch_candles(symbol, tf, 180)) for tf in context_map.get(timeframe, [])]
    closes = [x["close"] for x in rows]
    volumes = [x["volume"] for x in rows]

    e9, e21, e50 = ema(closes, 9)[-1], ema(closes, 21)[-1], ema(closes, 50)[-1]
    r = rsi(closes)
    m, ms = macd_values(closes)
    bb = bollinger_position(closes)
    momentum = closes[-1] - closes[-6]
    volume_avg = sum(volumes[-20:]) / max(1, len(volumes[-20:]))
    vr = volumes[-1] / volume_avg if volume_avg else None

    high20 = max(x["high"] for x in rows[-20:])
    low20 = min(x["low"] for x in rows[-20:])
    price = closes[-1]
    range20 = max(high20 - low20, price * 1e-8)
    near_support = (price - low20) / range20 < 0.16
    near_resistance = (high20 - price) / range20 < 0.16
    breakout_up = price > max(x["high"] for x in rows[-21:-1])
    breakout_down = price < min(x["low"] for x in rows[-21:-1])

    trend = "ALTA" if e9 > e21 > e50 else "BAIXA" if e9 < e21 < e50 else "NEUTRA"
    pattern = candle_pattern(rows)

    buy = sell = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    if trend == "ALTA":
        buy += 2.5
        reasons.append("Estrutura de médias alinhada para alta.")
    elif trend == "BAIXA":
        sell += 2.5
        reasons.append("Estrutura de médias alinhada para baixa.")
    else:
        warnings.append("As médias não estão em alinhamento direcional.")

    context_trends = []
    for ctx_tf, ctx in context_rows:
        cc = [x["close"] for x in ctx]
        c9, c21, c50 = ema(cc, 9)[-1], ema(cc, 21)[-1], ema(cc, 50)[-1]
        ctx_trend = "ALTA" if c9 > c21 > c50 else "BAIXA" if c9 < c21 < c50 else "NEUTRA"
        context_trends.append((ctx_tf, ctx_trend))
    aligned_up = sum(1 for _, t in context_trends if t == "ALTA")
    aligned_down = sum(1 for _, t in context_trends if t == "BAIXA")
    if trend == "ALTA" and aligned_up:
        buy += 1.5 + 0.5 * max(0, aligned_up - 1)
        reasons.append("Timeframes superiores confirmam a tendência de alta.")
    elif trend == "BAIXA" and aligned_down:
        sell += 1.5 + 0.5 * max(0, aligned_down - 1)
        reasons.append("Timeframes superiores confirmam a tendência de baixa.")
    elif trend != "NEUTRA" and (aligned_up or aligned_down):
        warnings.append("Há divergência entre o timeframe de entrada e o contexto superior.")

    if e9 > e21:
        buy += 1.5
    elif e9 < e21:
        sell += 1.5

    if e21 > e50:
        buy += 1.0
    elif e21 < e50:
        sell += 1.0

    if m > ms:
        buy += 1.5
        reasons.append("MACD acima da linha de sinal.")
    elif m < ms:
        sell += 1.5
        reasons.append("MACD abaixo da linha de sinal.")

    if 50 < r < 68:
        buy += 1.0
        reasons.append(f"RSI em {r:.1f}, com momentum comprador sem extremo.")
    elif 32 < r < 50:
        sell += 1.0
        reasons.append(f"RSI em {r:.1f}, com pressão vendedora moderada.")
    elif r >= 68:
        warnings.append(f"RSI em {r:.1f}: região já aquecida para compra.")
    elif r <= 32:
        warnings.append(f"RSI em {r:.1f}: região já pressionada para venda.")

    if momentum > 0:
        buy += 1.0
        reasons.append("Momentum recente positivo.")
    elif momentum < 0:
        sell += 1.0
        reasons.append("Momentum recente negativo.")

    if near_support:
        buy += 1.2
        reasons.append("Preço próximo da mínima recente/suporte.")
    if near_resistance:
        sell += 1.2
        reasons.append("Preço próximo da máxima recente/resistência.")

    if breakout_up:
        buy += 1.8
        reasons.append("Rompimento de máxima recente.")
    if breakout_down:
        sell += 1.8
        reasons.append("Rompimento de mínima recente.")

    if "alta" in pattern or pattern == "bullish":
        buy += 0.8
        reasons.append("Candle atual com comportamento comprador.")
    elif "baixa" in pattern or pattern == "bearish":
        sell += 0.8
        reasons.append("Candle atual com comportamento vendedor.")

    if bb < 0.15:
        buy += 0.6
        reasons.append("Preço em região inferior das bandas de Bollinger.")
    elif bb > 0.85:
        sell += 0.6
        reasons.append("Preço em região superior das bandas de Bollinger.")

    if vr is not None:
        if vr >= 1.2:
            reasons.append("Volume acima da média.")
        elif vr < 0.8:
            warnings.append("Volume abaixo da média.")

    base = buy + sell
    score = round(min(100.0, 45.0 + (abs(buy - sell) / base * 55.0))) if base else 0
    dominance = abs(buy - sell) / base if base else 0

    if dominance < 0.22 or score < 60:
        signal = "AGUARDAR"
    elif buy > sell:
        signal = "CALL"
    else:
        signal = "PUT"

    if signal != "AGUARDAR":
        quality = "MUITO FORTE" if score >= 82 else "FORTE" if score >= 72 else "MODERADA"
    else:
        quality = "SEM CONFLUÊNCIA"

    result = {
        "signal": signal,
        "score": score,
        "quality": quality,
        "symbol": symbol,
        "timeframe": timeframe,
        "price": price,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "buyScore": round(buy, 2),
        "sellScore": round(sell, 2),
        "reasons": reasons[:8],
        "warnings": warnings[:6],
        "indicators": {
            "trend": trend,
            "rsi": round(r, 2),
            "macd": round(m, 8),
            "macdSignal": round(ms, 8),
            "ema9": e9,
            "ema21": e21,
            "ema50": e50,
            "bbPosition": round(bb, 4),
            "momentum": momentum,
            "volumeRatio": round(vr, 3) if vr is not None else None,
            "candlePattern": pattern,
            "support": near_support,
            "resistance": near_resistance,
            "breakoutUp": breakout_up,
            "breakoutDown": breakout_down,
            "atrPct": round(atr_pct(rows) * 100, 3),
            "context": {tf: t for tf, t in context_trends},
        },
        "source": "Twelve Data",
    }
    SIGNALS.appendleft(result)
    return result


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
