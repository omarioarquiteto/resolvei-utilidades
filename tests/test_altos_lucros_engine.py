import unittest

from altos_lucros_engine import analyze_targets, _wilson_interval


def rising_candles(count: int = 600):
    rows = []
    start = 1.100000
    for index in range(count):
        close = start + index * 0.0001
        rows.append({
            "time": 1_700_000_000 + index * 60,
            "open": close - 0.00002,
            "high": close + 0.00004,
            "low": close - 0.00004,
            "close": close,
        })
    return rows


class TestAltosLucrosEngine(unittest.TestCase):
    def test_wilson_interval_is_bounded_and_ordered(self):
        low, high = _wilson_interval(40, 50)
        self.assertLessEqual(0, low)
        self.assertLessEqual(low, 0.8)
        self.assertLessEqual(0.8, high)
        self.assertLessEqual(high, 1)

    def test_selects_strike_with_200_percent_or_more_and_positive_edge(self):
        candles = rising_candles()
        current = candles[-1]["close"]
        strike = round(current * 1.00005, 6)
        quotes = {
            str(strike): {
                "call": {"profit": 250.0, "id": "sample-call"},
                "put": {"profit": 180.0, "id": "sample-put"},
            }
        }
        result = analyze_targets(candles, quotes, 5)
        self.assertEqual(result["status"], "ALVO_VALIDADO")
        self.assertEqual(result["recommendation"]["direction"], "ACIMA")
        self.assertEqual(result["recommendation"]["payout_percent"], 250.0)
        self.assertGreaterEqual(result["recommendation"]["samples"], 30)

    def test_does_not_treat_payout_below_200_as_eligible(self):
        candles = rising_candles()
        current = candles[-1]["close"]
        strike = round(current * 1.00005, 6)
        quotes = {str(strike): {"call": {"profit": 199.9}}}
        result = analyze_targets(candles, quotes, 5)
        self.assertEqual(result["status"], "SEM_STRIKE_200")
        self.assertIsNone(result["recommendation"])

    def test_rejects_unsupported_horizon(self):
        with self.assertRaisesRegex(ValueError, "5 ou 15"):
            analyze_targets(rising_candles(), {}, 10)


if __name__ == "__main__":
    unittest.main()
