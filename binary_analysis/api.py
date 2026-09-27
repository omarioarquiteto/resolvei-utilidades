from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from .engine import analyze_asset, get_chart_data, strategy_catalog, walkforward_asset
from .service import (
    connect_session,
    disconnect_session,
    get_balance,
    get_market_status,
    get_payout,
    is_connected,
    list_assets,
    session_count,
)

router = APIRouter(prefix="/api/iq", tags=["IQ Option"])


class IQLoginRequest(BaseModel):
    email: str
    password: str
    account: str = "PRACTICE"


@router.get("/health")
def iq_health():
    return {
        "ok": True,
        "provider": "IQ Option",
        "api_mode": "community/unofficial",
        "connected_sessions": session_count(),
    }


@router.post("/login")
def iq_login(request: IQLoginRequest):
    email = request.email.strip()
    if not email or not request.password:
        raise HTTPException(400, "Informe o usuário/e-mail e a senha da IQ Option.")
    account = request.account.upper()
    if account not in ("PRACTICE", "REAL"):
        raise HTTPException(400, "A conta deve ser PRACTICE (demo) ou REAL.")
    session_id = secrets.token_urlsafe(32)
    ok, message, balance = connect_session(session_id, email, request.password, account)
    if not ok:
        disconnect_session(session_id)
        raise HTTPException(502, message)
    return {
        "ok": True,
        "session_id": session_id,
        "message": message,
        "account": account,
        "balance": balance,
    }


@router.post("/logout")
def iq_logout(x_iq_session: str | None = Header(default=None)):
    if x_iq_session:
        disconnect_session(x_iq_session)
    return {"ok": True}


@router.get("/status")
def iq_status(x_iq_session: str | None = Header(default=None)):
    if not x_iq_session:
        return {"connected": False, "balance": None, "account": None}
    status = is_connected(x_iq_session)
    return {
        "connected": status["connected"],
        "balance": get_balance(x_iq_session),
        "account": status.get("account"),
    }


@router.get("/assets")
def iq_assets(x_iq_session: str | None = Header(default=None)):
    if not x_iq_session or not is_connected(x_iq_session)["connected"]:
        raise HTTPException(401, "Conecte sua conta da IQ Option primeiro.")
    return {"assets": list_assets(x_iq_session)}


@router.get("/strategies")
def iq_strategies():
    return {"strategies": strategy_catalog()}


@router.get("/analyze/{asset}")
def iq_analyze(
    asset: str,
    strategy: str = Query("trend_pullback"),
    refresh: bool = Query(False),
    x_iq_session: str | None = Header(default=None),
):
    if not x_iq_session or not is_connected(x_iq_session)["connected"]:
        raise HTTPException(401, "Conecte sua conta da IQ Option primeiro.")
    try:
        result = analyze_asset(x_iq_session, asset, strategy, force_refresh=refresh)
        result["market"] = get_market_status(x_iq_session, asset)
        result["payout"] = get_payout(x_iq_session, asset)
        for signal in (result.get("signals") or {}).values():
            if isinstance(signal, dict):
                signal["payout"] = result["payout"]
        result["updatedAt"] = datetime.now(timezone.utc).isoformat()
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            502, f"Não foi possível analisar {asset.upper()}: {exc}"
        ) from exc


@router.get("/candles/{asset}")
def iq_candles(
    asset: str,
    interval: int = Query(300, ge=60, le=1800),
    count: int = Query(200, ge=60, le=500),
    x_iq_session: str | None = Header(default=None),
):
    if not x_iq_session or not is_connected(x_iq_session)["connected"]:
        raise HTTPException(401, "Conecte sua conta da IQ Option primeiro.")
    try:
        return get_chart_data(x_iq_session, asset, interval, count)
    except Exception as exc:
        raise HTTPException(502, f"Falha ao obter candles: {exc}") from exc


@router.get("/backtest/{asset}")
def iq_backtest(
    asset: str,
    expiry: str = Query("1min"),
    count: int = Query(240, ge=80, le=500),
    x_iq_session: str | None = Header(default=None),
):
    if not x_iq_session or not is_connected(x_iq_session)["connected"]:
        raise HTTPException(401, "Conecte sua conta da IQ Option primeiro.")
    try:
        return walkforward_asset(x_iq_session, asset, expiry, count)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha no backtest: {exc}") from exc
