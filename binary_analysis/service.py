from __future__ import annotations

import threading
import time
import secrets
import requests
import socket
from urllib3.util import connection as urllib3_connection
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

def _http_login(email: str, password: str):
    url = "https://auth.iqoption.com/api/v2/login"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    # Render pode resolver auth.iqoption.com para IPv6 sem rota funcional.
    # Forçamos IPv4 somente durante a chamada de autenticação.
    original_family = urllib3_connection.allowed_gai_family
    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
    try:
        response = requests.post(
            url,
            data={"identifier": email.strip(), "password": password},
            headers=headers,
            timeout=30,
        )
    finally:
        urllib3_connection.allowed_gai_family = original_family
    try: payload = response.json()
    except Exception: payload = None
    if response.status_code == 200:
        ssid = response.cookies.get("ssid")
        if ssid: return ssid, None
        if isinstance(payload, dict) and payload.get("code") == "verify":
            return None, {"token": payload.get("token"), "method": payload.get("method") or "sms"}
        return None, {"error": "A IQ Option não retornou uma sessão válida."}
    if isinstance(payload, dict):
        detail = payload.get("message") or payload.get("error") or payload.get("reason")
        if detail: return None, {"error": str(detail)}
    return None, {"error": f"HTTP {response.status_code} na autenticação."}

def _http_verify_2fa(token: str, method: str, code: str):
    url = "https://auth.iqoption.com/api/v2/verify/2fa"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36", "Content-Type": "application/json"}
    response = requests.post(url, json={"method": method, "token": token, "code": code.strip()}, headers=headers, timeout=15)
    try: payload = response.json()
    except Exception: payload = {}
    if response.status_code == 200 and isinstance(payload, dict): return payload
    detail = payload.get("message") or payload.get("error") or payload.get("reason")
    return {"code": "error", "message": str(detail or f"HTTP {response.status_code}")}

def connect_session(session_id: str, email: str, password: str, account: str):
    with _LOCK:
        _cleanup()
        client = None
        try:
            ssid, challenge = _http_login(email, password)
            if challenge and challenge.get("token"):
                challenge_id = secrets.token_urlsafe(32)
                _PENDING_2FA[challenge_id] = {"client": IQ_Option(email.strip(), password), "account": account, "created_at": time.time(), "token": challenge["token"], "method": challenge.get("method") or "sms"}
                return False, "2FA_REQUIRED", {"challenge_id": challenge_id}
            if not ssid:
                reason = (challenge or {}).get("error") or "A IQ Option recusou a autenticação."
                return False, f"Falha na autenticação da IQ Option: {reason}", None
            client = IQ_Option(email.strip(), password, set_ssid=ssid)
            ok, reason = _call_with_timeout(client.connect, 25.0, "conexão WebSocket IQ Option")
            if not ok:
                _close_client(client)
                return False, f"Login aceito, mas a conexão de mercado da IQ Option falhou: {reason}", None
            _call_with_timeout(lambda: client.change_balance(account), 10.0, f"seleção da conta {account}")
            _SESSIONS[session_id] = IQSession(client, account, time.time(), time.time())
            return True, f"Conectado à conta {account}.", _safe_balance(client)
        except requests.RequestException as exc:
            _close_client(client)
            return False, f"Não foi possível alcançar o serviço de autenticação da IQ Option: {exc}", None
        except Exception as exc:
            _close_client(client)
            return False, f"Não foi possível autenticar/conectar à IQ Option: {exc}", None

def complete_2fa(challenge_id: str, code: str, session_id: str, method: str = "sms"):
    with _LOCK:
        _cleanup()
        pending = _PENDING_2FA.get(challenge_id)
        if not pending: return False, "A solicitação de verificação expirou. Faça o login novamente.", None
        client = pending["client"]
        try:
            token = pending.get("token")
            method = pending.get("method") or method or "sms"
            if not token: return False, "A IQ Option não forneceu o token necessário para a verificação.", None
            result = _http_verify_2fa(token, method, code)
            if result.get("code") != "success" or not result.get("token"):
                return False, f"Falha na verificação da IQ Option: {result.get('message') or result}", None
            client.setting_2FA_TOKEN(result["token"])
            ok, reason = _call_with_timeout(client.connect, 25.0, "login IQ Option após 2FA")
            if not ok: return False, f"Falha na conexão após 2FA: {reason}", None
            account = pending["account"]
            _call_with_timeout(lambda: client.change_balance(account), 10.0, f"seleção da conta {account}")
            _PENDING_2FA.pop(challenge_id, None)
            _SESSIONS[session_id] = IQSession(client, account, time.time(), time.time())
            return True, f"Conectado à conta {account}.", _safe_balance(client)
        except requests.RequestException as exc:
            return False, f"Não foi possível concluir a verificação da IQ Option: {exc}", None
        except Exception as exc:
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
