from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import guru_sinais_api as guru_base

router = APIRouter(prefix="/api/guru-sinais-iqoption", tags=["GURÚ DOS SINAIS IQOPTION"])

SESSION_TTL_SECONDS = 45 * 60
LOGIN_TIMEOUT_SECONDS = 25
REQUEST_TIMEOUT_SECONDS = 12
SESSIONS: dict[str, dict[str, Any]] = {}
ASSET_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CANDLE_CACHE: dict[str, tuple[float, list[dict[str, float]]]] = {}
BACKTEST_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}

OPTION_LABELS = {"binary": "Binárias", "digital": "Digitais", "blitz": "Blitz"}
OPTION_EXPIRIES = {"binary": (1, 5, 15), "digital": (1, 5, 15), "blitz": (30, 60)}

def _normalize_option_config(option_type: str, expiry_minutes: int) -> tuple[str, int]:
    option_type = str(option_type or "binary").strip().lower()
    if option_type not in OPTION_LABELS:
        raise HTTPException(status_code=400, detail="Tipo de opção não suportado.")
    try:
        expiry = int(expiry_minutes)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Tempo de expiração inválido.")
    if expiry not in OPTION_EXPIRIES[option_type]:
        allowed = ", ".join(str(x) + (" min" if option_type != "blitz" else " s") for x in OPTION_EXPIRIES[option_type])
        raise HTTPException(status_code=400, detail=f"Expiração inválida para {OPTION_LABELS[option_type]}. Escolha: {allowed}.")
    return option_type, expiry

def _iq_mtf_plan(candle_period: str, expiry_value: int, option_type: str) -> tuple[str, str, str]:
    context_tf, setup_tf, trigger_tf = guru_base._mtf_plan(candle_period)
    if option_type == "blitz":
        # Blitz usa expiração em segundos; o gatilho precisa ficar na escala de 1m,
        # que é a resolução histórica/realtime disponível nesta integração.
        trigger_tf = "1m"
        return context_tf, setup_tf, trigger_tf
    expiry_seconds = int(expiry_value) * 60
    if INTERVALS.get(trigger_tf, 60) > expiry_seconds:
        candidates = [tf for tf in ("1m", "5m", "15m") if INTERVALS[tf] <= expiry_seconds]
        if candidates:
            trigger_tf = max(candidates, key=lambda tf: INTERVALS[tf])
    return context_tf, setup_tf, trigger_tf


class IQLoginRequest(BaseModel):
    email: str
    password: str


class MarketAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str
    strategy: str = "automatica"
    option_type: str = "binary"
    expiry_minutes: int = 5
    analyze_with_ai: bool = False
    fast_mode: bool = False


def _client_class() -> Any:
    try:
        from iqoptionapi.aio import AsyncIQOption
        return AsyncIQOption
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="O cliente assíncrono da iqoptionapi não está disponível no servidor.",
        ) from exc


def _cleanup() -> None:
    now = time.time()
    cutoff = now - SESSION_TTL_SECONDS

    expired: list[tuple[str, Any]] = []
    for sid, item in list(SESSIONS.items()):
        if item.get("last_used", 0) < cutoff:
            expired.append((sid, item))

    for sid, item in expired:
        SESSIONS.pop(sid, None)
        ASSET_CACHE.pop(sid, None)
        for key in list(BACKTEST_CACHE):
            if key.startswith(sid + "|"):
                BACKTEST_CACHE.pop(key, None)
        for key in list(CANDLE_CACHE):
            if key.startswith(sid + "|"):
                CANDLE_CACHE.pop(key, None)
        client = item.get("client")
        if client is not None:
            try:
                asyncio.create_task(client.close())
            except Exception:
                pass

    for cache, ttl in ((ASSET_CACHE, 120), (CANDLE_CACHE, 40), (BACKTEST_CACHE, 180)):
        for key, (ts, _) in list(cache.items()):
            if now - ts > ttl:
                cache.pop(key, None)


def _new_session(client: Any, email: str) -> str:
    _cleanup()
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = {
        "client": client,
        "email": email,
        "last_used": time.time(),
    }
    return sid


def _get_session(session_id: str | None) -> dict[str, Any]:
    sid = (session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=401, detail="Conecte sua conta da IQ Option primeiro.")

    _cleanup()
    item = SESSIONS.get(sid)
    if not item:
        raise HTTPException(
            status_code=401,
            detail="A sessão da IQ Option expirou. Faça login novamente.",
        )
    item["last_used"] = time.time()
    return item


def _asset_list() -> dict[str, Any]:
    try:
        import iqoptionapi.constants as iq_constants
        active_map = dict(iq_constants.ACTIVES)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível carregar a tabela de ativos da iqoptionapi.",
        ) from exc

    normal: list[dict[str, Any]] = []
    otc: list[dict[str, Any]] = []

    for symbol, active_id in active_map.items():
        name = str(symbol or "").upper()
        is_otc = name.endswith("-OTC")
        base = name[:-4] if is_otc else name

        if not (len(base) == 6 and base.isalpha()):
            continue

        item = {
            "symbol": name,
            "market": "OTC" if is_otc else "normal",
            "type": "binary",
            "open": None,
            "active_id": int(active_id),
        }
        (otc if is_otc else normal).append(item)

    normal.sort(key=lambda x: x["symbol"])
    otc.sort(key=lambda x: x["symbol"])

    return {
        "normal": normal,
        "otc": otc,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def _candles(client: Any, session_id: str, symbol: str, timeframe: str, count: int = 1000) -> list[dict[str, float]]:
    size = INTERVALS.get(timeframe)
    if not size:
        raise HTTPException(status_code=400, detail="Timeframe não suportado.")

    symbol = str(symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Informe o ativo da IQ Option.")

    key = f"{session_id}|{symbol}|{timeframe}|{count}"
    cached = CANDLE_CACHE.get(key)
    if cached and time.time() - cached[0] < 8:
        return cached[1]

    try:
        raw = await asyncio.wait_for(
            client.get_candles(symbol, size, count, int(time.time())),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"A IQ Option não respondeu aos candles de {symbol} dentro do tempo limite.",
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"O ativo {symbol} não está mapeado na versão atual da iqoptionapi.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar candles da IQ Option: {str(exc)[:180]}",
        ) from exc

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
                    "datetime": float(item.get("from", item.get("to", 0)) or 0),
                }
            )
        except (TypeError, ValueError, KeyError):
            continue

    rows.sort(key=lambda x: x["datetime"])
    rows = _closed_candle_rows(rows, size)
    if len(rows) < 60:
        raise HTTPException(
            status_code=502,
            detail=f"A IQ Option retornou somente {len(rows)} candles para {symbol}; são necessários pelo menos 60.",
        )

    CANDLE_CACHE[key] = (time.time(), rows)
    return rows



def _normalize_stream_candle(item: Any) -> dict[str, float] | None:
    try:
        row = {
            "open": float(item["open"]),
            "high": float(item.get("max", item.get("high"))),
            "low": float(item.get("min", item.get("low"))),
            "close": float(item["close"]),
            "volume": float(item.get("volume") or 0),
            "datetime": float(item.get("from", item.get("to", 0)) or 0),
        }
        if row["high"] < row["low"] or row["datetime"] <= 0:
            return None
        return row
    except (TypeError, ValueError, KeyError):
        return None


