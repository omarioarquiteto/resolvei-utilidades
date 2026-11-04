from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

INTERVALS = {"1m": 60, "5m": 300}
MIN_CANDLES = 220
GROUP_WEIGHTS = {"trend": 30, "momentum": 25, "structure": 25, "conditions": 20}
STRATEGIES = {
    "auto": {"name": "Automática"},
    "trend": {"name": "Tendência"},
    "breakout": {"name": "Rompimento"},
    "reversion": {"name": "Reversão"},
}
STRATEGY_LABELS = {
    "trend": "Tendência",
    "breakout": "Rompimento",
    "reversion": "Reversão",
    "none": "Sem contexto favorável",
}


def clean(rows: list[dict[str, Any]]) -> pd.DataFrame:
    data = pd.DataFrame(rows).copy()
    if data.empty:
        raise ValueError("A IQ Option não retornou candles para análise.")
    for column in ("open", "high", "low", "close"):
        if column not in data:
            raise ValueError(f"Campo obrigatório ausente nos candles: {column}.")
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if "volume" not in data:
        data["volume"] = np.nan
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    if "time" not in data:
        data["time"] = np.arange(len(data), dtype=float)
    data["time"] = pd.to_numeric(data["time"], errors="coerce")
    data = data.dropna(subset=["time", "open", "high", "low", "close"])
    data = data[
        (data["open"] > 0)
        & (data["high"] >= data[["open", "close", "low"]].max(axis=1))
        & (data["low"] <= data[["open", "close", "high"]].min(axis=1))
    ]
    return (
        data.sort_values("time")
        .drop_duplicates("time", keep="last")
        .reset_index(drop=True)
    )


def _last(series: pd.Series) -> float:
    value = series.iloc[-1] if len(series) else np.nan
    return float(value) if pd.notna(value) else float("nan")


def _prev(series: pd.Series) -> float:
    value = series.iloc[-2] if len(series) > 1 else np.nan
    return float(value) if pd.notna(value) else float("nan")


