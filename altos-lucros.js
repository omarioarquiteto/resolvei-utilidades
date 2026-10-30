(() => {
  const API = "/api/altos-lucros";
  const IQ_API = "/api/trade-pro";
  // Compartilha a mesma sessão temporária de IQ Option já usada pelo TRADE-PRÓ.
  const KEY = "resolvei_trade_pro_session";
  let busy = false;
  const $ = id => document.getElementById(id);
  const sid = () => sessionStorage.getItem(KEY) || "";
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;"
  }[ch]));
  const price = value => Number(value).toLocaleString("pt-BR", {
    minimumFractionDigits: 2, maximumFractionDigits: 8
  });
  const pct = value => Number(value).toLocaleString("pt-BR", {
    minimumFractionDigits: 1, maximumFractionDigits: 1
  }) + "%";

  async function call(base, path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (sid()) headers["X-IQ-Session"] = sid();
    let response;
    try {
      response = await fetch(base + path, { ...options, headers });
    } catch (_) {
      throw new Error("Não foi possível alcançar a API do Resolvei. Verifique a conexão.");
    }
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      if (response.status === 401) sessionStorage.removeItem(KEY);
      throw new Error((data && data.detail) || ("API HTTP " + response.status));
    }
    return data || {};
  }

  function login() {
    const host = $("altosLucrosToolHost");
    if (!host) return;
    host.innerHTML =
      '<div class="al-login">' +
        '<small>RESOLVEI / IQ OPTION DIGITAL</small>' +
        '<div class="al-brand-mark">↗</div>' +
        '<h1>ALTOS <span>LUCROS</span></h1>' +
        '<p>Conecte sua conta IQ Option para consultar os candles e a grade real de strikes e payouts digitais. A senha não é armazenada.</p>' +
        '<form id="alLoginForm">' +
          '<label>E-MAIL IQ OPTION<input id="alEmail" type="email" autocomplete="username" required></label>' +
          '<label>SENHA IQ OPTION<input id="alPassword" type="password" autocomplete="current-password" required></label>' +
          '<button id="alLoginBtn" type="submit">CONECTAR À IQ OPTION</button>' +
        '</form>' +
        '<div id="alLoginMsg" role="status"></div>' +
        '<p class="al-login-note">Somente leitura e análise estatística. Nenhuma ordem será enviada.</p>' +
      '</div>';
    $("alLoginForm").onsubmit = async event => {
      event.preventDefault();
      const button = $("alLoginBtn");
      const message = $("alLoginMsg");
      button.disabled = true;
      button.textContent = "CONECTANDO…";
      message.textContent = "";
      try {
        const data = await call(IQ_API, "/login", {
          method: "POST",
          body: JSON.stringify({
            email: $("alEmail").value.trim(),
            password: $("alPassword").value
          })
        });
        sessionStorage.setItem(KEY, data.session_id);
        await render();
      } catch (error) {
        message.textContent = "⚠️ " + error.message;
      } finally {
        if ($("alLoginBtn")) {
          $("alLoginBtn").disabled = false;
          $("alLoginBtn").textContent = "CONECTAR À IQ OPTION";
        }
      }
    };
  }

  function shell() {
    const host = $("altosLucrosToolHost");
    if (!host) return;
    host.innerHTML =
      '<div class="al-app">' +
        '<header class="al-header">' +
          '<div><small>RESOLVEI / DIGITAL OPTIONS ANALYTICS</small><h1>ALTOS <span>LUCROS</span></h1>' +
          '<p>Seleção estatística de strikes com payout real de 200% ou mais</p></div>' +
          '<div class="al-head-actions"><b><i></i> IQ OPTION CONECTADA</b><button id="alLogout" type="button">SAIR</button></div>' +
        '</header>' +
        '<section class="al-config">' +
          '<label>ATIVO DIGITAL<select id="alSymbol"><option value="">Carregando ativos…</option></select></label>' +
          '<label>VENCIMENTO<select id="alHorizon"><option value="5">5 minutos</option><option value="15">15 minutos</option></select></label>' +
          '<div class="al-payout-floor"><small>PAYOUT MÍNIMO</small><strong>200%</strong><span>Somente strikes elegíveis</span></div>' +
          '<button id="alAnalyze" type="button">ANALISAR ALVOS</button>' +
        '</section>' +
        '<section class="al-toolbar"><span id="alStatus">Carregando ativos da IQ Option…</span><span id="alFreshness">Candles M1: aguardando análise</span></section>' +
        '<section id="alResult" class="al-result">' +
          '<article class="al-card al-empty"><small>ANÁLISE ESTATÍSTICA</small><strong>Aguardando consulta</strong><p>Selecione o ativo e o vencimento para procurar strikes com payout mínimo de 200%.</p></article>' +
        '</section>' +
        '<section class="al-method">' +
          '<div><small>CRITÉRIO DE APROVAÇÃO</small><h2>Probabilidade acima do ponto de equilíbrio</h2>' +
          '<p>O sistema compara o payout real de cada strike com a frequência histórica de candles M1 que fecharam além do mesmo deslocamento no vencimento. Usa janelas não sobrepostas e o limite inferior de confiança de 90%.</p></div>' +
          '<div class="al-method-rule"><b>+200%</b><span>payout mínimo</span><b>+5 p.p.</b><span>margem mínima sobre o breakeven</span><b>30</b><span>amostras históricas mínimas</span></div>' +
        '</section>' +
        '<p class="al-disclaimer">ALTOS LUCROS é uma ferramenta experimental de análise, não uma promessa ou garantia de resultado. A estimativa histórica não prevê o próximo candle, pode mudar com o mercado e não considera todos os fatores de execução, latência ou alterações de payout. O módulo somente lê dados e não executa operações.</p>' +
      '</div>';
  }

  async function loadAssets() {
    const select = $("alSymbol");
    if (!select) return;
    const data = await call(API, "/assets");
    const assets = Array.isArray(data.assets) ? data.assets : [];
    if (!assets.length) throw new Error("A IQ Option não retornou ativos nesta sessão.");
    select.innerHTML = assets.map(asset =>
      '<option value="' + esc(asset.symbol) + '">' + esc(asset.symbol) + '</option>'
    ).join("");
    const preferred = assets.find(asset => /^EURUSD(?:-OTC)?$/i.test(asset.symbol))
      || assets.find(asset => /EURUSD/i.test(asset.symbol))
      || assets[0];
    select.value = preferred.symbol;
    $("alStatus").textContent = assets.length + " ativos no catálogo · atualização " +
      new Date().toLocaleTimeString("pt-BR");
  }

  function candidateTable(candidates) {
    if (!Array.isArray(candidates) || !candidates.length) {
      return '<div class="al-empty-note">Nenhum strike com payout mínimo de 200% e amostra suficiente foi disponibilizado nesta consulta.</div>';
    }
    return '<div class="al-table-wrap"><table class="al-table"><thead><tr>' +
      '<th>Direção</th><th>Alvo</th><th>Payout</th><th>Histórico</th><th>Limite 90%</th><th>EV conservador</th>' +
      '</tr></thead><tbody>' + candidates.map(item =>
        '<tr class="' + (item.statistically_valid ? "al-row-valid" : "") + '">' +
          '<td><b>' + esc(item.direction) + '</b></td>' +
          '<td>' + price(item.target_price) + '</td>' +
          '<td>' + pct(item.payout_percent) + '</td>' +
          '<td>' + pct(item.probability_percent) + ' <small>(' + item.successes + '/' + item.samples + ')</small></td>' +
          '<td>' + pct(item.confidence_low_percent) + '</td>' +
          '<td>' + (Number(item.conservative_expected_value_percent) > 0 ? "+" : "") +
            pct(item.conservative_expected_value_percent) + '</td>' +
        '</tr>'
      ).join("") + '</tbody></table></div>';
  }

  function show(data) {
    const result = $("alResult");
    const freshness = $("alFreshness");
    const quality = data.data_quality || {};
    if (freshness) {
      freshness.textContent = "Último candle fechado há " +
        Math.round(Number(quality.last_candle_age_seconds) || 0) + " s · " +
        (quality.valid_closed_candles || 0) + " candles M1 válidos";
    }
    const valid = data.status === "ALVO_VALIDADO" && data.recommendation;
    const candidate = data.recommendation || data.best_candidate;
    const heading = valid ? "ALVO ESTATISTICAMENTE VALIDADO" : "SEM OPORTUNIDADE VÁLIDA";
    const direction = candidate ? candidate.direction : "—";
    const hero =
      '<article class="al-card al-hero ' + (valid ? "al-approved" : "al-blocked") + '">' +
        '<div class="al-hero-copy"><small>' + (valid ? "CENÁRIO ELEGÍVEL" : "DECISÃO DO MOTOR") + '</small>' +
          '<strong>' + heading + '</strong><p>' + esc(data.message || "Não foi possível validar um alvo.") + '</p></div>' +
        (candidate ?
          '<div class="al-target"><small>ALVO DIGITAL ' + esc(direction) + '</small><b>' + price(candidate.target_price) + '</b>' +
          '<span>Payout IQ Option: ' + pct(candidate.payout_percent) + '</span></div>' :
          '<div class="al-target al-no-target"><small>ALVO</small><b>—</b><span>Nenhum strike elegível</span></div>') +
      '</article>';
    const metrics = candidate ?
      '<section class="al-metrics">' +
        '<article class="al-card"><small>PROBABILIDADE HISTÓRICA</small><strong>' + pct(candidate.probability_percent) + '</strong><span>' + candidate.successes + ' acertos em ' + candidate.samples + ' janelas</span></article>' +
        '<article class="al-card"><small>LIMITE INFERIOR · 90%</small><strong>' + pct(candidate.confidence_low_percent) + '</strong><span>Estimativa conservadora usada no filtro</span></article>' +
        '<article class="al-card"><small>PONTO DE EQUILÍBRIO</small><strong>' + pct(candidate.breakeven_probability_percent) + '</strong><span>Probabilidade necessária para EV zero</span></article>' +
        '<article class="al-card"><small>EV CONSERVADOR</small><strong class="' + (candidate.conservative_expected_value_percent > 0 ? "al-positive" : "al-negative") + '">' +
          (candidate.conservative_expected_value_percent > 0 ? "+" : "") + pct(candidate.conservative_expected_value_percent) +
        '</strong><span>Por 100% de stake teórica, antes de custos</span></article>' +
      '</section>' : '';
    const context =
      '<section class="al-card al-context"><div><small>CONTEXTO DO MERCADO</small><strong>' +
        esc(data.market_bias || "—") + '</strong><span>EMA20 ' + price(data.ema20 || 0) +
        ' · EMA50 ' + price(data.ema50 || 0) + '</span></div><div><small>PREÇO ATUAL</small><strong>' +
        price(data.symbol_price || 0) + '</strong><span>' + esc(data.symbol || "") +
        ' · horizonte de ' + esc(data.horizon_minutes) + ' min</span></div><div><small>FILTRO ESTATÍSTICO</small><strong>' +
        (valid ? "APROVADO" : "REPROVADO") + '</strong><span>Margem mínima de 5 p.p. sobre o breakeven</span></div></section>';
    result.innerHTML = hero + metrics + context +
      '<section class="al-card al-candidates"><div class="al-section-title"><div><small>GRADE DE STRIKES</small><h2>Melhores alvos elegíveis</h2></div>' +
      '<span>Somente payout ≥ 200%</span></div>' + candidateTable(data.candidates) + '</section>' +
      '<div class="al-result-footnote">A estimativa mede o fechamento no vencimento além do strike. Um toque do preço durante o período, seguido de retorno antes da expiração, não conta como acerto. A probabilidade é histórica e não garante o próximo resultado.</div>';
  }

  async function analyze() {
    if (busy) return;
    const symbol = $("alSymbol")?.value || "";
    const horizon = Number($("alHorizon")?.value || 5);
    if (!symbol) {
      $("alStatus").textContent = "Selecione um ativo no catálogo.";
      return;
    }
    busy = true;
    const button = $("alAnalyze");
    button.disabled = true;
    button.textContent = "ANALISANDO…";
    $("alStatus").textContent = "Lendo candles M1 e payouts digitais reais…";
    try {
      const data = await call(API, "/analyze", {
        method: "POST",
        body: JSON.stringify({ symbol, horizon_minutes: horizon })
      });
      show(data);
      $("alStatus").textContent = symbol + " · vencimento " + horizon +
        " min · consulta " + new Date(data.timestamp || Date.now()).toLocaleTimeString("pt-BR");
    } catch (error) {
      $("alStatus").textContent = "⚠️ " + error.message;
    } finally {
      busy = false;
      if ($("alAnalyze")) {
        $("alAnalyze").disabled = false;
        $("alAnalyze").textContent = "ANALISAR ALVOS";
      }
    }
  }

  async function render() {
    const host = $("altosLucrosToolHost");
    if (!host) return;
    if (!sid()) {
      login();
      return;
    }
    try {
      await call(IQ_API, "/session");
    } catch (_) {
      login();
      return;
    }
    shell();
    $("alLogout").onclick = async () => {
      try { await call(IQ_API, "/logout", { method: "POST" }); } catch (_) {}
      sessionStorage.removeItem(KEY);
      login();
    };
    $("alAnalyze").onclick = analyze;
    try {
      await loadAssets();
    } catch (error) {
      $("alStatus").textContent = "⚠️ " + error.message;
    }
  }

  function isRoute() {
    const path = location.pathname.match(/ferramenta\/([^/]+)/)?.[1];
    const hash = location.hash.match(/ferramenta\/([^?]+)/)?.[1];
    return path === "altos-lucros" || hash === "altos-lucros";
  }
  function boot() {
    if (isRoute()) render();
  }
  window.renderAltosLucros = render;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  window.addEventListener("hashchange", boot);
})();
