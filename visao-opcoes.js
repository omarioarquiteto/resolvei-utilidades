(() => {
  const TOOL_ID = "visao-opcoes";
  const API = "/api/visao-opcoes";
  const SESSION_KEY = "resolvei_visao_opcoes_session";
  const candlePeriods = [["1m","1 minuto"],["5m","5 minutos"],["15m","15 minutos"],["30m","30 minutos"],["1h","1 hora"]];
  const optionTypes = [["binary","Binárias"]];
  const expiryOptions = {binary:[[1,"1 minuto"],[5,"5 minutos"],[15,"15 minutos"]]};
  const strategies = [["automatica","🤖 Automática — escolhe 1"],["tendencia","📈 Tendência"],["reversao","↩️ Reversão"],["rompimento","🚀 Rompimento"],["momentum","⚡ Momentum"]];
  const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));

  function card() {
    return `<article class="card tool-card guru-tool-card"><a href="#/ferramenta/${TOOL_ID}">
      <div class="tool-icon">🧙‍♂️</div><h3>VISÃO OPÇÕES</h3>
      <p>Analise técnica automática usando os dados da IQ Option, incluindo OTC.</p>
    </a></article>`;
  }

  function breadcrumbWrap(body){return `<div class="tool-page iq-tool-page">${body}</div>`;}

  function loginShell(message=""){
    return `<div class="guru-simple guru-iq-shell">
      <section class="guru-simple-head"><span class="eyebrow">IQ OPTION · DADOS DIRETOS</span>
        <h1>🧙‍♂️ VISÃO OPÇÕES</h1>
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
    const opts=assetOptions(assets);
    return `
      <div class="guru-simple guru-ux vo-app">
        <section class="guru-hero">
          <div>
            <span class="eyebrow">IQ OPTION · MARKET INSIGHT</span>
            <h1>🔭 VISÃO OPÇÕES</h1>
            <p>Terminal de análise de pares, contexto macroeconômico e leitura técnica em tempo real.</p>
          </div>
          <div class="guru-live-chip"><span></span>${hasAssets?"CONECTADO":"SEM ATIVOS"}</div>
        </section>

        <nav class="vo-nav" aria-label="Módulos do Visão Opções">
          <button class="vo-tab active" data-vo-tab="analysis">📊 Análise do par</button>
          <button class="vo-tab" data-vo-tab="radar">📡 Radar de pares</button>
          <button class="vo-tab" data-vo-tab="facts">📰 Fatos relevantes</button>
          <button class="vo-tab" data-vo-tab="indicators">🧭 Indicadores</button>
        </nav>

        <section class="vo-panel active" id="voPanelAnalysis">
          <section class="guru-config-card card">
            <div class="guru-config-row">
              <div class="guru-field guru-field-main">
                <label for="guruIqPair">PAR</label>
                <select id="guruIqPair">${opts}</select>
              </div>
              <div class="guru-field">
                <label for="guruIqExpiry">EXPIRAÇÃO</label>
                <select id="guruIqExpiry">
                  <option value="1">1 minuto</option>
                  <option value="5">5 minutos</option>
                  <option value="15">15 minutos</option>
                </select>
              </div>
              <div class="guru-field guru-field-strategy">
                <label for="guruIqStrategy">ESTRATÉGIA</label>
                <select id="guruIqStrategy">
                  ${strategies.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}
                </select>
              </div>
              <button class="guru-analyze-btn" id="guruIqAnalyzeBtn" ${hasAssets?"":"disabled"}>🔍 ANALISAR MERCADO</button>
            </div>
            <div class="guru-config-bottom">
              <div class="guru-option-hint">Leitura técnica contínua. O VISÃO OPÇÕES analisa e informa, mas não envia ordens para a IQ Option.</div>
              <div class="guru-config-actions">
                <button class="btn ghost small" id="iqRefreshAssets">↻ Atualizar</button>
                <button class="btn ghost small" id="guruIqCancelBtn" hidden>✕ Cancelar</button>
                <button class="btn ghost small" id="iqLogout">Sair</button>
              </div>
            </div>
            <div id="guruIqMessage" class="notice guru-inline-message" hidden></div>
          </section>

          <section id="guruIqResult" class="guru-result-stage">
            <div class="guru-empty card">
              <div class="guru-empty-icon">◈</div>
              <strong>Pronto para analisar</strong>
              <span>Selecione o par, a expiração e a estratégia.</span>
            </div>
          </section>
        </section>

        <section class="vo-panel" id="voPanelRadar">
          <div class="vo-section-head">
            <div><span class="eyebrow">SCAN DO MERCADO</span><h2>📡 Radar de pares</h2><p>Varre os pares disponíveis na sua sessão da IQ Option usando a mesma lógica técnica individual.</p></div>
            <div class="vo-controls">
              <select id="voRadarTf"><option value="1m">1m</option><option value="5m" selected>5m</option><option value="15m">15m</option></select>
              <select id="voRadarExpiry"><option value="1">1 min</option><option value="5" selected>5 min</option><option value="15">15 min</option></select>
              <select id="voRadarStrategy">${strategies.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}</select>
              <label class="vo-check"><input id="voRadarOtc" type="checkbox" checked> OTC</label>
              <button class="btn primary" id="voRadarRun">🔎 Atualizar radar</button>
            </div>
          </div>
          <div id="voRadarStatus" class="vo-status">Pronto para varrer os pares.</div>
          <div id="voRadarGrid" class="vo-radar-grid"></div>
        </section>

        <section class="vo-panel" id="voPanelFacts">
          <div class="vo-section-head">
            <div><span class="eyebrow">CALENDÁRIO MACRO</span><h2>📰 Fatos relevantes</h2><p>Eventos econômicos fornecidos pela Biquote, filtrados por moeda do par quando um par está selecionado.</p></div>
            <div class="vo-controls">
              <select id="voFactsHours"><option value="12">12h</option><option value="24" selected>24h</option><option value="48">48h</option><option value="168">7 dias</option></select>
              <select id="voFactsImportance"><option value="all" selected>Todos</option><option value="high">Alto impacto</option><option value="medium">Médio</option><option value="low">Baixo</option></select>
              <select id="voFactsPair"><option value="">Todos os pares</option>${(assets.normal||[]).concat(assets.otc||[]).map(x=>`<option value="${esc(x.symbol)}">${esc(readableAsset(x.symbol))}</option>`).join("")}</select>
              <button class="btn primary" id="voFactsRun">↻ Atualizar fatos</button>
            </div>
          </div>
          <div id="voFactsStatus" class="vo-status">Consultando o calendário da Biquote quando você abrir esta aba.</div>
          <div id="voFactsGrid" class="vo-facts-grid"></div>
        </section>

        <section class="vo-panel" id="voPanelIndicators">
          <div class="vo-section-head">
            <div><span class="eyebrow">LEITURA QUANTITATIVA</span><h2>🧭 Indicadores</h2><p>Valores da última análise do par selecionado. A leitura permanece somente informativa.</p></div>
          </div>
          <div id="voIndicatorGrid" class="vo-indicator-grid"><div class="vo-empty">Execute uma análise do par para preencher os indicadores.</div></div>
        </section>
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
    const signal=a?.signal||"AGUARDAR";
    const call=signal==="CALL";
    const put=signal==="PUT";
    const score=Math.max(0,Math.min(100,Number(a?.score||0)));
    const indicators=(a?.indicatorReadings||[]).map(v=>`
      <div class="guru-indicator-row">
        <span>${esc(v.name)}</span>
        <strong class="${v.signal==="CALL"?"call":v.signal==="PUT"?"put":"neutral"}">${esc(v.signal)}</strong>
        <small>${esc(v.reason)}</small>
      </div>`).join("");
    const reasons=(a?.reasons||[]).slice(0,6).map(x=>`<li>✓ ${esc(x)}</li>`).join("");
    const warnings=(a?.warnings||[]).slice(0,4).map(x=>`<li>⚠ ${esc(x)}</li>`).join("");
    return `
      <div class="guru-dashboard">
        <section class="guru-signal-card card">
          <div class="guru-signal-head">
            <div><span class="eyebrow">VISÃO OPÇÕES · ${esc(a?.strategyLabel||a?.strategy||"")}</span><span class="guru-signal-kicker">${esc(readableAsset(a?.symbol))}</span></div>
            <div class="guru-price">${a?.price!=null?esc(Number(a.price).toFixed(5)):"—"}</div>
          </div>
          <div class="guru-signal-core ${call?"guru-call":put?"guru-put":"guru-wait"}">
            <span class="guru-signal-label">${esc(call?"CALL":put?"PUT":"AGUARDAR")}</span>
            <span class="guru-signal-quality">${esc(a?.quality||"Leitura técnica")}</span>
          </div>
          <div class="guru-score-compact">
            <div><span>CONFLUÊNCIA TÉCNICA</span><strong>${score.toFixed(0)}%</strong></div>
            <div class="guru-meter"><span style="width:${score}%"></span></div>
          </div>
          <div class="guru-summary-grid">
            <div><span>EXPIRAÇÃO</span><strong>${esc(a?.expiryMinutes)} min</strong></div>
            <div><span>SETUP</span><strong>${esc(a?.analysisTimeframes?.setup||"—")}</strong></div>
            <div><span>GATILHO</span><strong>${esc(a?.analysisTimeframes?.trigger||"—")}</strong></div>
            <div><span>ESTRATÉGIA</span><strong>${esc(a?.strategyLabel||a?.strategy||"—")}</strong></div>
          </div>
          <div class="guru-entry-compact ${a?.signalConfirmed?"ready":""}">
            <div><span class="guru-entry-title">MOMENTO</span><strong>${esc(a?.entry?.status||"ANALISANDO")}</strong></div>
            <div class="guru-entry-direction">${call?"CALL":put?"PUT":"—"}</div>
            <div class="guru-entry-countdown">${Number(a?.entry?.secondsRemaining||0)}s</div>
          </div>
          <div class="guru-action-row">
            <button class="btn primary" id="guruNewAnalysis">↻ NOVA ANÁLISE</button>
            <span>${esc(a?.entry?.instruction||"O motor continua analisando o mercado.")}</span>
          </div>
        </section>
        <aside class="guru-side-stack">
          <section class="guru-evidence-card card">
            <div class="guru-panel-title"><strong>INDICADORES DA ESTRATÉGIA</strong><span>${score.toFixed(0)}%</span></div>
            <div class="guru-indicator-list">${indicators||"<span class='muted'>Calculando indicadores…</span>"}</div>
          </section>
          <section class="guru-evidence-card card">
            <div class="guru-panel-title"><strong>INTERPRETAÇÃO</strong></div>
            <ul class="guru-reason-list">${reasons||"<li>Leitura em atualização.</li>"}</ul>
            ${warnings?`<div class="guru-warning-mini">${warnings}</div>`:""}
          </section>
          <section class="guru-evidence-card card">
            <div class="guru-panel-title"><strong>CONTEXTO DO MERCADO</strong></div>
            <p>Contexto: <b>${esc(a?.mtf?.context?.direction||"—")}</b> · Setup: <b>${esc(a?.mtf?.setup?.direction||"—")}</b> · Gatilho: <b>${esc(a?.mtf?.trigger?.direction||"—")}</b></p>
          </section>
          <section class="guru-evidence-card card">
            <div class="guru-panel-title"><strong>FATOS RELEVANTES · BIQUOTE</strong><span>${Number(a?.relevantFacts?.events?.length||0)} evento(s)</span></div>
            <div class="vo-inline-facts">
              ${(a?.relevantFacts?.events||[]).slice(0,4).map(ev=>`<div><strong>${esc(ev.currency||"—")}</strong><span>${esc(ev.title||"Evento")}</span><em>${esc(ev.importance||"")}</em></div>`).join("")||"<span class='muted'>Nenhum evento no período.</span>"}
            </div>
          </section>
          <div class="guru-disclaimer-mini">Esta ferramenta interpreta os indicadores e o comportamento atual do preço. Não utiliza backtest para escolher o sinal. Confluência técnica não é garantia de resultado futuro.</div>
        </aside>
      </div>`;
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

  function iqMount(){return document.getElementById("visaoOpcoesToolHost")||document.getElementById("app");}

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
    document.getElementById("guruIqCancelBtn")?.addEventListener("click",()=>{
      monitoring=false; monitorRunId++; stopMonitorUiTicker(); setMonitoringUI(false);
      const result=document.getElementById("guruIqResult");
      if(result) result.innerHTML='<div class="guru-empty card"><div class="guru-empty-icon">◈</div><strong>Análise cancelada</strong><span>Selecione o par, a expiração e a estratégia para iniciar novamente.</span></div>';
    });
    document.querySelectorAll("[data-vo-tab]").forEach(btn=>btn.addEventListener("click",()=>switchVoTab(btn.dataset.voTab)));
    document.getElementById("voRadarRun")?.addEventListener("click",loadRadar);
    document.getElementById("voFactsRun")?.addEventListener("click",loadFacts);
    document.getElementById("guruIqPair")?.addEventListener("change",()=>syncFactsPair());
    syncOptionControls();
  }

  function switchVoTab(tab){
    const map={analysis:"voPanelAnalysis",radar:"voPanelRadar",facts:"voPanelFacts",indicators:"voPanelIndicators"};
    document.querySelectorAll(".vo-tab").forEach(b=>b.classList.toggle("active",b.dataset.voTab===tab));
    Object.entries(map).forEach(([key,id])=>document.getElementById(id)?.classList.toggle("active",key===tab));
    if(tab==="facts") loadFacts();
    if(tab==="radar" && !document.getElementById("voRadarGrid")?.children.length) loadRadar();
    if(tab==="indicators") renderIndicatorsFromLast();
  }

  function syncFactsPair(){
    const src=document.getElementById("guruIqPair"),dst=document.getElementById("voFactsPair");
    if(!src||!dst)return;
    const value=src.value||"";
    if([...dst.options].some(o=>o.value===value))dst.value=value;
  }

  function factHtml(ev){
    const imp=String(ev?.importance||"low").toLowerCase();
    const mins=ev?.time?Math.round((new Date(ev.time).getTime()-Date.now())/60000):null;
    const timing=mins!=null?(mins<60?("em "+Math.max(0,mins)+" min"):(mins<1440?("hoje · "+Math.round(mins/60)+"h"):(Math.round(mins/1440)+"d"))):"—";
    return `<article class="vo-fact-card impact-${esc(imp)}"><div class="vo-fact-top"><span>${esc(ev.currency||"—")}</span><strong>${esc(imp.toUpperCase())}</strong></div><h3>${esc(ev.title||"Evento econômico")}</h3><p>${esc(ev.description||"")}</p><div class="vo-fact-meta"><span>${esc(timing)}</span><span>${esc(ev.sector||"Macro")}</span></div><div class="vo-fact-values"><span>Anterior <b>${esc(ev.previous??"—")}</b></span><span>Previsão <b>${esc(ev.forecast??"—")}</b></span><span>Atual <b>${esc(ev.actual??"—")}</b></span></div></article>`;
  }

  async function loadFacts(){
    const grid=document.getElementById("voFactsGrid"),status=document.getElementById("voFactsStatus"),btn=document.getElementById("voFactsRun");
    if(!grid)return;
    const hours=Number(document.getElementById("voFactsHours")?.value||24);
    const importance=document.getElementById("voFactsImportance")?.value||"all";
    const symbol=document.getElementById("voFactsPair")?.value||document.getElementById("guruIqPair")?.value||"";
    if(btn){btn.disabled=true;btn.textContent="⏳ Atualizando…";}
    if(status)status.textContent="Consultando a Biquote…";
    try{
      const d=await jsonResponse(await iqFetch("/facts?hours="+hours+"&importance="+encodeURIComponent(importance)+"&symbol="+encodeURIComponent(symbol)));
      const events=d.events||[];
      grid.innerHTML=events.length?events.map(factHtml).join(""):`<div class="vo-empty">Nenhum evento encontrado para o filtro selecionado.</div>`;
      if(status)status.textContent=d.available?(`✓ ${events.length} evento(s) · fonte: Biquote`):("⚠️ "+(d.warning||"Calendário indisponível."));
    }catch(e){grid.innerHTML='<div class="vo-empty">⚠️ '+esc(e.message)+'</div>';if(status)status.textContent="⚠️ "+e.message;}
    finally{if(btn){btn.disabled=false;btn.textContent="↻ Atualizar fatos";}}
  }

  function radarCard(r){
    const signal=r?.signal||"SEM SINAL", cls=signal==="CALL"?"call":signal==="PUT"?"put":"wait";
    return `<article class="vo-radar-card ${cls}" data-pair="${esc(r?.symbol||"")}"><div class="vo-radar-head"><strong>${esc(readableAsset(r?.symbol))}</strong><span>${esc(r?.strategyLabel||r?.strategy||"")}</span></div><div class="vo-radar-main"><strong>${esc(signal)}</strong><span>${Number(r?.proximity||r?.confidence||0).toFixed(0)}%</span></div><div class="vo-radar-bar"><span style="width:${Math.max(0,Math.min(100,Number(r?.proximity||0)))}%"></span></div><div class="vo-radar-meta"><span>Preço <b>${r?.price!=null?Number(r.price).toFixed(5):"—"}</b></span><span>Biquote <b>${r?.newsCount||0}</b></span></div></article>`;
  }

  async function loadRadar(){
    const grid=document.getElementById("voRadarGrid"),status=document.getElementById("voRadarStatus"),btn=document.getElementById("voRadarRun");
    if(!grid)return;
    const tf=document.getElementById("voRadarTf")?.value||"5m",expiry=Number(document.getElementById("voRadarExpiry")?.value||5),strategy=document.getElementById("voRadarStrategy")?.value||"automatica",otc=document.getElementById("voRadarOtc")?.checked!==false;
    if(btn){btn.disabled=true;btn.textContent="⏳ Varrendo…";}
    if(status)status.textContent="Lendo pares e candles da IQ Option…";
    try{
      const d=await jsonResponse(await iqFetch("/pair-radar?timeframe="+tf+"&expiry="+expiry+"&strategy="+encodeURIComponent(strategy)+"&limit=30&include_otc="+otc));
      grid.innerHTML=(d.pairs||[]).map(radarCard).join("")||'<div class="vo-empty">Nenhum par retornou dados suficientes.</div>';
      if(status)status.textContent=`✓ ${d.totalAnalyzed||0} pares processados pela IQ Option.`;
      grid.querySelectorAll("[data-pair]").forEach(el=>el.addEventListener("click",()=>openPairFromRadar(el.dataset.pair)));
    }catch(e){grid.innerHTML='<div class="vo-empty">⚠️ '+esc(e.message)+'</div>';if(status)status.textContent="⚠️ "+e.message;}
    finally{if(btn){btn.disabled=false;btn.textContent="🔎 Atualizar radar";}}
  }

  async function openPairFromRadar(symbol){
    const sel=document.getElementById("guruIqPair");if(sel&&[...sel.options].some(o=>o.value===symbol))sel.value=symbol;
    switchVoTab("analysis");
    setTimeout(()=>analyze(),0);
  }

  function renderIndicatorsFromLast(){
    const grid=document.getElementById("voIndicatorGrid"),a=lastCompletedAnalysis||monitorCurrentAnalysis;
    if(!grid)return;
    const values=a?.indicators||{};
    const keys=Object.keys(values);
    grid.innerHTML=keys.length?keys.map(k=>`<div class="vo-ind-card"><span>${esc(k)}</span><strong>${esc(String(values[k]))}</strong></div>`).join(""):'<div class="vo-empty">Execute uma análise do par para preencher os indicadores.</div>';
  }

  let monitorRunId=0;
  let monitoring=false;
  let monitorUiTimer=null;
  let monitorRequestStartedAt=0;
  let monitorNextPollAt=0;
  let monitorLastUpdateAt=0;
  let monitorClockOffsetMs=0;
  let monitorCurrentAnalysis=null;
  let lastCompletedAnalysis=null;

  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  function monitorClock(){
    return Date.now()+monitorClockOffsetMs;
  }

  function clockLabel(tsMs){
    if(!tsMs)return "—";
    try{return new Date(tsMs).toLocaleTimeString("pt-BR",{hour12:false});}
    catch(_){return "—";}
  }

  function startMonitorUiTicker(){
    clearInterval(monitorUiTimer);
    monitorUiTimer=setInterval(()=>{
      if(!monitoring){
        clearInterval(monitorUiTimer);
        monitorUiTimer=null;
        return;
      }
      const stageEl=document.getElementById("guruIqMonitorStage");
      const reqEl=document.getElementById("guruIqMonitorRequest");
      const elapsedEl=document.getElementById("guruIqMonitorElapsed");
      const nextEl=document.getElementById("guruIqMonitorNext");
      const lastEl=document.getElementById("guruIqMonitorLastUpdate");
      const candleEl=document.getElementById("guruIqMonitorCandle");
      if(!stageEl&&!reqEl&&!elapsedEl&&!nextEl&&!lastEl&&!candleEl)return;

      const now=Date.now();
      if(monitorRequestStartedAt){
        const sec=(now-monitorRequestStartedAt)/1000;
        if(stageEl)stageEl.textContent="ANALISANDO INDICADORES";
        if(reqEl)reqEl.textContent="Lendo candles e interpretando os indicadores selecionados para esta estratégia.";
        if(elapsedEl)elapsedEl.textContent=sec.toFixed(1)+"s em processamento";
        if(nextEl)nextEl.textContent="AGORA";
      }else{
        const nextSec=Math.max(0,(monitorNextPollAt-now)/1000);
        const label=monitoringLabel(monitorCurrentAnalysis,0);
        if(stageEl)stageEl.textContent=label==="SINAL PRÓXIMO"?"INTERPRETANDO INDICADORES":label;
        if(reqEl)reqEl.textContent=label==="SINAL PRÓXIMO"
          ?"O sinal está próximo; o motor continua conferindo o candle de gatilho até a confirmação."
          :"Interpretando os indicadores atuais da estratégia escolhida.";
        if(elapsedEl)elapsedEl.textContent="Leitura concluída";
        if(nextEl)nextEl.textContent=nextSec<=0?"AGORA":nextSec.toFixed(1)+"s";
      }

      if(lastEl)lastEl.textContent=monitorLastUpdateAt?clockLabel(monitorLastUpdateAt):"aguardando";

      const closeAt=Number(monitorCurrentAnalysis?.entry?.candleCloseAt||0)*1000;
      if(candleEl&&closeAt>0){
        const remaining=Math.max(0,(closeAt-monitorClock())/1000);
        candleEl.textContent=remaining.toFixed(0)+"s";
      }else if(candleEl){
        candleEl.textContent="—";
      }
    },250);
  }

  function stopMonitorUiTicker(){
    clearInterval(monitorUiTimer);
    monitorUiTimer=null;
    monitorRequestStartedAt=0;
    monitorNextPollAt=0;
    monitorCurrentAnalysis=null;
  }

  function setMonitoringUI(active){
    const btn=document.getElementById("guruIqAnalyzeBtn");
    const cancel=document.getElementById("guruIqCancelBtn");
    const controls=["guruIqPair","guruIqOptionType","guruIqCandlePeriod","guruIqExpiry","guruIqStrategy","guruIqAnalyzeWithAI"]
      .map(id=>document.getElementById(id)).filter(Boolean);

    controls.forEach(el=>{el.disabled=active;});

    if(btn){
      btn.disabled=active;
      btn.textContent=active?"⏳ ANALISANDO MERCADO…":"🔍 ANALISAR MERCADO";
      btn.classList.toggle("guru-monitoring-active",active);
    }
    if(cancel)cancel.hidden=!active;
  }

  function monitorStatusHtml(symbol,analysis=null){
    const label=monitoringLabel(analysis,0);
    const detail=monitoringDetail(analysis,label,0);
    const p=Math.max(0,Math.min(100,Number(analysis?.proximity||0)));
    return `
      <div class="guru-monitor-compact card">
        <div class="guru-monitor-head">
          <div class="guru-monitor-main">
            <span class="guru-live-dot"></span>
            <div>
              <small>ANÁLISE TÉCNICA</small>
              <strong id="guruIqMonitorLabel">${esc(label)}</strong>
              <span>${esc(readableAsset(symbol))}</span>
            </div>
          </div>
        </div>
        <div class="guru-monitor-progress">
          <div class="guru-monitor-progress-top">
            <span>PROXIMIDADE PARA CONFIRMAÇÃO</span>
            <strong id="guruIqMonitorPercent">${p.toFixed(0)}%</strong>
          </div>
          <div class="guru-progress-track" aria-hidden="true"><span id="guruIqMonitorBar" style="width:${p}%"></span></div>
        </div>
        <div class="guru-monitor-live-meta">
          <div><span>ETAPA DO MOTOR</span><strong id="guruIqMonitorStage" aria-live="polite">PREPARANDO LEITURA</strong></div>
          <div><span>ÚLTIMA LEITURA</span><strong id="guruIqMonitorLastUpdate">aguardando</strong></div>
          <div><span>PRÓXIMA LEITURA</span><strong id="guruIqMonitorNext">AGORA</strong></div>
          <div><span>PROCESSAMENTO</span><strong id="guruIqMonitorElapsed">iniciando</strong></div>
          <div><span>CANDLE DO GATILHO</span><strong id="guruIqMonitorCandle">—</strong></div>
          <div><span>STATUS</span><strong id="guruIqMonitorRequest" aria-live="polite">Consultando o motor técnico…</strong></div>
        </div>
        <div class="guru-monitor-detail" id="guruIqMonitorDetail" aria-live="polite">${esc(detail)}</div>
      </div>`;
  }

  function monitoringLabel(analysis,cycle){
    const entry=analysis?.entry||{};
    if(entry.ready||analysis?.signalConfirmed) return "SINAL CONFIRMADO";
    const state=String(analysis?.analysisState||entry.state||entry.status||"").toUpperCase();
    const p=Math.max(0,Math.min(100,Number(analysis?.proximity||entry.proximity||0)));
    if(state==="SINAL PRÓXIMO"||p>=82) return "SINAL PRÓXIMO";
    if(state==="ATENÇÃO"||p>=65) return "ATENÇÃO";
    if(state==="BUSCANDO DIREÇÃO") return "BUSCANDO DIREÇÃO";
    return "ANALISANDO MERCADO";
  }

  function monitoringDetail(analysis,label,cycle){
    const entry=analysis?.entry||{};
    if(label==="SINAL CONFIRMADO"){
      const direction=analysis?.signal==="CALL"?"CALL":"PUT";
      return `Confirmação técnica encontrada para ${direction}. Encerrando o monitoramento e exibindo o sinal.`;
    }
    if(label==="ATENÇÃO"||label==="SINAL PRÓXIMO"){
      const triggerTf=entry.triggerTimeframe||analysis?.analysisTimeframes?.trigger||"1m";
      return entry.instruction
        ? "Gatilho "+triggerTf+": "+entry.instruction
        : "O motor está acompanhando o candle de gatilho e recalculando a confirmação em ciclos sucessivos.";
    }
    const direction=analysis?.signal==="CALL"||analysis?.signal==="PUT"
      ? analysis.signal
      : (analysis?.mtf?.setup?.direction==="CALL"||analysis?.mtf?.setup?.direction==="PUT" ? analysis.mtf.setup.direction : "");
    if(direction){
      return `Direção ${direction} identificada. O motor continua acompanhando confiança, grupos e gatilho antes de confirmar.`;
    }
    return "Lendo candles e procurando uma direção que atenda aos critérios da estratégia selecionada.";
  }

  function updateMonitorView(analysis,label,detail){
    const labelEl=document.getElementById("guruIqMonitorLabel");
    const percentEl=document.getElementById("guruIqMonitorPercent");
    const barEl=document.getElementById("guruIqMonitorBar");
    const detailEl=document.getElementById("guruIqMonitorDetail");
    const p=Math.max(0,Math.min(100,Number(analysis?.proximity||0)));
    monitorCurrentAnalysis=analysis||null;
    if(Number(analysis?.serverEpoch)) monitorClockOffsetMs=Number(analysis.serverEpoch)*1000-Date.now();
    if(labelEl) labelEl.textContent=label;
    if(percentEl) percentEl.textContent=`${p.toFixed(0)}%`;
    if(barEl) barEl.style.width=`${p}%`;
    if(detailEl) detailEl.textContent=detail||"Atualizando leitura técnica…";
  }

  async function validateFinalWithAI(config,technicalSignal){
    const note=document.getElementById("visaoOpcoesAiNote");
    if(note)note.textContent="✨ IA: validando o sinal em segundo plano…";
    try{
      const d=await jsonResponse(await iqFetch("/market-analysis",{
        method:"POST",
        body:JSON.stringify({
          symbol:config.symbol,
          timeframe:config.timeframe,
          strategy:config.strategy,
          option_type:config.optionType,
          expiry_minutes:config.expiryMinutes,
          analyze_with_ai:true,
          fast_mode:true
        })
      }));
      const ai=d.analysis?.gemini||{};
      if(!note)return;
      if(ai.available&&ai.signal){
        note.textContent=ai.signal===technicalSignal
          ?"🟢 IA: concordou com a direção técnica ("+ai.signal+")."
          :"🟠 IA: divergiu da direção técnica ("+(technicalSignal||"—")+" × "+ai.signal+"). O sinal exibido continua definido pelo motor técnico.";
      }else{
        note.textContent="ℹ️ IA: não forneceu uma direção complementar. O sinal técnico não foi bloqueado.";
      }
    }catch(_){
      if(note)note.textContent="ℹ️ IA: validação complementar não concluída. O sinal técnico permanece disponível.";
    }
  }
  async function analyze(){
    const result=document.getElementById("guruIqResult");
    const msg=document.getElementById("guruIqMessage");
    const symbol=document.getElementById("guruIqPair")?.value;
    const expiry=Number(document.getElementById("guruIqExpiry")?.value||1);
    const strategy=document.getElementById("guruIqStrategy")?.value||"automatica";
    if(!symbol||monitoring)return;

    const runId=++monitorRunId;
    monitoring=true;
    setMonitoringUI(true);
    if(msg){msg.hidden=true;msg.textContent="";}
    result.innerHTML=monitorStatusHtml(symbol,null);
    startMonitorUiTicker();

    try{
      while(monitoring&&runId===monitorRunId){
        const controller=new AbortController();
        const timeout=setTimeout(()=>controller.abort(),4500);
        monitorRequestStartedAt=Date.now();

        try{
          const d=await jsonResponse(await iqFetch("/market-analysis",{
            method:"POST",
            signal:controller.signal,
            body:JSON.stringify({
              symbol,
              timeframe:expiry===1?"1m":expiry===5?"5m":"15m",
              strategy,
              option_type:"binary",
              expiry_minutes:expiry,
              fast_mode:true
            })
          }));

          if(!monitoring||runId!==monitorRunId)break;

          const analysis=d.analysis||{};
          monitorCurrentAnalysis=analysis;
          lastCompletedAnalysis=analysis;
          monitorLastUpdateAt=Date.now();
          monitorRequestStartedAt=0;

          const confirmed=analysis.signalConfirmed===true && (analysis.signal==="CALL"||analysis.signal==="PUT");
          if(confirmed){
            try{
              const facts=await jsonResponse(await iqFetch("/facts?hours=24&importance=all&symbol="+encodeURIComponent(symbol)));
              analysis.relevantFacts=facts;
            }catch(_){}
            monitoring=false;
            setMonitoringUI(false);
            result.innerHTML=resultHtml(analysis);
            document.getElementById("guruNewAnalysis")?.addEventListener("click",analyze);
            stopMonitorUiTicker();
            return;
          }

          const state=String(analysis.analysisState||"ANALISANDO MERCADO").toUpperCase();
          const normalizedState=state==="SINAL PRÓXIMO"?"SINAL PRÓXIMO":state==="ATENÇÃO"?"ATENÇÃO":"ANALISANDO MERCADO";
          const detail=(analysis.signal==="CALL"||analysis.signal==="PUT")
            ?analysis.entry?.instruction||("Direção "+analysis.signal+" encontrada. Acompanhando o gatilho em tempo real.")
            :"Interpretando os indicadores atuais da estratégia selecionada.";

          updateMonitorView(analysis,normalizedState,detail);
        }catch(e){
          if(e?.name!=="AbortError"&&runId===monitorRunId){
            updateMonitorView(
              monitorCurrentAnalysis||null,
              "ANALISANDO MERCADO",
              "Leitura momentaneamente indisponível. O monitor continua tentando a próxima atualização."
            );
          }
        }finally{
          clearTimeout(timeout);
          monitorRequestStartedAt=0;
        }

        if(!monitoring||runId!==monitorRunId)break;

        const proximity=Number(monitorCurrentAnalysis?.proximity||0);
        await sleep(proximity>=82?700:950);
      }
    }catch(_){
      // O cancelamento/saída da ferramenta apenas encerra o loop.
    }
  }

async function renderRoute(){
    const hash=location.hash||"";
    if(!hash.includes("/ferramenta/"+TOOL_ID)){
      monitoring=false;
      monitorRunId++;
      stopMonitorUiTicker();
      document.body.classList.remove("iq-tool-active");
      return;
    }
    document.body.classList.add("iq-tool-active");
    if(!document.getElementById("visaoOpcoesToolHost")){
      setTimeout(renderRoute,0);
      return;
    }
    const existing=sessionStorage.getItem(SESSION_KEY);
    if(existing)await renderConnected();else renderLogin();
    document.title="VISÃO OPÇÕES | Resolvei";window.scrollTo({top:0,behavior:"auto"});
  }

  function boot(){renderRoute();window.addEventListener("hashchange",()=>setTimeout(()=>renderRoute(),0));}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();