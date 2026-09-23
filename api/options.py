from __future__ import annotations
import os, math, requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
app=FastAPI(title="Resolvei - Análise Técnica de Forex")
URL="https://api.twelvedata.com/time_series"
SYMBOLS={"EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","USD/CHF","NZD/USD","EUR/GBP","EUR/JPY","GBP/JPY"}
INTERVALS={"1min","5min","15min","30min","1h","4h","1day"}
def key():
    k=os.getenv("TWELVE_DATA_API_KEY","").strip()
    if not k: raise HTTPException(503,"TWELVE_DATA_API_KEY não configurada.")
    return k
def fetch(symbol,interval,size):
    symbol=symbol.upper().strip()
    if symbol not in SYMBOLS or interval not in INTERVALS: raise HTTPException(400,"Par ou timeframe não permitido.")
    try:
        r=requests.get(URL,params={"symbol":symbol,"interval":interval,"outputsize":min(max(int(size),100),5000),"apikey":key(),"order":"ASC"},timeout=12);r.raise_for_status();d=r.json()
    except requests.RequestException as e: raise HTTPException(502,f"Falha ao consultar mercado: {e}") from e
    if d.get("status")=="error" or "values" not in d: raise HTTPException(502,d.get("message","A fonte não retornou candles."))
    out=[]
    for x in d["values"]:
        try: out.append({"datetime":x["datetime"],"open":float(x["open"]),"high":float(x["high"]),"low":float(x["low"]),"close":float(x["close"])})
        except (KeyError,TypeError,ValueError): pass
    if len(out)<60: raise HTTPException(502,"Dados insuficientes para os indicadores.")
    return out
def sma(a,n): return [None if i+1<n else sum(a[i-n+1:i+1])/n for i in range(len(a))]
def ema(a,n):
    o=[None]*len(a)
    if len(a)<n:return o
    e=sum(a[:n])/n;o[n-1]=e;k=2/(n+1)
    for i in range(n,len(a)): e=a[i]*k+o[i-1]*(1-k);o[i]=e
    return o
def rsi(a,n=14):
    o=[None]*len(a)
    if len(a)<=n:return o
    g=[max(a[i]-a[i-1],0) for i in range(1,len(a))];l=[max(a[i-1]-a[i],0) for i in range(1,len(a))]
    ag=sum(g[:n])/n;al=sum(l[:n])/n;o[n]=100 if al==0 else 100-100/(1+ag/al)
    for i in range(n+1,len(a)):
        ag=(ag*(n-1)+g[i-1])/n;al=(al*(n-1)+l[i-1])/n;o[i]=100 if al==0 else 100-100/(1+ag/al)
    return o
def macd(a):
    a12,a26=ema(a,12),ema(a,26);m=[None if a12[i] is None or a26[i] is None else a12[i]-a26[i] for i in range(len(a))]
    v=[x for x in m if x is not None];s=ema(v,9);sig=[None]*len(a);j=0
    for i,x in enumerate(m):
        if x is not None:sig[i]=s[j];j+=1
    return m,sig,[None if m[i] is None or sig[i] is None else m[i]-sig[i] for i in range(len(a))]
def bands(a,n=20):
    mid=sma(a,n);up=[None]*len(a);lo=[None]*len(a)
    for i in range(n-1,len(a)):
        m=mid[i];sd=math.sqrt(sum((x-m)**2 for x in a[i-n+1:i+1])/n);up[i]=m+2*sd;lo[i]=m-2*sd
    return mid,up,lo
def adx(rows,n=14):
    tr=[];p=[];m=[]
    for i,x in enumerate(rows):
        if i==0:tr.append(x["high"]-x["low"]);p.append(0);m.append(0);continue
        u=x["high"]-rows[i-1]["high"];d=rows[i-1]["low"]-x["low"];p.append(max(u,0) if u>d else 0);m.append(max(d,0) if d>u else 0)
        tr.append(max(x["high"]-x["low"],abs(x["high"]-rows[i-1]["close"]),abs(x["low"]-rows[i-1]["close"])))
    av,pp,mm=sma(tr,n),sma(p,n),sma(m,n);dx=[0]*len(rows)
    for i in range(len(rows)):
        if av[i]: 
            pi=100*(pp[i] or 0)/av[i];mi=100*(mm[i] or 0)/av[i];dx[i]=100*abs(pi-mi)/(pi+mi) if pi+mi else 0
    return sma(dx,n)
