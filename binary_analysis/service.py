from __future__ import annotations

import threading
import time
import secrets
from dataclasses import dataclass
from typing import Any

from iqoptionapi.stable_api import IQ_Option

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
_PENDING_2FA: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()
_SESSION_TTL = 60 * 60 * 6
_metadata_cache: dict[Any, dict] = {}

def _call_with_timeout(fn, timeout_seconds: float, operation: str):
    """Executa chamadas potencialmente bloqueantes da API em thread daemon."""
    result = {}
    error = {}

    def runner():
        try:
            result["value"] = fn()
        except Exception as exc:
            error["value"] = exc

    worker = threading.Thread(target=runner, name=f"iq-{operation}", daemon=True)
    worker.start()
    worker.join(max(0.1, float(timeout_seconds)))

    if worker.is_alive():
        raise TimeoutError(f"{operation} excedeu {timeout_seconds:.1f}s")
    if "value" in error:
        raise error["value"]
    return result.get("value")

def _close_client(client):
    try:
        if client is not None and hasattr(client, "api") and client.api is not None:
            client.api.close()
    except Exception:
        pass

def _cleanup():
    now=time.time()
    stale=[k for k,v in _SESSIONS.items() if now-v.last_used > _SESSION_TTL]
    for k in stale:
        item=_SESSIONS.pop(k)
        _close_client(item.client)
    pending=[k for k,v in _PENDING_2FA.items() if now-v.get("created_at", now) > 600]
    for k in pending:
        item=_PENDING_2FA.pop(k, None)
        if item: _close_client(item.get("client"))

def connect_session(session_id: str, email: str, password: str, account: str):
    with _LOCK:
        _cleanup()
        try:
            client=IQ_Option(email.strip(), password)
            ok, reason=client.connect()
            if not ok:
                if str(reason).upper() == "2FA":
                    challenge_id = secrets.token_urlsafe(32)
                    _PENDING_2FA[challenge_id] = {"client": client, "account": account, "created_at": time.time()}
                    return False, "2FA_REQUIRED", {"challenge_id": challenge_id}
                _close_client(client)
                return False, f"Falha na autenticação da IQ Option: {reason}", None
            client.change_balance(account)
            _SESSIONS[session_id]=IQSession(client,account,time.time(),time.time())
            return True, f"Conectado à conta {account}.", _safe_balance(client)
        except Exception as exc:
            return False, f"Não foi possível autenticar na IQ Option: {exc}", None

def complete_2fa(challenge_id: str, code: str, session_id: str):
    with _LOCK:
        _cleanup()
        pending = _PENDING_2FA.pop(challenge_id, None)
        if not pending:
            return False, "A solicitação de verificação expirou. Faça o login novamente.", None
        client = pending["client"]
        try:
            ok, reason = client.connect_2fa(str(code).strip())
            if not ok:
                _PENDING_2FA[challenge_id] = pending
                return False, f"Falha na verificação 2FA: {reason}", None
            account = pending["account"]
            client.change_balance(account)
            _SESSIONS[session_id] = IQSession(client, account, time.time(), time.time())
            return True, f"Conectado à conta {account}.", _safe_balance(client)
        except Exception as exc:
            _PENDING_2FA[challenge_id] = pending
            return False, f"Não foi possível concluir a verificação 2FA: {exc}", None

def cancel_2fa(challenge_id: str):
    with _LOCK:
        pending = _PENDING_2FA.pop(challenge_id, None)
        if pending: _close_client(pending.get("client"))

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

def get_payout(session_id: str, asset: str):
    """Retorna o payout atual da modalidade binária/turbo como percentual, quando disponível."""
    client=get_client(session_id)
    key=str(asset or "").upper()
    try:
        cached=_metadata_cache.get(("payout", key))
        now=time.time()
        if cached and now-cached["ts"] < 60:
            return cached["value"]
        profits=_call_with_timeout(client.get_all_profit, 4.0, "get_all_profit") or {}
        is_otc = key.endswith("-OTC")
        info=profits.get(key) or (None if is_otc else profits.get(key.replace("-OTC",""))) or {}
        value=None
        for mode in ("binary","turbo"):
            raw=info.get(mode) if isinstance(info,dict) else None
            if isinstance(raw,(int,float)):
                value=float(raw)
                break
            if isinstance(raw,dict):
                for field in ("profit","payout"):
                    x=raw.get(field)
                    if isinstance(x,(int,float)):
                        value=float(x)
                        break
                if value is not None:
                    break
        result=round(value*100,1) if value is not None and value<=1.5 else (round(value,1) if value is not None else None)
        _metadata_cache[("payout", key)]={"ts":now,"value":result}
        return result
    except Exception as exc:
        print(f"[iq] erro get_payout({asset}): {exc}")
        return None

def get_market_status(session_id: str, asset: str):
    client=get_client(session_id)
    try:
        now=time.time()
        cached=_metadata_cache.get("open_time")
        if not cached or now-cached["ts"]>60:
            metadata=_call_with_timeout(client.get_all_open_time, 4.0, "get_all_open_time") or {}
            open_map={}
            for category, acts in metadata.items():
                if not isinstance(acts, dict): continue
                for ticker, info in acts.items():
                    if isinstance(info, dict) and "open" in info:
                        open_map[str(ticker).upper()] = bool(info["open"])
            _metadata_cache["open_time"]={"ts":now,"open_map":open_map}
        value=_metadata_cache["open_time"]["open_map"].get(asset.upper())
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
        raw=_call_with_timeout(lambda: client.get_candles(asset,interval,count,time.time()), 12.0, f"get_candles({asset},{interval})")
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
