import unittest

from trade_pro_engine import MIN_CANDLES, analyze


def make_candles(count=120, trend="flat", constant_volume=False):
    rows = []
    close = 100.0
    for index in range(count):
        opening = close
        if trend == "up":
            close += 0.06
        elif trend == "down":
            close -= 0.06
        else:
            close = 100.0
        candle_high = max(opening, close) + 0.025
        candle_low = min(opening, close) - 0.025
        volume = 100.0 if constant_volume else 90.0 + (index % 7) * 6.0
        rows.append({
            "time": index * 60,
            "open": opening,
            "high": candle_high,
            "low": candle_low,
            "close": close,
            "volume": volume,
        })
    return rows


class TradeProEngineTests(unittest.TestCase):
    def test_rejects_insufficient_candles(self):
        with self.assertRaisesRegex(ValueError, "insuficientes"):
            analyze(make_candles(MIN_CANDLES - 1), "1m")

    def test_never_returns_an_unsupported_signal(self):
        for trend in ("flat", "up", "down"):
            result = analyze(make_candles(trend=trend), "1m")
            self.assertIn(result["signal"], (None, "COMPRA", "VENDA"))

    def test_constant_volume_is_not_confirmed(self):
        result = analyze(make_candles(trend="up", constant_volume=True), "1m")
        self.assertFalse(result["market"]["volume_data_available"])
        self.assertIsNone(result["signal"])
        self.assertEqual(result["status"], "SEM_SINAL")

    def test_timeframe_must_be_supported(self):
        with self.assertRaisesRegex(ValueError, "Timeframe"):
            analyze(make_candles(), "30m")


if __name__ == "__main__":
    unittest.main()