def indicators(rows):
    c=[x["close"] for x in rows];e9,e21,e50=ema(c,9),ema(c,21),ema(c,50);rv=rsi(c);ml,ms,mh=macd(c);bm,bu,bl=bands(c);ax=adx(rows)
    return {"price":c[-1],"ema9":e9[-1],"ema21":e21[-1],"ema50":e50[-1],"rsi":rv[-1],"macd":ml[-1],"macdSignal":ms[-1],"macdHist":mh[-1],"bbMiddle":bm[-1],"bbUpper":bu[-1],"bbLower":bl[-1],"adx":ax[-1]}
def score(rows):
    x=indicators(rows);s=0;reasons=[];risks=[];p=x["price"]
    if all(x[k] is not None for k in ("ema9","ema21","ema50")):
        if p>x["ema9"]>x["ema21"]>x["ema50"]:s+=25;reasons.append("EMA 9/21/50 alinhadas para cima.")
        elif p<x["ema9"]<x["ema21"]<x["ema50"]:s-=25;reasons.append("EMA 9/21/50 alinhadas para baixo.")
        else:risks.append("Médias sem alinhamento claro.")
    if x["rsi"] is not None:
        if 55<=x["rsi"]<=70:s+=15;reasons.append("RSI em zona de momentum comprador.")
        elif 30<=x["rsi"]<=45:s-=15;reasons.append("RSI em zona de momentum vendedor.")
        elif x["rsi"]>70:risks.append("RSI acima de 70: possível sobrecompra.")
        elif x["rsi"]<30:risks.append("RSI abaixo de 30: possível sobrevenda.")
    if x["macdHist"] is not None:s+=15 if x["macdHist"]>0 else -15;reasons.append("Histograma MACD "+("positivo." if x["macdHist"]>0 else "negativo."))
    if x["adx"] is not None:
        if x["adx"]>=25:s+=10;reasons.append("ADX indica força de tendência.")
        elif x["adx"]<18:risks.append("ADX baixo: possível lateralização.")
    if x["bbUpper"] is not None:s+=5 if p>x["bbMiddle"] else -5
    s=max(-100,min(100,s));return {"score":s,"direction":"alta" if s>=20 else "baixa" if s<=-20 else "neutro","confidence":abs(s),"indicators":x,"reasons":reasons,"risks":risks}
def bt(rows,h):
    w=l=t=0
    for i in range(60,len(rows)-h):
        d=score(rows[:i+1])["direction"]
        if d=="neutro":continue
        a,b=rows[i]["close"],rows[i+h]["close"];ok=(d=="alta" and b>a) or (d=="baixa" and b<a)
        if b==a:t+=1
        elif ok:w+=1
        else:l+=1
    n=w+l+t
    return {"samples":n,"wins":w,"losses":l,"ties":t,"hitRate":w/n*100 if n else 0,"note":"Backtest histórico da regra técnica; não modela payout, spread, slippage ou regras da corretora."}
@app.get("/api/options/health")
def health(): return {"ok":True,"provider":"Twelve Data","configured":bool(os.getenv("TWELVE_DATA_API_KEY"))}
@app.get("/api/options/analyze")
def analyze(symbol:str=Query("EUR/USD"),interval:str=Query("1min"),outputsize:int=Query(300,ge=100,le=5000)):
    r=fetch(symbol,interval,outputsize);return {"provider":"Twelve Data","symbol":symbol.upper(),"interval":interval,"updatedAt":datetime.now(timezone.utc).isoformat(),"candles":r,"analysis":score(r)}
@app.get("/api/options/backtest")
def backtest(symbol:str=Query("EUR/USD"),interval:str=Query("1min"),outputsize:int=Query(1000,ge=100,le=5000),horizon:int=Query(1,ge=1,le=10)):
    r=fetch(symbol,interval,outputsize);return {"provider":"Twelve Data","symbol":symbol.upper(),"interval":interval,"backtest":bt(r,horizon)}
