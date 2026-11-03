"""Motor quantitativo somente-leitura do VIBE LUCRO.

Recebe candles já normalizados pela IQ Option e calcula confluência multi-timeframe.
Não envia ordens, não acessa carteira e não tenta automatizar operações.
"""
from __future__ import annotations

from math import isfinite, sqrt
from statistics import mean
from typing import Any

TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900}
MIN_CANDLES = 60
MAX_CANDLE_AGE_SECONDS = {"1m": 150, "5m": 420, "15m": 1080}


def _clean_rows(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    clean: dict[int, dict[str, float]] = {}
    for raw in rows:
        try:
            item = {
                "open": float(raw["open"]),
                "high": float(raw["high"]),
                "low": float(raw["low"]),
                "close": float(raw["close"]),
                "volume": float(raw.get("volume") or 0),
                "time": float(raw.get("datetime", raw.get("time", 0)) or 0),
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        values = list(item.values())
        if not all(isfinite(value) for value in values):
            continue
        if item["time"] <= 0 or item["high"] < item["low"]:
            continue
        if item["high"] < max(item["open"], item["close"]):
            continue
        if item["low"] > min(item["open"], item["close"]):
            continue
        clean[int(item["time"])] = item
    return [clean[key] for key in sorted(clean)]


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    current = mean(values[:period])
    multiplier = 2.0 / (period + 1.0)
    for value in values[period:]:
        current = value * multiplier + current * (1.0 - multiplier)
    return current


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes[-period:]]
    losses = [max(-change, 0.0) for change in changes[-period:]]
    average_gain = mean(gains)
    average_loss = mean(losses)
    if average_loss <= 1e-15:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _macd_histogram(values: list[float]) -> float | None:
    if len(values) < 35:
        return None
    macd_line: list[float] = []
    for index in range(26, len(values) + 1):
        sample = values[:index]
        fast = _ema(sample, 12)
        slow = _ema(sample, 26)
        if fast is None or slow is None:
            continue
        macd_line.append(fast - slow)
    signal = _ema(macd_line, 9)
    if signal is None or not macd_line:
        return None
    return macd_line[-1] - signal


def _atr(rows: list[dict[str, float]], period: int = 14) -> float | None:
    if len(rows) <= period:
        return None
    ranges: list[float] = []
    previous_close = rows[-period - 1]["close"]
    for row in rows[-period:]:
        ranges.append(
            max(
                row["high"] - row["low"],
                abs(row["high"] - previous_close),
                abs(row["low"] - previous_close),
            )
        )
        previous_close = row["close"]
    return mean(ranges)


def _features(rows: list[dict[str, float]], timeframe: str, now: float) -> dict[str, Any]:
    if len(rows) < MIN_CANDLES:
        raise ValueError(f"São necessários pelo menos {MIN_CANDLES} candles em {timeframe}.")
    closes = [row["close"] for row in rows]
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50)
    previous_ema9 = _ema(closes[:-3], 9)
    rsi = _rsi(closes)
    macd_hist = _macd_histogram(closes)
    atr = _atr(rows)
    close = closes[-1]
    candle = rows[-1]
    candle_range = max(candle["high"] - candle["low"], abs(close) * 1e-12)
    body_ratio = abs(close - candle["open"]) / candle_range
    close_location = (close - candle["low"]) / candle_range

    trend = 0
    if None not in (ema9, ema21, ema50, previous_ema9):
        if ema9 > ema21 > ema50 and ema9 > previous_ema9:
            trend = 1
        elif ema9 < ema21 < ema50 and ema9 < previous_ema9:
            trend = -1

    momentum = 0
    if rsi is not None and macd_hist is not None:
        if 54.0 <= rsi <= 76.0 and macd_hist > 0:
            momentum = 1
        elif 24.0 <= rsi <= 46.0 and macd_hist < 0:
            momentum = -1

    candle_direction = 0
    if body_ratio >= 0.32:
        if close > candle["open"] and close_location >= 0.66:
            candle_direction = 1
        elif close < candle["open"] and close_location <= 0.34:
            candle_direction = -1

    atr_pct = (atr / abs(close) * 100.0) if atr is not None and close else None
    period = TIMEFRAME_SECONDS[timeframe]
    age = max(0.0, now - (candle["time"] + period))

    return {
        "timeframe": timeframe,
        "trend": trend,
        "momentum": momentum,
        "candle_direction": candle_direction,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "rsi14": rsi,
        "macd_histogram": macd_hist,
        "atr": atr,
        "atr_percent": atr_pct,
        "body_ratio": body_ratio,
        "close_location": close_location,
        "last_close": close,
        "last_candle_time": candle["time"],
        "age_seconds": age,
        "fresh": age <= MAX_CANDLE_AGE_SECONDS[timeframe],
        "candles": len(rows),
    }


