from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from iqair.client import IQOptionClient

DEFAULT_ASSETS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
    "EURGBP","EURJPY","GBPJPY","EURCHF","AUDJPY","CADJPY","CHFJPY","EURAUD",
]
OTC_SUFFIX = "-OTC"

@dataclass
class IQSession:
    client: Any
    account: str
    created_at: float
    last_used: float

_SESSIONS: dict[str, IQSession] = {}
_LOCK = threading.RLock()
_SESSION_TTL = 60 * 60 * 6

def _cleanup():
    now=time.time()
    stale=[k for k,v in _SESSIONS.items() if now-v.last_used > _SESSION_TTL]
    for k in stale:
        _close_client(_SESSIONS.pop(k).client)

def _close_client(client):
    if client is None:
        return
    for name in ("close","logout","disconnect"):
        try:
            fn=getattr(client,name,None)
            if callable(fn):
                fn()
                break
        except Exception:
            pass

def connect_session(session_id: str, email: str, password: str, account: str):
    with _LOCK:
        _cleanup()
        old=_SESSIONS.pop(session_id,None)
        if old:
            _close_client(old.client)
        try:
            client=IQOptionClient(email, password)
            ok, reason=client.connect()
            if not ok:
                return False, f"Falha na autenticação da IQ Option: {reason}", None
            try:
                client.change_balance(account)
            except Exception as exc:
                _close_client(client)
                return False, f"Login realizado, mas não foi possível selecionar a conta {account}: {exc}", None
            _SESSIONS[session_id]=IQSession(client,account,time.time(),time.time())
            return True, f"Conectado à IQ Option — conta {account}.", _safe_balance(client)
        except Exception as exc:
            return False, f"Não foi possível autenticar na IQ Option: {exc}", None

def disconnect_session(session_id: str):
    with _LOCK:
        item=_SESSIONS.pop(session_id,None)
        if item:
            _close_client(item.client)

def _get(session_id: str):
    with _LOCK:
        _cleanup()
        item=_SESSIONS.get(session_id)
        if not item:
            return None
        item.last_used=time.time()
        return item

def is_connected(session_id: str):
    item=_get(session_id)
    if not item:
        return {"connected":False,"account":None}
    try:
        connected=item.client.check_connect() if hasattr(item.client,"check_connect") else True
    except Exception:
        connected=True
    return {"connected":bool(connected),"account":item.account}

def get_balance(session_id: str):
    item=_get(session_id)
    return _safe_balance(item.client) if item else None

def _safe_balance(client):
    try:
        return float(client.get_balance())
    except Exception:
        return None

def get_client(session_id: str):
    item=_get(session_id)
    if not item:
        raise RuntimeError("Sessão da IQ Option não encontrada ou expirada.")
    return item.client

def list_assets(session_id: str):
    client=get_client(session_id)
    # Preferimos os ativos conhecidos para manter a interface estável.
    # Se o cliente expuser metadados, adicionamos ativos abertos encontrados.
    assets=list(DEFAULT_ASSETS)
    try:
        metadata=client.get_asset_metadata()
        discovered=[]
        for acts in metadata.values():
            if not isinstance(acts,dict):
                continue
            for ticker in acts:
                t=str(ticker).upper()
                if t.endswith("-OTC") and t[:-4] in DEFAULT_ASSETS:
                    discovered.append(t)
        for t in discovered:
            if t not in assets:
                assets.append(t)
    except Exception:
        pass
    return assets

def get_market_status(session_id: str, asset: str):
    try:
        client=get_client(session_id)
        metadata=client.get_asset_metadata()
        target=asset.upper()
        for acts in metadata.values():
            if isinstance(acts,dict) and target in acts:
                info=acts[target]
                if isinstance(info,dict) and "is_open" in info:
                    return "aberto" if bool(info["is_open"]) else "fechado"
    except Exception:
        pass
    return None

def get_candles(session_id: str, asset: str, interval: int, count: int=240):
    client=get_client(session_id)
    raw=client.get_candles(asset.upper(), int(interval), int(count), time.time())
    if isinstance(raw,dict):
        raw=raw.get("candles") or raw.get("data") or list(raw.values())
    out=[]
    for c in raw or []:
        try:
            out.append({
                "time":int(c.get("from") or c.get("at") or 0),
                "open":float(c.get("open",0) or 0),
                "high":float(c.get("max") or c.get("high") or 0),
                "low":float(c.get("min") or c.get("low") or 0),
                "close":float(c.get("close",0) or 0),
                "volume":float(c.get("volume",0) or 0),
            })
        except Exception:
            continue
    return out

def get_candles_smart(session_id: str, asset: str, interval: int, count: int=240):
    return get_candles(session_id,asset,interval,count)[-count:]

def session_count():
    with _LOCK:
        _cleanup()
        return len(_SESSIONS)
