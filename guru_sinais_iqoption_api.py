from __future__ import annotations
import secrets, threading, time
from typing import Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import guru_sinais_api as guru_base

router=APIRouter(prefix="/api/guru-sinais-iqoption",tags=["GURÚ DOS SINAIS IQOPTION"])
SESSION_TTL=45*60
SESSIONS={}
LOCK=threading.Lock()
ASSET_CACHE={}
CANDLE_CACHE={}
ASSET_TTL=30
CANDLE_TTL=10
INTERVALS={"1m":60,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400}

class IQLoginRequest(BaseModel):
    email:str
    password:str
class IQ2FARequest(BaseModel):
    code:str
class MarketAnalysisRequest(BaseModel):
    symbol:str
    timeframe:str
    strategy:str="automatica"
    analyze_with_ai:bool=False

def _iq_class():
    try:
        from iqoptionapi.stable_api import IQ_Option
        return IQ_Option
    except Exception as exc:
        raise HTTPException(503,"A integração iqoptionapi não está disponível no servidor.") from exc

def _cleanup():
    now=time.time()
    cutoff=now-SESSION_TTL
    with LOCK:
        expired=[sid for sid,v in SESSIONS.items() if v.get("last_used",0)<cutoff]
        for sid in expired:
            item=SESSIONS.pop(sid,None)
            try:
                if item and item.get("api"): item["api"].close()
            except Exception: pass
    for cache,ttl in ((ASSET_CACHE,ASSET_TTL*4),(CANDLE_CACHE,CANDLE_TTL*4)):
        for key,(ts,_) in list(cache.items()):
            if now-ts>ttl: cache.pop(key,None)

def _new_session(api,email,pending=False):
    _cleanup()
    sid=secrets.token_urlsafe(32)
    with LOCK:
        SESSIONS[sid]={"api":api,"email":email,"pending_2fa":pending,"last_used":time.time()}
    return sid

def _session(sid,allow_2fa=False):
    sid=(sid or "").strip()
    if not sid: raise HTTPException(401,"Conecte sua conta da IQ Option primeiro.")
    _cleanup()
    with LOCK:
        item=SESSIONS.get(sid)
        if item: item["last_used"]=time.time()
    if not item: raise HTTPException(401,"A sessão da IQ Option expirou. Faça login novamente.")
    if item.get("pending_2fa") and not allow_2fa:
        raise HTTPException(401,"A IQ Option solicitou verificação em duas etapas.")
    return item

def _connect(api):
    try: result=api.connect()
    except Exception as exc: return False,str(exc)[:220]
    if isinstance(result,tuple):
        return bool(result[0]),str(result[1]) if len(result)>1 else ""
    return bool(result),""

