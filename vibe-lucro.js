(() => {
  "use strict";

  const API = "/api/vibe-lucro";
  const SESSION_KEY = "resolvei_vibe_lucro_session";
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[char]));
  const money = value => Number.isFinite(Number(value))
    ? Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 6 })
    : "—";
  const sid = () => sessionStorage.getItem(SESSION_KEY) || "";
  let loadedAssets = [];
  let activeAnalysis = null;
  let loading = false;

  async function request(path, options = {}, token = sid()) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (token) headers["X-IQ-Session"] = token;
    let response;
    try {
      response = await fetch(API + path, { ...options, headers });
    } catch (error) {
      if (error instanceof TypeError) throw new Error("Não foi possível acessar o servidor do Resolvei.");
      throw error;
    }
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (response.status === 401 && path !== "/login") {
      sessionStorage.removeItem(SESSION_KEY);
    }
    if (!response.ok) throw new Error(data.detail || "Falha ao consultar o VIBE LUCRO.");
    return data;
  }

  function loginShell(message = "") {
    return '<section class="vl-login">' +
      '<div class="vl-brand-mark">VL</div><span class="vl-eyebrow">RESOLVEI · INVESTIMENTOS</span>' +
      '<h1>VIBE <span>LUCRO</span></h1>' +
      '<p>Conecte a IQ Option diretamente nesta ferramenta. Esta conexão é independente das demais ferramentas do Resolvei.</p>' +
      '<form id="vlLoginForm" class="vl-login-form">' +
      '<label>E-MAIL DA IQ OPTION<input id="vlEmail" type="email" autocomplete="username" required placeholder="seu@email.com"></label>' +
      '<label>SENHA DA IQ OPTION<input id="vlPassword" type="password" autocomplete="current-password" required placeholder="Sua senha"></label>' +
      '<button id="vlLoginButton" class="vl-primary-link" type="submit">CONECTAR AO VIBE LUCRO</button>' +
      '</form>' +
      '<div id="vlLoginMessage" class="vl-error" role="status">' + esc(message) + '</div>' +
      '<p class="vl-footnote">As credenciais são usadas somente para abrir esta sessão temporária. Não são salvas no Resolvei. O VIBE LUCRO não compartilha nem encerra o login das outras ferramentas.</p>' +
      '</section>';
  }

  function bindLogin() {
    $("vlLoginForm")?.addEventListener("submit", async event => {
      event.preventDefault();
      const button = $("vlLoginButton");
      const message = $("vlLoginMessage");
      const email = $("vlEmail")?.value.trim() || "";
      const password = $("vlPassword")?.value || "";
      if (!email || !password) {
        if (message) message.textContent = "Informe o e-mail e a senha da IQ Option.";
        return;
      }
      if (button) { button.disabled = true; button.textContent = "CONECTANDO…"; }
      if (message) message.textContent = "";
      try {
        const result = await request("/login", {
          method: "POST",
          body: JSON.stringify({ email, password })
        }, "");
        if (!result.session_id) throw new Error("O servidor não devolveu o token exclusivo do VIBE LUCRO.");
        sessionStorage.setItem(SESSION_KEY, result.session_id);
        await render();
      } catch (error) {
        if (message) message.textContent = "⚠️ " + error.message;
      } finally {
        if ($("vlLoginButton")) {
          $("vlLoginButton").disabled = false;
          $("vlLoginButton").textContent = "CONECTAR AO VIBE LUCRO";
        }
      }
    });
  }

  async function logout() {
    const token = sid();
    try {
      if (token) await request("/logout", { method: "POST" }, token);
    } catch (_) {
      // Always clear only the local VIBE LUCRO token, even after a server timeout.
    }
    sessionStorage.removeItem(SESSION_KEY);
    activeAnalysis = null;
    render();
  }

  function assetOptions() {
    const normal = loadedAssets.filter(item => item.market !== "OTC");
    const otc = loadedAssets.filter(item => item.market === "OTC");
    const renderGroup = (label, rows) => rows.length
      ? '<optgroup label="' + label + '">' + rows.map(item =>
          '<option value="' + esc(item.symbol) + '">' + esc(item.symbol) + '</option>'
        ).join("") + '</optgroup>' : "";
    return renderGroup("MERCADO NORMAL", normal) + renderGroup("MERCADO OTC", otc);
  }

  function shell(status, vibeStatus = {}) {
    return '<div class="vl-app">' +
      '<header class="vl-header"><div><span class="vl-eyebrow">RESOLVEI · IQ OPTION · SOMENTE LEITURA</span>' +
      '<h1>VIBE <span>LUCRO</span></h1><p>Leitura multi-timeframe e pontos de atenção para opções de 1, 5 ou 15 minutos.</p></div>' +
      '<div class="vl-connection"><i></i><span>SESSÃO EXCLUSIVA · IQ OPTION</span><button id="vlRefreshAssets" type="button">↻ ATUALIZAR</button><button id="vlLogout" type="button">SAIR</button></div></header>' +
      '<section class="vl-controls">' +
      '<label>ATIVO<select id="vlSymbol">' + assetOptions() + '</select></label>' +
      '<label>EXPIRAÇÃO<select id="vlExpiry"><option value="1">1 minuto</option><option value="5" selected>5 minutos</option><option value="15">15 minutos</option></select></label>' +
      '<button id="vlAnalyze" class="vl-action" type="button">⌁ ANALISAR MERCADO</button>' +
      '</section>' +
      '<div id="vlStatus" class="vl-status" role="status">' + esc(status || "Conexão validada. Escolha o ativo e a expiração.") + '</div>' +
      '<div id="vlResult" class="vl-result"><section class="vl-placeholder"><span>◉</span><strong>Aguardando análise</strong><p>O motor vai comparar tendência, momentum, price action e contexto dos três períodos.</p></section></div>' +
      '<div id="vlInsightState" class="vl-agent-state"><span class="vl-agent-dot"></span><div><strong>Motor quantitativo VIBE LUCRO</strong><small>' + esc(vibeStatus.message || "Motor local ativo. A IA Vibe-Trading pode ser conectada como revisão complementar.") + '</small></div></div>' +
      '<p class="vl-disclaimer">A ferramenta somente lê candles e apresenta análises. Não envia ordens, não movimenta saldo e não garante resultados. O score mede confluência técnica, não probabilidade de acerto.</p>' +
      '</div>';
  }

  function directionName(value) {
    return value > 0 ? "ALTA" : value < 0 ? "BAIXA" : "NEUTRO";
  }

  function directionClass(value) {
    return value > 0 ? "up" : value < 0 ? "down" : "neutral";
  }

  function renderAnalysis(data) {
    const target = $("vlResult");
    if (!target) return;
    const signal = data.signal || "WAIT";
    const side = signal === "CALL" ? "call" : signal === "PUT" ? "put" : "wait";
    const label = signal === "CALL" ? "COMPRA · CALL" : signal === "PUT" ? "VENDA · PUT" : "AGUARDAR";
    const score = Math.max(0, Math.min(100, Number(data.score) || 0));
    const tf = data.timeframes || {};
    const rows = ["1m", "5m", "15m"].map(timeframe => {
      const item = tf[timeframe] || {};
      return '<div class="vl-tf-row"><b>' + timeframe.toUpperCase() + '</b>' +
        '<span class="' + directionClass(item.trend) + '">' + directionName(item.trend) + '</span>' +
        '<span>RSI ' + (item.rsi14 == null ? "—" : Number(item.rsi14).toFixed(1)) + '</span>' +
        '<span>' + (item.fresh ? "DADOS ATUAIS" : "DADOS ANTIGOS") + '</span></div>';
    }).join("");
    const votes = (data.votes || []).map(vote => {
      const cls = vote.direction === "CALL" ? "up" : vote.direction === "PUT" ? "down" : "neutral";
      return '<div class="vl-vote"><span>' + esc(vote.name) + '</span><strong class="' + cls + '">' +
        esc(vote.direction) + '</strong><small>' + Number(vote.weight || 0) + ' pts</small></div>';
    }).join("");
    const reasons = (data.reasons || []).map(reason => '<li>' + esc(reason) + '</li>').join("");
    const quality = data.data_quality || {};
    target.innerHTML =
      '<section class="vl-summary ' + side + '">' +
        '<div class="vl-summary-top"><span>' + esc(data.symbol || "—") + '</span><span>EXPIRAÇÃO ' + Number(data.expiry_minutes || 0) + ' MIN</span></div>' +
        '<div class="vl-signal-label">' + label + '</div>' +
        '<div class="vl-score"><strong>' + score + '</strong><span>/100</span></div>' +
        '<div class="vl-meter"><i style="width:' + score + '%"></i></div>' +
        '<p>' + (signal === "WAIT" ? "As condições ainda não justificam uma indicação direcional." : "Confluência técnica identificada. Confirme a atualidade antes de tomar qualquer decisão.") + '</p>' +
      '</section>' +
      '<div class="vl-metrics">' +
        '<article><small>PREÇO DE REFERÊNCIA</small><strong>' + money(data.entry_reference_price) + '</strong><span>Último fechamento do gatilho</span></article>' +
        '<article><small>PERÍODO DO GATILHO</small><strong>' + esc(String(data.trigger_timeframe || "—").toUpperCase()) + '</strong><span>Janela de validade estimada: ' + Number(data.valid_for_seconds || 0) + 's</span></article>' +
        '<article><small>VOTOS</small><strong class="up">' + Number(data.buy_score || 0) + ' CALL</strong><span class="down">' + Number(data.sell_score || 0) + ' PUT</span></article>' +
      '</div>' +
      '<section class="vl-panel"><div class="vl-panel-head"><div><small>CONTEXTO DO MERCADO</small><h2>Leitura dos candles</h2></div><span class="' + (quality.fresh ? "vl-tag-ok" : "vl-tag-warn") + '">' + (quality.fresh ? "DADOS ATUAIS" : "DADOS DESATUALIZADOS") + '</span></div>' +
        '<div class="vl-tf-table">' + rows + '</div></section>' +
      '<section class="vl-panel"><div class="vl-panel-head"><div><small>CONFLUÊNCIA</small><h2>Grupos de confirmação</h2></div></div><div class="vl-votes">' + votes + '</div></section>' +
      '<section class="vl-panel vl-reasons"><div class="vl-panel-head"><div><small>JUSTIFICATIVA</small><h2>Por que o motor chegou a esse estado</h2></div></div><ul>' + reasons + '</ul></section>' +
      (data.vibe_trading_review && data.vibe_trading_review.available
        ? '<section class="vl-panel vl-ai-review"><div class="vl-panel-head"><div><small>VIBE-TRADING · REVISÃO DE IA</small><h2>Segunda leitura independente</h2></div><span class="vl-tag-ok">CONECTADO</span></div><div class="vl-ai-review-text">' + esc(data.vibe_trading_review.review) + '</div><small>' + esc(data.vibe_trading_review.message || "Revisão complementar, sem alterar o sinal quantitativo.") + '</small></section>'
        : (data.vibe_trading_review && data.vibe_trading_review.configured
          ? '<section class="vl-panel vl-ai-review"><div class="vl-panel-head"><div><small>VIBE-TRADING · REVISÃO DE IA</small><h2>Segunda leitura indisponível</h2></div><span class="vl-tag-warn">INDISPONÍVEL</span></div><p>' + esc(data.vibe_trading_review.message || "A revisão de IA não respondeu.") + '</p></section>'
          : '<section class="vl-panel vl-ai-review"><div class="vl-panel-head"><div><small>VIBE-TRADING · REVISÃO DE IA</small><h2>Integração complementar</h2></div><span class="vl-tag-warn">NÃO CONFIGURADA</span></div><p>O motor quantitativo local continua funcionando. A segunda leitura por IA será ativada quando o endpoint protegido do Vibe-Trading estiver instalado e configurado.</p></section>')) +
      '<div class="vl-result-foot">Análise concluída em ' + new Date(Number(data.analysis_time || Date.now() / 1000) * 1000).toLocaleTimeString("pt-BR") +
        ' · ' + Number(data.timeframes?.["1m"]?.candles || 0) + ' candles M1 · ' + (quality.fresh ? "sem períodos atrasados" : "há períodos atrasados") + '</div>';
  }

  async function loadAssets() {
    const result = await request("/assets");
    loadedAssets = [...(result.normal || []), ...(result.otc || [])];
    return result;
  }

  async function analyzeNow() {
    if (loading) return;
    const button = $("vlAnalyze");
    const status = $("vlStatus");
    const symbol = $("vlSymbol")?.value || "";
    const expiry = Number($("vlExpiry")?.value || 5);
    if (!symbol) {
      if (status) status.textContent = "Selecione um ativo disponível na IQ Option.";
      return;
    }
    loading = true;
    if (button) { button.disabled = true; button.textContent = "⏳ ANALISANDO CANDLES…"; }
    if (status) status.textContent = "Consultando candles M1, M5 e M15 e calculando confluência.";
    try {
      const result = await request("/analyze", {
        method: "POST",
        body: JSON.stringify({ symbol, expiry_minutes: expiry })
      });
      activeAnalysis = result.analysis;
      renderAnalysis(activeAnalysis);
      if (status) status.textContent = result.analysis.signal === "WAIT"
        ? "Análise concluída: AGUARDAR. Os filtros não confirmaram uma direção."
        : "Análise concluída: " + result.analysis.signal + ". Não há execução automática.";
    } catch (error) {
      if (status) status.textContent = "⚠️ " + error.message;
    } finally {
      loading = false;
      if ($("vlAnalyze")) { $("vlAnalyze").disabled = false; $("vlAnalyze").textContent = "⌁ ANALISAR MERCADO"; }
    }
  }

  async function render() {
    const host = $("vibeLucroToolHost");
    if (!host) return;
    loading = false;
    if (!sid()) {
      host.innerHTML = loginShell();
      bindLogin();
      return;
    }
    try {
      const connectionStatus = await request("/status");
      await loadAssets();
      host.innerHTML = shell(
        "Sessão própria do VIBE LUCRO reconhecida. As outras ferramentas não são afetadas.",
        connectionStatus.vibe_trading_agent || {}
      );
      $("vlSymbol").innerHTML = assetOptions();
      if ([...$("vlSymbol").options].some(option => option.value === "EURUSD")) $("vlSymbol").value = "EURUSD";
      $("vlAnalyze")?.addEventListener("click", analyzeNow);
      $("vlLogout")?.addEventListener("click", logout);
      $("vlRefreshAssets")?.addEventListener("click", async () => {
        const status = $("vlStatus");
        if (status) status.textContent = "Atualizando catálogo da IQ Option…";
        try {
          await loadAssets();
          if ($("vlSymbol")) $("vlSymbol").innerHTML = assetOptions();
          if (status) status.textContent = "Catálogo de ativos atualizado.";
        } catch (error) {
          if (status) status.textContent = "⚠️ " + error.message;
        }
      });
    } catch (error) {
      host.innerHTML = loginShell(error.message);
      if (!sid()) bindLogin();
    }
  }

  function isRoute() {
    return (location.hash || "").includes("/ferramenta/vibe-lucro");
  }

  function boot() {
    if (isRoute()) render();
    window.addEventListener("hashchange", () => {
      if (isRoute()) render();
      else { loading = false; activeAnalysis = null; }
    });
  }

  window.renderVibeLucro = render;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
