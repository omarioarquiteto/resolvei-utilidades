"""Autenticação exclusiva da ferramenta VIBE LUCRO.

Cada login cria um cliente AsyncIQOption e um token próprios. Nenhuma sessão de
outra ferramenta é consultada, compartilhada, substituída ou encerrada.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/vibe-lucro", tags=["VIBE LUCRO · AUTENTICAÇÃO"])

SESSION_TTL_SECONDS = 45 * 60
LOGIN_TIMEOUT_SECONDS = 25
SESSIONS: dict[str, dict[str, Any]] = {}


class VibeLucroLoginRequest(BaseModel):
    model_config = {"extra": "forbid"}
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=512)


def _client_class() -> Any:
    try:
        from iqoptionapi.aio import AsyncIQOption
        return AsyncIQOption
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="O cliente assíncrono da iqoptionapi não está disponível no servidor.",
        ) from exc


async def _close_client(client: Any) -> None:
    if client is None:
        return
    try:
        await asyncio.wait_for(client.close(), timeout=5)
    except Exception:
        pass


async def _cleanup() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    expired = [
        (sid, item)
        for sid, item in list(SESSIONS.items())
        if item.get("last_used", 0) < cutoff
    ]
    for sid, item in expired:
        SESSIONS.pop(sid, None)
        await _close_client(item.get("client"))


def _get_session(session_id: str | None) -> dict[str, Any]:
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(
            status_code=401,
            detail="Conecte sua conta IQ Option pelo VIBE LUCRO.",
        )
    item = SESSIONS.get(sid)
    if not item:
        raise HTTPException(
            status_code=401,
            detail="A sessão exclusiva do VIBE LUCRO expirou. Faça login novamente.",
        )
    if item.get("last_used", 0) < time.time() - SESSION_TTL_SECONDS:
        SESSIONS.pop(sid, None)
        client = item.get("client")
        try:
            asyncio.get_running_loop().create_task(_close_client(client))
        except RuntimeError:
            pass
        raise HTTPException(
            status_code=401,
            detail="A sessão exclusiva do VIBE LUCRO expirou. Faça login novamente.",
        )
    client = item.get("client")
    websocket = getattr(client, "_ws", None)
    if websocket is None or bool(getattr(websocket, "_closed", False)):
        SESSIONS.pop(sid, None)
        raise HTTPException(
            status_code=401,
            detail="A conexão exclusiva do VIBE LUCRO foi encerrada. Faça login novamente.",
        )
    item["last_used"] = time.time()
    return item


@router.post("/login")
async def login(request: VibeLucroLoginRequest) -> dict[str, Any]:
    email = request.email.strip()
    password = request.password
    if not email or not password:
        raise HTTPException(status_code=400, detail="Informe e-mail e senha da IQ Option.")

    client = _client_class()(email, password)
    try:
        result = await asyncio.wait_for(client.connect(), timeout=LOGIN_TIMEOUT_SECONDS)
        if result is False or (isinstance(result, tuple) and result and result[0] is False):
            reason = result[1] if isinstance(result, tuple) and len(result) > 1 else "login recusado"
            raise RuntimeError(str(reason))
        websocket = getattr(client, "_ws", None)
        if websocket is None or bool(getattr(websocket, "_closed", False)):
            raise RuntimeError("A IQ Option não confirmou uma conexão ativa.")
    except asyncio.TimeoutError as exc:
        await _close_client(client)
        raise HTTPException(
            status_code=504,
            detail="A conexão exclusiva do VIBE LUCRO excedeu o tempo limite.",
        ) from exc
    except HTTPException:
        await _close_client(client)
        raise
    except Exception as exc:
        await _close_client(client)
        detail = str(exc)[:260] or "A IQ Option recusou a conexão."
        code = 401 if any(
            token in detail.lower()
            for token in ("login", "auth", "password", "credential", "senha")
        ) else 502
        raise HTTPException(
            status_code=code,
            detail=f"Falha ao conectar a sessão do VIBE LUCRO: {detail}",
        ) from exc

    await _cleanup()
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = {
        "client": client,
        "email": email,
        "last_used": time.time(),
        "session_owner": "vibe-lucro",
        "asset_cache": None,
    }
    return {
        "ok": True,
        "session_id": sid,
        "connected": True,
        "exclusive": True,
        "requires_2fa": False,
    }


@router.get("/session")
async def session(
    x_iq_session: str | None = Header(default=None, alias="X-IQ-Session"),
) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    return {
        "ok": True,
        "connected": True,
        "exclusive": True,
        "email": item.get("email"),
    }


@router.post("/logout")
async def logout(
    x_iq_session: str | None = Header(default=None, alias="X-IQ-Session"),
) -> dict[str, Any]:
    sid = (x_iq_session or "").strip()
    item = SESSIONS.pop(sid, None)
    if item:
        await _close_client(item.get("client"))
    # Only this module's session dictionary is touched. No other tool's token
    # or IQ Option websocket is read or closed here.
    return {"ok": True, "exclusive": True}
