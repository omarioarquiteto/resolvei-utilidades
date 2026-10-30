"""Motor estatístico de seleção de strikes digitais para ALTOS LUCROS.

A probabilidade é estimada por janelas históricas não sobrepostas. Um acerto
exige fechamento além do strike no horizonte, não apenas toque intraperíodo.
"""
from __future__ import annotations

from math import isfinite, sqrt
from statistics import NormalDist
from typing import Any

SUPPORTED_HORIZONS = {5, 15}
MINIMUM_PAYOUT_PERCENT = 200.0
MINIMUM_SAMPLES = 30
MAX_HISTORY_CANDLES = 1000
WILSON_Z_90 = 1.6448536269514722


def _clean_candles(rows: list[dict[str, Any]]) -> list[dict[str, float]]:
    cleaned: dict[int, dict[str, float]] = {}
    for row in rows:
        try:
            timestamp = int(float(row.get("time", row.get("from", 0))))
            opened = float(row["open"])
            high = float(row.get("high", row.get("max")))
            low = float(row.get("low", row.get("min")))
            close = float(row["close"])
        except (TypeError, ValueError, KeyError):
            continue
        if timestamp <= 0 or min(opened, high, low, close) <= 0:
            continue
        if high < low or high < max(opened, close) or low > min(opened, close):
            continue
        cleaned[timestamp] = {
            "time": float(timestamp),
            "open": opened,
            "high": high,
            "low": low,
            "close": close,
        }
    return [cleaned[key] for key in sorted(cleaned)][-MAX_HISTORY_CANDLES:]


