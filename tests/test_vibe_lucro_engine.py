from __future__ import annotations

import unittest

from vibe_lucro_engine import analyze


def make_rows(count: int, now: float, *, slope: float = 0.001, start: float = 1.0, period: int = 60):
    rows = []
    price = start
    base_time = now - count * period - 10
    for index in range(count):
        next_price = price * (1.0 + slope)
        rows.append({
            "open": price,
            "high": max(price, next_price) * 1.0002,
            "low": min(price, next_price) * 0.9998,
            "close": next_price,
            "volume": 100.0,
            "datetime": base_time + index * period,
        })
        price = next_price
    return rows


class TestVibeLucroEngine(unittest.TestCase):
    def test_aligned_bullish_timeframes_return_call(self):
        now = 1_800_000_000.0
        frames = {
            "1m": make_rows(220, now, slope=0.0004, period=60),
            "5m": make_rows(160, now, slope=0.0015, period=300),
            "15m": make_rows(110, now, slope=0.003, period=900),
        }
        result = analyze(frames, "EURUSD", 1, now=now)
        self.assertEqual(result["signal"], "CALL")
        self.assertGreaterEqual(result["buy_score"], 72)
        self.assertTrue(result["data_quality"]["fresh"])

    def test_stale_timeframes_force_wait(self):
        now = 1_900_000_000.0
        frames = {
            "1m": make_rows(220, now - 100_000, period=60),
            "5m": make_rows(160, now - 100_000, period=300),
            "15m": make_rows(110, now - 100_000, period=900),
        }
        result = analyze(frames, "EURUSD", 5, now=now)
        self.assertEqual(result["signal"], "WAIT")
        self.assertFalse(result["data_quality"]["fresh"])

    def test_unsupported_expiry_is_rejected(self):
        now = 1_800_000_000.0
        frames = {
            "1m": make_rows(220, now, period=60),
            "5m": make_rows(160, now, period=300),
            "15m": make_rows(110, now, period=900),
        }
        with self.assertRaisesRegex(ValueError, "1, 5 ou 15"):
            analyze(frames, "EURUSD", 3, now=now)


if __name__ == "__main__":
    unittest.main()
