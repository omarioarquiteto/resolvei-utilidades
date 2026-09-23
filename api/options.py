import os, math, requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query

app=FastAPI(title="Resolvei - Análise de Opções Binárias")
URL="https://api.twelvedata.com/time_series"
SYMBOLS={"EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","USD/CHF","NZD/USD","EUR/GBP","EUR/JPY","GBP/JPY"}

def key():
    k=os.getenv("TWELVE_DATA_API_KEY","").strip()
    if not k:
        raise HTTPException(503,"TWELVE_DATA_API_KEY não configurada.")
    return k

def fetch(symbol,size):
    symbol=symbol.upper().strip()
    if symbol not in SYMBOLS:
        raise HTTPException(400,"Par de moedas não permitido.")
    try:
        r=requests.get(
            URL,
            params={
                "symbol":symbol,
                "interval":"1min",
                "outputsize":min(max(int(size),120),5000),
                "apikey":key(),
                "order":"ASC",
            },
            timeout=12,
        )
        r.raise_for_status()
        d=r.json()
    except requests.RequestException as e:
        raise HTTPException(502,f"Falha ao consultar mercado: {e}") from e
    if d.get("status")=="error":
        raise HTTPException(502,d.get("message","A fonte de mercado recusou a consulta."))
    values=d.get("values") or []
    out=[]
    for x in values:
        try:
            out.append({
                "datetime":x.get("datetime",""),
                "open":float(x["open"]),
                "high":float(x["high"]),
                "low":float(x["low"]),
                "close":float(x["close"]),
                "volume":float(x.get("volume") or 0),
            })
        except (KeyError,TypeError,ValueError):
            continue
    if len(out)<80:
        raise HTTPException(502,"Dados insuficientes para os indicadores.")
    return out

def sma(a,n):
    return [None if i+1<n else sum(a[i-n+1:i+1])/n for i in range(len(a))]

def ema(a,n):
    o=[None]*len(a)
    if len(a)<n:return o
    e=sum(a[:n])/n;o[n-1]=e;k=2/(n+1)
    for i in range(n,len(a)):
        e=a[i]*k+o[i-1]*(1-k);o[i]=e
    return o

def rsi(a,n=14):
    o=[None]*len(a)
    if len(a)<=n:return o
    g=[max(a[i]-a[i-1],0) for i in range(1,len(a))]
    l=[max(a[i-1]-a[i],0) for i in range(1,len(a))]
    ag=sum(g[:n])/n;al=sum(l[:n])/n
    o[n]=100 if al==0 else 100-100/(1+ag/al)
    for i in range(n+1,len(a)):
        ag=(ag*(n-1)+g[i-1])/n;al=(al*(n-1)+l[i-1])/n
        o[i]=100 if al==0 else 100-100/(1+ag/al)
    return o

def macd(a):
    a12,a26=ema(a,12),ema(a,26)
    m=[None if a12[i] is None or a26[i] is None else a12[i]-a26[i] for i in range(len(a))]
    v=[x for x in m if x is not None]
    s=ema(v,9);sig=[None]*len(a);j=0
    for i,x in enumerate(m):
        if x is not None:
            sig[i]=s[j];j+=1
    return m,sig,[None if m[i] is None or sig[i] is None else m[i]-sig[i] for i in range(len(a))]

def bands(a,n=20):
    mid=sma(a,n);up=[None]*len(a);lo=[None]*len(a)
    for i in range(n-1,len(a)):
        m=mid[i]
        sd=math.sqrt(sum((x-m)**2 for x in a[i-n+1:i+1])/n)
        up[i]=m+2*sd;lo[i]=m-2*sd
    return mid,up,lo

def adx(rows,n=14):
    tr=[];p=[];m=[]
    for i,x in enumerate(rows):
        if i==0:
            tr.append(x["high"]-x["low"]);p.append(0);m.append(0);continue
        u=x["high"]-rows[i-1]["high"];d=rows[i-1]["low"]-x["low"]
        p.append(max(u,0) if u>d else 0);m.append(max(d,0) if d>u else 0)
        tr.append(max(x["high"]-x["low"],abs(x["high"]-rows[i-1]["close"]),abs(x["low"]-rows[i-1]["close"])))
    atr=sma(tr,n);pp=sma(p,n);mm=sma(m,n);dx=[None]*len(rows)
    for i in range(len(rows)):
        if not atr[i]:continue
        pi=100*(pp[i] or 0)/atr[i];mi=100*(mm[i] or 0)/atr[i]
        dx[i]=100*abs(pi-mi)/(pi+mi) if pi+mi else 0
    return sma([x or 0 for x in dx],n)

def indicators(rows):
    c=[x["close"] for x in rows]
    e9,e21,e50=ema(c,9),ema(c,21),ema(c,50)
    rv=rsi(c);ml,ms,mh=macd(c);bm,bu,bl=bands(c);ax=adx(rows)
    return {
        "price":c[-1],"ema9":e9[-1],"ema21":e21[-1],"ema50":e50[-1],
        "rsi":rv[-1],"macd":ml[-1],"macdSignal":ms[-1],"macdHist":mh[-1],
        "bbMiddle":bm[-1],"bbUpper":bu[-1],"bbLower":bl[-1],"adx":ax[-1]
    }

