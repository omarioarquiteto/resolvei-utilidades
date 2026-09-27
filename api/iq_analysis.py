from __future__ import annotations

import time
import numpy as np
import pandas as pd

from .iq_service import get_candles_smart

TIMEFRAMES={
    "1min":{"label":"1 minuto","interval":60},
    "5min":{"label":"5 minutos","interval":300},
    "15min":{"label":"15 minutos","interval":900},
}

STRATEGIES={
 "trend_pullback":{"name":"Retração na tendência","description":"Correção até a média dentro de uma tendência confirmada.","max_score":4,"indicadores":["EMA20/EMA50","ADX","RSI","candle de rejeição"]},
 "breakout":{"name":"Rompimento de faixa","description":"Fechamento além da máxima/mínima recente com expansão de volatilidade.","max_score":3,"indicadores":["máxima/mínima de 20 candles","ATR","candle de expansão"]},
 "mean_reversion":{"name":"Reversão à média","description":"Exaustão nas bandas com confirmação do RSI.","max_score":3,"indicadores":["Bollinger","RSI","reversão do RSI"]},
 "support_resistance":{"name":"Suporte e resistência","description":"Rejeição em zonas extremas recentes.","max_score":3,"indicadores":["zona de 20 candles","pavio","candle de rejeição"]},
 "momentum":{"name":"Momentum","description":"Alinhamento de médias, MACD, ADX e RSI.","max_score":4,"indicadores":["EMA9/EMA21","MACD","ADX","RSI"]},
 "stoch_adx":{"name":"Tendência com estocástico","description":"Tendência confirmada por EMA/ADX com estocástico.","max_score":3,"indicadores":["EMA9/EMA21","ADX","Stochastic","vela direcional"]},
 "banda_stoch":{"name":"Banda com estocástico","description":"Reversão na Bollinger confirmada pelo estocástico.","max_score":3,"indicadores":["Bollinger","Stochastic","reversão do Stoch"]},
 "rsi_divergencia":{"name":"Divergência de RSI","description":"Extremo de preço sem confirmação do RSI.","max_score":3,"indicadores":["RSI","preço","divergência"]},
}

PARAMS={
 "trend_pullback":{"adx_min":20,"near_ema_atr":0.8,"rsi_call_min":45,"rsi_call_max":65,"rsi_put_min":35,"rsi_put_max":55,"min_score":3},
 "breakout":{"expansao_atr":1.1,"min_score":2},
 "mean_reversion":{"rsi_sobrevenda":35,"rsi_sobrecompra":65,"min_score":2},
 "support_resistance":{"zona_atr":0.15,"pavio_ratio":1.2,"min_score":2},
 "momentum":{"adx_min":22,"rsi_call":52,"rsi_put":48,"min_score":3},
 "stoch_adx":{"adx_min":20,"stoch_limite":30,"min_score":2},
 "banda_stoch":{"stoch_min":20,"stoch_max":80,"min_score":2},
 "rsi_divergencia":{"rsi_limite":45,"min_score":2},
}

def strategy_catalog():
    return STRATEGIES

def _df(candles):
    if not candles:return pd.DataFrame()
    df=pd.DataFrame(candles)
    need={"time","open","high","low","close","volume"}
    if not need.issubset(df.columns):return pd.DataFrame()
    for c in need:df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.replace([np.inf,-np.inf],np.nan).dropna(subset=["time","open","high","low","close"])
    df=df[(df.time>0)&(df.high>=df.low)&(df.high>=df[["open","close"]].max(axis=1))&(df.low<=df[["open","close"]].min(axis=1))]
    if df.empty:return pd.DataFrame()
    df["datetime"]=pd.to_datetime(df.time,unit="s",utc=True)
    return df.set_index("datetime").sort_index()[~df.index.duplicated(keep="last")].rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})

def _drop_incomplete(candles,interval):
    bucket=int(time.time())//interval*interval
    return [c for c in candles if int(c.get("time",0))<bucket]