def _votes(expiry: int, features: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if expiry == 1:
        plan = [
            ("Tendência M1", 25, features["1m"]["trend"]),
            ("Momentum M1", 20, features["1m"]["momentum"]),
            ("Gatilho M1", 20, features["1m"]["candle_direction"]),
            ("Confirmação M5", 20, features["5m"]["trend"]),
            ("Contexto M15", 15, features["15m"]["trend"]),
        ]
    elif expiry == 5:
        plan = [
            ("Tendência M5", 25, features["5m"]["trend"]),
            ("Momentum M5", 20, features["5m"]["momentum"]),
            ("Gatilho M1", 20, features["1m"]["candle_direction"]),
            ("Contexto M15", 20, features["15m"]["trend"]),
            ("Momentum M1", 15, features["1m"]["momentum"]),
        ]
    else:
        plan = [
            ("Tendência M15", 30, features["15m"]["trend"]),
            ("Momentum M15", 20, features["15m"]["momentum"]),
            ("Gatilho M5", 25, features["5m"]["candle_direction"]),
            ("Confirmação M5", 15, features["5m"]["trend"]),
            ("Contexto M1", 10, features["1m"]["trend"]),
        ]
    return [
        {
            "name": name,
            "weight": weight,
            "direction": "CALL" if direction > 0 else "PUT" if direction < 0 else "NEUTRO",
        }
        for name, weight, direction in plan
    ]


def analyze(
    candles: dict[str, list[dict[str, Any]]],
    symbol: str,
    expiry_minutes: int,
    *,
    now: float,
) -> dict[str, Any]:
    """Calculate a read-only CALL/PUT/WAIT assessment from closed IQ Option candles."""
    if expiry_minutes not in (1, 5, 15):
        raise ValueError("A expiração precisa ser de 1, 5 ou 15 minutos.")
    if not symbol or len(symbol) > 32:
        raise ValueError("Ativo inválido.")

    cleaned = {tf: _clean_rows(candles.get(tf, [])) for tf in TIMEFRAME_SECONDS}
    features = {
        tf: _features(cleaned[tf], tf, now)
        for tf in TIMEFRAME_SECONDS
    }
    stale = [tf for tf, item in features.items() if not item["fresh"]]
    votes = _votes(expiry_minutes, features)
    buy_score = sum(item["weight"] for item in votes if item["direction"] == "CALL")
    sell_score = sum(item["weight"] for item in votes if item["direction"] == "PUT")
    difference = abs(buy_score - sell_score)

    signal = "WAIT"
    score = max(buy_score, sell_score)
    if not stale and buy_score >= 72 and buy_score - sell_score >= 28:
        signal = "CALL"
    elif not stale and sell_score >= 72 and sell_score - buy_score >= 28:
        signal = "PUT"

    trigger_tf = "1m" if expiry_minutes in (1, 5) else "5m"
    trigger = features[trigger_tf]
    valid_for = max(
        0,
        int(TIMEFRAME_SECONDS[trigger_tf] + 20 - trigger["age_seconds"]),
    )
    if valid_for <= 0:
        signal = "WAIT"

    reasons: list[str] = []
    if signal == "CALL":
        reasons.append("Predomínio de confluências compradoras nos grupos independentes.")
    elif signal == "PUT":
        reasons.append("Predomínio de confluências vendedoras nos grupos independentes.")
    else:
        reasons.append("Os filtros não encontraram uma confluência direcional suficientemente forte.")
    if stale:
        reasons.append("Dados desatualizados nos períodos: " + ", ".join(stale) + ".")
    if difference < 28:
        reasons.append("Há divergência ou equilíbrio entre os votos de compra e venda.")
    if signal == "WAIT" and valid_for <= 0:
        reasons.append("O candle de gatilho está fora da janela de atualidade.")

    atr_values = [features[tf]["atr_percent"] for tf in ("1m", "5m", "15m")]
    if any(value is not None and value < 0.006 for value in atr_values):
        reasons.append("Volatilidade muito baixa em pelo menos um período.")
    if any(value is not None and value > 0.8 for value in atr_values):
        reasons.append("Volatilidade elevada: risco de movimentos bruscos.")

    return {
        "symbol": symbol,
        "signal": signal,
        "score": int(score),
        "buy_score": int(buy_score),
        "sell_score": int(sell_score),
        "expiry_minutes": expiry_minutes,
        "setup_timeframe": {1: "1m", 5: "5m", 15: "15m"}[expiry_minutes],
        "trigger_timeframe": trigger_tf,
        "entry_reference_price": trigger["last_close"],
        "last_trigger_candle_time": trigger["last_candle_time"],
        "trigger_candle_age_seconds": round(trigger["age_seconds"], 1),
        "valid_for_seconds": valid_for,
        "analysis_time": now,
        "votes": votes,
        "reasons": reasons,
        "timeframes": {
            tf: {
                "trend": item["trend"],
                "momentum": item["momentum"],
                "rsi14": round(item["rsi14"], 2) if item["rsi14"] is not None else None,
                "macd_histogram": item["macd_histogram"],
                "atr_percent": round(item["atr_percent"], 4) if item["atr_percent"] is not None else None,
                "last_close": item["last_close"],
                "candles": item["candles"],
                "age_seconds": round(item["age_seconds"], 1),
                "fresh": item["fresh"],
            }
            for tf, item in features.items()
        },
        "data_quality": {
            "fresh": not stale,
            "stale_timeframes": stale,
            "minimum_candles": MIN_CANDLES,
        },
        "disclaimer": (
            "Score representa confluência técnica, não probabilidade de acerto. "
            "O resultado é informativo e não executa ordens."
        ),
    }
