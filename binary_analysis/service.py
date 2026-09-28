from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from iqoptionapi.stable_api import IQ_Option

DEFAULT_ASSETS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
    "EURGBP","EURJPY","GBPJPY","EURCHF","AUDJPY","CADJPY","CHFJPY","EURAUD",
]
DEFAULT_ASSETS_OTC = [f"{x}-OTC" for x in DEFAULT_ASSETS]

@dataclass
class IQSession:
    client: Any
    account: str
    created_at: float
    last_used: float

_SESSIONS: dict[str, IQSession] = {}
_LOCK = threading.RLock()
_TTL = 6 * 60 * 60

def _timed(fn, timeout: float):
    box: dict[str, Any] = {}
    err: list[Exception] = []
    def run():
        try:
            box["value"] = fn()
        except Exception as exc:
            err.append(exc)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"Operação excedeu {timeout:.0f}s")
    if err:
        raise err[0]
    return box.get("value")

def _close(client):
    try:
        api = getattr(client, "api", None)
        if api is not None:
            api.close()
    except Exception:
        pass

def _cleanup():
    now = time.time()
    for sid, item in list(_SESSIONS.items()):
        if now - item.last_used > _TTL:
            _SESSIONS.pop(sid, None)
            _close(item.client)

def connect_session(session_id: str, email: str, password: str, account: str):
    with _LOCK:
        _cleanup()
        client = IQ_Option(email.strip(), password)
        try:
            result = _timed(client.connect, 45)
            if not isinstance(result, tuple):
                ok, reason = bool(result), "Resposta inesperada da biblioteca IQ Option."
            else:
                ok, reason = result[0], result[1] if len(result) > 1 else ""
            if not ok:
                _close(client)
                return False, f"Falha no login da IQ Option: {reason or 'credenciais recusadas ou conexão rejeitada.'}", None
            account = account.upper()
            if account not in ("PRACTICE", "REAL"):
                _close(client)
                return False, "Tipo de conta inválido.", None
            try:
                client.change_balance(account)
            except Exception as exc:
                _close(client)
                return False, f"Login realizado, mas não foi possível selecionar a conta {account}: {exc}", None
            _SESSIONS[session_id] = IQSession(client, account, time.time(), time.time())
            return True, f"Conectado à IQ Option — conta {account}.", safe_balance(client)
        except TimeoutError:
            _close(client)
            return False, "A IQ Option não respondeu ao login em 45 segundos. Isso indica bloqueio/indisponibilidade da conexão do servidor, não erro de layout.", None
        except Exception as exc:
            _close(client)
            return False, f"Erro ao conectar à IQ Option: {type(exc).__name__}: {exc}", None

def disconnect_session(session_id: str):
    with _LOCK:
        item = _SESSIONS.pop(session_id, None)
        if item:
            _close(item.client)

def _get(session_id: str) -> IQSession:
    with _LOCK:
        _cleanup()
        item = _SESSIONS.get(session_id)
        if not item:
            raise RuntimeError("Sessão IQ Option inexistente ou expirada.")
        item.last_used = time.time()
        return item

def get_client(session_id: str):
    return _get(session_id).client

def status(session_id: str):
    try:
        item = _get(session_id)
    except Exception:
        return {"connected": False, "account": None}
    try:
        connected = bool(item.client.check_connect())
    except Exception:
        connected = True
    return {"connected": connected, "account": item.account}

def safe_balance(client):
    try:
        return float(client.get_balance())
    except Exception:
        return None

def get_balance(session_id: str):
    try:
        return safe_balance(get_client(session_id))
    except Exception:
        return None

def list_assets(session_id: str):
    client = get_client(session_id)
    try:
        opened = client.get_all_open_time() or {}
        names = set()
        for group in opened.values():
            if isinstance(group, dict):
                names.update(str(k).upper() for k in group)
        regular = sorted(x for x in names if not x.endswith("-OTC"))
        otc = sorted(x for x in names if x.endswith("-OTC"))
        if regular or otc:
            return regular + otc
    except Exception:
        pass
    return DEFAULT_ASSETS + DEFAULT_ASSETS_OTC

def get_market_status(session_id: str, asset: str):
    try:
        opened = get_client(session_id).get_all_open_time() or {}
        key = asset.upper()
        for group in opened.values():
            info = group.get(key) if isinstance(group, dict) else None
            if isinstance(info, dict) and "open" in info:
                return "aberto" if info["open"] else "fechado"
    except Exception:
        pass
    return None

def get_payout(session_id: str, asset: str):
    try:
        data = get_client(session_id).get_all_profit() or {}
        info = data.get(asset.upper()) or {}
        for mode in ("binary", "turbo"):
            value = info.get(mode) if isinstance(info, dict) else None
            if isinstance(value, dict):
                value = value.get("profit", value.get("payout"))
            if isinstance(value, (int, float)):
                return round(value * 100 if value <= 1.5 else value, 1)
    except Exception:
        pass
    return None

def _normalize(c):
    return {
        "time": int(c.get("from") or c.get("at") or 0),
        "open": float(c.get("open", 0) or 0),
        "high": float(c.get("max") or c.get("high") or 0),
        "low": float(c.get("min") or c.get("low") or 0),
        "close": float(c.get("close", 0) or 0),
        "volume": float(c.get("volume", 0) or 0),
    }

def get_candles(session_id: str, asset: str, interval: int, count: int, include_current: bool = False):
    client = get_client(session_id)
    endtime = time.time()
    raw = _timed(lambda: client.get_candles(asset, interval, count, endtime), 20)
    if isinstance(raw, dict):
        raw = raw.get("candles") or raw.get("data") or []
    candles = [_normalize(x) for x in (raw or []) if isinstance(x, dict)]
    candles = sorted({c["time"]: c for c in candles}.values(), key=lambda x: x["time"])
    if not include_current:
        bucket = int(time.time()) // interval * interval
        candles = [x for x in candles if x["time"] < bucket]
    return candles[-count:]

def get_realtime_candle(session_id: str, asset: str, interval: int):
    client = get_client(session_id)
    try:
        data = client.get_realtime_candles(asset, interval)
        if isinstance(data, dict) and data:
            item = max(data.values(), key=lambda x: int(x.get("from", 0)))
            return _normalize(item)
    except Exception:
        pass
    return None

def start_stream(session_id: str, asset: str, interval: int):
    client = get_client(session_id)
    try:
        client.start_candles_stream(asset, interval, 20)
    except Exception:
        pass

def stop_stream(session_id: str, asset: str, interval: int):
    try:
        get_client(session_id).stop_candles_stream(asset, interval)
    except Exception:
        pass

def session_count():
    with _LOCK:
        _cleanup()
        return len(_SESSIONS)
