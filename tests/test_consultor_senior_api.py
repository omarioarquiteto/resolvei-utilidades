import time
import unittest

from consultor_senior_api import _chart_frames, _entry_confirmed, _entry_trigger, _sanitize_analysis


def make_candles(count=120, interval=60, stale=False, final_engulfing=False):
    now = time.time() - (600 if stale else 60)
    rows = []
    for index in range(count):
        opening = 100.0 + index * 0.05
        close = opening + 0.03
        rows.append({
            "time": now - (count - index - 1) * interval,
            "open": opening,
            "high": close + 0.02,
            "low": opening - 0.02,
            "close": close,
            "volume": 100.0,
        })

    if final_engulfing:
        rows[-2].update({
            "open": 105.92,
            "high": 105.94,
            "low": 105.86,
            "close": 105.88,
        })
        rows[-1].update({
            "open": 105.87,
            "high": 105.96,
            "low": 105.85,
            "close": 105.94,
        })

    return rows


class ConsultorSeniorSignalTests(unittest.TestCase):
    def test_expiration_is_always_five_minutes(self):
        result = _sanitize_analysis({
            "decision": "CALL",
            "status": "AGORA",
            "confidence": 80,
            "timeframe": "15m",
            "expiry_minutes": 30,
            "data_quality": "boa",
        })
        self.assertEqual(result["timeframe"], "1m")
        self.assertEqual(result["expiry_minutes"], 5)

    def test_detects_bullish_engulfing_on_closed_one_minute_candle(self):
        candles = make_candles(final_engulfing=True)
        self.assertIn("engolfo comprador", _entry_trigger(candles, "CALL"))
        self.assertIsNone(_entry_trigger(candles, "PUT"))

    def test_confirmed_signal_requires_aligned_trend_and_recent_trigger(self):
        frames = {
            "1m": make_candles(interval=60, final_engulfing=True),
            "5m": make_candles(interval=300),
            "15m": make_candles(interval=900),
        }
        analysis = {
            "decision": "CALL",
            "status": "AGORA",
            "confidence": 80,
            "timeframe": "1m",
            "expiry_minutes": 5,
            "trigger": "Engolfo comprador no candle fechado de 1m",
            "data_quality": "boa",
        }
        self.assertTrue(_entry_confirmed(analysis, frames, "EURUSD"))

    def test_rejects_stale_one_minute_candles(self):
        frames = {
            "1m": make_candles(interval=60, stale=True, final_engulfing=True),
            "5m": make_candles(interval=300),
            "15m": make_candles(interval=900),
        }
        analysis = {
            "decision": "CALL",
            "status": "AGORA",
            "confidence": 80,
            "timeframe": "1m",
            "expiry_minutes": 5,
            "trigger": "Engolfo comprador no candle fechado de 1m",
            "data_quality": "boa",
        }
        self.assertFalse(_entry_confirmed(analysis, frames, "EURUSD"))

    def test_single_consult_snapshot_contains_all_chart_timeframes(self):
        frames = {
            "1m": make_candles(interval=60),
            "5m": make_candles(interval=300),
            "15m": make_candles(interval=900),
        }
        snapshot = _chart_frames(frames)
        self.assertEqual(set(snapshot), {"1m", "5m", "15m"})
        for timeframe, expected_limit in (("1m", 110), ("5m", 90), ("15m", 70)):
            self.assertIn("summary", snapshot[timeframe])
            self.assertIn("candles", snapshot[timeframe])
            self.assertEqual(len(snapshot[timeframe]["candles"]), expected_limit)



if __name__ == "__main__":
    unittest.main()
