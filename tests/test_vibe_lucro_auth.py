from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import vibe_lucro_auth as auth


class FakeClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self._ws = SimpleNamespace(_closed=False)
        self.closed = False

    async def connect(self):
        return True

    async def close(self):
        self.closed = True
        self._ws._closed = True


class TestVibeLucroExclusiveSession(unittest.TestCase):
    def setUp(self):
        self.original_sessions = dict(auth.SESSIONS)
        auth.SESSIONS.clear()

    def tearDown(self):
        auth.SESSIONS.clear()
        auth.SESSIONS.update(self.original_sessions)

    def test_login_creates_only_a_vibe_lucro_owned_session(self):
        created = []

        def client_factory(email, password):
            client = FakeClient(email, password)
            created.append(client)
            return client

        with patch.object(auth, "_client_class", return_value=client_factory):
            result = asyncio.run(
                auth.login(auth.VibeLucroLoginRequest(email="vibe@example.com", password="secret"))
            )

        self.assertTrue(result["exclusive"])
        self.assertEqual(len(auth.SESSIONS), 1)
        stored = auth.SESSIONS[result["session_id"]]
        self.assertEqual(stored["session_owner"], "vibe-lucro")
        self.assertEqual(stored["email"], "vibe@example.com")
        self.assertNotIn("password", stored)
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].closed)

    def test_logout_closes_only_its_own_session_and_leaves_other_tool_sessions(self):
        client = FakeClient("vibe@example.com", "secret")
        other_client = FakeClient("trade@example.com", "other")
        auth.SESSIONS["vibe-token"] = {
            "client": client,
            "email": "vibe@example.com",
            "last_used": 9_999_999_999,
            "session_owner": "vibe-lucro",
        }
        import trade_pro_auth
        previous = dict(trade_pro_auth.SESSIONS)
        trade_pro_auth.SESSIONS.clear()
        trade_pro_auth.SESSIONS["trade-token"] = {
            "client": other_client,
            "email": "trade@example.com",
            "last_used": 9_999_999_999,
        }
        try:
            result = asyncio.run(
                auth.logout("vibe-token")
            )
            self.assertTrue(result["exclusive"])
            self.assertNotIn("vibe-token", auth.SESSIONS)
            self.assertTrue(client.closed)
            self.assertIn("trade-token", trade_pro_auth.SESSIONS)
            self.assertFalse(other_client.closed)
        finally:
            trade_pro_auth.SESSIONS.clear()
            trade_pro_auth.SESSIONS.update(previous)

    def test_unknown_or_expired_token_does_not_resolve(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as error:
            auth._get_session("token-from-another-tool")
        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
