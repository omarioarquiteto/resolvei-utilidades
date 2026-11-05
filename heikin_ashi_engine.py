from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


INTERVALS = {"1m": 60, "5m": 300, "15m": 900}
MIN_CANDLES = 180
CHART_CANDLES = 72
MIN_SIGNAL_SCORE = 76.0


def clean(rows: list[dict[str, Any]]) -> pd.DataFrame:
    data = pd.DataFrame(rows).copy()
    if data.empty:
        raise ValueError("A IQ Option não retornou candles para análise.")
    for column in ("open", "high", "low", "close"):
        if column not in data:
            raise ValueError(f"Campo obrigatório ausente nos candles: {column}.")
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if "time" not in data:
        data["time"] = np.arange(len(data), dtype=float)
    data["time"] = pd.to_numeric(data["time"], errors="coerce")
    if "volume" not in data:
        data["volume"] = np.nan
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["time", "open", "high", "low", "close"])
    data = data[
        (data["open"] > 0)
        & (data["high"] >= data[["open", "close", "low"]].max(axis=1))
        & (data["low"] <= data[["open", "close", "high"]].min(axis=1))
    ]
    return data.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def heikin_ashi(rows: pd.DataFrame | list[dict[str, Any]]) -> pd.DataFrame:
    data = clean(rows) if not isinstance(rows, pd.DataFrame) else rows.copy()
    ha_close = (data["open"] + data["high"] + data["low"] + data["close"]) / 4.0
    ha_open = np.zeros(len(data), dtype=float)
    if len(data):
        ha_open[0] = (float(data["open"].iloc[0]) + float(data["close"].iloc[0])) / 2.0
        for index in range(1, len(data)):
            ha_open[index] = (ha_open[index - 1] + float(ha_close.iloc[index - 1])) / 2.0
    result = pd.DataFrame(index=data.index)
    result["ha_open"] = ha_open
    result["ha_close"] = ha_close
    result["ha_high"] = pd.concat([data["high"], result["ha_open"], result["ha_close"]], axis=1).max(axis=1)
    result["ha_low"] = pd.concat([data["low"], result["ha_open"], result["ha_close"]], axis=1).min(axis=1)
    candle_range = (result["ha_high"] - result["ha_low"]).replace(0, np.nan)
    body = (result["ha_close"] - result["ha_open"]).abs()
    result["body_ratio"] = (body / candle_range).fillna(0.0).clip(0.0, 1.0)
    result["upper_wick"] = (result["ha_high"] - result[["ha_open", "ha_close"]].max(axis=1)).clip(lower=0)
    result["lower_wick"] = (result[["ha_open", "ha_close"]].min(axis=1) - result["ha_low"]).clip(lower=0)
    result["color"] = np.where(result["ha_close"] > result["ha_open"], 1,
                               np.where(result["ha_close"] < result["ha_open"], -1, 0))
    return result


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    result = result.where(loss.ne(0), 100.0)
    result = result.where(gain.ne(0) | loss.ne(0), 50.0)
    return result.fillna(50.0)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    previous = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous).abs(), (low - previous).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    true_range = _atr(high, low, close, period)
    plus_smoothed = plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    minus_smoothed = minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100.0 * plus_smoothed / true_range.replace(0, np.nan)
    minus_di = 100.0 * minus_smoothed / true_range.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return adx.fillna(0.0), plus_di.fillna(0.0), minus_di.fillna(0.0)


def _last(series: pd.Series, default: float = 0.0) -> float:
    if not len(series) or pd.isna(series.iloc[-1]):
        return float(default)
    return float(series.iloc[-1])


def _previous(series: pd.Series, default: float = 0.0) -> float:
    if len(series) < 2 or pd.isna(series.iloc[-2]):
        return float(default)
    return float(series.iloc[-2])