def _vote(value: float, threshold: float = 0.0) -> int:
    if not np.isfinite(value) or abs(value) <= threshold:
        return 0
    return 1 if value > 0 else -1


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.where(loss.ne(0), 100.0)
    result = result.where(gain.ne(0) | loss.ne(0), 50.0)
    return result.fillna(50.0)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous).abs(), (low - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    true_range = _atr(high, low, close, period)
    plus_di = 100 * plus_dm.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean() / true_range.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(
        alpha=1 / period, adjust=False, min_periods=period
    ).mean() / true_range.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return (
        dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().fillna(0),
        plus_di.fillna(0),
        minus_di.fillna(0),
    )


def _stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(period, min_periods=period).min()
    highest = high.rolling(period, min_periods=period).max()
    k = (100 * (close - lowest) / (highest - lowest).replace(0, np.nan)).fillna(50)
    return k, k.rolling(3, min_periods=3).mean().fillna(50)


def _parabolic_sar(high: pd.Series, low: pd.Series, step: float = 0.02, maximum: float = 0.2) -> pd.Series:
    highs = high.to_numpy(dtype=float)
    lows = low.to_numpy(dtype=float)
    count = len(highs)
    output = np.full(count, np.nan, dtype=float)
    if count < 3:
        return pd.Series(output, index=high.index)

    rising = highs[1] + lows[1] >= highs[0] + lows[0]
    sar = min(lows[0], lows[1]) if rising else max(highs[0], highs[1])
    extreme = max(highs[0], highs[1]) if rising else min(lows[0], lows[1])
    acceleration = step

    for index in range(2, count):
        candidate = sar + acceleration * (extreme - sar)
        if rising:
            candidate = min(candidate, lows[index - 1], lows[index - 2])
            if lows[index] < candidate:
                rising = False
                candidate = extreme
                extreme = lows[index]
                acceleration = step
            elif highs[index] > extreme:
                extreme = highs[index]
                acceleration = min(maximum, acceleration + step)
        else:
            candidate = max(candidate, highs[index - 1], highs[index - 2])
            if highs[index] > candidate:
                rising = True
                candidate = extreme
                extreme = highs[index]
                acceleration = step
            elif lows[index] < extreme:
                extreme = lows[index]
                acceleration = min(maximum, acceleration + step)
        sar = candidate
        output[index] = sar
    return pd.Series(output, index=high.index)


def _aroon(high: pd.Series, low: pd.Series, period: int = 25) -> tuple[pd.Series, pd.Series]:
    window = period + 1
    up = high.rolling(window, min_periods=window).apply(
        lambda values: 100.0 * int(np.argmax(values)) / period, raw=True
    )
    down = low.rolling(window, min_periods=window).apply(
        lambda values: 100.0 * int(np.argmin(values)) / period, raw=True
    )
    return up, down


def _ichimoku_cloud(
    high: pd.Series, low: pd.Series
) -> tuple[pd.Series, pd.Series]:
    tenkan = (high.rolling(9, min_periods=9).max() + low.rolling(9, min_periods=9).min()) / 2
    kijun = (high.rolling(26, min_periods=26).max() + low.rolling(26, min_periods=26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = (
        (high.rolling(52, min_periods=52).max() + low.rolling(52, min_periods=52).min()) / 2
    ).shift(26)
    return span_a, span_b


def _resample_context(
    rows: pd.DataFrame, target_seconds: int, now: float
) -> pd.DataFrame:
    buckets = (rows["time"].astype(float) // target_seconds) * target_seconds
    temp = rows.assign(_bucket=buckets)
    grouped = temp.groupby("_bucket", sort=True).agg(
        time=("time", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        count=("close", "count"),
    )
    grouped = grouped[(grouped.index + target_seconds) <= (float(now) + 0.2)]
    return grouped.drop(columns=["count"]).reset_index(drop=True)


def _context_direction(rows: pd.DataFrame) -> tuple[int, float, float]:
    if len(rows) < 35:
        return 0, 0.0, 0.0
    close = rows["close"]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    adx, plus_di, minus_di = _adx(rows["high"], rows["low"], close)
    spread = _last(ema20) - _last(ema50)
    atr_value = _last(_atr(rows["high"], rows["low"], close))
    direction = 0
    if _last(adx) >= 18 and _last(plus_di) > _last(minus_di) and spread > 0:
        direction = 1
    elif _last(adx) >= 18 and _last(minus_di) > _last(plus_di) and spread < 0:
        direction = -1
    elif np.isfinite(atr_value) and atr_value > 0 and abs(spread) >= atr_value * 0.08:
        direction = 1 if spread > 0 else -1
    return direction, _last(adx), spread


def _candle_force(row: pd.Series) -> int:
    candle_range = max(float(row["high"] - row["low"]), 1e-12)
    body = float(row["close"] - row["open"])
    close_position = (float(row["close"]) - float(row["low"])) / candle_range
    if body > 0 and body / candle_range >= 0.55 and close_position >= 0.75:
        return 1
    if body < 0 and abs(body) / candle_range >= 0.55 and close_position <= 0.25:
        return -1
    return 0


def _rejection(row: pd.Series) -> int:
    candle_range = max(float(row["high"] - row["low"]), 1e-12)
    body = abs(float(row["close"] - row["open"]))
    upper = float(row["high"] - max(row["open"], row["close"]))
    lower = float(min(row["open"], row["close"]) - row["low"])
    if lower >= max(body * 1.8, candle_range * 0.42) and lower > upper * 1.25:
        return 1
    if upper >= max(body * 1.8, candle_range * 0.42) and upper > lower * 1.25:
        return -1
    return 0


def _support_resistance(
    rows: pd.DataFrame, atr_value: float, rejection: int
) -> int:
    if len(rows) < 65 or not np.isfinite(atr_value) or atr_value <= 0:
        return 0
    price = float(rows["close"].iloc[-1])
    prior = rows.iloc[-61:-1]
    support = float(prior["low"].min())
    resistance = float(prior["high"].max())
    tolerance = atr_value * 0.35
    if abs(price - support) <= tolerance and (rejection >= 0):
        return 1
    if abs(price - resistance) <= tolerance and (rejection <= 0):
        return -1
    return 0


def _group_support(votes: list[int], direction: int) -> float:
    active = [value for value in votes if value != 0]
    if not active:
        return 0.0
    return sum(1 for value in active if value == direction) / len(active)


def analyze(
    rows: list[dict[str, Any]],
    strategy: str = "auto",
    timeframe: str = "1m",
    now: float | None = None,
) -> dict[str, Any]:
    if timeframe not in INTERVALS:
        raise ValueError("Timeframe deve ser 1m ou 5m.")
    if strategy not in STRATEGIES:
        raise ValueError("Estratégia inválida.")

    data = clean(rows)
    if len(data) < MIN_CANDLES:
        raise ValueError(
            f"Candles fechados insuficientes: {len(data)}. São necessários pelo menos {MIN_CANDLES}."
        )

    interval = INTERVALS[timeframe]
    current_time = float(now) if now is not None else float(data["time"].iloc[-1] + interval)
    higher_seconds = 300 if timeframe == "1m" else 900
    higher_timeframe = "5m" if timeframe == "1m" else "15m"
    higher_rows = _resample_context(data, higher_seconds, current_time)

    high = data["high"]
    low = data["low"]
    close = data["close"]
    volume = data["volume"]
    price = _last(close)

    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    atr = _atr(high, low, close)
    atr_mean = atr.rolling(50, min_periods=30).mean()
    atr_value = _last(atr)
    atr_ratio = atr_value / _last(atr_mean) if _last(atr_mean) > 0 else float("nan")
    adx, plus_di, minus_di = _adx(high, low, close)
    rsi14 = _rsi(close, 14)
    rsi7 = _rsi(close, 7)
    stoch_k, stoch_d = _stochastic(high, low, close)

    macd = _ema(close, 12) - _ema(close, 26)
    macd_signal = _ema(macd, 9)
    macd_hist = macd - macd_signal

    psar = _parabolic_sar(high, low)
    aroon_up, aroon_down = _aroon(high, low)
    cloud_a, cloud_b = _ichimoku_cloud(high, low)

    previous_high = high.shift(1).rolling(20, min_periods=20).max()
    previous_low = low.shift(1).rolling(20, min_periods=20).min()
    prior_high = _last(previous_high)
    prior_low = _last(previous_low)
    donchian_vote = 1 if price > prior_high else -1 if price < prior_low else 0

    bb_middle = close.rolling(20, min_periods=20).mean()
    bb_std = close.rolling(20, min_periods=20).std(ddof=0)
    bb_upper = bb_middle + 2 * bb_std
    bb_lower = bb_middle - 2 * bb_std
    bandwidth = (bb_upper - bb_lower) / close.replace(0, np.nan)
    squeeze_threshold = _last(bandwidth.rolling(100, min_periods=40).quantile(0.25))
    prior_squeeze = bool((bandwidth.shift(1).tail(3) <= squeeze_threshold).any()) if np.isfinite(squeeze_threshold) else False
    bandwidth_expanding = (
        np.isfinite(_last(bandwidth))
        and np.isfinite(_prev(bandwidth))
        and _last(bandwidth) > _prev(bandwidth) * 1.12
    )
    breakout_confirmed = (
        prior_squeeze
        and bandwidth_expanding
        and donchian_vote != 0
        and np.isfinite(atr_ratio)
        and atr_ratio >= 1.05
    )

    recent_volume = volume.tail(30)
    valid_volume = recent_volume.notna() & (recent_volume > 0)
    volume_available = (
        len(recent_volume) >= 25
        and float(valid_volume.mean()) >= 0.85
        and float(recent_volume[valid_volume].std(ddof=0) or 0) > 1e-9
    )
    volume_vote = 0
    if volume_available:
        volume_mean = volume.rolling(20, min_periods=15).mean()
        flow = np.sign(close.diff().fillna(0)) * volume
        flow_mean = flow.rolling(8, min_periods=6).mean()
        if _last(volume) >= 1.5 * _last(volume_mean):
            volume_vote = _vote(_last(flow_mean))

    current_row = data.iloc[-1]
    candle_vote = _candle_force(current_row)
    rejection_vote = _rejection(current_row)
    sr_vote = _support_resistance(data, atr_value, rejection_vote)

    current_adx = _last(adx)
    current_plus = _last(plus_di)
    current_minus = _last(minus_di)
    ema_spread = _last(ema20) - _last(ema50)
    ema_vote = 1 if ema_spread > 0 and _last(ema20) >= _prev(ema20) else -1 if ema_spread < 0 and _last(ema20) <= _prev(ema20) else 0
    ema200_vote = _vote(price - _last(ema200))
    adx_vote = (
        1 if current_adx >= 20 and current_plus > current_minus
        else -1 if current_adx >= 20 and current_minus > current_plus
        else 0
    )
    psar_vote = _vote(price - _last(psar))
    aroon_vote = 1 if _last(aroon_up) >= 70 and _last(aroon_down) <= 30 else -1 if _last(aroon_down) >= 70 and _last(aroon_up) <= 30 else 0
    cloud_top = max(_last(cloud_a), _last(cloud_b))
    cloud_bottom = min(_last(cloud_a), _last(cloud_b))
    ichimoku_vote = 1 if price > cloud_top else -1 if price < cloud_bottom else 0

    macd_vote = _vote(_last(macd_hist), max(atr_value * 0.005, 1e-12))
    rsi_trend_vote = (
        1 if _last(rsi14) >= 53 and _last(rsi14) > _prev(rsi14)
        else -1 if _last(rsi14) <= 47 and _last(rsi14) < _prev(rsi14)
        else 0
    )
    stoch_trend_vote = (
        1 if _last(stoch_k) > _last(stoch_d) and 25 < _last(stoch_k) < 80
        else -1 if _last(stoch_k) < _last(stoch_d) and 20 < _last(stoch_k) < 75
        else 0
    )

    range_regime = current_adx <= 18
    trend_regime = (
        current_adx >= 20
        and ((current_plus > current_minus and ema_spread > 0) or (current_minus > current_plus and ema_spread < 0))
    )
    if breakout_confirmed:
        market_regime = "breakout"
    elif trend_regime:
        market_regime = "trend"
    elif range_regime:
        market_regime = "range"
    else:
        market_regime = "transition"

    if strategy == "auto":
        if market_regime == "breakout":
            selected_strategy = "breakout"
        elif market_regime == "trend":
            selected_strategy = "trend"
        elif market_regime == "range":
            selected_strategy = "reversion"
        else:
            selected_strategy = "none"
    else:
        selected_strategy = strategy

    higher_direction, higher_adx, higher_spread = _context_direction(higher_rows)
    current_context_direction = 1 if ema_spread > 0 else -1 if ema_spread < 0 else 0

    if selected_strategy == "reversion":
        rsi_reversal = (
            1 if _last(rsi7) <= 28 and _last(rsi7) > _prev(rsi7)
            else -1 if _last(rsi7) >= 72 and _last(rsi7) < _prev(rsi7)
            else 0
        )
        stoch_reversal = (
            1 if _last(stoch_k) <= 25 and _last(stoch_k) > _last(stoch_d)
            else -1 if _last(stoch_k) >= 75 and _last(stoch_k) < _last(stoch_d)
            else 0
        )
        typical = (high + low + close) / 3
        typical_mean = typical.rolling(20, min_periods=20).mean()
        mean_deviation = typical.rolling(20, min_periods=20).apply(
            lambda values: float(np.mean(np.abs(values - np.mean(values)))), raw=True
        )
        cci = (typical - typical_mean) / (0.015 * mean_deviation).replace(0, np.nan)
        cci_value = _last(cci)
        cci_reversal = 1 if cci_value <= -100 else -1 if cci_value >= 100 else 0
        band_reversal = 1 if price <= _last(bb_lower) else -1 if price >= _last(bb_upper) else 0
        trend_votes = [0, 0, 0, 0, higher_direction if higher_adx < 25 else 0]
        momentum_votes = [rsi_reversal, stoch_reversal, cci_reversal, rejection_vote]
        structure_votes = [sr_vote, band_reversal, rejection_vote]
        items = [
            ("RSI em extremo", rsi_reversal, "momentum", 12),
            ("Estocástico de reversão", stoch_reversal, "momentum", 10),
            ("CCI", cci_reversal, "momentum", 8),
            ("Rejeição de candle", rejection_vote, "structure", 12),
            ("Suporte / resistência", sr_vote, "structure", 12),
            ("Banda de Bollinger", band_reversal, "structure", 10),
            ("Divergência de momentum", 0, "momentum", 8),
            ("Distância da EMA 20", _vote(_last(ema20) - price) if price < _last(ema20) else _vote(_last(ema20) - price), "structure", 8),
            ("Contexto superior", higher_direction, "trend", 10),
            ("Volatilidade adequada", 1 if np.isfinite(atr_ratio) and 0.55 <= atr_ratio <= 2.4 else 0, "conditions", 10),
        ]
    elif selected_strategy == "breakout":
        momentum_votes = [macd_vote, rsi_trend_vote, volume_vote]
        structure_votes = [donchian_vote, candle_vote, 1 if breakout_confirmed else 0, sr_vote]
        trend_votes = [ema_vote, ema200_vote, adx_vote, psar_vote, higher_direction]
        items = [
            ("EMA 20 / 50", ema_vote, "trend", 10),
            ("EMA 200", ema200_vote, "trend", 8),
            ("ADX + DI", adx_vote, "trend", 10),
            ("Parabolic SAR", psar_vote, "trend", 7),
            ("Contexto superior", higher_direction, "trend", 10),
            ("MACD", macd_vote, "momentum", 10),
            ("RSI 14", rsi_trend_vote, "momentum", 8),
            ("Fluxo de volume", volume_vote, "momentum", 7),
            ("Donchian 20", donchian_vote, "structure", 10),
            ("Expansão após squeeze", 1 if breakout_confirmed and donchian_vote == 1 else -1 if breakout_confirmed and donchian_vote == -1 else 0, "structure", 8),
            ("Força do candle", candle_vote, "structure", 8),
            ("Suporte / resistência", sr_vote, "structure", 7),
            ("Volatilidade adequada", 1 if np.isfinite(atr_ratio) and 0.55 <= atr_ratio <= 2.4 else 0, "conditions", 10),
        ]
    else:
        trend_votes = [ema_vote, ema200_vote, adx_vote, psar_vote, higher_direction]
        momentum_votes = [macd_vote, rsi_trend_vote, stoch_trend_vote]
        structure_votes = [donchian_vote, candle_vote, sr_vote, ichimoku_vote]
        items = [
            ("EMA 20 / 50", ema_vote, "trend", 8),
            ("EMA 200", ema200_vote, "trend", 8),
            ("ADX + DI", adx_vote, "trend", 8),
            ("Parabolic SAR real", psar_vote, "trend", 8),
            ("Ichimoku Kumo", ichimoku_vote, "structure", 8),
            ("Aroon 25", aroon_vote, "momentum", 8),
            ("MACD", macd_vote, "momentum", 10),
            ("RSI 14", rsi_trend_vote, "momentum", 8),
            ("Estocástico", stoch_trend_vote, "momentum", 8),
            ("Donchian 20", donchian_vote, "structure", 8),
            ("Força do candle", candle_vote, "structure", 8),
            ("Suporte / resistência", sr_vote, "structure", 8),
            ("Fluxo de volume", volume_vote, "momentum", 8),
        ]

    if selected_strategy == "none":
        trend_votes = [ema_vote, ema200_vote, adx_vote, higher_direction]
        momentum_votes = [macd_vote, rsi_trend_vote, stoch_trend_vote]
        structure_votes = [donchian_vote, candle_vote, sr_vote]
        items = [
            ("EMA 20 / 50", ema_vote, "trend", 10),
            ("EMA 200", ema200_vote, "trend", 10),
            ("ADX + DI", adx_vote, "trend", 10),
            ("Contexto superior", higher_direction, "trend", 10),
            ("MACD", macd_vote, "momentum", 10),
            ("RSI 14", rsi_trend_vote, "momentum", 10),
            ("Estocástico", stoch_trend_vote, "momentum", 10),
            ("Donchian 20", donchian_vote, "structure", 10),
            ("Força do candle", candle_vote, "structure", 10),
            ("Suporte / resistência", sr_vote, "structure", 10),
        ]

    quality_ok = np.isfinite(atr_ratio) and 0.55 <= atr_ratio <= 2.4
    if selected_strategy == "reversion":
        quality_ok = quality_ok and market_regime == "range"
    elif selected_strategy == "trend":
        quality_ok = quality_ok and market_regime == "trend"
    elif selected_strategy == "breakout":
        quality_ok = quality_ok and market_regime == "breakout"

    group_votes = {
        "trend": trend_votes,
        "momentum": momentum_votes,
        "structure": structure_votes,
    }
    scores: dict[str, dict[str, float]] = {}
    for group, votes in group_votes.items():
        scores[group] = {
            "call": round(_group_support(votes, 1) * GROUP_WEIGHTS[group], 1),
            "put": round(_group_support(votes, -1) * GROUP_WEIGHTS[group], 1),
            "activeVotes": sum(1 for value in votes if value != 0),
        }
    scores["conditions"] = {
        "call": float(GROUP_WEIGHTS["conditions"] if quality_ok else 0),
        "put": float(GROUP_WEIGHTS["conditions"] if quality_ok else 0),
        "activeVotes": 1 if quality_ok else 0,
    }

    call_score = sum(group["call"] for group in scores.values())
    put_score = sum(group["put"] for group in scores.values())
    direction = "CALL" if call_score > put_score else "PUT" if put_score > call_score else "NONE"
    score = max(call_score, put_score)
    selected_score = call_score if direction == "CALL" else put_score
    opposing_score = put_score if direction == "CALL" else call_score
    confirmed_groups = 0
    opposing_groups = 0
    if direction != "NONE":
        for group in group_votes.values():
            support = _group_support(group, 1 if direction == "CALL" else -1)
            opposite = _group_support(group, -1 if direction == "CALL" else 1)
            if support >= 0.60:
                confirmed_groups += 1
            if opposite >= 0.60:
                opposing_groups += 1

    blocking_reasons: list[str] = []
    if selected_strategy == "none":
        blocking_reasons.append("Mercado em transição: as estratégias não apresentam contexto suficientemente definido.")
    if not quality_ok:
        blocking_reasons.append("Volatilidade fora da faixa operacional validada.")
    if len(higher_rows) < 35:
        blocking_reasons.append(f"Histórico insuficiente para confirmar o contexto de {higher_timeframe}.")
    elif direction != "NONE" and higher_direction not in (0, 1 if direction == "CALL" else -1):
        blocking_reasons.append(f"O contexto de {higher_timeframe} está contrário ao sinal.")
    if selected_strategy == "trend" and market_regime != "trend":
        blocking_reasons.append("A estratégia de tendência foi bloqueada porque o mercado não apresenta tendência confirmada.")
    if selected_strategy == "breakout" and market_regime != "breakout":
        blocking_reasons.append("Não houve rompimento confirmado após compressão e expansão.")
    if selected_strategy == "reversion" and market_regime != "range":
        blocking_reasons.append("A reversão foi bloqueada porque o mercado não está lateral.")
    if direction != "NONE":
        distance_atr = abs(price - _last(ema20)) / atr_value if atr_value > 0 else 0
        if distance_atr > 1.35:
            blocking_reasons.append("Preço muito distante da EMA 20: risco de entrada atrasada.")
        if direction == "CALL" and _last(rsi14) >= 80 and distance_atr > 0.8:
            blocking_reasons.append("CALL bloqueada por momentum excessivamente esticado.")
        if direction == "PUT" and _last(rsi14) <= 20 and distance_atr > 0.8:
            blocking_reasons.append("PUT bloqueada por momentum excessivamente esticado.")
    if confirmed_groups < 2:
        blocking_reasons.append("Menos de dois grupos independentes confirmam a direção.")
    if opposing_groups:
        blocking_reasons.append("Há conflito relevante entre grupos de indicadores.")
    if selected_score - opposing_score < 16:
        blocking_reasons.append("A diferença entre CALL e PUT é insuficiente.")
    if score < 72:
        blocking_reasons.append("Confluência abaixo do limite operacional de 72 pontos.")

    valid_signal = not blocking_reasons and direction != "NONE"
    if valid_signal:
        signal = "SINAL FORTE" if score >= 82 else "SINAL MODERADO"
    else:
        direction = "NONE"
        signal = "SEM SINAL"

    indicator_items = [
        {
            "name": name,
            "weight": weight,
            "direction": vote_value,
            "group": group,
            "active": valid_signal and vote_value == (1 if direction == "CALL" else -1),
        }
        for name, vote_value, group, weight in items
    ]
    regime_labels = {
        "trend": "Tendência identificada",
        "breakout": "Rompimento em confirmação",
        "range": "Mercado lateral",
        "transition": "Mercado em transição",
    }
    return {
        "strategy": selected_strategy,
        "strategyLabel": STRATEGY_LABELS.get(selected_strategy, "Automática"),
        "requestedStrategy": strategy,
        "direction": direction,
        "score": round(score, 1),
        "callScore": round(call_score, 1),
        "putScore": round(put_score, 1),
        "signal": signal,
        "indicators": indicator_items,
        "groupScores": scores,
        "marketRegime": market_regime,
        "marketRegimeLabel": regime_labels[market_regime],
        "higherTimeframe": higher_timeframe,
        "higherDirection": "CALL" if higher_direction == 1 else "PUT" if higher_direction == -1 else "NEUTRO",
        "higherAdx": round(higher_adx, 1),
        "higherTrendSpread": higher_spread,
        "atrRatio": round(float(atr_ratio), 3) if np.isfinite(atr_ratio) else None,
        "volumeDataAvailable": bool(volume_available),
        "qualityOk": bool(quality_ok),
        "confirmedGroups": confirmed_groups,
        "blockingReasons": blocking_reasons,
        "expiryMinutes": int(interval / 60),
        "analysisVersion": "2.0",
    }