def indicators(df):
    if df.empty:return df
    close,high,low=df.Close,df.High,df.Low
    for p in (5,9,10,20,21,50):df[f"EMA{p}"]=close.ewm(span=p,adjust=False).mean()
    delta=close.diff();gain=delta.clip(lower=0).rolling(14).mean();loss=(-delta.clip(upper=0)).rolling(14).mean()
    rs=gain/loss.replace(0,np.nan);df["RSI"]=100-100/(1+rs)
    df.loc[(gain>0)&(loss==0),"RSI"]=100;df.loc[(gain==0)&(loss>0),"RSI"]=0;df.loc[(gain==0)&(loss==0),"RSI"]=50
    low14,high14=low.rolling(14).min(),high.rolling(14).max()
    df["Stoch_K"]=100*(close-low14)/(high14-low14).replace(0,np.nan);df["Stoch_D"]=df.Stoch_K.rolling(3).mean()
    rmin,rmax=df.RSI.rolling(14).min(),df.RSI.rolling(14).max();df["StochRSI"]=(df.RSI-rmin)/(rmax-rmin).replace(0,np.nan)*100
    e12,e26=close.ewm(span=12,adjust=False).mean(),close.ewm(span=26,adjust=False).mean()
    df["MACD"]=e12-e26;df["MACD_signal"]=df.MACD.ewm(span=9,adjust=False).mean();df["MACD_hist"]=df.MACD-df.MACD_signal
    mid=close.rolling(20).mean();std=close.rolling(20).std();df["BB_middle"]=mid;df["BB_upper"]=mid+2*std;df["BB_lower"]=mid-2*std
    tr=pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1);df["ATR"]=tr.rolling(14).mean()
    up,down=high.diff(),-low.diff();plus=((up>down)&(up>0))*up;minus=((down>up)&(down>0))*down
    atr14=tr.rolling(14).mean();pdi=100*plus.rolling(14).mean()/atr14.replace(0,np.nan);mdi=100*minus.rolling(14).mean()/atr14.replace(0,np.nan)
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan);df["ADX"]=dx.rolling(14).mean();df["PLUS_DI"]=pdi;df["MINUS_DI"]=mdi
    tp=(high+low+close)/3;sma=tp.rolling(20).mean();mad=tp.rolling(20).apply(lambda x:np.abs(x-x.mean()).mean(),raw=True);df["CCI"]=(tp-sma)/(0.015*mad.replace(0,np.nan))
    df["WilliamsR"]=-100*(high14-close)/(high14-low14).replace(0,np.nan)
    df["range_high_20"]=high.shift(1).rolling(20).max();df["range_low_20"]=low.shift(1).rolling(20).min()
    df["body"]=(close-df.Open).abs();df["upper_wick"]=high-pd.concat([df.Open,close],axis=1).max(axis=1);df["lower_wick"]=pd.concat([df.Open,close],axis=1).min(axis=1)-low
    return df

def _signal(direction,score,reason,indicators_list,min_score=3):
    if score<min_score:direction="AGUARDAR"
    return {"signal":direction,"score":int(score),"reason":reason,"indicators":indicators_list}

