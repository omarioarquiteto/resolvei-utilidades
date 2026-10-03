from __future__ import annotations
import asyncio,time
from fastapi import APIRouter,Header,HTTPException
from pydantic import BaseModel
import guru_sinais_iqoption_api as iq_auth
from analista_bin_engine import analyze,STRATEGIES
router=APIRouter(prefix="/api/analista-bin",tags=["ANALISTA BIN"])
INTERVALS={"1m":60,"5m":300}
class Req(BaseModel):
 symbol:str
 timeframe:str="1m"
 strategy:str="trend"
def _session(h): return iq_auth._get_session(h)
@router.post("/login")
async def login(req: iq_auth.IQLoginRequest): return await iq_auth.iq_login(req)
@router.get("/session")
async def session(x_iq_session:str|None=Header(default=None)): return await iq_auth.iq_session(x_iq_session)
@router.get("/assets")
async def assets(x_iq_session:str|None=Header(default=None)): return await iq_auth.iq_assets(x_iq_session)
@router.post("/logout")
async def logout(x_iq_session:str|None=Header(default=None)): return await iq_auth.iq_logout(x_iq_session)
@router.get("/config")
async def config(x_iq_session:str|None=Header(default=None)):
 _session(x_iq_session); return {"strategies":{k:v["name"] for k,v in STRATEGIES.items()},"weights":{k:v["weights"] for k,v in STRATEGIES.items()}}
@router.post("/analyze")
async def run(req:Req,x_iq_session:str|None=Header(default=None)):
 item=_session(x_iq_session)
 if req.timeframe not in INTERVALS: raise HTTPException(400,"Timeframe deve ser 1m ou 5m.")
 if req.strategy not in STRATEGIES: raise HTTPException(400,"Estratégia inválida.")
 symbol=req.symbol.upper().strip()
 try: raw=await asyncio.wait_for(item["client"].get_candles(symbol,INTERVALS[req.timeframe],260,int(time.time())),5)
 except asyncio.TimeoutError: raise HTTPException(504,"A IQ Option demorou para responder.")
 except Exception as e: raise HTTPException(502,f"Falha ao obter candles: {str(e)[:160]}")
 rows=[]
 for x in raw or []:
  try: rows.append({"time":float(x.get("from",x.get("to",0))),"open":float(x["open"]),"high":float(x.get("max",x.get("high"))),"low":float(x.get("min",x.get("low"))),"close":float(x["close"]),"volume":float(x.get("volume") or 1)})
  except: pass
 rows.sort(key=lambda x:x["time"]); now=time.time(); closed=[x for x in rows if x["time"]+INTERVALS[req.timeframe]<=now+0.2]
 if len(closed)<220: raise HTTPException(502,f"Candles fechados insuficientes: {len(closed)}. Aguarde mais dados.")
 result=analyze(closed[-260:],req.strategy); result.update({"ok":True,"symbol":symbol,"timeframe":req.timeframe,"candleTime":closed[-1]["time"],"nextCandleAt":((int(now)//INTERVALS[req.timeframe])+1)*INTERVALS[req.timeframe]})
 return result
