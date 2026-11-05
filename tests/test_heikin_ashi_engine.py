import unittest

import numpy as np

from heikin_ashi_engine import MIN_CANDLES, analyze, clean, heikin_ashi


def make_candles(count=320, mode="up", interval=60):
    rows = []
    for index in range(count):
        if mode == "flat":
            middle = 100.0
            opening = middle
            closing = middle
        elif mode == "down":
            middle = 120.0 - index * 0.025 + np.sin(index / 4) * 0.008
            opening = middle + 0.01
            closing = middle - 0.01
        else:
            middle = 100.0 + index * 0.025 + np.sin(index / 4) * 0.008
            opening = middle - 0.01
            closing = middle + 0.01
        rows.append({
            "time": 1_700_000_040 + index * interval,
            "open": opening,
            "high": max(opening, closing) + 0.08,
            "low": min(opening, closing) - 0.08,
            "close": closing,
        })
    return rows


class HeikinAshiEngineTests(unittest.TestCase):
    def test_heikin_ashi_uses_recursive_open_and_ohlc_average(self):
        data = clean(make_candles(count=5))
        ha = heikin_ashi(data)
        self.assertAlmostEqual(float(ha["ha_close"].iloc[0]), (
            data["open"].iloc[0] + data["high"].iloc[0] + data["low"].iloc[0] + data["close"].iloc[0]
        ) / 4.0)
        self.assertAlmostEqual(float(ha["ha_open"].iloc[1]), (
            ha["ha_open"].iloc[0] + ha["ha_close"].iloc[0]
        ) / 2.0)
        self.assertTrue((ha["ha_high"] >= ha[["ha_open", "ha_close"]].max(axis=1)).all())
        self.assertTrue((ha["ha_low"] <= ha[["ha_open", "ha_close"]].min(axis=1)).all())

    def test_flat_market_does_not_force_a_direction(self):
        candles = make_candles(mode="flat")
        result = analyze(candles, "1m", "auto", candles[-1]["time"] + 60)
        self.assertEqual(result["direction"], "NONE")
        self.assertEqual(result["signal"], "AGUARDAR")
        self.assertTrue(result["blockingReasons"])

    def test_expiration_supports_one_five_and_fifteen_minutes(self):
        for timeframe, interval in (("1m", 60), ("5m", 300), ("15m", 900)):
            candles = make_candles(interval=interval)
            result = analyze(candles, timeframe, "auto", candles[-1]["time"] + interval)
            self.assertEqual(result["expiryMinutes"], interval // 60)
            self.assertEqual(result["expiryAt"] - result["entryAt"], interval)

    def test_incomplete_history_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "insuficientes"):
            analyze(make_candles(count=MIN_CANDLES - 1), "1m", "auto")

    def test_late_entry_window_is_not_recommended(self):
        candles = make_candles()
        now = candles[-1]["time"] + 60 + 60
        result = analyze(candles, "1m", "auto", now)
        self.assertFalse(result["entryWindowOpen"])

    def test_chart_contains_heikin_ashi_candles(self):
        candles = make_candles()
        result = analyze(candles, "1m", "auto", candles[-1]["time"] + 60)
        ha = heikin_ashi(clean(candles))
        self.assertGreater(len(result["candles"]), 0)
        self.assertIn("ha_open", ha.columns)
        self.assertAlmostEqual(result["candles"][-1]["open"], float(ha["ha_open"].iloc[-1]), places=5)


if __name__ == "__main__":
    unittest.main()
