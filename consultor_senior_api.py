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
