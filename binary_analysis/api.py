from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from .engine import analyze_asset, chart_data, backtest_asset, strategy_catalog
from .service import (
    connect_session, disconnect_session, get_balance, get_market_status,
    get_payout, list_assets, session_count, status
)

router = APIRouter(prefix="/api/iq", tags=["IQ Option"])

class LoginRequest(BaseModel):
    email: str
    password: str
    account: str = "PRACTICE"

def _session(x_iq_session):
    if not x_iq_session or not status(x_iq_session)["connected"]:
        raise HTTPException(401, "Conecte sua conta da IQ Option primeiro.")
    return x_iq_session

@router.get("/health")
def health():
    return {"ok": True, "provider": "IQ Option", "community_api": True, "sessions": session_count()}

@router.post("/login")
def login(req: LoginRequest):
    email = req.email.strip()
    account = req.account.upper()
    if not email or not req.password:
        raise HTTPException(400, "Informe e-mail e senha.")
    if account not in ("PRACTICE", "REAL"):
        raise HTTPException(400, "Conta inválida. Use PRACTICE ou REAL.")
    sid = secrets.token_urlsafe(32)
    ok, message, balance = connect_session(sid, email, req.password, account)
    if not ok:
        raise HTTPException(502, message)
    return {"ok": True, "session_id": sid, "message": message, "account": account, "balance": balance}

@router.post("/logout")
def logout(x_iq_session: str | None = Header(default=None)):
    if x_iq_session:
        disconnect_session(x_iq_session)
    return {"ok": True}

@router.get("/status")
def get_status(x_iq_session: str | None = Header(default=None)):
    if not x_iq_session:
        return {"connected": False, "account": None, "balance": None}
    s = status(x_iq_session)
    return {"connected": s["connected"], "account": s["account"], "balance": get_balance(x_iq_session)}

@router.get("/assets")
def assets(x_iq_session: str | None = Header(default=None)):
    sid = _session(x_iq_session)
    return {"assets": list_assets(sid)}

@router.get("/strategies")
def strategies():
    return {"strategies": strategy_catalog()}

@router.get("/analyze/{asset}")
def analyze(
    asset: str,
    expiry: str = Query("1min"),
    strategy: str = Query("smart_confluence"),
    x_iq_session: str | None = Header(default=None),
):
    sid = _session(x_iq_session)
    if expiry not in ("1min", "5min"):
        raise HTTPException(400, "Expiração deve ser 1min ou 5min.")
    try:
        result = analyze_asset(sid, asset.upper(), expiry, strategy)
        result["market"] = get_market_status(sid, asset)
        result["payout"] = get_payout(sid, asset)
        result["updatedAt"] = datetime.now(timezone.utc).isoformat()
        return result
    except TimeoutError as exc:
        raise HTTPException(504, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha na análise: {type(exc).__name__}: {exc}") from exc

@router.get("/candles/{asset}")
def candles(
    asset: str,
    interval: int = Query(60, ge=60, le=1800),
    count: int = Query(200, ge=50, le=500),
    x_iq_session: str | None = Header(default=None),
):
    sid = _session(x_iq_session)
    try:
        return chart_data(sid, asset.upper(), interval, count)
    except Exception as exc:
        raise HTTPException(502, f"Falha ao obter candles: {exc}") from exc

@router.get("/backtest/{asset}")
def backtest(
    asset: str,
    expiry: str = Query("1min"),
    count: int = Query(500, ge=100, le=1000),
    x_iq_session: str | None = Header(default=None),
):
    sid = _session(x_iq_session)
    if expiry not in ("1min", "5min"):
        raise HTTPException(400, "Expiração deve ser 1min ou 5min.")
    try:
        return backtest_asset(sid, asset.upper(), expiry, count)
    except Exception as exc:
        raise HTTPException(502, f"Falha no backtest: {type(exc).__name__}: {exc}") from exc
