"""
Motor de análise para opções binárias.
Fonte: IQ Option via service.
"""
from __future__ import annotations

import json
import time
import numpy as np
import pandas as pd

from . import service
from . import news_service
from . import trade_manager


# Timeframes em segundos (o que a IQ Option usa internamente)
TIMEFRAMES = {
    "1min":  {"label": "1 minuto",   "interval": 60},
    "5min":  {"label": "5 minutos",  "interval": 300},
    "15min": {"label": "15 minutos", "interval": 900},
    "30min": {"label": "30 minutos", "interval": 1800},
}

STRATEGIES = {
    "smart_confluence": {
        "name": "Confluência Profissional",
        "description": "Análise multi-timeframe para 1m/5m: tendência, momentum, estrutura, volatilidade e confirmação de candle.",
        "max_score": 100,
        "indicadores": ["EMA 9/21/50","RSI","MACD","ADX/DI","Bollinger","Stochastic","ATR","CCI","Williams %R","MFI","ROC","OBV","CMF","Donchian","estrutura de preço"],
    },
}

_SIGNAL_CACHE: dict[tuple[str, str, str], dict] = {}
MIN_ACCURACY_SAMPLE = 20
ACCURACY_WINDOW = 60
ACCURACY_LOOKBACK = 900

STRATEGY_PARAMS_DEFAULT = {
    "smart_confluence": {
        "context_min": 68.0,
        "trigger_min": 70.0,
        "min_margin": 12.0,
        "adx_min": 18.0,
        "max_atr_ratio": 2.8,
    },
}
_PARAMS_CACHE: dict[str, tuple[float, dict]] = {}



