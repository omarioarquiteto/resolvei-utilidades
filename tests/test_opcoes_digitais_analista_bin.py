import unittest
from unittest.mock import patch

from analista_bin_engine import analyze as analyze_analista_bin
from opcoes_digitais_analista_bin import analyze_opcoes_signal


def make_candles(count=320):
    rows = []
    for index in range(count):
        close = 100.0 + index * 0.1
        opening = close - 0.02
        rows.append({
            "time": 1_700_000_040 + index * 60,
            "open": opening,
            "high": close + 0.02,
            "low": opening - 0.02,
            "close": close,
            "volume": 100 + (index % 7),
        })
    return rows


def fake_result(strategy, direction, score):
    names = [f"Indicador {index}" for index in range(10)]
    indicators = [
        {
            "name": name,
            "weight": 10,
            "direction": 1 if direction == "CALL" else -1 if direction == "PUT" else 0,
            "active": direction in ("CALL", "PUT"),
        }
        for name in names
    ]
    return {
        "strategy": strategy,
        "strategyLabel": strategy.title(),
        "direction": direction,
        "score": score,
        "signal": "SINAL MODERADO" if direction in ("CALL", "PUT") else "SEM SINAL",
        "callScore": score if direction == "CALL" else 0,
        "putScore": score if direction == "PUT" else 0,
        "indicators": indicators,
    }


class OpcoesDigitaisAnalistaBinTests(unittest.TestCase):
    def test_manual_strategy_uses_the_same_engine_scores(self):
        candles = make_candles()
        expected = analyze_analista_bin(candles, "trend")
        actual = analyze_opcoes_signal(candles, "trend")

        self.assertEqual(actual["engine"], "Analista Bin")
        self.assertEqual(actual["strategy"], expected["strategy"])
        self.assertEqual(actual["direction"], expected["direction"])
        self.assertEqual(actual["score"], expected["score"])
        self.assertEqual(actual["callScore"], expected["callScore"])
        self.assertEqual(actual["putScore"], expected["putScore"])
        self.assertEqual(
            [(item["name"], item["weight"], item["direction"]) for item in actual["indicators"]],
            [(item["name"], item["weight"], item["direction"]) for item in expected["indicators"]],
        )

    def test_auto_evaluates_all_three_analista_bin_strategies(self):
        candles = make_candles()
        result = analyze_opcoes_signal(candles, "auto")

        self.assertEqual(result["requestedStrategy"], "auto")
        self.assertEqual(result["engine"], "Analista Bin")
        self.assertEqual(len(result["strategyCandidates"]), 3)
        self.assertEqual(
            {item["strategy"] for item in result["strategyCandidates"]},
            {"trend", "breakout", "reversion"},
        )

    def test_auto_blocks_close_opposing_signals(self):
        candles = make_candles()
        mocked = {
            "trend": fake_result("trend", "CALL", 76),
            "breakout": fake_result("breakout", "PUT", 70),
            "reversion": fake_result("reversion", "NONE", 48),
        }

        with patch(
            "opcoes_digitais_analista_bin.analyze_analista_bin",
            side_effect=lambda rows, strategy: mocked[strategy],
        ):
            result = analyze_opcoes_signal(candles, "auto")

        self.assertEqual(result["direction"], "NONE")
        self.assertEqual(result["signal"], "SEM SINAL")
        self.assertTrue(any("direções opostas" in reason for reason in result["blockingReasons"]))
        self.assertFalse(any(item["active"] for item in result["indicators"]))


if __name__ == "__main__":
    unittest.main()
