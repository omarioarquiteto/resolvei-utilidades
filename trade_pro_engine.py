"""Motor de análise do TRADE-PRÓ: regime, confluência e duração sugerida.

A adaptação é heurística e educacional. As estratégias CME descritas no guia são
estruturas de opções/futuros; aqui inspiram filtros de direção e volatilidade,
não são copiadas como ordens de opções. Este módulo nunca envia ordens.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900}
MIN_CANDLES = 80
SIGNAL_THRESHOLD = 72.0


def _ema(values: pd.Series, period: int) -> pd.Series:
    return values.ewm(span=period, adjust=False, min_periods=period).mean()


def _atr(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(14, min_periods=7).mean()


def _adx(frame: pd.DataFrame, atr: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = frame["high"].diff()
    down = -frame["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=7).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=7).mean() / atr.replace(0, np.nan)
    denominator = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denominator
    return (
        dx.ewm(alpha=1 / 14, adjust=False, min_periods=7).mean().fillna(0),
        plus_di.fillna(0),
        minus_di.fillna(0),
    )


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    if not np.isfinite(value):
        return minimum
    return float(max(minimum, min(maximum, value)))


def _clean(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).copy()
    required = ("open", "high", "low", "close")
    for column in required:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "volume" not in frame:
        frame["volume"] = np.nan
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    if "time" not in frame:
        frame["time"] = range(len(frame))
    frame["time"] = pd.to_numeric(frame["time"], errors="coerce")
    frame = (
        frame.dropna(subset=["open", "high", "low", "close", "time"])
        .sort_values("time")
        .drop_duplicates("time")
        .reset_index(drop=True)
    )
    frame = frame[
        (frame["high"] >= frame["low"])
        & (frame["open"] > 0)
        & (frame["high"] > 0)
        & (frame["low"] > 0)
        & (frame["close"] > 0)
    ].copy()
    return frame.reset_index(drop=True)


def _expiration_minutes(
    timeframe: str,
    atr_ratio: float,
    velocity_atr: float,
    candle_body_ratio: float,
    volatility_expanding: bool,
) -> int:
    """Estima a janela mínima compatível com o timeframe e o impulso recente."""
    base_minutes = {"1m": 1, "5m": 5, "15m": 15}[timeframe]
    fast_impulse = velocity_atr >= 1.35 and candle_body_ratio >= 0.55
    very_fast = velocity_atr >= 2.0 and atr_ratio >= 1.10

    if base_minutes == 1:
        if very_fast and volatility_expanding:
            return 1
        if fast_impulse and atr_ratio >= 0.95:
            return 5
        return 15
    if base_minutes == 5:
        if very_fast and volatility_expanding:
            return 5
        return 15
    return 15


def analyze(rows: list[dict[str, Any]], timeframe: str) -> dict[str, Any]:
    """Analisa candles FECHADOS e devolve um sinal ou uma decisão de não operar."""
    if timeframe not in TIMEFRAMES:
        raise ValueError("Timeframe deve ser 1m, 5m ou 15m.")

    frame = _clean(rows)
    if len(frame) < MIN_CANDLES:
        raise ValueError(
            f"Candles fechados insuficientes: {len(frame)}. "
            f"São necessários pelo menos {MIN_CANDLES}."
        )

    close = frame["close"]
    volume = frame["volume"]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    macd = _ema(close, 12) - _ema(close, 26)
    macd_signal = _ema(macd, 9)
    macd_hist = macd - macd_signal
    atr = _atr(frame)
    atr_baseline = atr.rolling(50, min_periods=20).mean()
    adx, plus_di, minus_di = _adx(frame, atr)

    bb_mid = close.rolling(20, min_periods=15).mean()
    bb_std = close.rolling(20, min_periods=15).std(ddof=0)
    bb_width = (4 * bb_std) / bb_mid.replace(0, np.nan)

    current = frame.iloc[-1]
    previous = frame.iloc[-2]
    price = float(current["close"])
    current_atr = float(atr.iloc[-1]) if np.isfinite(atr.iloc[-1]) else 0.0
    baseline_atr = float(atr_baseline.iloc[-1]) if np.isfinite(atr_baseline.iloc[-1]) else 0.0
    atr_ratio = current_atr / baseline_atr if baseline_atr > 0 else 0.0
    adx_value = float(adx.iloc[-1])
    macd_value = float(macd_hist.iloc[-1]) if np.isfinite(macd_hist.iloc[-1]) else 0.0
    plus_value = float(plus_di.iloc[-1])
    minus_value = float(minus_di.iloc[-1])

    ema20_now = float(ema20.iloc[-1])
    ema50_now = float(ema50.iloc[-1])
    ema50_past = float(ema50.iloc[-4]) if len(ema50) >= 4 and np.isfinite(ema50.iloc[-4]) else ema50_now

    prior_high = float(frame["high"].iloc[-21:-1].max())
    prior_low = float(frame["low"].iloc[-21:-1].min())
    breakout_up = price > prior_high
    breakout_down = price < prior_low

    candle_range = max(float(current["high"] - current["low"]), 1e-12)
    candle_body = abs(float(current["close"] - current["open"]))
    body_ratio = candle_body / candle_range
    candle_direction = 1 if current["close"] > current["open"] else -1 if current["close"] < current["open"] else 0
    range_atr = candle_range / current_atr if current_atr > 0 else 0.0
    velocity_atr = (
        abs(price - float(frame["close"].iloc[-4])) / current_atr
        if current_atr > 0 and len(frame) >= 4
        else 0.0
    )

    width_now = float(bb_width.iloc[-1]) if np.isfinite(bb_width.iloc[-1]) else 0.0
    width_prev = float(bb_width.iloc[-2]) if np.isfinite(bb_width.iloc[-2]) else 0.0
    prior_widths = bb_width.iloc[-30:-1].dropna()
    recent_widths = bb_width.iloc[-6:-1].dropna()
    squeeze_level = float(prior_widths.quantile(0.35)) if len(prior_widths) >= 15 else 0.0
    squeeze_recent = bool(len(recent_widths) and squeeze_level > 0 and float(recent_widths.min()) <= squeeze_level)
    width_expanding = width_prev > 0 and width_now >= width_prev * 1.08
    volatility_expanding = bool(squeeze_recent and width_expanding and atr_ratio >= 1.02)

    prior_volume_mean = float(volume.iloc[-21:-1].mean()) if volume.iloc[-21:-1].notna().any() else 0.0
    current_volume = float(volume.iloc[-1]) if np.isfinite(volume.iloc[-1]) else 0.0
    recent_volume = volume.iloc[-30:].dropna()
    volume_has_information = (
        len(recent_volume) >= 20
        and float(recent_volume.max()) > 0
        and (float(recent_volume.max()) - float(recent_volume.min())) > 1e-12
    )
    volume_ratio = current_volume / prior_volume_mean if prior_volume_mean > 0 else 0.0

    bull_ema = price > ema20_now > ema50_now and ema50_now >= ema50_past
    bear_ema = price < ema20_now < ema50_now and ema50_now <= ema50_past
    bull_macd = macd_value > 0 and plus_value >= minus_value
    bear_macd = macd_value < 0 and minus_value >= plus_value
    bull_trend = bool(bull_ema and bull_macd and adx_value >= 18)
    bear_trend = bool(bear_ema and bear_macd and adx_value >= 18)

    # Tendência/rompimento define o candidato direcional. A expansão de volatilidade
    # só autoriza direção depois que o preço rompe a faixa anterior.
    if volatility_expanding and breakout_up:
        regime = "EXPANSÃO DE VOLATILIDADE"
        candidate = "COMPRA"
    elif volatility_expanding and breakout_down:
        regime = "EXPANSÃO DE VOLATILIDADE"
        candidate = "VENDA"
    elif bull_trend:
        regime = "ALTISTA"
        candidate = "COMPRA"
    elif bear_trend:
        regime = "BAIXISTA"
        candidate = "VENDA"
    elif adx_value < 18 and (atr_ratio < 0.90 or (len(prior_widths) >= 15 and width_now <= squeeze_level)):
        regime = "CONSOLIDAÇÃO / ESTABILIZAÇÃO"
        candidate = None
    else:
        regime = "TRANSIÇÃO / SEM CONFIRMAÇÃO"
        candidate = None

    if candidate == "COMPRA":
        trend_ok = bool(
            (bull_ema and (bull_macd or breakout_up) and adx_value >= 16)
            or (breakout_up and price > ema20_now and macd_value > 0)
        )
        directional_candle_ok = candle_direction == 1
        trend_score = (
            (20 if price > ema20_now else 0)
            + (20 if ema20_now > ema50_now else 0)
            + (10 if ema50_now >= ema50_past else 0)
            + (20 if macd_value > 0 else 0)
            + (15 if adx_value >= 25 and plus_value > minus_value else 8 if adx_value >= 18 else 0)
            + (15 if breakout_up else 0)
        )
    elif candidate == "VENDA":
        trend_ok = bool(
            (bear_ema and (bear_macd or breakout_down) and adx_value >= 16)
            or (breakout_down and price < ema20_now and macd_value < 0)
        )
        directional_candle_ok = candle_direction == -1
        trend_score = (
            (20 if price < ema20_now else 0)
            + (20 if ema20_now < ema50_now else 0)
            + (10 if ema50_now <= ema50_past else 0)
            + (20 if macd_value < 0 else 0)
            + (15 if adx_value >= 25 and minus_value > plus_value else 8 if adx_value >= 18 else 0)
            + (15 if breakout_down else 0)
        )
    else:
        trend_ok = False
        directional_candle_ok = False
        trend_score = 0

    volume_ok = bool(
        volume_has_information
        and prior_volume_mean > 0
        and volume_ratio >= 1.02
        and directional_candle_ok
    )
    volume_score = (
        _clamp(58 + (volume_ratio - 1.0) * 65)
        if volume_has_information and volume_ratio > 0 and directional_candle_ok
        else 0.0
    )

    volatility_ok = bool(
        current_atr > 0
        and (atr_ratio >= 0.90 or range_atr >= 1.10)
        and (atr_ratio >= 0.98 or range_atr >= 0.90 or width_expanding)
    )
    volatility_score = _clamp(
        48
        + max(0.0, atr_ratio - 0.80) * 55
        + (14 if width_expanding else 0)
        + (12 if range_atr >= 1.10 else 0)
        + (8 if volatility_expanding else 0)
    )
    trend_score = _clamp(float(trend_score))
    # A direção é o fator principal; volume e volatilidade continuam obrigatórios
    # como filtros, mas não devem bloquear quase toda tendência por um score
    # de volatilidade estruturalmente limitado em mercados direcionais.
    confluence = round(0.50 * trend_score + 0.25 * volume_score + 0.25 * volatility_score, 1)

    signal = None
    expiration = None
    if (
        candidate in {"COMPRA", "VENDA"}
        and trend_ok
        and volume_ok
        and volatility_ok
        and confluence >= SIGNAL_THRESHOLD
        and regime != "CONSOLIDAÇÃO / ESTABILIZAÇÃO"
    ):
        signal = candidate
        expiration = _expiration_minutes(
            timeframe,
            atr_ratio,
            velocity_atr,
            body_ratio,
            volatility_expanding,
        )

    if regime == "ALTISTA":
        reason = "Long Call adaptada (CME): tendência altista confirmada por preço, médias e MACD."
    elif regime == "BAIXISTA":
        reason = "Long Put adaptada (CME): tendência baixista confirmada por preço, médias e MACD."
    elif regime == "EXPANSÃO DE VOLATILIDADE":
        reason = "Long Straddle/Strangle adaptada (CME): compressão prévia, expansão e rompimento direcional."
    elif regime == "CONSOLIDAÇÃO / ESTABILIZAÇÃO":
        reason = "Filtro Short Straddle/Strangle (CME): consolidação detectada; sinais direcionais pausados."
    else:
        reason = "Sem confluência suficiente: mercado em transição; aguardar confirmação."

    if signal and not volume_has_information:
        # Salvaguarda defensiva: sem dados de volume confiáveis, não se emite sinal.
        signal = None
        expiration = None

    # Explique cada filtro que bloqueou o sinal. Isso permite depuração sem
    # afrouxar os controles às cegas e torna o SEM SINAL acionável pelo usuário.
    blocking_reasons: list[str] = []
    if candidate not in {"COMPRA", "VENDA"}:
        blocking_reasons.append(
            "Direção não identificada: tendência, MACD, ADX ou rompimento ainda não confirmam um cenário."
        )
    if candidate in {"COMPRA", "VENDA"} and not trend_ok:
        blocking_reasons.append("Confirmação direcional insuficiente pelos indicadores de tendência.")
    if candidate in {"COMPRA", "VENDA"} and not directional_candle_ok:
        blocking_reasons.append("O candle fechado não confirmou a direção do sinal.")
    if not volume_has_information:
        blocking_reasons.append("Dados de volume indisponíveis ou sem variação suficiente.")
    elif not volume_ok:
        blocking_reasons.append(
            f"Volume não confirmado: exige pelo menos 1,02× a média recente e candle na direção do sinal (atual: {volume_ratio:.2f}×)."
        )
    if not volatility_ok:
        blocking_reasons.append("Volatilidade insuficiente para validar a entrada.")
    if confluence < SIGNAL_THRESHOLD:
        blocking_reasons.append(
            f"Confluência de {confluence:.1f}% abaixo do mínimo de {SIGNAL_THRESHOLD:.0f}%."
        )

    return {
        "signal": signal,
        "status": "SINAL_VALIDADO" if signal else "SEM_SINAL",
        "regime": regime,
        "reason": reason,
        "confluence": confluence,
        "threshold": SIGNAL_THRESHOLD,
        "expiration_minutes": expiration,
        "blocking_reasons": blocking_reasons,
        "checks": {
            "direction_detected": candidate in {"COMPRA", "VENDA"},
            "trend_confirmed": bool(trend_ok),
            "directional_candle_confirmed": bool(directional_candle_ok),
            "volume_data_available": bool(volume_has_information),
            "volume_confirmed": bool(volume_ok),
            "volatility_confirmed": bool(volatility_ok),
            "confluence_confirmed": bool(confluence >= SIGNAL_THRESHOLD),
            "signal_valid": bool(signal),
        },
        "market": {
            "price": round(price, 8),
            "adx": round(adx_value, 2),
            "atr_ratio": round(atr_ratio, 3),
            "volume_ratio": round(volume_ratio, 3),
            "velocity_atr": round(velocity_atr, 3),
            "range_atr": round(range_atr, 3),
            "breakout_up": bool(breakout_up),
            "breakout_down": bool(breakout_down),
            "volume_confirmed": bool(volume_ok),
            "volatility_confirmed": bool(volatility_ok),
            "trend_confirmed": bool(trend_ok),
            "volume_data_available": bool(volume_has_information),
            "volatility_expanding": bool(volatility_expanding),
        },
        "scores": {
            "trend": round(trend_score, 1),
            "volume": round(volume_score, 1),
            "volatility": round(volatility_score, 1),
        },
        "candle_time": int(float(current["time"])),
        "timeframe": timeframe,
    }
