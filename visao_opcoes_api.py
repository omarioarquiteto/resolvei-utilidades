from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

# SOMENTE autenticação/sessão/ativos: preserva o sistema de login da Visão atual.
import guru_sinais_iqoption_api as iq_auth

router = APIRouter(prefix="/api/visao-opcoes", tags=["VISÃO OPÇÕES"])

INTERVALS = {"1m": 60, "5m": 300, "15m": 900}
EXPIRIES = (1, 5, 15)
SESSION = iq_auth.SESSIONS
CANDLE_CACHE: dict[str, tuple[float, list[dict[str, float]]]] = {}

STRATEGIES = {
    "automatica": "Automática",
    "tendencia": "Tendência",
    "reversao": "Reversão",
    "rompimento": "Rompimento",
    "momentum": "Momentum",
}


class MarketAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str = "1m"
    strategy: str = "automatica"
    expiry_minutes: int = 1


def _session(x_iq_session: str | None) -> dict[str, Any]:
    # Reutiliza a sessão já autenticada pela implementação original.
    return iq_auth._get_session(x_iq_session)


def _clean_rows(raw: Any) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for item in raw or []:
        try:
            rows.append({
                "open": float(item["open"]),
                "high": float(item.get("max", item.get("high"))),
                "low": float(item.get("min", item.get("low"))),
                "close": float(item["close"]),
                "volume": float(item.get("volume") or 0),
                "datetime": float(item.get("from", item.get("to", 0)) or 0),
            })
        except (TypeError, ValueError, KeyError):
            continue
    rows.sort(key=lambda x: x["datetime"])
    return [r for r in rows if r["datetime"] > 0 and r["high"] >= r["low"]]


def _is_forming(row: dict[str, float], timeframe: str, now: float | None = None) -> bool:
    now = now or time.time()
    return float(row.get("datetime") or 0) + INTERVALS[timeframe] > now - 1


def _closed(rows: list[dict[str, float]], timeframe: str) -> list[dict[str, float]]:
    if not rows:
        return []
    size = INTERVALS[timeframe]
    out = [r for r in rows if not _is_forming(r, timeframe)]
    return out if len(out) >= 60 else rows[:-1]


