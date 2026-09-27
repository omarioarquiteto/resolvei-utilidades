from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from iqoptionapi.stable_api import IQ_Option

DEFAULT_ASSETS = ["EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD","EURGBP","EURJPY","GBPJPY","EURCHF","AUDJPY","CADJPY","CHFJPY","EURAUD"]

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
        item=_SESSIONS.pop(k)
        _close_client(item.client)

def _close_client(client):
    if not client:
        return
    try:
        if getattr(client,"api",None):
            client.api.close()
    except Exception:
        pass

def connect_session(session_id: str, email: str, password: str, account: str):
    with _LOCK:
        _cleanup()
        try:
            client=IQ_Option(email,password)
            client.set_max_reconnect(3)
            ok, reason=client.connect()
            if not ok:
                _close_client(client)
                return False, f"Falha na autenticação da IQ Option: {reason}", None
            client.change_balance(account)
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
        if item:
            item.last_used=time.time()
        return item

def is_connected(session_id: str):
    item=_get(session_id)
    if not item:
        return {"connected":False,"account":None}
    try:
        connected=bool(item.client.check_connect())
    except Exception:
        connected=False
    return {"connected":connected,"account":item.account}

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
    assets=[]
    try:
        opened=client.get_all_open_time()
        for market,items in opened.items():
            if not isinstance(items,dict):
                continue
            for name,info in items.items():
                if isinstance(info,dict) and info.get("open") and name not in assets:
                    assets.append(str(name))
    except Exception:
        pass
    # Mantém os pares mais usados mesmo quando a IQ Option demora a responder ao inventário.
    for asset in DEFAULT_ASSETS:
        if asset not in assets:
            assets.append(asset)
    return sorted(assets)

def get_market_status(session_id: str, asset: str):
    try:
        opened=get_client(session_id).get_all_open_time()
        asset=asset.upper()
        for market,items in opened.items():
            if isinstance(items,dict) and asset in items:
                return "aberto" if bool(items[asset].get("open")) else "fechado"
    except Exception:
        pass
    return None

def get_candles(session_id: str, asset: str, interval: int, count: int=240):
    client=get_client(session_id)
    raw=client.get_candles(asset.upper(),int(interval),int(count),time.time())
    out=[]
    for c in raw or []:
        try:
            out.append({"time":int(c.get("from",0)),"open":float(c.get("open",0)),"high":float(c.get("max",c.get("high",0))),"low":float(c.get("min",c.get("low",0))),"close":float(c.get("close",0)),"volume":float(c.get("volume",0))})
        except Exception:
            continue
    return out

def get_candles_smart(session_id: str, asset: str, interval: int, count: int=240):
    candles=get_candles(session_id,asset,interval,count)
    return sorted(candles,key=lambda x:x["time"])[-count:]

def session_count():
    with _LOCK:
        _cleanup()
        return len(_SESSIONS)
