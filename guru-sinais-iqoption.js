(() => {
  const TOOL_ID = "guru-dos-sinais-iqoption";
  const API = "/api/guru-sinais-iqoption";
  const SESSION_KEY = "resolvei_iqoption_session";
  const timeframes = [["1m","1 minuto"],["5m","5 minutos"],["15m","15 minutos"],["30m","30 minutos"],["1h","1 hora"]];
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
        <p>Mesma leitura técnica do GURÚ DOS SINAIS, mas usando candles diretamente da IQ Option.</p>
      </section>
      <section class="card guru-control-card">
        <div class="iq-connected-bar"><span><strong>● CONECTADO À IQ OPTION</strong><small>${hasAssets?"Ativos de opções disponíveis agora.":"Nenhum ativo de opções está aberto agora."}</small></span>
          <button class="btn ghost small" id="iqRefreshAssets">↻ Atualizar ativos</button><button class="btn ghost small" id="iqLogout">Sair</button>
        </div>
        <div class="guru-control-grid guru-control-grid-3">
          <div class="field"><label for="guruIqPair">Par de moedas</label><select id="guruIqPair">${assetOptions(assets)}</select></div>
          <div class="field"><label for="guruIqTimeframe">Timeframe de entrada</label><select id="guruIqTimeframe">${timeframes.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}</select></div>
          <div class="field"><label for="guruIqStrategy">Estratégia</label><select id="guruIqStrategy">${strategies.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}</select></div>
        </div>
        <label class="guru-ai-toggle"><input type="checkbox" id="guruIqAnalyzeWithAI"><span>Analisar com I.A.</span><small>Valida somente a estratégia selecionada.</small></label>
        <button class="guru-analyze-btn" id="guruIqAnalyzeBtn" ${hasAssets?"":"disabled"}>🔍 ANALISAR MERCADO</button>
        <div id="guruIqMessage" class="notice" hidden></div>
      </section>
      <section id="guruIqResult"><div class="card guru-empty"><div class="guru-empty-icon">📊</div><strong>Pronto para analisar</strong><span>Os candles serão buscados diretamente na sessão conectada da IQ Option.</span></div></section>
      <section class="guru-foot-note"><span>Ferramenta de estudo. A API comunitária da IQ Option é não oficial, os indicadores não garantem resultado futuro e o sistema não executa operações.</span></section>
    </div>`;
  }

  function classFor(signal) {
    return signal === "CALL" ? "guru-call" : signal === "PUT" ? "guru-put" : "guru-wait";
  }

  function resultHtml(a) {
    const reasons = (a.reasons || []).slice(0,7).map(x => `<li>✓ ${esc(x)}</li>`).join("");
    const warnings = (a.warnings || []).slice(0,5).map(x => `<li>⚠ ${esc(x)}</li>`).join("");
    const score = Math.max(0, Math.min(100, Number(a.score || 0)));
    const selectedStrategy = (a.strategies || []).find(s => s.strategy === a.strategy) || a.strategies?.[0];
    const strategyRows = selectedStrategy ? `
      <div class="guru-strategy-card ${selectedStrategy.direction === "CALL" ? "guru-strategy-call" : selectedStrategy.direction === "PUT" ? "guru-strategy-put" : ""}">
        <div><strong>${esc(selectedStrategy.strategyLabel)}</strong><span>${esc(selectedStrategy.direction)}</span></div>
        <small>${Number(selectedStrategy.confidence || 0).toFixed(0)}% · ${Number(selectedStrategy.indicators?.length || 0)} indicadores · estratégia isolada</small>
      </div>` : "";

    const indicators = (a.strategies || []).find(s => s.strategy === a.strategy)?.indicators || [];
    const indicatorRows = indicators.map(i => `
      <div class="guru-indicator-row">
        <span>${esc(i.name)}</span><strong>${esc(i.signal)}</strong>
      </div>`).join("");
    const gemini = a.gemini || {};
    const mtf = a.mtf || {};
    const tf = a.analysisTimeframes || {};
    const tfLabel = x => x === "1m" ? "1 min" : x === "5m" ? "5 min" : x === "15m" ? "15 min" : x === "30m" ? "30 min" : x === "1h" ? "1 hora" : x === "4h" ? "4 horas" : x;
    const mtfRows = [
      ["CONTEXTO", tf.context || mtf.context?.timeframe, mtf.context?.direction, mtf.context?.confidence],
      ["SETUP", tf.setup || mtf.setup?.timeframe, mtf.setup?.direction, mtf.setup?.confidence],
      ["GATILHO", tf.trigger || mtf.trigger?.timeframe, mtf.trigger?.direction, mtf.trigger?.confidence]
    ].map(([label,timeframe,direction,confidence]) =>
      '<div class="guru-mtf-item"><span>' + label + '</span><strong>' + esc(tfLabel(timeframe || "—")) + '</strong><em class="' +
      (direction === "CALL" ? "guru-call-text" : direction === "PUT" ? "guru-put-text" : "") + '">' +
      esc(direction || "—") + '</em><small>' + (confidence != null ? Number(confidence).toFixed(0) + "%" : "—") + '</small></div>'
    ).join("");
    return `
      <div class="card guru-result">
        <div class="guru-result-top">
          <div>
            <span class="eyebrow">${esc(a.symbol)} · ${esc(a.timeframe)} · ${esc(a.strategyLabel || "estratégia")}</span>
            <div class="guru-result-title">SINAL DE ENTRADA</div>
          </div>
          <div class="guru-price">${a.price != null ? esc(Number(a.price).toFixed(5)) : "—"}</div>
        </div>

        <div class="guru-big-signal ${classFor(a.signal)}">${esc(a.signal)}</div>
        <div class="guru-quality">${esc(a.quality)}</div>
        <div class="guru-entry-box ${a.entry?.ready ? "ready" : "wait"}">
          <div class="guru-entry-head"><strong>⏱ MOMENTO DA ENTRADA</strong><span class="guru-entry-status">${esc(a.entry?.status || "AGUARDE O GATILHO")}</span></div>
          <div class="guru-entry-instruction">${esc(a.entry?.instruction || (a.signal === "CALL" ? "Aguarde a confirmação do gatilho antes de clicar no CALL." : a.signal === "PUT" ? "Aguarde a confirmação do gatilho antes de clicar no PUT." : "Aguarde uma direção técnica clara."))}</div>
          <div class="guru-entry-meta"><span>Direção: <strong>${esc(a.signal)}</strong></span><span>Gatilho: <strong>${esc(tfLabel(a.entry?.triggerTimeframe || tf.trigger || "1m"))}</strong></span><span>Tempo da vela: <strong>${Number(a.entry?.secondsRemaining || 0)}s</strong></span></div>
          <div class="guru-entry-disclaimer">O sinal e o timing são uma leitura técnica de estudo. A condição pode mudar rapidamente e não garante o resultado da operação.</div>
        </div>

        <div class="guru-score-line">
          <span>Confluência final</span>
          <strong>${score}%</strong>
        </div>
        <div class="guru-meter"><span style="width:${score}%"></span></div>
        <div class="guru-backtest-box">
          <div class="guru-backtest-head"><strong>📊 TESTE HISTÓRICO DA ESTRATÉGIA</strong><span>mesma lógica do sinal atual</span></div>
          <div class="guru-backtest-grid">
            <div><span>Sinais testados</span><strong>\${Number(a.backtest?.testedSignals || 0)}</strong></div>
            <div><span>Acertos</span><strong>\${Number(a.backtest?.wins || 0)}</strong></div>
            <div><span>Erros</span><strong>\${Number(a.backtest?.losses || 0)}</strong></div>
            <div><span>Taxa de acerto</span><strong>\${Number(a.backtest?.hitRate || 0).toFixed(1)}%</strong></div>
            <div><span>Parte anterior</span><strong>\${Number(a.backtest?.olderHitRate || 0).toFixed(1)}%</strong></div>
            <div><span>Parte recente</span><strong>\${Number(a.backtest?.recentHitRate || 0).toFixed(1)}%</strong></div>
          </div>
          <div class="guru-backtest-note">\${
            Number(a.backtest?.testedSignals || 0) >= 100
              ? "Foram simulados 100 sinais históricos da mesma estratégia."
              : \`Foram encontrados \${Number(a.backtest?.testedSignals || 0)} sinais históricos válidos no conjunto disponível.\`
          } \${
            a.backtest?.consistent
              ? "O desempenho ficou acima de 50% nas duas metades da amostra."
              : "A amostra não mostrou consistência suficiente entre as duas metades."
          }</div>
          <div class="guru-backtest-method">Modelo: entrada hipotética na abertura do candle seguinte à confirmação e resultado no fechamento correspondente à expiração de \${Number(a.backtest?.expiryMinutes || 0)} min.</div>
        </div>

        <div class="guru-ai-box">
          <strong>✨ Gemini</strong>
          <span>${gemini.available ? "Validação da leitura técnica concluída." : "Validação IA indisponível; sinal calculado somente pela estratégia selecionada."}</span>
          ${gemini.reason ? `<small>${esc(gemini.reason)}</small>` : ""}
        </div>

        <div class="guru-strategy-grid">${strategyRows}</div>

        <div class="guru-mtf-box">
          <div class="guru-mtf-head">
            <strong>Leitura em múltiplos timeframes</strong>
            <span>Contexto → Setup → Gatilho</span>
          </div>
          <div class="guru-mtf-grid">${mtfRows}</div>
          <small class="guru-mtf-note">A mesma estratégia é aplicada no contexto, setup e gatilho; nenhuma outra estratégia entra no cálculo.</small>
        </div>

        <div class="guru-columns">
          <div>
            <h3>Leitura do GURÚ</h3>
            <ul>${reasons || "<li>Sem confirmação suficiente.</li>"}</ul>
          </div>
          <div>
            <h3>Pontos de atenção</h3>
            <ul>${warnings || "<li>Nenhum alerta relevante detectado.</li>"}</ul>
          </div>
        </div>

        <details class="guru-indicators-details">
          <summary>Ver os indicadores da estratégia (${indicatorRows ? indicators.length : 0})</summary>
          <div class="guru-indicator-list">${indicatorRows}</div>
        </details>

        <div class="guru-mini-grid">
          <div><span>RSI</span><strong>${a.indicators?.RSI != null ? Number(a.indicators.RSI).toFixed(1) : "—"}</strong></div>
          <div><span>ADX</span><strong>${a.indicators?.ADX != null ? Number(a.indicators.ADX).toFixed(1) : "—"}</strong></div>
          <div><span>Stochastic</span><strong>${a.indicators?.StochasticK != null ? Number(a.indicators.StochasticK).toFixed(1) : "—"}</strong></div>
          <div><span>ATR</span><strong>${a.indicators?.ATRpct != null ? Number(a.indicators.ATRpct).toFixed(3) + "%" : "—"}</strong></div>
        </div>

        <div class="guru-result-bottom">
          <button class="btn primary" id="guruNewAnalysis">Nova análise</button>
          <span>Atualizado: ${esc(a.timestamp)}</span>
        </div>
      </div>
    `;
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

  function renderLogin(message=""){
    const app=document.getElementById("app"); if(!app)return;
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
        const app=document.getElementById("app");app.innerHTML=breadcrumbWrap(twoFAShell());bindTwoFA();return;
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
    const app=document.getElementById("app");if(!app)return;
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
  }

  async function analyze(){
    const btn=document.getElementById("guruIqAnalyzeBtn"),result=document.getElementById("guruIqResult"),msg=document.getElementById("guruIqMessage");
    const symbol=document.getElementById("guruIqPair")?.value,timeframe=document.getElementById("guruIqTimeframe")?.value,strategy=document.getElementById("guruIqStrategy")?.value||"automatica",analyzeWithAI=!!document.getElementById("guruIqAnalyzeWithAI")?.checked;
    if(!symbol||!timeframe)return;
    btn.disabled=true;btn.textContent="⏳ CALCULANDO…";if(msg){msg.hidden=true;msg.textContent="";}
    result.innerHTML=`<div class="card guru-loading"><div class="guru-spinner"></div><strong>Analisando ${esc(readableAsset(symbol))}</strong><span>indicadores da estratégia selecionada + contexto maior + setup + gatilho${analyzeWithAI?" + validação Gemini":"."}</span></div>`;
    try{
      const d=await jsonResponse(await iqFetch("/market-analysis",{method:"POST",body:JSON.stringify({symbol,timeframe,strategy,analyze_with_ai:analyzeWithAI})}));
      result.innerHTML=resultHtml(d.analysis);
      document.getElementById("guruNewAnalysis")?.addEventListener("click",()=>window.scrollTo({top:0,behavior:"smooth"}));
    }catch(e){result.innerHTML=`<div class="card guru-error"><strong>Não foi possível concluir a análise.</strong><span>${esc(e.message)}</span></div>`;}
    finally{const b=document.getElementById("guruIqAnalyzeBtn");if(b){b.disabled=false;b.textContent="🔍 ANALISAR MERCADO";}}
  }

  async function renderRoute(){
    const hash=location.hash||"";if(!hash.includes("/ferramenta/"+TOOL_ID))return;
    const existing=sessionStorage.getItem(SESSION_KEY);
    if(existing)await renderConnected();else renderLogin();
    document.title="GURÚ DOS SINAIS IQOPTION | Resolvei";window.scrollTo({top:0,behavior:"auto"});
  }

  function boot(){renderRoute();window.addEventListener("hashchange",()=>setTimeout(()=>renderRoute(),0));}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();