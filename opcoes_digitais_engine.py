from __future__ import annotations
import numpy as np
import pandas as pd

STRATEGIES={"trend":{"name":"Tendência","weights":[15,15,12,10,10,8,8,8,7,7]},"breakout":{"name":"Rompimento","weights":[15,12,12,12,10,8,8,8,7,8]},"reversion":{"name":"Reversão","weights":[15,12,11,11,10,10,8,8,8,7]}}
NAMES={"trend":["EMA 20/50","EMA 200","ADX > 25","MACD","PSAR","Aroon","RSI 14 / 50","Ichimoku Kumo","OBV","Estocástico"],"breakout":["S/R + Fractals","ATR Expansion","Bollinger Squeeze","Volume Spike","Keltner","Donchian 20","Vela de Força","CMF","VWAP","RSI 7 / 50"],"reversion":["Suporte / Resistência","RSI Extremo","Estocástico Extremo","Bollinger 2.5","CCI","Rejeição de Vela","Williams %R","MFI","Divergência RSI","Envelope EMA"]}

def S(x,index=None):
    if isinstance(x,pd.Series): return pd.to_numeric(x,errors="coerce").astype(float)
    return pd.Series(x,index=index,dtype="float64")
def clean(rows):
    d=pd.DataFrame(rows).copy()
    for c in ("open","high","low","close","volume"):
        if c not in d: d[c]=1.0 if c=="volume" else np.nan
        d[c]=pd.to_numeric(d[c],errors="coerce").astype(float)
    d["volume"]=d["volume"].fillna(1.0)
    d["time"]=pd.to_numeric(d.get("time",pd.Series(range(len(d)))),errors="coerce")
    return d.dropna(subset=["open","high","low","close"]).sort_values("time").drop_duplicates("time").reset_index(drop=True)
def last(x):
    x=S(x); return float(x.iloc[-1]) if len(x) and pd.notna(x.iloc[-1]) else np.nan
def prev(x):
    x=S(x); return float(x.iloc[-2]) if len(x)>1 and pd.notna(x.iloc[-2]) else np.nan
def vote(x): return 1 if np.isfinite(x) and x>0 else -1 if np.isfinite(x) and x<0 else 0
def ema(x,n): return S(x).ewm(span=n,adjust=False,min_periods=1).mean()
def sma(x,n): return S(x).rolling(n,min_periods=1).mean()
def rsi(x,n=14):
    x=S(x); d=x.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
    au=up.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); ad=dn.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return (100-100/(1+au/ad.replace(0,np.nan))).fillna(50)