def score(rows):
    x=indicators(rows);s=0;reasons=[];risks=[];p=x["price"]
    if all(x[k] is not None for k in ("ema9","ema21","ema50")):
        if p>x["ema9"]>x["ema21"]>x["ema50"]:
            s+=25;reasons.append("EMA 9/21/50 alinhadas para cima.")
        elif p<x["ema9"]<x["ema21"]<x["ema50"]:
            s-=25;reasons.append("EMA 9/21/50 alinhadas para baixo.")
        else:risks.append("Médias sem alinhamento claro.")
    if x["rsi"] is not None:
        if x["rsi"]<30:s+=15;reasons.append("RSI em sobrevenda.")
        elif x["rsi"]>70:s-=15;reasons.append("RSI em sobrecompra.")
    if x["macdHist"] is not None:
        if x["macdHist"]>0:s+=20;reasons.append("Histograma MACD positivo.")
        elif x["macdHist"]<0:s-=20;reasons.append("Histograma MACD negativo.")
    if x["adx"] is not None:
        if x["adx"]>=25:
            reasons.append("ADX indica tendência com força relativa.")
        elif x["adx"]<18:
            risks.append("ADX baixo: possível lateralização.")
    if x["bbUpper"] is not None:
        s+=5 if p>x["bbMiddle"] else -5
    s=max(-100,min(100,s))
    return {
        "score":s,
        "direction":"alta" if s>=20 else "baixa" if s<=-20 else "neutro",
        "confidence":abs(s),
        "indicators":x,
        "reasons":reasons,
        "risks":risks,
    }

def bt(rows,expiry):
    call_w=call_l=call_t=put_w=put_l=put_t=0
    for i in range(60,len(rows)-expiry):
        a=score(rows[:i+1])
        d=a["direction"]
        if d=="neutro":continue
        p0=rows[i]["close"];p1=rows[i+expiry]["close"]
        if d=="alta":
            if p1>p0:call_w+=1
            elif p1<p0:call_l+=1
            else:call_t+=1
        else:
            if p1<p0:put_w+=1
            elif p1>p0:put_l+=1
            else:put_t+=1
    call_n=call_w+call_l;put_n=put_w+put_l
    return {
        "samples":call_n+put_n,
        "callWins":call_w,"callLosses":call_l,"callTies":call_t,
        "putWins":put_w,"putLosses":put_l,"putTies":put_t,
        "callHitRate":call_w/call_n*100 if call_n else 0,
        "putHitRate":put_w/put_n*100 if put_n else 0,
        "note":"Backtest histórico da regra técnica usando candles de 1 minuto e comparando o preço após a expiração. Não modela payout, spread, latência, OTC, execução ou regras da corretora."
    }

@app.get("/api/options/health")
def health():
    return {"ok":True,"provider":"Twelve Data","mode":"binary-options","configured":bool(os.getenv("TWELVE_DATA_API_KEY"))}

@app.get("/api/options/analyze")
def analyze(
    symbol:str=Query("EUR/USD"),
    expiry:int=Query(1,ge=1,le=15),
    outputsize:int=Query(1200,ge=120,le=5000),
    entry_index:int=Query(-1),
):
    if expiry not in (1,5,15):
        raise HTTPException(400,"A expiração deve ser 1, 5 ou 15 minutos.")
    rows=fetch(symbol,outputsize)
    idx=len(rows)-1 if entry_index<0 else min(max(entry_index,60),len(rows)-1)
    a=score(rows[:idx+1])
    expiry_idx=idx+expiry
    expiry_price=rows[expiry_idx]["close"] if expiry_idx<len(rows) else None
    return {
        "provider":"Twelve Data","symbol":symbol.upper(),"expiry":expiry,
        "updatedAt":datetime.now(timezone.utc).isoformat(),
        "candles":rows,"entryIndex":idx,
        "entry":{
            **a,
            "entryPrice":rows[idx]["close"],
            "entryTime":rows[idx]["datetime"],
            "expiryPrice":expiry_price,
            "expiryTime":rows[expiry_idx]["datetime"] if expiry_idx<len(rows) else None
        },
        "backtest":bt(rows,expiry)
    }

@app.get("/api/options/backtest")
def backtest(
    symbol:str=Query("EUR/USD"),
    expiry:int=Query(1,ge=1,le=15),
    outputsize:int=Query(1200,ge=120,le=5000),
):
    if expiry not in (1,5,15):
        raise HTTPException(400,"A expiração deve ser 1, 5 ou 15 minutos.")
    rows=fetch(symbol,outputsize)
    return {"provider":"Twelve Data","symbol":symbol.upper(),"expiry":expiry,"backtest":bt(rows,expiry)}
