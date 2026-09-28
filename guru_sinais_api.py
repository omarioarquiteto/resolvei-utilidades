from __future__ import annotations

import os
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/guru-sinais", tags=["GURÚ DOS SINAIS"])

WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
SIGNALS = deque(maxlen=200)


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


def _num(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def analyze_signal(data: TradingViewSignal) -> dict[str, Any]:
    buy = 0.0
    sell = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    trend = (data.trend or "").upper()
    rsi = _num(data.rsi)
    macd = _num(data.macd)
    macd_signal = _num(data.macdSignal)
    ema9 = _num(data.ema9)
    ema21 = _num(data.ema21)
    ema50 = _num(data.ema50)
    bb = _num(data.bbPosition)
    momentum = _num(data.momentum)
    volume_ratio = _num(data.volumeRatio)

    if trend == "ALTA":
        buy += 2
        reasons.append("Tendência de curto prazo favorável à alta.")
    elif trend == "BAIXA":
        sell += 2
        reasons.append("Tendência de curto prazo favorável à baixa.")
    else:
        warnings.append("Tendência sem direção clara.")

    if ema9 is not None and ema21 is not None:
        if ema9 > ema21:
            buy += 1.5
            reasons.append("EMA 9 acima da EMA 21.")
        elif ema9 < ema21:
            sell += 1.5
            reasons.append("EMA 9 abaixo da EMA 21.")

    if ema21 is not None and ema50 is not None:
        if ema21 > ema50:
            buy += 1
            reasons.append("EMA 21 acima da EMA 50.")
        elif ema21 < ema50:
            sell += 1
            reasons.append("EMA 21 abaixo da EMA 50.")

    if rsi is not None:
        if 50 < rsi < 70:
            buy += 1
            reasons.append(f"RSI em {rsi:.1f}, favorecendo momentum comprador sem sobrecompra extrema.")
        elif 30 < rsi < 50:
            sell += 1
            reasons.append(f"RSI em {rsi:.1f}, mostrando pressão vendedora moderada.")
        elif rsi >= 70:
            warnings.append(f"RSI em {rsi:.1f}: atenção à sobrecompra.")
        elif rsi <= 30:
            warnings.append(f"RSI em {rsi:.1f}: atenção à sobrevenda.")

    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            buy += 1.5
            reasons.append("MACD acima da linha de sinal.")
        elif macd < macd_signal:
            sell += 1.5
            reasons.append("MACD abaixo da linha de sinal.")

    if momentum is not None:
        if momentum > 0:
            buy += 1
            reasons.append("Momentum positivo.")
        elif momentum < 0:
            sell += 1
            reasons.append("Momentum negativo.")

    if bb is not None:
        if bb < 0.2:
            buy += 1
            reasons.append("Preço próximo da banda inferior de Bollinger.")
        elif bb > 0.8:
            sell += 1
            reasons.append("Preço próximo da banda superior de Bollinger.")

    if data.support:
        buy += 1.5
        reasons.append("Preço identificado próximo de suporte.")
    if data.resistance:
        sell += 1.5
        reasons.append("Preço identificado próximo de resistência.")

    if data.breakoutUp:
        buy += 1.5
        reasons.append("Rompimento de resistência detectado.")
    if data.breakoutDown:
        sell += 1.5
        reasons.append("Rompimento de suporte detectado.")

    pattern = (data.candlePattern or "").lower()
    if any(x in pattern for x in ("bull", "alta", "engolfo de alta", "hammer", "martelo")):
        buy += 1
        reasons.append("Padrão de candle com viés comprador.")
    elif any(x in pattern for x in ("bear", "baixa", "engolfo de baixa", "shooting", "estrela cadente")):
        sell += 1
        reasons.append("Padrão de candle com viés vendedor.")

    if volume_ratio is not None and volume_ratio >= 1.2:
        reasons.append("Volume acima da média, reforçando a relevância do movimento.")
    elif volume_ratio is not None and volume_ratio < 0.8:
        warnings.append("Volume abaixo da média: confirmação mais fraca.")

    total = buy + sell
    if total <= 0:
        signal = "AGUARDAR"
        score = 0
    else:
        dominance = abs(buy - sell) / total
        score = min(100, round(40 + dominance * 60))
        if dominance < 0.18:
            signal = "AGUARDAR"
            score = min(score, 59)
            warnings.append("Indicadores estão divididos; falta confluência.")
        elif buy > sell:
            signal = "CALL"
        else:
            signal = "PUT"

    if len(warnings) == 0 and score >= 75:
        quality = "FORTE"
    elif score >= 60:
        quality = "MODERADA"
    else:
        quality = "FRACA"

    return {
        "signal": signal,
        "score": score,
        "quality": quality,
        "buyScore": round(buy, 2),
        "sellScore": round(sell, 2),
        "symbol": data.symbol or "—",
        "timeframe": data.timeframe or "—",
        "price": data.price,
        "timestamp": data.timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reasons": reasons[:10],
        "warnings": warnings[:8],
        "source": data.source,
        "raw": data.model_dump(),
    }


@router.post("/webhook")
def receive_webhook(data: TradingViewSignal) -> dict[str, Any]:
    if WEBHOOK_SECRET and data.secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Webhook não autorizado.")
    result = analyze_signal(data)
    SIGNALS.appendleft(result)
    return {"ok": True, "analysis": result}


@router.post("/analyze")
def analyze_manual(data: TradingViewSignal) -> dict[str, Any]:
    result = analyze_signal(data)
    SIGNALS.appendleft(result)
    return {"ok": True, "analysis": result}


@router.get("/latest")
def latest_signal() -> dict[str, Any]:
    return {"ok": True, "signal": SIGNALS[0] if SIGNALS else None}


@router.get("/history")
def signal_history(limit: int = 30) -> dict[str, Any]:
    limit = max(1, min(int(limit or 30), 200))
    return {"ok": True, "signals": list(SIGNALS)[:limit]}
