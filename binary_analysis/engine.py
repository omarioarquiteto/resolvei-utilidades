def walkforward_asset(session_id: str, asset: str, expiry: str, count: int = 240) -> dict:
    """Mede o sinal do timeframe contra o candle seguinte sem olhar o futuro."""
    if expiry not in TIMEFRAMES or expiry == "30min":
        raise ValueError("expiry deve ser 1min, 5min ou 15min")

    cfg = TIMEFRAMES[expiry]
    candles = _drop_incomplete_candle(
        service.get_candles_smart(session_id, asset.upper().replace("=X", ""), cfg["interval"], count),
        cfg["interval"],
    )
    df = candles_to_df(candles)
    evaluated = wins = losses = 0
    for end in range(40, len(df)):
        signal = analyze_timeframe(df.iloc[:end], expiry)
        if not signal or signal["signal"] not in ("CALL", "PUT"):
            continue
        close_before = float(df["Close"].iloc[end - 1])
        close_after = float(df["Close"].iloc[end])
        won = (signal["signal"] == "CALL" and close_after > close_before) or (
            signal["signal"] == "PUT" and close_after < close_before
        )
        evaluated += 1
        wins += int(won)
        losses += int(not won)

    return {
        "asset": asset.upper().replace("=X", ""),
        "expiry": expiry,
        "sample_size": evaluated,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / evaluated * 100, 1) if evaluated else None,
        "note": "Proxy walk-forward de um timeframe; não substitui backtest da estratégia completa nem garante resultado futuro.",
    }