async def _latest_realtime_candle(
    client: Any,
    symbol: str,
    timeframe: str,
) -> dict[str, float] | None:
    size = INTERVALS.get(timeframe)
    if not size:
        return None

    async def _read_one() -> dict[str, float] | None:
        async for item in client.stream_candles(symbol, size):
            return _normalize_stream_candle(item)
        return None

    try:
        return await asyncio.wait_for(_read_one(), timeout=3.5)
    except Exception:
        # O streaming é um reforço de precisão do gatilho. Se ficar indisponível,
        # mantemos a análise histórica em vez de derrubar toda a operação.
        return None


def _closed_candle_rows(rows: list[dict[str, float]], size: int) -> list[dict[str, float]]:
    now = time.time()
    closed = [
        row for row in rows
        if not row.get("datetime") or row["datetime"] + size <= now - 1
    ]
    if len(closed) >= 60:
        return closed
    # Evita perder a análise inteira em caso de relógio do servidor ligeiramente
    # desalinhado com a origem dos candles.
    return rows[:-1] if len(rows) > 60 else rows


async def _mtf_for_symbol(
    client: Any,
    session_id: str,
    symbol: str,
    timeframe: str,
    expiry_minutes: int,
    option_type: str,
    count: int = 1000,
) -> tuple[dict[str, list[dict[str, float]]], tuple[str, str, str], bool]:
    plan = _iq_mtf_plan(timeframe, expiry_minutes, option_type)
    rows: dict[str, list[dict[str, float]]] = {}

    unique_tfs = list(dict.fromkeys(plan))
    safe_count = max(80, min(int(count or 1000), 1000))
    results = await asyncio.gather(
        *[_candles(client, session_id, symbol, tf, safe_count) for tf in unique_tfs]
    )

    for tf, data in zip(unique_tfs, results):
        rows[tf] = data

    context_tf, setup_tf, trigger_tf = plan
    live_trigger = await _latest_realtime_candle(client, symbol, trigger_tf)

    # O histórico é calculado somente com candles fechados. O candle em formação
    # entra apenas no timeframe de gatilho, para que o sinal reflita o preço atual.
    live_used = False
    if live_trigger:
        trigger_rows = rows.get(trigger_tf) or []
        last_ts = trigger_rows[-1]["datetime"] if trigger_rows else 0.0
        if trigger_rows and live_trigger["datetime"] == last_ts:
            rows[trigger_tf] = trigger_rows[:-1] + [live_trigger]
            live_used = True
        elif live_trigger["datetime"] > last_ts:
            rows[trigger_tf] = trigger_rows + [live_trigger]
            live_used = True

    return rows, plan, live_used

def _candle_metrics(candle: dict[str, float]) -> dict[str, float]:
    rng = max(candle["high"] - candle["low"], 1e-12)
    body = abs(candle["close"] - candle["open"])
    upper = candle["high"] - max(candle["open"], candle["close"])
    lower = min(candle["open"], candle["close"]) - candle["low"]
    location = (candle["close"] - candle["low"]) / rng
    return {
        "range": rng,
        "body": body,
        "body_ratio": body / rng,
        "upper_wick": upper / rng,
        "lower_wick": lower / rng,
        "close_location": location,
    }


def _iq_score_signal(items: list[tuple[str, float, str, str]]) -> tuple[float, float, float, int]:
    """
    Pontua grupos independentes em vez de somar indiscriminadamente indicadores
    correlacionados. Dentro de um grupo, somente o sinal dominante conta.
    """
    groups: dict[str, list[tuple[float, str]]] = {}
    for _, weight, direction, group in items:
        groups.setdefault(group, []).append((weight, direction))

    buy = sell = 0.0
    active_groups = 0
    total_groups = len(groups)

    for values in groups.values():
        call_weight = sum(w for w, d in values if d == "CALL")
        put_weight = sum(w for w, d in values if d == "PUT")
        if not call_weight and not put_weight:
            continue
        strongest = max(call_weight, put_weight)
        weakest = min(call_weight, put_weight)
        # Se o grupo estiver dividido, ele não aumenta a confiança.
        if strongest <= weakest * 1.35:
            continue
        side = "CALL" if call_weight > put_weight else "PUT"
        group_weight = max([w for w, d in values if d == side] or [0.0])
        if group_weight <= 0:
            continue
        active_groups += 1
        if side == "CALL":
            buy += group_weight
        else:
            sell += group_weight

    active_weight = buy + sell
    if not active_weight:
        return 0.0, 0.0, 50.0, 0

    dominance = abs(buy - sell) / active_weight
    coverage = active_groups / max(total_groups, 1)
    agreement = max(buy, sell) / active_weight
    confidence = 50.0 + 50.0 * (
        0.55 * dominance + 0.30 * coverage + 0.15 * agreement
    )
    return buy, sell, min(99.0, confidence), active_groups


