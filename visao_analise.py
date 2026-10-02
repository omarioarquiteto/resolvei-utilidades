"""Motor de análise do VISÃO OPÇÕES baseado no market-insight-ai.

Mantém as 8 estratégias e os 20 indicadores do motor atual do
market-insight-ai, mas adiciona uma camada de perfil: cada estratégia
possui sua própria lista de indicadores habilitados.

A camada de perfil não mistura estratégias. "Automática" apenas escolhe
uma única estratégia entre as oito pela leitura atual.

Não há execução de ordens nem backtest bloqueante neste módulo.
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
    "trend_pullback": {
        "name": "Retração na tendência",
        "description": "Busca uma correção até a média em uma tendência confirmada.",
        "max_score": 4,
    },
    "breakout": {
        "name": "Rompimento de faixa",
        "description": "Exige fechamento além da máxima ou mínima recente com expansão de volatilidade.",
        "max_score": 3,
    },
    "mean_reversion": {
        "name": "Reversão à média",
        "description": "Procura exaustão nas bandas e confirmação de retorno pelo RSI.",
        "max_score": 3,
    },
    "support_resistance": {
        "name": "Suporte e resistência",
        "description": "Procura rejeição clara em zonas extremas recentes.",
        "max_score": 3,
    },
    "momentum": {
        "name": "Momentum",
        "description": "Exige alinhamento de médias, MACD e força direcional.",
        "max_score": 4,
    },
    "stoch_adx": {
        "name": "Tendência com estocástico",
        "description": "Tendência confirmada por EMA e ADX, com estocástico na mesma direção.",
        "max_score": 3,
    },
    "banda_stoch": {
        "name": "Banda com estocástico",
        "description": "Reversão na banda de Bollinger confirmada por virada do estocástico.",
        "max_score": 3,
    },
    "rsi_divergencia": {
        "name": "Divergência de RSI",
        "description": "Preço faz extremo mas o RSI não acompanha; reversão na divergência.",
        "max_score": 3,
    },
}

# Os 20 indicadores do catálogo declarativo do market-insight-ai, mais
# regras nativas que representam componentes específicos de cada estratégia.
INDICATOR_CATALOG = [
    {"id":"rsi","name":"RSI (14)","description":"Oscilador de momentum; sobrevenda/sobrecompra e viés direcional.","kind":"indicador","weight":1.5},
    {"id":"stoch","name":"Stochastic","description":"Posição do preço na faixa recente, com cruzamentos.","kind":"indicador","weight":1.3},
    {"id":"stochrsi","name":"Stoch RSI","description":"RSI dentro da própria faixa; extremos de sobrevenda/sobrecompra.","kind":"indicador","weight":1.0},
    {"id":"macd","name":"MACD","description":"Convergência/divergência de médias com histograma.","kind":"indicador","weight":1.5},
    {"id":"ema510","name":"EMA 5/10","description":"Médias curtas; tendência de curtíssimo prazo.","kind":"indicador","weight":1.0},
    {"id":"ema1020","name":"EMA 10/20","description":"Médias médias; direção da tendência recente.","kind":"indicador","weight":1.0},
    {"id":"bollinger","name":"Bollinger","description":"Bandas de volatilidade; extremos sugerem reversão.","kind":"indicador","weight":1.2},
    {"id":"adx","name":"ADX / DI","description":"Força direcional da tendência (+DI/-DI).","kind":"indicador","weight":1.3},
    {"id":"cci","name":"CCI","description":"Desvio do preço típico em relação à média; extremos.","kind":"indicador","weight":0.8},
    {"id":"williams","name":"Williams %R","description":"Oscilador de momento; extremos de sobrevenda/sobrecompra.","kind":"indicador","weight":0.8},
    {"id":"mfi","name":"MFI (14)","description":"Money Flow Index com volume; extremos de fluxo.","kind":"indicador","weight":1.0},
    {"id":"roc","name":"ROC (10)","description":"Rate of Change; momentum percentual do preço.","kind":"indicador","weight":0.8},
    {"id":"sar","name":"Parabolic SAR","description":"Ponto de reversão que acompanha o preço.","kind":"indicador","weight":1.0},
    {"id":"obv","name":"OBV","description":"On-Balance Volume; pressão acumulada.","kind":"indicador","weight":0.8},
    {"id":"engolfo","name":"Candle de engolfo","description":"Corpo atual engole o corpo anterior.","kind":"indicador","weight":0.9},
    {"id":"atr","name":"ATR (14)","description":"Expansão de volatilidade do candle.","kind":"indicador","weight":0.9},
    {"id":"momentum10","name":"Momentum (10)","description":"Diferença do fechamento contra 10 velas atrás.","kind":"indicador","weight":0.8},
    {"id":"cmf","name":"CMF (20)","description":"Chaikin Money Flow; fluxo monetário.","kind":"indicador","weight":0.9},
    {"id":"donchian","name":"Donchian (20)","description":"Máxima/mínima da faixa de 20 velas.","kind":"indicador","weight":1.0},
    {"id":"rejeicao","name":"Vela de rejeição","description":"Sombra longa no topo ou na base.","kind":"indicador","weight":0.8},

    {"id":"ema_pullback","name":"EMA 20/50 + Pullback","description":"Regra nativa: tendência por EMA20/EMA50 e proximidade da EMA20.","kind":"regra nativa","weight":1.0},
    {"id":"ema921","name":"EMA 9/21","description":"Regra nativa de alinhamento rápido usada pelas estratégias direcionais.","kind":"regra nativa","weight":1.0},
    {"id":"candle_direction","name":"Candle direcional","description":"Regra nativa: fechamento na direção da estratégia.","kind":"regra nativa","weight":1.0},
    {"id":"candle_expansion","name":"Candle de expansão","description":"Regra nativa: corpo forte e fechamento próximo da extremidade.","kind":"regra nativa","weight":1.0},
    {"id":"rsi_reversal","name":"Reversão do RSI","description":"Regra nativa: RSI extremo virando na direção contrária.","kind":"regra nativa","weight":1.0},
    {"id":"support_zone","name":"Zona de suporte/resistência","description":"Regra nativa: proximidade da máxima/mínima recente.","kind":"regra nativa","weight":1.0},
    {"id":"stoch_reversal","name":"Reversão do Stoch","description":"Regra nativa: Stochastic virando a partir de extremo.","kind":"regra nativa","weight":1.0},
    {"id":"rsi_divergence","name":"Divergência de RSI","description":"Regra nativa: preço e RSI fazem movimentos opostos.","kind":"regra nativa","weight":1.0},
]

INDICATOR_BY_ID = {x["id"]:x for x in INDICATOR_CATALOG}

# Perfis padrão correspondem aos componentes que o market-insight-ai usa
# diretamente em cada uma de suas oito estratégias.
DEFAULT_PROFILES = {
    "trend_pullback":["ema_pullback","adx","rsi","candle_direction"],
    "breakout":["donchian","atr","candle_expansion"],
    "mean_reversion":["bollinger","rsi","rsi_reversal"],
    "support_resistance":["support_zone","rejeicao","candle_direction"],
    "momentum":["ema921","macd","adx","rsi"],
    "stoch_adx":["ema921","adx","stoch","candle_direction"],
    "banda_stoch":["bollinger","stoch","stoch_reversal"],
    "rsi_divergencia":["rsi","rsi_divergence","candle_direction"],
}

P = {
    "trend_pullback":{"adx_min":20,"near_ema_atr":0.8,"rsi_call_min":45,"rsi_call_max":65,"rsi_put_min":35,"rsi_put_max":55},
    "breakout":{"expansao_atr":1.1},
    "mean_reversion":{"rsi_sobrevenda":35,"rsi_sobrecompra":65},
    "support_resistance":{"zona_atr":0.15,"pavio_ratio":1.2},
    "momentum":{"adx_min":22,"rsi_call":52,"rsi_put":48},
    "stoch_adx":{"adx_min":20,"stoch_limite":30},
    "banda_stoch":{"stoch_min":20,"stoch_max":80},
    "rsi_divergencia":{"rsi_limite":45},
}


def default_profiles() -> dict[str,list[str]]:
    return {k:list(v) for k,v in DEFAULT_PROFILES.items()}


def sanitize_profiles(raw: dict | None) -> dict[str,list[str]]:
    base = default_profiles()
    if not isinstance(raw,dict):
        return base
    for strategy in STRATEGIES:
        value = raw.get(strategy)
        if not isinstance(value,list):
            continue
        clean=[]
        for indicator_id in value:
            indicator_id=str(indicator_id or "").strip().lower()
            if indicator_id in INDICATOR_BY_ID and indicator_id not in clean:
                clean.append(indicator_id)
        base[strategy]=clean
    return base


def candles_to_df(candles:list[dict]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame()
    df=pd.DataFrame(candles)
    required={"time","open","high","low","close","volume"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    for column in required:
        df.loc[:,column]=pd.to_numeric(df[column],errors="coerce")
    finite=np.isfinite(df[list(required)].astype(float)).all(axis=1)
    valid=((df["time"]>0)&(df[["open","high","low","close"]]>0).all(axis=1)&
           (df["high"]>=df[["open","close"]].max(axis=1))&
           (df["low"]<=df[["open","close"]].min(axis=1))&
           (df["high"]>=df["low"]))
    df=df.loc[finite&valid].copy()
    if df.empty:
        return pd.DataFrame()
    df.loc[:,"datetime"]=pd.to_datetime(df["time"],unit="s",utc=True)
    df=df.set_index("datetime").sort_index()
    df=df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
    return df[~df.index.duplicated(keep="last")]


def compute_indicators(df:pd.DataFrame) -> pd.DataFrame:
    close,high,low=df["Close"],df["High"],df["Low"]
    for p in (5,10,20):
        df.loc[:,f"EMA{p}"]=close.ewm(span=p,adjust=False).mean()

    delta=close.diff()
    gain=delta.clip(lower=0).rolling(14).mean()
    loss=(-delta.clip(upper=0)).rolling(14).mean()
    rs=gain/loss.replace(0,np.nan)
    rsi=100-(100/(1+rs))
    rsi=rsi.mask((gain>0)&(loss==0),100.0)
    rsi=rsi.mask((gain==0)&(loss>0),0.0)
    rsi=rsi.mask((gain==0)&(loss==0),50.0)
    df.loc[:,"RSI"]=rsi

    low14=low.rolling(14).min()
    high14=high.rolling(14).max()
    df.loc[:,"Stoch_K"]=100*(close-low14)/(high14-low14).replace(0,np.nan)
    df.loc[:,"Stoch_D"]=df["Stoch_K"].rolling(3).mean()

    rsi2=df["RSI"]
    rmin,rmax=rsi2.rolling(14).min(),rsi2.rolling(14).max()
    df.loc[:,"StochRSI"]=(rsi2-rmin)/(rmax-rmin).replace(0,np.nan)*100

    ema12=close.ewm(span=12,adjust=False).mean()
    ema26=close.ewm(span=26,adjust=False).mean()
    df.loc[:,"MACD"]=ema12-ema26
    df.loc[:,"MACD_signal"]=df["MACD"].ewm(span=9,adjust=False).mean()
    df.loc[:,"MACD_hist"]=df["MACD"]-df["MACD_signal"]

    mid=close.rolling(20).mean()
    std=close.rolling(20).std()
    df.loc[:,"BB_upper"]=mid+2*std
    df.loc[:,"BB_lower"]=mid-2*std

    tr=pd.concat([(high-low),(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    df.loc[:,"ATR"]=tr.rolling(14).mean()

    up,down=high.diff(),-low.diff()
    plus_dm=((up>down)&(up>0))*up
    minus_dm=((down>up)&(down>0))*down
    atr14=tr.rolling(14).mean()
    plus_di=100*(plus_dm.rolling(14).mean()/atr14.replace(0,np.nan))
    minus_di=100*(minus_dm.rolling(14).mean()/atr14.replace(0,np.nan))
    dx=100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0,np.nan)
    df.loc[:,"ADX"]=dx.rolling(14).mean()
    df.loc[:,"PLUS_DI"]=plus_di
    df.loc[:,"MINUS_DI"]=minus_di

    tp=(high+low+close)/3
    sma_tp=tp.rolling(20).mean()
    mad=tp.rolling(20).apply(lambda x:np.abs(x-x.mean()).mean(),raw=True)
    df.loc[:,"CCI"]=(tp-sma_tp)/(0.015*mad.replace(0,np.nan))
    df.loc[:,"WilliamsR"]=-100*(high14-close)/(high14-low14).replace(0,np.nan)
    df.loc[:,"EMA50"]=close.ewm(span=50,adjust=False).mean()
    df.loc[:,"EMA9"]=close.ewm(span=9,adjust=False).mean()
    df.loc[:,"EMA21"]=close.ewm(span=21,adjust=False).mean()
    df.loc[:,"range_high_20"]=high.shift(1).rolling(20).max()
    df.loc[:,"range_low_20"]=low.shift(1).rolling(20).min()
    df.loc[:,"body"]=(close-df["Open"]).abs()
    df.loc[:,"upper_wick"]=high-pd.concat([df["Open"],close],axis=1).max(axis=1)
    df.loc[:,"lower_wick"]=pd.concat([df["Open"],close],axis=1).min(axis=1)-low

    typical=(high+low+close)/3
    raw=typical*df["Volume"]
    diff=typical.diff()
    positive=raw.where(diff>0,0.0).rolling(14).sum()
    negative=raw.where(diff<0,0.0).rolling(14).sum()
    df.loc[:,"MFI"]=100-(100/(1+positive/negative.replace(0,np.nan)))
    df.loc[:,"ROC"]=close.pct_change(periods=10)*100

    closes=close.to_numpy(); highs=high.to_numpy(); lows=low.to_numpy()
    sar=np.full(len(df),np.nan)
    af=0.02; af_max=0.2; is_long=True
    ext=lows[0] if len(df) else 0.0; value=closes[0] if len(df) else np.nan
    for k in range(1,len(df)):
        value=value+af*(ext-value)
        if is_long:
            value=min(value,lows[k-1],lows[k])
            if closes[k]<value:
                is_long=False; value=ext; ext=highs[k]; af=0.02
            elif highs[k]>ext:
                ext=highs[k]; af=min(af+0.02,af_max)
        else:
            value=max(value,highs[k-1],highs[k])
            if closes[k]>value:
                is_long=True; value=ext; ext=lows[k]; af=0.02
            elif lows[k]<ext:
                ext=lows[k]; af=min(af+0.02,af_max)
        sar[k]=value
    df.loc[:,"SAR"]=sar

    direction=np.sign(close.diff().fillna(0))
    df.loc[:,"OBV"]=(direction*df["Volume"]).cumsum()

    faixa=(high-low).replace(0,np.nan)
    mfm=((close-low)-(high-close))/faixa
    money_flow=mfm*df["Volume"]
    vol20=df["Volume"].rolling(20).sum().replace(0,np.nan)
    df.loc[:,"CMF"]=money_flow.rolling(20).sum()/vol20
    df.loc[:,"DC_high"]=high.rolling(20).max()
    df.loc[:,"DC_low"]=low.rolling(20).min()
    return df


def _vote_rsi(df,i):
    value=df["RSI"].iloc[i]; prev=df["RSI"].iloc[i-1] if i else value
    if pd.isna(value) or pd.isna(prev): return 0,"RSI sem dados"
    if value<30 and value>prev:return 1,f"RSI {value:.1f} saindo de sobrevenda — CALL"
    if value>70 and value<prev:return -1,f"RSI {value:.1f} saindo de sobrecompra — PUT"
    if value<30:return 1,f"RSI {value:.1f} sobrevenda — CALL"
    if value>70:return -1,f"RSI {value:.1f} sobrecompra — PUT"
    if value>55 and value>prev:return 1,f"RSI {value:.1f} viés de alta — CALL"
    if value<45 and value<prev:return -1,f"RSI {value:.1f} viés de baixa — PUT"
    return 0,f"RSI {value:.1f} neutro"


def _vote_stoch(df,i):
    k,d=df["Stoch_K"].iloc[i],df["Stoch_D"].iloc[i]
    pk=df["Stoch_K"].iloc[i-1] if i else k
    pdv=df["Stoch_D"].iloc[i-1] if i else d
    if any(pd.isna(x) for x in (k,d,pk,pdv)):return 0,"Stoch sem dados"
    if pk<=pdv and k>d and k<30:return 1,f"Stoch cruzou p/ cima em sobrevenda ({k:.1f}) — CALL"
    if pk>=pdv and k<d and k>70:return -1,f"Stoch cruzou p/ baixo em sobrecompra ({k:.1f}) — PUT"
    if k<20:return 1,f"Stoch {k:.1f} sobrevenda — CALL"
    if k>80:return -1,f"Stoch {k:.1f} sobrecompra — PUT"
    return 0,f"Stoch {k:.1f} neutro"


def _vote_stochrsi(df,i):
    value=df["StochRSI"].iloc[i]
    if pd.isna(value):return 0,"Stoch RSI sem dados"
    if value<20:return 1,f"Stoch RSI {value:.1f} sobrevenda — CALL"
    if value>80:return -1,f"Stoch RSI {value:.1f} sobrecompra — PUT"
    return 0,f"Stoch RSI {value:.1f} neutro"


def _vote_macd(df,i):
    m,s,h=df["MACD"].iloc[i],df["MACD_signal"].iloc[i],df["MACD_hist"].iloc[i]
    ph=df["MACD_hist"].iloc[i-1] if i else h
    if any(pd.isna(x) for x in (m,s,h,ph)):return 0,"MACD sem dados"
    if m>s and h>ph:return 1,"MACD acima do sinal com histograma subindo — CALL"
    if m<s and h<ph:return -1,"MACD abaixo do sinal com histograma caindo — PUT"
    if m>s:return 1,"MACD acima da linha de sinal — CALL"
    if m<s:return -1,"MACD abaixo da linha de sinal — PUT"
    return 0,"MACD neutro"


def _vote_ema(df,i,fast,slow):
    a,b=df[fast].iloc[i],df[slow].iloc[i]
    if pd.isna(a) or pd.isna(b):return 0,"EMAs sem dados"
    if a>b:return 1,f"{fast} acima da {slow} — CALL"
    if a<b:return -1,f"{fast} abaixo da {slow} — PUT"
    return 0,"EMAs sem direção"


def _vote_bollinger(df,i):
    c,u,l=df["Close"].iloc[i],df["BB_upper"].iloc[i],df["BB_lower"].iloc[i]
    if pd.isna(u) or pd.isna(l):return 0,"Bollinger sem dados"
    if c<=l:return 1,"Preço na banda inferior — CALL"
    if c>=u:return -1,"Preço na banda superior — PUT"
    return 0,"Preço dentro das bandas"


def _vote_adx(df,i):
    adx,plus,minus=df["ADX"].iloc[i],df["PLUS_DI"].iloc[i],df["MINUS_DI"].iloc[i]
    if pd.isna(adx) or pd.isna(plus) or pd.isna(minus) or adx<20:return 0,"ADX sem tendência forte"
    if plus>minus:return 1,f"ADX {adx:.1f} com +DI dominante — CALL"
    if minus>plus:return -1,f"ADX {adx:.1f} com -DI dominante — PUT"
    return 0,"ADX sem direção"


def _vote_cci(df,i):
    v=df["CCI"].iloc[i]
    if pd.isna(v):return 0,"CCI sem dados"
    if v<-100:return 1,f"CCI {v:.1f} em sobrevenda — CALL"
    if v>100:return -1,f"CCI {v:.1f} em sobrecompra — PUT"
    return 0,f"CCI {v:.1f} neutro"


def _vote_williams(df,i):
    v=df["WilliamsR"].iloc[i]
    if pd.isna(v):return 0,"Williams %R sem dados"
    if v<-80:return 1,f"Williams %R {v:.1f} em sobrevenda — CALL"
    if v>-20:return -1,f"Williams %R {v:.1f} em sobrecompra — PUT"
    return 0,f"Williams %R {v:.1f} neutro"


def _vote_mfi(df,i):
    v,prev=df["MFI"].iloc[i],df["MFI"].iloc[i-1] if i else df["MFI"].iloc[i]
    if pd.isna(v) or pd.isna(prev):return 0,"MFI sem dados"
    if v<20 and v>prev:return 1,f"MFI {v:.1f} saindo de sobrevenda — CALL"
    if v>80 and v<prev:return -1,f"MFI {v:.1f} saindo de sobrecompra — PUT"
    if v<20:return 1,f"MFI {v:.1f} sobrevenda — CALL"
    if v>80:return -1,f"MFI {v:.1f} sobrecompra — PUT"
    return 0,f"MFI {v:.1f} neutro"


def _vote_roc(df,i):
    v=df["ROC"].iloc[i]
    if pd.isna(v):return 0,"ROC sem dados"
    if v>0.5:return 1,f"ROC {v:.2f}% momentum de alta — CALL"
    if v<-0.5:return -1,f"ROC {v:.2f}% momentum de baixa — PUT"
    return 0,f"ROC {v:.2f}% neutro"


def _vote_sar(df,i):
    c,s=df["Close"].iloc[i],df["SAR"].iloc[i]
    if pd.isna(s):return 0,"SAR sem dados"
    if c>s:return 1,f"Preço acima do SAR ({s:.5f}) — CALL"
    if c<s:return -1,f"Preço abaixo do SAR ({s:.5f}) — PUT"
    return 0,"SAR na direção indefinida"


def _vote_obv(df,i):
    v=df["OBV"].iloc[i]
    if pd.isna(v) or i<10:return 0,"OBV sem histórico"
    mean=df["OBV"].iloc[max(0,i-10):i+1].mean()
    if v>mean:return 1,"OBV acima da média — pressão compradora — CALL"
    if v<mean:return -1,"OBV abaixo da média — pressão vendedora — PUT"
    return 0,"OBV neutro"


def _vote_engolfo(df,i):
    if i<1:return 0,"Engolfo sem vela anterior"
    o,c=df["Open"].iloc[i],df["Close"].iloc[i]
    po,pc=df["Open"].iloc[i-1],df["Close"].iloc[i-1]
    body,body_prev=abs(c-o),abs(pc-po)
    if any(pd.isna(x) for x in (o,c,po,pc)) or body<1e-12 or body_prev<1e-12:return 0,"Engolfo sem corpo"
    if c>o and c>=po and o<=pc and body>body_prev*1.2:return 1,"Candle de alta engolfa o anterior — CALL"
    if c<o and c<=po and o>=pc and body>body_prev*1.2:return -1,"Candle de baixa engolfa o anterior — PUT"
    return 0,"Sem engolfo"


def _vote_atr(df,i):
    a,o,c=df["ATR"].iloc[i],df["Open"].iloc[i],df["Close"].iloc[i]
    if pd.isna(a) or a<=0:return 0,"ATR sem dados"
    body=abs(c-o)
    if body>2*a:return (1,f"Expansão ({body/a:.1f}x ATR) de alta — CALL") if c>o else (-1,f"Expansão ({body/a:.1f}x ATR) de baixa — PUT")
    return 0,"Volatilidade normal"


def _vote_momentum10(df,i):
    v=df["Close"].iloc[i]-df["Close"].iloc[i-10] if i>=10 else np.nan
    if pd.isna(v):return 0,"Momentum sem dados"
    if v>0:return 1,f"Momentum +{v:.5f} — CALL"
    if v<0:return -1,f"Momentum {v:.5f} — PUT"
    return 0,"Momentum neutro"


def _vote_cmf(df,i):
    v=df["CMF"].iloc[i]
    if pd.isna(v):return 0,"CMF sem dados"
    if v>0.05:return 1,f"CMF {v:.3f} fluxo comprador — CALL"
    if v<-0.05:return -1,f"CMF {v:.3f} fluxo vendedor — PUT"
    return 0,f"CMF {v:.3f} neutro"


def _vote_donchian(df,i):
    c,hi,lo=df["Close"].iloc[i],df["DC_high"].iloc[i],df["DC_low"].iloc[i]
    if pd.isna(hi) or pd.isna(lo):return 0,"Donchian sem dados"
    if c>=hi:return 1,f"Acima da máxima de 20 velas ({hi:.5f}) — CALL"
    if c<=lo:return -1,f"Abaixo da mínima de 20 velas ({lo:.5f}) — PUT"
    return 0,"Dentro da faixa de 20 velas"


def _vote_rejeicao(df,i):
    o,h,l,c=df["Open"].iloc[i],df["High"].iloc[i],df["Low"].iloc[i],df["Close"].iloc[i]
    if any(pd.isna(x) for x in (o,h,l,c)):return 0,"Sem dados"
    faixa=max(h-l,1e-12); body=abs(c-o); upper=h-max(o,c); lower=min(o,c)-l
    if upper>body*1.5 and upper>faixa*0.5:return -1,"Pavio superior longo — rejeição de alta — PUT"
    if lower>body*1.5 and lower>faixa*0.5:return 1,"Pavio inferior longo — rejeição de baixa — CALL"
    return 0,"Sem rejeição"


GENERIC_VOTES = {
    "rsi":_vote_rsi,"stoch":_vote_stoch,"stochrsi":_vote_stochrsi,"macd":_vote_macd,
    "ema510":lambda d,i:_vote_ema(d,i,"EMA5","EMA10"),
    "ema1020":lambda d,i:_vote_ema(d,i,"EMA10","EMA20"),
    "bollinger":_vote_bollinger,"adx":_vote_adx,"cci":_vote_cci,"williams":_vote_williams,
    "mfi":_vote_mfi,"roc":_vote_roc,"sar":_vote_sar,"obv":_vote_obv,"engolfo":_vote_engolfo,
    "atr":_vote_atr,"momentum10":_vote_momentum10,"cmf":_vote_cmf,"donchian":_vote_donchian,
    "rejeicao":_vote_rejeicao,
}

GENERIC_WEIGHT={item["id"]:item["weight"] for item in INDICATOR_CATALOG}


def _component(indicator_id, signal, reason, score=1.0) -> dict:
    return {
        "id":indicator_id,
        "name":INDICATOR_BY_ID[indicator_id]["name"],
        "signal":signal,
        "reason":reason,
        "weight":float(score),
        "native":True,
    }


def _strategy_components(df:pd.DataFrame,strategy:str) -> list[dict]:
    row,prev=df.iloc[-1],df.iloc[-2]
    close=float(row["Close"]); atr=float(row["ATR"])
    rsi=float(row["RSI"]); rsi_prev=float(prev["RSI"])
    out=[]

    def add(indicator_id, signal, reason):
        out.append(_component(indicator_id,signal,reason,1.0))

    if strategy=="trend_pullback":
        up=bool(row["EMA20"]>row["EMA50"] and row["ADX"]>=P[strategy]["adx_min"])
        down=bool(row["EMA20"]<row["EMA50"] and row["ADX"]>=P[strategy]["adx_min"])
        near=bool(abs(close-row["EMA20"])<=atr*P[strategy]["near_ema_atr"])
        add("ema_pullback","CALL" if up and near else "PUT" if down and near else "NEUTRA","EMA20/EMA50 com proximidade da EMA20.")
        add("adx","CALL" if float(row["ADX"])>=P[strategy]["adx_min"] and up else "PUT" if float(row["ADX"])>=P[strategy]["adx_min"] and down else "NEUTRA",f"ADX {float(row['ADX']):.1f} e direção de tendência.")
        add("rsi","CALL" if up and P[strategy]["rsi_call_min"]<=rsi<=P[strategy]["rsi_call_max"] else "PUT" if down and P[strategy]["rsi_put_min"]<=rsi<=P[strategy]["rsi_put_max"] else "NEUTRA",f"RSI {rsi:.1f} dentro/fora da zona da estratégia.")
        add("candle_direction","CALL" if close>float(row["Open"]) else "PUT" if close<float(row["Open"]) else "NEUTRA","Candle atual na direção do movimento.")

    elif strategy=="breakout":
        expansion=bool(float(row["High"]-row["Low"])>=atr*P[strategy]["expansao_atr"])
        add("donchian","CALL" if close>float(row["range_high_20"]) else "PUT" if close<float(row["range_low_20"]) else "NEUTRA","Rompimento da máxima/mínima de 20 candles.")
        add("atr","CALL" if expansion and close>float(row["Open"]) else "PUT" if expansion and close<float(row["Open"]) else "NEUTRA","Expansão de volatilidade.")
        loc=(float(row["Close"])-float(row["Low"]))/max(float(row["High"]-row["Low"]),1e-12)
        body=abs(close-float(row["Open"]))/max(float(row["High"]-row["Low"]),1e-12)
        add("candle_expansion","CALL" if body>=0.5 and loc>=0.7 else "PUT" if body>=0.5 and loc<=0.3 else "NEUTRA","Candle com corpo e fechamento de expansão.")

    elif strategy=="mean_reversion":
        add("bollinger","CALL" if close<=float(row["BB_lower"]) else "PUT" if close>=float(row["BB_upper"]) else "NEUTRA","Extremo de Bollinger.")
        add("rsi","CALL" if rsi<P[strategy]["rsi_sobrevenda"] else "PUT" if rsi>P[strategy]["rsi_sobrecompra"] else "NEUTRA",f"RSI {rsi:.1f} frente aos limites de reversão.")
        add("rsi_reversal","CALL" if rsi<P[strategy]["rsi_sobrevenda"] and rsi>rsi_prev else "PUT" if rsi>P[strategy]["rsi_sobrecompra"] and rsi<rsi_prev else "NEUTRA","RSI extremo virando para reversão.")

    elif strategy=="support_resistance":
        support=float(df["Low"].iloc[-21:-1].min()); resistance=float(df["High"].iloc[-21:-1].max())
        add("support_zone","CALL" if float(row["Low"])<=support+atr*P[strategy]["zona_atr"] else "PUT" if float(row["High"])>=resistance-atr*P[strategy]["zona_atr"] else "NEUTRA","Preço próximo da zona extrema recente.")
        body=float(row["body"]); lower=float(row["lower_wick"]); upper=float(row["upper_wick"])
        add("rejeicao","CALL" if lower>body*P[strategy]["pavio_ratio"] else "PUT" if upper>body*P[strategy]["pavio_ratio"] else "NEUTRA","Pavio e rejeição na zona.")
        add("candle_direction","CALL" if close>float(row["Open"]) else "PUT" if close<float(row["Open"]) else "NEUTRA","Candle atual reagindo da zona.")

    elif strategy=="momentum":
        add("ema921","CALL" if float(row["EMA9"])>float(row["EMA21"]) else "PUT" if float(row["EMA9"])<float(row["EMA21"]) else "NEUTRA","EMA9/EMA21 alinhadas.")
        add("macd","CALL" if float(row["MACD"])>float(row["MACD_signal"]) else "PUT" if float(row["MACD"])<float(row["MACD_signal"]) else "NEUTRA","MACD alinhado com a direção.")
        adx=float(row["ADX"]); add("adx","CALL" if adx>=P[strategy]["adx_min"] and float(row["PLUS_DI"])>float(row["MINUS_DI"]) else "PUT" if adx>=P[strategy]["adx_min"] and float(row["MINUS_DI"])>float(row["PLUS_DI"]) else "NEUTRA",f"ADX {adx:.1f} e DI.")
        add("rsi","CALL" if rsi>P[strategy]["rsi_call"] else "PUT" if rsi<P[strategy]["rsi_put"] else "NEUTRA",f"RSI {rsi:.1f} frente ao limiar de momentum.")

    elif strategy=="stoch_adx":
        up=bool(float(row["EMA9"])>float(row["EMA21"]) and float(row["ADX"])>=P[strategy]["adx_min"])
        down=bool(float(row["EMA9"])<float(row["EMA21"]) and float(row["ADX"])>=P[strategy]["adx_min"])
        add("ema921","CALL" if up else "PUT" if down else "NEUTRA","EMA9/EMA21 definindo tendência.")
        add("adx","CALL" if up and float(row["PLUS_DI"])>float(row["MINUS_DI"]) else "PUT" if down and float(row["MINUS_DI"])>float(row["PLUS_DI"]) else "NEUTRA",f"ADX {float(row['ADX']):.1f} confirmando força.")
        add("stoch","CALL" if float(row["Stoch_K"])>float(row["Stoch_D"]) and float(row["Stoch_K"])<P[strategy]["stoch_limite"] else "PUT" if float(row["Stoch_K"])<float(row["Stoch_D"]) and float(row["Stoch_K"])>100-P[strategy]["stoch_limite"] else "NEUTRA","Stochastic alinhado à tendência.")
    
    elif strategy=="banda_stoch":
        k=float(row["Stoch_K"]); pk=float(prev["Stoch_K"])
        add("bollinger","CALL" if close<=float(row["BB_lower"]) else "PUT" if close>=float(row["BB_upper"]) else "NEUTRA","Extremo da banda.")
        add("stoch","CALL" if k<P[strategy]["stoch_min"] else "PUT" if k>P[strategy]["stoch_max"] else "NEUTRA",f"Stochastic {k:.1f}.")
        add("stoch_reversal","CALL" if k<P[strategy]["stoch_min"] and k>pk else "PUT" if k>P[strategy]["stoch_max"] and k<pk else "NEUTRA","Virada do Stochastic no extremo.")

    elif strategy=="rsi_divergencia":
        p2=df.iloc[-3]
        pc=float(p2["Close"]); pr=float(p2["RSI"])
        add("rsi","CALL" if rsi<P[strategy]["rsi_limite"] else "PUT" if rsi>100-P[strategy]["rsi_limite"] else "NEUTRA",f"RSI {rsi:.1f}.")
        add("rsi_divergence","CALL" if close<pc and rsi>pr else "PUT" if close>pc and rsi<pr else "NEUTRA","Preço e RSI em movimentos divergentes.")
        add("candle_direction","CALL" if close>float(row["Open"]) else "PUT" if close<float(row["Open"]) else "NEUTRA","Candle confirma ou nega a reversão.")

    return out


def _generic_votes(df,selected:set[str]) -> list[dict]:
    votes=[]
    for indicator_id in selected:
        fn=GENERIC_VOTES.get(indicator_id)
        if not fn: continue
        try:
            vote,reason=fn(df,len(df)-1)
        except Exception:
            vote,reason=0,f"{INDICATOR_BY_ID[indicator_id]['name']} indisponível"
        votes.append({
            "id":indicator_id,
            "name":INDICATOR_BY_ID[indicator_id]["name"],
            "signal":"CALL" if vote>0 else "PUT" if vote<0 else "NEUTRA",
            "reason":reason,
            "weight":float(GENERIC_WEIGHT.get(indicator_id,1.0)),
            "native":False,
        })
    return votes


def _aggregate(votes:list[dict],native_total:int) -> dict:
    bull=sum(float(v["weight"]) for v in votes if v["signal"]=="CALL")
    bear=sum(float(v["weight"]) for v in votes if v["signal"]=="PUT")
    bulls=sum(1 for v in votes if v["signal"]=="CALL")
    bears=sum(1 for v in votes if v["signal"]=="PUT")
    neutrals=sum(1 for v in votes if v["signal"]=="NEUTRA")
    directional=bulls+bears
    total=len(votes)
    coverage=directional/total*100 if total else 0

    if bull>bear: direction="CALL"
    elif bear>bull: direction="PUT"
    else: direction="NEUTRAL"

    # Para perfis personalizados, o quórum dos componentes nativos escala
    # proporcionalmente ao número escolhido. Assim o usuário pode remover
    # componentes sem tornar a estratégia matematicamente impossível.
    selected_native=sum(1 for v in votes if v.get("native"))
    required_native=max(1,math.ceil(selected_native*0.75)) if selected_native else 0
    native_bull=sum(1 for v in votes if v.get("native") and v["signal"]=="CALL")
    native_bear=sum(1 for v in votes if v.get("native") and v["signal"]=="PUT")

    if selected_native:
        native_winner=max(native_bull,native_bear)
        native_loser=min(native_bull,native_bear)
        if native_winner<required_native or native_winner==native_loser:
            direction="NEUTRAL"

    if directional<1 or coverage<25:
        direction="NEUTRAL"

    winner=max(bulls,bears); loser=min(bulls,bears)
    confidence=round((winner/directional*100) if directional else 0,1)
    strength="Forte" if confidence>=75 else "Moderada" if confidence>=55 else "Fraca" if directional else "Sem direção"
    return {
        "direction":direction,
        "confidence":min(98.0,confidence),
        "confluence_score":min(98.0,confidence),
        "strength":strength,
        "bulls":bulls,"bears":bears,"neutrals":neutrals,
        "total":total,"coverage":round(coverage,1),
        "weightedCall":round(bull,3),"weightedPut":round(bear,3),
        "nativeSelected":selected_native,
        "nativeRequired":required_native,
        "nativeBull":native_bull,"nativeBear":native_bear,
    }


def analyze_frame(candles:list[dict],timeframe:str,strategy:str,selected_ids:list[str]) -> dict:
    df=candles_to_df(candles)
    if len(df)<60: raise ValueError("Candles fechados insuficientes para a análise.")
    df=compute_indicators(df)
    selected=set(selected_ids)
    native_components=_strategy_components(df,strategy)
    native_by_id={x["id"]:x for x in native_components}
    votes=[]
    for component in native_components:
        if component["id"] in selected:
            votes.append(component)
    votes.extend(_generic_votes(df,selected-set(native_by_id)))
    agg=_aggregate(votes,len(native_components))
    values=_indicator_values(df)
    return {
        "timeframe":timeframe,
        "price":float(df["Close"].iloc[-1]),
        "signal":agg["direction"],
        "confidence":agg["confidence"],
        "strength":agg["strength"],
        "bulls":agg["bulls"],"bears":agg["bears"],"neutrals":agg["neutrals"],
        "total":agg["total"],"coverage":agg["coverage"],
        "weightedCall":agg["weightedCall"],"weightedPut":agg["weightedPut"],
        "indicators":votes,"values":values,
        "nativeRequired":agg["nativeRequired"],
    }


def _indicator_values(df:pd.DataFrame) -> dict:
    row=df.iloc[-1]
    columns={
        "EMA5":"EMA5","EMA10":"EMA10","EMA20":"EMA20","EMA9":"EMA9","EMA21":"EMA21","EMA50":"EMA50",
        "RSI":"RSI","StochK":"Stoch_K","StochD":"Stoch_D","StochRSI":"StochRSI",
        "MACD":"MACD","MACDSignal":"MACD_signal","MACDHistogram":"MACD_hist",
        "ADX":"ADX","PlusDI":"PLUS_DI","MinusDI":"MINUS_DI","CCI":"CCI","WilliamsR":"WilliamsR",
        "MFI":"MFI","ROC":"ROC","SAR":"SAR","OBV":"OBV","ATR":"ATR","CMF":"CMF",
        "DonchianHigh":"DC_high","DonchianLow":"DC_low","BollingerUpper":"BB_upper","BollingerLower":"BB_lower",
    }
    out={}
    for name,col in columns.items():
        value=row.get(col)
        if pd.isna(value):continue
        out[name]=round(float(value),8 if name in {"MACD","MACDSignal","MACDHistogram","SAR","ATR","CMF"} else 3)
    return out


def resample(candles:list[dict],minutes:int) -> list[dict]:
    if minutes<=1:return list(candles)
    interval=minutes*60; buckets={}
    for candle in candles:
        timestamp=int(candle.get("time",0)); bucket=(timestamp//interval)*interval
        buckets.setdefault(bucket,[]).append(candle)
    output=[]
    for bucket in sorted(buckets):
        chunk=sorted(buckets[bucket],key=lambda x:int(x.get("time",0)))
        if len(chunk)<minutes:continue
        output.append({
            "time":bucket,"open":float(chunk[0]["open"]),
            "high":max(float(x["high"]) for x in chunk),
            "low":min(float(x["low"]) for x in chunk),
            "close":float(chunk[-1]["close"]),
            "volume":sum(float(x.get("volume",0) or 0) for x in chunk),
        })
    return output


def drop_forming(candles:list[dict],interval_seconds:int) -> list[dict]:
    if not candles:return []
    import time
    bucket=int(time.time())//interval_seconds*interval_seconds
    return [c for c in candles if int(c.get("time",0))<bucket]


def expiry_plan(expiry:int) -> tuple[str,str,list[str]]:
    if expiry==1:return "1m","1m",["5m","15m"]
    if expiry==5:return "5m","1m",["15m"]
    if expiry==15:return "15m","1m",["5m","15m"]
    raise ValueError("Expiração deve ser 1, 5 ou 15 minutos.")


def choose_automatic(packs:dict[str,dict]) -> str:
    ranked=[]
    for strategy,pack in packs.items():
        signal=pack.get("signal")
        score=float(pack.get("confidence") or 0)
        if signal in {"CALL","PUT"}: score+=5
        ranked.append((score,strategy))
    ranked.sort(reverse=True)
    return ranked[0][1]


def trigger(rows:list[dict],timeframe:str,direction:str) -> dict:
    import time
    if direction not in {"CALL","PUT"} or len(rows)<2:
        return {"ready":False,"status":"SEM DIREÇÃO","confidence":0.0,"proximity":0.0,"state":"ATENÇÃO"}
    current,previous=rows[-1],rows[-2]
    start=float(current.get("time",0)); size=TIMEFRAMES[timeframe]["minutes"]*60
    elapsed=max(0,time.time()-start); remaining=max(0,size-elapsed)
    if elapsed>size*0.82:
        return {"ready":False,"status":"PRÓXIMO CANDLE","confidence":0.0,"proximity":80.0,
                "secondsRemaining":int(round(remaining)),"elapsedSeconds":int(round(elapsed)),
                "candleCloseAt":int(round(start+size)) if start else 0,"state":"PRÓXIMO CANDLE"}
    rng=max(float(current["high"]-current["low"]),1e-12)
    body=abs(float(current["close"]-current["open"]))/rng
    location=(float(current["close"])-float(current["low"]))/rng
    up=float(current["close"])>=float(previous["close"])
    down=float(current["close"])<=float(previous["close"])
    if direction=="CALL": hits=sum([float(current["close"])>float(current["open"]),up,body>=0.28,location>=0.58])
    else: hits=sum([float(current["close"])<float(current["open"]),down,body>=0.28,location<=0.42])
    ready=hits>=3
    return {"ready":ready,"status":"ENTRADA CONFIRMADA" if ready else "AGUARDANDO GATILHO",
            "confidence":round(50+hits*12.5,1),"proximity":round(min(99,25+hits*20),1),
            "hits":hits,"secondsRemaining":int(round(remaining)),"elapsedSeconds":int(round(elapsed)),
            "candleCloseAt":int(round(start+size)) if start else 0,
            "state":"ENTRADA CONFIRMADA" if ready else "SINAL PRÓXIMO" if hits>=2 else "ATENÇÃO"}


def analyze_market(base_candles:list[dict],expiry:int,strategy:str,profiles:dict[str,list[str]]|None=None) -> dict:
    if strategy!="automatica" and strategy not in STRATEGIES:
        raise ValueError("Estratégia inválida.")
    profiles=sanitize_profiles(profiles)
    setup_tf,trigger_tf,context_tfs=expiry_plan(expiry)
    frames={"1m":list(base_candles),"5m":resample(base_candles,5),"15m":resample(base_candles,15)}
    closed={tf:drop_forming(frames[tf],TIMEFRAMES[tf]["minutes"]*60) for tf in ("1m","5m","15m")}
    setup_rows=closed[setup_tf]; trigger_rows=frames[trigger_tf]; context_frames=[closed[x] for x in context_tfs]
    if len(setup_rows)<60 or any(len(x)<25 for x in context_frames) or len(trigger_rows)<2:
        raise ValueError("Dados insuficientes para a análise atual.")

    if strategy=="automatica":
        packs={s:analyze_frame(setup_rows,setup_tf,s,profiles[s]) for s in STRATEGIES}
        selected=choose_automatic(packs)
    else:
        selected=strategy
        packs={selected:analyze_frame(setup_rows,setup_tf,selected,profiles[selected])}

    setup=packs[selected]
    contexts=[analyze_frame(rows,tf,selected,profiles[selected]) for tf,rows in zip(context_tfs,context_frames)]
    direction=setup["signal"]
    same=sum(1 for p in contexts if p["signal"]==direction and direction in {"CALL","PUT"})
    opposite=sum(1 for p in contexts if p["signal"] in {"CALL","PUT"} and p["signal"]!=direction)
    context_bonus=7*same-8*opposite if direction in {"CALL","PUT"} else 0

    trigger_state=trigger(trigger_rows,trigger_tf,direction)
    final_score=max(0,min(99,setup["confidence"]+context_bonus+(trigger_state["confidence"]-50)*0.12))
    indicator_ready=bool(direction in {"CALL","PUT"} and setup["confidence"]>=55 and
                         (same>=1 or opposite==0) and setup["total"]>0)
    final_ready=bool(indicator_ready and trigger_state["ready"])

    selected_ids=profiles[selected]
    selected_names=[INDICATOR_BY_ID[x]["name"] for x in selected_ids]
    return {
        "signal":direction if final_ready else "AGUARDAR",
        "signalConfirmed":final_ready,
        "score":round(final_score,1),
        "quality":"MUITO FORTE" if final_ready and final_score>=86 else "FORTE" if final_ready and final_score>=76 else "MODERADA" if final_ready else "SINAL PRÓXIMO" if indicator_ready else "ANALISANDO MERCADO",
        "strategy":selected,
        "strategyLabel":STRATEGIES[selected]["name"],
        "strategyDescription":STRATEGIES[selected]["description"],
        "price":setup["price"],
        "indicatorReadings":setup["indicators"],
        "indicatorSet":selected_names,
        "indicators":setup["values"],
        "buyScore":setup["weightedCall"],
        "sellScore":setup["weightedPut"],
        "coverage":setup["coverage"],
        "reasons":[
            f"{STRATEGIES[selected]['name']}: motor de estratégia do market-insight-ai.",
            f"Setup {setup_tf}: {setup['signal']} com {setup['confidence']:.1f}% de confluência.",
            f"Contexto: {same} alinhado(s) e {opposite} divergente(s).",
            *[f"{v['name']}: {v['signal']} — {v['reason']}" for v in setup["indicators"]],
        ][:10],
        "warnings":[
            "A pontuação é confluência técnica; não é probabilidade estatística de acerto.",
            *([ "Contexto divergente; a confirmação permanece bloqueada." ] if opposite else []),
            *([ "Nenhum indicador selecionado para esta estratégia." ] if not selected_ids else []),
        ][:4],
        "mtf":{
            "context":{"timeframe":",".join(context_tfs),
                       "direction":direction if same==len(contexts) and direction in {"CALL","PUT"} else "MISTO",
                       "confidence":round(sum(p["confidence"] for p in contexts)/len(contexts),1)},
            "setup":{"timeframe":setup_tf,"direction":setup["signal"],"confidence":setup["confidence"]},
            "trigger":{"timeframe":trigger_tf,"direction":direction,"confidence":trigger_state["confidence"]},
            "score":round(final_score,1),"liveTrigger":True,
        },
        "entry":{
            **trigger_state,
            "ready":final_ready,
            "direction":direction if final_ready else "AGUARDAR",
            "triggerTimeframe":trigger_tf,"setupTimeframe":setup_tf,
            "status":"ENTRADA CONFIRMADA" if final_ready else "SINAL PRÓXIMO" if indicator_ready else "ANALISANDO MERCADO",
            "instruction":f"CLIQUE NO {direction} AGORA. Confirmação técnica encontrada." if final_ready else f"Monitorando a próxima confirmação para {direction}." if indicator_ready else "Interpretando novamente os indicadores selecionados.",
        },
        "analysisTimeframes":{"context":context_tfs,"setup":setup_tf,"trigger":trigger_tf},
        "profile":{"strategy":selected,"indicatorIds":selected_ids,"indicatorNames":selected_names,"totalSelected":len(selected_ids)},
        "diagnostics":{"engine":"market-insight-ai","strategyMode":"individual","fastMode":True,"backtest":False,"aiBlocking":False,
                       "strategyEvaluations":len(STRATEGIES) if strategy=="automatica" else 1},
    }


def indicator_catalog() -> list[dict]:
    return [
        {"id":x["id"],"name":x["name"],"description":x["description"],"kind":x["kind"],"weight":x["weight"]}
        for x in INDICATOR_CATALOG
    ]
