"""Autenticação isolada da ferramenta TRADE-PRÓ.

Usa a mesma implementação assíncrona da iqoptionapi adotada no Analista Bin,
mas mantém sessões independentes para não alterar o login de outras ferramentas.
As credenciais são usadas apenas para abrir a sessão e não são persistidas.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/trade-pro", tags=["TRADE-PRÓ"])

SESSION_TTL_SECONDS = 45 * 60
LOGIN_TIMEOUT_SECONDS = 25
SESSIONS: dict[str, dict[str, Any]] = {}


class TradeProLoginRequest(BaseModel):
    email: str
    password: str


def _client_class() -> Any:
    try:
        from iqoptionapi.aio import AsyncIQOption
        return AsyncIQOption
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="O cliente assíncrono da iqoptionapi não está disponível no servidor.",
        ) from exc


def _close_expired_item(item: dict[str, Any]) -> None:
    """Fecha, em melhor esforço, clientes cuja sessão expirou."""
    client = item.get("client")
    if client is not None:
        try:
            asyncio.create_task(client.close())
        except Exception:
            pass
    asset_client = item.get("asset_client")
    if asset_client is not None:
        try:
            asyncio.create_task(asyncio.to_thread(asset_client.close))
        except Exception:
            pass


def _cleanup() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    for sid, item in list(SESSIONS.items()):
        if item.get("last_used", 0) < cutoff:
            SESSIONS.pop(sid, None)
            _close_expired_item(item)


def _get_session(session_id: str | None) -> dict[str, Any]:
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=401, detail="Faça login na IQ Option pelo TRADE-PRÓ.")

    _cleanup()
    item = SESSIONS.get(sid)
    if not item:
        raise HTTPException(
            status_code=401,
            detail="A sessão do TRADE-PRÓ expirou. Faça login novamente.",
        )

    client = item.get("client")
    ws = getattr(client, "_ws", None)
    if ws is not None and bool(getattr(ws, "_closed", False)):
        SESSIONS.pop(sid, None)
        raise HTTPException(
            status_code=401,
            detail="A conexão com a IQ Option foi encerrada. Faça login novamente.",
        )

    item["last_used"] = time.time()
    return item


@router.post("/login")
async def login(req: TradeProLoginRequest) -> dict[str, Any]:
    email = req.email.strip()
    password = req.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="Informe e-mail e senha da IQ Option.")

    AsyncIQOption = _client_class()
    client = AsyncIQOption(email, password)

    try:
        await asyncio.wait_for(client.connect(), timeout=LOGIN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        try:
            await client.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=504,
            detail="A conexão com a IQ Option excedeu o tempo limite.",
        ) from exc
    except Exception as exc:
        try:
            await client.close()
        except Exception:
            pass
        detail = str(exc)[:320] or "A IQ Option recusou a conexão."
        status = 401 if "login" in detail.lower() or "auth" in detail.lower() else 502
        raise HTTPException(
            status_code=status,
            detail=f"Falha ao conectar à IQ Option: {detail}",
        ) from exc

    _cleanup()
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = {
        "client": client,
        "email": email,
        "last_used": time.time(),
        "asset_cache": {"at": 0.0, "data": None},
        "last_logged_candle": {},
    }

    return {
        "ok": True,
        "session_id": sid,
        "connected": True,
        "requires_2fa": False,
    }


@router.get("/session")
async def session(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    return {"ok": True, "connected": True, "email": item.get("email")}


@router.post("/logout")
async def logout(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    sid = (x_iq_session or "").strip()
    item = SESSIONS.pop(sid, None)
    if item:
        try:
            await item["client"].close()
        except Exception:
            pass
        asset_client = item.get("asset_client")
        if asset_client is not None:
            try:
                await asyncio.to_thread(asset_client.close)
            except Exception:
                pass
    return {"ok": True}
