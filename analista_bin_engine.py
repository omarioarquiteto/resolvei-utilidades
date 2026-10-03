from __future__ import annotations
import numpy as np
import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator, MACD, AroonIndicator, IchimokuIndicator, PSARIndicator, CCIIndicator
from ta.momentum import RSIIndicator, StochasticOscillator, WilliamsRIndicator
from ta.volatility import AverageTrueRange, BollingerBands, KeltnerChannel
from ta.volume import OnBalanceVolumeIndicator, ChaikinMoneyFlowIndicator, MFIIndicator

STRATEGIES={"trend":{"name":"Tendência","weights":[15,15,12,10,10,8,8,8,7,7]},"breakout":{"name":"Rompimento","weights":[15,12,12,12,10,8,8,8,7,8]},"reversion":{"name":"Reversão","weights":[15,12,11,11,10,10,8,8,8,7]}}
NAMES={"trend":["EMA 20/50","EMA 200","ADX > 25","MACD","PSAR","Aroon","RSI 14 / 50","Ichimoku Kumo","OBV","Estocástico"],"breakout":["S/R + Fractals","ATR Expansion","Bollinger Squeeze","Volume Spike","Keltner","Donchian 20","Vela de Força","CMF","VWAP","RSI 7 / 50"],"reversion":["Suporte / Resistência","RSI Extremo","Estocástico Extremo","Bollinger 2.5","CCI","Rejeição de Vela","Williams %R","MFI","Divergência RSI","Envelope EMA"]}
def clean(rows):
 d=pd.DataFrame(rows).copy()
 for c in ["open","high","low","close","volume"]: d[c]=pd.to_numeric(d[c],errors="coerce")
 d["volume"]=d["volume"].fillna(1)
 return d.dropna(subset=["open","high","low","close"]).sort_values("time").drop_duplicates("time").reset_index(drop=True)
def last(s): return float(s.iloc[-1]) if len(s) and pd.notna(s.iloc[-1]) else np.nan
def prev(s): return float(s.iloc[-2]) if len(s)>1 and pd.notna(s.iloc[-2]) else np.nan
def vote(v): return 1 if v>0 else -1 if v<0 else 0
def score_result(strategy,vals):
 w=STRATEGIES[strategy]["weights"]; call=sum(a for a,v in zip(w,vals) if v==1); put=sum(a for a,v in zip(w,vals) if v==-1)
 direction="CALL" if call>put else "PUT" if put>call else "NONE"; score=max(call,put)
 conflict=min(call,put)>=35 and abs(call-put)<20
 signal="SINAL FORTE" if score>=80 and not conflict else "SINAL MODERADO" if score>=65 and not conflict else "SEM SINAL"
 return (direction if signal!="SEM SINAL" else "NONE"),score,signal,call,put
def _candle(d):
 c=d.iloc[-1]; r=max(c.high-c.low,1e-12); b=abs(c.close-c.open); u=c.high-max(c.open,c.close); l=min(c.open,c.close)-c.low
 bull=c.close>c.open and b/r>=.8 and u/r<=.1 and l/r<=.1; bear=c.close<c.open and b/r>=.8 and u/r<=.1 and l/r<=.1
 if len(d)>1:
  p=d.iloc[-2]; bull|=c.close>c.open and p.close<p.open and c.open<=p.close and c.close>=p.open; bear|=c.close<c.open and p.close>p.open and c.open>=p.close and c.close<=p.open
 return 1 if bull else -1 if bear else 0
def _reject(d):
 c=d.iloc[-1]; r=max(c.high-c.low,1e-12); b=abs(c.close-c.open); u=c.high-max(c.open,c.close); l=min(c.open,c.close)-c.low
 return 1 if l>=max(b*2,r*.45) and u<l else -1 if u>=max(b*2,r*.45) and l<u else 0
def _div(d):
 if len(d)<40:return 0
 r=RSIIndicator(d.close,14).rsi(); lows=[i for i in range(2,len(d)-2) if d.low.iloc[i]<d.low.iloc[i-1] and d.low.iloc[i]<d.low.iloc[i+1]]; highs=[i for i in range(2,len(d)-2) if d.high.iloc[i]>d.high.iloc[i-1] and d.high.iloc[i]>d.high.iloc[i+1]]
 if len(lows)>1:
  a,b=lows[-2:]
  if d.low.iloc[b]<d.low.iloc[a] and r.iloc[b]>r.iloc[a]:return 1
 if len(highs)>1:
  a,b=highs[-2:]
  if d.high.iloc[b]>d.high.iloc[a] and r.iloc[b]<r.iloc[a]:return -1
 return 0
def _sr(d):
 p=last(d.close); a=last(AverageTrueRange(d.high,d.low,d.close,14).average_true_range()); tol=max(p*.0015,a*.35 if np.isfinite(a) else p*.001); s=False; r=False
 for w in (5,15,60):
  if len(d)>w: s|=abs(p-float(d.low.iloc[-w-1:-1].min()))<=tol; r|=abs(p-float(d.high.iloc[-w-1:-1].max()))<=tol
 return 1 if s and not r else -1 if r and not s else 0