def get_chart_data(session_id: str, asset: str, interval: int = 300, count: int = 200) -> dict:
    """Retorna candles + EMAs + Bollinger para o gráfico."""
    candles = service.get_candles_smart(session_id, asset, interval, count)
    df = candles_to_df(candles)
    if df.empty:
        return {"candles": [], "ema10": [], "ema20": [], "bb_upper": [], "bb_lower": []}
    df = compute_indicators(df)
    return {
        "candles": [
            {"time": int(idx.timestamp()), "open": float(r["Open"]),
             "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"])}
            for idx, r in df.iterrows()
        ],
        "ema10": [{"time": int(idx.timestamp()), "value": float(r["EMA10"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA10"])],
        "ema20": [{"time": int(idx.timestamp()), "value": float(r["EMA20"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA20"])],
        "bb_upper": [{"time": int(idx.timestamp()), "value": float(r["BB_upper"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_upper"])],
        "bb_lower": [{"time": int(idx.timestamp()), "value": float(r["BB_lower"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_lower"])],
    }


def strategy_catalog() -> dict:
    """Catálogo público das estratégias disponíveis na análise binária."""
    return STRATEGIES.copy()

def _resample_ohlcv(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rule = f"{int(minutes)}min"
    out = df[["Open","High","Low","Close","Volume"]].resample(
        rule, label="right", closed="right"
    ).agg({
        "Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"
    }).dropna()
    return out


def _prepare_frames_from_1m(candles: list[dict]) -> dict[str, pd.DataFrame]:
    base = candles_to_df(candles)
    if base.empty:
        return {}
    # Somente candles M1 fechados. Timeframes maiores são derivados dos mesmos dados,
    # evitando misturar relógios de fontes diferentes.
    frames = {
        "1m": base,
        "5m": _resample_ohlcv(base, 5),
        "15m": _resample_ohlcv(base, 15),
    }
    return {k:v for k,v in frames.items() if not v.empty}


def _smart_multiframe_signal(frames: dict[str,pd.DataFrame], expiry: str) -> dict:
    trigger_key = "1m" if expiry == "1min" else "5m"
    context_keys = ("5m","15m") if expiry == "1min" else ("15m",)
    trigger = _strategy_signal(frames.get(trigger_key, pd.DataFrame()))
    contexts = [_strategy_signal(frames.get(k, pd.DataFrame())) for k in context_keys]

    result = {
        "signal":"AGUARDAR","confirmed":False,"score":0,"confidence":0,
        "reason":"Aguardando confluência entre contexto e gatilho.",
        "context_timeframes":list(context_keys),
        "trigger_timeframe":trigger_key,
    }
    if not contexts or any(x.get("signal") not in ("CALL","PUT") for x in contexts):
        result["reason"] = "Contexto de mercado sem direção limpa."
        result["proximity"] = {"label":"ANALISANDO MERCADO","percent":45.0,"score":0,"target":100}
        return {**result,"trigger":trigger,"contexts":contexts}

    dirs=[x["signal"] for x in contexts]
    context_dir=dirs[0] if all(d==dirs[0] for d in dirs) else "AGUARDAR"
    trigger_dir=trigger.get("signal")
    context_conf = min(float(x.get("confidence",0) or 0) for x in contexts)
    trigger_conf = float(trigger.get("confidence",0) or 0)

    if context_dir == "AGUARDAR":
        result["reason"]="Os timeframes de contexto estão em conflito."
    elif trigger_dir != context_dir:
        result["reason"]=f"Contexto aponta {context_dir}, mas o gatilho ainda não confirma."
    else:
        result["signal"]=context_dir
        result["confirmed"]=True
        result["confidence"]=round(min(context_conf,trigger_conf),1)
        result["score"]=int(round(result["confidence"]))
        result["reason"]=(
            f"Contexto {', '.join(context_keys)} e gatilho {trigger_key} alinhados em {context_dir}."
        )
        result["technical_score"]=result["confidence"]
        result["technical_margin"]=min(
            float(x.get("margin",0) or 0) for x in (*contexts,trigger)
        )
        result["resumo_votos"]=trigger.get("resumo_votos",{})
        result["votos"]=trigger.get("votos",[])
        result["regime"]=contexts[0].get("regime","")
        result["proximity"]={"label":"LIMIAR TÉCNICO ATINGIDO","percent":100.0,"score":100,"target":100}
        return {**result,"trigger":trigger,"contexts":contexts}

    # Barra interna de proximidade: não é probabilidade.
    combined=min(context_conf, trigger_conf)
    if context_dir != "AGUARDAR" and trigger_dir != context_dir:
        combined=max(combined, 60.0)
        label="SINAL MUITO PRÓXIMO" if combined >= 75 else "ATENÇÃO"
    else:
        label="ATENÇÃO" if combined >= 50 else "ANALISANDO MERCADO"
    result["confidence"]=round(combined,1)
    result["score"]=int(round(combined))
    result["proximity"]={"label":label,"percent":combined,"score":int(round(combined)),"target":100}
    result["resumo_votos"]=trigger.get("resumo_votos",{})
    result["votos"]=trigger.get("votos",[])
    return {**result,"trigger":trigger,"contexts":contexts}


def _historical_multiframe_accuracy(base_df: pd.DataFrame, expiry: str) -> dict:
    """Walk-forward da mesma arquitetura MTF usada no sinal ao vivo."""
    if base_df is None or len(base_df) < 300:
        return {"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}

    trigger_minutes = 1 if expiry=="1min" else 5
    trigger = _resample_ohlcv(base_df, trigger_minutes)
    context5 = _resample_ohlcv(base_df, 5)
    context15 = _resample_ohlcv(base_df, 15)
    if trigger.empty:
        return {"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}

    # Alinha os contextos somente com barras anteriores ao instante do gatilho.
    results=[]
    start=max(80, len(trigger)-ACCURACY_LOOKBACK)
    for i in range(start, len(trigger)-1):
        t=trigger.index[i]
        past_trigger=trigger.iloc[:i+1]
        c5=context5.loc[context5.index <= t]
        c15=context15.loc[context15.index <= t]
        frames={"1m":past_trigger if expiry=="1min" else pd.DataFrame(),
                "5m":c5,"15m":c15}
        if expiry=="5min":
            frames["5m"]=past_trigger
        decision=_smart_multiframe_signal(frames,expiry)
        if decision.get("signal") not in ("CALL","PUT"):
            continue
        entry=float(trigger["Close"].iloc[i])
        exit_price=float(trigger["Close"].iloc[i+1])
        won=(decision["signal"]=="CALL" and exit_price>entry) or (decision["signal"]=="PUT" and exit_price<entry)
        results.append(bool(won))
    total=len(results)
    wins=sum(results)
    return {
        "rate":round(wins/total*100,1) if total else None,
        "sample_size":total,"wins":wins,
        "ultimos":[("OK" if x else "ERRO") for x in reversed(results[-12:])],
        "label":"Walk-forward da mesma análise multi-timeframe." if total>=MIN_ACCURACY_SAMPLE else "Amostra insuficiente",
    }


def build_strategy(expiry: str, context: dict, trigger: dict | None, context_keys: tuple[str,...]) -> dict:
    # Compatibilidade com chamadas antigas.
    return _smart_multiframe_signal(context, expiry)


def analyze_asset(
    session_id: str,
    asset: str,
    strategy: str = "smart_confluence",
    force_refresh: bool = False,
    only_expiry: str | None = None,
) -> dict:
    asset=asset.upper().replace("=X","")
    strategy="smart_confluence"
    expiries=(only_expiry,) if only_expiry else ("1min","5min")
    news=news_service.get_news_risk(asset)
    market_status=service.get_market_status(session_id,asset)
    signals={}

    for expiry in expiries:
        if expiry not in TIMEFRAMES:
            raise ValueError(f"Vencimento desconhecido: {expiry}")
        key=(asset,strategy,expiry)
        now=int(time.time())
        cached=_SIGNAL_CACHE.get(key)
        if not force_refresh and cached and cached.get("expires_at",0)>now:
            signals[expiry]={**cached,"locked":True,"seconds_remaining":max(0,cached["expires_at"]-now)}
            continue

        # Uma fonte única M1 alimenta o M1, M5 e M15. Assim o relógio da análise
        # fica coerente e o histórico é comparável ao sinal ao vivo.
        raw=service.get_candles_smart(session_id,asset,60,900)
        raw=_drop_incomplete_candle(raw,60)
        base=candles_to_df(raw)
        frames=_prepare_frames_from_1m(raw)

        if base.empty or not frames.get("1m") is not None:
            decision={"signal":"AGUARDAR","confirmed":False,"score":0,"reason":"A IQ Option não retornou candles fechados.","data_ready":False}
            accuracy={"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}
        else:
            decision=_smart_multiframe_signal(frames,expiry)
            accuracy=_historical_multiframe_accuracy(base,expiry)
            decision["data_ready"]=True
            decision["candle_count"]=len(base)

        # Gate de qualidade: histórico real da mesma arquitetura.
        sample=int(accuracy.get("sample_size") or 0)
        rate=accuracy.get("rate")
        accuracy_ok=sample>=MIN_ACCURACY_SAMPLE and rate is not None and float(rate)>=70.0
        decision["historical_accuracy"]=accuracy
        decision["accuracy_gate"]=accuracy_ok
        decision["accuracy_gate_reason"]=None if accuracy_ok else (
            f"Histórico ainda não libera o sinal: {sample}/20 sinais e "
            f"{rate if rate is not None else 0:.1f}% de acerto; mínimo 20 sinais e 70%."
        )

        if news.get("blocked"):
            decision["news_blocked"]=True
            decision["news_warning"]="Evento econômico de alto impacto detectado no intervalo monitorado."
        else:
            decision["news_blocked"]=False
            decision["news_warning"]=None if news.get("available") else "Calendário econômico indisponível."

        # Só publica direção quando há confirmação técnica + histórico.
        if decision.get("signal") in ("CALL","PUT") and not accuracy_ok:
            decision["signal_before_accuracy_gate"]=decision["signal"]
            decision["signal"]="AGUARDAR"
            decision["confirmed"]=False
            decision["reason"]=decision["accuracy_gate_reason"]

        # Expiração é contada a partir da emissão do sinal, não da abertura do candle.
        interval=TIMEFRAMES[expiry]["interval"]
        entry_at=now if decision.get("signal") in ("CALL","PUT") else 0
        expires_at=(entry_at+interval) if entry_at else 0
        decision.update({
            "expiry":expiry,"entry_at":entry_at,"expires_at":expires_at,
            "locked":False,
            "seconds_to_entry":0 if entry_at else 0,
            "seconds_remaining":max(0,expires_at-now) if expires_at else 0,
            "technical_gate":bool(decision.get("confirmed")),
            "technical_gate_reason":None if decision.get("confirmed") else decision.get("reason"),
        })
        signals[expiry]=decision
        _SIGNAL_CACHE[key]=decision

    warning=news.get("warning") if not news.get("available") else None
    return {
        "asset":asset,"strategy":strategy,
        "strategy_name":STRATEGIES[strategy]["name"],
        "strategy_description":STRATEGIES[strategy]["description"],
        "signals":signals,"news":news,"warning":warning,
        "market":market_status or ("aberto" if signals else "sem_dados"),
        "market_closed":market_status=="fechado",
    }


def walkforward_asset(session_id: str, asset: str, expiry: str, count: int = 240) -> dict:
    """Mede o sinal do timeframe contra o candle seguinte sem olhar o futuro."""
    if expiry not in TIMEFRAMES or expiry == "30min":
        raise ValueError("expiry deve ser 1min, 5min ou 15min")

    cfg = TIMEFRAMES[expiry]
    candles = _drop_incomplete_candle(
        service.get_candles_smart(session_id, asset.upper().replace("=X", ""), cfg["interval"], count),
        cfg["interval"],
    )
    df = candles_to_df(candles)
    evaluated = wins = losses = 0
    for end in range(40, len(df)):
        signal = analyze_timeframe(df.iloc[:end], expiry)
        if not signal or signal["signal"] not in ("CALL", "PUT"):
            continue
        close_before = float(df["Close"].iloc[end - 1])
        close_after = float(df["Close"].iloc[end])
        won = (signal["signal"] == "CALL" and close_after > close_before) or (
            signal["signal"] == "PUT" and close_after < close_before
        )
        evaluated += 1
        wins += int(won)
        losses += int(not won)

    return {
        "asset": asset.upper().replace("=X", ""),
        "expiry": expiry,
        "sample_size": evaluated,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / evaluated * 100, 1) if evaluated else None,
        "note": "Proxy walk-forward de um timeframe; não substitui backtest da estratégia completa nem garante resultado futuro.",
    }


def get_chart_data(session_id: str, asset: str, interval: int = 300, count: int = 200) -> dict:
    """Retorna candles + EMAs + Bollinger para o gráfico."""
    candles = service.get_candles_smart(session_id, asset, interval, count)
    df = candles_to_df(candles)
    if df.empty:
        return {"candles": [], "ema10": [], "ema20": [], "bb_upper": [], "bb_lower": []}
    df = compute_indicators(df)
    return {
        "candles": [
            {"time": int(idx.timestamp()), "open": float(r["Open"]),
             "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"])}
            for idx, r in df.iterrows()
        ],
        "ema10": [{"time": int(idx.timestamp()), "value": float(r["EMA10"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA10"])],
        "ema20": [{"time": int(idx.timestamp()), "value": float(r["EMA20"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA20"])],
        "bb_upper": [{"time": int(idx.timestamp()), "value": float(r["BB_upper"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_upper"])],
        "bb_lower": [{"time": int(idx.timestamp()), "value": float(r["BB_lower"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_lower"])],
    }


def strategy_catalog() -> dict:
    """Catálogo público das estratégias disponíveis na análise binária."""
    return STRATEGIES.copy()

def walkforward_asset(session_id: str, asset: str, expiry: str, count: int = 900) -> dict:
    if expiry not in ("1min","5min"):
        raise ValueError("expiry deve ser 1min ou 5min")
    raw=service.get_candles_smart(session_id,asset.upper().replace("=X",""),60,max(900,int(count)))
    raw=_drop_incomplete_candle(raw,60)
    base=candles_to_df(raw)
    acc=_historical_multiframe_accuracy(base,expiry)
    return {
        "asset":asset.upper().replace("=X",""),
        "expiry":expiry,
        "sample_size":int(acc.get("sample_size") or 0),
        "wins":int(acc.get("wins") or 0),
        "losses":int(acc.get("sample_size") or 0)-int(acc.get("wins") or 0),
        "win_rate":acc.get("rate"),
        "note":"Walk-forward da mesma arquitetura multi-timeframe usada no sinal.",
    }


def get_chart_data(session_id: str, asset: str, interval: int = 300, count: int = 200) -> dict:
    """Retorna candles + EMAs + Bollinger para o gráfico."""
    candles = service.get_candles_smart(session_id, asset, interval, count)
    df = candles_to_df(candles)
    if df.empty:
        return {"candles": [], "ema10": [], "ema20": [], "bb_upper": [], "bb_lower": []}
    df = compute_indicators(df)
    return {
        "candles": [
            {"time": int(idx.timestamp()), "open": float(r["Open"]),
             "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"])}
            for idx, r in df.iterrows()
        ],
        "ema10": [{"time": int(idx.timestamp()), "value": float(r["EMA10"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA10"])],
        "ema20": [{"time": int(idx.timestamp()), "value": float(r["EMA20"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA20"])],
        "bb_upper": [{"time": int(idx.timestamp()), "value": float(r["BB_upper"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_upper"])],
        "bb_lower": [{"time": int(idx.timestamp()), "value": float(r["BB_lower"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_lower"])],
    }


def strategy_catalog() -> dict:
    """Catálogo público das estratégias disponíveis na análise binária."""
    return STRATEGIES.copy()

def _resample_ohlcv(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rule = f"{int(minutes)}min"
    out = df[["Open","High","Low","Close","Volume"]].resample(
        rule, label="right", closed="right"
    ).agg({
        "Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"
    }).dropna()
    return out


def _prepare_frames_from_1m(candles: list[dict]) -> dict[str, pd.DataFrame]:
    base = candles_to_df(candles)
    if base.empty:
        return {}
    # Somente candles M1 fechados. Timeframes maiores são derivados dos mesmos dados,
    # evitando misturar relógios de fontes diferentes.
    frames = {
        "1m": base,
        "5m": _resample_ohlcv(base, 5),
        "15m": _resample_ohlcv(base, 15),
    }
    return {k:v for k,v in frames.items() if not v.empty}


def _smart_multiframe_signal(frames: dict[str,pd.DataFrame], expiry: str) -> dict:
    trigger_key = "1m" if expiry == "1min" else "5m"
    context_keys = ("5m","15m") if expiry == "1min" else ("15m",)
    trigger = _strategy_signal(frames.get(trigger_key, pd.DataFrame()))
    contexts = [_strategy_signal(frames.get(k, pd.DataFrame())) for k in context_keys]

    result = {
        "signal":"AGUARDAR","confirmed":False,"score":0,"confidence":0,
        "reason":"Aguardando confluência entre contexto e gatilho.",
        "context_timeframes":list(context_keys),
        "trigger_timeframe":trigger_key,
    }
    if not contexts or any(x.get("signal") not in ("CALL","PUT") for x in contexts):
        result["reason"] = "Contexto de mercado sem direção limpa."
        result["proximity"] = {"label":"ANALISANDO MERCADO","percent":45.0,"score":0,"target":100}
        return {**result,"trigger":trigger,"contexts":contexts}

    dirs=[x["signal"] for x in contexts]
    context_dir=dirs[0] if all(d==dirs[0] for d in dirs) else "AGUARDAR"
    trigger_dir=trigger.get("signal")
    context_conf = min(float(x.get("confidence",0) or 0) for x in contexts)
    trigger_conf = float(trigger.get("confidence",0) or 0)

    if context_dir == "AGUARDAR":
        result["reason"]="Os timeframes de contexto estão em conflito."
    elif trigger_dir != context_dir:
        result["reason"]=f"Contexto aponta {context_dir}, mas o gatilho ainda não confirma."
    else:
        result["signal"]=context_dir
        result["confirmed"]=True
        result["confidence"]=round(min(context_conf,trigger_conf),1)
        result["score"]=int(round(result["confidence"]))
        result["reason"]=(
            f"Contexto {', '.join(context_keys)} e gatilho {trigger_key} alinhados em {context_dir}."
        )
        result["technical_score"]=result["confidence"]
        result["technical_margin"]=min(
            float(x.get("margin",0) or 0) for x in (*contexts,trigger)
        )
        result["resumo_votos"]=trigger.get("resumo_votos",{})
        result["votos"]=trigger.get("votos",[])
        result["regime"]=contexts[0].get("regime","")
        result["proximity"]={"label":"LIMIAR TÉCNICO ATINGIDO","percent":100.0,"score":100,"target":100}
        return {**result,"trigger":trigger,"contexts":contexts}

    # Barra interna de proximidade: não é probabilidade.
    combined=min(context_conf, trigger_conf)
    if context_dir != "AGUARDAR" and trigger_dir != context_dir:
        combined=max(combined, 60.0)
        label="SINAL MUITO PRÓXIMO" if combined >= 75 else "ATENÇÃO"
    else:
        label="ATENÇÃO" if combined >= 50 else "ANALISANDO MERCADO"
    result["confidence"]=round(combined,1)
    result["score"]=int(round(combined))
    result["proximity"]={"label":label,"percent":combined,"score":int(round(combined)),"target":100}
    result["resumo_votos"]=trigger.get("resumo_votos",{})
    result["votos"]=trigger.get("votos",[])
    return {**result,"trigger":trigger,"contexts":contexts}


def _historical_multiframe_accuracy(base_df: pd.DataFrame, expiry: str) -> dict:
    """Walk-forward da mesma arquitetura MTF usada no sinal ao vivo."""
    if base_df is None or len(base_df) < 300:
        return {"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}

    trigger_minutes = 1 if expiry=="1min" else 5
    trigger = _resample_ohlcv(base_df, trigger_minutes)
    context5 = _resample_ohlcv(base_df, 5)
    context15 = _resample_ohlcv(base_df, 15)
    if trigger.empty:
        return {"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}

    # Alinha os contextos somente com barras anteriores ao instante do gatilho.
    results=[]
    start=max(80, len(trigger)-ACCURACY_LOOKBACK)
    for i in range(start, len(trigger)-1):
        t=trigger.index[i]
        past_trigger=trigger.iloc[:i+1]
        c5=context5.loc[context5.index <= t]
        c15=context15.loc[context15.index <= t]
        frames={"1m":past_trigger if expiry=="1min" else pd.DataFrame(),
                "5m":c5,"15m":c15}
        if expiry=="5min":
            frames["5m"]=past_trigger
        decision=_smart_multiframe_signal(frames,expiry)
        if decision.get("signal") not in ("CALL","PUT"):
            continue
        entry=float(trigger["Close"].iloc[i])
        exit_price=float(trigger["Close"].iloc[i+1])
        won=(decision["signal"]=="CALL" and exit_price>entry) or (decision["signal"]=="PUT" and exit_price<entry)
        results.append(bool(won))
    total=len(results)
    wins=sum(results)
    return {
        "rate":round(wins/total*100,1) if total else None,
        "sample_size":total,"wins":wins,
        "ultimos":[("OK" if x else "ERRO") for x in reversed(results[-12:])],
        "label":"Walk-forward da mesma análise multi-timeframe." if total>=MIN_ACCURACY_SAMPLE else "Amostra insuficiente",
    }


def build_strategy(expiry: str, context: dict, trigger: dict | None, context_keys: tuple[str,...]) -> dict:
    # Compatibilidade com chamadas antigas.
    return _smart_multiframe_signal(context, expiry)


def analyze_asset(
    session_id: str,
    asset: str,
    strategy: str = "smart_confluence",
    force_refresh: bool = False,
    only_expiry: str | None = None,
) -> dict:
    asset=asset.upper().replace("=X","")
    strategy="smart_confluence"
    expiries=(only_expiry,) if only_expiry else ("1min","5min")
    news=news_service.get_news_risk(asset)
    market_status=service.get_market_status(session_id,asset)
    signals={}

    for expiry in expiries:
        if expiry not in TIMEFRAMES:
            raise ValueError(f"Vencimento desconhecido: {expiry}")
        key=(asset,strategy,expiry)
        now=int(time.time())
        cached=_SIGNAL_CACHE.get(key)
        if not force_refresh and cached and cached.get("expires_at",0)>now:
            signals[expiry]={**cached,"locked":True,"seconds_remaining":max(0,cached["expires_at"]-now)}
            continue

        # Uma fonte única M1 alimenta o M1, M5 e M15. Assim o relógio da análise
        # fica coerente e o histórico é comparável ao sinal ao vivo.
        raw=service.get_candles_smart(session_id,asset,60,900)
        raw=_drop_incomplete_candle(raw,60)
        base=candles_to_df(raw)
        frames=_prepare_frames_from_1m(raw)

        if base.empty or not frames.get("1m") is not None:
            decision={"signal":"AGUARDAR","confirmed":False,"score":0,"reason":"A IQ Option não retornou candles fechados.","data_ready":False}
            accuracy={"rate":None,"sample_size":0,"wins":0,"ultimos":[],"label":"Amostra insuficiente"}
        else:
            decision=_smart_multiframe_signal(frames,expiry)
            accuracy=_historical_multiframe_accuracy(base,expiry)
            decision["data_ready"]=True
            decision["candle_count"]=len(base)

        # Gate de qualidade: histórico real da mesma arquitetura.
        sample=int(accuracy.get("sample_size") or 0)
        rate=accuracy.get("rate")
        accuracy_ok=sample>=MIN_ACCURACY_SAMPLE and rate is not None and float(rate)>=70.0
        decision["historical_accuracy"]=accuracy
        decision["accuracy_gate"]=accuracy_ok
        decision["accuracy_gate_reason"]=None if accuracy_ok else (
            f"Histórico ainda não libera o sinal: {sample}/20 sinais e "
            f"{rate if rate is not None else 0:.1f}% de acerto; mínimo 20 sinais e 70%."
        )

        if news.get("blocked"):
            decision["news_blocked"]=True
            decision["news_warning"]="Evento econômico de alto impacto detectado no intervalo monitorado."
        else:
            decision["news_blocked"]=False
            decision["news_warning"]=None if news.get("available") else "Calendário econômico indisponível."

        # Só publica direção quando há confirmação técnica + histórico.
        if decision.get("signal") in ("CALL","PUT") and not accuracy_ok:
            decision["signal_before_accuracy_gate"]=decision["signal"]
            decision["signal"]="AGUARDAR"
            decision["confirmed"]=False
            decision["reason"]=decision["accuracy_gate_reason"]

        # Expiração é contada a partir da emissão do sinal, não da abertura do candle.
        interval=TIMEFRAMES[expiry]["interval"]
        entry_at=now if decision.get("signal") in ("CALL","PUT") else 0
        expires_at=(entry_at+interval) if entry_at else 0
        decision.update({
            "expiry":expiry,"entry_at":entry_at,"expires_at":expires_at,
            "locked":False,
            "seconds_to_entry":0 if entry_at else 0,
            "seconds_remaining":max(0,expires_at-now) if expires_at else 0,
            "technical_gate":bool(decision.get("confirmed")),
            "technical_gate_reason":None if decision.get("confirmed") else decision.get("reason"),
        })
        signals[expiry]=decision
        _SIGNAL_CACHE[key]=decision

    warning=news.get("warning") if not news.get("available") else None
    return {
        "asset":asset,"strategy":strategy,
        "strategy_name":STRATEGIES[strategy]["name"],
        "strategy_description":STRATEGIES[strategy]["description"],
        "signals":signals,"news":news,"warning":warning,
        "market":market_status or ("aberto" if signals else "sem_dados"),
        "market_closed":market_status=="fechado",
    }


def walkforward_asset(session_id: str, asset: str, expiry: str, count: int = 240) -> dict:
    """Mede o sinal do timeframe contra o candle seguinte sem olhar o futuro."""
    if expiry not in TIMEFRAMES or expiry == "30min":
        raise ValueError("expiry deve ser 1min, 5min ou 15min")

    cfg = TIMEFRAMES[expiry]
    candles = _drop_incomplete_candle(
        service.get_candles_smart(session_id, asset.upper().replace("=X", ""), cfg["interval"], count),
        cfg["interval"],
    )
    df = candles_to_df(candles)
    evaluated = wins = losses = 0
    for end in range(40, len(df)):
        signal = analyze_timeframe(df.iloc[:end], expiry)
        if not signal or signal["signal"] not in ("CALL", "PUT"):
            continue
        close_before = float(df["Close"].iloc[end - 1])
        close_after = float(df["Close"].iloc[end])
        won = (signal["signal"] == "CALL" and close_after > close_before) or (
            signal["signal"] == "PUT" and close_after < close_before
        )
        evaluated += 1
        wins += int(won)
        losses += int(not won)

    return {
        "asset": asset.upper().replace("=X", ""),
        "expiry": expiry,
        "sample_size": evaluated,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / evaluated * 100, 1) if evaluated else None,
        "note": "Proxy walk-forward de um timeframe; não substitui backtest da estratégia completa nem garante resultado futuro.",
    }


def get_chart_data(session_id: str, asset: str, interval: int = 300, count: int = 200) -> dict:
    """Retorna candles + EMAs + Bollinger para o gráfico."""
    candles = service.get_candles_smart(session_id, asset, interval, count)
    df = candles_to_df(candles)
    if df.empty:
        return {"candles": [], "ema10": [], "ema20": [], "bb_upper": [], "bb_lower": []}
    df = compute_indicators(df)
    return {
        "candles": [
            {"time": int(idx.timestamp()), "open": float(r["Open"]),
             "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"])}
            for idx, r in df.iterrows()
        ],
        "ema10": [{"time": int(idx.timestamp()), "value": float(r["EMA10"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA10"])],
        "ema20": [{"time": int(idx.timestamp()), "value": float(r["EMA20"])}
                  for idx, r in df.iterrows() if not pd.isna(r["EMA20"])],
        "bb_upper": [{"time": int(idx.timestamp()), "value": float(r["BB_upper"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_upper"])],
        "bb_lower": [{"time": int(idx.timestamp()), "value": float(r["BB_lower"])}
                     for idx, r in df.iterrows() if not pd.isna(r["BB_lower"])],
    }


def strategy_catalog() -> dict:
    """Catálogo público das estratégias disponíveis na análise binária."""
    return STRATEGIES.copy()
