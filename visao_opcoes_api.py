from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

# SOMENTE autenticação/sessão/ativos: login da VISÃO permanece delegado
# à implementação original já funcional do Guru IQ Option.
import guru_sinais_iqoption_api as iq_auth
import biquote_service
import visao_analise as engine

router = APIRouter(prefix="/api/visao-opcoes", tags=["VISÃO OPÇÕES"])

INTERVALS = {"1m": 60, "5m": 300, "15m": 900}
EXPIRIES = (1, 5, 15)
STRATEGIES = {
    "automatica": "Automática — escolhe 1 estratégia",
    **{key: value["name"] for key, value in engine.STRATEGIES.items()},
}

# Cache somente de dados de mercado. Perfis de indicadores ficam no navegador
# para que cada usuário tenha sua própria configuração.
CANDLE_CACHE: dict[str, tuple[float, list[dict[str, float]]]] = {}


class MarketAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str = "1m"
    strategy: str = "automatica"
    expiry_minutes: int = 1
    indicator_ids_by_strategy: dict[str, list[str]] | None = None


def _session(x_iq_session: str | None) -> dict[str, Any]:
    return iq_auth._get_session(x_iq_session)


def _clean_rows(raw: Any) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for item in raw or []:
        try:
            rows.append(
                {
                    "open": float(item["open"]),
                    "high": float(item.get("max", item.get("high"))),
                    "low": float(item.get("min", item.get("low"))),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume") or 0),
                    "time": float(item.get("from", item.get("to", 0)) or 0),
                }
            )
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda item: item["time"])
    return [row for row in rows if row["time"] > 0 and row["high"] >= row["low"]]


def _profile_map(raw: dict[str, list[str]] | None) -> dict[str, list[str]]:
    return engine.sanitize_profiles(raw)


def _profiles_from_query(profiles_json: str | None) -> dict[str, list[str]]:
    if not profiles_json:
        return engine.default_profiles()
    try:
        raw = json.loads(profiles_json)
    except Exception:
        return engine.default_profiles()
    return _profile_map(raw)


def _is_forming(row: dict[str, float], timeframe: str, now: float | None = None) -> bool:
    now = now or time.time()
    return row["time"] + INTERVALS[timeframe] > now - 1


def _closed(rows: list[dict[str, float]], timeframe: str) -> list[dict[str, float]]:
    if not rows:
        return []
    closed = [row for row in rows if not _is_forming(row, timeframe)]
    if len(closed) >= 60:
        return closed
    return rows[:-1] if len(rows) > 1 else []


async def _get_base_candles(
    client: Any,
    sid: str,
    symbol: str,
    count: int = 1000,
) -> list[dict[str, float]]:
    symbol = symbol.upper().strip()
    key = f"{sid}|{symbol}|1m|{count}"
    cached = CANDLE_CACHE.get(key)
    if cached and time.time() - cached[0] <= 0.8:
        return cached[1]

    try:
        raw = await asyncio.wait_for(
            client.get_candles(
                symbol,
                60,
                min(max(count, 240), 1000),
                int(time.time()),
            ),
            timeout=6.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, f"A IQ Option demorou para responder aos candles de {symbol}.") from exc
    except KeyError as exc:
        raise HTTPException(502, f"O ativo {symbol} não está mapeado na API da IQ Option.") from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha ao ler candles da IQ Option: {str(exc)[:180]}") from exc

    rows = _clean_rows(raw)
    if len(rows) < 80:
        raise HTTPException(502, f"A IQ Option forneceu poucos candles para {symbol}.")
    CANDLE_CACHE[key] = (time.time(), rows)
    return rows


def _analysis_result(
    base: list[dict[str, float]],
    expiry: int,
    strategy: str,
    profiles: dict[str, list[str]] | None,
) -> dict[str, Any]:
    return engine.analyze_market(base, expiry, strategy, profiles)


def _facts_for_symbol(symbol: str) -> dict[str, Any]:
    facts = biquote_service.get_facts(hours=24, importance="all", symbol=symbol)
    high = [
        event
        for event in facts.get("events", [])
        if event.get("importance") in {"high", "holiday"}
    ]
    return {
        "source": "Biquote",
        "events": facts.get("events", []),
        "highImpactNearby": high,
        "available": facts.get("available", False),
        "warning": facts.get("warning"),
    }