def _iq_strategy_pack(rows: list[dict[str, float]], strategy: str) -> dict[str, Any]:
    """
    Estratégias exclusivas do GURÚ IQ Option.
    As famílias continuam isoladas; o motor não mistura sinais de estratégias
    diferentes. A pontuação usa grupos independentes para reduzir dupla contagem.
    """
    closes = [x["close"] for x in rows]
    if len(closes) < 60:
        raise HTTPException(status_code=502, detail="Candles insuficientes para a estratégia.")

    e9, e21, e50 = [guru_base.ema(closes, p)[-1] for p in (9, 21, 50)]
    e9_prev = guru_base.ema(closes[:-1], 9)[-1]
    e9_prev2 = guru_base.ema(closes[:-2], 9)[-1] if len(closes) > 2 else e9_prev
    r = guru_base.rsi(closes)
    macd, macd_signal = guru_base.macd_values(closes)
    hist = macd - macd_signal
    prev_macd, prev_signal = guru_base.macd_values(closes[:-1])
    prev_hist = prev_macd - prev_signal
    roc = guru_base._roc(closes)
    adx, di_diff = guru_base._adx(rows)
    atr = guru_base._atr_value(rows, 14)
    atr_prev = guru_base._atr_value(rows[:-8], 14) if len(rows) > 40 else atr
    atr_pct = atr / closes[-1] * 100 if closes[-1] else 0.0

    st_k, st_d = guru_base._stochastic(rows)
    cci = guru_base._cci(rows)
    willr = guru_base._williams_r(rows)
    candle = guru_base.candle_pattern(rows)

    current_cm = _candle_metrics(rows[-1])
    current_body_ratio = current_cm["body_ratio"]
    close_location = current_cm["close_location"]

    high20 = max(x["high"] for x in rows[-20:])
    low20 = min(x["low"] for x in rows[-20:])
    prev_high20 = max(x["high"] for x in rows[-21:-1])
    prev_low20 = min(x["low"] for x in rows[-21:-1])

    close = closes[-1]
    extension_from_e21 = abs(close - e21) / max(atr, close * 1e-8)
    ema_slope_atr = (e9 - e9_prev2) / max(atr, close * 1e-8)

    bull_trend = e9 > e21 > e50
    bear_trend = e9 < e21 < e50
    strong_bull_context = bull_trend and adx >= 24 and di_diff > 4
    strong_bear_context = bear_trend and adx >= 24 and di_diff < -4

    structure = (
        "CALL"
        if closes[-1] > closes[-3] > closes[-6]
        else "PUT"
        if closes[-1] < closes[-3] < closes[-6]
        else "NEUTRA"
    )

    breakout_up = close > prev_high20
    breakout_down = close < prev_low20
    breakout_up_distance = (close - prev_high20) / max(atr, 1e-12)
    breakout_down_distance = (prev_low20 - close) / max(atr, 1e-12)
    atr_expanding = atr > atr_prev * 1.04

    # Evita transformar uma vela já esticada em entrada atrasada.
    extension_ok_call = e21 <= close <= e21 + max(0.95 * atr, close * 0.00005)
    extension_ok_put = e21 - max(0.95 * atr, close * 0.00005) <= close <= e21

    # Candle de rejeição: útil sobretudo na reversão e no reteste.
    rejection_call = (
        current_cm["lower_wick"] >= 0.32
        and current_cm["lower_wick"] > current_cm["upper_wick"] * 1.25
        and close_location >= 0.62
    )
    rejection_put = (
        current_cm["upper_wick"] >= 0.32
        and current_cm["upper_wick"] > current_cm["lower_wick"] * 1.25
        and close_location <= 0.38
    )

    sweep_support = rows[-1]["low"] < prev_low20 and close > prev_low20
    sweep_resistance = rows[-1]["high"] > prev_high20 and close < prev_high20

    if strategy == "tendencia":
        items = [
            ("Alinhamento EMA", 2.0, "CALL" if bull_trend else "PUT" if bear_trend else "NEUTRA", "regime"),
            ("ADX + DI", 1.5, "CALL" if adx >= 20 and di_diff >= 3 else "PUT" if adx >= 20 and di_diff <= -3 else "NEUTRA", "regime"),
            ("Estrutura", 1.3, structure, "estrutura"),
            ("MACD + aceleração", 1.2, "CALL" if hist > 0 and hist >= prev_hist else "PUT" if hist < 0 and hist <= prev_hist else "NEUTRA", "momentum"),
            ("Inclinação EMA 9", 1.0, "CALL" if ema_slope_atr > 0.02 else "PUT" if ema_slope_atr < -0.02 else "NEUTRA", "momentum"),
            ("Pullback/reclaim EMA21", 1.4, "CALL" if bull_trend and rows[-1]["low"] <= e21 + 0.25 * atr and close > e21 and close_location >= 0.58 else "PUT" if bear_trend and rows[-1]["high"] >= e21 - 0.25 * atr and close < e21 and close_location <= 0.42 else "NEUTRA", "entrada"),
            ("Candle de continuidade", 1.1, "CALL" if close > rows[-2]["close"] and current_body_ratio >= 0.55 and close_location >= 0.70 else "PUT" if close < rows[-2]["close"] and current_body_ratio >= 0.55 and close_location <= 0.30 else "NEUTRA", "entrada"),
            ("RSI de regime", 0.8, "CALL" if 52 <= r <= 68 else "PUT" if 32 <= r <= 48 else "NEUTRA", "momentum"),
        ]
        min_confidence, required_groups, label = 76.0, 4, "Tendência"

    elif strategy == "reversao":
        range_regime = adx < 20 and abs(e9 - e21) <= max(0.55 * atr, close * 0.00004)
        near_support = (close - low20) <= max(0.35 * atr, close * 0.00005)
        near_resistance = (high20 - close) <= max(0.35 * atr, close * 0.00005)

        items = [
            ("Regime lateral", 1.2, "CALL" if range_regime and near_support else "PUT" if range_regime and near_resistance else "NEUTRA", "regime"),
            ("Extremo de RSI", 1.4, "CALL" if r <= 28 else "PUT" if r >= 72 else "NEUTRA", "oscilador"),
            ("Stochastic", 1.1, "CALL" if st_k <= 25 and st_k >= st_d else "PUT" if st_k >= 75 and st_k <= st_d else "NEUTRA", "oscilador"),
            ("CCI/Williams extremo", 0.8, "CALL" if cci <= -100 or willr <= -80 else "PUT" if cci >= 100 or willr >= -20 else "NEUTRA", "oscilador"),
            ("Rejeição de suporte/resistência", 1.7, "CALL" if near_support and rejection_call else "PUT" if near_resistance and rejection_put else "NEUTRA", "entrada"),
            ("Sweep/falso rompimento", 1.5, "CALL" if sweep_support and rejection_call else "PUT" if sweep_resistance and rejection_put else "NEUTRA", "entrada"),
            ("Candle de reversão", 0.9, "CALL" if candle == "engolfo de alta" or (current_body_ratio >= 0.45 and close > rows[-2]["close"] and close_location >= 0.68) else "PUT" if candle == "engolfo de baixa" or (current_body_ratio >= 0.45 and close < rows[-2]["close"] and close_location <= 0.32) else "NEUTRA", "entrada"),
        ]
        blocked = strong_bull_context or strong_bear_context
        min_confidence, required_groups, label = 77.0, 4, "Reversão"
        if blocked:
            for idx, item in enumerate(items):
                items[idx] = (item[0], item[1], "NEUTRA", item[3])

    elif strategy == "rompimento":
        clean_breakout_call = (
            breakout_up
            and 0.08 <= breakout_up_distance <= 0.90
            and current_body_ratio >= 0.55
            and close_location >= 0.72
        )
        clean_breakout_put = (
            breakout_down
            and 0.08 <= breakout_down_distance <= 0.90
            and current_body_ratio >= 0.55
            and close_location <= 0.28
        )
        retest_call = (
            rows[-2]["close"] <= prev_high20
            and rows[-1]["low"] <= prev_high20 + 0.18 * atr
            and close > prev_high20
            and close_location >= 0.58
        )
        retest_put = (
            rows[-2]["close"] >= prev_low20
            and rows[-1]["high"] >= prev_low20 - 0.18 * atr
            and close < prev_low20
            and close_location <= 0.42
        )
        items = [
            ("Rompimento limpo", 2.0, "CALL" if clean_breakout_call else "PUT" if clean_breakout_put else "NEUTRA", "breakout"),
            ("Reteste da zona", 1.7, "CALL" if retest_call else "PUT" if retest_put else "NEUTRA", "breakout"),
            ("ADX + DI", 1.4, "CALL" if adx >= 20 and di_diff >= 3 else "PUT" if adx >= 20 and di_diff <= -3 else "NEUTRA", "regime"),
            ("Expansão ATR", 1.0, "CALL" if atr_expanding and close > rows[-2]["close"] else "PUT" if atr_expanding and close < rows[-2]["close"] else "NEUTRA", "volatilidade"),
            ("MACD", 0.9, "CALL" if hist > 0 else "PUT" if hist < 0 else "NEUTRA", "momentum"),
            ("Estrutura", 0.9, structure, "estrutura"),
            ("Candle de força", 1.0, "CALL" if current_body_ratio >= 0.60 and close_location >= 0.74 else "PUT" if current_body_ratio >= 0.60 and close_location <= 0.26 else "NEUTRA", "entrada"),
        ]
        min_confidence, required_groups, label = 77.0, 4, "Rompimento"

    elif strategy == "momentum":
        impulse_call = close > rows[-2]["close"] and current_body_ratio >= 0.58 and close_location >= 0.72
        impulse_put = close < rows[-2]["close"] and current_body_ratio >= 0.58 and close_location <= 0.28
        items = [
            ("Regime EMA", 1.6, "CALL" if e9 > e21 > e50 else "PUT" if e9 < e21 < e50 else "NEUTRA", "regime"),
            ("ADX + DI", 1.2, "CALL" if adx >= 19 and di_diff >= 3 else "PUT" if adx >= 19 and di_diff <= -3 else "NEUTRA", "regime"),
            ("MACD + aceleração", 1.6, "CALL" if hist > 0 and hist > prev_hist else "PUT" if hist < 0 and hist < prev_hist else "NEUTRA", "momentum"),
            ("Inclinação EMA 9", 1.1, "CALL" if ema_slope_atr > 0.025 else "PUT" if ema_slope_atr < -0.025 else "NEUTRA", "momentum"),
            ("ROC", 1.0, "CALL" if roc > 0.05 else "PUT" if roc < -0.05 else "NEUTRA", "momentum"),
            ("RSI de impulso", 0.9, "CALL" if 53 <= r <= 68 else "PUT" if 32 <= r <= 47 else "NEUTRA", "oscilador"),
            ("Estrutura", 1.1, structure, "estrutura"),
            ("Candle de impulso", 1.1, "CALL" if impulse_call else "PUT" if impulse_put else "NEUTRA", "entrada"),
            ("Filtro anti-extensão", 1.0, "CALL" if extension_ok_call else "PUT" if extension_ok_put else "NEUTRA", "risco"),
        ]
        min_confidence, required_groups, label = 76.0, 5, "Momentum"

    else:
        raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    buy, sell, confidence, active_groups = _iq_score_signal(items)
    direction = "CALL" if buy > sell else "PUT" if sell > buy else "NEUTRA"
    signal_eligible = (
        direction in {"CALL", "PUT"}
        and confidence >= min_confidence
        and active_groups >= required_groups
    )
    if min(buy, sell) > 0 and max(buy, sell) / min(buy, sell) < 1.25:
        signal_eligible = False

    values = {
        "EMA9": e9,
        "EMA21": e21,
        "EMA50": e50,
        "RSI": r,
        "MACD": macd,
        "MACDSignal": macd_signal,
        "MACDHistogram": hist,
        "ATRpct": atr_pct,
        "ADX": adx,
        "DIplusMinus": di_diff,
        "ROC": roc,
        "StochasticK": st_k,
        "StochasticD": st_d,
        "CCI": cci,
        "WilliamsR": willr,
        "Candle": candle,
        "PriceStructure": structure,
        "BodyRatio": current_body_ratio,
        "CloseLocation": close_location,
        "EMASlopeATR": ema_slope_atr,
        "ExtensionATR": extension_from_e21,
        "BreakoutDistanceATR": max(breakout_up_distance, breakout_down_distance, 0.0),
        "ATRExpanding": atr_expanding,
    }

    return {
        "strategy": strategy,
        "strategyLabel": label,
        "buy": round(buy, 2),
        "sell": round(sell, 2),
        "confidence": round(confidence, 1),
        "direction": direction,
        "signalEligible": signal_eligible,
        "minConfidence": min_confidence,
        "requiredGroups": required_groups,
        "activeGroups": active_groups,
        "indicators": [
            {"name": n, "weight": w, "signal": d}
            for n, w, d, _ in items
        ],
        "values": values,
    }