async def _get_base_candles(client: Any, sid: str, symbol: str, count: int = 1000) -> list[dict[str, float]]:
    symbol = symbol.upper().strip()
    key = f"{sid}|{symbol}|1m|{count}"
    cached = CANDLE_CACHE.get(key)
    if cached and time.time() - cached[0] <= 1.0:
        return cached[1]
    try:
        raw = await asyncio.wait_for(
            client.get_candles(symbol, 60, min(max(count, 200), 1000), int(time.time())),
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


def _resample(rows: list[dict[str, float]], minutes: int) -> list[dict[str, float]]:
    if minutes <= 1:
        return list(rows)
    interval = minutes * 60
    buckets: dict[int, list[dict[str, float]]] = {}
    for row in rows:
        ts = int(row.get("datetime") or 0)
        bucket = (ts // interval) * interval
        buckets.setdefault(bucket, []).append(row)

    out: list[dict[str, float]] = []
    for bucket in sorted(buckets):
        chunk = sorted(buckets[bucket], key=lambda x: x["datetime"])
        # Só um candle-base completo pode formar um candle maior.
        if len(chunk) < minutes:
            continue
        out.append({
            "open": chunk[0]["open"],
            "high": max(x["high"] for x in chunk),
            "low": min(x["low"] for x in chunk),
            "close": chunk[-1]["close"],
            "volume": sum(x.get("volume", 0) for x in chunk),
            "datetime": float(bucket),
        })
    return out


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    ema = values[0]
    for value in values[1:]:
        ema = alpha * value + (1.0 - alpha) * ema
    return ema


def _ema_prev(values: list[float], period: int) -> float:
    return _ema(values[:-1], period) if len(values) > period + 1 else _ema(values, period)


def _rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    gains = losses = 0.0
    start = max(1, len(values) - period)
    for i in range(start, len(values)):
        delta = values[i] - values[i - 1]
        if delta > 0:
            gains += delta
        elif delta < 0:
            losses -= delta
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(rows: list[dict[str, float]], period: int = 14) -> float:
    if len(rows) < 2:
        return 0.0
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-period:] if len(trs) >= period else trs
    return sum(window) / len(window) if window else 0.0


def _macd(values: list[float]) -> tuple[float, float, float, float]:
    line = _ema(values, 12) - _ema(values, 26)
    signal = _ema(_macd_series(values, 12, 26), 9)
    hist = line - signal
    prev_values = values[:-1]
    prev_line = _ema(prev_values, 12) - _ema(prev_values, 26)
    prev_signal = _ema(_macd_series(prev_values, 12, 26), 9)
    return line, signal, hist, prev_line - prev_signal


def _macd_series(values: list[float], fast: int, slow: int) -> list[float]:
    if not values:
        return []
    af = 2.0 / (fast + 1.0)
    aslow = 2.0 / (slow + 1.0)
    ef = values[0]
    es = values[0]
    out = [0.0]
    for v in values[1:]:
        ef = af * v + (1.0 - af) * ef
        es = aslow * v + (1.0 - aslow) * es
        out.append(ef - es)
    return out


def _stoch(rows: list[dict[str, float]], period: int = 14) -> tuple[float, float]:
    if len(rows) < period + 2:
        return 50.0, 50.0
    ks: list[float] = []
    for i in range(max(period - 1, len(rows) - 8), len(rows)):
        window = rows[max(0, i - period + 1):i + 1]
        hi = max(x["high"] for x in window)
        lo = min(x["low"] for x in window)
        rng = max(hi - lo, 1e-12)
        ks.append(100.0 * (rows[i]["close"] - lo) / rng)
    k = ks[-1]
    d = sum(ks[-3:]) / min(3, len(ks))
    return k, d


def _adx(rows: list[dict[str, float]], period: int = 14) -> tuple[float, float]:
    if len(rows) < period + 2:
        return 0.0, 0.0
    trs: list[float] = []
    plus: list[float] = []
    minus: list[float] = []
    for i in range(1, len(rows)):
        h, l = rows[i]["high"], rows[i]["low"]
        ph, pl, pc = rows[i - 1]["high"], rows[i - 1]["low"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, down = h - ph, pl - l
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
    trw = sum(trs[-period:]) / period
    if trw <= 0:
        return 0.0, 0.0
    pdi = 100.0 * (sum(plus[-period:]) / period) / trw
    mdi = 100.0 * (sum(minus[-period:]) / period) / trw
    dx = 100.0 * abs(pdi - mdi) / max(pdi + mdi, 1e-12)
    return dx, pdi - mdi


def _indicator_pack(rows: list[dict[str, float]], timeframe: str, strategy: str) -> dict[str, Any]:
    closed = _closed(rows, timeframe) if len(rows) and _is_forming(rows[-1], timeframe) else rows
    if len(closed) < 60:
        raise HTTPException(502, "Candles fechados insuficientes.")

    closes = [x["close"] for x in closed]
    c, p = closed[-1], closed[-2]
    close = closes[-1]
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50)
    rsi = _rsi(closes)
    rsi_prev = _rsi(closes[:-1])
    macd, macd_sig, hist, prev_hist = _macd(closes)
    adx, di = _adx(closed)
    st_k, st_d = _stoch(closed)
    atr = _atr(closed)
    mean = sum(closes[-20:]) / 20
    variance = sum((x - mean) ** 2 for x in closes[-20:]) / 20
    std = math.sqrt(variance)
    bb_hi, bb_lo = mean + 2 * std, mean - 2 * std
    high20 = max(x["high"] for x in closed[-21:-1])
    low20 = min(x["low"] for x in closed[-21:-1])

    rng = max(c["high"] - c["low"], 1e-12)
    body_ratio = abs(c["close"] - c["open"]) / rng
    close_location = (c["close"] - c["low"]) / rng
    upper_wick = (c["high"] - max(c["open"], c["close"])) / rng
    lower_wick = (min(c["open"], c["close"]) - c["low"]) / rng
    atr_prev = _atr(closed[:-5], 14) if len(closed) > 45 else atr
    atr_expand = atr >= atr_prev * 1.05

    votes: list[dict[str, Any]] = []
    weights = {"primary": 3, "confirm": 2, "trigger": 2}

    def vote(name: str, side: str, reason: str, weight_group: str = "primary") -> None:
        votes.append({"name": name, "signal": side, "reason": reason, "weight": weights[weight_group]})

    trend_up = ema9 > ema21 > ema50
    trend_down = ema9 < ema21 < ema50

    if strategy == "tendencia":
        if trend_up:
            vote("EMA9/21/50", "CALL", "Médias alinhadas para alta.")
        elif trend_down:
            vote("EMA9/21/50", "PUT", "Médias alinhadas para baixa.")
        else:
            vote("EMA9/21/50", "NEUTRA", "Médias sem alinhamento completo.")

        if adx >= 18 and di > 3:
            vote("ADX/DI", "CALL", f"Força compradora com ADX {adx:.1f}.", "confirm")
        elif adx >= 18 and di < -3:
            vote("ADX/DI", "PUT", f"Força vendedora com ADX {adx:.1f}.", "confirm")
        else:
            vote("ADX/DI", "NEUTRA", f"Força direcional insuficiente (ADX {adx:.1f}).", "confirm")

        if trend_up and close >= ema21 and 48 <= rsi <= 68:
            vote("RSI + EMA21", "CALL", "Preço sustentado acima da média com RSI favorável.", "confirm")
        elif trend_down and close <= ema21 and 32 <= rsi <= 52:
            vote("RSI + EMA21", "PUT", "Preço sustentado abaixo da média com RSI favorável.", "confirm")
        else:
            vote("RSI + EMA21", "NEUTRA", "Preço/RSI sem confirmação.")

        if c["close"] > c["open"] and c["close"] >= p["close"] and body_ratio >= 0.4:
            vote("Candle", "CALL", "Candle comprador de continuidade.", "trigger")
        elif c["close"] < c["open"] and c["close"] <= p["close"] and body_ratio >= 0.4:
            vote("Candle", "PUT", "Candle vendedor de continuidade.", "trigger")
        else:
            vote("Candle", "NEUTRA", "Candle sem força suficiente.", "trigger")

    elif strategy == "reversao":
        if close <= bb_lo + atr * 0.18:
            vote("Bollinger", "CALL", "Preço em extremidade inferior.")
        elif close >= bb_hi - atr * 0.18:
            vote("Bollinger", "PUT", "Preço em extremidade superior.")
        else:
            vote("Bollinger", "NEUTRA", "Preço sem extremo relevante.")

        if rsi <= 35 and rsi > rsi_prev:
            vote("RSI", "CALL", "RSI saindo da sobrevenda.", "confirm")
        elif rsi >= 65 and rsi < rsi_prev:
            vote("RSI", "PUT", "RSI saindo da sobrecompra.", "confirm")
        else:
            vote("RSI", "NEUTRA", "RSI sem reversão extrema.", "confirm")

        if st_k < 25 and st_k > st_d:
            vote("Stochastic", "CALL", "Estocástico virando para cima.", "confirm")
        elif st_k > 75 and st_k < st_d:
            vote("Stochastic", "PUT", "Estocástico virando para baixo.", "confirm")
        else:
            vote("Stochastic", "NEUTRA", "Sem virada clara do estocástico.", "confirm")

        if lower_wick >= 0.28 and lower_wick > upper_wick * 1.25 and close_location >= 0.58:
            vote("Rejeição", "CALL", "Pavio inferior indica rejeição de preços baixos.", "trigger")
        elif upper_wick >= 0.28 and upper_wick > lower_wick * 1.25 and close_location <= 0.42:
            vote("Rejeição", "PUT", "Pavio superior indica rejeição de preços altos.", "trigger")
        else:
            vote("Rejeição", "NEUTRA", "Sem rejeição clara.", "trigger")

    elif strategy == "rompimento":
        if close > high20:
            vote("Donchian 20", "CALL", "Máxima de 20 candles rompida.")
        elif close < low20:
            vote("Donchian 20", "PUT", "Mínima de 20 candles rompida.")
        else:
            vote("Donchian 20", "NEUTRA", "Sem rompimento atual.")

        if atr_expand and c["close"] > c["open"]:
            vote("ATR expansão", "CALL", "Volatilidade expandindo com candle comprador.", "confirm")
        elif atr_expand and c["close"] < c["open"]:
            vote("ATR expansão", "PUT", "Volatilidade expandindo com candle vendedor.", "confirm")
        else:
            vote("ATR expansão", "NEUTRA", "Volatilidade sem expansão direcional.", "confirm")

        if body_ratio >= 0.5 and close_location >= 0.7:
            vote("Candle expansão", "CALL", "Fechamento forte na parte superior.", "trigger")
        elif body_ratio >= 0.5 and close_location <= 0.3:
            vote("Candle expansão", "PUT", "Fechamento forte na parte inferior.", "trigger")
        else:
            vote("Candle expansão", "NEUTRA", "Candle sem força de rompimento.", "trigger")

        if adx >= 18 and di > 3 and c["close"] > c["open"]:
            vote("ADX/DI", "CALL", "Força confirma o rompimento.", "confirm")
        elif adx >= 18 and di < -3 and c["close"] < c["open"]:
            vote("ADX/DI", "PUT", "Força confirma o rompimento.", "confirm")
        else:
            vote("ADX/DI", "NEUTRA", "ADX/DI não confirma.", "confirm")

    elif strategy == "momentum":
        if trend_up:
            vote("EMA9/21/50", "CALL", "Estrutura de alta.")
        elif trend_down:
            vote("EMA9/21/50", "PUT", "Estrutura de baixa.")
        else:
            vote("EMA9/21/50", "NEUTRA", "Estrutura sem alinhamento.")

        if hist > 0 and hist >= prev_hist:
            vote("MACD", "CALL", "Histograma positivo e acelerando.", "confirm")
        elif hist < 0 and hist <= prev_hist:
            vote("MACD", "PUT", "Histograma negativo e acelerando.", "confirm")
        else:
            vote("MACD", "NEUTRA", "MACD sem aceleração.", "confirm")

        if adx >= 18 and di > 3:
            vote("ADX/DI", "CALL", "Força compradora.", "confirm")
        elif adx >= 18 and di < -3:
            vote("ADX/DI", "PUT", "Força vendedora.", "confirm")
        else:
            vote("ADX/DI", "NEUTRA", "Força insuficiente.", "confirm")

        if 53 <= rsi <= 70:
            vote("RSI", "CALL", "RSI em zona de impulso comprador.", "trigger")
        elif 30 <= rsi <= 47:
            vote("RSI", "PUT", "RSI em zona de impulso vendedor.", "trigger")
        else:
            vote("RSI", "NEUTRA", "RSI sem zona de impulso.", "trigger")
    else:
        raise HTTPException(400, "Estratégia não suportada.")

    call_weight = sum(v["weight"] for v in votes if v["signal"] == "CALL")
    put_weight = sum(v["weight"] for v in votes if v["signal"] == "PUT")
    total_directional = call_weight + put_weight
    direction = "CALL" if call_weight > put_weight else "PUT" if put_weight > call_weight else "NEUTRA"
    dominance = max(call_weight, put_weight) / max(total_directional, 1)
    confidence = 50.0 + dominance * 45.0

    return {
        "strategy": strategy,
        "direction": direction,
        "confidence": round(min(98.0, confidence), 1),
        "callWeight": call_weight,
        "putWeight": put_weight,
        "votes": votes,
        "values": {
            "EMA9": round(ema9, 8),
            "EMA21": round(ema21, 8),
            "EMA50": round(ema50, 8),
            "RSI": round(rsi, 2),
            "MACD": round(macd, 8),
            "MACDSignal": round(macd_sig, 8),
            "MACDHistogram": round(hist, 8),
            "ADX": round(adx, 2),
            "DI": round(di, 2),
            "StochasticK": round(st_k, 2),
            "StochasticD": round(st_d, 2),
            "ATR": round(atr, 8),
            "BBUpper": round(bb_hi, 8),
            "BBLower": round(bb_lo, 8),
            "BodyRatio": round(body_ratio, 3),
            "CloseLocation": round(close_location, 3),
        },
    }


def _choose_automatic(packs: dict[str, dict[str, Any]]) -> str:
    scores = {}
    for name, pack in packs.items():
        directional = pack["direction"] in {"CALL", "PUT"}
        if not directional:
            scores[name] = -1.0
            continue
        score = float(pack["confidence"])
        if pack["strategy"] == "tendencia" and pack["values"]["ADX"] >= 20:
            score += 5
        if pack["strategy"] == "momentum" and abs(pack["values"]["MACDHistogram"]) > 0:
            score += 3
        if pack["strategy"] == "rompimento":
            score += 2 if pack["values"]["BodyRatio"] >= 0.5 else 0
        if pack["strategy"] == "reversao":
            score += 2 if pack["values"]["StochasticK"] < 25 or pack["values"]["StochasticK"] > 75 else 0
        scores[name] = score
    return max(scores, key=scores.get)


def _trigger(rows: list[dict[str, float]], timeframe: str, direction: str) -> dict[str, Any]:
    if direction not in {"CALL", "PUT"} or len(rows) < 2:
        return {"ready": False, "status": "SEM DIREÇÃO", "confidence": 0.0}

    current = rows[-1]
    previous = rows[-2]
    start = float(current.get("datetime") or 0)
    size = INTERVALS[timeframe]
    elapsed = max(0.0, time.time() - start)
    remaining = max(0.0, size - elapsed)
    if elapsed > size * 0.82:
        return {
            "ready": False,
            "status": "PRÓXIMO CANDLE",
            "confidence": 0.0,
            "secondsRemaining": int(round(remaining)),
            "elapsedSeconds": int(round(elapsed)),
            "candleCloseAt": int(round(start + size)) if start else 0,
        }

    rng = max(current["high"] - current["low"], 1e-12)
    body = abs(current["close"] - current["open"]) / rng
    location = (current["close"] - current["low"]) / rng
    price_up = current["close"] >= previous["close"]
    price_down = current["close"] <= previous["close"]

    if direction == "CALL":
        hits = sum([
            current["close"] > current["open"],
            price_up,
            body >= 0.28,
            location >= 0.58,
        ])
    else:
        hits = sum([
            current["close"] < current["open"],
            price_down,
            body >= 0.28,
            location <= 0.42,
        ])

    ready = hits >= 3
    return {
        "ready": ready,
        "status": "ENTRADA CONFIRMADA" if ready else "AGUARDANDO GATILHO",
        "confidence": round(50 + hits * 12.5, 1),
        "hits": hits,
        "secondsRemaining": int(round(remaining)),
        "elapsedSeconds": int(round(elapsed)),
        "candleCloseAt": int(round(start + size)) if start else 0,
    }


def _expiry_plan(expiry: int) -> tuple[str, str, list[str]]:
    if expiry == 1:
        return "1m", "1m", ["5m", "15m"]
    if expiry == 5:
        return "5m", "1m", ["15m"]
    if expiry == 15:
        return "15m", "5m", ["5m", "15m"]
    raise HTTPException(400, "Expiração deve ser 1, 5 ou 15 minutos.")


async def _analyze(
    client: Any,
    sid: str,
    symbol: str,
    timeframe: str,
    strategy: str,
    expiry: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    if expiry not in EXPIRIES:
        raise HTTPException(400, "Expiração deve ser 1, 5 ou 15 minutos.")
    if strategy not in STRATEGIES:
        raise HTTPException(400, "Estratégia inválida.")

    setup_tf, trigger_tf, context_tfs = _expiry_plan(expiry)
    base = await _get_base_candles(client, sid, symbol, 1000)
    one = base
    five = _resample(base, 5)
    fifteen = _resample(base, 15)
    frames = {"1m": one, "5m": five, "15m": fifteen}

    setup_rows = _closed(frames[setup_tf], setup_tf)
    trigger_rows = frames[trigger_tf]
    available_context = [_closed(frames[x], x) for x in context_tfs]
    if len(setup_rows) < 60 or any(len(x) < 25 for x in available_context):
        raise HTTPException(502, "Dados insuficientes para a análise atual.")

    if strategy == "automatica":
        packs = {
            s: _indicator_pack(setup_rows, setup_tf, s)
            for s in ("tendencia", "reversao", "rompimento", "momentum")
        }
        selected = _choose_automatic(packs)
    else:
        packs = {strategy: _indicator_pack(setup_rows, setup_tf, strategy)}
        selected = strategy

    setup_pack = packs[selected]
    context_packs = [
        _indicator_pack(rows, tf, selected)
        for tf, rows in zip(context_tfs, available_context)
    ]

    direction = setup_pack["direction"]
    context_same = sum(
        1 for pack in context_packs
        if pack["direction"] == direction and direction in {"CALL", "PUT"}
    )
    context_opposite = sum(
        1 for pack in context_packs
        if pack["direction"] in {"CALL", "PUT"} and pack["direction"] != direction
    )

    context_bonus = 0.0
    if direction in {"CALL", "PUT"}:
        context_bonus = 7.0 * context_same - 8.0 * context_opposite

    trigger = _trigger(trigger_rows, trigger_tf, direction)
    final_score = max(
        0.0,
        min(99.0, setup_pack["confidence"] + context_bonus + (trigger["confidence"] - 50.0) * 0.12),
    )

    # Limiar técnico: suficientemente seletivo para não gerar qualquer CALL/PUT,
    # mas sem exigir uma combinação impossível de condições.
    required_context = 1 if expiry in (5, 15) else 1
    indicator_ready = (
        direction in {"CALL", "PUT"}
        and setup_pack["confidence"] >= 69
        and setup_pack["callWeight"] + setup_pack["putWeight"] > 0
        and (context_same >= required_context or context_opposite == 0)
    )
    final_ready = bool(indicator_ready and trigger["ready"])

    return {
        "signal": direction if final_ready else "AGUARDAR",
        "signalConfirmed": final_ready,
        "score": round(final_score, 1),
        "quality": (
            "MUITO FORTE" if final_ready and final_score >= 86
            else "FORTE" if final_ready and final_score >= 78
            else "MODERADA" if final_ready
            else "SINAL PRÓXIMO" if indicator_ready
            else "ANALISANDO MERCADO"
        ),
        "symbol": symbol.upper(),
        "timeframe": setup_tf,
        "candlePeriod": setup_tf,
        "expiryMinutes": expiry,
        "optionType": "binary",
        "optionLabel": "Binárias",
        "strategy": selected,
        "strategyLabel": STRATEGIES[selected],
        "price": setup_rows[-1]["close"],
        "indicatorReadings": setup_pack["votes"],
        "indicators": setup_pack["values"],
        "indicatorSet": [v["name"] for v in setup_pack["votes"]],
        "buyScore": setup_pack["callWeight"],
        "sellScore": setup_pack["putWeight"],
        "reasons": [
            f"{STRATEGIES[selected]}: leitura atual dos indicadores.",
            f"Setup {setup_tf}: {setup_pack['direction']} com {setup_pack['confidence']:.0f} pontos técnicos.",
            f"Contexto: {context_same} alinhado(s) e {context_opposite} divergente(s).",
            *[f"{v['name']}: {v['signal']} — {v['reason']}" for v in setup_pack["votes"]],
        ][:9],
        "warnings": [
            "A pontuação é uma medida de confluência técnica, não uma probabilidade estatística de acerto.",
            *(
                ["Contexto divergente; o motor não confirma enquanto houver oposição relevante."]
                if context_opposite else []
            ),
        ][:4],
        "mtf": {
            "context": {
                "timeframe": ",".join(context_tfs),
                "direction": (
                    direction if context_same == len(context_packs) and direction in {"CALL", "PUT"} else "MISTO"
                ),
                "confidence": round(
                    sum(p["confidence"] for p in context_packs) / len(context_packs), 1
                ),
            },
            "setup": {
                "timeframe": setup_tf,
                "direction": setup_pack["direction"],
                "confidence": setup_pack["confidence"],
            },
            "trigger": {
                "timeframe": trigger_tf,
                "direction": direction,
                "confidence": trigger["confidence"],
            },
            "score": round(final_score, 1),
            "liveTrigger": True,
        },
        "entry": {
            **trigger,
            "ready": final_ready,
            "direction": direction if final_ready else "AGUARDAR",
            "triggerTimeframe": trigger_tf,
            "setupTimeframe": setup_tf,
            "status": "ENTRADA CONFIRMADA" if final_ready else (
                "SINAL PRÓXIMO" if indicator_ready else "ANALISANDO MERCADO"
            ),
            "instruction": (
                f"CLIQUE NO {direction} AGORA. Confirmação técnica encontrada."
                if final_ready
                else f"Monitorando a próxima confirmação para {direction}."
                if indicator_ready
                else "Interpretando novamente os indicadores atuais."
            ),
        },
        "analysisTimeframes": {
            "context": context_tfs,
            "setup": setup_tf,
            "trigger": trigger_tf,
        },
        "diagnostics": {
            "serverDurationMs": round((time.perf_counter() - started) * 1000),
            "candlesBase": len(base),
            "strategyEvaluations": 4 if strategy == "automatica" else 1,
            "backtest": False,
            "aiBlocking": False,
        },
        "analysisState": "ENTRADA CONFIRMADA" if final_ready else (
            "SINAL PRÓXIMO" if indicator_ready else "ANALISANDO MERCADO"
        ),
        "source": "IQ Option + motor técnico direto por indicadores",
    }


# O login é deliberadamente delegado às funções já existentes do Guru IQ Option.
# Assim, e-mail/senha/sessão/ativos/logout permanecem iguais na Visão.
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


@router.post("/market-analysis")
async def market_analysis(
    req: MarketAnalysisRequest,
    x_iq_session: str | None = Header(default=None),
):
    item = _session(x_iq_session)
    try:
        analysis = await _analyze(
            item["client"],
            x_iq_session or "",
            req.symbol,
            req.timeframe,
            req.strategy,
            req.expiry_minutes,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Falha durante a análise da Visão Opções: {str(exc)[:220]}") from exc
    return {"ok": True, "analysis": analysis}