def _pair_assets() -> list[str]:
    assets = iq_auth._asset_list()
    normal = [
        item["symbol"]
        for item in assets.get("normal", [])
        if item.get("symbol")
    ]
    otc = [
        item["symbol"]
        for item in assets.get("otc", [])
        if item.get("symbol")
    ]
    return list(dict.fromkeys(normal + otc))


async def _analyze_pair_for_radar(
    client: Any,
    sid: str,
    symbol: str,
    timeframe: str,
    expiry: int,
    strategy: str,
    profiles: dict[str, list[str]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        base = await _get_base_candles(client, sid, symbol, 1000)
        result = _analysis_result(base, expiry, strategy, profiles)

        base_symbol = symbol.replace("-OTC", "").replace("/", "")
        currencies = {base_symbol[:3], base_symbol[3:]} if len(base_symbol) == 6 else set()
        high_nearby = [
            event
            for event in events
            if str(event.get("currency", "")).upper() in currencies
            and event.get("importance") in {"high", "holiday"}
        ]

        return {
            "symbol": symbol,
            "signal": result["signal"] if result["signal"] in {"CALL", "PUT"} else "SEM SINAL",
            "direction": result["mtf"]["setup"]["direction"],
            "proximity": round(float(result["score"] or 0), 1),
            "confidence": round(float(result["mtf"]["setup"]["confidence"] or 0), 1),
            "strategy": result["strategy"],
            "strategyLabel": result["strategyLabel"],
            "price": result["price"],
            "buyScore": result["buyScore"],
            "sellScore": result["sellScore"],
            "newsCount": len(high_nearby),
            "newsBlocked": bool(high_nearby),
            "indicatorCount": result["profile"]["totalSelected"],
        }
    except Exception as exc:
        return {"symbol": symbol, "signal": "ERRO", "status": str(exc)[:120]}


async def _pair_radar(
    client: Any,
    sid: str,
    timeframe: str,
    expiry: int,
    strategy: str,
    profiles: dict[str, list[str]],
    include_otc: bool = True,
) -> list[dict[str, Any]]:
    assets = _pair_assets()
    if not include_otc:
        assets = [symbol for symbol in assets if not symbol.endswith("-OTC")]

    all_facts = biquote_service.get_facts(hours=2, importance="high", symbol="")
    events = all_facts.get("events", [])
    semaphore = asyncio.Semaphore(5)

    async def run(symbol: str):
        async with semaphore:
            return await _analyze_pair_for_radar(
                client,
                sid,
                symbol,
                timeframe,
                expiry,
                strategy,
                profiles,
                events,
            )

    results = await asyncio.gather(*(run(symbol) for symbol in assets))
    valid = [item for item in results if item.get("signal") != "ERRO"]
    valid.sort(key=lambda item: -float(item.get("proximity", 0)))
    return valid


# -----------------------------------------------------------------------------
# Login: deliberadamente delegado ao módulo já existente. Não alterar o fluxo.
# -----------------------------------------------------------------------------
@router.post("/login")
async def login(req: iq_auth.IQLoginRequest):
    return await iq_auth.iq_login(req)


@router.get("/session")
async def session(x_iq_session: str | None = Header(default=None)):
    return await iq_auth.iq_session(x_iq_session)


@router.get("/assets")
async def assets(x_iq_session: str | None = Header(default=None)):
    return await iq_auth.iq_assets(x_iq_session)


@router.post("/logout")
async def logout(x_iq_session: str | None = Header(default=None)):
    return await iq_auth.iq_logout(x_iq_session)


@router.get("/strategy-config")
async def strategy_config(x_iq_session: str | None = Header(default=None)):
    _session(x_iq_session)
    return {
        "ok": True,
        "strategies": [
            {
                "id": "automatica",
                "name": STRATEGIES["automatica"],
                "description": "Escolhe uma única estratégia pelos sinais atuais; não mistura estratégias.",
            },
            *[
                {
                    "id": key,
                    "name": value["name"],
                    "description": value["description"],
                }
                for key, value in engine.STRATEGIES.items()
            ],
        ],
        "indicators": engine.indicator_catalog(),
        "defaultProfiles": engine.default_profiles(),
    }


@router.get("/facts")
async def visao_facts(
    hours: int = 24,
    importance: str = "all",
    symbol: str = "",
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    _session(x_iq_session)
    return biquote_service.get_facts(
        hours=max(1, min(hours, 168)),
        importance=importance,
        symbol=symbol,
    )


@router.get("/pair-analysis/{symbol}")
async def visao_pair_analysis(
    symbol: str,
    timeframe: str = "5m",
    strategy: str = "automatica",
    expiry: int = 5,
    profiles_json: str = "",
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = _session(x_iq_session)
    if timeframe not in INTERVALS:
        raise HTTPException(400, "Timeframe inválido.")
    if expiry not in EXPIRIES:
        raise HTTPException(400, "Expiração inválida.")
    if strategy not in STRATEGIES:
        raise HTTPException(400, "Estratégia inválida.")

    profiles = _profiles_from_query(profiles_json)
    analysis = _analysis_result(
        await _get_base_candles(item["client"], x_iq_session or "", symbol, 1000),
        expiry,
        strategy,
        profiles,
    )
    analysis["relevantFacts"] = _facts_for_symbol(symbol)
    analysis["automation"] = {"enabled": False, "orders": False, "execution": False}
    return analysis


@router.get("/pair-radar")
async def visao_pair_radar(
    timeframe: str = "5m",
    strategy: str = "automatica",
    expiry: int = 5,
    limit: int = 16,
    include_otc: bool = True,
    profiles_json: str = "",
    x_iq_session: str | None = Header(default=None),
) -> dict[str, Any]:
    item = _session(x_iq_session)
    if timeframe not in INTERVALS:
        raise HTTPException(400, "Timeframe inválido.")
    if expiry not in EXPIRIES:
        raise HTTPException(400, "Expiração inválida.")
    if strategy not in STRATEGIES:
        raise HTTPException(400, "Estratégia inválida.")

    profiles = _profiles_from_query(profiles_json)
    results = await _pair_radar(
        item["client"],
        x_iq_session or "",
        timeframe,
        expiry,
        strategy,
        profiles,
        include_otc,
    )
    return {
        "ok": True,
        "timeframe": timeframe,
        "expiry": expiry,
        "strategy": strategy,
        "pairs": results[: max(1, min(limit, 30))],
        "totalAnalyzed": len(results),
        "source": "IQ Option + motor market-insight-ai + Biquote",
        "automation": {"enabled": False, "orders": False, "execution": False},
    }


@router.post("/market-analysis")
async def market_analysis(
    req: MarketAnalysisRequest,
    x_iq_session: str | None = Header(default=None),
):
    item = _session(x_iq_session)
    if req.timeframe not in INTERVALS:
        raise HTTPException(400, "Período de vela inválido.")
    if req.expiry_minutes not in EXPIRIES:
        raise HTTPException(400, "Expiração deve ser 1, 5 ou 15 minutos.")
    if req.strategy not in STRATEGIES:
        raise HTTPException(400, "Estratégia inválida.")

    try:
        started = time.perf_counter()
        candle_count = {1:240, 5:420, 15:1000}[req.expiry_minutes]
        base = await _get_base_candles(
            item["client"],
            x_iq_session or "",
            req.symbol,
            candle_count,
        )
        profiles = _profile_map(req.indicator_ids_by_strategy)
        analysis = _analysis_result(
            base,
            req.expiry_minutes,
            req.strategy,
            profiles,
        )
        analysis["timeframe"] = analysis["analysisTimeframes"]["setup"]
        analysis["candlePeriod"] = analysis["analysisTimeframes"]["setup"]
        analysis["expiryMinutes"] = req.expiry_minutes
        analysis["optionType"] = "binary"
        analysis["optionLabel"] = "Binárias"
        analysis["symbol"] = req.symbol.upper().strip()
        analysis["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        analysis["serverEpoch"] = time.time()
        # O calendário Biquote fica na aba Fatos; não bloqueia a leitura técnica principal.
        analysis["relevantFacts"] = {"source":"Biquote","events":[],"available":None,"warning":None}
        analysis["automation"] = {"enabled": False, "orders": False, "execution": False}
        analysis["diagnostics"]["serverDurationMs"] = round((time.perf_counter() - started) * 1000)
        analysis["diagnostics"]["profileSource"] = "navegador" if req.indicator_ids_by_strategy else "padrão market-insight-ai"
        return {"ok": True, "analysis": analysis}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(502, f"Falha durante a análise da Visão Opções: {exc}") from exc
    except Exception as exc:
        raise HTTPException(502, f"Falha durante a análise da Visão Opções: {str(exc)[:220]}") from exc
