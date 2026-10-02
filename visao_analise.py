"""Motor técnico do VISÃO OPÇÕES.

Baseado no motor de análise do repositório market-insight-ai:
- 4 estratégias: tendência, reversão, rompimento e momentum;
- catálogo de 20 indicadores/votos;
- mesma matemática dos indicadores e da confluência;
- configuração por estratégia: o usuário escolhe quais indicadores participam;
- sem backtest, sem execução e sem envio de ordens.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd


TIMEFRAMES = {
    "1m": {"label": "1 minuto", "minutes": 1},
    "5m": {"label": "5 minutos", "minutes": 5},
    "15m": {"label": "15 minutos", "minutes": 15},
    "30m": {"label": "30 minutos", "minutes": 30},
}

STRATEGIES = {
    "tendencia": {
        "name": "Tendência",
        "description": "Estrutura de tendência, força direcional, RSI e candle de continuidade.",
    },
    "reversao": {
        "name": "Reversão",
        "description": "Extremos de Bollinger, RSI, Stochastic e rejeição.",
    },
    "rompimento": {
        "name": "Rompimento",
        "description": "Quebra de faixa, expansão de ATR, candle de força e ADX/DI.",
    },
    "momentum": {
        "name": "Momentum",
        "description": "Estrutura de médias, MACD, força direcional e RSI.",
    },
}

# Os quatro controles estruturais abaixo representam regras nativas do
# _indicator_pack() do market-insight-ai. Os demais são os 20 indicadores
# do catálogo declarativo daquele projeto.
INDICATOR_CATALOG = [
    {
        "id": "ema_structure",
        "name": "EMA 9/21/50",
        "description": "Estrutura de tendência pelas EMAs 9, 21 e 50.",
        "kind": "estrategia",
    },
    {
        "id": "ema510",
        "name": "EMA 5/10",
        "description": "Médias curtas de tendência.",
        "kind": "indicador",
    },
    {
        "id": "ema1020",
        "name": "EMA 10/20",
        "description": "Médias médias de direção recente.",
        "kind": "indicador",
    },
    {
        "id": "rsi",
        "name": "RSI (14)",
        "description": "Momentum, extremos e viés direcional.",
        "kind": "indicador",
    },
    {
        "id": "stoch",
        "name": "Stochastic",
        "description": "Posição do preço na faixa recente e cruzamentos.",
        "kind": "indicador",
    },
    {
        "id": "stochrsi",
        "name": "Stoch RSI",
        "description": "RSI normalizado em sua própria faixa.",
        "kind": "indicador",
    },
    {
        "id": "macd",
        "name": "MACD",
        "description": "Convergência/divergência e aceleração.",
        "kind": "indicador",
    },
    {
        "id": "bollinger",
        "name": "Bollinger",
        "description": "Bandas de volatilidade e extremos.",
        "kind": "indicador",
    },
    {
        "id": "adx",
        "name": "ADX / DI",
        "description": "Força e direção da tendência.",
        "kind": "indicador",
    },
    {
        "id": "cci",
        "name": "CCI",
        "description": "Extremos do preço típico.",
        "kind": "indicador",
    },
    {
        "id": "williams",
        "name": "Williams %R",
        "description": "Oscilador de extremos.",
        "kind": "indicador",
    },
    {
        "id": "mfi",
        "name": "MFI (14)",
        "description": "Fluxo monetário com volume.",
        "kind": "indicador",
    },
    {
        "id": "roc",
        "name": "ROC (10)",
        "description": "Rate of Change e momentum percentual.",
        "kind": "indicador",
    },
    {
        "id": "sar",
        "name": "Parabolic SAR",
        "description": "Ponto de reversão acompanhado do preço.",
        "kind": "indicador",
    },
    {
        "id": "obv",
        "name": "OBV",
        "description": "Pressão compradora/vendedora por volume.",
        "kind": "indicador",
    },
    {
        "id": "engolfo",
        "name": "Candle de engolfo",
        "description": "Padrão de vela de engolfo.",
        "kind": "indicador",
    },
    {
        "id": "atr",
        "name": "ATR (14)",
        "description": "Expansão de volatilidade.",
        "kind": "indicador",
    },
    {
        "id": "momentum",
        "name": "Momentum (10)",
        "description": "Diferença do fechamento contra 10 velas atrás.",
        "kind": "indicador",
    },
    {
        "id": "cmf",
        "name": "CMF (20)",
        "description": "Chaikin Money Flow.",
        "kind": "indicador",
    },
    {
        "id": "donchian",
        "name": "Donchian (20)",
        "description": "Máxima/mínima da faixa de 20 velas.",
        "kind": "indicador",
    },
    {
        "id": "rejeicao",
        "name": "Vela de rejeição",
        "description": "Pavio longo no topo ou na base.",
        "kind": "indicador",
    },
    {
        "id": "candle_continuity",
        "name": "Candle de continuidade",
        "description": "Candle com corpo e fechamento confirmando a direção.",
        "kind": "estrategia",
    },
    {
        "id": "candle_expansion",
        "name": "Candle de expansão",
        "description": "Candle forte fechando próximo da extremidade.",
        "kind": "estrategia",
    },
]

INDICATOR_BY_ID = {item["id"]: item for item in INDICATOR_CATALOG}

# Perfis iniciais espelham o núcleo de cada estratégia do market-insight-ai.
DEFAULT_PROFILES = {
    "tendencia": ["ema_structure", "adx", "rsi", "candle_continuity"],
    "reversao": ["bollinger", "rsi", "stoch", "rejeicao"],
    "rompimento": ["donchian", "atr", "candle_expansion", "adx"],
    "momentum": ["ema_structure", "macd", "adx", "rsi"],
}

NATIVE_WEIGHTS = {
    "primary": 3,
    "confirm": 2,
    "trigger": 2,
}


def default_profiles() -> dict[str, list[str]]:
    return {key: list(value) for key, value in DEFAULT_PROFILES.items()}


def sanitize_profiles(raw: dict | None) -> dict[str, list[str]]:
    base = default_profiles()
    if not isinstance(raw, dict):
        return base
    for strategy in STRATEGIES:
        ids = raw.get(strategy)
        if not isinstance(ids, list):
            continue
        clean = []
        for indicator_id in ids:
            indicator_id = str(indicator_id or "").strip().lower()
            if indicator_id in INDICATOR_BY_ID and indicator_id not in clean:
                clean.append(indicator_id)
        # Um perfil vazio significa exatamente "nenhum indicador selecionado".
        base[strategy] = clean
    return base


def candles_to_df(candles: list[dict]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    required = {"time", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    for col in required:
        df.loc[:, col] = pd.to_numeric(df[col], errors="coerce")
    finite = np.isfinite(df[list(required)].astype(float)).all(axis=1)
    valid = (
        (df["time"] > 0)
        & (df[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
        & (df["high"] >= df["low"])
    )
    df = df.loc[finite & valid].copy()
    if df.empty:
        return pd.DataFrame()
    df.loc[:, "datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("datetime").sort_index()
    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    return df[~df.index.duplicated(keep="last")]


def compute_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close, high, low = df["Close"], df["High"], df["Low"]

    for period in (5, 10, 20):
        df.loc[:, f"EMA{period}"] = close.ewm(span=period, adjust=False).mean()

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

    rmin, rmax = rsi.rolling(14).min(), rsi.rolling(14).max()
    df.loc[:, "StochRSI"] = (rsi - rmin) / (rmax - rmin).replace(0, np.nan) * 100

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df.loc[:, "MACD"] = ema12 - ema26
    df.loc[:, "MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df.loc[:, "MACD_hist"] = df["MACD"] - df["MACD_signal"]

    mean = close.rolling(20).mean()
    std = close.rolling(20).std()
    df.loc[:, "BB_upper"] = mean + 2 * std
    df.loc[:, "BB_lower"] = mean - 2 * std

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df.loc[:, "TR"] = tr
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

    typical = (high + low + close) / 3
    sma_typical = typical.rolling(20).mean()
    mad = typical.rolling(20).apply(lambda values: np.abs(values - values.mean()).mean(), raw=True)
    df.loc[:, "CCI"] = (typical - sma_typical) / (0.015 * mad.replace(0, np.nan))
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


def _prepare_extras(df: pd.DataFrame) -> pd.DataFrame:
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    raw = typical * df["Volume"]
    diff = typical.diff()

    positive = raw.where(diff > 0, 0.0).rolling(14).sum()
    negative = raw.where(diff < 0, 0.0).rolling(14).sum()
    df.loc[:, "MFI"] = 100 - (100 / (1 + positive / negative.replace(0, np.nan)))
    df.loc[:, "ROC"] = df["Close"].pct_change(periods=10) * 100

    closes = df["Close"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    sar = np.full(len(df), np.nan)
    af = 0.02
    af_max = 0.2
    is_long = True
    ext = lows[0] if len(df) else 0.0
    value = closes[0] if len(df) else np.nan
    for k in range(1, len(df)):
        value = value + af * (ext - value)
        if is_long:
            value = min(value, lows[k - 1], lows[k])
            if closes[k] < value:
                is_long = False
                value = ext
                ext = highs[k]
                af = 0.02
            elif highs[k] > ext:
                ext = highs[k]
                af = min(af + 0.02, af_max)
        else:
            value = max(value, highs[k - 1], highs[k])
            if closes[k] > value:
                is_long = True
                value = ext
                ext = lows[k]
                af = 0.02
            elif lows[k] < ext:
                ext = lows[k]
                af = min(af + 0.02, af_max)
        sar[k] = value
    df.loc[:, "SAR"] = sar

    direction = np.sign(df["Close"].diff().fillna(0))
    df.loc[:, "OBV"] = (direction * df["Volume"]).cumsum()

    faixa = (df["High"] - df["Low"]).replace(0, np.nan)
    mfm = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / faixa
    money_flow = mfm * df["Volume"]
    vol20 = df["Volume"].rolling(20).sum().replace(0, np.nan)
    df.loc[:, "CMF"] = money_flow.rolling(20).sum() / vol20

    df.loc[:, "DC_high"] = df["High"].rolling(20).max()
    df.loc[:, "DC_low"] = df["Low"].rolling(20).min()
    return df


def _vote_rsi(df, i):
    rsi = df["RSI"].iloc[i]
    prev = df["RSI"].iloc[i - 1] if i >= 1 else rsi
    if pd.isna(rsi) or pd.isna(prev):
        return 0, "RSI sem dados"
    if rsi < 30 and rsi > prev:
        return 1, f"RSI {rsi:.1f} saindo de sobrevenda — CALL"
    if rsi > 70 and rsi < prev:
        return -1, f"RSI {rsi:.1f} saindo de sobrecompra — PUT"
    if rsi < 30:
        return 1, f"RSI {rsi:.1f} sobrevenda — CALL"
    if rsi > 70:
        return -1, f"RSI {rsi:.1f} sobrecompra — PUT"
    if rsi > 55 and rsi > prev:
        return 1, f"RSI {rsi:.1f} viés de alta — CALL"
    if rsi < 45 and rsi < prev:
        return -1, f"RSI {rsi:.1f} viés de baixa — PUT"
    return 0, f"RSI {rsi:.1f} neutro"


def _vote_stoch(df, i):
    k, d = df["Stoch_K"].iloc[i], df["Stoch_D"].iloc[i]
    pk = df["Stoch_K"].iloc[i - 1] if i >= 1 else k
    pdv = df["Stoch_D"].iloc[i - 1] if i >= 1 else d
    if any(pd.isna(x) for x in (k, d, pk, pdv)):
        return 0, "Stoch sem dados"
    if pk <= pdv and k > d and k < 30:
        return 1, f"Stoch cruzou p/ cima em sobrevenda ({k:.1f}) — CALL"
    if pk >= pdv and k < d and k > 70:
        return -1, f"Stoch cruzou p/ baixo em sobrecompra ({k:.1f}) — PUT"
    if k < 20:
        return 1, f"Stoch {k:.1f} sobrevenda — CALL"
    if k > 80:
        return -1, f"Stoch {k:.1f} sobrecompra — PUT"
    return 0, f"Stoch {k:.1f} neutro"


def _vote_stochrsi(df, i):
    value = df["StochRSI"].iloc[i]
    if pd.isna(value):
        return 0, "Stoch RSI sem dados"
    if value < 20:
        return 1, f"Stoch RSI {value:.1f} sobrevenda — CALL"
    if value > 80:
        return -1, f"Stoch RSI {value:.1f} sobrecompra — PUT"
    return 0, f"Stoch RSI {value:.1f} neutro"


def _vote_macd(df, i):
    macd, signal, hist = df["MACD"].iloc[i], df["MACD_signal"].iloc[i], df["MACD_hist"].iloc[i]
    prev_hist = df["MACD_hist"].iloc[i - 1] if i >= 1 else hist
    if any(pd.isna(x) for x in (macd, signal, hist, prev_hist)):
        return 0, "MACD sem dados"
    if macd > signal and hist > prev_hist:
        return 1, "MACD acima do sinal com histograma subindo — CALL"
    if macd < signal and hist < prev_hist:
        return -1, "MACD abaixo do sinal com histograma caindo — PUT"
    if macd > signal:
        return 1, "MACD acima da linha de sinal — CALL"
    if macd < signal:
        return -1, "MACD abaixo da linha de sinal — PUT"
    return 0, "MACD neutro"


def _vote_ema(df, i, fast_column, slow_column):
    fast, slow = df[fast_column].iloc[i], df[slow_column].iloc[i]
    if pd.isna(fast) or pd.isna(slow):
        return 0, "EMAs sem dados"
    if fast > slow:
        return 1, f"{fast_column} acima da {slow_column} — CALL"
    if fast < slow:
        return -1, f"{fast_column} abaixo da {slow_column} — PUT"
    return 0, "EMAs sem direção"


def _vote_bollinger(df, i):
    close, upper, lower = df["Close"].iloc[i], df["BB_upper"].iloc[i], df["BB_lower"].iloc[i]
    if pd.isna(upper) or pd.isna(lower):
        return 0, "Bollinger sem dados"
    if close <= lower:
        return 1, "Preço na banda inferior — CALL"
    if close >= upper:
        return -1, "Preço na banda superior — PUT"
    return 0, "Preço dentro das bandas"


def _vote_adx(df, i):
    adx, plus_di, minus_di = df["ADX"].iloc[i], df["PLUS_DI"].iloc[i], df["MINUS_DI"].iloc[i]
    if pd.isna(adx) or pd.isna(plus_di) or pd.isna(minus_di) or adx < 20:
        return 0, "ADX sem tendência forte"
    if plus_di > minus_di:
        return 1, f"ADX {adx:.1f} com +DI dominante — CALL"
    if minus_di > plus_di:
        return -1, f"ADX {adx:.1f} com -DI dominante — PUT"
    return 0, "ADX sem direção"


def _vote_cci(df, i):
    value = df["CCI"].iloc[i]
    if pd.isna(value):
        return 0, "CCI sem dados"
    if value < -100:
        return 1, f"CCI {value:.1f} em sobrevenda — CALL"
    if value > 100:
        return -1, f"CCI {value:.1f} em sobrecompra — PUT"
    return 0, f"CCI {value:.1f} neutro"


def _vote_williams(df, i):
    value = df["WilliamsR"].iloc[i]
    if pd.isna(value):
        return 0, "Williams %R sem dados"
    if value < -80:
        return 1, f"Williams %R {value:.1f} em sobrevenda — CALL"
    if value > -20:
        return -1, f"Williams %R {value:.1f} em sobrecompra — PUT"
    return 0, f"Williams %R {value:.1f} neutro"


def _vote_mfi(df, i):
    value = df["MFI"].iloc[i]
    prev = df["MFI"].iloc[i - 1] if i >= 1 else value
    if pd.isna(value) or pd.isna(prev):
        return 0, "MFI sem dados"
    if value < 20 and value > prev:
        return 1, f"MFI {value:.1f} saindo de sobrevenda — CALL"
    if value > 80 and value < prev:
        return -1, f"MFI {value:.1f} saindo de sobrecompra — PUT"
    if value < 20:
        return 1, f"MFI {value:.1f} sobrevenda — CALL"
    if value > 80:
        return -1, f"MFI {value:.1f} sobrecompra — PUT"
    return 0, f"MFI {value:.1f} neutro"


def _vote_roc(df, i):
    value = df["ROC"].iloc[i]
    if pd.isna(value):
        return 0, "ROC sem dados"
    if value > 0.5:
        return 1, f"ROC {value:.2f}% momentum de alta — CALL"
    if value < -0.5:
        return -1, f"ROC {value:.2f}% momentum de baixa — PUT"
    return 0, f"ROC {value:.2f}% neutro"


def _vote_sar(df, i):
    close, sar = df["Close"].iloc[i], df["SAR"].iloc[i]
    if pd.isna(sar):
        return 0, "SAR sem dados"
    if close > sar:
        return 1, f"Preço acima do SAR ({sar:.5f}) — CALL"
    if close < sar:
        return -1, f"Preço abaixo do SAR ({sar:.5f}) — PUT"
    return 0, "SAR na direção indefinida"


def _vote_obv(df, i):
    value = df["OBV"].iloc[i]
    if pd.isna(value) or i < 10:
        return 0, "OBV sem histórico"
    mean = df["OBV"].iloc[max(0, i - 10): i + 1].mean()
    if value > mean:
        return 1, "OBV acima da média — pressão compradora — CALL"
    if value < mean:
        return -1, "OBV abaixo da média — pressão vendedora — PUT"
    return 0, "OBV neutro"


def _vote_engolfo(df, i):
    if i < 1:
        return 0, "Engolfo sem vela anterior"
    o, c = df["Open"].iloc[i], df["Close"].iloc[i]
    po, pc = df["Open"].iloc[i - 1], df["Close"].iloc[i - 1]
    body, previous_body = abs(c - o), abs(pc - po)
    if any(pd.isna(x) for x in (o, c, po, pc)) or body < 1e-12 or previous_body < 1e-12:
        return 0, "Engolfo sem corpo"
    if c > o and c >= po and o <= pc and body > previous_body * 1.2:
        return 1, "Candle de alta engolfa o anterior — CALL"
    if c < o and c <= po and o >= pc and body > previous_body * 1.2:
        return -1, "Candle de baixa engolfa o anterior — PUT"
    return 0, "Sem engolfo"


def _vote_atr(df, i):
    value = df["ATR"].iloc[i]
    o, c = df["Open"].iloc[i], df["Close"].iloc[i]
    if pd.isna(value) or value <= 0:
        return 0, "ATR sem dados"
    body = abs(c - o)
    if body > 2.0 * value:
        if c > o:
            return 1, f"Expansão ({body / value:.1f}x ATR) de alta — CALL"
        return -1, f"Expansão ({body / value:.1f}x ATR) de baixa — PUT"
    return 0, "Volatilidade normal"


def _vote_momentum(df, i):
    value = df["Momentum"].iloc[i]
    if pd.isna(value):
        return 0, "Momentum sem dados"
    if value > 0:
        return 1, f"Momentum +{value:.5f} — CALL"
    if value < 0:
        return -1, f"Momentum {value:.5f} — PUT"
    return 0, "Momentum neutro"


def _vote_cmf(df, i):
    value = df["CMF"].iloc[i]
    if pd.isna(value):
        return 0, "CMF sem dados"
    if value > 0.05:
        return 1, f"CMF {value:.3f} fluxo comprador — CALL"
    if value < -0.05:
        return -1, f"CMF {value:.3f} fluxo vendedor — PUT"
    return 0, f"CMF {value:.3f} neutro"


def _vote_donchian(df, i):
    close, dh, dl = df["Close"].iloc[i], df["DC_high"].iloc[i], df["DC_low"].iloc[i]
    if pd.isna(dh) or pd.isna(dl):
        return 0, "Donchian sem dados"
    if close >= dh:
        return 1, f"Acima da máxima de 20 velas ({dh:.5f}) — CALL"
    if close <= dl:
        return -1, f"Abaixo da mínima de 20 velas ({dl:.5f}) — PUT"
    return 0, "Dentro da faixa de 20 velas"


def _vote_rejeicao(df, i):
    o, h, l, c = df["Open"].iloc[i], df["High"].iloc[i], df["Low"].iloc[i], df["Close"].iloc[i]
    if any(pd.isna(x) for x in (o, h, l, c)):
        return 0, "Sem dados"
    faixa = max(h - l, 1e-12)
    corpo = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    if upper > corpo * 1.5 and upper > faixa * 0.5:
        return -1, "Pavio superior longo — rejeição de alta — PUT"
    if lower > corpo * 1.5 and lower > faixa * 0.5:
        return 1, "Pavio inferior longo — rejeição de baixa — CALL"
    return 0, "Sem rejeição"


def _vote_ema_structure(df, i):
    row = df.iloc[i]
    if any(pd.isna(row[col]) for col in ("EMA9", "EMA21", "EMA50")):
        return 0, "Estrutura de EMA sem dados"
    if row["EMA9"] > row["EMA21"] > row["EMA50"]:
        return 1, "EMA9 > EMA21 > EMA50 — estrutura de alta — CALL"
    if row["EMA9"] < row["EMA21"] < row["EMA50"]:
        return -1, "EMA9 < EMA21 < EMA50 — estrutura de baixa — PUT"
    return 0, "EMAs sem alinhamento completo"


def _vote_candle_continuity(df, i):
    if i < 1:
        return 0, "Candle sem vela anterior"
    c, p = df.iloc[i], df.iloc[i - 1]
    rng = max(c["High"] - c["Low"], 1e-12)
    body_ratio = abs(c["Close"] - c["Open"]) / rng
    if c["Close"] > c["Open"] and c["Close"] >= p["Close"] and body_ratio >= 0.4:
        return 1, "Candle comprador de continuidade — CALL"
    if c["Close"] < c["Open"] and c["Close"] <= p["Close"] and body_ratio >= 0.4:
        return -1, "Candle vendedor de continuidade — PUT"
    return 0, "Candle sem força suficiente"


def _vote_candle_expansion(df, i):
    c = df.iloc[i]
    rng = max(c["High"] - c["Low"], 1e-12)
    body_ratio = abs(c["Close"] - c["Open"]) / rng
    location = (c["Close"] - c["Low"]) / rng
    if body_ratio >= 0.5 and location >= 0.7:
        return 1, "Candle de expansão com fechamento forte na parte superior — CALL"
    if body_ratio >= 0.5 and location <= 0.3:
        return -1, "Candle de expansão com fechamento forte na parte inferior — PUT"
    return 0, "Candle sem força de rompimento"


GENERIC_VOTES = {
    "rsi": _vote_rsi,
    "stoch": _vote_stoch,
    "stochrsi": _vote_stochrsi,
    "macd": _vote_macd,
    "ema510": lambda df, i: _vote_ema(df, i, "EMA5", "EMA10"),
    "ema1020": lambda df, i: _vote_ema(df, i, "EMA10", "EMA20"),
    "bollinger": _vote_bollinger,
    "adx": _vote_adx,
    "cci": _vote_cci,
    "williams": _vote_williams,
    "mfi": _vote_mfi,
    "roc": _vote_roc,
    "sar": _vote_sar,
    "obv": _vote_obv,
    "engolfo": _vote_engolfo,
    "atr": _vote_atr,
    "momentum": _vote_momentum,
    "cmf": _vote_cmf,
    "donchian": _vote_donchian,
    "rejeicao": _vote_rejeicao,
    "ema_structure": _vote_ema_structure,
    "candle_continuity": _vote_candle_continuity,
    "candle_expansion": _vote_candle_expansion,
}

# Regras nativas, na mesma ordem e com os mesmos pesos do market-insight-ai.
def _native_votes(df: pd.DataFrame, strategy: str, selected: set[str]) -> list[dict]:
    row = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(row["Close"])
    ema9, ema21, ema50 = float(row["EMA9"]), float(row["EMA21"]), float(row["EMA50"])
    rsi, rsi_prev = float(row["RSI"]), float(prev["RSI"])
    macd, macd_sig, hist = float(row["MACD"]), float(row["MACD_signal"]), float(row["MACD_hist"])
    prev_hist = float(prev["MACD_hist"])
    adx, di = float(row["ADX"]), float(row["PLUS_DI"] - row["MINUS_DI"])
    st_k, st_d = float(row["Stoch_K"]), float(row["Stoch_D"])
    atr, atr_prev = float(row["ATR"]), float(_atr_from_df(df.iloc[:-5]))
    atr_expand = atr >= atr_prev * 1.05
    rng = max(float(row["High"] - row["Low"]), 1e-12)
    body_ratio = abs(float(row["Close"] - row["Open"])) / rng
    close_location = (float(row["Close"]) - float(row["Low"])) / rng
    upper_wick = (float(row["High"]) - max(float(row["Open"]), float(row["Close"]))) / rng
    lower_wick = (min(float(row["Open"]), float(row["Close"])) - float(row["Low"])) / rng
    trend_up = ema9 > ema21 > ema50
    trend_down = ema9 < ema21 < ema50

    votes: list[dict] = []

    def add(indicator_id: str, signal: str, reason: str, weight_group: str = "primary") -> None:
        if indicator_id not in selected:
            return
        votes.append(
            {
                "id": indicator_id,
                "name": INDICATOR_BY_ID[indicator_id]["name"],
                "signal": signal,
                "reason": reason,
                "weight": NATIVE_WEIGHTS[weight_group],
                "native": True,
            }
        )

    if strategy == "tendencia":
        if trend_up:
            add("ema_structure", "CALL", "Médias alinhadas para alta.")
        elif trend_down:
            add("ema_structure", "PUT", "Médias alinhadas para baixa.")
        else:
            add("ema_structure", "NEUTRA", "Médias sem alinhamento completo.")

        if adx >= 18 and di > 3:
            add("adx", "CALL", f"Força compradora com ADX {adx:.1f}.", "confirm")
        elif adx >= 18 and di < -3:
            add("adx", "PUT", f"Força vendedora com ADX {adx:.1f}.", "confirm")
        else:
            add("adx", "NEUTRA", f"Força direcional insuficiente (ADX {adx:.1f}).", "confirm")

        if trend_up and close >= ema21 and 48 <= rsi <= 68:
            add("rsi", "CALL", "Preço sustentado acima da média com RSI favorável.", "confirm")
        elif trend_down and close <= ema21 and 32 <= rsi <= 52:
            add("rsi", "PUT", "Preço sustentado abaixo da média com RSI favorável.", "confirm")
        else:
            add("rsi", "NEUTRA", "Preço/RSI sem confirmação.", "confirm")

        if float(row["Close"]) > float(row["Open"]) and float(row["Close"]) >= float(prev["Close"]) and body_ratio >= 0.4:
            add("candle_continuity", "CALL", "Candle comprador de continuidade.", "trigger")
        elif float(row["Close"]) < float(row["Open"]) and float(row["Close"]) <= float(prev["Close"]) and body_ratio >= 0.4:
            add("candle_continuity", "PUT", "Candle vendedor de continuidade.", "trigger")
        else:
            add("candle_continuity", "NEUTRA", "Candle sem força suficiente.", "trigger")

    elif strategy == "reversao":
        bb_lo, bb_hi = float(row["BB_lower"]), float(row["BB_upper"])
        if close <= bb_lo + atr * 0.18:
            add("bollinger", "CALL", "Preço em extremidade inferior.")
        elif close >= bb_hi - atr * 0.18:
            add("bollinger", "PUT", "Preço em extremidade superior.")
        else:
            add("bollinger", "NEUTRA", "Preço sem extremo relevante.")

        if rsi <= 35 and rsi > rsi_prev:
            add("rsi", "CALL", "RSI saindo da sobrevenda.", "confirm")
        elif rsi >= 65 and rsi < rsi_prev:
            add("rsi", "PUT", "RSI saindo da sobrecompra.", "confirm")
        else:
            add("rsi", "NEUTRA", "RSI sem reversão extrema.", "confirm")

        if st_k < 25 and st_k > st_d:
            add("stoch", "CALL", "Estocástico virando para cima.", "confirm")
        elif st_k > 75 and st_k < st_d:
            add("stoch", "PUT", "Estocástico virando para baixo.", "confirm")
        else:
            add("stoch", "NEUTRA", "Sem virada clara do estocástico.", "confirm")

        if lower_wick >= 0.28 and lower_wick > upper_wick * 1.25 and close_location >= 0.58:
            add("rejeicao", "CALL", "Pavio inferior indica rejeição de preços baixos.", "trigger")
        elif upper_wick >= 0.28 and upper_wick > lower_wick * 1.25 and close_location <= 0.42:
            add("rejeicao", "PUT", "Pavio superior indica rejeição de preços altos.", "trigger")
        else:
            add("rejeicao", "NEUTRA", "Sem rejeição clara.", "trigger")

    elif strategy == "rompimento":
        high20 = float(row["range_high_20"])
        low20 = float(row["range_low_20"])
        if close > high20:
            add("donchian", "CALL", "Máxima de 20 candles rompida.")
        elif close < low20:
            add("donchian", "PUT", "Mínima de 20 candles rompida.")
        else:
            add("donchian", "NEUTRA", "Sem rompimento atual.")

        if atr_expand and float(row["Close"]) > float(row["Open"]):
            add("atr", "CALL", "Volatilidade expandindo com candle comprador.", "confirm")
        elif atr_expand and float(row["Close"]) < float(row["Open"]):
            add("atr", "PUT", "Volatilidade expandindo com candle vendedor.", "confirm")
        else:
            add("atr", "NEUTRA", "Volatilidade sem expansão direcional.", "confirm")

        if body_ratio >= 0.5 and close_location >= 0.7:
            add("candle_expansion", "CALL", "Fechamento forte na parte superior.", "trigger")
        elif body_ratio >= 0.5 and close_location <= 0.3:
            add("candle_expansion", "PUT", "Fechamento forte na parte inferior.", "trigger")
        else:
            add("candle_expansion", "NEUTRA", "Candle sem força de rompimento.", "trigger")

        if adx >= 18 and di > 3 and float(row["Close"]) > float(row["Open"]):
            add("adx", "CALL", "Força confirma o rompimento.", "confirm")
        elif adx >= 18 and di < -3 and float(row["Close"]) < float(row["Open"]):
            add("adx", "PUT", "Força confirma o rompimento.", "confirm")
        else:
            add("adx", "NEUTRA", "ADX/DI não confirma.", "confirm")

    elif strategy == "momentum":
        if trend_up:
            add("ema_structure", "CALL", "Estrutura de alta.")
        elif trend_down:
            add("ema_structure", "PUT", "Estrutura de baixa.")
        else:
            add("ema_structure", "NEUTRA", "Estrutura sem alinhamento.")

        if hist > 0 and hist >= prev_hist:
            add("macd", "CALL", "Histograma positivo e acelerando.", "confirm")
        elif hist < 0 and hist <= prev_hist:
            add("macd", "PUT", "Histograma negativo e acelerando.", "confirm")
        else:
            add("macd", "NEUTRA", "MACD sem aceleração.", "confirm")

        if adx >= 18 and di > 3:
            add("adx", "CALL", "Força compradora.", "confirm")
        elif adx >= 18 and di < -3:
            add("adx", "PUT", "Força vendedora.", "confirm")
        else:
            add("adx", "NEUTRA", "Força insuficiente.", "confirm")

        if 53 <= rsi <= 70:
            add("rsi", "CALL", "RSI em zona de impulso comprador.", "trigger")
        elif 30 <= rsi <= 47:
            add("rsi", "PUT", "RSI em zona de impulso vendedor.", "trigger")
        else:
            add("rsi", "NEUTRA", "RSI sem zona de impulso.", "trigger")

    return votes


def _atr_from_df(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 0.0
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"] - df["Close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    values = tr.dropna().to_numpy()
    window = values[-14:]
    return float(window.mean()) if len(window) else 0.0


def _generic_weight(indicator_id: str) -> float:
    return {
        "rsi": 1.5,
        "stoch": 1.3,
        "stochrsi": 1.0,
        "macd": 1.5,
        "ema510": 1.0,
        "ema1020": 1.0,
        "bollinger": 1.2,
        "adx": 1.3,
        "cci": 0.8,
        "williams": 0.8,
        "mfi": 1.0,
        "roc": 0.8,
        "sar": 1.0,
        "obv": 0.8,
        "engolfo": 0.9,
        "atr": 0.9,
        "momentum": 0.8,
        "cmf": 0.9,
        "donchian": 1.0,
        "rejeicao": 0.8,
        "ema_structure": 3.0,
        "candle_continuity": 2.0,
        "candle_expansion": 2.0,
    }.get(indicator_id, 1.0)


def _generic_votes(df: pd.DataFrame, strategy: str, selected: set[str], native_ids: set[str]) -> list[dict]:
    votes = []
    for indicator_id in selected:
        if indicator_id in native_ids:
            continue
        fn = GENERIC_VOTES.get(indicator_id)
        if not fn:
            continue
        try:
            vote, reason = fn(df, len(df) - 1)
        except Exception:
            vote, reason = 0, f"{INDICATOR_BY_ID[indicator_id]['name']} indisponível"
        votes.append(
            {
                "id": indicator_id,
                "name": INDICATOR_BY_ID[indicator_id]["name"],
                "signal": "CALL" if vote > 0 else "PUT" if vote < 0 else "NEUTRA",
                "reason": reason,
                "weight": _generic_weight(indicator_id),
                "native": False,
            }
        )
    return votes


def aggregate_votes(votes: list[dict]) -> dict:
    total = len(votes)
    weighted_bull = sum(float(v.get("weight", 1.0)) for v in votes if v["signal"] == "CALL")
    weighted_bear = sum(float(v.get("weight", 1.0)) for v in votes if v["signal"] == "PUT")
    bulls = sum(1 for v in votes if v["signal"] == "CALL")
    bears = sum(1 for v in votes if v["signal"] == "PUT")
    neutrals = sum(1 for v in votes if v["signal"] == "NEUTRA")
    directional = bulls + bears
    coverage = directional / total * 100 if total else 0.0

    if weighted_bull > weighted_bear:
        direction = "CALL"
        winner, loser = bulls, bears
    elif weighted_bear > weighted_bull:
        direction = "PUT"
        winner, loser = bears, bulls
    else:
        direction = "NEUTRAL"
        winner, loser = max(bulls, bears), min(bulls, bears)

    margin = winner - loser
    if directional < 1:
        direction = "NEUTRAL"
    if margin < 1:
        direction = "NEUTRAL"
    if total and coverage < 25:
        direction = "NEUTRAL"

    if direction == "NEUTRAL":
        confidence = round((winner / directional * 100) if directional else 0.0, 1)
        strength = "Sem direção"
    else:
        concordance = winner / directional if directional else 0
        confidence = round(concordance * 100, 1)
        if confidence >= 75:
            strength = "Forte"
        elif confidence >= 55:
            strength = "Moderada"
        else:
            strength = "Fraca"

    return {
        "direction": direction,
        "confidence": min(98.0, confidence),
        "confluence_score": min(98.0, confidence),
        "strength": strength,
        "bulls": bulls,
        "bears": bears,
        "neutrals": neutrals,
        "total": total,
        "coverage": round(coverage, 1),
        "margin": margin,
        "weightedCall": round(weighted_bull, 3),
        "weightedPut": round(weighted_bear, 3),
    }


def analyze_frame(candles: list[dict], timeframe: str, strategy: str, selected_ids: list[str]) -> dict:
    df = candles_to_df(candles)
    if len(df) < 60:
        raise ValueError("Candles fechados insuficientes para a análise.")
    df = compute_base_indicators(df)
    df = _prepare_extras(df)
    selected = set(selected_ids)
    native_votes = _native_votes(df, strategy, selected)
    native_ids = {vote["id"] for vote in native_votes}
    extra_votes = _generic_votes(df, strategy, selected, native_ids)
    votes = native_votes + extra_votes
    agg = aggregate_votes(votes)
    values = _indicator_values(df)
    return {
        "timeframe": timeframe,
        "price": float(df["Close"].iloc[-1]),
        "signal": agg["direction"],
        "confidence": agg["confidence"],
        "strength": agg["strength"],
        "bulls": agg["bulls"],
        "bears": agg["bears"],
        "neutrals": agg["neutrals"],
        "coverage": agg["coverage"],
        "margin": agg["margin"],
        "weightedCall": agg["weightedCall"],
        "weightedPut": agg["weightedPut"],
        "indicators": votes,
        "values": values,
    }


def _indicator_values(df: pd.DataFrame) -> dict:
    row = df.iloc[-1]
    keys = {
        "EMA5": "EMA5",
        "EMA10": "EMA10",
        "EMA20": "EMA20",
        "EMA9": "EMA9",
        "EMA21": "EMA21",
        "EMA50": "EMA50",
        "RSI": "RSI",
        "StochK": "Stoch_K",
        "StochD": "Stoch_D",
        "StochRSI": "StochRSI",
        "MACD": "MACD",
        "MACDSignal": "MACD_signal",
        "MACDHistogram": "MACD_hist",
        "ADX": "ADX",
        "PlusDI": "PLUS_DI",
        "MinusDI": "MINUS_DI",
        "CCI": "CCI",
        "WilliamsR": "WilliamsR",
        "MFI": "MFI",
        "ROC": "ROC",
        "SAR": "SAR",
        "OBV": "OBV",
        "ATR": "ATR",
        "CMF": "CMF",
        "DonchianHigh": "DC_high",
        "DonchianLow": "DC_low",
        "BollingerUpper": "BB_upper",
        "BollingerLower": "BB_lower",
    }
    out = {}
    for name, column in keys.items():
        value = row.get(column)
        if pd.isna(value):
            continue
        out[name] = round(float(value), 8 if name in {"MACD", "MACDSignal", "MACDHistogram", "SAR", "ATR", "CMF"} else 3)
    return out


def resample(candles: list[dict], minutes: int) -> list[dict]:
    if minutes <= 1:
        return list(candles)
    interval = minutes * 60
    buckets: dict[int, list[dict]] = {}
    for candle in candles:
        timestamp = int(candle.get("time", 0))
        bucket = (timestamp // interval) * interval
        buckets.setdefault(bucket, []).append(candle)
    output = []
    for bucket in sorted(buckets):
        chunk = sorted(buckets[bucket], key=lambda item: int(item.get("time", 0)))
        if len(chunk) < minutes:
            continue
        output.append(
            {
                "time": bucket,
                "open": float(chunk[0]["open"]),
                "high": max(float(item["high"]) for item in chunk),
                "low": min(float(item["low"]) for item in chunk),
                "close": float(chunk[-1]["close"]),
                "volume": sum(float(item.get("volume", 0) or 0) for item in chunk),
            }
        )
    return output


def drop_forming(candles: list[dict], interval_seconds: int) -> list[dict]:
    if not candles:
        return []
    import time
    bucket = int(time.time()) // interval_seconds * interval_seconds
    return [c for c in candles if int(c.get("time", 0)) < bucket]


def expiry_plan(expiry: int) -> tuple[str, str, list[str]]:
    if expiry == 1:
        return "1m", "1m", ["5m", "15m"]
    if expiry == 5:
        return "5m", "1m", ["15m"]
    if expiry == 15:
        return "15m", "1m", ["5m", "15m"]
    raise ValueError("Expiração deve ser 1, 5 ou 15 minutos.")


def choose_automatic(packs: dict[str, dict]) -> str:
    scores = {}
    for name, pack in packs.items():
        if pack["signal"] not in {"CALL", "PUT"}:
            scores[name] = -1.0
            continue
        score = float(pack["confidence"])
        if name == "tendencia" and pack["values"].get("ADX", 0) >= 20:
            score += 5
        if name == "momentum" and abs(pack["values"].get("MACDHistogram", 0)) > 0:
            score += 3
        if name == "rompimento":
            row = pack.get("_row", {})
            score += 2 if float(row.get("body_ratio", 0)) >= 0.5 else 0
        if name == "reversao":
            k = pack["values"].get("StochK", 50)
            score += 2 if k < 25 or k > 75 else 0
        scores[name] = score
    return max(scores, key=scores.get)


def trigger(rows: list[dict], timeframe: str, direction: str) -> dict:
    import time
    if direction not in {"CALL", "PUT"} or len(rows) < 2:
        return {"ready": False, "status": "SEM DIREÇÃO", "confidence": 0.0, "proximity": 0.0}

    current, previous = rows[-1], rows[-2]
    start = float(current.get("time", 0))
    size = TIMEFRAMES[timeframe]["minutes"] * 60
    elapsed = max(0.0, time.time() - start)
    remaining = max(0.0, size - elapsed)
    if elapsed > size * 0.82:
        return {
            "ready": False,
            "status": "PRÓXIMO CANDLE",
            "confidence": 0.0,
            "proximity": 80.0,
            "secondsRemaining": int(round(remaining)),
            "elapsedSeconds": int(round(elapsed)),
            "candleCloseAt": int(round(start + size)) if start else 0,
            "state": "PRÓXIMO CANDLE",
        }

    rng = max(float(current["high"] - current["low"]), 1e-12)
    body = abs(float(current["close"] - current["open"])) / rng
    location = (float(current["close"]) - float(current["low"])) / rng
    price_up = float(current["close"]) >= float(previous["close"])
    price_down = float(current["close"]) <= float(previous["close"])

    if direction == "CALL":
        hits = sum([float(current["close"]) > float(current["open"]), price_up, body >= 0.28, location >= 0.58])
    else:
        hits = sum([float(current["close"]) < float(current["open"]), price_down, body >= 0.28, location <= 0.42])

    ready = hits >= 3
    return {
        "ready": ready,
        "status": "ENTRADA CONFIRMADA" if ready else "AGUARDANDO GATILHO",
        "confidence": round(50 + hits * 12.5, 1),
        "proximity": round(min(99.0, 25 + hits * 20), 1),
        "hits": hits,
        "secondsRemaining": int(round(remaining)),
        "elapsedSeconds": int(round(elapsed)),
        "candleCloseAt": int(round(start + size)) if start else 0,
        "state": "ENTRADA CONFIRMADA" if ready else "SINAL PRÓXIMO" if hits >= 2 else "ATENÇÃO",
    }


def strategy_pack(candles: list[dict], timeframe: str, strategy: str, selected_ids: list[str]) -> dict:
    frame = analyze_frame(candles, timeframe, strategy, selected_ids)
    body = 0.0
    if candles:
        last = candles[-1]
        rng = max(float(last.get("high", 0) - last.get("low", 0)), 1e-12)
        body = abs(float(last.get("close", 0) - last.get("open", 0))) / rng
    frame["_row"] = {"body_ratio": body}
    return frame


def analyze_market(
    base_candles: list[dict],
    expiry: int,
    strategy: str,
    profiles: dict[str, list[str]] | None = None,
) -> dict:
    if strategy not in {"automatica", *STRATEGIES.keys()}:
        raise ValueError("Estratégia inválida.")

    profiles = sanitize_profiles(profiles)
    setup_tf, trigger_tf, context_tfs = expiry_plan(expiry)

    frames = {
        "1m": list(base_candles),
        "5m": resample(base_candles, 5),
        "15m": resample(base_candles, 15),
    }

    closed = {
        tf: drop_forming(frames[tf], TIMEFRAMES[tf]["minutes"] * 60)
        for tf in ("1m", "5m", "15m")
    }

    setup_rows = closed[setup_tf]
    trigger_rows = frames[trigger_tf]
    context_frames = [closed[tf] for tf in context_tfs]

    if len(setup_rows) < 60 or any(len(rows) < 25 for rows in context_frames) or len(trigger_rows) < 2:
        raise ValueError("Dados insuficientes para a análise atual.")

    if strategy == "automatica":
        packs = {
            key: strategy_pack(setup_rows, setup_tf, key, profiles[key])
            for key in STRATEGIES
        }
        selected = choose_automatic(packs)
    else:
        packs = {strategy: strategy_pack(setup_rows, setup_tf, strategy, profiles[strategy])}
        selected = strategy

    setup_pack = packs[selected]
    context_packs = [
        strategy_pack(rows, tf, selected, profiles[selected])
        for tf, rows in zip(context_tfs, context_frames)
    ]

    direction = setup_pack["signal"]
    context_same = sum(
        1
        for pack in context_packs
        if pack["signal"] == direction and direction in {"CALL", "PUT"}
    )
    context_opposite = sum(
        1
        for pack in context_packs
        if pack["signal"] in {"CALL", "PUT"} and pack["signal"] != direction
    )

    context_bonus = 0.0
    if direction in {"CALL", "PUT"}:
        context_bonus = 7.0 * context_same - 8.0 * context_opposite

    trigger_state = trigger(trigger_rows, trigger_tf, direction)
    final_score = max(
        0.0,
        min(
            99.0,
            setup_pack["confidence"] + context_bonus + (trigger_state["confidence"] - 50.0) * 0.12,
        ),
    )

    indicator_ready = (
        direction in {"CALL", "PUT"}
        and setup_pack["confidence"] >= 69
        and setup_pack["weightedCall"] + setup_pack["weightedPut"] > 0
        and (context_same >= 1 or context_opposite == 0)
    )
    final_ready = bool(indicator_ready and trigger_state["ready"])

    active_ids = profiles[selected]
    selected_names = [INDICATOR_BY_ID[item]["name"] for item in active_ids]
    return {
        "signal": direction if final_ready else "AGUARDAR",
        "signalConfirmed": final_ready,
        "score": round(final_score, 1),
        "quality": (
            "MUITO FORTE"
            if final_ready and final_score >= 86
            else "FORTE"
            if final_ready and final_score >= 78
            else "MODERADA"
            if final_ready
            else "SINAL PRÓXIMO"
            if indicator_ready
            else "ANALISANDO MERCADO"
        ),
        "strategy": selected,
        "strategyLabel": STRATEGIES[selected]["name"],
        "strategyDescription": STRATEGIES[selected]["description"],
        "price": setup_rows[-1]["close"],
        "indicatorReadings": setup_pack["indicators"],
        "indicatorSet": selected_names,
        "indicators": setup_pack["values"],
        "buyScore": setup_pack["weightedCall"],
        "sellScore": setup_pack["weightedPut"],
        "coverage": setup_pack["coverage"],
        "reasons": [
            f"{STRATEGIES[selected]['name']}: motor do market-insight-ai com perfil de indicadores personalizado.",
            f"Setup {setup_tf}: {setup_pack['signal']} com {setup_pack['confidence']:.1f}% de confluência.",
            f"Contexto: {context_same} alinhado(s) e {context_opposite} divergente(s).",
            *[f"{v['name']}: {v['signal']} — {v['reason']}" for v in setup_pack["indicators"]],
        ][:10],
        "warnings": [
            "A pontuação é confluência técnica; não é probabilidade estatística de acerto.",
            *(["Contexto divergente; a confirmação permanece bloqueada."] if context_opposite else []),
            *(["Nenhum indicador selecionado para esta estratégia."] if not active_ids else []),
        ][:4],
        "mtf": {
            "context": {
                "timeframe": ",".join(context_tfs),
                "direction": direction if context_same == len(context_packs) and direction in {"CALL", "PUT"} else "MISTO",
                "confidence": round(sum(p["confidence"] for p in context_packs) / len(context_packs), 1),
            },
            "setup": {
                "timeframe": setup_tf,
                "direction": setup_pack["signal"],
                "confidence": setup_pack["confidence"],
            },
            "trigger": {
                "timeframe": trigger_tf,
                "direction": direction,
                "confidence": trigger_state["confidence"],
            },
            "score": round(final_score, 1),
            "liveTrigger": True,
        },
        "entry": {
            **trigger_state,
            "ready": final_ready,
            "direction": direction if final_ready else "AGUARDAR",
            "triggerTimeframe": trigger_tf,
            "setupTimeframe": setup_tf,
            "status": "ENTRADA CONFIRMADA" if final_ready else "SINAL PRÓXIMO" if indicator_ready else "ANALISANDO MERCADO",
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
        "profile": {
            "strategy": selected,
            "indicatorIds": active_ids,
            "indicatorNames": selected_names,
            "totalSelected": len(active_ids),
        },
        "diagnostics": {
            "engine": "market-insight-ai",
            "fastMode": True,
            "backtest": False,
            "aiBlocking": False,
            "strategyEvaluations": 4 if strategy == "automatica" else 1,
            "baseCandles": len(base_candles),
        },
    }


def indicator_catalog() -> list[dict]:
    return [dict(item) for item in INDICATOR_CATALOG]
