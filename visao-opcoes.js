(() => {
  const TOOL_ID = "visao-opcoes";
  const API = "/api/visao-opcoes";
  const SESSION_KEY = "resolvei_visao_opcoes_session";
  const PROFILE_KEY = "resolvei_visao_opcoes_indicator_profiles_v1";

  const strategies = [
    ["automatica", "🤖 Automática — escolhe 1"],
    ["trend_pullback", "📈 Retração na tendência"],
    ["breakout", "🚀 Rompimento de faixa"],
    ["mean_reversion", "↩️ Reversão à média"],
    ["support_resistance", "🧱 Suporte e resistência"],
    ["momentum", "⚡ Momentum"],
    ["stoch_adx", "📊 Tendência com estocástico"],
    ["banda_stoch", "🎯 Banda com estocástico"],
    ["rsi_divergencia", "🔀 Divergência de RSI"]
  ];
  let indicatorCatalog = [];
  let defaultProfiles = {
    trend_pullback:["ema_pullback","adx","rsi","candle_direction"],
    breakout:["donchian","atr","candle_expansion"],
    mean_reversion:["bollinger","rsi","rsi_reversal"],
    support_resistance:["support_zone","rejeicao","candle_direction"],
    momentum:["ema921","macd","adx","rsi"],
    stoch_adx:["ema921","adx","stoch","candle_direction"],
    banda_stoch:["bollinger","stoch","stoch_reversal"],
    rsi_divergencia:["rsi","rsi_divergence","candle_direction"]
  };
  let indicatorProfiles = {};
  let selectedProfileStrategy = "trend_pullback";
  let strategyDescriptions = {
    trend_pullback:"Busca uma correção até a média em uma tendência confirmada.",
    breakout:"Exige fechamento além da máxima ou mínima recente com expansão de volatilidade.",
    mean_reversion:"Procura exaustão nas bandas e confirmação de retorno pelo RSI.",
    support_resistance:"Procura rejeição clara em zonas extremas recentes.",
    momentum:"Exige alinhamento de médias, MACD e força direcional.",
    stoch_adx:"Tendência confirmada por EMA e ADX, com estocástico na mesma direção.",
    banda_stoch:"Reversão na banda de Bollinger confirmada por virada do estocástico.",
    rsi_divergencia:"Preço faz extremo mas o RSI não acompanha; reversão na divergência."
  };

  const fallbackCatalog = [
    ["rsi","RSI (14)","Oscilador de momentum; sobrevenda/sobrecompra e viés direcional."],
    ["stoch","Stochastic","Posição do preço na faixa recente, com cruzamentos."],
    ["stochrsi","Stoch RSI","RSI dentro da própria faixa; extremos de sobrevenda/sobrecompra."],
    ["macd","MACD","Convergência/divergência de médias com histograma."],
    ["ema510","EMA 5/10","Médias curtas; tendência de curtíssimo prazo."],
    ["ema1020","EMA 10/20","Médias médias; direção da tendência recente."],
    ["bollinger","Bollinger","Bandas de volatilidade; extremos sugerem reversão."],
    ["adx","ADX / DI","Força direcional da tendência."],
    ["cci","CCI","Extremos do preço típico."],
    ["williams","Williams %R","Oscilador de momento."],
    ["mfi","MFI (14)","Money Flow Index com volume."],
    ["roc","ROC (10)","Rate of Change."],
    ["sar","Parabolic SAR","Ponto de reversão que acompanha o preço."],
    ["obv","OBV","On-Balance Volume."],
    ["engolfo","Candle de engolfo","Corpo atual engole o corpo anterior."],
    ["atr","ATR (14)","Expansão de volatilidade."],
    ["momentum","Momentum (10)","Diferença do fechamento contra 10 velas atrás."],
    ["cmf","CMF (20)","Chaikin Money Flow."],
    ["donchian","Donchian (20)","Máxima/mínima da faixa de 20 velas."],
    ["rejeicao","Vela de rejeição","Sombra longa no topo ou na base."],
    ["ema_pullback","EMA 20/50 + Pullback","Regra nativa da Retração na tendência."],
    ["ema921","EMA 9/21","Regra nativa de alinhamento rápido."],
    ["candle_direction","Candle direcional","Regra nativa de direção do candle."],
    ["candle_expansion","Candle de expansão","Regra nativa de expansão."],
    ["rsi_reversal","Reversão do RSI","Regra nativa de virada do RSI."],
    ["support_zone","Zona de suporte/resistência","Regra nativa de proximidade da zona."],
    ["stoch_reversal","Reversão do Stoch","Regra nativa de virada do Stochastic."],
    ["rsi_divergence","Divergência de RSI","Regra nativa de divergência."],
  ].map(x => ({ id:x[0], name:x[1], description:x[2], kind:"indicador" }));
  let monitorRunId = 0, monitoring = false, monitorUiTimer = null, monitorRequestStartedAt = 0, monitorNextPollAt = 0, monitorLastUpdateAt = 0, monitorClockOffsetMs = 0, monitorCurrentAnalysis = null, lastCompletedAnalysis = null;
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;" }[c]));

  function breadcrumbWrap(body){ return `<div class="tool-page iq-tool-page">${body}</div>`; }
  function iqMount(){ return document.getElementById("visaoOpcoesToolHost") || document.getElementById("app"); }
  function readableAsset(asset){
    const s=String(asset||"").toUpperCase(); const otc=s.endsWith("-OTC"); const base=s.replace(/-OTC$/,"");
    const pair=(base.length===6&&/^[A-Z]{6}$/.test(base))?base.slice(0,3)+"/"+base.slice(3):base; return otc?pair+" · OTC":pair;
  }
  function assetOptions(data){
    const normal=Array.isArray(data?.normal)?data.normal:[], otc=Array.isArray(data?.otc)?data.otc:[];
    const make=a=>`<option value="${esc(a.symbol)}">${esc(readableAsset(a.symbol))}</option>`; const chunks=[];
    if(otc.length)chunks.push(`<optgroup label="OTC — disponíveis agora">${otc.map(make).join("")}</optgroup>`);
    if(normal.length)chunks.push(`<optgroup label="Mercado normal — disponíveis agora">${normal.map(make).join("")}</optgroup>`);
    return chunks.join("")||"<option value=\"\">Nenhum ativo aberto encontrado</option>";
  }

  function loginShell(message=""){ return `<div class="guru-simple guru-iq-shell"><section class="guru-simple-head"><span class="eyebrow">IQ OPTION · DADOS DIRETOS</span><h1>🔭 VISÃO OPÇÕES</h1><p>Faça login para consultar os ativos e candles diretamente pela conexão da IQ Option.</p></section><section class="card guru-control-card iq-login-card"><div class="iq-login-icon">🔐</div><h2>Entrar na IQ Option</h2><p class="iq-login-note">Suas credenciais são usadas somente para abrir uma sessão temporária com a IQ Option. A sessão não é persistida no banco de dados do Resolvei.</p><div class="form-grid"><div class="field full"><label for="iqEmail">E-mail da IQ Option</label><input id="iqEmail" type="email" autocomplete="username" placeholder="seu@email.com"></div><div class="field full"><label for="iqPassword">Senha</label><input id="iqPassword" type="password" autocomplete="current-password" placeholder="Sua senha da IQ Option"></div></div><div class="actions"><button class="btn primary full" id="iqLoginBtn">🔗 CONECTAR À IQ OPTION</button></div><div id="iqLoginMessage" class="notice" ${message ? "":"hidden"}>${esc(message)}</div><div class="iq-security-note">🔒 A senha não é exibida de volta na tela e não é enviada ao Gemini.</div></section><section class="guru-foot-note"><span>Ferramenta de estudo. A integração usa uma API comunitária não oficial da IQ Option e o Resolvei não executa operações.</span></section></div>`; }
  function twoFAShell(){ return `<div class="guru-simple guru-iq-shell"><section class="guru-simple-head"><span class="eyebrow">IQ OPTION · AUTENTICAÇÃO</span><h1>🔐 Verificação adicional</h1><p>A IQ Option solicitou um código de autenticação para concluir a conexão.</p></section><section class="card guru-control-card iq-login-card"><div class="form-grid"><div class="field full"><label for="iq2faCode">Código de verificação</label><input id="iq2faCode" inputmode="numeric" autocomplete="one-time-code" placeholder="Digite o código recebido"></div></div><div class="actions"><button class="btn primary full" id="iq2faBtn">✅ VALIDAR CÓDIGO</button><button class="btn ghost full" id="iq2faBack">Voltar para o login</button></div><div id="iqLoginMessage" class="notice" hidden></div></section></div>`; }

  function shell(assets){
    const hasAssets=((assets?.normal?.length||0)+(assets?.otc?.length||0))>0;
    return `<style>.vo-strategy-panel{display:grid;grid-template-columns:230px minmax(0,1fr);gap:16px}.vo-strategy-menu{display:flex;flex-direction:column;gap:8px}.vo-strategy-menu button{width:100%;text-align:left;border:1px solid rgba(0,0,0,.08);background:var(--card-bg,#fff);padding:12px;border-radius:10px;cursor:pointer}.vo-strategy-menu button.active{border-color:currentColor}.vo-profile-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}.vo-profile-actions{display:flex;flex-wrap:wrap;gap:8px}.vo-indicator-grid-config{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.vo-indicator-option{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;padding:10px 12px;border:1px solid rgba(0,0,0,.08);border-radius:10px;background:var(--card-bg,#fff)}.vo-indicator-option input{width:18px;height:18px}.vo-indicator-option strong{display:block;font-size:13px}.vo-indicator-option small{display:block;opacity:.68;margin-top:2px;line-height:1.25}.vo-indicator-kind{font-size:10px;text-transform:uppercase;opacity:.55}.vo-profile-summary{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 16px}.vo-profile-chip{border:1px solid rgba(0,0,0,.08);border-radius:999px;padding:6px 9px;font-size:11px}.vo-profile-note{font-size:12px;opacity:.72;margin:0 0 14px}@media(max-width:800px){.vo-strategy-panel{grid-template-columns:1fr}.vo-indicator-grid-config{grid-template-columns:1fr}}</style>
      <div class="guru-simple guru-ux vo-app"><section class="guru-hero"><div><span class="eyebrow">IQ OPTION · MARKET INSIGHT</span><h1>🔭 VISÃO OPÇÕES</h1><p>Motor técnico do market-insight-ai com indicadores configuráveis por estratégia.</p></div><div class="guru-live-chip"><span></span>${hasAssets?"CONECTADO":"SEM ATIVOS"}</div></section>
      <nav class="vo-nav"><button class="vo-tab active" data-vo-tab="analysis">📊 Análise do par</button><button class="vo-tab" data-vo-tab="strategies">⚙️ Estratégias</button><button class="vo-tab" data-vo-tab="radar">📡 Radar</button><button class="vo-tab" data-vo-tab="facts">📰 Fatos</button><button class="vo-tab" data-vo-tab="indicators">🧭 Indicadores</button></nav>
      <section class="vo-panel active" id="voPanelAnalysis"><section class="guru-config-card card"><div class="guru-config-row"><div class="guru-field guru-field-main"><label for="guruIqPair">PAR</label><select id="guruIqPair">${assetOptions(assets)}</select></div><div class="guru-field"><label for="guruIqExpiry">EXPIRAÇÃO</label><select id="guruIqExpiry"><option value="1">1 minuto</option><option value="5">5 minutos</option><option value="15">15 minutos</option></select></div><div class="guru-field guru-field-strategy"><label for="guruIqStrategy">ESTRATÉGIA</label><select id="guruIqStrategy">${strategies.map(x=>`<option value="${x[0]}">${x[1]}</option>`).join("")}</select></div><button class="guru-analyze-btn" id="guruIqAnalyzeBtn" ${hasAssets?"":"disabled"}>🔍 ANALISAR MERCADO</button></div><div class="guru-config-bottom"><div class="guru-option-hint">A estratégia é individual. Use ⚙️ Estratégias para escolher os indicadores que podem participar de cada uma.</div><div class="guru-config-actions"><button class="btn ghost small" id="iqRefreshAssets">↻ Atualizar</button><button class="btn ghost small" id="guruIqCancelBtn" hidden>✕ Cancelar</button><button class="btn ghost small" id="iqLogout">Sair</button></div></div><div id="guruIqMessage" class="notice guru-inline-message" hidden></div></section><section id="guruIqResult" class="guru-result-stage"><div class="guru-empty card"><div class="guru-empty-icon">◈</div><strong>Pronto para analisar</strong><span>Selecione o par, a expiração e a estratégia.</span></div></section></section>
      <section class="vo-panel" id="voPanelStrategies"><div class="vo-section-head"><div><span class="eyebrow">CONFIGURAÇÃO DO MOTOR</span><h2>⚙️ Indicadores por estratégia</h2><p>Cada estratégia tem seu próprio perfil. Marque exatamente os indicadores que poderão votar no cálculo.</p></div></div><div id="voStrategyConfigStatus" class="vo-status">Carregando catálogo…</div><div class="vo-strategy-panel"><div class="vo-strategy-menu" id="voStrategyMenu"></div><div class="card"><div class="vo-profile-head"><div><span class="eyebrow">PERFIL ATUAL</span><h3 id="voStrategyTitle">Tendência</h3><p id="voStrategyDescription" class="vo-profile-note"></p></div><strong id="voStrategyCount">0 indicadores</strong></div><div class="vo-profile-actions"><button class="btn ghost small" id="voMarkAll">✓ Marcar todos</button><button class="btn ghost small" id="voClearAll">□ Desmarcar todos</button><button class="btn ghost small" id="voRestoreDefault">↺ Restaurar padrão</button><button class="btn primary small" id="voSaveProfile">💾 Salvar</button></div><div id="voProfileSummary" class="vo-profile-summary"></div><div id="voIndicatorConfigGrid" class="vo-indicator-grid-config"></div></div></div></section>
      <section class="vo-panel" id="voPanelRadar"><div class="vo-section-head"><div><span class="eyebrow">SCAN DO MERCADO</span><h2>📡 Radar de pares</h2><p>O radar usa os mesmos perfis de indicadores configurados acima.</p></div><div class="vo-controls"><select id="voRadarTf"><option value="1m">1m</option><option value="5m" selected>5m</option><option value="15m">15m</option></select><select id="voRadarExpiry"><option value="1">1 min</option><option value="5" selected>5 min</option><option value="15">15 min</option></select><select id="voRadarStrategy">${strategies.map(x=>`<option value="${x[0]}">${x[1]}</option>`).join("")}</select><label class="vo-check"><input id="voRadarOtc" type="checkbox" checked> OTC</label><button class="btn primary" id="voRadarRun">🔎 Atualizar radar</button></div></div><div id="voRadarStatus" class="vo-status">Pronto para varrer os pares.</div><div id="voRadarGrid" class="vo-radar-grid"></div></section>
      <section class="vo-panel" id="voPanelFacts"><div class="vo-section-head"><div><span class="eyebrow">CALENDÁRIO MACRO</span><h2>📰 Fatos relevantes</h2><p>Eventos econômicos da Biquote filtrados por moeda do par.</p></div><div class="vo-controls"><select id="voFactsHours"><option value="12">12h</option><option value="24" selected>24h</option><option value="48">48h</option><option value="168">7 dias</option></select><select id="voFactsImportance"><option value="all">Todos</option><option value="high">Alto impacto</option><option value="medium">Médio</option><option value="low">Baixo</option></select><select id="voFactsPair"><option value="">Todos os pares</option>${(assets?.normal||[]).concat(assets?.otc||[]).map(x=>`<option value="${esc(x.symbol)}">${esc(readableAsset(x.symbol))}</option>`).join("")}</select><button class="btn primary" id="voFactsRun">↻ Atualizar fatos</button></div></div><div id="voFactsStatus" class="vo-status">Consultando a Biquote quando necessário.</div><div id="voFactsGrid" class="vo-facts-grid"></div></section>
      <section class="vo-panel" id="voPanelIndicators"><div class="vo-section-head"><div><span class="eyebrow">LEITURA QUANTITATIVA</span><h2>🧭 Indicadores</h2><p>Valores e votos da última análise.</p></div></div><div id="voIndicatorGrid" class="vo-indicator-grid"><div class="vo-empty">Execute uma análise para preencher os indicadores.</div></div></section></div>`;
  }

  function sanitizeProfilesLocal(raw){
    const out={};
    ["trend_pullback","breakout","mean_reversion","support_resistance","momentum","stoch_adx","banda_stoch","rsi_divergencia"].forEach(s=>{
      const ids=Array.isArray(raw?.[s])?raw[s]:[];
      out[s]=[...new Set(ids.map(x=>String(x||"").trim().toLowerCase()))].filter(id=>indicatorCatalog.some(i=>i.id===id));
    });
    return out;
  }
  function readProfiles(){
    try{
      const raw=JSON.parse(localStorage.getItem(PROFILE_KEY)||"null");
      if(!raw || typeof raw!=="object") return sanitizeProfilesLocal(defaultProfiles);
      const out=sanitizeProfilesLocal(raw);
      const keys=["trend_pullback","breakout","mean_reversion","support_resistance","momentum","stoch_adx","banda_stoch","rsi_divergencia"];
      keys.forEach(key=>{
        if(!Array.isArray(raw[key])) out[key]=[...(defaultProfiles[key]||[])];
      });
      return out;
    }catch(_){ return sanitizeProfilesLocal(defaultProfiles); }
  }
  function persistProfiles(){ indicatorProfiles=sanitizeProfilesLocal(indicatorProfiles); localStorage.setItem(PROFILE_KEY,JSON.stringify(indicatorProfiles)); }
  function strategyName(id){ return ({trend_pullback:"Retração na tendência",breakout:"Rompimento de faixa",mean_reversion:"Reversão à média",support_resistance:"Suporte e resistência",momentum:"Momentum",stoch_adx:"Tendência com estocástico",banda_stoch:"Banda com estocástico",rsi_divergencia:"Divergência de RSI"})[id] || id; }
  function showProfileStatus(msg){ const el=document.getElementById("voStrategyConfigStatus"); if(el){el.textContent="✓ "+msg;setTimeout(()=>{if(el)el.textContent="✓ Perfil salvo neste navegador.";},1800);} }
  function renderStrategyEditor(){
    const menu=document.getElementById("voStrategyMenu"),grid=document.getElementById("voIndicatorConfigGrid"); if(!menu||!grid)return;
    menu.innerHTML=["trend_pullback","breakout","mean_reversion","support_resistance","momentum","stoch_adx","banda_stoch","rsi_divergencia"].map(id=>`<button class="${selectedProfileStrategy===id?"active":""}" data-profile-strategy="${id}"><strong>${esc(strategyName(id))}</strong><br><small>${indicatorProfiles[id]?.length||0} indicadores ativos</small></button>`).join("");
    document.getElementById("voStrategyTitle").textContent=strategyName(selectedProfileStrategy); document.getElementById("voStrategyDescription").textContent=strategyDescriptions[selectedProfileStrategy];
    const active=new Set(indicatorProfiles[selectedProfileStrategy]||[]); document.getElementById("voStrategyCount").textContent=active.size+" indicador(es) ativo(s)";
    grid.innerHTML=indicatorCatalog.map(ind=>`<label class="vo-indicator-option"><input type="checkbox" data-indicator-id="${esc(ind.id)}" ${active.has(ind.id)?"checked":""}><span><strong>${esc(ind.name)}</strong><small>${esc(ind.description||"")}</small></span><span class="vo-indicator-kind">${esc(ind.kind||"indicador")}</span></label>`).join("");
    const summary=document.getElementById("voProfileSummary"); summary.innerHTML=active.size?[...active].map(id=>`<span class="vo-profile-chip">${esc(indicatorCatalog.find(x=>x.id===id)?.name||id)}</span>`).join(""):"<span class=\"vo-profile-note\">Nenhum indicador selecionado. A estratégia não poderá confirmar uma entrada.</span>";
    menu.querySelectorAll("[data-profile-strategy]").forEach(btn=>btn.addEventListener("click",()=>{selectedProfileStrategy=btn.dataset.profileStrategy;renderStrategyEditor();}));
    grid.querySelectorAll("[data-indicator-id]").forEach(input=>input.addEventListener("change",()=>{indicatorProfiles[selectedProfileStrategy]=[...grid.querySelectorAll("input:checked")].map(x=>x.dataset.indicatorId);persistProfiles();renderStrategyEditor();}));
  }
  function selectCurrentProfileFromUI(){ const grid=document.getElementById("voIndicatorConfigGrid"); if(!grid)return; indicatorProfiles[selectedProfileStrategy]=[...grid.querySelectorAll("input:checked")].map(x=>x.dataset.indicatorId); persistProfiles(); }
  function configureProfileAll(active){ indicatorProfiles[selectedProfileStrategy]=active?indicatorCatalog.map(x=>x.id):[];persistProfiles();renderStrategyEditor();showProfileStatus(active?"Todos os indicadores habilitados.":"Todos os indicadores desabilitados."); }
  function restoreDefaultProfile(){ indicatorProfiles[selectedProfileStrategy]=[...(defaultProfiles[selectedProfileStrategy]||[])];persistProfiles();renderStrategyEditor();showProfileStatus("Perfil padrão restaurado."); }
  function saveAllProfiles(){ selectCurrentProfileFromUI(); persistProfiles(); showProfileStatus("Configurações salvas. A análise e o radar usarão estes perfis."); }
  function profileForRequest(){ selectCurrentProfileFromUI(); return sanitizeProfilesLocal(indicatorProfiles); }

  async function iqFetch(path,options={}){ const session=sessionStorage.getItem(SESSION_KEY)||""; const headers={"Content-Type":"application/json",...(options.headers||{})}; if(session)headers["X-IQ-Session"]=session; try{if(typeof resolveiUser!=="undefined"&&resolveiUser&&typeof resolveiUser.getIdToken==="function"){const token=await resolveiUser.getIdToken();if(typeof token==="string"&&token.split(".").length===3)headers.Authorization="Bearer "+token;}}catch(_){} return fetch(new URL(API+path,window.location.origin).toString(),{...options,headers}); }
  async function jsonResponse(r){ const ct=r.headers.get("content-type")||""; const data=ct.includes("application/json")?await r.json():{detail:await r.text()}; if(!r.ok)throw new Error(data.detail||"Não foi possível concluir a solicitação."); return data; }
  function renderLogin(message=""){const app=iqMount();if(!app)return;app.innerHTML=breadcrumbWrap(loginShell(message));document.getElementById("iqLoginBtn")?.addEventListener("click",login);}
  async function login(){const email=document.getElementById("iqEmail")?.value.trim(),password=document.getElementById("iqPassword")?.value||"",btn=document.getElementById("iqLoginBtn"),msg=document.getElementById("iqLoginMessage");if(!email||!password){if(msg){msg.hidden=false;msg.textContent="Informe e-mail e senha.";}return;}btn.disabled=true;btn.textContent="⏳ CONECTANDO…";try{const r=await fetch(new URL(API+"/login",window.location.origin).toString(),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});const d=await jsonResponse(r);sessionStorage.setItem(SESSION_KEY,d.session_id);if(d.requires_2fa){const app=iqMount();if(app){app.innerHTML=breadcrumbWrap(twoFAShell());bindTwoFA();}return;}await renderConnected();}catch(e){if(msg){msg.hidden=false;msg.textContent="⚠️ "+e.message;}}finally{const b=document.getElementById("iqLoginBtn");if(b){b.disabled=false;b.textContent="🔗 CONECTAR À IQ OPTION";}}}
  function bindTwoFA(){document.getElementById("iq2faBtn")?.addEventListener("click",submit2FA);document.getElementById("iq2faBack")?.addEventListener("click",async()=>{await logout(false);renderLogin();});}
  async function submit2FA(){const code=document.getElementById("iq2faCode")?.value.trim(),btn=document.getElementById("iq2faBtn"),msg=document.getElementById("iqLoginMessage");if(!/^[0-9]{4,10}$/.test(code||"")){if(msg){msg.hidden=false;msg.textContent="Digite um código de verificação válido.";}return;}btn.disabled=true;btn.textContent="⏳ VALIDANDO…";try{const d=await jsonResponse(await iqFetch("/2fa",{method:"POST",body:JSON.stringify({code})}));sessionStorage.setItem(SESSION_KEY,d.session_id);await renderConnected();}catch(e){if(msg){msg.hidden=false;msg.textContent="⚠️ "+e.message;}}finally{const b=document.getElementById("iq2faBtn");if(b){b.disabled=false;b.textContent="✅ VALIDAR CÓDIGO";}}}
  async function loadAssets(){return jsonResponse(await iqFetch("/assets"));}
  async function loadStrategyConfig(){try{const d=await jsonResponse(await iqFetch("/strategy-config"));if(Array.isArray(d.indicators)&&d.indicators.length)indicatorCatalog=d.indicators;if(d.defaultProfiles)defaultProfiles=sanitizeProfilesLocal(d.defaultProfiles);const stored=localStorage.getItem(PROFILE_KEY);indicatorProfiles=stored?readProfiles():sanitizeProfilesLocal(defaultProfiles);if(!stored)persistProfiles();renderStrategyEditor();showProfileStatus("Catálogo carregado.");}catch(e){indicatorCatalog=fallbackCatalog;indicatorProfiles=readProfiles();renderStrategyEditor();const el=document.getElementById("voStrategyConfigStatus");if(el)el.textContent="⚠️ Catálogo local carregado; perfil será enviado ao motor.";}}
  async function renderConnected(){const app=iqMount();if(!app)return;try{await jsonResponse(await iqFetch("/session"));const assets=await loadAssets();app.innerHTML=breadcrumbWrap(shell(assets));bindConnected();await loadStrategyConfig();}catch(e){sessionStorage.removeItem(SESSION_KEY);renderLogin(e.message);}}
  async function refreshAssets(){const btn=document.getElementById("iqRefreshAssets"),msg=document.getElementById("guruIqMessage");if(btn){btn.disabled=true;btn.textContent="⏳ Atualizando…";}try{const assets=await loadAssets(),sel=document.getElementById("guruIqPair"),current=sel?.value;if(sel){sel.innerHTML=assetOptions(assets);if([...sel.options].some(o=>o.value===current))sel.value=current;}const fp=document.getElementById("voFactsPair");if(fp)fp.innerHTML='<option value="">Todos os pares</option>'+(assets.normal||[]).concat(assets.otc||[]).map(x=>`<option value="${esc(x.symbol)}">${esc(readableAsset(x.symbol))}</option>`).join("");const ok=((assets?.normal?.length||0)+(assets?.otc?.length||0))>0;if(document.getElementById("guruIqAnalyzeBtn"))document.getElementById("guruIqAnalyzeBtn").disabled=!ok;if(msg){msg.hidden=false;msg.textContent=ok?"Ativos atualizados diretamente da IQ Option.":"Nenhum ativo aberto neste momento.";}}catch(e){if(msg){msg.hidden=false;msg.textContent="⚠️ "+e.message;}}finally{if(btn){btn.disabled=false;btn.textContent="↻ Atualizar";}}}
  async function logout(showLogin=true){try{await iqFetch("/logout",{method:"POST"});}catch(_){}sessionStorage.removeItem(SESSION_KEY);if(showLogin)renderLogin();}

  function resultHtml(a){const signal=a?.signal||"AGUARDAR",call=signal==="CALL",put=signal==="PUT",score=Math.max(0,Math.min(100,Number(a?.score||0)));const rows=(a?.indicatorReadings||[]).map(v=>`<div class="guru-indicator-row"><span>${esc(v.name)}</span><strong class="${v.signal==="CALL"?"call":v.signal==="PUT"?"put":"neutral"}">${esc(v.signal)}</strong><small>${esc(v.reason)}</small></div>`).join("");const names=(a?.profile?.indicatorNames||[]).map(x=>`<span class="vo-profile-chip">${esc(x)}</span>`).join("");const reasons=(a?.reasons||[]).slice(0,6).map(x=>`<li>✓ ${esc(x)}</li>`).join("");const warnings=(a?.warnings||[]).slice(0,4).map(x=>`<li>⚠ ${esc(x)}</li>`).join("");return `<div class="guru-dashboard"><section class="guru-signal-card card"><div class="guru-signal-head"><div><span class="eyebrow">VISÃO OPÇÕES · ${esc(a?.strategyLabel||a?.strategy||"")}</span><span class="guru-signal-kicker">${esc(readableAsset(a?.symbol))}</span></div><div class="guru-price">${a?.price!=null?esc(Number(a.price).toFixed(5)):"—"}</div></div><div class="guru-signal-core ${call?"guru-call":put?"guru-put":"guru-wait"}"><span class="guru-signal-label">${call?"CALL":put?"PUT":"AGUARDAR"}</span><span class="guru-signal-quality">${esc(a?.quality||"Leitura técnica")}</span></div><div class="guru-score-compact"><div><span>CONFLUÊNCIA TÉCNICA</span><strong>${score.toFixed(0)}%</strong></div><div class="guru-meter"><span style="width:${score}%"></span></div></div><div class="guru-summary-grid"><div><span>EXPIRAÇÃO</span><strong>${esc(a?.expiryMinutes)} min</strong></div><div><span>SETUP</span><strong>${esc(a?.analysisTimeframes?.setup||"—")}</strong></div><div><span>GATILHO</span><strong>${esc(a?.analysisTimeframes?.trigger||"—")}</strong></div><div><span>INDICADORES</span><strong>${Number(a?.profile?.totalSelected||0)}</strong></div></div><div class="guru-entry-compact ${a?.signalConfirmed?"ready":""}"><div><span class="guru-entry-title">MOMENTO</span><strong>${esc(a?.entry?.status||"ANALISANDO")}</strong></div><div class="guru-entry-direction">${call?"CALL":put?"PUT":"—"}</div><div class="guru-entry-countdown">${Number(a?.entry?.secondsRemaining||0)}s</div></div><div class="guru-action-row"><button class="btn primary" id="guruNewAnalysis">↻ NOVA ANÁLISE</button><span>${esc(a?.entry?.instruction||"O motor continua analisando o mercado.")}</span></div></section><aside class="guru-side-stack"><section class="guru-evidence-card card"><div class="guru-panel-title"><strong>INDICADORES DO PERFIL</strong><span>${Number(a?.profile?.totalSelected||0)}</span></div><div class="vo-profile-summary">${names||"<span class=\"muted\">Nenhum.</span>"}</div><div class="guru-indicator-list">${rows||"<span class=\"muted\">Nenhum voto.</span>"}</div></section><section class="guru-evidence-card card"><div class="guru-panel-title"><strong>INTERPRETAÇÃO</strong></div><ul class="guru-reason-list">${reasons||"<li>Leitura em atualização.</li>"}</ul>${warnings?`<div class="guru-warning-mini">${warnings}</div>`:""}</section><section class="guru-evidence-card card"><div class="guru-panel-title"><strong>CONTEXTO DO MERCADO</strong></div><p>Contexto: <b>${esc(a?.mtf?.context?.direction||"—")}</b> · Setup: <b>${esc(a?.mtf?.setup?.direction||"—")}</b> · Gatilho: <b>${esc(a?.mtf?.trigger?.direction||"—")}</b></p></section><section class="guru-evidence-card card"><div class="guru-panel-title"><strong>FATOS RELEVANTES · BIQUOTE</strong><span>${Number(a?.relevantFacts?.events?.length||0)} evento(s)</span></div><div class="vo-inline-facts">${(a?.relevantFacts?.events||[]).slice(0,4).map(ev=>`<div><strong>${esc(ev.currency||"—")}</strong><span>${esc(ev.title||"Evento")}</span><em>${esc(ev.importance||"")}</em></div>`).join("")||"<span class=\"muted\">Nenhum evento no período.</span>"}</div></section><div class="guru-disclaimer-mini">Motor técnico baseado no market-insight-ai. Seleção de indicadores é independente por estratégia. Não há execução automática.</div></aside></div>`;}

  function monitoringLabel(a){
  const phase=String(a?.phase||a?.analysisState||"ANALISANDO MERCADO").toUpperCase();
  if(phase.includes("EXECUTE"))return "EXECUTE A OPERAÇÃO";
  if(phase.includes("GATILHO"))return "BUSCANDO GATILHO";
  if(phase.includes("PRÓXIMO")||phase.includes("PROXIMO"))return "SINAL PRÓXIMO";
  return "ANALISANDO MERCADO";
}
function monitoringDetail(a,label){
  if(label==="EXECUTE A OPERAÇÃO")return a?.entry?.instruction||"Confirmação técnica encontrada. Clique em CALL ou PUT agora.";
  if(label==="BUSCANDO GATILHO")return a?.entry?.instruction||"A direção estrutural está confirmada. Procurando a confirmação final.";
  if(label==="SINAL PRÓXIMO")return a?.entry?.instruction||"Setup encontrado. Aguardando o gatilho técnico.";
  return "Analisando estrutura, contexto, estratégia e indicadores selecionados.";
}
function monitorStatusHtml(symbol,a=null){const p=Math.max(0,Math.min(100,Number(a?.proximity||0)));return `<div class="guru-monitor-compact card"><div class="guru-monitor-head"><div class="guru-monitor-main"><span class="guru-live-dot"></span><div><small>ANÁLISE · MARKET-INSIGHT-AI</small><strong id="guruIqMonitorLabel">${esc(monitoringLabel(a))}</strong><span>${esc(readableAsset(symbol))}</span></div></div></div><div class="guru-monitor-progress"><div class="guru-monitor-progress-top"><span>PROXIMIDADE PARA CONFIRMAÇÃO</span><strong id="guruIqMonitorPercent">${p.toFixed(0)}%</strong></div><div class="guru-progress-track"><span id="guruIqMonitorBar" style="width:${p}%"></span></div></div><div class="guru-monitor-live-meta"><div><span>ETAPA</span><strong id="guruIqMonitorStage">PREPARANDO LEITURA</strong></div><div><span>ÚLTIMA LEITURA</span><strong id="guruIqMonitorLastUpdate">aguardando</strong></div><div><span>PRÓXIMA</span><strong id="guruIqMonitorNext">AGORA</strong></div><div><span>PROCESSAMENTO</span><strong id="guruIqMonitorElapsed">iniciando</strong></div><div><span>CANDLE DO GATILHO</span><strong id="guruIqMonitorCandle">—</strong></div><div><span>STATUS</span><strong id="guruIqMonitorRequest">Consultando o motor técnico…</strong></div></div><div class="guru-monitor-detail" id="guruIqMonitorDetail">${esc(monitoringDetail(a,monitoringLabel(a)))}</div></div>`;}
  function updateMonitorView(a,label,detail){const p=Math.max(0,Math.min(100,Number(a?.proximity||0)));monitorCurrentAnalysis=a||null;if(Number(a?.serverEpoch))monitorClockOffsetMs=Number(a.serverEpoch)*1000-Date.now();const l=document.getElementById("guruIqMonitorLabel"),pe=document.getElementById("guruIqMonitorPercent"),b=document.getElementById("guruIqMonitorBar"),d=document.getElementById("guruIqMonitorDetail");if(l)l.textContent=label;if(pe)pe.textContent=p.toFixed(0)+"%";if(b)b.style.width=p+"%";if(d)d.textContent=detail||"Atualizando leitura técnica…";}
  function startMonitorUiTicker(){clearInterval(monitorUiTimer);monitorUiTimer=setInterval(()=>{if(!monitoring){clearInterval(monitorUiTimer);monitorUiTimer=null;return;}const stage=document.getElementById("guruIqMonitorStage"),req=document.getElementById("guruIqMonitorRequest"),elapsed=document.getElementById("guruIqMonitorElapsed"),next=document.getElementById("guruIqMonitorNext"),last=document.getElementById("guruIqMonitorLastUpdate"),candle=document.getElementById("guruIqMonitorCandle");const now=Date.now();if(monitorRequestStartedAt){const s=(now-monitorRequestStartedAt)/1000;if(stage)stage.textContent="ANALISANDO INDICADORES";if(req)req.textContent="Lendo candles e interpretando os indicadores selecionados.";if(elapsed)elapsed.textContent=s.toFixed(1)+"s em processamento";if(next)next.textContent="AGORA";}else{const ns=Math.max(0,(monitorNextPollAt-now)/1000),label=monitoringLabel(monitorCurrentAnalysis);if(stage)stage.textContent=label;if(req)req.textContent=label==="SINAL PRÓXIMO"?"Acompanhando o gatilho até a confirmação.":"Interpretando a estratégia e o perfil atual.";if(elapsed)elapsed.textContent="Leitura concluída";if(next)next.textContent=ns<=0?"AGORA":ns.toFixed(1)+"s";}if(last)last.textContent=monitorLastUpdateAt?new Date(monitorLastUpdateAt).toLocaleTimeString("pt-BR",{hour12:false}):"aguardando";const closeAt=Number(monitorCurrentAnalysis?.entry?.candleCloseAt||0)*1000;if(candle)candle.textContent=closeAt?Math.max(0,(closeAt-(Date.now()+monitorClockOffsetMs))/1000).toFixed(0)+"s":"—";},250);}
  function stopMonitorUiTicker(){clearInterval(monitorUiTimer);monitorUiTimer=null;monitorRequestStartedAt=0;monitorNextPollAt=0;monitorCurrentAnalysis=null;}
  function setMonitoringUI(active){["guruIqPair","guruIqExpiry","guruIqStrategy"].map(id=>document.getElementById(id)).filter(Boolean).forEach(el=>el.disabled=active);const btn=document.getElementById("guruIqAnalyzeBtn"),cancel=document.getElementById("guruIqCancelBtn");if(btn){btn.disabled=active;btn.textContent=active?"⏳ ANALISANDO MERCADO…":"🔍 ANALISAR MERCADO";}if(cancel)cancel.hidden=!active;}
  function renderIndicatorsFromLast(){const grid=document.getElementById("voIndicatorGrid"),a=lastCompletedAnalysis||monitorCurrentAnalysis;if(!grid)return;if(!a){grid.innerHTML="<div class=\"vo-empty\">Execute uma análise para preencher os indicadores.</div>";return;}const vals=Object.entries(a.indicators||{}).map(([k,v])=>`<div class="vo-ind-card"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join("");const votes=(a.indicatorReadings||[]).map(v=>`<div class="guru-indicator-row"><span>${esc(v.name)}</span><strong class="${v.signal==="CALL"?"call":v.signal==="PUT"?"put":"neutral"}">${esc(v.signal)}</strong><small>${esc(v.reason)}</small></div>`).join("");grid.innerHTML=`<div style="width:100%"><div class="vo-indicator-grid">${vals}</div><section class="guru-evidence-card card" style="margin-top:14px"><div class="guru-panel-title"><strong>VOTOS DO PERFIL</strong><span>${(a.indicatorReadings||[]).length}</span></div><div class="guru-indicator-list">${votes||"<span class=\"muted\">Nenhum voto.</span>"}</div></section></div>`;}
  async function loadFacts(){const grid=document.getElementById("voFactsGrid"),status=document.getElementById("voFactsStatus"),btn=document.getElementById("voFactsRun");if(!grid)return;const hours=Number(document.getElementById("voFactsHours")?.value||24),importance=document.getElementById("voFactsImportance")?.value||"all",symbol=document.getElementById("voFactsPair")?.value||document.getElementById("guruIqPair")?.value||"";if(btn){btn.disabled=true;btn.textContent="⏳ Atualizando…";}try{const d=await jsonResponse(await iqFetch("/facts?hours="+hours+"&importance="+encodeURIComponent(importance)+"&symbol="+encodeURIComponent(symbol)));const events=d.events||[];grid.innerHTML=events.length?events.map(ev=>`<article class="vo-fact-card impact-${esc(String(ev.importance||"low").toLowerCase())}"><div class="vo-fact-top"><span>${esc(ev.currency||"—")}</span><strong>${esc(String(ev.importance||"low").toUpperCase())}</strong></div><h3>${esc(ev.title||"Evento econômico")}</h3><p>${esc(ev.description||"")}</p><div class="vo-fact-meta"><span>${esc(ev.time||"—")}</span><span>${esc(ev.sector||"Macro")}</span></div><div class="vo-fact-values"><span>Anterior <b>${esc(ev.previous??"—")}</b></span><span>Previsão <b>${esc(ev.forecast??"—")}</b></span><span>Atual <b>${esc(ev.actual??"—")}</b></span></div></article>`).join(""):"<div class=\"vo-empty\">Nenhum evento encontrado.</div>";if(status)status.textContent=d.available?`✓ ${events.length} evento(s) · fonte: Biquote`:"⚠️ "+(d.warning||"Calendário indisponível.");}catch(e){grid.innerHTML="<div class=\"vo-empty\">⚠️ "+esc(e.message)+"</div>";if(status)status.textContent="⚠️ "+e.message;}finally{if(btn){btn.disabled=false;btn.textContent="↻ Atualizar fatos";}}}
  async function loadRadar(){const grid=document.getElementById("voRadarGrid"),status=document.getElementById("voRadarStatus"),btn=document.getElementById("voRadarRun");if(!grid)return;const tf=document.getElementById("voRadarTf")?.value||"5m",expiry=Number(document.getElementById("voRadarExpiry")?.value||5),strategy=document.getElementById("voRadarStrategy")?.value||"automatica",otc=document.getElementById("voRadarOtc")?.checked!==false;if(btn){btn.disabled=true;btn.textContent="⏳ Varrendo…";}try{const profiles=encodeURIComponent(JSON.stringify(profileForRequest())),url="/pair-radar?timeframe="+tf+"&expiry="+expiry+"&strategy="+encodeURIComponent(strategy)+"&limit=30&include_otc="+otc+"&profiles_json="+profiles,d=await jsonResponse(await iqFetch(url));grid.innerHTML=(d.pairs||[]).map(r=>`<article class="vo-radar-card ${r.signal==="CALL"?"call":r.signal==="PUT"?"put":"wait"}" data-pair="${esc(r.symbol||"")}"><div class="vo-radar-head"><strong>${esc(readableAsset(r.symbol))}</strong><span>${esc(r.strategyLabel||r.strategy||"")}</span></div><div class="vo-radar-main"><strong>${esc(r.signal||"SEM SINAL")}</strong><span>${Number(r.proximity||r.confidence||0).toFixed(0)}%</span></div><div class="vo-radar-bar"><span style="width:${Math.max(0,Math.min(100,Number(r.proximity||0)))}%"></span></div><div class="vo-radar-meta"><span>Preço <b>${r.price!=null?Number(r.price).toFixed(5):"—"}</b></span><span>Indicadores <b>${Number(r.indicatorCount||0)}</b></span><span>Biquote <b>${Number(r.newsCount||0)}</b></span></div></article>`).join("")||"<div class=\"vo-empty\">Nenhum par retornou dados suficientes.</div>";if(status)status.textContent=`✓ ${d.totalAnalyzed||0} pares processados pelo market-insight-ai.`;grid.querySelectorAll("[data-pair]").forEach(el=>el.addEventListener("click",()=>{const sel=document.getElementById("guruIqPair");if(sel&&[...sel.options].some(o=>o.value===el.dataset.pair))sel.value=el.dataset.pair;switchVoTab("analysis");setTimeout(analyze,0);}));}catch(e){grid.innerHTML="<div class=\"vo-empty\">⚠️ "+esc(e.message)+"</div>";if(status)status.textContent="⚠️ "+e.message;}finally{if(btn){btn.disabled=false;btn.textContent="🔎 Atualizar radar";}}}
  function switchVoTab(tab){const map={analysis:"voPanelAnalysis",strategies:"voPanelStrategies",radar:"voPanelRadar",facts:"voPanelFacts",indicators:"voPanelIndicators"};document.querySelectorAll(".vo-tab").forEach(b=>b.classList.toggle("active",b.dataset.voTab===tab));Object.entries(map).forEach(([k,id])=>document.getElementById(id)?.classList.toggle("active",k===tab));if(tab==="strategies")renderStrategyEditor();if(tab==="facts")loadFacts();if(tab==="radar"&&!document.getElementById("voRadarGrid")?.children.length)loadRadar();if(tab==="indicators")renderIndicatorsFromLast();}
  async function analyze(){
    const result=document.getElementById("guruIqResult"),
      msg=document.getElementById("guruIqMessage"),
      btn=document.getElementById("guruIqAnalyzeBtn"),
      symbol=document.getElementById("guruIqPair")?.value,
      expiry=Number(document.getElementById("guruIqExpiry")?.value||1),
      strategy=document.getElementById("guruIqStrategy")?.value||"automatica";
    if(!symbol || btn?.disabled)return;
    const profiles=profileForRequest();
    const runId=++monitorRunId;
    monitoring=true;
    setMonitoringUI(true);
    if(msg){msg.hidden=true;msg.textContent="";}
    if(result)result.innerHTML=monitorStatusHtml(symbol);
    startMonitorUiTicker();
    try{
      while(monitoring&&runId===monitorRunId){
        monitorRequestStartedAt=Date.now();
        let timeoutId=0;
        try{
          const controller=new AbortController();
          timeoutId=setTimeout(()=>controller.abort(),9000);
          const d=await jsonResponse(await iqFetch("/market-analysis",{
            method:"POST",
            signal:controller.signal,
            body:JSON.stringify({
              symbol,
              timeframe:expiry===1?"1m":expiry===5?"5m":"15m",
              strategy,
              expiry_minutes:expiry,
              indicator_ids_by_strategy:profiles
            })
          }));
          const a=d.analysis||{};
          lastCompletedAnalysis=a;
          monitorCurrentAnalysis=a;
          monitorLastUpdateAt=Date.now();
          const phase=monitoringLabel(a);
          if(phase==="EXECUTE A OPERAÇÃO"&&a.signalConfirmed===true&&(a.signal==="CALL"||a.signal==="PUT")){
            monitoring=false;
            setMonitoringUI(false);
            stopMonitorUiTicker();
            if(result){
              result.innerHTML=resultHtml(a);
              document.getElementById("guruNewAnalysis")?.addEventListener("click",analyze);
            }
            return;
          }
          updateMonitorView(a,phase,monitoringDetail(a,phase));
        }catch(e){
          if(e?.name!=="AbortError"&&msg){
            msg.hidden=false;
            msg.textContent="⚠️ "+e.message;
          }
        }finally{
          if(timeoutId)clearTimeout(timeoutId);
          monitorRequestStartedAt=0;
        }
        if(!monitoring||runId!==monitorRunId)break;
        monitorNextPollAt=Date.now()+1000;
        await sleep(1000);
      }
    }catch(_){}
  }
function bindConnected(){document.getElementById("guruIqAnalyzeBtn")?.addEventListener("click",analyze);document.getElementById("iqRefreshAssets")?.addEventListener("click",refreshAssets);document.getElementById("iqLogout")?.addEventListener("click",()=>logout(true));document.getElementById("guruIqCancelBtn")?.addEventListener("click",()=>{monitoring=false;monitorRunId++;stopMonitorUiTicker();setMonitoringUI(false);const r=document.getElementById("guruIqResult");if(r)r.innerHTML="<div class=\"guru-empty card\"><div class=\"guru-empty-icon\">◈</div><strong>Análise cancelada</strong><span>Selecione o par e a estratégia para iniciar novamente.</span></div>";});document.querySelectorAll("[data-vo-tab]").forEach(btn=>btn.addEventListener("click",()=>switchVoTab(btn.dataset.voTab)));document.getElementById("voRadarRun")?.addEventListener("click",loadRadar);document.getElementById("voFactsRun")?.addEventListener("click",loadFacts);document.getElementById("voMarkAll")?.addEventListener("click",()=>configureProfileAll(true));document.getElementById("voClearAll")?.addEventListener("click",()=>configureProfileAll(false));document.getElementById("voRestoreDefault")?.addEventListener("click",restoreDefaultProfile);document.getElementById("voSaveProfile")?.addEventListener("click",saveAllProfiles);document.getElementById("guruIqPair")?.addEventListener("change",()=>{const src=document.getElementById("guruIqPair"),dst=document.getElementById("voFactsPair");if(src&&dst&&[...dst.options].some(o=>o.value===src.value))dst.value=src.value;});}
  async function renderRoute(){const hash=location.hash||"";if(!hash.includes("/ferramenta/"+TOOL_ID)){monitoring=false;monitorRunId++;stopMonitorUiTicker();document.body.classList.remove("iq-tool-active");return;}document.body.classList.add("iq-tool-active");if(!document.getElementById("visaoOpcoesToolHost")){setTimeout(renderRoute,0);return;}if(sessionStorage.getItem(SESSION_KEY))await renderConnected();else renderLogin();document.title="VISÃO OPÇÕES | Resolvei";window.scrollTo({top:0,behavior:"auto"});}
  function boot(){renderRoute();window.addEventListener("hashchange",()=>setTimeout(renderRoute,0));}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot);else boot();
})();