def _resample_context(data: pd.DataFrame, target_seconds: int, now: float) -> pd.DataFrame:
    buckets = (data["time"].astype(float) // target_seconds) * target_seconds
    temp = data.assign(_bucket=buckets)
    grouped = temp.groupby("_bucket", sort=True).agg(
        time=("time", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    grouped = grouped[(grouped.index + target_seconds) <= float(now) + 0.2]
    return grouped.reset_index(drop=True)


def _context_direction(data: pd.DataFrame) -> int:
    if len(data) < 35:
        return 0
    ha = heikin_ashi(data)
    close = ha["ha_close"]
    ema9, ema21, ema50 = _ema(close, 9), _ema(close, 21), _ema(close, 50)
    adx, plus_di, minus_di = _adx(data["high"], data["low"], data["close"])
    rising = _last(ema21) > _previous(ema21)
    falling = _last(ema21) < _previous(ema21)
    if _last(adx) >= 15 and _last(ema9) > _last(ema21) > _last(ema50) and rising and _last(plus_di) > _last(minus_di):
        return 1
    if _last(adx) >= 15 and _last(ema9) < _last(ema21) < _last(ema50) and falling and _last(minus_di) > _last(plus_di):
        return -1
    return 0


def _round(value: float, digits: int = 6) -> float | None:
    return round(float(value), digits) if np.isfinite(value) else None


def analyze(
    rows: list[dict[str, Any]],
    timeframe: str = "1m",
    strategy: str = "auto",
    now: float | None = None,
) -> dict[str, Any]:
    if timeframe not in INTERVALS:
        raise ValueError("Expiração deve ser 1m, 5m ou 15m.")
    if strategy not in ("auto", "trend", "reversal"):
        raise ValueError("Estratégia inválida: use automática, tendência ou reversão.")

    data = clean(rows)
    if len(data) < MIN_CANDLES:
        raise ValueError(
            f"Candles fechados insuficientes: {len(data)}. São necessários pelo menos {MIN_CANDLES}."
        )

    interval = INTERVALS[timeframe]
    current_time = float(now) if now is not None else float(data["time"].iloc[-1] + interval)
    ha = heikin_ashi(data)
    ha_close = ha["ha_close"]
    raw_close = data["close"]
    ema9 = _ema(ha_close, 9)
    ema21 = _ema(ha_close, 21)
    ema50 = _ema(ha_close, 50)
    rsi = _rsi(raw_close, 14)
    macd = _ema(ha_close, 12) - _ema(ha_close, 26)
    macd_signal = _ema(macd, 9)
    macd_hist = macd - macd_signal
    atr = _atr(data["high"], data["low"], raw_close)
    adx, plus_di, minus_di = _adx(data["high"], data["low"], raw_close)

    price = _last(raw_close)
    atr_value = _last(atr)
    atr_average = _last(atr.rolling(50, min_periods=20).mean(), atr_value)
    volatility_ratio = atr_value / atr_average if atr_average > 0 else 1.0
    atr_percent = (atr_value / price * 100.0) if price else 0.0
    current_adx = _last(adx)
    current_rsi = _last(rsi)
    previous_rsi = _previous(rsi, current_rsi)
    current_macd = _last(macd_hist)
    previous_macd = _previous(macd_hist, current_macd)
    last_color = int(ha["color"].iloc[-1])
    previous_color = int(ha["color"].iloc[-2])
    colors3 = [int(value) for value in ha["color"].tail(3).tolist()]
    colors4 = [int(value) for value in ha["color"].tail(4).tolist()]
    last_body = _last(ha["body_ratio"])
    last_open = _last(ha["ha_open"])
    last_ha_close = _last(ha_close)
    last_ha_high = _last(ha["ha_high"])
    last_ha_low = _last(ha["ha_low"])
    last_upper_wick = _last(ha["upper_wick"])
    last_lower_wick = _last(ha["lower_wick"])
    ema9_value, ema21_value, ema50_value = _last(ema9), _last(ema21), _last(ema50)
    ema21_slope = (_last(ema21) - float(ema21.iloc[-4])) if len(ema21) >= 4 and pd.notna(ema21.iloc[-4]) else 0.0
    ema50_slope = (_last(ema50) - float(ema50.iloc[-4])) if len(ema50) >= 4 and pd.notna(ema50.iloc[-4]) else 0.0
    trend_up = (
        ema9_value > ema21_value > ema50_value
        and ema21_slope > 0
        and _last(plus_di) > _last(minus_di)
        and current_adx >= 17
    )
    trend_down = (
        ema9_value < ema21_value < ema50_value
        and ema21_slope < 0
        and _last(minus_di) > _last(plus_di)
        and current_adx >= 17
    )
    trend_direction = 1 if trend_up else -1 if trend_down else 0

    higher_seconds = {60: 300, 300: 900, 900: 3600}[interval]
    higher_rows = _resample_context(data, higher_seconds, current_time)
    higher_direction = _context_direction(higher_rows)
    higher_label = {1: "ALTA", -1: "BAIXA", 0: "NEUTRO"}[higher_direction]

    previous = data.iloc[-31:-1]
    support = float(previous["low"].min()) if len(previous) else float(data["low"].iloc[-1])
    resistance = float(previous["high"].max()) if len(previous) else float(data["high"].iloc[-1])
    tolerance = max(atr_value * 0.38, price * 0.00005)
    near_support = abs(float(data["low"].iloc[-1]) - support) <= tolerance or (
        float(data["low"].iloc[-1]) <= support + tolerance and float(data["close"].iloc[-1]) > support
    )
    near_resistance = abs(float(data["high"].iloc[-1]) - resistance) <= tolerance or (
        float(data["high"].iloc[-1]) >= resistance - tolerance and float(data["close"].iloc[-1]) < resistance
    )

    range_mean = float((data["high"] - data["low"]).tail(30).mean())
    range_std = float((data["high"] - data["low"]).tail(30).std(ddof=0) or 0.0)
    market_sideways = current_adx < 14.5 or (current_adx < 18 and abs(ema21_slope) <= max(atr_value * 0.035, 1e-12))
    market_volatile = volatility_ratio >= 2.8 or (
        range_mean > 0 and range_std > range_mean * 1.8 and current_adx < 18
    )
    regime = "SIDEWAYS" if market_sideways else "VOLATILE" if market_volatile else "TREND" if trend_direction else "TRANSITION"
    regime_label = {
        "SIDEWAYS": "MERCADO LATERAL",
        "VOLATILE": "VOLATILIDADE ELEVADA",
        "TREND": "TENDÊNCIA ATIVA",
        "TRANSITION": "TRANSIÇÃO DE TENDÊNCIA",
    }[regime]

    distance_atr = abs(price - ema21_value) / max(atr_value, 1e-12)
    extension_ok = distance_atr <= 2.15
    bullish_wick_ok = last_lower_wick <= max(abs(last_ha_close - last_open) * 1.25, atr_value * 0.06)
    bearish_wick_ok = last_upper_wick <= max(abs(last_ha_close - last_open) * 1.25, atr_value * 0.06)
    bullish_sequence = last_color == 1 and sum(1 for value in colors3 if value == 1) >= 2
    bearish_sequence = last_color == -1 and sum(1 for value in colors3 if value == -1) >= 2
    bullish_turn = last_color == 1 and previous_color <= 0 and (
        last_ha_close > _last(ha["ha_high"].shift(1)) or last_body >= 0.42
    )
    bearish_turn = last_color == -1 and previous_color >= 0 and (
        last_ha_close < _last(ha["ha_low"].shift(1)) or last_body >= 0.42
    )

    candidates: list[tuple[float, int, str, list[str]]] = []
    reasons: list[str] = []
    if market_sideways:
        reasons.append("ADX/estrutura indicam mercado lateral; a ferramenta evita forçar uma entrada.")
    if market_volatile:
        reasons.append("Volatilidade fora do padrão recente; aguarde o mercado estabilizar.")
    if not extension_ok:
        reasons.append("Preço muito afastado da EMA 21 em relação ao ATR; risco de entrada atrasada.")
    if higher_direction not in (0, trend_direction) and trend_direction:
        reasons.append("O contexto do timeframe superior está contrário à tendência principal.")

    if strategy in ("auto", "trend"):
        for direction, enabled, sequence, wick_ok, momentum_ok, di_ok in (
            (1, trend_up, bullish_sequence, bullish_wick_ok, current_macd > 0, _last(plus_di) > _last(minus_di)),
            (-1, trend_down, bearish_sequence, bearish_wick_ok, current_macd < 0, _last(minus_di) > _last(plus_di)),
        ):
            if not enabled:
                continue
            trigger = sequence and last_body >= 0.18 and wick_ok and (
                (direction == 1 and last_ha_close > _previous(ha_close))
                or (direction == -1 and last_ha_close < _previous(ha_close))
            )
            if not trigger:
                continue
            if direction == 1:
                rsi_ok = 48 <= current_rsi <= 74 and current_rsi >= previous_rsi - 2.0
                htf_ok = higher_direction in (0, 1)
                score = (
                    20 * 1.0
                    + 16 * min(current_adx / 30.0, 1.0)
                    + 18 * (1.0 if sequence else 0.0)
                    + 12 * (1.0 if momentum_ok else 0.0)
                    + 10 * (1.0 if rsi_ok else 0.0)
                    + 14 * (1.0 if htf_ok else 0.0)
                    + 10 * (1.0 if extension_ok else 0.0)
                )
            else:
                rsi_ok = 26 <= current_rsi <= 52 and current_rsi <= previous_rsi + 2.0
                htf_ok = higher_direction in (0, -1)
                score = (
                    20 * 1.0
                    + 16 * min(current_adx / 30.0, 1.0)
                    + 18 * (1.0 if sequence else 0.0)
                    + 12 * (1.0 if momentum_ok else 0.0)
                    + 10 * (1.0 if rsi_ok else 0.0)
                    + 14 * (1.0 if htf_ok else 0.0)
                    + 10 * (1.0 if extension_ok else 0.0)
                )
            details = ["Tendência alinhada nas EMA 9/21/50", "ADX e DI confirmam a direção",
                       "Sequência Heikin-Ashi e corpo da vela confirmados"]
            if not momentum_ok:
                details.append("MACD não confirmou o impulso")
            if not rsi_ok:
                details.append("RSI fora da faixa de continuação saudável")
            if not htf_ok:
                details.append("Timeframe superior não confirmou a direção")
            if not extension_ok:
                details.append("Preço estendido em relação à EMA 21")
            candidates.append((float(score), direction, "trend", details))

    if strategy in ("auto", "reversal") and not market_sideways and not market_volatile:
        for direction, zone_ok, turned, wick_rejection, rsi_turn, momentum_turn, context_ok in (
            (
                1, near_support, bullish_turn,
                last_lower_wick > max(last_upper_wick * 1.15, atr_value * 0.10),
                current_rsi > previous_rsi + 1.0 and current_rsi < 58,
                current_macd > previous_macd,
                higher_direction in (0, 1),
            ),
            (
                -1, near_resistance, bearish_turn,
                last_upper_wick > max(last_lower_wick * 1.15, atr_value * 0.10),
                current_rsi < previous_rsi - 1.0 and current_rsi > 42,
                current_macd < previous_macd,
                higher_direction in (0, -1),
            ),
        ):
            trend_was_opposite = (direction == 1 and (trend_down or sum(v == -1 for v in colors4) >= 3)) or (
                direction == -1 and (trend_up or sum(v == 1 for v in colors4) >= 3)
            )
            if not (zone_ok and turned and (wick_rejection or trend_was_opposite) and rsi_turn and momentum_turn):
                continue
            score = (
                22 * (1.0 if zone_ok else 0.0)
                + 22 * (1.0 if turned else 0.0)
                + 15 * (1.0 if wick_rejection or trend_was_opposite else 0.0)
                + 14 * (1.0 if rsi_turn else 0.0)
                + 12 * (1.0 if momentum_turn else 0.0)
                + 10 * (1.0 if context_ok else 0.0)
                + 5 * (1.0 if extension_ok else 0.0)
            )
            details = ["Preço em região técnica de suporte/resistência", "Virada de cor e rompimento da máxima/mínima Heikin-Ashi",
                       "RSI e MACD começaram a confirmar a reversão"]
            if not context_ok:
                details.append("Timeframe superior contrário; reversão bloqueada")
            candidates.append((float(score), direction, "reversal", details))

    next_candle_at = float(data["time"].iloc[-1]) + interval
    entry_lag = max(0.0, current_time - next_candle_at)
    entry_window_seconds = min(30.0, max(12.0, interval * 0.08))
    entry_window_open = entry_lag <= entry_window_seconds
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)

    selected = candidates[0] if candidates else None
    direction = selected[1] if selected and selected[0] >= MIN_SIGNAL_SCORE else 0
    selected_strategy = selected[2] if selected and direction else "none"
    score = selected[0] if selected and direction else (selected[0] if selected else 0.0)
    if direction and (market_sideways or market_volatile or not extension_ok):
        direction = 0
        selected_strategy = "none"
        reasons.append("Os filtros de proteção bloquearam o sinal, apesar de existir confluência direcional.")
    if direction and not entry_window_open:
        direction = 0
        selected_strategy = "none"
        reasons.append("A janela para entrada na abertura da próxima vela já passou. Aguarde o próximo gatilho.")

    direction_label = {1: "CALL", -1: "PUT", 0: "NONE"}[direction]
    signal_label = {
        1: "COMPRA · CALL",
        -1: "VENDA · PUT",
        0: "AGUARDAR",
    }[direction]
    strategy_label = {
        "trend": "Continuação de tendência",
        "reversal": "Reversão confirmada",
        "none": "Sem configuração válida",
    }[selected_strategy]

    indicator_direction = trend_direction
    indicators = [
        {"name": "EMA Heikin-Ashi 9/21/50", "group": "Tendência", "direction": indicator_direction,
         "active": bool(indicator_direction and direction == indicator_direction),
         "detail": "Alinhamento e inclinação das médias"},
        {"name": "ADX + DI", "group": "Força", "direction": 1 if _last(plus_di) > _last(minus_di) else -1 if _last(minus_di) > _last(plus_di) else 0,
         "active": bool(current_adx >= 17 and direction and ((direction == 1 and _last(plus_di) > _last(minus_di)) or (direction == -1 and _last(minus_di) > _last(plus_di)))),
         "detail": "ADX " + str(round(current_adx, 1)) + " · mede força, não direção"},
        {"name": "MACD Heikin-Ashi", "group": "Momentum", "direction": 1 if current_macd > 0 else -1 if current_macd < 0 else 0,
         "active": bool(direction and ((direction == 1 and current_macd > 0) or (direction == -1 and current_macd < 0))),
         "detail": "Histograma " + ("positivo" if current_macd > 0 else "negativo" if current_macd < 0 else "neutro")},
        {"name": "RSI 14", "group": "Momentum", "direction": 1 if current_rsi > 52 else -1 if current_rsi < 48 else 0,
         "active": bool(direction and ((direction == 1 and current_rsi > 48) or (direction == -1 and current_rsi < 52))),
         "detail": "RSI " + str(round(current_rsi, 1))},
        {"name": "Sequência Heikin-Ashi", "group": "Gatilho", "direction": last_color,
         "active": bool(direction and last_color == direction and last_body >= 0.18),
         "detail": str(sum(1 for value in colors3 if value == last_color and value != 0)) + " de 3 velas na direção atual"},
        {"name": "Contexto superior", "group": "Confirmação", "direction": higher_direction,
         "active": bool(direction and higher_direction in (0, direction)),
         "detail": higher_label + " · timeframe " + {60: "M5", 300: "M15", 900: "H1"}[interval]},
        {"name": "Suporte / resistência", "group": "Estrutura", "direction": 1 if near_support else -1 if near_resistance else 0,
         "active": bool(selected_strategy == "reversal" and direction and ((direction == 1 and near_support) or (direction == -1 and near_resistance))),
         "detail": "Zona monitorada com tolerância baseada no ATR"},
        {"name": "Filtro ATR", "group": "Proteção", "direction": 0,
         "active": bool(direction and extension_ok and not market_volatile),
         "detail": "ATR " + str(round(atr_percent, 4)) + "% · extensão " + str(round(distance_atr, 2)) + " ATR"},
    ]

    if not candidates:
        reasons.append("Nenhum gatilho Heikin-Ashi de continuação ou reversão foi confirmado.")
    elif selected and selected[0] < MIN_SIGNAL_SCORE:
        reasons.append("Confluência abaixo do mínimo de " + str(int(MIN_SIGNAL_SCORE)) + " pontos.")
    if not reasons and direction:
        reasons.append("Confluência aprovada: aguarde apenas a abertura da próxima vela para avaliar a entrada.")
    if not reasons:
        reasons.append("Sem confirmação suficiente. Não entre por antecipação; aguarde novo fechamento.")

    chart = []
    for index in range(max(0, len(data) - CHART_CANDLES), len(data)):
        chart.append({
            "time": int(data["time"].iloc[index]),
            "open": _round(float(ha["ha_open"].iloc[index])),
            "high": _round(float(ha["ha_high"].iloc[index])),
            "low": _round(float(ha["ha_low"].iloc[index])),
            "close": _round(float(ha["ha_close"].iloc[index])),
            "color": int(ha["color"].iloc[index]),
        })

    expiry_at = next_candle_at + interval
    entry_window_ends_at = next_candle_at + entry_window_seconds
    return {
        "ok": True,
        "timeframe": timeframe,
        "expiryMinutes": int(interval / 60),
        "direction": direction_label,
        "signal": signal_label,
        "score": round(float(score), 1),
        "minSignalScore": MIN_SIGNAL_SCORE,
        "strategy": selected_strategy,
        "strategyLabel": strategy_label,
        "marketRegime": regime,
        "marketRegimeLabel": regime_label,
        "higherTimeframe": {60: "M5", 300: "M15", 900: "H1"}[interval],
        "higherDirection": higher_label,
        "adx": round(current_adx, 1),
        "rsi": round(current_rsi, 1),
        "atrPercent": round(atr_percent, 4),
        "distanceToEmaAtr": round(distance_atr, 2),
        "referencePrice": _round(price),
        "entryAt": int(next_candle_at),
        "entryWindowEndsAt": int(entry_window_ends_at),
        "entryWindowOpen": bool(entry_window_open),
        "entryLagSeconds": round(entry_lag, 1),
        "expiryAt": int(expiry_at),
        "candlesAnalyzed": len(data),
        "indicators": indicators,
        "blockingReasons": list(dict.fromkeys(reasons)),
        "details": selected[3] if selected and direction else [],
        "candles": chart,
        "analysisNote": "Pontuação representa confluência técnica, não probabilidade estatística de vitória.",
    }
