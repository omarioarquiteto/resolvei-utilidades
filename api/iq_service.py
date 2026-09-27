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
DEFAULT_ASSETS_OTC = [f"{asset}-OTC" for asset in DEFAULT_ASSETS]

@dataclass
class IQSession:
    client: Any
    account: str
    created_at: float
    last_used: float

_SESSIONS: dict[str, IQSession] = {}
_LOCK = threading.RLock()
_SESSION_TTL = 60 * 60 * 6
_metadata_cache: dict[str, dict] = {}

def _close_client(client):
    try:
        if client is not None and hasattr(client, "close"):
            client.close()
    except Exception:
        pass

def _cleanup():
    now=time.time()
    stale=[k for k,v in _SESSIONS.items() if now-v.last_used > _SESSION_TTL]
    for k in stale:
        item=_SESSIONS.pop(k)
        _close_client(item.client)

def connect_session(session_id: str, email: str, password: str, account: str):
    with _LOCK:
        _cleanup()
        try:
            client=IQOptionClient(email.strip(), password)
            ok, reason=client.connect()
            if not ok:
                _close_client(client)
                return False, f"Falha na autenticação da IQ Option: {reason}", None
            client.change_balance(account)
            _SESSIONS[session_id]=IQSession(client,account,time.time(),time.time())
            return True, f"Conectado à conta {account}.", _safe_balance(client)
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

def get_client(session_id: str):
    item=_get(session_id)
    if not item:
        raise RuntimeError("Sessão da IQ Option não encontrada ou expirada.")
    return item.client

def is_connected(session_id: str):
    item=_get(session_id)
    if not item:
        return {"connected":False,"account":None}
    try:
        connected=bool(item.client.check_connect())
    except Exception:
        connected=True
    return {"connected":connected,"account":item.account}

def _safe_balance(client):
    try:
        return float(client.get_balance())
    except Exception:
        return None

def get_balance(session_id: str):
    item=_get(session_id)
    return _safe_balance(item.client) if item else None

def list_assets(session_id: str):
    # Mesmo catálogo do Market Insight AI: pares normais e OTC.
    return [*DEFAULT_ASSETS,*DEFAULT_ASSETS_OTC]

def get_market_status(session_id: str, asset: str):
    client=get_client(session_id)
    key="metadata"
    try:
        now=time.time()
        cached=_metadata_cache.get(key)
        if not cached or now-cached["ts"]>60:
            metadata=client.get_asset_metadata()
            open_map={}
            for category,acts in (metadata or {}).items():
                if not isinstance(acts,dict): continue
                for ticker,info in acts.items():
                    if isinstance(info,dict) and "is_open" in info:
                        open_map[str(ticker).upper()]=bool(info["is_open"])
            _metadata_cache[key]={"ts":now,"open_map":open_map}
        value=_metadata_cache[key]["open_map"].get(asset.upper())
        return None if value is None else ("aberto" if value else "fechado")
    except Exception as exc:
        print(f"[iq] erro get_market_status({asset}): {exc}")
        return None

def _normalize(c: dict):
    return {
        "time":int(c.get("from") or c.get("at") or 0),
        "open":float(c.get("open",0) or 0),
        "high":float(c.get("max") or c.get("high") or 0),
        "low":float(c.get("min") or c.get("low") or 0),
        "close":float(c.get("close",0) or 0),
        "volume":float(c.get("volume",0) or 0),
    }

def get_candles(session_id: str, asset: str, interval: int=300, count: int=200):
    client=get_client(session_id)
    try:
        raw=client.get_candles(asset,interval,count,time.time())
        if isinstance(raw,dict): raw=raw.get("candles") or raw.get("data") or []
        return [_normalize(c) for c in (raw or [])]
    except Exception as exc:
        print(f"[iq] erro get_candles({asset},{interval}): {exc}")
        return []

def get_candles_smart(session_id: str, asset: str, interval: int=300, count: int=200):
    candles=get_candles(session_id,asset,interval,count)
    return candles[-count:] if len(candles)>count else candles

def session_count():
    with _LOCK:
        _cleanup()
        return len(_SESSIONS)