def analyze(rows,strategy):
 d=clean(rows)
 if len(d)<220: raise ValueError(f"Candles fechados insuficientes: {len(d)}. Necessários pelo menos 220.")
 c=d.close; e20=EMAIndicator(c,20).ema_indicator(); e50=EMAIndicator(c,50).ema_indicator(); e200=EMAIndicator(c,200).ema_indicator()
 ad=ADXIndicator(d.high,d.low,c,14); ax=ad.adx(); dip=ad.adx_pos(); dim=ad.adx_neg(); mc=MACD(c); mac=mc.macd(); ms=mc.macd_signal(); mh=mc.macd_diff()
 ps=PSARIndicator(d.high,d.low,c).psar(); ar=AroonIndicator(c,25); au=ar.aroon_up(); dn=ar.aroon_down(); r14=RSIIndicator(c,14).rsi(); r7=RSIIndicator(c,7).rsi()
 ic=IchimokuIndicator(d.high,d.low,9,26,52); ia=ic.ichimoku_a(); ib=ic.ichimoku_b(); ob=OnBalanceVolumeIndicator(c,d.volume).on_balance_volume(); st=StochasticOscillator(d.high,d.low,c,14,3); sk=st.stoch(); sd=st.stoch_signal()
 atr=AverageTrueRange(d.high,d.low,c,14).average_true_range(); atr_ma20=atr.rolling(20).mean(); bb=BollingerBands(c,20,2); bh=bb.bollinger_hband(); bl=bb.bollinger_lband(); bw=(bh-bl)/c.replace(0,np.nan); kc=KeltnerChannel(d.high,d.low,c,20,10,2); kh=kc.keltner_channel_hband(); kl=kc.keltner_channel_lband()
 vm=d.volume.rolling(20).mean(); dh=d.high.shift(1).rolling(20).max(); dl=d.low.shift(1).rolling(20).min(); cmf=ChaikinMoneyFlowIndicator(d.high,d.low,c,d.volume,20).chaikin_money_flow(); cci=CCIIndicator(d.high,d.low,c,20).cci(); wr=WilliamsRIndicator(d.high,d.low,c,14).williams_r(); mfi=MFIIndicator(d.high,d.low,c,d.volume,14).money_flow_index(); ema=e20; vw=(c*d.volume).rolling(20).sum()/d.volume.rolling(20).sum().replace(0,np.nan)
 if strategy=="trend":
  vals=[1 if last(e20)>last(e50) and last(e20)>=prev(e20) else -1 if last(e20)<last(e50) and last(e20)<=prev(e20) else 0,vote(last(c)-last(e200)),1 if last(ax)>25 and last(dip)>last(dim) else -1 if last(ax)>25 and last(dim)>last(dip) else 0,1 if last(mac)>last(ms) and last(mh)>0 else -1 if last(mac)<last(ms) and last(mh)<0 else 0,vote(last(c)-last(ps)),vote(last(au)-last(dn)),vote(last(r14)-50),1 if last(c)>max(last(ia),last(ib)) else -1 if last(c)<min(last(ia),last(ib)) else 0,1 if last(ob)>prev(ob) and last(c)>prev(c) else -1 if last(ob)<prev(ob) and last(c)<prev(c) else 0,1 if last(sk)>last(sd) and 20<last(sk)<80 else -1 if last(sk)<last(sd) and 20<last(sk)<80 else 0]
 elif strategy=="breakout":
  vs=last(d.volume)>=2*last(vm); vals=[1 if last(c)>last(dh) else -1 if last(c)<last(dl) else 0,1 if last(atr)>1.25*last(atr_ma20) and last(c)>prev(c) else -1 if last(atr)>1.25*last(atr_ma20) and last(c)<prev(c) else 0,1 if last(bw)>float(bw.shift(3).iloc[-1]) and last(c)>last(bh) else -1 if last(bw)>float(bw.shift(3).iloc[-1]) and last(c)<last(bl) else 0,1 if vs and last(c)>prev(c) else -1 if vs and last(c)<prev(c) else 0,1 if last(c)>last(kh) else -1 if last(c)<last(kl) else 0,1 if last(c)>last(dh) else -1 if last(c)<last(dl) else 0,_candle(d),1 if last(cmf)>.05 else -1 if last(cmf)<-.05 else 0,1 if last(c)>last(vw) and last(c)>prev(c) else -1 if last(c)<last(vw) and last(c)<prev(c) else 0,1 if last(r7)>50 and last(r7)-prev(r7)>2 else -1 if last(r7)<50 and last(r7)-prev(r7)<-2 else 0]
 else:
  bb25=BollingerBands(c,20,2.5); vals=[_sr(d),1 if last(r7)<20 or last(r14)<20 else -1 if last(r7)>80 or last(r14)>80 else 0,1 if last(sk)<20 and last(sk)>last(sd) else -1 if last(sk)>80 and last(sk)<last(sd) else 0,1 if last(c)<=last(bb25.bollinger_lband()) else -1 if last(c)>=last(bb25.bollinger_hband()) else 0,1 if last(cci)<-100 else -1 if last(cci)>100 else 0,_reject(d),1 if last(wr)<-80 else -1 if last(wr)>-20 else 0,1 if last(mfi)<20 else -1 if last(mfi)>80 else 0,_div(d),1 if last(c)<last(ema)*.997 else -1 if last(c)>last(ema)*1.003 else 0]
 direction,score,signal,call,put=score_result(strategy,vals); items=[{"name":n,"weight":w,"direction":v,"active":direction!="NONE" and v==(1 if direction=="CALL" else -1)} for n,w,v in zip(NAMES[strategy],STRATEGIES[strategy]["weights"],vals)]
 return {"strategy":strategy,"strategyLabel":STRATEGIES[strategy]["name"],"direction":direction,"score":round(score,1),"signal":signal,"callScore":call,"putScore":put,"indicators":items}