def atr(h,l,c,n=14):
    pc=c.shift(1); tr=pd.concat([(h-l).abs(),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=1).mean()
def adx(h,l,c,n=14):
    up=h.diff(); dn=-l.diff(); plus=up.where((up>dn)&(up>0),0.0); minus=dn.where((dn>up)&(dn>0),0.0)
    av=atr(h,l,c,n); dip=100*plus.ewm(alpha=1/n,adjust=False,min_periods=1).mean()/av.replace(0,np.nan); dim=100*minus.ewm(alpha=1/n,adjust=False,min_periods=1).mean()/av.replace(0,np.nan)
    dx=100*(dip-dim).abs()/(dip+dim).replace(0,np.nan); return dx.ewm(alpha=1/n,adjust=False,min_periods=1).mean().fillna(0),dip.fillna(0),dim.fillna(0)
def stoch(h,l,c,n=14):
    lo=l.rolling(n,min_periods=1).min(); hi=h.rolling(n,min_periods=1).max(); k=(100*(c-lo)/(hi-lo).replace(0,np.nan)).fillna(50); return k,k.rolling(3,min_periods=1).mean()
def score(strategy,vals):
    w=STRATEGIES[strategy]["weights"]; call=sum(a for a,v in zip(w,vals) if v==1); put=sum(a for a,v in zip(w,vals) if v==-1); direction="CALL" if call>put else "PUT" if put>call else "NONE"; top=max(call,put); conflict=min(call,put)>=35 and abs(call-put)<20
    signal="SINAL FORTE" if top>=80 and not conflict else "SINAL MODERADO" if top>=65 and not conflict else "SEM SINAL"
    return (direction if signal!="SEM SINAL" else "NONE"),top,signal,call,put
def candle(d):
    c=d.iloc[-1]; r=max(float(c.high-c.low),1e-12); b=abs(float(c.close-c.open)); u=float(c.high-max(c.open,c.close)); l=float(min(c.open,c.close)-c.low); bull=c.close>c.open and b/r>=.8 and u/r<=.1 and l/r<=.1; bear=c.close<c.open and b/r>=.8 and u/r<=.1 and l/r<=.1
    return 1 if bull else -1 if bear else 0
def reject(d):
    c=d.iloc[-1]; r=max(float(c.high-c.low),1e-12); b=abs(float(c.close-c.open)); u=float(c.high-max(c.open,c.close)); l=float(min(c.open,c.close)-c.low)
    return 1 if l>=max(b*2,r*.45) and u<l else -1 if u>=max(b*2,r*.45) and l<u else 0
def divergence(d):
    if len(d)<40:return 0
    r=rsi(d.close); lows=[i for i in range(2,len(d)-2) if d.low.iloc[i]<d.low.iloc[i-1] and d.low.iloc[i]<d.low.iloc[i+1]]; highs=[i for i in range(2,len(d)-2) if d.high.iloc[i]>d.high.iloc[i-1] and d.high.iloc[i]>d.high.iloc[i+1]]
    if len(lows)>1:
        a,b=lows[-2:]
        if d.low.iloc[b]<d.low.iloc[a] and r.iloc[b]>r.iloc[a]: return 1
    if len(highs)>1:
        a,b=highs[-2:]
        if d.high.iloc[b]>d.high.iloc[a] and r.iloc[b]<r.iloc[a]: return -1
    return 0
def sr(d,av):
    p=last(d.close); a=last(av); tol=max(p*.0015,a*.35 if np.isfinite(a) else p*.001); sup=res=False
    for w in (5,15,60):
        if len(d)>w:
            sup=bool(sup or abs(p-float(d.low.iloc[-w-1:-1].min()))<=tol); res=bool(res or abs(p-float(d.high.iloc[-w-1:-1].max()))<=tol)
    return 1 if sup and not res else -1 if res and not sup else 0
def analyze(rows,strategy):
    if strategy not in STRATEGIES: raise ValueError("Estratégia inválida")
    d=clean(rows)
    if len(d)<220: raise ValueError(f"Candles fechados insuficientes: {len(d)}. Necessários pelo menos 220.")
    h=S(d.high,d.index); l=S(d.low,d.index); c=S(d.close,d.index); v=S(d.volume,d.index)
    e20=ema(c,20); e50=ema(c,50); e200=ema(c,200); av=atr(h,l,c); avm=av.rolling(20,min_periods=1).mean(); ax,dip,dim=adx(h,l,c); r14=rsi(c,14); r7=rsi(c,7); sk,sd=stoch(h,l,c)
    mid=sma(c,20); std=c.rolling(20,min_periods=1).std(ddof=0); bh=mid+2*std; bl=mid-2*std; bw=(bh-bl)/c.replace(0,np.nan); bu25=mid+2.5*std; bl25=mid-2.5*std
    vm=v.rolling(20,min_periods=1).mean(); dh=h.shift(1).rolling(20,min_periods=1).max(); dl=l.shift(1).rolling(20,min_periods=1).min(); vw=(c*v).rolling(20,min_periods=1).sum()/v.rolling(20,min_periods=1).sum().replace(0,np.nan)
    cmf=((2*c-h-l)/(h-l).replace(0,np.nan)*v).rolling(20,min_periods=1).sum()/v.rolling(20,min_periods=1).sum().replace(0,np.nan); mac=ema(c,12)-ema(c,26); ms=ema(mac,9); mh=mac-ms
    kc=ema(c,20); kh=kc+2*av; kl=kc-2*av; ob=(np.sign(c.diff().fillna(0))*v).cumsum(); wr=-100*(h.rolling(14,min_periods=1).max()-c)/(h.rolling(14,min_periods=1).max()-l.rolling(14,min_periods=1).min()).replace(0,np.nan)
    tp=(h+l+c)/3; dev=tp.rolling(20,min_periods=1).apply(lambda x: float(np.mean(np.abs(x-np.mean(x)))),raw=True); cci=((tp-sma(tp,20))/(.015*dev.replace(0,np.nan))).fillna(0)
    pos=(c.diff()>0)*c*v; neg=(c.diff()<0)*c*v; mfi=(100-100/(1+pos.rolling(14,min_periods=1).sum()/neg.abs().rolling(14,min_periods=1).sum().replace(0,np.nan))).fillna(50)
    ps=ema(c,5); au=100*h.rolling(25,min_periods=1).apply(lambda x: float(np.argmax(x))+1,raw=True)/25; dn=100*l.rolling(25,min_periods=1).apply(lambda x: float(np.argmin(x))+1,raw=True)/25
    if strategy=="trend":
        ia=ema(c,26); ib=ema(c,52); vals=[1 if last(e20)>last(e50) and last(e20)>=prev(e20) else -1 if last(e20)<last(e50) and last(e20)<=prev(e20) else 0,vote(last(c)-last(e200)),1 if last(ax)>25 and last(dip)>last(dim) else -1 if last(ax)>25 and last(dim)>last(dip) else 0,1 if last(mac)>last(ms) and last(mh)>0 else -1 if last(mac)<last(ms) and last(mh)<0 else 0,vote(last(c)-last(ps)),vote(last(au)-last(dn)),vote(last(r14)-50),1 if last(c)>max(last(ia),last(ib)) else -1 if last(c)<min(last(ia),last(ib)) else 0,1 if last(ob)>prev(ob) and last(c)>prev(c) else -1 if last(ob)<prev(ob) and last(c)<prev(c) else 0,1 if last(sk)>last(sd) and 20<last(sk)<80 else -1 if last(sk)<last(sd) and 20<last(sk)<80 else 0]
    elif strategy=="breakout":
        bw3=float(bw.shift(3).iloc[-1]); vs=last(v)>=2*last(vm); vals=[1 if last(c)>last(dh) else -1 if last(c)<last(dl) else 0,1 if last(av)>1.25*last(avm) and last(c)>prev(c) else -1 if last(av)>1.25*last(avm) and last(c)<prev(c) else 0,1 if last(bw)>bw3 and last(c)>last(bh) else -1 if last(bw)>bw3 and last(c)<last(bl) else 0,1 if vs and last(c)>prev(c) else -1 if vs and last(c)<prev(c) else 0,1 if last(c)>last(kh) else -1 if last(c)<last(kl) else 0,1 if last(c)>last(dh) else -1 if last(c)<last(dl) else 0,candle(d),1 if last(cmf)>.05 else -1 if last(cmf)<-.05 else 0,1 if last(c)>last(vw) and last(c)>prev(c) else -1 if last(c)<last(vw) and last(c)<prev(c) else 0,1 if last(r7)>50 and last(r7)-prev(r7)>2 else -1 if last(r7)<50 and last(r7)-prev(r7)<-2 else 0]
    else:
        vals=[sr(d,av),1 if last(r7)<20 or last(r14)<20 else -1 if last(r7)>80 or last(r14)>80 else 0,1 if last(sk)<20 and last(sk)>last(sd) else -1 if last(sk)>80 and last(sk)<last(sd) else 0,1 if last(c)<=last(bl25) else -1 if last(c)>=last(bu25) else 0,1 if last(cci)<-100 else -1 if last(cci)>100 else 0,reject(d),1 if last(wr)<-80 else -1 if last(wr)>-20 else 0,1 if last(mfi)<20 else -1 if last(mfi)>80 else 0,divergence(d),1 if last(c)<last(e20)*.997 else -1 if last(c)>last(e20)*1.003 else 0]
    direction,sc,signal,call,put=score(strategy,vals); items=[{"name":n,"weight":w,"direction":v,"active":direction!="NONE" and v==(1 if direction=="CALL" else -1)} for n,w,v in zip(NAMES[strategy],STRATEGIES[strategy]["weights"],vals)]
    return {"strategy":strategy,"strategyLabel":STRATEGIES[strategy]["name"],"direction":direction,"score":round(sc,1),"signal":signal,"callScore":call,"putScore":put,"indicators":items}
