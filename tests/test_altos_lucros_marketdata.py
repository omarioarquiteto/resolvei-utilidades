import unittest

from altos_lucros_marketdata import (
    normalize_client_price_event,
    normalize_digital_underlyings,
    normalize_legacy_quote_event,
    normalize_legacy_strike_list,
    normalize_library_snapshot,
    payout_from_ask,
)


class TestAltosLucrosMarketData(unittest.TestCase):
    def setUp(self):
        self.active_map = {"1": "EURUSD", "76": "EURJPY"}

    def test_client_price_generated_maps_strikes_and_call_put_payouts(self):
        message = {
            "name": "client-price-generated",
            "msg": {
                "asset_id": 1,
                "prices": [
                    {
                        "strike": "1.10000",
                        "call": {"ask": 30.0, "symbol": "doEURUSD202610301300PT5MCALL"},
                        "put": {"ask": 40.0, "symbol": "doEURUSD202610301300PT5MPUT"},
                    },
                    {
                        "strike": "SPT",
                        "call": {"ask": 50.0, "symbol": "doEURUSD202610301300PT5MPSPT"},
                        "put": {"ask": 50.0, "symbol": "doEURUSD202610301300PT5MPSPT"},
                    },
                ],
            },
        }
        parsed = normalize_client_price_event(message, self.active_map)
        self.assertIsNotNone(parsed)
        symbol, duration, grid = parsed
        self.assertEqual(symbol, "EURUSD")
        self.assertEqual(duration, 5)
        self.assertEqual(grid["1.10000000"]["call"]["profit"], 233.333333)
        self.assertEqual(grid["1.10000000"]["put"]["profit"], 150.0)
        self.assertEqual(len(grid), 1)

    def test_client_price_generated_accepts_string_asset_id_and_15m(self):
        message = {
            "name": "client-price-generated",
            "msg": {
                "asset_id": "76",
                "prices": [{
                    "strike": "160.250",
                    "call": {"ask": "25", "symbol": "doEURJPY202610301300PT15MCALL"},
                    "put": {"ask": "35", "symbol": "doEURJPY202610301300PT15MPUT"},
                }],
            },
        }
        parsed = normalize_client_price_event(message, self.active_map)
        self.assertEqual(parsed[0:2], ("EURJPY", 15))

    def test_unrelated_or_unknown_active_event_is_ignored(self):
        self.assertIsNone(normalize_client_price_event({"name": "timeSync", "msg": 1}, self.active_map))
        message = {
            "name": "client-price-generated",
            "msg": {"asset_id": 999, "prices": []},
        }
        self.assertIsNone(normalize_client_price_event(message, self.active_map))

    def test_invalid_ask_does_not_create_fabricated_payout(self):
        self.assertIsNone(payout_from_ask(None))
        self.assertIsNone(payout_from_ask(0))
        self.assertIsNone(payout_from_ask(101))
        self.assertEqual(payout_from_ask(50), 100.0)

    def test_legacy_quote_event_joins_contract_ids_to_payout(self):
        message = {
            "name": "instrument-quotes-generated",
            "msg": {
                "active": 1,
                "expiration": {"period": 300, "timestamp": 1_800_000_000},
                "quotes": [
                    {"price": {"ask": 25}, "symbols": ["call-id"]},
                    {"price": {"ask": 40}, "symbols": ["put-id", "put-id-2"]},
                ],
            },
        }
        parsed = normalize_legacy_quote_event(message, self.active_map)
        self.assertEqual(parsed[0:2], ("EURUSD", 5))
        self.assertEqual(parsed[2]["call-id"], 300.0)
        self.assertEqual(parsed[2]["put-id"], 150.0)

    def test_legacy_strike_list_combines_real_ids_and_payouts(self):
        message = {
            "msg": {
                "strike": [{
                    "value": "1100000",
                    "call": {"id": "call-id"},
                    "put": {"id": "put-id"},
                }]
            }
        }
        grid = normalize_legacy_strike_list(
            message, {"call-id": 250.0, "put-id": 180.0}
        )
        self.assertEqual(grid["1.10000000"]["call"]["profit"], 250.0)
        self.assertEqual(grid["1.10000000"]["put"]["profit"], 180.0)

    def test_library_snapshot_skips_spot_and_malformed_rows(self):
        snapshot = {
            "SPT": {"call": {"profit": 0}, "put": {"profit": 0}},
            "1.10000": {
                "call": {"id": "c", "profit": 255.0},
                "put": {"id": "p", "profit": None},
            },
            "broken": {"call": {}, "put": {}},
        }
        grid = normalize_library_snapshot(snapshot)
        self.assertEqual(list(grid), ["1.10000000"])
        self.assertEqual(grid["1.10000000"]["call"]["profit"], 255.0)

    def test_digital_catalog_reads_current_open_window(self):
        response = {
            "underlying": [
                {
                    "underlying": "EURUSD",
                    "active_id": 1,
                    "schedule": [{"open": 100, "close": 200}],
                },
                {
                    "name": "EURJPY",
                    "active_id": 76,
                    "schedule": [{"open": 100, "close": 120}],
                },
            ]
        }
        catalog = normalize_digital_underlyings(response, 150)
        self.assertTrue(catalog["EURUSD"]["digital_open"])
        self.assertFalse(catalog["EURJPY"]["digital_open"])


if __name__ == "__main__":
    unittest.main()
