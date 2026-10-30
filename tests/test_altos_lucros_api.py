import asyncio
import time
import unittest
from types import SimpleNamespace

from iqoptionapi import global_value

from altos_lucros_api import (
    _clear_strike_buffer,
    _ensure_asset_client_connected,
    _install_digital_quote_callback,
    _load_digital_catalog,
    _wait_for_strikes,
)


def _sample_client_event():
    return {
        "name": "client-price-generated",
        "msg": {
            "asset_id": 1,
            "prices": [{
                "strike": "1.10000",
                "call": {"ask": 25.0, "symbol": "doEURUSD202610301300PT5MCALL"},
                "put": {"ask": 40.0, "symbol": "doEURUSD202610301300PT5MPUT"},
            }],
        },
    }


class FakeApi:
    def __init__(self, object_id="altos-lucros-test"):
        self.object_id = object_id
        self.timesync = SimpleNamespace(server_timestamp=time.time())
        self.instrument_quites_generated_data = {}
        self.instrument_quotes_generated_raw_data = {}
        self.underlying_list_data = None
        self.alive = True
        self.reconnects = 0

    def websocket_alive(self):
        return self.alive

    def get_digital_underlying(self):
        self.underlying_list_data = {
            "underlying": [{
                "underlying": "EURUSD",
                "active_id": 1,
                "schedule": [{"open": time.time() - 60, "close": time.time() + 3600}],
            }]
        }


class FakeAssetClient:
    def __init__(self, api=None):
        self.api = api or FakeApi()

    def connect(self):
        self.api = FakeApi(object_id="altos-lucros-reconnected")
        self.api.reconnects += 1
        return True, None


class TestAltosLucrosApiIntegration(unittest.TestCase):
    def tearDown(self):
        for key in ("altos-lucros-test", "altos-lucros-reconnected"):
            global_value.client_callback.pop(key, None)

    def test_raw_websocket_callback_captures_v2_grid_before_library_parser(self):
        item = {}
        client = FakeAssetClient()
        _install_digital_quote_callback(
            item, client, [{"symbol": "EURUSD", "activeId": 1}]
        )
        callback = global_value.client_callback[client.api.object_id]
        callback(_sample_client_event())

        quotes = _wait_for_strikes(
            item, client, "EURUSD", 5, time.time() - 1
        )
        self.assertIn("1.10000000", quotes)
        self.assertEqual(quotes["1.10000000"]["call"]["profit"], 300.0)
        self.assertEqual(
            item["altos_last_quote_source"], "client-price-generated"
        )

    def test_clearing_buffer_removes_previous_callback_and_library_snapshot(self):
        item = {
            "altos_digital_quote_cache": {
                ("EURUSD", 5): {"quotes": {"1.1": {}}, "received_at": time.time()}
            },
            "altos_legacy_payout_cache": {
                ("EURUSD", 5): {"payouts": {"id": 250}, "received_at": time.time()}
            },
        }
        client = FakeAssetClient()
        client.api.instrument_quites_generated_data = {
            "EURUSD": {300: {"1.1": {"call": {"profit": 250}}}}
        }
        client.api.instrument_quotes_generated_raw_data = {
            "EURUSD": {300: {"name": "old"}}
        }
        _clear_strike_buffer(item, client, "EURUSD", 5)
        self.assertNotIn(("EURUSD", 5), item["altos_digital_quote_cache"])
        self.assertNotIn(("EURUSD", 5), item["altos_legacy_payout_cache"])
        self.assertEqual(client.api.instrument_quites_generated_data["EURUSD"][300], {})
        self.assertEqual(client.api.instrument_quotes_generated_raw_data["EURUSD"][300], {})

    def test_stale_asset_websocket_is_reconnected_before_subscribing(self):
        client = FakeAssetClient()
        client.api.alive = False
        client.api.timesync.server_timestamp = time.time() - 500
        item = {"asset_client": client}
        result = asyncio.run(_ensure_asset_client_connected(item))
        self.assertIs(result, client)
        self.assertTrue(client.api.websocket_alive())
        self.assertEqual(client.api.object_id, "altos-lucros-reconnected")

    def test_digital_catalog_loads_symbols_and_open_schedule(self):
        client = FakeAssetClient()
        item = {"asset_client": client}
        result = asyncio.run(_load_digital_catalog(item))
        self.assertTrue(result["available"])
        self.assertTrue(result["assets"]["EURUSD"]["digital_open"])


if __name__ == "__main__":
    unittest.main()
