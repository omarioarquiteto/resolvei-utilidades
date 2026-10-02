"""Calendário econômico da Biquote para exibir fatos relevantes do mercado."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import threading
import time
import requests

CALENDAR_URL = (os.getenv("BIQUOTE_CALENDAR_URL") or "").strip() or "https://biquote.io/api/calendar/upcoming"
CACHE_SECONDS = 60
_cache = {"expires_at": 0.0, "payload": None}
_lock = threading.Lock()

CURRENCIES = {
    "EUR", "GBP", "USD", "JPY", "CHF", "CAD", "AUD", "NZD",
}

DESCRIPTIONS = {
    "interest rate": "Decisão ou referência de juros, capaz de alterar expectativas sobre a moeda.",
    "inflation": "Indicador de inflação, relevante para expectativas de juros e poder de compra.",
    "cpi": "Índice de preços ao consumidor, um dos principais indicadores de inflação.",
    "ppi": "Índice de preços ao produtor, sinal de pressão de custos.",
    "employment": "Indicador do mercado de trabalho, relevante para expectativas econômicas.",
    "nonfarm": "Relatório de emprego dos EUA, normalmente acompanhado com atenção pelo mercado.",
    "payroll": "Dados de criação de empregos, relevantes para expectativas sobre o dólar.",
    "gdp": "Produto Interno Bruto, indicador do ritmo de atividade econômica.",
    "retail sales": "Vendas no varejo, indicador da força do consumo.",
    "unemployment": "Taxa de desemprego, indicador da condição do mercado de trabalho.",
    "manufacturing": "Atividade industrial e manufatureira.",
    "services": "Atividade do setor de serviços.",
    "pmi": "Índice de gerentes de compras; ajuda a acompanhar expansão ou contração.",
    "central bank": "Comunicação ou decisão de banco central, com potencial de mexer nas expectativas.",
}


def _payload() -> list[dict]:
    now = time.monotonic()
    with _lock:
        if _cache["payload"] is not None and _cache["expires_at"] > now:
            return _cache["payload"]
        response = requests.get(CALENDAR_URL, timeout=8)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("A Biquote não retornou uma lista de eventos.")
        _cache.update(payload=data, expires_at=now + CACHE_SECONDS)
        return data


def _parse_time(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _describe(name: str, sector: str | None = None) -> str:
    text = f"{name} {sector or ''}".lower()
    for key, value in DESCRIPTIONS.items():
        if key in text:
            return value
    return "Evento macroeconômico agendado; a divulgação pode aumentar a volatilidade."


def currencies_for_pair(symbol: str) -> set[str]:
    raw = str(symbol or "").upper().replace("-OTC", "").replace("=X", "")
    if len(raw) >= 6:
        found = {raw[:3], raw[3:6]}
        return {x for x in found if x in CURRENCIES}
    return set()


def get_facts(hours: int = 24, importance: str = "all", symbol: str = "") -> dict:
    try:
        data = _payload()
    except Exception as exc:
        return {
            "available": False,
            "source": "Biquote",
            "events": [],
            "hours": hours,
            "warning": f"Calendário Biquote indisponível: {str(exc)[:180]}",
        }

    now = datetime.now(timezone.utc)
    limit = now.timestamp() + max(1, min(int(hours or 24), 168)) * 3600
    pair_currencies = currencies_for_pair(symbol) if symbol else CURRENCIES
    events = []

    for item in data:
        if not isinstance(item, dict):
            continue
        dt = _parse_time(item.get("time"))
        if dt is None:
            continue
        ts = dt.timestamp()
        if ts < now.timestamp() or ts > limit:
            continue
        currency = str(item.get("currency") or item.get("countryCode") or "").upper().strip()
        if currency and currency not in pair_currencies:
            continue
        imp = str(item.get("importance") or "low").lower().strip()
        if importance != "all" and imp != importance:
            continue
        events.append({
            "id": item.get("id"),
            "currency": currency or "—",
            "title": str(item.get("name") or "Evento econômico"),
            "description": _describe(str(item.get("name") or "Evento econômico"), item.get("sector")),
            "importance": imp,
            "time": dt.isoformat(),
            "actual": item.get("actual"),
            "forecast": item.get("forecast"),
            "previous": item.get("previous"),
            "sector": item.get("sector"),
        })

    events.sort(key=lambda x: x["time"])
    return {
        "available": True,
        "source": "Biquote",
        "events": events,
        "hours": hours,
        "symbol": symbol.upper() if symbol else None,
        "warning": None,
    }