def _trigger_state(
    rows: list[dict[str, float]],
    timeframe: str,
    direction: str,
) -> dict[str, Any]:
    """Determina o momento operacional sem transformar o candle em formação no
    único responsável pela direção do sinal."""
    size = INTERVALS.get(timeframe, 60)
    if not rows or direction not in {"CALL", "PUT"}:
        return {
            "ready": False,
            "status": "SEM DIREÇÃO",
            "instruction": "A análise ainda não definiu uma direção.",
            "secondsRemaining": 0,
            "elapsedSeconds": 0,
        }

    now = time.time()
    candle = rows[-1]
    start_ts = float(candle.get("datetime") or 0)
    elapsed = max(0.0, now - start_ts) if start_ts else 0.0
    remaining = max(0.0, size - elapsed)

    cm = _candle_metrics(candle)
    prev = rows[-2] if len(rows) >= 2 else candle
    price_up = candle["close"] > prev["close"]
    price_down = candle["close"] < prev["close"]

    # A entrada deve ocorrer enquanto ainda existe tempo suficiente para a vela
    # de gatilho confirmar, evitando entrar no fim do candle.
    early = elapsed <= max(12.0, size * 0.55)
    late = elapsed > max(45.0, size * 0.78)

    if direction == "CALL":
        confirmed = (
            price_up
            and cm["body_ratio"] >= 0.35
            and cm["close_location"] >= 0.55
        )
    else:
        confirmed = (
            price_down
            and cm["body_ratio"] >= 0.35
            and cm["close_location"] <= 0.45
        )

    if confirmed and early and not late:
        return {
            "ready": True,
            "status": "ENTRADA CONFIRMADA",
            "instruction": f"CLIQUE NO {'CALL' if direction == 'CALL' else 'PUT'} AGORA, enquanto o candle de gatilho mantém a confirmação.",
            "secondsRemaining": int(round(remaining)),
            "elapsedSeconds": int(round(elapsed)),
            "candleCloseAt": int(round(start_ts + size)),
        }

    if late:
        return {
            "ready": False,
            "status": "PRÓXIMO CANDLE",
            "instruction": f"Não entre no fim do candle. Aguarde o próximo candle de {timeframe} para nova confirmação de {'CALL' if direction == 'CALL' else 'PUT'}.",
            "secondsRemaining": int(round(remaining)),
            "elapsedSeconds": int(round(elapsed)),
            "candleCloseAt": int(round(start_ts + size)),
        }

    if direction == "CALL":
        instruction = "Aguarde o candle de gatilho começar a confirmar para cima; quando houver fechamento/pressão compradora clara, clique no CALL."
    else:
        instruction = "Aguarde o candle de gatilho começar a confirmar para baixo; quando houver fechamento/pressão vendedora clara, clique no PUT."

    return {
        "ready": False,
        "status": "AGUARDE O GATILHO",
        "instruction": instruction,
        "secondsRemaining": int(round(remaining)),
        "elapsedSeconds": int(round(elapsed)),
        "candleCloseAt": int(round(start_ts + size)),
    }