def _strategy_signal(df,strategy):
    if len(df)<60:return _signal("AGUARDAR",0,"Dados insuficientes para esta estratégia.",[])
    row,prev=df.iloc[-1],df.iloc[-2];close=float(row.Close);atr=float(row.ATR) if pd.notna(row.ATR) else 0
    if atr<=0:return _signal("AGUARDAR",0,"Volatilidade insuficiente.",[])
    p=PARAMS[strategy]
    if strategy=="trend_pullback":
        up=row.EMA20>row.EMA50 and row.ADX>=p["adx_min"];down=row.EMA20<row.EMA50 and row.ADX>=p["adx_min"];near=abs(close-row.EMA20)<=atr*p["near_ema_atr"]
        cs=sum((up,near,p["rsi_call_min"]<=row.RSI<=p["rsi_call_max"],close>row.Open));ps=sum((down,near,p["rsi_put_min"]<=row.RSI<=p["rsi_put_max"],close<row.Open))
        d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Retração confirmada na EMA20 dentro de tendência." if d!="AGUARDAR" else "Retração sem confirmação suficiente.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    if strategy=="breakout":
        ex=row.High-row.Low>=atr*p["expansao_atr"];cs=sum((close>row.range_high_20,ex,close>row.Open));ps=sum((close<row.range_low_20,ex,close<row.Open))
        d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Rompimento confirmado por faixa e expansão." if d!="AGUARDAR" else "Rompimento sem confirmação suficiente.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    if strategy=="mean_reversion":
        cs=sum((close<=row.BB_lower,row.RSI<p["rsi_sobrevenda"],row.RSI>prev.RSI));ps=sum((close>=row.BB_upper,row.RSI>p["rsi_sobrecompra"],row.RSI<prev.RSI))
        d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Reversão confirmada por banda e RSI." if d!="AGUARDAR" else "Reversão sem confirmação suficiente.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    if strategy=="support_resistance":
        support=df.Low.iloc[-21:-1].min();resistance=df.High.iloc[-21:-1].max();cs=sum((row.Low<=support+atr*p["zona_atr"],row.lower_wick>row.body*p["pavio_ratio"],close>row.Open));ps=sum((row.High>=resistance-atr*p["zona_atr"],row.upper_wick>row.body*p["pavio_ratio"],close<row.Open))
        d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Rejeição confirmada por zona e candle." if d!="AGUARDAR" else "Rejeição sem confirmação suficiente.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    if strategy=="momentum":
        cs=sum((row.EMA9>row.EMA21,row.MACD>row.MACD_signal,row.ADX>=p["adx_min"],row.RSI>p["rsi_call"]));ps=sum((row.EMA9<row.EMA21,row.MACD<row.MACD_signal,row.ADX>=p["adx_min"],row.RSI<p["rsi_put"]))
        d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Momentum alinhado entre médias, MACD e ADX." if d!="AGUARDAR" else "Momentum sem alinhamento suficiente.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    if strategy=="stoch_adx":
        tu=row.EMA9>row.EMA21 and row.ADX>=p["adx_min"];td=row.EMA9<row.EMA21 and row.ADX>=p["adx_min"];sc=row.Stoch_K>row.Stoch_D and row.Stoch_K<p["stoch_limite"];sp=row.Stoch_K<row.Stoch_D and row.Stoch_K>100-p["stoch_limite"]
        cs=sum((tu,sc,close>row.Open));ps=sum((td,sp,close<row.Open));d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Tendência e estocástico alinhados." if d!="AGUARDAR" else "Tendência/estocástico sem alinhamento.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    if strategy=="banda_stoch":
        cs=sum((close<=row.BB_lower,row.Stoch_K<p["stoch_min"],row.Stoch_K>prev.Stoch_K));ps=sum((close>=row.BB_upper,row.Stoch_K>p["stoch_max"],row.Stoch_K<prev.Stoch_K));d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Banda e estocástico confirmando a reversão." if d!="AGUARDAR" else "Reversão sem confirmação do estocástico.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    if strategy=="rsi_divergencia":
        p2=df.iloc[-3];cs=sum((close<p2.Close,row.RSI>p2.RSI,row.RSI<p["rsi_limite"],close>row.Open));ps=sum((close>p2.Close,row.RSI<p2.RSI,row.RSI>100-p["rsi_limite"],close<row.Open));d="CALL" if cs>=p["min_score"] and cs>ps else "PUT" if ps>=p["min_score"] and ps>cs else "AGUARDAR"
        return _signal(d,max(cs,ps),"Divergência de RSI favorecendo reversão." if d!="AGUARDAR" else "Divergência sem confirmação.",STRATEGIES[strategy]["indicadores"],p["min_score"])
    raise ValueError(f"Estratégia desconhecida: {strategy}")

def _votes(df):
    if df.empty:return []
    r=df.iloc[-1];prev=df.iloc[-2]
    vals=[]
    def add(name,vote,reason):vals.append({"name":name,"vote":"CALL" if vote>0 else "PUT" if vote<0 else "NEUTRO","reason":reason})
    if pd.notna(r.RSI):
        v=1 if r.RSI<45 and r.RSI>prev.RSI else -1 if r.RSI>55 and r.RSI<prev.RSI else 1 if r.RSI>55 else -1 if r.RSI<45 else 0
        add("RSI",v,f"RSI {r.RSI:.1f}")
    if pd.notna(r.Stoch_K) and pd.notna(r.Stoch_D):
        add("Stochastic",1 if r.Stoch_K>r.Stoch_D and r.Stoch_K<80 else -1 if r.Stoch_K<r.Stoch_D and r.Stoch_K>20 else 0,f"K {r.Stoch_K:.1f} / D {r.Stoch_D:.1f}")
    if pd.notna(r.MACD_hist):add("MACD",1 if r.MACD_hist>0 else -1 if r.MACD_hist<0 else 0,f"Histograma {r.MACD_hist:.5g}")
    add("EMA9/EMA21",1 if r.EMA9>r.EMA21 else -1 if r.EMA9<r.EMA21 else 0,"Alinhamento das médias")
    if pd.notna(r.BB_upper):add("Bollinger",1 if r.Close<=r.BB_lower else -1 if r.Close>=r.BB_upper else 0,"Preço em relação às bandas")
    if pd.notna(r.ADX) and r.ADX>=20:add("ADX",1 if r.PLUS_DI>r.MINUS_DI else -1 if r.MINUS_DI>r.PLUS_DI else 0,f"ADX {r.ADX:.1f}")
    return vals

