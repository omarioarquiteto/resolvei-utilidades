import json
import unittest

from trade_pro_ai import build_trade_pro_ai_prompt, parse_trade_pro_ai_response


def base_analysis(signal="COMPRA", stale=False):
    return {
        "symbol": "EURUSD",
        "timeframe": "1m",
        "candle_time": 123456,
        "signal": signal,
        "status": "SINAL_VALIDADO" if signal else "SEM_SINAL",
        "regime": "ALTISTA",
        "reason": "Tendência confirmada.",
        "confluence": 88.5,
        "threshold": 72,
        "expiration_minutes": 1 if signal else None,
        "market": {"adx": 27.1, "atr_ratio": 1.1, "volume_ratio": 1.4},
        "scores": {"trend": 90, "volume": 85, "volatility": 82},
        "checks": {
            "trend_confirmed": bool(signal),
            "volume_confirmed": bool(signal),
            "volatility_confirmed": bool(signal),
            "confluence_confirmed": bool(signal),
        },
        "blocking_reasons": [] if signal else ["Volume não confirmado."],
        "data_quality": {"stale": stale, "last_candle_age_seconds": 4},
        "recent_candles": [
            {"time": 60, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 120}
        ],
    }


def response(direction="COMPRA"):
    return json.dumps({
        "recommendation": direction,
        "confidence": 86,
        "summary": "A estrutura técnica favorece a direção confirmada.",
        "reasons": ["Médias alinhadas.", "ADX confirma força."],
        "risks": ["Pode ocorrer reversão rápida."],
        "entry_condition": "Considere somente após novo candle fechado confirmar a direção.",
    }, ensure_ascii=False)


class TradeProAITests(unittest.TestCase):
    def test_keeps_matching_buy_recommendation(self):
        result = parse_trade_pro_ai_response(response("COMPRA"), base_analysis("COMPRA"))
        self.assertEqual(result["recommendation"], "COMPRA")
        self.assertEqual(result["expiration_minutes"], 1)
        self.assertEqual(result["confidence"], 86)

    def test_keeps_matching_sell_recommendation(self):
        result = parse_trade_pro_ai_response(response("VENDA"), base_analysis("VENDA"))
        self.assertEqual(result["recommendation"], "VENDA")

    def test_ai_cannot_reverse_the_validated_direction(self):
        result = parse_trade_pro_ai_response(response("VENDA"), base_analysis("COMPRA"))
        self.assertEqual(result["recommendation"], "AGUARDAR")
        self.assertIsNone(result["expiration_minutes"])
        self.assertTrue(any("divergiu" in item for item in result["reasons"]))

    def test_ai_cannot_release_entry_without_base_signal(self):
        result = parse_trade_pro_ai_response(response("COMPRA"), base_analysis(None))
        self.assertEqual(result["recommendation"], "AGUARDAR")
        self.assertIsNone(result["expiration_minutes"])
        self.assertTrue(any("não validou" in item for item in result["reasons"]))

    def test_stale_market_data_always_blocks_entry(self):
        result = parse_trade_pro_ai_response(response("COMPRA"), base_analysis("COMPRA", stale=True))
        self.assertEqual(result["recommendation"], "AGUARDAR")
        self.assertIsNone(result["expiration_minutes"])
        self.assertTrue(any("desatualizado" in item for item in result["reasons"]))

    def test_prompt_contains_decision_guardrails_and_real_metrics(self):
        prompt = build_trade_pro_ai_prompt(base_analysis("COMPRA"))
        self.assertIn("Nunca inverta a direção", prompt)
        self.assertIn('"symbol":"EURUSD"', prompt)
        self.assertIn('"confluence":88.5', prompt)
        self.assertIn('"recent_closed_candles"', prompt)
        self.assertIn('"high":1.2', prompt)

    def test_rejects_invalid_gemini_json(self):
        with self.assertRaisesRegex(ValueError, "JSON inválido"):
            parse_trade_pro_ai_response("não é JSON", base_analysis("COMPRA"))

    def test_rejects_unknown_recommendation(self):
        with self.assertRaisesRegex(ValueError, "recomendação"):
            parse_trade_pro_ai_response(response("TALVEZ"), base_analysis("COMPRA"))


if __name__ == "__main__":
    unittest.main()