def _iq_mtf_score(
    context: dict[str, Any],
    setup: dict[str, Any],
    trigger: dict[str, Any],
    trigger_rows: list[dict[str, float]] | None = None,
    trigger_tf: str = "1m",
    option_type: str = "binary",
    expiry_minutes: int = 5,
) -> tuple[str, float, list[str], dict[str, Any]]:
    """
    Contexto define o regime; setup define a oportunidade; gatilho define o
    momento da entrada. O monitor usa proximity como distância técnica
    até os critérios configurados, nunca como probabilidade de vitória.
    """
    strategy = setup["strategy"]
    s = setup["direction"]
    c = context["direction"]
    t = trigger["direction"]
    option_type = str(option_type or "binary").lower()
    expiry_minutes = int(expiry_minutes or 5)

    min_confidence = float(setup.get("minConfidence", 60.0) or 60.0)
    required_groups = int(setup.get("requiredGroups", 1) or 1)
    active_groups = int(setup.get("activeGroups", 0) or 0)
    setup_eligible = bool(setup.get("signalEligible", False))

    score = float(setup["confidence"])
    notes: list[str] = []

    if option_type == "blitz":
        score += 4 if t == s else -4
        notes.append("Blitz: prioridade para confirmação do gatilho em tempo real.")
        min_signal_score = 75
    elif option_type == "digital":
        if expiry_minutes >= 5 and c == s:
            score += 2
            notes.append("Digital: contexto maior confirma a direção para o vencimento.")
        notes.append("Digital: strike/preço de exercício não disponível na API comunitária; sinal é direcional.")
        min_signal_score = 70
    else:
        if expiry_minutes <= 1 and t == s:
            score += 2
        elif expiry_minutes >= 15 and c == s:
            score += 2
        min_signal_score = 67

    directional = s in {"CALL", "PUT"}
    if not directional:
        notes.append("A estratégia ainda não apresenta uma direção dominante.")

    if directional:
        if c == s and context.get("signalEligible", context["confidence"] >= 64):
            score += 11
            notes.append(f"Contexto {c} confirma o setup.")
        elif c == s:
            score += 6
            notes.append(f"Contexto acompanha {s}, mas ainda não é uma confirmação máxima.")
        elif c in {"CALL", "PUT"} and c != s:
            score -= 16 if context["confidence"] >= 72 else 9
            notes.append("Contexto maior está contra o setup.")
        else:
            score -= 2
            notes.append("Contexto maior está neutro.")

        if t == s:
            score += 7
            notes.append(f"Gatilho acompanha {s}.")
        elif t in {"CALL", "PUT"} and t != s:
            score -= 10
            notes.append("Gatilho atual está contra o setup.")
        else:
            notes.append("Gatilho ainda está em transição.")

    eligible = (
        directional
        and setup_eligible
        and score >= min_signal_score
        and not (
            c in {"CALL", "PUT"}
            and c != s
            and context["confidence"] >= (80 if strategy == "reversao" else 82)
        )
    )

    if eligible:
        trigger_state = _trigger_state(trigger_rows or [], trigger_tf, s)
    else:
        trigger_state = {
            "ready": False,
            "status": "SEM SETUP" if directional else "SEM DIREÇÃO",
            "instruction": (
                "Direção técnica identificada; monitorando confiança, grupos mínimos "
                "e confirmação do gatilho."
                if directional
                else "A leitura ainda está dividida; procurando uma direção técnica dominante."
            ),
            "secondsRemaining": 0,
            "elapsedSeconds": 0,
        }

    conf_target = max(min_confidence, min_signal_score, 1.0)
    conf_progress = min(1.0, max(0.0, score / conf_target))
    group_progress = min(1.0, active_groups / max(required_groups, 1))
    if directional:
        context_progress = 1.0 if c == s else 0.55 if c == "NEUTRA" else 0.15
        trigger_progress = 1.0 if t == s else 0.45 if t == "NEUTRA" else 0.10
    else:
        context_progress = 0.35 if c in {"CALL", "PUT"} else 0.20
        trigger_progress = 0.30 if t in {"CALL", "PUT"} else 0.20

    proximity = round(min(99.0, 100.0 * (
        0.48 * conf_progress
        + 0.22 * group_progress
        + 0.16 * context_progress
        + 0.14 * trigger_progress
    )), 1)

    if trigger_state.get("ready"):
        proximity = 100.0
        trigger_state["state"] = "ENTRADA CONFIRMADA"
        trigger_state["status"] = "ENTRADA CONFIRMADA"
    elif proximity >= 82:
        trigger_state["state"] = "SINAL PRÓXIMO"
        trigger_state["status"] = "SINAL PRÓXIMO"
    elif proximity >= 65:
        trigger_state["state"] = "ATENÇÃO"
        trigger_state["status"] = "ATENÇÃO"
    else:
        trigger_state["state"] = "ANALISANDO MERCADO"
        trigger_state["status"] = "ANALISANDO MERCADO"

    trigger_state["proximity"] = proximity
    signal = s if directional else "AGUARDAR"
    return signal, round(max(0.0, min(99.0, score)), 1), notes, trigger_state