def _wilson_interval(successes: int, samples: int, z: float = WILSON_Z_90) -> tuple[float, float]:
    if samples <= 0:
        return 0.0, 0.0
    p = successes / samples
    z2 = z * z
    denominator = 1.0 + z2 / samples
    center = (p + z2 / (2.0 * samples)) / denominator
    margin = z * sqrt((p * (1.0 - p) / samples) + (z2 / (4.0 * samples * samples))) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _read_payout(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("profit", "payout", "return", "rate"):
            if key in value:
                return _read_payout(value.get(key))
        return None
    try:
        payout = float(value)
    except (TypeError, ValueError):
        return None
    return payout if isfinite(payout) and payout > 0 else None


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _historical_probability(
    candles: list[dict[str, float]],
    relative_distance: float,
    direction: str,
    horizon: int,
) -> tuple[int, int]:
    """Mede fechamento além do strike em janelas históricas não sobrepostas."""
    successes = 0
    samples = 0
    for start in range(0, len(candles) - horizon, horizon):
        end = start + horizon
        # Descarta intervalos com candles ausentes ou lacunas de mercado.
        elapsed = candles[end]["time"] - candles[start]["time"]
        if abs(elapsed - horizon * 60) > 20:
            continue
        entry = candles[start]["close"]
        expiry_close = candles[end]["close"]
        historical_target = entry * (1.0 + relative_distance)
        samples += 1
        if direction == "ACIMA" and expiry_close >= historical_target:
            successes += 1
        elif direction == "ABAIXO" and expiry_close <= historical_target:
            successes += 1
    return successes, samples


def analyze_targets(
    rows: list[dict[str, Any]],
    strike_quotes: dict[str, Any],
    horizon_minutes: int,
    minimum_payout: float = MINIMUM_PAYOUT_PERCENT,
    reference_price: float | None = None,
) -> dict[str, Any]:
    if horizon_minutes not in SUPPORTED_HORIZONS:
        raise ValueError("O vencimento deve ser de 5 ou 15 minutos.")
    if minimum_payout < MINIMUM_PAYOUT_PERCENT:
        raise ValueError("O payout mínimo não pode ser inferior a 200%.")

    candles = _clean_candles(rows)
    required = horizon_minutes * (MINIMUM_SAMPLES + 1) + 1
    if len(candles) < required:
        raise ValueError(
            f"Histórico insuficiente: {len(candles)} candles M1. "
            f"São necessários pelo menos {required} candles fechados para "
            f"avaliar janelas de {horizon_minutes} minutos."
        )
    if not isinstance(strike_quotes, dict) or not strike_quotes:
        raise ValueError("A IQ Option não disponibilizou a grade de strikes digitais.")

    closes = [row["close"] for row in candles]
    try:
        live_reference = float(reference_price) if reference_price is not None else 0.0
    except (TypeError, ValueError):
        live_reference = 0.0
    current_price = live_reference if isfinite(live_reference) and live_reference > 0 else closes[-1]
    ema20 = _ema(closes[-80:], 20)
    ema50 = _ema(closes[-160:], 50)
    bias = "ALTA" if ema20 > ema50 * 1.00005 else "BAIXA" if ema20 < ema50 * 0.99995 else "NEUTRA"

    eligible: list[tuple[float, str, str, float]] = []
    for raw_strike, sides in strike_quotes.items():
        try:
            strike = float(raw_strike)
        except (TypeError, ValueError):
            continue
        if not isfinite(strike) or strike <= 0 or not isinstance(sides, dict):
            continue

        for side, direction in (("call", "ACIMA"), ("put", "ABAIXO")):
            if direction == "ACIMA" and strike <= current_price:
                continue
            if direction == "ABAIXO" and strike >= current_price:
                continue
            payout = _read_payout(sides.get(side))
            if payout is not None and payout + 1e-9 >= minimum_payout:
                eligible.append((strike, direction, side.upper(), payout))

    # Corrige a seleção entre vários strikes testados simultaneamente.
    # O limite inferior de 90% permanece conservador após procurar o melhor alvo.
    comparisons = max(1, len(eligible))
    adjusted_z = NormalDist().inv_cdf(1.0 - 0.10 / (2.0 * comparisons))

    candidates: list[dict[str, Any]] = []
    for strike, direction, side, payout in eligible:
        relative_distance = strike / current_price - 1.0
        successes, samples = _historical_probability(
            candles, relative_distance, direction, horizon_minutes
        )
        if samples < MINIMUM_SAMPLES:
            continue

        probability = successes / samples
        low, high = _wilson_interval(successes, samples, z=adjusted_z)
        breakeven = 100.0 / (100.0 + payout)
        edge = low - breakeven
        conservative_ev = low * payout - (1.0 - low) * 100.0
        candidates.append({
            "direction": direction,
            "side": side,
            "target_price": round(strike, 8),
            "payout_percent": round(payout, 2),
            "distance_percent": round(abs(relative_distance) * 100.0, 4),
            "samples": samples,
            "successes": successes,
            "probability_percent": round(probability * 100.0, 1),
            "confidence_low_percent": round(low * 100.0, 1),
            "confidence_high_percent": round(high * 100.0, 1),
            "confidence_level_percent": 90,
            "breakeven_probability_percent": round(breakeven * 100.0, 1),
            "edge_lower_bound_pp": round(edge * 100.0, 1),
            "conservative_expected_value_percent": round(conservative_ev, 1),
            "statistically_valid": bool(edge >= 0.05 and conservative_ev > 0),
        })

    candidates.sort(
        key=lambda item: (
            item["conservative_expected_value_percent"],
            item["confidence_low_percent"],
            item["payout_percent"],
            -item["distance_percent"],
        ),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    recommendation = next((item for item in candidates if item["statistically_valid"]), None)

    if recommendation:
        status = "ALVO_VALIDADO"
        message = (
            "Há um strike com payout mínimo de 200% cuja estimativa histórica "
            "conservadora supera o ponto de equilíbrio com margem estatística."
        )
    elif best:
        status = "SEM_OPORTUNIDADE"
        message = (
            "A grade contém strikes com payout de 200% ou mais, mas nenhum "
            "superou o ponto de equilíbrio com a margem estatística exigida."
        )
    elif eligible:
        status = "HISTORICO_INSUFICIENTE"
        message = (
            "Há strikes com payout de 200% ou mais, mas os candles válidos "
            "não formaram 30 janelas completas do vencimento selecionado."
        )
    else:
        status = "SEM_STRIKE_200"
        message = (
            "A IQ Option não disponibilizou strikes elegíveis com payout de "
            "pelo menos 200% para este ativo e vencimento."
        )

    return {
        "status": status,
        "message": message,
        "symbol_price": round(current_price, 8),
        "reference_price_source": "live_m1" if live_reference > 0 and isfinite(live_reference) else "last_closed_m1",
        "horizon_minutes": horizon_minutes,
        "minimum_payout_percent": round(minimum_payout, 2),
        "market_bias": bias,
        "ema20": round(ema20, 8),
        "ema50": round(ema50, 8),
        "historical_samples": best["samples"] if best else max(0, (len(candles) - 1) // horizon_minutes),
        "recommendation": recommendation,
        "best_candidate": best,
        "candidates": candidates[:8],
        "method": {
            "candle_timeframe": "1m",
            "outcome_rule": "Fechamento do candle no vencimento além do strike",
            "sample_windows": "Não sobrepostas",
            "confidence_level_percent": 90,
            "confidence_adjustment": "Bonferroni",
            "tested_strikes": comparisons,
            "minimum_samples": MINIMUM_SAMPLES,
            "minimum_edge_percentage_points": 5.0,
        },
        "execution_enabled": False,
    }