def candles_to_df(candles: list[dict]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    required = {"time", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    for column in required:
        df.loc[:, column] = pd.to_numeric(df[column], errors="coerce")
    finite = np.isfinite(df[list(required)].astype(float)).all(axis=1)
    valid_ohlc = (
        (df["time"] > 0)
        & (df[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
        & (df["high"] >= df["low"])
    )
    df = df.loc[finite & valid_ohlc].copy()
    if df.empty:
        return pd.DataFrame()
    df.loc[:, "datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("datetime").sort_index()
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    })
    # Remove duplicatas (stream pode repetir)
    df = df[~df.index.duplicated(keep="last")]
    return df


def _drop_incomplete_candle(candles: list[dict], interval: int) -> list[dict]:
    """Remove o candle correspondente ao intervalo que ainda está aberto."""
    if not candles or interval <= 0:
        return candles

    current_bucket = int(time.time()) // interval * interval
    return [candle for candle in candles if int(candle.get("time", 0)) < current_bucket]


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close, high, low = df["Close"], df["High"], df["Low"]

    for p in (5, 10, 20):
        df.loc[:, f"EMA{p}"] = close.ewm(span=p, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((gain > 0) & (loss == 0), 100.0)
    rsi = rsi.mask((gain == 0) & (loss > 0), 0.0)
    rsi = rsi.mask((gain == 0) & (loss == 0), 50.0)
    df.loc[:, "RSI"] = rsi

    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    df.loc[:, "Stoch_K"] = 100 * (close - low14) / (high14 - low14).replace(0, np.nan)
    df.loc[:, "Stoch_D"] = df["Stoch_K"].rolling(3).mean()

    rsi = df["RSI"]
    rmin, rmax = rsi.rolling(14).min(), rsi.rolling(14).max()
    df.loc[:, "StochRSI"] = (rsi - rmin) / (rmax - rmin).replace(0, np.nan) * 100

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df.loc[:, "MACD"] = ema12 - ema26
    df.loc[:, "MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df.loc[:, "MACD_hist"] = df["MACD"] - df["MACD_signal"]

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    df.loc[:, "BB_upper"] = mid + 2 * std
    df.loc[:, "BB_lower"] = mid - 2 * std

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    df.loc[:, "ATR"] = tr.rolling(14).mean()

    up, down = high.diff(), -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    atr14 = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df.loc[:, "ADX"] = dx.rolling(14).mean()
    df.loc[:, "PLUS_DI"] = plus_di
    df.loc[:, "MINUS_DI"] = minus_di

    tp = (high + low + close) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df.loc[:, "CCI"] = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))

    df.loc[:, "WilliamsR"] = -100 * (high14 - close) / (high14 - low14).replace(0, np.nan)
    df.loc[:, "EMA50"] = close.ewm(span=50, adjust=False).mean()
    df.loc[:, "EMA9"] = close.ewm(span=9, adjust=False).mean()
    df.loc[:, "EMA21"] = close.ewm(span=21, adjust=False).mean()
    df.loc[:, "range_high_20"] = high.shift(1).rolling(20).max()
    df.loc[:, "range_low_20"] = low.shift(1).rolling(20).min()
    df.loc[:, "body"] = (close - df["Open"]).abs()
    df.loc[:, "upper_wick"] = high - pd.concat([df["Open"], close], axis=1).max(axis=1)
    df.loc[:, "lower_wick"] = pd.concat([df["Open"], close], axis=1).min(axis=1) - low
    return df


def _signal(direction: str, score: int, reason: str, indicators: list[str], min_score: int = 3) -> dict:
    score = int(score)
    # O limiar de score mede CONFIRMAÇÃO, não deve apagar uma direção técnica
    # já determinada pelo chamador. A normalização final decide se há direção
    # suficiente para publicar CALL/PUT.
    return {
        "signal": direction,
        "score": score,
        "reason": reason,
        "indicators": indicators,
        "confirmed": bool(direction in ("CALL", "PUT") and score >= int(min_score)),
    }


def _fallback_direction_from_data(df: pd.DataFrame, votes: list[dict] | None = None) -> tuple[str, str]:
    """Gera uma direção técnica quando a estratégia não atinge o quórum mínimo.

    Isso não transforma uma análise fraca em uma confirmação forte: a direção
    publicada continua acompanhada da proximidade técnica e de confirmed=False.
    """
    if votes:
        weighted_bull = sum(float(v.get("peso", 1.0)) for v in votes if int(v.get("vote", 0)) == 1)
        weighted_bear = sum(float(v.get("peso", 1.0)) for v in votes if int(v.get("vote", 0)) == -1)
        if weighted_bull > weighted_bear:
            return "CALL", f"Votos ativos favorecem CALL ({weighted_bull:.1f} contra {weighted_bear:.1f})."
        if weighted_bear > weighted_bull:
            return "PUT", f"Votos ativos favorecem PUT ({weighted_bear:.1f} contra {weighted_bull:.1f})."

    row = df.iloc[-1]
    score_call = 0.0
    score_put = 0.0

    if np.isfinite(row.get("EMA9", np.nan)) and np.isfinite(row.get("EMA21", np.nan)):
        if row["EMA9"] > row["EMA21"]:
            score_call += 2.0
        elif row["EMA9"] < row["EMA21"]:
            score_put += 2.0

    if np.isfinite(row.get("MACD", np.nan)) and np.isfinite(row.get("MACD_signal", np.nan)):
        if row["MACD"] > row["MACD_signal"]:
            score_call += 1.5
        elif row["MACD"] < row["MACD_signal"]:
            score_put += 1.5

    if np.isfinite(row.get("PLUS_DI", np.nan)) and np.isfinite(row.get("MINUS_DI", np.nan)):
        if row["PLUS_DI"] > row["MINUS_DI"]:
            score_call += 1.5
        elif row["MINUS_DI"] > row["PLUS_DI"]:
            score_put += 1.5

    if np.isfinite(row.get("RSI", np.nan)):
        if row["RSI"] > 50:
            score_call += 1.0
        elif row["RSI"] < 50:
            score_put += 1.0

    if np.isfinite(row.get("Open", np.nan)) and np.isfinite(row.get("Close", np.nan)):
        if row["Close"] > row["Open"]:
            score_call += 0.5
        elif row["Close"] < row["Open"]:
            score_put += 0.5

    if score_call > score_put:
        return "CALL", f"Direção técnica predominante: CALL ({score_call:.1f} x {score_put:.1f})."
    if score_put > score_call:
        return "PUT", f"Direção técnica predominante: PUT ({score_put:.1f} x {score_call:.1f})."

    ema20 = float(row.get("EMA20", np.nan))
    close = float(row.get("Close", np.nan))
    if np.isfinite(ema20) and np.isfinite(close) and close >= ema20:
        return "CALL", "Desempate técnico por preço acima da EMA20."
    return "PUT", "Desempate técnico por preço abaixo da EMA20."



def _strategy_signal(df: pd.DataFrame, strategy: str = "smart_confluence") -> dict:
    """Motor técnico único. Nunca cria direção por desempate."""
    if len(df) < 80:
        return _signal("AGUARDAR", 0, "Histórico técnico insuficiente.", [])
    work = compute_indicators(df.copy())
    for prep in (_preparar_mfi, _preparar_roc, _preparar_sar, _preparar_obv,
                 _preparar_cmf, _preparar_donchian, _preparar_momentum):
        work = prep(work)
    i = len(work) - 1
    votes = _votar(work, i)
    agg = aggregate_votes(votes)
    row, prev = work.iloc[-1], work.iloc[-2]

    required = ("EMA9","EMA21","EMA50","RSI","MACD","MACD_signal","MACD_hist","ADX","PLUS_DI","MINUS_DI","ATR")
    if any(not np.isfinite(float(row.get(k, np.nan))) for k in required):
        return _signal("AGUARDAR", 0, "Indicadores principais ainda não estão completos.", [])

    close=float(row["Close"])
    atr=float(row["ATR"])
    if close<=0 or atr<=0:
        return _signal("AGUARDAR",0,"Volatilidade inválida.",[])

    ema_up=row["EMA9"]>row["EMA21"]>row["EMA50"]
    ema_down=row["EMA9"]<row["EMA21"]<row["EMA50"]
    di_up=row["PLUS_DI"]>row["MINUS_DI"]
    di_down=row["MINUS_DI"]>row["PLUS_DI"]
    macd_up=row["MACD"]>row["MACD_signal"] and row["MACD_hist"]>=prev["MACD_hist"]
    macd_down=row["MACD"]<row["MACD_signal"] and row["MACD_hist"]<=prev["MACD_hist"]
    rsi_up=52<=row["RSI"]<=68 and row["RSI"]>=prev["RSI"]
    rsi_down=32<=row["RSI"]<=48 and row["RSI"]<=prev["RSI"]

    body=abs(float(row["Close"])-float(row["Open"]))
    range_=max(float(row["High"])-float(row["Low"]),1e-12)
    body_ratio=body/range_
    bullish=row["Close"]>row["Open"] and body_ratio>=0.35
    bearish=row["Close"]<row["Open"] and body_ratio>=0.35

    call=0.0; put=0.0; rc=[]; rp=[]
    if ema_up: call+=18; rc.append("EMAs alinhadas para alta")
    if ema_down: put+=18; rp.append("EMAs alinhadas para baixa")
    if di_up and row["ADX"]>=18: call+=12; rc.append("ADX/+DI confirma força compradora")
    if di_down and row["ADX"]>=18: put+=12; rp.append("ADX/-DI confirma força vendedora")
    if macd_up: call+=12; rc.append("MACD e histograma acelerando")
    if macd_down: put+=12; rp.append("MACD e histograma enfraquecendo")
    if rsi_up: call+=8; rc.append("RSI em zona direcional saudável")
    if rsi_down: put+=8; rp.append("RSI em zona direcional saudável")
    if bullish: call+=10; rc.append("candle direcional")
    if bearish: put+=10; rp.append("candle direcional")

    recent_high=float(work["High"].iloc[-21:-1].max())
    recent_low=float(work["Low"].iloc[-21:-1].min())
    breakout_up=close>recent_high and body_ratio>=0.45
    breakout_down=close<recent_low and body_ratio>=0.45
    rejection_up=row["lower_wick"]>body*1.4 and close>row["Open"]
    rejection_down=row["upper_wick"]>body*1.4 and close<row["Open"]
    if breakout_up: call+=14; rc.append("rompimento de máxima recente")
    if breakout_down: put+=14; rp.append("rompimento de mínima recente")
    if rejection_up and not ema_down: call+=7; rc.append("rejeição de suporte")
    if rejection_down and not ema_up: put+=7; rp.append("rejeição de resistência")

    if row["RSI"]>72: call-=15
    if row["RSI"]<28: put-=15

    maximum=max(call,put)
    minimum=min(call,put)
    margin=maximum-minimum
    direction="CALL" if call>put else "PUT" if put>call else "AGUARDAR"
    p=get_params_estrategia("smart_confluence")
    trigger_min=float(p.get("trigger_min",70))
    min_margin=float(p.get("min_margin",12))
    if maximum<trigger_min or margin<min_margin:
        direction="AGUARDAR"

    reason=(" + ".join(rc[:5]) if call>=put else " + ".join(rp[:5])) if direction!="AGUARDAR" else f"Sem confluência suficiente: CALL {call:.0f} x PUT {put:.0f}."
    result=_signal(direction,int(round(maximum)),reason,["EMA 9/21/50","RSI","MACD","ADX/DI","estrutura","ATR","Bollinger","Stochastic","CCI","Williams %R","MFI","ROC","OBV","CMF","Donchian"],min_score=int(trigger_min))
    result["confidence"]=round(max(0,min(100,maximum)),1)
    result["margin"]=round(margin,1)
    result["regime"]="tendência" if (ema_up or ema_down) and row["ADX"]>=18 else "lateral"
    result["resumo_votos"]={"bulls":agg["bulls"],"bears":agg["bears"],"neutros":agg["neutrals"],"total":agg["total"],"confianca":agg["confidence"]}
    result["votos"]=[{"nome":v["name"],"voto":v["vote"],"motivo":v["reason"]} for v in votes]
    result["technical_score"]=result["confidence"]
    result["technical_margin"]=result["margin"]
    return result


def _proximity(score: int, max_score: int = 4, min_score: int | None = None) -> dict:
    """Mede quão perto o score técnico está do limiar necessário da estratégia.

    100% significa que o score atingiu o mínimo técnico configurado.
    Não representa probabilidade de acerto.
    """
    score = max(0, int(score or 0))
    target = max(1, int(min_score or max_score or 1))
    ratio = max(0.0, min(1.0, score / target))
    if ratio >= 1.0:
        label = "LIMIAR TÉCNICO ATINGIDO"
    elif ratio >= 0.75:
        label = "SINAL MUITO PRÓXIMO"
    elif ratio >= 0.5:
        label = "ATENÇÃO"
    else:
        label = "AGUARDAR"
    return {
        "label": label,
        "percent": round(ratio * 100, 1),
        "score": score,
        "target": target,
    }



def estimate_historical_accuracy(df: pd.DataFrame, strategy: str = "smart_confluence", horizon: int = 1) -> dict:
    if df is None or len(df)<100:
        return {"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}
    results=[]
    start=max(80,len(df)-ACCURACY_LOOKBACK)
    for end in range(start,len(df)-horizon+1):
        decision=_strategy_signal(df.iloc[:end],strategy)
        if decision.get("signal") not in ("CALL","PUT"):
            continue
        entry=float(df["Close"].iloc[end-1]); exit_price=float(df["Close"].iloc[end+horizon-1])
        results.append((decision["signal"]=="CALL" and exit_price>entry) or (decision["signal"]=="PUT" and exit_price<entry))
    total=len(results); wins=sum(results)
    return {"rate":round(wins/total*100,1) if total else None,"sample_size":total,"wins":wins,
            "ultimos":[("OK" if x else "ERRO") for x in reversed(results[-12:])],
            "label":"Walk-forward dos sinais comparáveis." if total>=MIN_ACCURACY_SAMPLE else "Amostra insuficiente"}


def set_params_estrategia(strategy: str, params: dict) -> tuple[bool, str]:
    """Salva parâmetros customizados para uma estratégia (limiares, min_score)."""
    if strategy not in STRATEGY_PARAMS_DEFAULT:
        return False, f"Estratégia desconhecida: {strategy}"
    for chave, valor in params.items():
        if chave not in STRATEGY_PARAMS_DEFAULT[strategy]:
            continue
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return False, f"Parâmetro '{chave}' inválido para {strategy}."
        trade_manager.set_config_raw(f"sp_{strategy}_{chave}", f"{numero:.4g}")
    _PARAMS_CACHE.pop(strategy, None)
    return True, "Parâmetros da estratégia salvos."


def get_params_estrategia(strategy: str) -> dict:
    """Parâmetros efetivos da estratégia (overrides persistidos sobre defaults)."""
    agora = time.time()
    cached = _PARAMS_CACHE.get(strategy)
    if cached and agora - cached[0] < 2.0:
        return cached[1]
    params = dict(STRATEGY_PARAMS_DEFAULT.get(strategy, {}))
    for chave in params:
        bruto = trade_manager.get_config_valor(f"sp_{strategy}_{chave}", None)
        if bruto is not None and str(bruto).strip() != "":
            try:
                params[chave] = float(bruto)
            except (TypeError, ValueError):
                pass
    _PARAMS_CACHE[strategy] = (agora, params)
    return params


def set_usar_votos(ativado: bool) -> None:
    """Habilita/desabilita o filtro dos votos dos indicadores no sinal."""
    trade_manager.set_config_raw("usar_votos", "1" if ativado else "0")


def _usar_votos() -> bool:
    return str(trade_manager.get_config_valor("usar_votos", "0")) == "1"


# --------- Votos ---------
def _vote_rsi(df, i):
    rsi = df["RSI"].iloc[i]
    prev = df["RSI"].iloc[i-1] if i >= 1 else rsi
    if pd.isna(rsi) or pd.isna(prev): return 0, "RSI sem dados"
    if rsi < 30 and rsi > prev: return 1, f"RSI {rsi:.1f} saindo de sobrevenda — CALL"
    if rsi > 70 and rsi < prev: return -1, f"RSI {rsi:.1f} saindo de sobrecompra — PUT"
    if rsi < 30: return 1, f"RSI {rsi:.1f} sobrevenda — CALL"
    if rsi > 70: return -1, f"RSI {rsi:.1f} sobrecompra — PUT"
    if rsi > 55 and rsi > prev: return 1, f"RSI {rsi:.1f} viés de alta — CALL"
    if rsi < 45 and rsi < prev: return -1, f"RSI {rsi:.1f} viés de baixa — PUT"
    return 0, f"RSI {rsi:.1f} neutro"


def _vote_stoch(df, i):
    k, d = df["Stoch_K"].iloc[i], df["Stoch_D"].iloc[i]
    pk = df["Stoch_K"].iloc[i-1] if i >= 1 else k
    pdd = df["Stoch_D"].iloc[i-1] if i >= 1 else d
    if pd.isna(k) or pd.isna(d) or pd.isna(pk) or pd.isna(pdd): return 0, "Stoch sem dados"
    if pk <= pdd and k > d and k < 30: return 1, f"Stoch cruzou p/ cima em sobrevenda ({k:.1f}) — CALL"
    if pk >= pdd and k < d and k > 70: return -1, f"Stoch cruzou p/ baixo em sobrecompra ({k:.1f}) — PUT"
    if k < 20: return 1, f"Stoch {k:.1f} sobrevenda — CALL"
    if k > 80: return -1, f"Stoch {k:.1f} sobrecompra — PUT"
    return 0, f"Stoch {k:.1f} neutro"


def _vote_stoch_rsi(df, i):
    sr = df["StochRSI"].iloc[i]
    if pd.isna(sr): return 0, "Stoch RSI sem dados"
    if sr < 20: return 1, f"Stoch RSI {sr:.1f} sobrevenda — CALL"
    if sr > 80: return -1, f"Stoch RSI {sr:.1f} sobrecompra — PUT"
    return 0, f"Stoch RSI {sr:.1f} neutro"


def _vote_macd(df, i):
    m, s = df["MACD"].iloc[i], df["MACD_signal"].iloc[i]
    h = df["MACD_hist"].iloc[i]
    ph = df["MACD_hist"].iloc[i - 1] if i >= 1 else h
    if pd.isna(m) or pd.isna(s) or pd.isna(h) or pd.isna(ph):
        return 0, "MACD sem dados"
    if m > s and h > ph:
        return 1, "MACD acima do sinal com histograma subindo — CALL"
    if m < s and h < ph:
        return -1, "MACD abaixo do sinal com histograma caindo — PUT"
    if m > s:
        return 1, "MACD acima da linha de sinal — CALL"
    if m < s:
        return -1, "MACD abaixo da linha de sinal — PUT"
    return 0, "MACD neutro"


def _vote_ema(df, i, fast_column, slow_column):
    fast = df[fast_column].iloc[i]
    slow = df[slow_column].iloc[i]
    if pd.isna(fast) or pd.isna(slow):
        return 0, "EMAs sem dados"
    if fast > slow:
        return 1, f"{fast_column} acima da {slow_column} — CALL"
    if fast < slow:
        return -1, f"{fast_column} abaixo da {slow_column} — PUT"
    return 0, "EMAs sem direção"


def _vote_bollinger(df, i):
    close = df["Close"].iloc[i]
    upper = df["BB_upper"].iloc[i]
    lower = df["BB_lower"].iloc[i]
    if pd.isna(upper) or pd.isna(lower):
        return 0, "Bollinger sem dados"
    if close <= lower:
        return 1, "Preço na banda inferior — CALL"
    if close >= upper:
        return -1, "Preço na banda superior — PUT"
    return 0, "Preço dentro das bandas"


def _vote_adx(df, i):
    adx = df["ADX"].iloc[i]
    plus_di = df["PLUS_DI"].iloc[i]
    minus_di = df["MINUS_DI"].iloc[i]
    if pd.isna(adx) or pd.isna(plus_di) or pd.isna(minus_di) or adx < 20:
        return 0, "ADX sem tendência forte"
    if plus_di > minus_di:
        return 1, f"ADX {adx:.1f} com +DI dominante — CALL"
    if minus_di > plus_di:
        return -1, f"ADX {adx:.1f} com -DI dominante — PUT"
    return 0, "ADX sem direção"


def _vote_cci(df, i):
    cci = df["CCI"].iloc[i]
    if pd.isna(cci):
        return 0, "CCI sem dados"
    if cci < -100:
        return 1, f"CCI {cci:.1f} em sobrevenda — CALL"
    if cci > 100:
        return -1, f"CCI {cci:.1f} em sobrecompra — PUT"
    return 0, f"CCI {cci:.1f} neutro"


def _vote_williams(df, i):
    williams = df["WilliamsR"].iloc[i]
    if pd.isna(williams):
        return 0, "Williams %R sem dados"
    if williams < -80:
        return 1, f"Williams %R {williams:.1f} em sobrevenda — CALL"
    if williams > -20:
        return -1, f"Williams %R {williams:.1f} em sobrecompra — PUT"
    return 0, f"Williams %R {williams:.1f} neutro"


def _preparar_mfi(df):
    """Money Flow Index (14): fluxo monetário com volume e preço típico."""
    if "MFI" not in df.columns:
        típico = (df["High"] + df["Low"] + df["Close"]) / 3
        raw = típico * df["Volume"]
        diff = típico.diff()
        positivo = raw.where(diff > 0, 0.0).rolling(14).sum()
        negativo = raw.where(diff < 0, 0.0).rolling(14).sum()
        mfi = 100 - (100 / (1 + positivo / negativo.replace(0, np.nan)))
        df = df.assign(MFI=mfi)
    return df


def _vote_mfi(df, i):
    mfi = df["MFI"].iloc[i]
    prev = df["MFI"].iloc[i - 1] if i >= 1 else mfi
    if pd.isna(mfi) or pd.isna(prev):
        return 0, "MFI sem dados"
    if mfi < 20 and mfi > prev:
        return 1, f"MFI {mfi:.1f} saindo de sobrevenda — CALL"
    if mfi > 80 and mfi < prev:
        return -1, f"MFI {mfi:.1f} saindo de sobrecompra — PUT"
    if mfi < 20:
        return 1, f"MFI {mfi:.1f} sobrevenda — CALL"
    if mfi > 80:
        return -1, f"MFI {mfi:.1f} sobrecompra — PUT"
    return 0, f"MFI {mfi:.1f} neutro"


def _preparar_roc(df):
    """Rate of Change (10): variação percentual do preço de fechamento."""
    if "ROC" not in df.columns:
        df = df.assign(ROC=df["Close"].pct_change(periods=10) * 100)
    return df


def _vote_roc(df, i):
    roc = df["ROC"].iloc[i]
    if pd.isna(roc):
        return 0, "ROC sem dados"
    if roc > 0.5:
        return 1, f"ROC {roc:.2f}% momentum de alta — CALL"
    if roc < -0.5:
        return -1, f"ROC {roc:.2f}% momentum de baixa — PUT"
    return 0, f"ROC {roc:.2f}% neutro"


def _preparar_sar(df):
    """Parabolic SAR (0.02 / 0.2): ponto de reversão que segue o preço."""
    if "SAR" not in df.columns:
        closes = df["Close"].to_numpy()
        highs = df["High"].to_numpy()
        lows = df["Low"].to_numpy()
        n = len(df)
        sar = np.full(n, np.nan)
        af = 0.02
        af_max = 0.2
        is_long = True
        ext = lows[0]
        valor = closes[0]
        for k in range(1, n):
            valor = valor + af * (ext - valor)
            if is_long:
                valor = min(valor, lows[k - 1], lows[k])
                if closes[k] < valor:
                    is_long = False
                    valor = ext
                    ext = highs[k]
                    af = 0.02
                elif highs[k] > ext:
                    ext = highs[k]
                    af = min(af + 0.02, af_max)
            else:
                valor = max(valor, highs[k - 1], highs[k])
                if closes[k] > valor:
                    is_long = True
                    valor = ext
                    ext = lows[k]
                    af = 0.02
                elif lows[k] < ext:
                    ext = lows[k]
                    af = min(af + 0.02, af_max)
            sar[k] = valor
        df = df.assign(SAR=sar)
    return df


def _vote_sar(df, i):
    close = df["Close"].iloc[i]
    sar = df["SAR"].iloc[i]
    if pd.isna(sar):
        return 0, "SAR sem dados"
    if close > sar:
        return 1, f"Preço acima do SAR ({sar:.5f}) — CALL"
    if close < sar:
        return -1, f"Preço abaixo do SAR ({sar:.5f}) — PUT"
    return 0, "SAR na direção indefinida"


def _preparar_obv(df):
    """On-Balance Volume: volume acumulado conforme a direção do close."""
    if "OBV" not in df.columns:
        direcao = np.sign(df["Close"].diff().fillna(0))
        df = df.assign(OBV=(direcao * df["Volume"]).cumsum())
    return df


def _vote_obv(df, i):
    obv = df["OBV"].iloc[i]
    if pd.isna(obv) or i < 10:
        return 0, "OBV sem histórico"
    media = df["OBV"].iloc[max(0, i - 10):i + 1].mean()
    if obv > media:
        return 1, "OBV acima da média — pressão compradora — CALL"
    if obv < media:
        return -1, "OBV abaixo da média — pressão vendedora — PUT"
    return 0, "OBV neutro"


def _vote_engolfo(df, i):
    """Padrão de vela: corpo atual engole o corpo anterior (rejeição)."""
    if i < 1:
        return 0, "Engolfo sem vela anterior"
    o, c = df["Open"].iloc[i], df["Close"].iloc[i]
    po, pc = df["Open"].iloc[i - 1], df["Close"].iloc[i - 1]
    corpo = abs(c - o)
    corpo_prev = abs(pc - po)
    if pd.isna(o) or pd.isna(c) or corpo < 1e-12 or corpo_prev < 1e-12:
        return 0, "Engolfo sem corpo"
    if c > o and c >= po and o <= pc and corpo > corpo_prev * 1.2:
        return 1, "Candle de alta engolfa o anterior — CALL"
    if c < o and c <= po and o >= pc and corpo > corpo_prev * 1.2:
        return -1, "Candle de baixa engolfa o anterior — PUT"
    return 0, "Sem engolfo"


def _preparar_atr(df):
    """ATR (14): média do True Range; expansão direcional do candle."""
    if "ATR" not in df.columns:
        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"] - df["Close"].shift()).abs(),
        ], axis=1).max(axis=1)
        df = df.assign(ATR=tr.rolling(14).mean())
    return df


def _vote_atr(df, i):
    a = df["ATR"].iloc[i]
    o, c = df["Open"].iloc[i], df["Close"].iloc[i]
    if pd.isna(a) or a <= 0:
        return 0, "ATR sem dados"
    corpo = abs(c - o)
    if corpo > 2.0 * a:
        if c > o:
            return 1, f"Expansão ({corpo / a:.1f}x ATR) de alta — CALL"
        return -1, f"Expansão ({corpo / a:.1f}x ATR) de baixa — PUT"
    return 0, "Volatilidade normal"


def _preparar_momentum(df):
    """Momentum (10): diferença do fechamento em relação a 10 velas atrás."""
    if "Momentum" not in df.columns:
        df = df.assign(Momentum=df["Close"] - df["Close"].shift(10))
    return df


def _vote_momentum(df, i):
    m = df["Momentum"].iloc[i]
    if pd.isna(m):
        return 0, "Momentum sem dados"
    if m > 0:
        return 1, f"Momentum +{m:.5f} — CALL"
    if m < 0:
        return -1, f"Momentum {m:.5f} — PUT"
    return 0, "Momentum neutro"


def _preparar_cmf(df):
    """Chaikin Money Flow (20): fluxo monetário com posição no range."""
    if "CMF" not in df.columns:
        faixa = (df["High"] - df["Low"]).replace(0, np.nan)
        mfm = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / faixa
        vlr = mfm * df["Volume"]
        vol20 = df["Volume"].rolling(20).sum().replace(0, np.nan)
        df = df.assign(CMF=vlr.rolling(20).sum() / vol20)
    return df


def _vote_cmf(df, i):
    c = df["CMF"].iloc[i]
    if pd.isna(c):
        return 0, "CMF sem dados"
    if c > 0.05:
        return 1, f"CMF {c:.3f} fluxo comprador — CALL"
    if c < -0.05:
        return -1, f"CMF {c:.3f} fluxo vendedor — PUT"
    return 0, f"CMF {c:.3f} neutro"


def _preparar_donchian(df):
    """Donchian (20): máximas e mínimas da janela para detecção de rompimento."""
    if "DC_high" not in df.columns:
        df = df.assign(
            DC_high=df["High"].rolling(20).max(),
            DC_low=df["Low"].rolling(20).min(),
        )
    return df


def _vote_donchian(df, i):
    c = df["Close"].iloc[i]
    dh = df["DC_high"].iloc[i]
    dl = df["DC_low"].iloc[i]
    if pd.isna(dh) or pd.isna(dl):
        return 0, "Donchian sem dados"
    if c >= dh:
        return 1, f"Acima da máxima de 20 velas ({dh:.5f}) — CALL"
    if c <= dl:
        return -1, f"Abaixo da mínima de 20 velas ({dl:.5f}) — PUT"
    return 0, "Dentro da faixa de 20 velas"


def _vote_rejeicao(df, i):
    """Vela de rejeição: sombra longa no topo (PUT) ou na base (CALL)."""
    o, h, l, c = df["Open"].iloc[i], df["High"].iloc[i], df["Low"].iloc[i], df["Close"].iloc[i]
    if pd.isna(o) or pd.isna(h) or pd.isna(l) or pd.isna(c):
        return 0, "Sem dados"
    faixa = max(h - l, 1e-12)
    corpo = abs(c - o)
    pavio_sup = h - max(o, c)
    pavio_inf = min(o, c) - l
    if pavio_sup > corpo * 1.5 and pavio_sup > faixa * 0.5:
        return -1, "Pavio superior longo — rejeição de alta — PUT"
    if pavio_inf > corpo * 1.5 and pavio_inf > faixa * 0.5:
        return 1, "Pavio inferior longo — rejeição de baixa — CALL"
    return 0, "Sem rejeição"


# ===========================================================================
# Registro declarativo de indicadores
# ===========================================================================
# Para adicionar um indicador novo:
#   1) Escreva uma função `def _vote_seu(df, i) -> (voto, motivo)` que retorna
#      +1 (CALL/alta), -1 (PUT/baixa) ou 0 (neutro) e um texto explicativo.
#      Se precisar de colunas novas, use o campo `preparar` para calculá-las
#      (recebe o DataFrame e retorna o mesmo DataFrame ampliado).
#   2) Adicione um registro no INDICADORES_PADRAO abaixo com `id`, `nome`
#      (rótulo exibido), `descricao`, `peso` e `votar`.
#   3) Ative/desative pela aba Estratégias (ou via PUT /api/indicators).
INDICADORES_PADRAO = [
    {
        "id": "rsi",
        "nome": "RSI (14)",
        "descricao": "Oscilador de momentum; sobrevenda/sobrecompra e viés direcional.",
        "peso": 1.5,
        "votar": _vote_rsi,
    },
    {
        "id": "stoch",
        "nome": "Stochastic",
        "descricao": "Posição do preço na faixa recente, com cruzamentos.",
        "peso": 1.3,
        "votar": _vote_stoch,
    },
    {
        "id": "stochrsi",
        "nome": "Stoch RSI",
        "descricao": "RSI dentro da própria faixa; extremos de sobrevenda/sobrecompra.",
        "peso": 1.0,
        "votar": _vote_stoch_rsi,
    },
    {
        "id": "macd",
        "nome": "MACD",
        "descricao": "Convergência/divergência de médias com histograma.",
        "peso": 1.5,
        "votar": _vote_macd,
    },
    {
        "id": "ema510",
        "nome": "EMA 5/10",
        "descricao": "Médias curtas: tendência de curtíssimo prazo.",
        "peso": 1.0,
        "votar": lambda d, i: _vote_ema(d, i, "EMA5", "EMA10"),
    },
    {
        "id": "ema1020",
        "nome": "EMA 10/20",
        "descricao": "Médias médias: direção da tendência recente.",
        "peso": 1.0,
        "votar": lambda d, i: _vote_ema(d, i, "EMA10", "EMA20"),
    },
    {
        "id": "bollinger",
        "nome": "Bollinger",
        "descricao": "Bandas de volatilidade; extremos sugerem reversão.",
        "peso": 1.2,
        "votar": _vote_bollinger,
    },
    {
        "id": "adx",
        "nome": "ADX / DI",
        "descricao": "Força direcional da tendência (+DI/−DI).",
        "peso": 1.3,
        "votar": _vote_adx,
    },
    {
        "id": "cci",
        "nome": "CCI",
        "descricao": "Desvio do preço típico em relação à média; extremos.",
        "peso": 0.8,
        "votar": _vote_cci,
    },
    {
        "id": "williams",
        "nome": "Williams %R",
        "descricao": "Oscilador de momento; extremos de sobrevenda/sobrecompra.",
        "peso": 0.8,
        "votar": _vote_williams,
    },
    # ---- Novos indicadores (padrão DESMARCADO; ative na aba Estratégias) ----
    {
        "id": "mfi",
        "nome": "MFI (14)",
        "descricao": "Money Flow Index: fluxo monetário com volume; extremos de sobrevenda/sobrecompra.",
        "peso": 1.0,
        "padrao": False,
        "preparar": _preparar_mfi,
        "votar": _vote_mfi,
    },
    {
        "id": "roc",
        "nome": "ROC (10)",
        "descricao": "Rate of Change: momentum percentual do preço.",
        "peso": 0.8,
        "padrao": False,
        "preparar": _preparar_roc,
        "votar": _vote_roc,
    },
    {
        "id": "sar",
        "nome": "Parabolic SAR",
        "descricao": "Ponto de reversão que segue o preço; direção do SAR.",
        "peso": 1.0,
        "padrao": False,
        "preparar": _preparar_sar,
        "votar": _vote_sar,
    },
    {
        "id": "obv",
        "nome": "OBV",
        "descricao": "On-Balance Volume: pressão compradora/vendedora acumulada.",
        "peso": 0.8,
        "padrao": False,
        "preparar": _preparar_obv,
        "votar": _vote_obv,
    },
    {
        "id": "engolfo",
        "nome": "Candle de engolfo",
        "descricao": "Padrão de vela: o corpo atual engole o anterior (rejeição).",
        "peso": 0.9,
        "padrao": False,
        "votar": _vote_engolfo,
    },
    {
        "id": "atr",
        "nome": "ATR (14)",
        "descricao": "Expansão de volatilidade: corpo do candle acima de 2× ATR na direção.",
        "peso": 0.9,
        "padrao": False,
        "preparar": _preparar_atr,
        "votar": _vote_atr,
    },
    {
        "id": "momentum",
        "nome": "Momentum (10)",
        "descricao": "Diferença do fechamento em relação a 10 velas atrás.",
        "peso": 0.8,
        "padrao": False,
        "preparar": _preparar_momentum,
        "votar": _vote_momentum,
    },
    {
        "id": "cmf",
        "nome": "CMF (20)",
        "descricao": "Chaikin Money Flow: fluxo monetário acumulado com volume.",
        "peso": 0.9,
        "padrao": False,
        "preparar": _preparar_cmf,
        "votar": _vote_cmf,
    },
    {
        "id": "donchian",
        "nome": "Donchian (20)",
        "descricao": "Rompimento da máxima/mínima de 20 velas.",
        "peso": 1.0,
        "padrao": False,
        "preparar": _preparar_donchian,
        "votar": _vote_donchian,
    },
    {
        "id": "rejeicao",
        "nome": "Vela de rejeição",
        "descricao": "Sombra longa no topo (PUT) ou na base (CALL).",
        "peso": 0.8,
        "padrao": False,
        "votar": _vote_rejeicao,
    },
]

_INDICADORES_POR_ID = {reg["id"]: reg for reg in INDICADORES_PADRAO}


def listar_indicadores() -> list[dict]:
    """Catálogo de indicadores com o status ativo e peso EFETIVO (persistido no SQLite)."""
    ativos = set(_ids_indicadores_ativos())
    return [
        {
            "id": reg["id"],
            "nome": reg["nome"],
            "descricao": reg["descricao"],
            "peso": _peso_indicador(reg["id"]),
            "peso_padrao": reg["peso"],
            "ativo": reg["id"] in ativos,
        }
        for reg in INDICADORES_PADRAO
    ]


def _pesos_customizados() -> dict:
    """Pesos salvos pelo usuário no SQLite (config 'indicadores_pesos')."""
    bruto = trade_manager.get_config_valor("indicadores_pesos", "")
    if not bruto:
        return {}
    try:
        dados = json.loads(bruto)
    except Exception:
        return {}
    if not isinstance(dados, dict):
        return {}
    return {str(k).lower(): v for k, v in dados.items()}


def _peso_indicador(reg_id: str) -> float:
    """Peso efetivo: o customizado (se válido) ou o do registro."""
    custom = _pesos_customizados().get(str(reg_id).lower())
    if custom is not None:
        try:
            peso = float(custom)
            if 0 < peso <= 10:
                return round(peso, 2)
        except (TypeError, ValueError):
            pass
    return _INDICADORES_POR_ID[reg_id]["peso"]


def set_indicadores_pesos(pesos: dict) -> tuple[bool, str]:
    """Persiste pesos customizados (id → número entre 0 e 10)."""
    validos: dict[str, float] = {}
    for i, peso in (pesos or {}).items():
        i = str(i or "").strip().lower()
        if i not in _INDICADORES_POR_ID:
            continue
        try:
            p = float(peso)
        except (TypeError, ValueError):
            return False, f"Peso inválido para {i}: {peso}"
        if not 0 < p <= 10:
            return False, f"O peso de {i} deve estar entre 0 e 10."
        validos[i] = round(p, 2)
    trade_manager.set_config_raw("indicadores_pesos", json.dumps(validos, ensure_ascii=False))
    return True, "Pesos dos indicadores salvos."


def _ids_indicadores_ativos() -> list[str]:
    bruto = trade_manager.get_config_valor("indicadores_ativos", "")
    ids = [parte.strip() for parte in str(bruto or "").split(",") if parte.strip()]
    validos = [i for i in ids if i in _INDICADORES_POR_ID]

    # Núcleo mínimo obrigatório para a análise binária: pelo menos 12
    # indicadores de famílias diferentes/relacionadas. Uma configuração
    # antiga com menos indicadores é automaticamente complementada.
    recomendados = [
        "rsi", "macd", "ema510", "ema1020", "bollinger", "adx",
        "mfi", "roc", "sar", "obv", "cmf", "donchian",
    ]
    base = validos or recomendados
    for indicador in recomendados:
        if indicador not in base:
            base.append(indicador)
    return base


def set_indicadores_ativos(ids: list[str]) -> tuple[bool, str]:
    """Persiste a lista de indicadores ativos; ids inválidos são ignorados."""
    validos = []
    for i in ids:
        i = (i or "").strip().lower()
        if i in _INDICADORES_POR_ID and i not in validos:
            validos.append(i)
    if not validos:
        return False, "Nenhum indicador válido foi informado."
    trade_manager.set_config_raw("indicadores_ativos", ",".join(validos))
    return True, "Indicadores ativos salvos."


def _votar(df: pd.DataFrame, i: int) -> list[dict]:
    """Aplica os indicadores ATIVOS no candle i e devolve os votos."""
    votos = []
    for reg in INDICADORES_PADRAO:
        if reg["id"] not in _ids_indicadores_ativos():
            continue
        try:
            fn_preparar = reg.get("preparar")
            if fn_preparar:
                df = fn_preparar(df)
            voto, motivo = reg["votar"](df, i)
        except Exception:
            voto, motivo = 0, f"{reg['nome']} indisponível"
        votos.append({
            "id": reg["id"],
            "name": reg["nome"],
            "vote": voto,
            "reason": motivo,
            "peso": _peso_indicador(reg["id"]),
        })
    return votos


# Quórum mínimo para o sinal ser considerado acionável
MIN_DIRECTIONAL_VOTES = 5    # pelo menos 5 dos indicadores precisam votar
MIN_MARGIN = 3               # diferença mínima entre bulls e bears
MIN_COVERAGE = 60.0          # 60% dos indicadores precisam ter opinião


def aggregate_votes(votes):
    total = len(votes)

    # Soma ponderada dos votos
    weighted_bull = sum(v.get("peso", 1.0) for v in votes if v["vote"] == 1)
    weighted_bear = sum(v.get("peso", 1.0) for v in votes if v["vote"] == -1)
    bulls = sum(1 for v in votes if v["vote"] == 1)
    bears = sum(1 for v in votes if v["vote"] == -1)
    neutrals = sum(1 for v in votes if v["vote"] == 0)

    directional = bulls + bears
    coverage = (directional / total * 100) if total else 0.0

    # Direção majoritária (por peso)
    if weighted_bull > weighted_bear:
        direction = "CALL"
        winner = bulls
        loser = bears
    elif weighted_bear > weighted_bull:
        direction = "PUT"
        winner = bears
        loser = bulls
    else:
        direction = "NEUTRAL"
        winner = max(bulls, bears)
        loser = min(bulls, bears)

    margin = winner - loser

    # ----- Verificações de quórum -----
    # Se não há votos direcionais suficientes, é NEUTRAL
    if directional < MIN_DIRECTIONAL_VOTES:
        direction = "NEUTRAL"

    # Se a margem entre vencedor e perdedor é pequena, é NEUTRAL
    if margin < MIN_MARGIN:
        direction = "NEUTRAL"

    # Se a cobertura é baixa, é NEUTRAL
    if coverage < MIN_COVERAGE:
        direction = "NEUTRAL"

    # Confiança calculada APENAS sobre os votos direcionais (CALL/PUT) —
    # os votos neutros não reduzem nem diluem o percentual exibido.
    if direction == "NEUTRAL":
        confidence = round((winner / directional * 100) if directional else 0.0, 1)
        strength = "Sem direção"
    else:
        concordancia = winner / directional if directional > 0 else 0
        confidence = round(concordancia * 100, 1)
        if confidence >= 75:
            strength = "Forte"
        elif confidence >= 55:
            strength = "Moderada"
        else:
            strength = "Fraca"

    return {
        "direction": direction,
        "confidence": confidence,
        "confluence_score": confidence,
        "strength": strength,
        "bulls": bulls,
        "bears": bears,
        "neutrals": neutrals,
        "total": total,
        "coverage": round(coverage, 1),
        "margin": margin,
    }

def analyze_timeframe(df: pd.DataFrame, tf_key: str) -> dict | None:
    if df is None or len(df) < 30:
        return None
    df = compute_indicators(df.copy())
    i = len(df) - 1

    votes = _votar(df, i)

    agg = aggregate_votes(votes)
    last = df.iloc[-1]
    return {
        "timeframe": tf_key,
        "price": float(last["Close"]),
        "signal": agg["direction"],
        "confidence": agg["confidence"],
        "strength": agg["strength"],
        "bulls": agg["bulls"],
        "bears": agg["bears"],
        "neutrals": agg["neutrals"],
        "total": agg["total"],
        "coverage": agg["coverage"],
        "margin": agg["margin"],
        "indicators": votes,
    }



def _resample_ohlcv(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out=df[["Open","High","Low","Close","Volume"]].resample(
        f"{int(minutes)}min",label="right",closed="left"
    ).agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
    current_bucket=int(time.time())//(minutes*60)*(minutes*60)
    return out.loc[out.index<=pd.to_datetime(current_bucket,unit="s",utc=True)]


def _prepare_frames_from_1m(candles: list[dict]) -> dict[str,pd.DataFrame]:
    base=candles_to_df(candles)
    if base.empty: return {}
    return {"1m":base,"5m":_resample_ohlcv(base,5),"15m":_resample_ohlcv(base,15)}


def _smart_multiframe_signal(frames: dict[str,pd.DataFrame], expiry: str) -> dict:
    trigger_key="1m" if expiry=="1min" else "5m"
    context_keys=("5m","15m") if expiry=="1min" else ("15m",)
    trigger=_strategy_signal(frames.get(trigger_key,pd.DataFrame()))
    contexts=[_strategy_signal(frames.get(k,pd.DataFrame())) for k in context_keys]
    result={"signal":"AGUARDAR","confirmed":False,"score":0,"confidence":0,
            "reason":"Aguardando confluência entre contexto e gatilho.",
            "context_timeframes":list(context_keys),"trigger_timeframe":trigger_key}
    if not contexts or any(x.get("signal") not in ("CALL","PUT") for x in contexts):
        result["reason"]="Contexto de mercado sem direção limpa."
        result["proximity"]={"label":"ANALISANDO MERCADO","percent":45.0,"score":45,"target":100}
        return {**result,"trigger":trigger,"contexts":contexts}
    context_dir=contexts[0]["signal"] if all(x.get("signal")==contexts[0].get("signal") for x in contexts) else "AGUARDAR"
    trigger_dir=trigger.get("signal")
    context_conf=min(float(x.get("confidence",0) or 0) for x in contexts)
    trigger_conf=float(trigger.get("confidence",0) or 0)
    if context_dir=="AGUARDAR":
        result["reason"]="Os timeframes de contexto estão em conflito."
    elif trigger_dir!=context_dir:
        result["reason"]=f"Contexto aponta {context_dir}, mas o gatilho ainda não confirma."
    else:
        confidence=min(context_conf,trigger_conf)
        result.update({"signal":context_dir,"confirmed":True,"confidence":round(confidence,1),
                       "score":int(round(confidence)),
                       "reason":f"Contexto {', '.join(context_keys)} e gatilho {trigger_key} alinhados em {context_dir}.",
                       "technical_score":round(confidence,1),
                       "technical_margin":min(float(x.get("margin",0) or 0) for x in (*contexts,trigger)),
                       "resumo_votos":trigger.get("resumo_votos",{}),"votos":trigger.get("votos",[]),
                       "regime":contexts[0].get("regime",""),
                       "proximity":{"label":"LIMIAR TÉCNICO ATINGIDO","percent":100.0,"score":100,"target":100}})
        return {**result,"trigger":trigger,"contexts":contexts}
    combined=min(context_conf,trigger_conf)
    label="SINAL MUITO PRÓXIMO" if combined>=75 else "ATENÇÃO" if combined>=50 else "ANALISANDO MERCADO"
    result["confidence"]=round(combined,1); result["score"]=int(round(combined))
    result["proximity"]={"label":label,"percent":combined,"score":int(round(combined)),"target":100}
    result["resumo_votos"]=trigger.get("resumo_votos",{}); result["votos"]=trigger.get("votos",[])
    return {**result,"trigger":trigger,"contexts":contexts}


def _historical_multiframe_accuracy(base_df: pd.DataFrame, expiry: str) -> dict:
    if base_df is None or len(base_df)<300:
        return {"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}
    trigger_minutes=1 if expiry=="1min" else 5
    trigger=_resample_ohlcv(base_df,trigger_minutes)
    context5=_resample_ohlcv(base_df,5)
    context15=_resample_ohlcv(base_df,15)
    if trigger.empty:
        return {"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}
    results=[]
    start=max(80,len(trigger)-ACCURACY_LOOKBACK)
    for i in range(start,len(trigger)-1):
        t=trigger.index[i]
        past_trigger=trigger.iloc[:i+1]
        frames={"1m":past_trigger if expiry=="1min" else pd.DataFrame(),
                "5m":context5.loc[context5.index<=t],
                "15m":context15.loc[context15.index<=t]}
        if expiry=="5min": frames["5m"]=past_trigger
        decision=_smart_multiframe_signal(frames,expiry)
        if decision.get("signal") not in ("CALL","PUT"): continue
        entry=float(trigger["Close"].iloc[i]); exit_price=float(trigger["Close"].iloc[i+1])
        results.append((decision["signal"]=="CALL" and exit_price>entry) or (decision["signal"]=="PUT" and exit_price<entry))
    total=len(results); wins=sum(results)
    return {"rate":round(wins/total*100,1) if total else None,"sample_size":total,"wins":wins,
            "ultimos":[("OK" if x else "ERRO") for x in reversed(results[-12:])],
            "label":"Walk-forward da mesma análise multi-timeframe." if total>=MIN_ACCURACY_SAMPLE else "Amostra insuficiente"}


def build_strategy(expiry: str, context: dict, trigger: dict | None, context_keys: tuple[str,...]) -> dict:
    return _smart_multiframe_signal(context,expiry)


def analyze_asset(session_id: str, asset: str, strategy: str = "smart_confluence",
                  force_refresh: bool = False, only_expiry: str | None = None) -> dict:
    asset=asset.upper().replace("=X","")
    strategy="smart_confluence"
    expiries=(only_expiry,) if only_expiry else ("1min","5min")
    news=news_service.get_news_risk(asset)
    market_status=service.get_market_status(session_id,asset)
    signals={}
    for expiry in expiries:
        if expiry not in TIMEFRAMES: raise ValueError(f"Vencimento desconhecido: {expiry}")
        key=(asset,strategy,expiry); now=int(time.time())
        cached=_SIGNAL_CACHE.get(key)
        if not force_refresh and cached and cached.get("expires_at",0)>now:
            signals[expiry]={**cached,"locked":True,"seconds_remaining":max(0,cached["expires_at"]-now)}
            continue
        raw=service.get_candles_smart(session_id,asset,60,900)
        raw=_drop_incomplete_candle(raw,60)
        base_df=candles_to_df(raw)
        frames=_prepare_frames_from_1m(raw)
        if base_df.empty or "1m" not in frames or frames["1m"].empty:
            decision={"signal":"AGUARDAR","confirmed":False,"score":0,"confidence":0,
                      "reason":"A IQ Option não retornou candles fechados.","data_ready":False}
            accuracy={"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}
        else:
            decision=_smart_multiframe_signal(frames,expiry)
            accuracy=_historical_multiframe_accuracy(base_df,expiry)
            decision["data_ready"]=True; decision["candle_count"]=len(base_df)
        sample=int(accuracy.get("sample_size") or 0); rate=accuracy.get("rate")
        accuracy_ok=sample>=MIN_ACCURACY_SAMPLE and rate is not None and float(rate)>=70.0
        decision["historical_accuracy"]=accuracy
        decision["accuracy_gate"]=accuracy_ok
        decision["accuracy_gate_reason"]=None if accuracy_ok else (
            f"Histórico ainda não libera o sinal: {sample}/20 sinais e "
            f"{rate if rate is not None else 0:.1f}% de acerto; mínimo 20 sinais e 70%."
        )
        if news.get("blocked"):
            decision["news_blocked"]=True
            decision["news_warning"]="Evento econômico de alto impacto detectado no intervalo monitorado."
            if decision.get("signal") in ("CALL","PUT"):
                decision["signal_before_news_gate"]=decision["signal"]
                decision["signal"]="AGUARDAR"; decision["confirmed"]=False
                decision["reason"]="Sinal técnico bloqueado por evento econômico de alto impacto."
        else:
            decision["news_blocked"]=False
            decision["news_warning"]=None if news.get("available") else "Calendário econômico indisponível."
        if decision.get("signal") in ("CALL","PUT") and not accuracy_ok:
            decision["signal_before_accuracy_gate"]=decision["signal"]
            decision["signal"]="AGUARDAR"; decision["confirmed"]=False
            decision["reason"]=decision["accuracy_gate_reason"]
        interval=TIMEFRAMES[expiry]["interval"]
        entry_at=now if decision.get("signal") in ("CALL","PUT") else 0
        expires_at=entry_at+interval if entry_at else 0
        decision.update({"expiry":expiry,"entry_at":entry_at,"expires_at":expires_at,"locked":False,
                         "seconds_to_entry":0,"seconds_remaining":max(0,expires_at-now) if expires_at else 0,
                         "technical_gate":bool(decision.get("confirmed")),
                         "technical_gate_reason":None if decision.get("confirmed") else decision.get("reason")})
        signals[expiry]=decision; _SIGNAL_CACHE[key]=decision
    return {"asset":asset,"strategy":strategy,"strategy_name":STRATEGIES[strategy]["name"],
            "strategy_description":STRATEGIES[strategy]["description"],"signals":signals,"news":news,
            "warning":news.get("warning") if not news.get("available") else None,
            "market":market_status or ("aberto" if signals else "sem_dados"),
            "market_closed":market_status=="fechado"}



def walkforward_asset(session_id: str, asset: str, expiry: str, count: int = 900) -> dict:
    if expiry not in ("1min","5min"):
        raise ValueError("expiry deve ser 1min ou 5min")
    raw=service.get_candles_smart(session_id,asset.upper().replace("=X",""),60,max(900,int(count)))
    raw=_drop_incomplete_candle(raw,60)
    acc=_historical_multiframe_accuracy(candles_to_df(raw),expiry)
    sample=int(acc.get("sample_size") or 0); wins=int(acc.get("wins") or 0)
    return {"asset":asset.upper().replace("=X",""),"expiry":expiry,"sample_size":sample,
            "wins":wins,"losses":sample-wins,"win_rate":acc.get("rate"),
            "note":"Walk-forward da mesma arquitetura multi-timeframe usada no sinal."}


def get_chart_data(session_id: str, asset: str, interval: int = 300, count: int = 200) -> dict:
    """Retorna candles + EMAs + Bollinger para o gráfico."""
    candles = service.get_candles_smart(session_id, asset, interval, count)
    df = candles_to_df(candles)
    if df.empty:
        return {"candles": [], "ema10": [], "ema20": [], "bb_upper": [], "bb_lower": []}
    df = compute_indicators(df)
    return {
        "candles": [
            {"time": int(idx.timestamp()), "open": float(r["Open"]),
             "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"])}
            for idx, r in df.iterrows()
        ],
        "ema10": [{"time": int(idx.timestamp()), "value": float(r["EMA10"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA10"])],
        "ema20": [{"time": int(idx.timestamp()), "value": float(r["EMA20"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA20"])],
        "bb_upper": [{"time": int(idx.timestamp()), "value": float(r["BB_upper"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_upper"])],
        "bb_lower": [{"time": int(idx.timestamp()), "value": float(r["BB_lower"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_lower"])],
    }


def strategy_catalog() -> dict:
    """Catálogo público das estratégias disponíveis na análise binária."""
    return STRATEGIES.copy()