def _assets(api,sid):
    cached=ASSET_CACHE.get(sid)
    if cached and time.time()-cached[0]<ASSET_TTL: return cached[1]
    try: all_open=api.get_all_open_time()
    except Exception as exc:
        raise HTTPException(502,f"Não foi possível consultar os ativos da IQ Option: {str(exc)[:160]}") from exc
    normal,otc={},{}
    priority={"binary":1,"turbo":2,"digital":3}
    for typ in ("digital","turbo","binary"):
        section=all_open.get(typ,{}) if isinstance(all_open,dict) else {}
        for raw,info in section.items():
            name=str(raw or "").upper()
            opened=bool(info.get("open")) if isinstance(info,dict) else False
            if not opened or not (name.endswith("-OTC") or (len(name)==6 and name.isalpha())): continue
            item={"symbol":name,"market":"OTC" if name.endswith("-OTC") else "normal","type":typ,"open":True,"priority":priority[typ]}
            target=otc if name.endswith("-OTC") else normal
            if name not in target or item["priority"]>target[name]["priority"]: target[name]=item
    data={"normal":sorted(normal.values(),key=lambda x:x["symbol"]),"otc":sorted(otc.values(),key=lambda x:x["symbol"]),"updated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    ASSET_CACHE[sid]=(time.time(),data)
    return data

def _candles(api,sid,symbol,timeframe,count=1000):
    seconds=INTERVALS.get(timeframe)
    if not seconds: raise HTTPException(400,"Timeframe não suportado.")
    symbol=str(symbol or "").strip().upper()
    if not symbol: raise HTTPException(400,"Informe o ativo da IQ Option.")
    key=f"{sid}|{symbol}|{timeframe}|{count}"
    cached=CANDLE_CACHE.get(key)
    if cached and time.time()-cached[0]<CANDLE_TTL: return cached[1]
    try: raw=api.get_candles(symbol,seconds,count,time.time())
    except Exception as exc: raise HTTPException(502,f"Falha ao consultar candles da IQ Option: {str(exc)[:170]}") from exc
    if not isinstance(raw,list): raise HTTPException(502,"A IQ Option não retornou candles válidos para esse ativo.")
    rows=[]
    for x in raw:
        try:
            rows.append({"open":float(x["open"]),"high":float(x.get("max",x.get("high"))),"low":float(x.get("min",x.get("low"))),"close":float(x["close"]),"volume":float(x.get("volume") or 0),"datetime":float(x.get("from",x.get("to",0)) or 0)})
        except (TypeError,ValueError,KeyError): pass
    rows.sort(key=lambda x:x["datetime"])
    if len(rows)<60: raise HTTPException(502,"A IQ Option não retornou candles suficientes para a análise técnica.")
    CANDLE_CACHE[key]=(time.time(),rows)
    return rows

def _mtf(api,sid,symbol,timeframe):
    plan=guru_base._mtf_plan(timeframe)
    rows={}
    for tf in dict.fromkeys(plan): rows[tf]=_candles(api,sid,symbol,tf,1000)
    return rows,plan

def _analyze(api,sid,symbol,timeframe,strategy,authorization,with_ai):
    if timeframe not in INTERVALS: raise HTTPException(400,"Timeframe não suportado.")
    symbol=str(symbol or "").strip().upper()
    if not symbol: raise HTTPException(400,"Informe um ativo.")
    mtf,plan=_mtf(api,sid,symbol,timeframe)
    ctf,stf,ttf=plan
    if min(len(mtf[ctf]),len(mtf[stf]),len(mtf[ttf]))<60:
        raise HTTPException(502,"Não foram recebidos candles suficientes para a análise em múltiplos timeframes.")
    families=("tendencia","reversao","rompimento")
    cs=[guru_base._strategy_pack(mtf[ctf],s) for s in families]
    ss=[guru_base._strategy_pack(mtf[stf],s) for s in families]
    ts=[guru_base._strategy_pack(mtf[ttf],s) for s in families]
    if strategy=="automatica":
        candidates=[]
        for s in ss:
            c=next(x for x in cs if x["strategy"]==s["strategy"]); t=next(x for x in ts if x["strategy"]==s["strategy"])
            sig,score,_=guru_base._mtf_score(c,s,t); candidates.append((score if sig!="AGUARDAR" else 0,s))
        selected=max(candidates,key=lambda x:x[0])[1]
    else:
        selected=next((x for x in ss if x["strategy"]==strategy),None)
        if not selected: raise HTTPException(400,"Estratégia não suportada.")
    ctx=next(x for x in cs if x["strategy"]==selected["strategy"])
    trg=next(x for x in ts if x["strategy"]==selected["strategy"])
    base_signal,base_score,notes=guru_base._mtf_score(ctx,selected,trg)
    gemini=guru_base._gemini_review(symbol,f"{ctf} → {stf} → {ttf}",selected["strategy"],ss,mtf[stf][-1]["close"],mtf[stf],authorization) if with_ai else {"available":False,"reason":"Análise com IA desativada."}
    gs=gemini.get("signal"); gc=float(gemini.get("confidence",0)) if gs else 0.0
    if base_signal in {"CALL","PUT"} and gs==base_signal:
        signal=base_signal; score=round(min(99,.72*base_score+.28*gc)); quality="MUITO FORTE" if score>=82 else "FORTE" if score>=72 else "MODERADA"
    elif base_signal in {"CALL","PUT"} and gs in {"CALL","PUT"}:
        signal=base_signal; score=round(max(50,min(90,.82*base_score+.18*gc-8))); quality="CONFLUÊNCIA PARCIAL"
    else:
        signal=base_signal; score=round(base_score); quality="FORTE" if score>=75 else "MODERADA" if score>=65 else "BAIXA"
    reasons=[f"Contexto {ctf}: {ctx['direction']} com {ctx['confidence']:.0f}% de confluência.",f"Setup {stf}: {selected['direction']} com {selected['confidence']:.0f}% de confluência.",f"Gatilho {ttf}: {trg['direction']} com {trg['confidence']:.0f}% de confluência."]+notes
    if gemini.get("available"): reasons.append("Gemini: "+(gemini.get("reason") or "validação concluída."))
    warnings=[]
    if ctx["direction"] in {"CALL","PUT"} and selected["direction"] in {"CALL","PUT"} and ctx["direction"]!=selected["direction"]: warnings.append("Contexto e setup estão em direções opostas.")
    if trg["direction"] in {"CALL","PUT"} and selected["direction"] in {"CALL","PUT"} and trg["direction"]!=selected["direction"]: warnings.append("O gatilho de entrada ainda diverge do setup.")
    if gemini.get("available") and gs in {"CALL","PUT"} and gs!=base_signal: warnings.append("O Gemini divergiu da leitura técnica em múltiplos timeframes.")
    if gemini.get("available") and gemini.get("risk")=="alto": warnings.append("O Gemini classificou o contexto como risco alto.")
    if signal=="AGUARDAR": warnings.append("Sem alinhamento suficiente entre contexto, setup e gatilho.")
    return {"signal":signal,"score":score,"quality":quality,"symbol":symbol,"timeframe":timeframe,"analysisTimeframes":{"context":ctf,"setup":stf,"trigger":ttf},"price":mtf[stf][-1]["close"],"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"buyScore":selected["buy"],"sellScore":selected["sell"],"reasons":reasons[:10],"warnings":warnings[:8],"strategy":selected["strategy"],"strategyLabel":selected["strategyLabel"],"strategies":ss,"mtf":{"context":{"timeframe":ctf,"direction":ctx["direction"],"confidence":ctx["confidence"]},"setup":{"timeframe":stf,"direction":selected["direction"],"confidence":selected["confidence"]},"trigger":{"timeframe":ttf,"direction":trg["direction"],"confidence":trg["confidence"]},"score":base_score,"notes":notes},"gemini":gemini,"indicators":selected["values"],"source":"IQ Option + motor técnico MTF + Gemini"}

@router.post("/login")
def login(req:IQLoginRequest):
    email=req.email.strip(); password=req.password
    if not email or not password: raise HTTPException(400,"Informe e-mail e senha da IQ Option.")
    IQ_Option=_iq_class()
    try: api=IQ_Option(email,password)
    except Exception as exc: raise HTTPException(502,"Não foi possível iniciar a conexão com a IQ Option.") from exc
    sid=_new_session(api,email)
    status,reason=_connect(api)
    if status: return {"ok":True,"session_id":sid,"connected":True,"requires_2fa":False}
    if str(reason).upper()=="2FA":
        with LOCK: SESSIONS[sid]["pending_2fa"]=True
        return {"ok":True,"session_id":sid,"connected":False,"requires_2fa":True}
    with LOCK: SESSIONS.pop(sid,None)
    try: api.close()
    except Exception: pass
    raise HTTPException(401,f"A IQ Option não autorizou o login: {str(reason or 'credenciais rejeitadas ou conexão recusada')[:220]}")

@router.post("/2fa")
def two_fa(req:IQ2FARequest,x_iq_session:str|None=Header(default=None)):
    code=req.code.strip()
    if not code.isdigit() or not 4<=len(code)<=10: raise HTTPException(400,"Código de verificação inválido.")
    item=_session(x_iq_session,True)
    try: result=item["api"].connect_2fa(code)
    except Exception as exc: raise HTTPException(502,"Falha na validação do código.") from exc
    if isinstance(result,tuple): status=bool(result[0]); reason=str(result[1]) if len(result)>1 else ""
    else: status=bool(result); reason=""
    if not status: raise HTTPException(401,f"A IQ Option não aceitou o código: {reason[:180] or 'código inválido'}")
    item["pending_2fa"]=False; item["last_used"]=time.time()
    return {"ok":True,"session_id":x_iq_session,"connected":True}

@router.get("/session")
def session(x_iq_session:str|None=Header(default=None)):
    item=_session(x_iq_session)
    try: connected=bool(item["api"].check_connect())
    except Exception: connected=False
    if not connected: raise HTTPException(401,"A conexão com a IQ Option foi encerrada. Faça login novamente.")
    return {"ok":True,"connected":True}

@router.get("/assets")
def assets(x_iq_session:str|None=Header(default=None)):
    item=_session(x_iq_session)
    return _assets(item["api"],x_iq_session or "")

@router.post("/logout")
def logout(x_iq_session:str|None=Header(default=None)):
    sid=(x_iq_session or "").strip()
    with LOCK: item=SESSIONS.pop(sid,None)
    ASSET_CACHE.pop(sid,None)
    for key in list(CANDLE_CACHE):
        if key.startswith(sid+"|"): CANDLE_CACHE.pop(key,None)
    if item:
        try: item["api"].close()
        except Exception: pass
    return {"ok":True}

@router.post("/market-analysis")
def market_analysis(req:MarketAnalysisRequest,x_iq_session:str|None=Header(default=None),authorization:str|None=Header(default=None)):
    item=_session(x_iq_session)
    return {"ok":True,"analysis":_analyze(item["api"],x_iq_session or "",req.symbol,req.timeframe,req.strategy,authorization,req.analyze_with_ai)}
