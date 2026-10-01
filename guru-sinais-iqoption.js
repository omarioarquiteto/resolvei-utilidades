(() => {
  const TOOL_ID = "guru-dos-sinais-iqoption";
  const API = "/api/guru-sinais-iqoption";
  const SESSION_KEY = "resolvei_iqoption_session";
  const candlePeriods = [["1m","1 minuto"],["5m","5 minutos"],["15m","15 minutos"],["30m","30 minutos"],["1h","1 hora"]];
  const optionTypes = [["binary","Binárias"],["digital","Digitais"],["blitz","Blitz"]];
  const expiryOptions = {binary:[[1,"1 minuto"],[5,"5 minutos"],[15,"15 minutos"]],digital:[[1,"1 minuto"],[5,"5 minutos"],[15,"15 minutos"]],blitz:[[30,"30 segundos"],[60,"60 segundos"]]};
  const strategies = [["automatica","🤖 Automática — escolhe 1"],["tendencia","📈 Tendência"],["reversao","↩️ Reversão"],["rompimento","🚀 Rompimento"],["momentum","⚡ Momentum"]];
  const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));

  function card() {
    return `<article class="card tool-card guru-tool-card"><a href="#/ferramenta/${TOOL_ID}">
      <div class="tool-icon">🧙‍♂️</div><h3>GURÚ DOS SINAIS IQOPTION</h3>
      <p>Analise técnica automática usando os dados da IQ Option, incluindo OTC.</p>
    </a></article>`;
  }

  function breadcrumbWrap(body){return `<div class="tool-page"><div class="breadcrumb"><a href="#/">Início</a> / GURÚ DOS SINAIS IQOPTION</div>${body}</div>`;}

  function loginShell(message=""){
    return `<div class="guru-simple guru-iq-shell">
      <section class="guru-simple-head"><span class="eyebrow">IQ OPTION · DADOS DIRETOS</span>
        <h1>🧙‍♂️ GURÚ DOS SINAIS IQOPTION</h1>
        <p>Faça login para consultar os ativos e candles diretamente pela conexão da IQ Option.</p>
      </section>
      <section class="card guru-control-card iq-login-card">
        <div class="iq-login-icon">🔐</div><h2>Entrar na IQ Option</h2>
        <p class="iq-login-note">Suas credenciais são usadas somente para abrir uma sessão temporária com a IQ Option. A sessão não é persistida no banco de dados do Resolvei.</p>
        <div class="form-grid">
          <div class="field full"><label for="iqEmail">E-mail da IQ Option</label><input id="iqEmail" type="email" autocomplete="username" placeholder="seu@email.com"></div>
          <div class="field full"><label for="iqPassword">Senha</label><input id="iqPassword" type="password" autocomplete="current-password" placeholder="Sua senha da IQ Option"></div>
        </div>
        <div class="actions"><button class="btn primary full" id="iqLoginBtn">🔗 CONECTAR À IQ OPTION</button></div>
        <div id="iqLoginMessage" class="notice" ${message ? "" : "hidden"}>${esc(message)}</div>
        <div class="iq-security-note">🔒 A senha não é exibida de volta na tela e não é enviada ao Gemini.</div>
      </section>
      <section class="guru-foot-note"><span>Ferramenta de estudo. A integração usa uma API comunitária não oficial da IQ Option e o Resolvei não executa operações.</span></section>
    </div>`;
  }

  function twoFAShell(){
    return `<div class="guru-simple guru-iq-shell">
      <section class="guru-simple-head"><span class="eyebrow">IQ OPTION · AUTENTICAÇÃO</span>
        <h1>🔐 Verificação adicional</h1><p>A IQ Option solicitou um código de autenticação para concluir a conexão.</p>
      </section>
      <section class="card guru-control-card iq-login-card">
        <div class="form-grid"><div class="field full"><label for="iq2faCode">Código de verificação</label><input id="iq2faCode" inputmode="numeric" autocomplete="one-time-code" placeholder="Digite o código recebido"></div></div>
        <div class="actions"><button class="btn primary full" id="iq2faBtn">✅ VALIDAR CÓDIGO</button><button class="btn ghost full" id="iq2faBack">Voltar para o login</button></div>
        <div id="iqLoginMessage" class="notice" hidden></div>
      </section>
    </div>`;
  }

  function readableAsset(asset){
    const s=String(asset||"").toUpperCase(), otc=s.endsWith("-OTC"), base=s.replace(/-OTC$/,"");
    const pair=/^[A-Z]{6}$/.test(base)?base.slice(0,3)+"/"+base.slice(3):base;
    return otc ? pair+" · OTC" : pair;
  }

  function assetOptions(data){
    const normal=Array.isArray(data?.normal)?data.normal:[], otc=Array.isArray(data?.otc)?data.otc:[];
    const make=a=>`<option value="${esc(a.symbol)}">${esc(readableAsset(a.symbol))}</option>`;
    const chunks=[];
    if(otc.length) chunks.push(`<optgroup label="OTC — disponíveis agora">${otc.map(make).join("")}</optgroup>`);
    if(normal.length) chunks.push(`<optgroup label="Mercado normal — disponíveis agora">${normal.map(make).join("")}</optgroup>`);
    return chunks.join("") || '<option value="">Nenhum ativo aberto encontrado</option>';
  }

  function shell(assets){
    const hasAssets=(assets?.normal?.length||0)+(assets?.otc?.length||0)>0;
    return `<div class="guru-simple">
      <section class="guru-simple-head"><span class="eyebrow">IQ OPTION · DADOS DIRETOS</span>
        <h1>🧙‍♂️ GURÚ DOS SINAIS IQOPTION</h1>
        <p>Motor técnico exclusivo do IQOPTION: período da vela, tempo de expiração e tipo de opção são analisados separadamente.</p>
      </section>
      <section class="card guru-control-card">
        <div class="iq-connected-bar"><span><strong>● CONECTADO À IQ OPTION</strong><small>${hasAssets?"Ativos de opções disponíveis agora.":"Nenhum ativo de opções está aberto agora."}</small></span>
          <button class="btn ghost small" id="iqRefreshAssets">↻ Atualizar ativos</button><button class="btn ghost small" id="iqLogout">Sair</button>
        </div>
        <div class="guru-control-grid guru-control-grid-4">
          <div class="field"><label for="guruIqOptionType">Tipo de opção</label><select id="guruIqOptionType">${optionTypes.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}</select></div>
          <div class="field"><label for="guruIqPair">Par de moedas</label><select id="guruIqPair">${assetOptions(assets)}</select></div>
          <div class="field"><label for="guruIqCandlePeriod">Período da vela</label><select id="guruIqCandlePeriod">${candlePeriods.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}</select></div>
          <div class="field"><label for="guruIqExpiry">Tempo de expiração</label><select id="guruIqExpiry"></select></div>
        </div>
        <div class="guru-control-grid guru-control-grid-2">
          <div class="field"><label for="guruIqStrategy">Estratégia</label><select id="guruIqStrategy">${strategies.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}</select></div>
          <label class="guru-ai-toggle"><input type="checkbox" id="guruIqAnalyzeWithAI"><span>Analisar com I.A.</span><small>Valida somente a estratégia selecionada.</small></label>
        </div>
        <div id="guruIqOptionHint" class="guru-option-hint"></div>
        <button class="guru-analyze-btn" id="guruIqAnalyzeBtn" ${hasAssets?"":"disabled"}>🔍 ANALISAR MERCADO</button>
        <div id="guruIqMessage" class="notice" hidden></div>
      </section>
      <section id="guruIqResult"><div class="card guru-empty"><div class="guru-empty-icon">📊</div><strong>Pronto para analisar</strong><span>Escolha separadamente o tipo da opção, o período das velas e o vencimento.</span></div></section>
      <section class="guru-foot-note"><span>Ferramenta de estudo. A API comunitária da IQ Option é não oficial; o Resolvei não executa operações e os indicadores não garantem resultados futuros.</span></section>
    </div>`;
  }

  function syncOptionControls(){
    const type=document.getElementById("guruIqOptionType")?.value||"binary";
    const expiry=document.getElementById("guruIqExpiry");
    const hint=document.getElementById("guruIqOptionHint");
    const current=expiry?.value||"";
    if(expiry){
      expiry.innerHTML=(expiryOptions[type]||expiryOptions.binary).map(([v,t])=>`<option value="${v}">${t}</option>`).join("");
      if([...expiry.options].some(o=>o.value===current))expiry.value=current;
    }
    if(hint){
      hint.textContent=type==="digital"
        ?"Digital: a direção é analisada separadamente, mas o strike/preço de exercício da plataforma não é recebido pela API comunitária."
        :type==="blitz"
          ?"Blitz: expiração curta e confirmação em tempo real; o backtest histórico de segundos fica desativado com dados de candles de 1 minuto."
          :"Binárias: o foco é a direção no momento do vencimento.";
    }
  }


  function classFor(signal) {
    return signal === "CALL" ? "guru-call" : signal === "PUT" ? "guru-put" : "guru-wait";
  }

  function resultHtml(a){
    const score=Math.max(0,Math.min(100,Number(a.score||0)));
    const signal=a.signal||"AGUARDAR";
    const isCall=signal==="CALL", isPut=signal==="PUT";
    const signalClass=isCall?"guru-call":isPut?"guru-put":"guru-wait";
    const optionLabel=a.optionLabel||(a.optionType==="digital"?"Digitais":a.optionType==="blitz"?"Blitz":"Binárias");
    const candleLabel={"1m":"1 min","5m":"5 min","15m":"15 min","30m":"30 min","1h":"1 h","4h":"4 h"}[a.candlePeriod||a.timeframe]||(a.candlePeriod||a.timeframe||"—");
    const expiryLabel=a.optionType==="blitz"?\`\${Number(a.expiryMinutes||0)} s\`:\`\${Number(a.expiryMinutes||0)} min\`;
    const strategy=(a.strategyLabel||a.strategy||"—");
    const trigger=a.entry?.triggerTimeframe||a.analysisTimeframes?.trigger||"1m";
    const triggerLabel={"1m":"1 min","5m":"5 min","15m":"15 min","30m":"30 min","1h":"1 h"}[trigger]||trigger;
    const entryReady=!!a.entry?.ready;
    const entryStatus=entryReady?"ENTRADA CONFIRMADA":(a.entry?.status||"ANALISANDO");
    const reasons=(a.reasons||[]).slice(0,3).map(x=>\`<li>✓ \${esc(x)}</li>\`).join("");
    const warnings=(a.warnings||[]).slice(0,3).map(x=>\`<li>⚠ \${esc(x)}</li>\`).join("");
    const back=a.backtest||{};
    const tested=Number(back.testedSignals||0);
    const hit=Number(back.hitRate||0);
    const mtf=a.mtf||{};
    return \`
      <div class="guru-dashboard">
        <section class="guru-signal-card card">
          <div class="guru-signal-head">
            <div>
              <span class="eyebrow">\${esc(readableAsset(a.symbol))} · \${esc(strategy)}</span>
              <span class="guru-signal-kicker">DIREÇÃO ANALISADA</span>
            </div>
            <div class="guru-price">\${a.price!=null?esc(Number(a.price).toFixed(5)):"—"}</div>
          </div>
          <div class="guru-signal-core \${signalClass}">
            <span class="guru-signal-label">\${esc(signal)}</span>
            <span class="guru-signal-quality">\${esc(a.quality||"LEITURA TÉCNICA")}</span>
          </div>
          <div class="guru-entry-compact \${entryReady?"ready":""}">
            <div><span class="guru-entry-title">MOMENTO</span><strong>\${esc(entryStatus)}</strong></div>
            <div class="guru-entry-direction">\${isCall?"CALL":isPut?"PUT":"—"}</div>
            <div class="guru-entry-countdown">\${Number(a.entry?.secondsRemaining||0)}s</div>
          </div>
          <div class="guru-score-compact">
            <div><span>CONFLUÊNCIA</span><strong>\${score}%</strong></div>
            <div class="guru-meter"><span style="width:\${score}%"></span></div>
          </div>
          <div class="guru-action-row">
            <button class="btn primary" id="guruNewAnalysis">↻ NOVA ANÁLISE</button>
            <span>\${entryReady?"Confirmação encontrada no gatilho em tempo real.":"O Guru continua monitorando e atualiza o resultado automaticamente."}</span>
          </div>
        </section>

        <aside class="guru-side-stack">
          <section class="guru-config-summary card">
            <div class="guru-panel-title"><strong>SUA CONFIGURAÇÃO</strong><span>IQOPTION</span></div>
            <div class="guru-summary-grid">
              <div><span>OPÇÃO</span><strong>\${esc(optionLabel)}</strong></div>
              <div><span>VELA</span><strong>\${esc(candleLabel)}</strong></div>
              <div><span>EXPIRAÇÃO</span><strong>\${esc(expiryLabel)}</strong></div>
              <div><span>ESTRATÉGIA</span><strong>\${esc(strategy)}</strong></div>
            </div>
            <div class="guru-trigger-line"><span>Gatilho atual</span><strong>\${esc(triggerLabel)}</strong></div>
          </section>

          <section class="guru-evidence-card card">
            <div class="guru-panel-title"><strong>POR QUE ESTE SINAL?</strong><span>\${score}%</span></div>
            <ul class="guru-reason-list">\${reasons||"<li>Leitura técnica em atualização.</li>"}</ul>
            \${warnings?\`<div class="guru-warning-mini">\${warnings}</div>\`:""}
          </section>

          <details class="guru-details-card card">
            <summary>Ver desempenho histórico</summary>
            <div class="guru-mini-history">
              \${back.available===false
                ? \`<div class="guru-history-note">\${esc(back.instrumentModel||"Backtest específico indisponível para esta configuração.")}</div>\`
                : \`<div><span>Sinais</span><strong>\${tested}</strong></div><div><span>Acertos</span><strong>\${Number(back.wins||0)}</strong></div><div><span>Erros</span><strong>\${Number(back.losses||0)}</strong></div><div><span>Taxa</span><strong>\${hit.toFixed(1)}%</strong></div>\`}
            </div>
          </details>

          <details class="guru-details-card card">
            <summary>Ver contexto técnico</summary>
            <div class="guru-mtf-compact">
              <div><span>CONTEXTO</span><strong>\${esc(mtf.context?.timeframe||"—")}</strong><em>\${esc(mtf.context?.direction||"—")}</em></div>
              <div><span>SETUP</span><strong>\${esc(mtf.setup?.timeframe||"—")}</strong><em>\${esc(mtf.setup?.direction||"—")}</em></div>
              <div><span>GATILHO</span><strong>\${esc(mtf.trigger?.timeframe||"—")}</strong><em>\${esc(mtf.trigger?.direction||"—")}</em></div>
            </div>
          </details>
          <div class="guru-disclaimer-mini">Estudo técnico. Não há garantia de resultado futuro. O Resolvei não executa operações.</div>
        </aside>
      </div>\`;
  }


  async function iqFetch(path,options={}){
    const session=sessionStorage.getItem(SESSION_KEY)||"";
    const headers={"Content-Type":"application/json",...(options.headers||{})};
    if(session) headers["X-IQ-Session"]=session;
    try{
      if(typeof resolveiUser!=="undefined"&&resolveiUser&&typeof resolveiUser.getIdToken==="function"){
        const token=await resolveiUser.getIdToken();
        if(typeof token==="string"&&/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token)) headers.Authorization="Bearer "+token;
      }
    }catch(_){}
    return fetch(new URL(API+path,window.location.origin).toString(),{...options,headers});
  }

  async function jsonResponse(r){
    const ct=r.headers.get("content-type")||"";
    const data=ct.includes("application/json")?await r.json():{detail:await r.text()};
    if(!r.ok) throw new Error(data.detail||"Não foi possível concluir a solicitação.");
    return data;
  }

  function iqMount(){return document.getElementById("guruIqToolHost")||document.getElementById("app");}

  function renderLogin(message=""){
    const app=iqMount(); if(!app)return;
    app.innerHTML=breadcrumbWrap(loginShell(message));
    document.getElementById("iqLoginBtn")?.addEventListener("click",login);
  }

  async function login(){
    const email=document.getElementById("iqEmail")?.value.trim(), password=document.getElementById("iqPassword")?.value||"";
    const btn=document.getElementById("iqLoginBtn"), msg=document.getElementById("iqLoginMessage");
    if(!email||!password){if(msg){msg.hidden=false;msg.textContent="Informe e-mail e senha.";}return;}
    btn.disabled=true;btn.textContent="⏳ CONECTANDO…";if(msg){msg.hidden=true;msg.textContent="";}
    try{
      const r=await fetch(new URL(API+"/login",window.location.origin).toString(),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
      const d=await jsonResponse(r);
      sessionStorage.setItem(SESSION_KEY,d.session_id);
      if(d.requires_2fa){
        const app=iqMount();if(app){app.innerHTML=breadcrumbWrap(twoFAShell());bindTwoFA();}return;
      }
      await renderConnected();
    }catch(e){if(msg){msg.hidden=false;msg.textContent="⚠️ "+e.message;}}
    finally{const b=document.getElementById("iqLoginBtn");if(b){b.disabled=false;b.textContent="🔗 CONECTAR À IQ OPTION";}}
  }

  function bindTwoFA(){
    document.getElementById("iq2faBtn")?.addEventListener("click",submit2FA);
    document.getElementById("iq2faBack")?.addEventListener("click",async()=>{await logout(false);renderLogin();});
  }

  async function submit2FA(){
    const code=document.getElementById("iq2faCode")?.value.trim(),btn=document.getElementById("iq2faBtn"),msg=document.getElementById("iqLoginMessage");
    if(!/^\d{4,10}$/.test(code||"")){if(msg){msg.hidden=false;msg.textContent="Digite um código de verificação válido.";}return;}
    btn.disabled=true;btn.textContent="⏳ VALIDANDO…";
    try{const d=await jsonResponse(await iqFetch("/2fa",{method:"POST",body:JSON.stringify({code})}));sessionStorage.setItem(SESSION_KEY,d.session_id);await renderConnected();}
    catch(e){if(msg){msg.hidden=false;msg.textContent="⚠️ "+e.message;}}
    finally{const b=document.getElementById("iq2faBtn");if(b){b.disabled=false;b.textContent="✅ VALIDAR CÓDIGO";}}
  }

  async function loadAssets(){return jsonResponse(await iqFetch("/assets"));}

  async function renderConnected(){
    const app=iqMount();if(!app)return;
    try{await jsonResponse(await iqFetch("/session"));const assets=await loadAssets();app.innerHTML=breadcrumbWrap(shell(assets));bindConnected();}
    catch(e){sessionStorage.removeItem(SESSION_KEY);renderLogin(e.message);}
  }

  async function refreshAssets(){
    const btn=document.getElementById("iqRefreshAssets"),msg=document.getElementById("guruIqMessage");
    if(btn){btn.disabled=true;btn.textContent="⏳ Atualizando…";}
    try{
      const assets=await loadAssets(),select=document.getElementById("guruIqPair"),current=select?.value;
      if(select){select.innerHTML=assetOptions(assets);if([...select.options].some(o=>o.value===current))select.value=current;}
      const hasAssets=(assets?.normal?.length||0)+(assets?.otc?.length||0)>0,analyzeBtn=document.getElementById("guruIqAnalyzeBtn");
      if(analyzeBtn)analyzeBtn.disabled=!hasAssets;
      if(msg){msg.hidden=false;msg.textContent=hasAssets?"Ativos atualizados diretamente da IQ Option.":"Nenhum ativo de opções está aberto neste momento.";}
    }catch(e){if(msg){msg.hidden=false;msg.textContent="⚠️ "+e.message;}}
    finally{if(btn){btn.disabled=false;btn.textContent="↻ Atualizar ativos";}}
  }

  async function logout(showLogin=true){
    try{await iqFetch("/logout",{method:"POST"});}catch(_){}
    sessionStorage.removeItem(SESSION_KEY);
    if(showLogin)renderLogin();
  }

  function bindConnected(){
    document.getElementById("guruIqAnalyzeBtn")?.addEventListener("click",analyze);
    document.getElementById("iqRefreshAssets")?.addEventListener("click",refreshAssets);
    document.getElementById("iqLogout")?.addEventListener("click",()=>logout(true));
    document.getElementById("guruIqOptionType")?.addEventListener("change",syncOptionControls);
    syncOptionControls();
  }

  let monitorRunId=0;
  let monitoring=false;

  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  function setMonitoringUI(active){
    const btn=document.getElementById("guruIqAnalyzeBtn");
    const controls=["guruIqPair","guruIqOptionType","guruIqCandlePeriod","guruIqExpiry","guruIqStrategy","guruIqAnalyzeWithAI"]
      .map(id=>document.getElementById(id)).filter(Boolean);
    controls.forEach(el=>{el.disabled=active;});
    if(btn){
      btn.disabled=active;
      btn.textContent=active?"⏳ MONITORANDO MERCADO…":"🔍 ANALISAR NOVAMENTE";
      btn.classList.toggle("guru-monitoring-active",active);
    }
  }

  function monitorStatusHtml(symbol,label,detail=""){
    const stage={"BUSCANDO SINAL":"1/4","CALCULANDO MERCADO":"2/4","TESTANDO SINAIS":"3/4","ATENÇÃO":"4/4","SINAL PRÓXIMO":"4/4","FAÇA A ENTRADA AGORA":"4/4"}[label]||"1/4";
    return \`<div class="guru-monitor-compact card">
      <div class="guru-monitor-main"><span class="guru-live-dot"></span><div><small>MONITORAMENTO ATIVO · \${esc(stage)}</small><strong>\${esc(label)}</strong><span>\${esc(readableAsset(symbol))}</span></div></div>
      <div class="guru-monitor-detail">\${esc(detail||"Atualizando leitura técnica…")}</div>
    </div>\`;
  }

  function monitoringLabel(analysis,cycle){
    const entry=analysis?.entry||{};
    if(entry.ready||entry.status==="ENTRADA CONFIRMADA") return "FAÇA A ENTRADA AGORA";
    if(entry.status==="PRÓXIMO CANDLE") return "ATENÇÃO";
    if(analysis?.signal&&analysis?.score>=72) return "SINAL PRÓXIMO";
    return ["BUSCANDO SINAL","CALCULANDO MERCADO","TESTANDO SINAIS"][cycle%3];
  }

  function monitoringDetail(analysis,label,cycle){
    const entry=analysis?.entry||{};
    if(label==="FAÇA A ENTRADA AGORA") return `Confirmação encontrada para ${analysis?.signal==="CALL"?"CALL":"PUT"}. O monitoramento será encerrado agora.`;
    if(label==="ATENÇÃO") return entry.instruction||"A configuração está próxima, mas o gatilho ainda não confirmou.";
    if(label==="SINAL PRÓXIMO") return entry.instruction||`Direção ${analysis?.signal||"definida"} encontrada; acompanhando a confirmação do gatilho em tempo real.`;
    return cycle%3===0?"Atualizando candles e procurando uma configuração válida.":cycle%3===1?"Recalculando a estratégia selecionada, contexto, setup e gatilho.":"Testando a condição atual contra os critérios da estratégia isolada.";
  }

  async function analyze(){
    const btn=document.getElementById("guruIqAnalyzeBtn"),result=document.getElementById("guruIqResult"),msg=document.getElementById("guruIqMessage");
    const symbol=document.getElementById("guruIqPair")?.value;
    const timeframe=document.getElementById("guruIqCandlePeriod")?.value;
    const strategy=document.getElementById("guruIqStrategy")?.value||"automatica";
    const optionType=document.getElementById("guruIqOptionType")?.value||"binary";
    const expiryMinutes=Number(document.getElementById("guruIqExpiry")?.value||5);
    const analyzeWithAI=!!document.getElementById("guruIqAnalyzeWithAI")?.checked;
    if(!symbol||!timeframe||monitoring)return;

    const runId=++monitorRunId;
    monitoring=true;
    setMonitoringUI(true);
    if(msg){msg.hidden=true;msg.textContent="";}

    let cycle=0;
    let lastAnalysis=null;
    result.innerHTML=monitorStatusHtml(symbol,"BUSCANDO SINAL","Iniciando a busca automática. Você não precisa clicar novamente.");

    try{
      while(monitoring&&runId===monitorRunId){
        const label=monitoringLabel(lastAnalysis,cycle);
        const detail=monitoringDetail(lastAnalysis,label,cycle);
        result.innerHTML=monitorStatusHtml(symbol,label,detail);

        const useAI=analyzeWithAI && (!lastAnalysis || cycle%5===0);
        const d=await jsonResponse(await iqFetch("/market-analysis",{
          method:"POST",
          body:JSON.stringify({symbol,timeframe,strategy,option_type:optionType,expiry_minutes:expiryMinutes,analyze_with_ai:useAI})
        }));

        if(runId!==monitorRunId)break;
        lastAnalysis=d.analysis;
        result.innerHTML=resultHtml(lastAnalysis);
        document.getElementById("guruNewAnalysis")?.addEventListener("click",()=>analyze());

        if(lastAnalysis?.entry?.ready){
          monitoring=false;
          setMonitoringUI(false);
          const finalBtn=document.getElementById("guruIqAnalyzeBtn");
          if(finalBtn)finalBtn.textContent="🔍 ANALISAR NOVAMENTE";
          break;
        }

        cycle++;
        await sleep(4500);
      }
    }catch(e){
      if(runId===monitorRunId){
        monitoring=false;
        result.innerHTML=`<div class="card guru-error"><strong>Não foi possível continuar o monitoramento.</strong><span>${esc(e.message)}</span><small>A análise automática foi encerrada. Clique novamente em “Analisar novamente” para iniciar outro ciclo.</small></div>`;
        setMonitoringUI(false);
      }
    }finally{
      if(runId===monitorRunId&&monitoring===false){
        const b=document.getElementById("guruIqAnalyzeBtn");
        if(b)b.textContent="🔍 ANALISAR NOVAMENTE";
      }
    }
  }

  async function renderRoute(){
    const hash=location.hash||"";
    if(!hash.includes("/ferramenta/"+TOOL_ID)){
      monitoring=false;
      monitorRunId++;
      return;
    }
    if(!document.getElementById("guruIqToolHost")){
      setTimeout(renderRoute,0);
      return;
    }
    const existing=sessionStorage.getItem(SESSION_KEY);
    if(existing)await renderConnected();else renderLogin();
    document.title="GURÚ DOS SINAIS IQOPTION | Resolvei";window.scrollTo({top:0,behavior:"auto"});
  }

  function boot(){renderRoute();window.addEventListener("hashchange",()=>setTimeout(()=>renderRoute(),0));}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();