def _wilson_lower_bound(wins: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = wins / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * ((p * (1 - p) + z * z / (4 * total)) / total) ** 0.5
    return max(0.0, (centre - margin) / denom) * 100


def _rows_closed_at(
    rows: list[dict[str, float]],
    close_time: float,
    candle_size: int,
) -> tuple[list[dict[str, float]], int]:
    eligible = [
        i for i, row in enumerate(rows)
        if float(row.get("datetime") or 0) + candle_size <= close_time + 1
    ]
    if not eligible:
        return [], -1
    idx = eligible[-1]
    return rows[: idx + 1], idx


def _historical_strategy_result(
    context_rows: list[dict[str, float]],
    setup_rows: list[dict[str, float]],
    trigger_rows: list[dict[str, float]],
    strategy: str,
    setup_size: int,
    trigger_size: int,
    expiry_minutes: int,
    option_type: str,
    max_signals: int = 100,
) -> dict[str, Any]:
    """
    Backtest sem look-ahead:
    - somente candles já fechados entram na decisão;
    - a entrada hipotética ocorre na abertura do próximo candle do gatilho;
    - o resultado é marcado no fechamento correspondente à expiração.
    """
    expiry_minutes = max(1, int(expiry_minutes or 1))
    expiry_seconds = expiry_minutes * 60

    occurrences: list[dict[str, Any]] = []
    min_setup = 60
    min_trigger = 60

    for setup_idx in range(min_setup, max(min_setup, len(setup_rows) - 2)):
        setup_candle = setup_rows[setup_idx]
        setup_close = float(setup_candle.get("datetime") or 0) + setup_size
        if setup_close <= 0:
            continue

        # Selecionamos o último candle de contexto que já havia fechado.
        context_size = _infer_candle_size(context_rows, max(1, len(context_rows) - 1))
        ctx_candidates = [
            i for i, row in enumerate(context_rows)
            if float(row.get("datetime") or 0) + context_size <= setup_close + 1
        ]
        if len(ctx_candidates) < min_trigger:
            # Fallback: a lista já chega fechada e ordenada; use o último candle
            # cujo final não ultrapassa o fechamento do setup.
            ctx_idx = -1
            for i, row in enumerate(context_rows):
                if float(row.get("datetime") or 0) <= setup_close:
                    ctx_idx = i
            if ctx_idx < min_trigger - 1:
                continue
        else:
            ctx_idx = ctx_candidates[-1]

        trigger_end_idx = -1
        for i, row in enumerate(trigger_rows):
            if float(row.get("datetime") or 0) + trigger_size <= setup_close + 1:
                trigger_end_idx = i
            else:
                break

        if trigger_end_idx < min_trigger - 1:
            continue

        context_cut = context_rows[: ctx_idx + 1]
        setup_cut = setup_rows[: setup_idx + 1]
        trigger_cut = trigger_rows[: trigger_end_idx + 1]
        context_pack = _iq_strategy_pack(context_cut, strategy)
        setup_pack = _iq_strategy_pack(setup_cut, strategy)
        trigger_pack = _iq_strategy_pack(trigger_cut, strategy)
        signal, score, notes, _ = _iq_mtf_score(
            context_pack,
            setup_pack,
            trigger_pack,
            trigger_cut,
            "1m" if trigger_size == 60 else "5m" if trigger_size == 300 else "15m",
            option_type,
            expiry_minutes,
        )
        if signal not in {"CALL", "PUT"}:
            continue

        # Próximo candle do gatilho = abertura hipotética da entrada.
        entry_idx = trigger_end_idx + 1
        if entry_idx >= len(trigger_rows):
            continue
        entry = trigger_rows[entry_idx]
        entry_price = float(entry["open"])
        entry_start = float(entry.get("datetime") or 0)
        if entry_start <= 0:
            continue

        target_close = entry_start + expiry_seconds
        outcome_idx = -1
        for i in range(entry_idx, len(trigger_rows)):
            row_end = float(trigger_rows[i].get("datetime") or 0) + trigger_size
            if row_end >= target_close - 1:
                outcome_idx = i
                break
        if outcome_idx < 0:
            continue

        exit_price = float(trigger_rows[outcome_idx]["close"])
        win = (exit_price > entry_price) if signal == "CALL" else (exit_price < entry_price)
        tie = abs(exit_price - entry_price) <= max(abs(entry_price) * 1e-10, 1e-12)

        occurrences.append({
            "signal": signal,
            "score": round(score, 1),
            "entryPrice": entry_price,
            "exitPrice": exit_price,
            "win": bool(win and not tie),
            "tie": bool(tie),
            "setupTime": setup_close,
        })
        if len(occurrences) >= max_signals:
            break

    wins = sum(1 for x in occurrences if x["win"])
    ties = sum(1 for x in occurrences if x["tie"])
    decisive = len(occurrences) - ties
    losses = max(0, decisive - wins)
    hit_rate = (wins / decisive * 100) if decisive else 0.0

    half = len(occurrences) // 2
    older = occurrences[:half] if half else []
    recent = occurrences[half:] if half else []
    older_decisive = [x for x in older if not x["tie"]]
    recent_decisive = [x for x in recent if not x["tie"]]
    older_rate = (
        sum(1 for x in older_decisive if x["win"]) / len(older_decisive) * 100
        if older_decisive else 0.0
    )
    recent_rate = (
        sum(1 for x in recent_decisive if x["win"]) / len(recent_decisive) * 100
        if recent_decisive else 0.0
    )

    return {
        "strategy": strategy,
        "testedSignals": len(occurrences),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "hitRate": round(hit_rate, 1),
        "wilsonLower95": round(_wilson_lower_bound(wins, decisive), 1),
        "olderHitRate": round(older_rate, 1),
        "recentHitRate": round(recent_rate, 1),
        "consistent": (
            len(older_decisive) >= 15
            and len(recent_decisive) >= 15
            and older_rate >= 50
            and recent_rate >= 50
        ),
        "available": True,
        "expiryMinutes": expiry_minutes,
        "optionType": option_type,
        "instrumentModel": "Direção no vencimento" if option_type == "binary" else "Direção no vencimento; strike não recebido pela API comunitária",
        "entryModel": "Próximo candle do gatilho após a confirmação",
        "occurrences": occurrences[-20:],
    }


def _infer_candle_size(rows: list[dict[str, float]], idx: int) -> int:
    if idx > 0:
        delta = float(rows[idx].get("datetime") or 0) - float(rows[idx - 1].get("datetime") or 0)
        if delta > 0:
            return max(60, int(round(delta)))
    return 60


def _backtest_selected(
    mtf: dict[str, list[dict[str, float]]],
    plan: tuple[str, str, str],
    strategy: str,
    timeframe: str,
    expiry_minutes: int,
    option_type: str,
    max_signals: int = 100,
) -> dict[str, Any]:
    context_tf, setup_tf, trigger_tf = plan
    setup_rows = mtf[setup_tf]
    trigger_rows = mtf[trigger_tf]
    context_rows = mtf[context_tf]
    setup_size = INTERVALS[setup_tf]
    trigger_size = INTERVALS[trigger_tf]
    expiry_minutes = int(expiry_minutes or 1)

    result = _historical_strategy_result(
        context_rows,
        setup_rows,
        trigger_rows,
        strategy,
        setup_size,
        trigger_size,
        expiry_minutes,
        option_type,
        max_signals,
    )
    result["requestedTimeframe"] = timeframe
    result["analysisTimeframes"] = {
        "context": context_tf,
        "setup": setup_tf,
        "trigger": trigger_tf,
    }
    return result


async def _analyze(
    client: Any,
    session_id: str,
    symbol: str,
    timeframe: str,
    strategy: str,
    option_type: str,
    expiry_minutes: int,
    authorization: str | None,
    analyze_with_ai: bool,
    fast_mode: bool = False,
) -> dict[str, Any]:
    analysis_started = time.perf_counter()
    if timeframe not in INTERVALS:
        raise HTTPException(status_code=400, detail="Período de vela não suportado.")

    option_type, expiry_minutes = _normalize_option_config(option_type, expiry_minutes)

    symbol = str(symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Informe um ativo.")

    mtf, plan, live_trigger_used = await _mtf_for_symbol(
        client,
        session_id,
        symbol,
        timeframe,
        expiry_minutes,
        option_type,
        220 if fast_mode else 1000,
    )
    context_tf, setup_tf, trigger_tf = plan
    setup_rows = mtf[setup_tf]
    trigger_rows = mtf[trigger_tf]

    if min(len(mtf[context_tf]), len(setup_rows), len(trigger_rows)) < 60:
        raise HTTPException(
            status_code=502,
            detail="Não foram recebidos candles suficientes para a análise em múltiplos timeframes.",
        )

    families = ("tendencia", "reversao", "rompimento", "momentum")
    eval_strategies = families if strategy == "automatica" else (strategy,)
    # Na Visão Opções, contexto + setup são estrutura: eles só mudam quando
    # nasce um novo candle do timeframe de setup. Reutilizamos esse cálculo entre
    # os ciclos de monitoramento e deixamos o gatilho como a única parte dinâmica.
    if fast_mode:
        structure_key = (
            f"{session_id}|{symbol}|{context_tf}|{setup_tf}|"
            f"{strategy}|{option_type}|{expiry_minutes}|"
            f"{mtf[context_tf][-1].get('datetime', 0)}|{setup_rows[-1].get('datetime', 0)}"
        )
        cached_structure = FAST_STRUCTURE_CACHE.get(structure_key)
        if cached_structure and time.time() - cached_structure[0] <= 120:
            context_strategies, setup_strategies = cached_structure[1]
        else:
            context_strategies = [
                _iq_strategy_pack(mtf[context_tf], strategy_name) for strategy_name in eval_strategies
            ]
            setup_strategies = [
                _iq_strategy_pack(setup_rows, strategy_name) for strategy_name in eval_strategies
            ]
            FAST_STRUCTURE_CACHE[structure_key] = (
                time.time(),
                (context_strategies, setup_strategies),
            )
    else:
        context_strategies = [
            _iq_strategy_pack(mtf[context_tf], strategy_name) for strategy_name in eval_strategies
        ]
        setup_strategies = [
            _iq_strategy_pack(setup_rows, strategy_name) for strategy_name in eval_strategies
        ]

    trigger_strategies = [
        _iq_strategy_pack(trigger_rows, strategy_name) for strategy_name in eval_strategies
    ]

    candidates: list[tuple[float, dict[str, Any], str, list[str], dict[str, Any]]] = []
    for setup in setup_strategies:
        context = next(
            x for x in context_strategies if x["strategy"] == setup["strategy"]
        )
        trigger = next(
            x for x in trigger_strategies if x["strategy"] == setup["strategy"]
        )
        signal, score, notes, trigger_state = _iq_mtf_score(
            context, setup, trigger, trigger_rows, trigger_tf, option_type, expiry_minutes
        )
        candidates.append((
            score if signal != "AGUARDAR" else 0.0,
            setup,
            signal,
            notes,
            trigger_state,
        ))

    if strategy == "automatica":
        valid = [x for x in candidates if x[2] in {"CALL", "PUT"}]
        if valid:
            valid.sort(key=lambda x: (x[0], x[4].get("ready", False)), reverse=True)
            selected = valid[0][1]
        else:
            selected = max(setup_strategies, key=lambda x: x["confidence"])
    else:
        selected = next(
            (x for x in setup_strategies if x["strategy"] == strategy),
            None,
        )
        if not selected:
            raise HTTPException(status_code=400, detail="Estratégia não suportada.")

    context = next(
        x for x in context_strategies if x["strategy"] == selected["strategy"]
    )
    trigger = next(
        x for x in trigger_strategies if x["strategy"] == selected["strategy"]
    )

    base_signal, base_score, notes, trigger_state = _iq_mtf_score(
        context, selected, trigger, trigger_rows, trigger_tf, option_type, expiry_minutes
    )

    gemini = (
        guru_base._gemini_review(
            symbol,
            f"{context_tf} → {setup_tf} → {trigger_tf} | {OPTION_LABELS[option_type]} | expiração {expiry_minutes}{' s' if option_type == 'blitz' else ' min'}",
            selected["strategy"],
            [selected],
            setup_rows[-1]["close"],
            setup_rows,
            authorization,
        )
        if analyze_with_ai
        else {"available": False, "reason": "Análise com IA desativada."}
    )

    gem_signal = gemini.get("signal")
    gem_conf = float(gemini.get("confidence", 0)) if gem_signal else 0.0

    if base_signal in {"CALL", "PUT"} and gem_signal == base_signal:
        signal = base_signal
        score = round(min(99, 0.82 * base_score + 0.18 * gem_conf))
        quality = "MUITO FORTE" if score >= 84 else "FORTE" if score >= 76 else "MODERADA"
    elif base_signal in {"CALL", "PUT"} and gem_signal in {"CALL", "PUT"}:
        signal = base_signal
        score = round(max(50, min(86, 0.90 * base_score + 0.10 * gem_conf - 6)))
        quality = "CONFLUÊNCIA PARCIAL"
    else:
        signal = base_signal
        score = round(base_score)
        quality = "FORTE" if score >= 78 else "MODERADA" if score >= 68 else "BAIXA"

    reasons = [
        f"Contexto {context_tf}: {context['direction']} com {context['confidence']:.0f}% de confluência.",
        f"Setup {setup_tf}: {selected['direction']} com {selected['confidence']:.0f}% de confluência.",
        f"Gatilho {trigger_tf}: {trigger['direction']} com {trigger['confidence']:.0f}% de confluência.",
    ] + notes

    if live_trigger_used:
        reasons.append("O gatilho foi atualizado por candle em tempo real da sessão da IQ Option.")

    if gemini.get("available"):
        reasons.append("Gemini: " + (gemini.get("reason") or "validação concluída."))

    warnings: list[str] = []
    if option_type == "digital":
        warnings.append("Digital: o strike/preço de exercício não é recebido pela API comunitária; o motor calcula a direção, não a distância até o strike.")
    if option_type == "blitz":
        warnings.append("Blitz: o gatilho precisa de confirmação em tempo real; não há backtest histórico exato de expirações em segundos com candles de 1 minuto.")
    if expiry_minutes == 1 and option_type != "blitz":
        warnings.append("Expiração de 1 minuto: o timing do gatilho recebe peso adicional na seleção do momento.")
    if (
        context["direction"] in {"CALL", "PUT"}
        and selected["direction"] in {"CALL", "PUT"}
        and context["direction"] != selected["direction"]
    ):
        warnings.append("Contexto e setup estão em direções opostas.")
    if (
        trigger["direction"] in {"CALL", "PUT"}
        and selected["direction"] in {"CALL", "PUT"}
        and trigger["direction"] != selected["direction"]
    ):
        warnings.append("O gatilho atual diverge do setup.")
    if selected["values"].get("ExtensionATR", 0) > 0.95:
        warnings.append("Preço está esticado em relação à EMA21; o motor evita perseguir a entrada.")
    if gemini.get("available") and gem_signal in {"CALL", "PUT"} and gem_signal != base_signal:
        warnings.append("O Gemini divergiu da leitura técnica em múltiplos timeframes.")
    if gemini.get("available") and gemini.get("risk") == "alto":
        warnings.append("O Gemini classificou o contexto como risco alto.")

    entry_instruction = trigger_state.get("instruction") or (
        f"Aguarde confirmação do gatilho para {'CALL' if signal == 'CALL' else 'PUT'}."
        if signal in {"CALL", "PUT"}
        else "Nenhuma direção técnica suficiente."
    )

    backtest_cached = False
    if fast_mode:
        backtest = {
            "available": False,
            "skipped": True,
            "strategy": selected["strategy"],
            "optionType": option_type,
            "testedSignals": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "hitRate": 0.0,
            "wilsonLower95": 0.0,
            "olderHitRate": 0.0,
            "recentHitRate": 0.0,
            "consistent": False,
            "expiryMinutes": expiry_minutes,
            "instrumentModel": "Backtest desativado no modo rápido da Visão Opções.",
            "entryModel": "Confirmação técnica em tempo real",
        }
    else:
        backtest_cache_key = f"{session_id}|{symbol}|{timeframe}|{selected['strategy']}|{option_type}|{expiry_minutes}"
        cached_backtest = BACKTEST_CACHE.get(backtest_cache_key)
        backtest_cached = bool(cached_backtest and time.time() - cached_backtest[0] <= 180)
        try:
            if backtest_cached:
                backtest = cached_backtest[1]
            elif option_type == "blitz":
                backtest = {
                    "available": False,
                    "strategy": selected["strategy"],
                    "optionType": option_type,
                    "testedSignals": 0,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "hitRate": 0.0,
                    "wilsonLower95": 0.0,
                    "olderHitRate": 0.0,
                    "recentHitRate": 0.0,
                    "consistent": False,
                    "expiryMinutes": expiry_minutes,
                    "instrumentModel": "Sem backtest exato para expiração em segundos usando apenas candles de 1 minuto.",
                    "entryModel": "Gatilho em tempo real",
                }
            else:
                backtest = _backtest_selected(
                    mtf,
                    plan,
                    selected["strategy"],
                    timeframe,
                    expiry_minutes,
                    option_type,
                    max_signals=100,
                )
            if not backtest_cached:
                BACKTEST_CACHE[backtest_cache_key] = (time.time(), backtest)
        except Exception as exc:
            backtest = {
                "strategy": selected["strategy"],
                "testedSignals": 0,
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "hitRate": 0.0,
                "wilsonLower95": 0.0,
                "olderHitRate": 0.0,
                "recentHitRate": 0.0,
                "consistent": False,
                "available": False,
                "expiryMinutes": expiry_minutes,
                "optionType": option_type,
                "instrumentModel": "Indisponível",
                "entryModel": "Indisponível",
                "error": f"Falha no backtest: {str(exc)[:160]}",
            }

    return {
        "signal": signal,
        "score": score,
        "quality": quality,
        "symbol": symbol,
        "timeframe": timeframe,
        "candlePeriod": timeframe,
        "optionType": option_type,
        "optionLabel": OPTION_LABELS[option_type],
        "expiryMinutes": expiry_minutes,
        "analysisTimeframes": {
            "context": context_tf,
            "setup": setup_tf,
            "trigger": trigger_tf,
        },
        "price": setup_rows[-1]["close"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "serverEpoch": time.time(),
        "diagnostics": {
            "serverDurationMs": round((time.perf_counter() - analysis_started) * 1000),
            "fastMode": fast_mode,
            "backtestCached": backtest_cached,
            "backtestSkipped": fast_mode,
            "liveTrigger": live_trigger_used,
            "candles": {tf: len(data) for tf, data in mtf.items()},
            "strategyEvaluations": len(eval_strategies),
        },
        "buyScore": selected["buy"],
        "sellScore": selected["sell"],
        "reasons": reasons[:10],
        "warnings": warnings[:8],
        "strategy": selected["strategy"],
        "strategyLabel": selected["strategyLabel"],
        "strategies": setup_strategies,
        "entry": {
            **trigger_state,
            "direction": signal,
            "triggerTimeframe": trigger_tf,
            "setupTimeframe": setup_tf,
        },
        "backtest": backtest,
        "mtf": {
            "context": {
                "timeframe": context_tf,
                "direction": context["direction"],
                "confidence": context["confidence"],
            },
            "setup": {
                "timeframe": setup_tf,
                "direction": selected["direction"],
                "confidence": selected["confidence"],
            },
            "trigger": {
                "timeframe": trigger_tf,
                "direction": trigger["direction"],
                "confidence": trigger["confidence"],
            },
            "score": base_score,
            "notes": notes,
            "liveTrigger": live_trigger_used,
        },
        "gemini": gemini,
        "indicators": selected["values"],
        "analysisState": trigger_state.get("state") or trigger_state.get("status") or "ANALISANDO MERCADO",
        "fastMode": fast_mode,
        "proximity": round(float(trigger_state.get("proximity", 0.0) or 0.0), 1),
        "signalConfirmed": bool(trigger_state.get("ready")),
        "source": "IQ Option + motor técnico MTF + tipo de opção + expiração + gatilho em tempo real",
    }


@router.post("/login")
async def iq_login(req: IQLoginRequest) -> dict[str, Any]:
    email = req.email.strip()
    password = req.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="Informe e-mail e senha da IQ Option.")

    AsyncIQOption = _client_class()
    client = AsyncIQOption(email, password)
    sid = secrets.token_urlsafe(32)

    try:
        await asyncio.wait_for(client.connect(), timeout=LOGIN_TIMEOUT_SECONDS)
        # O cliente assíncrono considera a autenticação concluída quando
        # recebe "authenticated=true" no WebSocket. Não exigimos um broadcast
        # de perfil aqui, pois ele não é enviado automaticamente pela plataforma.
    except asyncio.TimeoutError as exc:
        try:
            await client.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=504,
            detail="A conexão com a IQ Option excedeu o tempo limite. Isso indica falha na autenticação ou no WebSocket, não erro de senha.",
        ) from exc
    except Exception as exc:
        try:
            await client.close()
        except Exception:
            pass
        detail = str(exc)[:320] or "A IQ Option recusou a conexão."
        raise HTTPException(
            status_code=401 if "login" in detail.lower() or "auth" in detail.lower() else 502,
            detail=f"Falha ao conectar à IQ Option: {detail}",
        ) from exc

    SESSIONS[sid] = {"client": client, "email": email, "last_used": time.time()}
    _cleanup()

    return {
        "ok": True,
        "session_id": sid,
        "connected": True,
        "requires_2fa": False,
    }


@router.get("/session")
async def iq_session(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    client = item["client"]
    ws = getattr(client, "_ws", None)
    connected = ws is not None and not bool(getattr(ws, "_closed", False))
    if not connected:
        raise HTTPException(status_code=401, detail="A conexão com a IQ Option foi encerrada. Faça login novamente.")

    return {
        "ok": True,
        "connected": True,
    }


@router.get("/assets")
async def iq_assets(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    _get_session(x_iq_session)
    return _asset_list()


@router.post("/logout")
async def iq_logout(x_iq_session: str | None = Header(default=None)) -> dict[str, Any]:
    sid = (x_iq_session or "").strip()
    item = SESSIONS.pop(sid, None)
    ASSET_CACHE.pop(sid, None)

    for key in list(CANDLE_CACHE):
        if key.startswith(sid + "|"):
            CANDLE_CACHE.pop(key, None)
    for key in list(BACKTEST_CACHE):
        if key.startswith(sid + "|"):
            BACKTEST_CACHE.pop(key, None)

    if item:
        try:
            await item["client"].close()
        except Exception:
            pass

    return {"ok": True}


@router.post("/market-analysis")
async def iq_market_analysis(
    req: MarketAnalysisRequest,
    x_iq_session: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    item = _get_session(x_iq_session)
    try:
        analysis = await _analyze(
            item["client"],
            x_iq_session or "",
            req.symbol,
            req.timeframe,
            req.strategy,
            req.option_type,
            req.expiry_minutes,
            authorization,
            req.analyze_with_ai,
            req.fast_mode,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha durante a análise pela IQ Option: {str(exc)[:220]}",
        ) from exc

    return {"ok": True, "analysis": analysis}
