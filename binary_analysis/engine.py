from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from . import service

STRATEGIES = {
    "smart_confluence": {
        "name": "Confluência Profissional",
        "description": "Tendência + momentum + estrutura + volatilidade em múltiplos tempos.",
    }
}
MIN_SAMPLE = 20
MIN_ACCURACY = 70.0

def strategy_catalog():
    return STRATEGIES

def _df(candles):
    if not candles:
        return pd.DataFrame()
    d = pd.DataFrame(candles)
    if d.empty:
        return d
    d = d.sort_values("time").drop_duplicates("time")
    for c in ("open","high","low","close","volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["open","high","low","close"])

def indicators(d):
    d = d.copy()
    c,h,l,v = d.close,d.high,d.low,d.volume
    d["ema9"]=c.ewm(span=9,adjust=False).mean()
    d["ema21"]=c.ewm(span=21,adjust=False).mean()
    d["ema50"]=c.ewm(span=50,adjust=False).mean()
    delta=c.diff()
    gain=delta.clip(lower=0).rolling(14).mean()
    loss=(-delta.clip(upper=0)).rolling(14).mean()
    rs=gain/loss.replace(0,np.nan)
    d["rsi"]=(100-100/(1+rs)).fillna(50)
    d["macd"]=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    d["macd_signal"]=d.macd.ewm(span=9,adjust=False).mean()
    mid=c.rolling(20).mean()
    std=c.rolling(20).std()
    d["bb_hi"]=mid+2*std
    d["bb_lo"]=mid-2*std
    tr=pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    d["atr"]=tr.rolling(14).mean()
    up=h.diff(); down=-l.diff()
    plus=((up>down)&(up>0))*up
    minus=((down>up)&(down>0))*down
    atr14=tr.rolling(14).mean().replace(0,np.nan)
    pdi=100*plus.rolling(14).mean()/atr14
    mdi=100*minus.rolling(14).mean()/atr14
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    d["adx"]=dx.rolling(14).mean()
    d["pdi"]=pdi; d["mdi"]=mdi
    low14=l.rolling(14).min(); high14=h.rolling(14).max()
    d["stoch"]=100*(c-low14)/(high14-low14).replace(0,np.nan)
    d["stochd"]=d.stoch.rolling(3).mean()
    d["roc"]=c.pct_change(5)*100
    d["vol_avg"]=v.rolling(20).mean()
    d["body"]=(c-d.open)
    d["range"]=(h-l).replace(0,np.nan)
    d["body_ratio"]=d.body.abs()/d.range
    d["hh20"]=h.shift(1).rolling(20).max()
    d["ll20"]=l.shift(1).rolling(20).min()
    return d

def _vote(row):
    call=put=0
    votes=[]
    def add(name, direction, weight=1):
        nonlocal call,put
        votes.append({"id":name,"name":name,"vote":direction})
        if direction>0: call+=weight
        elif direction<0: put+=weight
    add("trend", 1 if row.ema9>row.ema21>row.ema50 else -1 if row.ema9<row.ema21<row.ema50 else 0, 3)
    add("rsi", 1 if 52<=row.rsi<=68 else -1 if 32<=row.rsi<=48 else 0, 2)
    add("macd", 1 if row.macd>row.macd_signal else -1 if row.macd<row.macd_signal else 0, 2)
    add("adx", 1 if row.adx>=18 and row.pdi>row.mdi else -1 if row.adx>=18 and row.mdi>row.pdi else 0, 2)
    add("stochastic", 1 if row.stoch>row.stochd and row.stoch<85 else -1 if row.stoch<row.stochd and row.stoch>15 else 0, 1)
    add("bollinger", 1 if row.close>row.bb_hi else -1 if row.close<row.bb_lo else 0, 1)
    add("breakout", 1 if row.close>row.hh20 else -1 if row.close<row.ll20 else 0, 2)
    add("candle", 1 if row.body>0 and row.body_ratio>=0.45 else -1 if row.body<0 and row.body_ratio>=0.45 else 0, 1)
    total=call+put
    score=0 if total==0 else max(call,put)/max(1,total)*100
    direction="CALL" if call>put else "PUT" if put>call else None
    return direction, float(score), call, put, votes

def _evaluate(d, index=-1):
    if len(d)<60:
        return None
    row=d.iloc[index]
    if not np.isfinite(row[["ema9","ema21","ema50","rsi","macd","macd_signal","adx","pdi","mdi","stoch","bb_hi","bb_lo","atr"]].astype(float)).all():
        return None
    direction,score,call,put,votes=_vote(row)
    atr_ratio=float(row.atr/row.close*10000) if row.close else 999
    if direction and float(row.adx)>=18:
        score=min(100,score + min(10, float(row.adx-18)/3))
    return {"direction":direction,"score":round(score,1),"call":call,"put":put,"votes":votes,"atr_ratio":atr_ratio}

def _historical_accuracy(d, expiry_bars):
    wins=losses=0
    recent=[]
    start=max(60,len(d)-220)
    end=len(d)-expiry_bars-1
    for i in range(start,end+1):
        ev=_evaluate(d,i)
        if not ev or not ev["direction"] or ev["score"]<70:
            continue
        a=float(d.iloc[i].close); b=float(d.iloc[i+expiry_bars].close)
        win=(b>a) if ev["direction"]=="CALL" else (b<a)
        recent.append("OK" if win else "X")
        wins += int(win); losses += int(not win)
    sample=wins+losses
    rate=(wins/sample*100) if sample else None
    return {"sample_size":sample,"wins":wins,"losses":losses,"rate":round(rate,1) if rate is not None else None,"recent":recent[-12:]}

def _proximity(ev, accuracy):
    score=float(ev["score"] if ev else 0)
    technical=max(0,min(100,score))
    if accuracy["sample_size"] < MIN_SAMPLE:
        gate=0
    elif accuracy["rate"] is None:
        gate=0
    else:
        gate=max(0,min(100,(accuracy["rate"]-MIN_ACCURACY)/10*100))
    return round(min(100, technical*0.75+gate*0.25),1)

def _signal(d1,d5,d15,expiry):
    trigger=_evaluate(d1 if expiry=="1min" else d5)
    context5=_evaluate(d5)
    context15=_evaluate(d15)
    bars=1 if expiry=="1min" else 1
    acc=_historical_accuracy(d1 if expiry=="1min" else d5,bars)
    prox=_proximity(trigger,acc)
    if not trigger:
        return {"signal":None,"confirmed":False,"proximity":{"percent":0,"label":"ANALISANDO MERCADO"},"historical_accuracy":acc,"votes":[],"reason":"Dados insuficientes para calcular o sinal.","candle_count":len(d1 if expiry=="1min" else d5)}
    direction=trigger["direction"]
    contexts=[x["direction"] for x in (context5,context15) if x and x["direction"]]
    agreement=sum(1 for x in contexts if x==direction)
    aligned=agreement>= (1 if expiry=="5min" else 2)
    eligible=bool(direction and trigger["score"]>=70 and aligned and acc["sample_size"]>=MIN_SAMPLE and (acc["rate"] or 0)>=MIN_ACCURACY)
    label="LIMIAR ATINGIDO" if eligible else "SINAL MUITO PRÓXIMO" if prox>=75 else "ATENÇÃO" if prox>=50 else "ANALISANDO MERCADO"
    reason = (
        f"{direction}: confluência técnica confirmada; histórico {acc['rate']:.1f}% em {acc['sample_size']} sinais."
        if eligible else
        "Confluência técnica ainda não atingiu simultaneamente os filtros de contexto e histórico."
    )
    return {
        "signal":direction if eligible else None,
        "confirmed":eligible,
        "proximity":{"percent":prox,"label":label},
        "historical_accuracy":acc,
        "score":trigger["score"],
        "context_agreement":agreement,
        "votes":trigger["votes"],
        "resumo_votos":{"bulls":trigger["call"],"bears":trigger["put"],"neutros":max(0,10-trigger["call"]-trigger["put"])},
        "reason":reason,
        "candle_count":len(d1 if expiry=="1min" else d5),
    }

def analyze_asset(session_id, asset, expiry, strategy="smart_confluence"):
    if strategy not in STRATEGIES:
        raise ValueError("Estratégia inexistente.")
    if expiry not in ("1min","5min"):
        raise ValueError("Expiração inválida.")
    # 1m usa M1 como gatilho + M5/M15 como contexto. 5m usa M5 + M15.
    d1=indicators(_df(service.get_candles(session_id,asset,60,320,include_current=True)))
    d5=indicators(_df(service.get_candles(session_id,asset,300,220,include_current=True)))
    d15=indicators(_df(service.get_candles(session_id,asset,900,160,include_current=True)))
    if min(len(d1),len(d5),len(d15))<70:
        raise ValueError("A IQ Option não forneceu candles suficientes para uma análise confiável.")
    selected=_signal(d1,d5,d15,expiry)
    # A API de histórico usa candles fechados; o gatilho usa o candle atual quando disponível.
    return {
        "asset":asset,
        "strategy":strategy,
        "expiry":expiry,
        "signal":selected,
        "signals":{expiry:selected},
        "selected_signal":selected["signal"],
        "selected_confidence":selected.get("score"),
        "selected_score":selected.get("score"),
        "selected_reason":selected.get("reason"),
        "selected_data_ready":True,
        "selected_candle_count":selected["candle_count"],
        "timeframes":{"trigger":"M1" if expiry=="1min" else "M5","context":["M5","M15"] if expiry=="1min" else ["M15"]},
        "live_candle":True,
    }

def chart_data(session_id, asset, interval, count):
    candles=service.get_candles(session_id,asset,interval,count,include_current=True)
    return {"asset":asset,"interval":interval,"candles":candles}

def backtest_asset(session_id, asset, expiry, count):
    interval=60 if expiry=="1min" else 300
    candles=service.get_candles(session_id,asset,interval,count,include_current=False)
    d=indicators(_df(candles))
    bars=1
    acc=_historical_accuracy(d,bars)
    return {"asset":asset,"expiry":expiry,"sample_size":acc["sample_size"],"wins":acc["wins"],"losses":acc["losses"],"accuracy":acc["rate"],"history":acc["recent"],"minimum_sample":MIN_SAMPLE,"minimum_accuracy":MIN_ACCURACY}