def _accuracy(df,strategy):
    if len(df)<60:return {"rate":None,"sample_size":0,"wins":0,"label":"Amostra insuficiente"}
    results=[]
    start=max(50,len(df)-50)
    for end in range(start,len(df)-1):
        s=_strategy_signal(df.iloc[:end],strategy)
        if s["signal"] not in ("CALL","PUT"):continue
        entry=float(df.Close.iloc[end-1]);exitp=float(df.Close.iloc[end]);results.append((s["signal"]=="CALL" and exitp>entry) or (s["signal"]=="PUT" and exitp<entry))
    if not results:return {"rate":None,"sample_size":0,"wins":0,"label":"Nenhum sinal comparável"}
    wins=sum(results);return {"rate":round(wins/len(results)*100,1) if len(results)>=10 else None,"sample_size":len(results),"wins":wins,"ultimos":["OK" if x else "ERRO" for x in results[-12:]],"label":"Acerto histórico da regra; não garante o próximo resultado." if len(results)>=10 else "Amostra insuficiente"}

def _proximity(score,max_score):
    ratio=max(0,min(1,score/max_score));return {"label":"SINAL MUITO PRÓXIMO" if ratio>=.75 else "ATENÇÃO" if ratio>=.5 else "AGUARDAR","percent":round(ratio*100,1)}

def analyze_asset(session_id,asset,strategy="trend_pullback"):
    asset=asset.upper().replace("=X","")
    if strategy not in STRATEGIES:raise ValueError("Estratégia desconhecida.")
    signals={}
    for expiry,cfg in TIMEFRAMES.items():
        candles=_drop_incomplete(get_candles_smart(session_id,asset,cfg["interval"],240),cfg["interval"])
        df=indicators(_df(candles))
        decision=_strategy_signal(df,strategy) if not df.empty else _signal("AGUARDAR",0,"Sem dados de mercado.",[])
        votes=_votes(df)
        bulls=sum(v["vote"]=="CALL" for v in votes);bears=sum(v["vote"]=="PUT" for v in votes)
        decision["votos"]=votes;decision["resumo_votos"]={"bulls":bulls,"bears":bears,"neutros":len(votes)-bulls-bears,"total":len(votes),"confianca":round(max(bulls,bears)/len(votes)*100,1) if votes else 0}
        decision["proximity"]=_proximity(decision["score"],STRATEGIES[strategy]["max_score"])
        decision["historical_accuracy"]=_accuracy(df,strategy)
        interval=cfg["interval"];now=int(time.time());expires=((now//interval)+1)*interval
        decision.update({"expiry":expiry,"expires_at":expires,"seconds_remaining":expires-now,"locked":False})
        signals[expiry]=decision
    return {"asset":asset,"strategy":strategy,"strategy_name":STRATEGIES[strategy]["name"],"strategy_description":STRATEGIES[strategy]["description"],"signals":signals}

def get_chart_data(session_id,asset,interval=300,count=200):
    candles=_drop_incomplete(get_candles_smart(session_id,asset,interval,count),interval);df=indicators(_df(candles))
    if df.empty:return {"candles":[],"ema20":[],"ema50":[],"bb_upper":[],"bb_lower":[]}
    return {
      "candles":[{"time":int(i.timestamp()),"open":float(r.Open),"high":float(r.High),"low":float(r.Low),"close":float(r.Close)} for i,r in df.iterrows()],
      "ema20":[{"time":int(i.timestamp()),"value":float(r.EMA20)} for i,r in df.iterrows() if pd.notna(r.EMA20)],
      "ema50":[{"time":int(i.timestamp()),"value":float(r.EMA50)} for i,r in df.iterrows() if pd.notna(r.EMA50)],
      "bb_upper":[{"time":int(i.timestamp()),"value":float(r.BB_upper)} for i,r in df.iterrows() if pd.notna(r.BB_upper)],
      "bb_lower":[{"time":int(i.timestamp()),"value":float(r.BB_lower)} for i,r in df.iterrows() if pd.notna(r.BB_lower)],
    }

def walkforward_asset(session_id,asset,expiry,count=240):
    if expiry not in TIMEFRAMES:raise ValueError("expiry deve ser 1min, 5min ou 15min")
    cfg=TIMEFRAMES[expiry];df=indicators(_df(_drop_incomplete(get_candles_smart(session_id,asset,cfg["interval"],count),cfg["interval"])))
    evaluated=wins=0
    for end in range(60,len(df)):
        s=_strategy_signal(df.iloc[:end],"trend_pullback")
        if s["signal"] not in ("CALL","PUT"):continue
        before=float(df.Close.iloc[end-1]);after=float(df.Close.iloc[end]);evaluated+=1;wins+=int((s["signal"]=="CALL" and after>before) or (s["signal"]=="PUT" and after<before))
    return {"asset":asset.upper(),"expiry":expiry,"sample_size":evaluated,"wins":wins,"losses":evaluated-wins,"win_rate":round(wins/evaluated*100,1) if evaluated else None,"note":"Walk-forward técnico; não é garantia de resultado futuro."}
