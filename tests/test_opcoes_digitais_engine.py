import unittest

import numpy as np

from opcoes_digitais_engine import (
    GROUP_WEIGHTS,
    MIN_CANDLES,
    _ema,
    _parabolic_sar,
    _resample_context,
    _group_support,
    analyze,
    analyze_trend_strength,
    clean,
)


def make_candles(count=320, mode="up", include_volume=True):
    rows = []
    for index in range(count):
        if mode == "flat":
            middle = 100.0
        elif mode == "down":
            middle = 120.0 - index * 0.05 + np.sin(index / 4) * 0.03
        else:
            middle = 100.0 + index * 0.05 + np.sin(index / 4) * 0.03
        opening = middle - 0.015
        closing = middle + 0.015 if mode != "down" else middle - 0.015
        row = {
            "time": 1_700_000_040 + index * 60,
            "open": opening,
            "high": max(opening, closing) + 0.01,
            "low": min(opening, closing) - 0.01,
            "close": closing,
        }
        if include_volume:
            row["volume"] = 90 + (index % 9) * 7
        rows.append(row)
    return rows


class OpcoesDigitaisEngineTests(unittest.TestCase):
    def test_rejects_insufficient_closed_candles(self):
        with self.assertRaisesRegex(ValueError, "insuficientes"):
            analyze(make_candles(MIN_CANDLES - 1), "auto", "1m")

    def test_clean_does_not_invent_volume(self):
        cleaned = clean(make_candles(include_volume=False))
        self.assertTrue(cleaned["volume"].isna().all())

    def test_parabolic_sar_is_not_an_ema_substitute(self):
        rows = make_candles()
        cleaned = clean(rows)
        sar = _parabolic_sar(cleaned["high"], cleaned["low"])
        ema = _ema(cleaned["close"], 5)
        self.assertTrue(np.isfinite(sar.iloc[-1]))
        self.assertNotAlmostEqual(float(sar.iloc[-1]), float(ema.iloc[-1]), places=5)

    def test_context_resampling_uses_only_completed_bars(self):
        rows = clean(make_candles())
        now = float(rows["time"].iloc[-1] + 60)
        context = _resample_context(rows, 300, now)
        self.assertGreaterEqual(len(context), 40)
        self.assertTrue(((context["time"] // 300) * 300 + 300 <= now + 0.2).all())

    def test_auto_detects_trending_market_and_reports_groups(self):
        candles = make_candles(mode="up")
        result = analyze(candles, "auto", "1m", candles[-1]["time"] + 60)
        self.assertEqual(result["strategy"], "trend")
        self.assertEqual(result["marketRegime"], "trend")
        self.assertEqual(sum(GROUP_WEIGHTS.values()), 100)
        self.assertIn("groupScores", result)
        self.assertIn("higherDirection", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_trend_radar_detects_very_strong_uptrend(self):
        result = analyze_trend_strength(make_candles(mode="up"))
        self.assertEqual(result["direction"], "CALL")
        self.assertEqual(result["trendLabel"], "ALTA")
        self.assertGreater(result["strength"], 85)
        self.assertLessEqual(result["strength"], 100)

    def test_trend_radar_detects_very_strong_downtrend(self):
        result = analyze_trend_strength(make_candles(mode="down"))
        self.assertEqual(result["direction"], "PUT")
        self.assertEqual(result["trendLabel"], "BAIXA")
        self.assertGreaterEqual(result["strength"], 85)
        self.assertLessEqual(result["strength"], 100)

    def test_trend_radar_does_not_classify_flat_market_as_strong(self):
        result = analyze_trend_strength(make_candles(mode="flat"))
        self.assertEqual(result["direction"], "NONE")
        self.assertLess(result["strength"], 85)

    def test_neutral_indicators_do_not_inflate_group_consensus(self):
        self.assertEqual(_group_support([1, 0, 0, 0], 1), 0.25)
        self.assertEqual(_group_support([1, 1, 0, 0], 1), 0.50)
        self.assertEqual(_group_support([1, -1, 0, 0], 1), 0.25)

    def test_flat_market_does_not_force_a_signal(self):
        candles = make_candles(mode="flat")
        result = analyze(candles, "auto", "1m", candles[-1]["time"] + 60)
        self.assertEqual(result["direction"], "NONE")
        self.assertEqual(result["signal"], "SEM SINAL")
        self.assertTrue(result["blockingReasons"])

    def test_manual_trend_strategy_is_blocked_outside_a_trend(self):
        candles = make_candles(mode="flat")
        result = analyze(candles, "trend", "1m", candles[-1]["time"] + 60)
        self.assertEqual(result["direction"], "NONE")
        self.assertTrue(any("tendência" in reason.lower() for reason in result["blockingReasons"]))

    def test_missing_volume_is_reported_and_not_used(self):
        candles = make_candles(include_volume=False)
        result = analyze(candles, "auto", "1m", candles[-1]["time"] + 60)
        self.assertFalse(result["volumeDataAvailable"])
        self.assertFalse(any(item["name"] == "Fluxo de volume" and item["direction"] != 0 for item in result["indicators"]))

    def test_timeframe_must_be_supported(self):
        with self.assertRaisesRegex(ValueError, "Timeframe"):
            analyze(make_candles(), "auto", "15m")


if __name__ == "__main__":
    unittest.main()
