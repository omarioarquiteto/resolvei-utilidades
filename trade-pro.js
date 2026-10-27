(() => {
  const API = "/api/trade-pro";
  const KEY = "resolvei_trade_pro_session";
  let timer = null;
  let busy = false;
  let lastUiSignalKey = "";
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;"
  }[ch]));
  const sid = () => sessionStorage.getItem(KEY) || "";
  const clearSession = () => sessionStorage.removeItem(KEY);

  async function call(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (sid()) headers["X-IQ-Session"] = sid();
    let response;
    try {
      response = await fetch(API + path, { ...options, headers });
    } catch (error) {
      throw new Error("Não foi possível alcançar a API do TRADE-PRÓ. Verifique a conexão com o Resolvei.");
    }
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      if (response.status === 401) clearSession();
      throw new Error((data && data.detail) || ("API HTTP " + response.status));
    }
    return data || {};
  }

  function stopAuto() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  function login() {
    stopAuto();
    const host = $("tradeProToolHost");
    if (!host) return;
    host.innerHTML =
      '<div class="tp-login">' +
        '<small>RESOLVEI / IQ OPTION</small>' +
        '<h1>TRADE<span>-PRÓ</span></h1>' +
        '<p>Conecte sua conta IQ Option para carregar candles e gerar análises. A sessão é exclusiva desta ferramenta; a senha não fica salva no navegador.</p>' +
        '<form id="tpLoginForm">' +
          '<label>E-MAIL IQ OPTION<input id="tpEmail" type="email" autocomplete="username" required></label>' +
          '<label>SENHA IQ OPTION<input id="tpPassword" type="password" autocomplete="current-password" required></label>' +
          '<button id="tpLoginBtn" type="submit">CONECTAR À IQ OPTION</button>' +
        '</form>' +
        '<div id="tpLoginMsg" role="status"></div>' +
        '<p class="tp-login-note">Módulo somente analítico: não envia ordens nem movimenta saldo.</p>' +
      '</div>';

    $("tpLoginForm").onsubmit = async event => {
      event.preventDefault();
      const button = $("tpLoginBtn");
      const message = $("tpLoginMsg");
      button.disabled = true;
      button.textContent = "CONECTANDO…";
      message.textContent = "";
      try {
        const data = await call("/login", {
          method: "POST",
          body: JSON.stringify({
            email: $("tpEmail").value.trim(),
            password: $("tpPassword").value
          })
        });
        sessionStorage.setItem(KEY, data.session_id);
        await render();
      } catch (error) {
        message.textContent = "⚠️ " + error.message;
      } finally {
        if ($("tpLoginBtn")) {
          $("tpLoginBtn").disabled = false;
          $("tpLoginBtn").textContent = "CONECTAR À IQ OPTION";
        }
      }
    };
  }

  function shell() {
    const host = $("tradeProToolHost");
    if (!host) return;
    host.innerHTML =
      '<div class="tp-app">' +
        '<header class="tp-header">' +
          '<div><small>RESOLVEI / TRADING ANALYTICS</small><h1>TRADE<span>-PRÓ</span></h1>' +
          '<p>Regime de mercado · Confluência · Expiração sugerida</p></div>' +
          '<div class="tp-head-actions"><b><i></i> IQ OPTION</b><button id="tpLogout" type="button">SAIR</button></div>' +
        '</header>' +
        '<section class="tp-config">' +
          '<label class="tp-asset-label">ATIVO (digite para filtrar)' +
            '<input id="tpSymbol" list="tpAssetList" autocomplete="off" placeholder="Ex.: EURUSD-OTC" required>' +
            '<datalist id="tpAssetList"></datalist>' +
          '</label>' +
          '<label>TIMEFRAME DOS CANDLES<select id="tpTimeframe"><option value="1m">M1 · 1 minuto</option><option value="5m">M5 · 5 minutos</option><option value="15m">M15 · 15 minutos</option></select></label>' +
          '<button id="tpAnalyze" type="button">ANALISAR AGORA</button>' +
        '</section>' +
        '<section class="tp-toolbar"><span id="tpConnectionStatus">Carregando catálogo de ativos…</span>' +
          '<span id="tpCandleFreshness" class="tp-candle-freshness">Candles: aguardando análise</span>' +
          '<label class="tp-auto"><input id="tpAuto" type="checkbox"> Análise automática a cada 20 s</label></section>' +
        '<section class="tp-summary-grid">' +
          '<article id="tpSignalCard" class="tp-card tp-signal tp-neutral"><small>DECISÃO ATUAL</small><strong id="tpSignal">AGUARDANDO</strong><span id="tpSignalCaption">Selecione um ativo e inicie a análise.</span></article>' +
          '<article class="tp-card tp-confidence"><small>CONFLUÊNCIA</small><div class="tp-score"><b id="tpScore">0</b><span>%</span></div>' +
            '<div class="tp-meter"><i id="tpMeter"></i></div><div class="tp-min-score">LIMIAR MÍNIMO: <b id="tpThreshold">72%</b></div></article>' +
          '<article class="tp-card tp-expiration"><small>EXPIRAÇÃO SUGERIDA</small><strong id="tpExpiration">—</strong><span id="tpExpiryCaption">Calculada pela velocidade e volatilidade.</span></article>' +
        '</section>' +
        '<section class="tp-two-col">' +
          '<article class="tp-card"><div class="tp-section-title"><div><small>CONTEXTO DO MERCADO</small><h2 id="tpRegime">Ainda não analisado</h2></div><span id="tpMode" class="tp-chip">AGUARDANDO</span></div>' +
            '<p id="tpReason" class="tp-reason">A análise verifica tendência, volume e volatilidade em conjunto antes de validar uma entrada.</p>' +
            '<div class="tp-metrics">' +
              '<div><span>ADX</span><b id="tpAdx">—</b></div><div><span>ATR relativo</span><b id="tpAtr">—</b></div>' +
              '<div><span>Volume relativo</span><b id="tpVolume">—</b></div><div><span>Velocidade (ATR)</span><b id="tpVelocity">—</b></div>' +
            '</div>' +
            '<div id="tpChecks" class="tp-checks"></div><div id="tpBlockers" class="tp-blockers" role="status"></div>' +
          '</article>' +
          '<article class="tp-card"><div class="tp-section-title"><div><small>PONTUAÇÃO DA CONFLUÊNCIA</small><h2>Filtros simultâneos</h2></div></div>' +
            '<div class="tp-score-row"><span>Tendência</span><div class="tp-meter"><i id="tpTrendMeter"></i></div><b id="tpTrendScore">0%</b></div>' +
            '<div class="tp-score-row"><span>Volume</span><div class="tp-meter"><i id="tpVolumeMeter"></i></div><b id="tpVolumeScore">0%</b></div>' +
            '<div class="tp-score-row"><span>Volatilidade</span><div class="tp-meter"><i id="tpVolatilityMeter"></i></div><b id="tpVolatilityScore">0%</b></div>' +
            '<p class="tp-small-note">Um score alto, isoladamente, não emite sinal: os três filtros também precisam ser confirmados.</p>' +
          '</article>' +
        '</section>' +
        '<section class="tp-card tp-log-card"><div class="tp-section-title"><div><small>HISTÓRICO DE SINAIS VALIDADOS</small><h2>Registro desta sessão</h2></div><button id="tpClearLog" type="button">LIMPAR</button></div>' +
          '<div id="tpLog" class="tp-log-empty">Nenhum sinal validado nesta sessão. Análises sem confluência não entram no histórico.</div>' +
        '</section>' +
        '<div id="tpError" class="tp-error" role="status"></div>' +
        '<p class="tp-disclaimer">TRADE-PRÓ é uma ferramenta experimental de análise, não uma promessa de resultado. A adaptação do guia CME não transforma estratégias de opções em estratégias equivalentes de opções binárias. A ferramenta somente lê candles e exibe análises; não executa operações.</p>' +
      '</div>';
  }

  async function loadAssets() {
    const input = $("tpSymbol");
    const list = $("tpAssetList");
    if (!input || !list) return;
    $("tpConnectionStatus").textContent = "Carregando catálogo de ativos…";
    try {
      const data = await call("/assets");
      const assets = Array.isArray(data.assets) ? data.assets : [];
      list.innerHTML = assets.map(asset => '<option value="' + esc(asset.symbol) + '"></option>').join("");
      if (!input.value && assets.length) {
        const preferred = assets.find(asset => /-OTC$/i.test(asset.symbol)) || assets.find(asset => /EURUSD/i.test(asset.symbol)) || assets[0];
        input.value = preferred.symbol;
      }
      $("tpConnectionStatus").textContent = assets.length + " ativos no catálogo · atualização " + new Date().toLocaleTimeString("pt-BR");
    } catch (error) {
      $("tpConnectionStatus").textContent = "Não foi possível carregar os ativos.";
      $("tpError").textContent = "⚠️ " + error.message;
      throw error;
    }
  }

  function displayScore(id, value) {
    const numeric = Math.max(0, Math.min(100, Number(value) || 0));
    if ($(id + "Meter")) $(id + "Meter").style.width = numeric + "%";
    if ($(id + "Score")) $(id + "Score").textContent = Math.round(numeric) + "%";
  }

  function addLog(data) {
    if (!data.signal || !["COMPRA", "VENDA"].includes(data.signal)) return;
    const key = [data.symbol, data.timeframe, data.candle_time, data.signal].join("|");
    if (key === lastUiSignalKey) return;
    lastUiSignalKey = key;
    const log = $("tpLog");
    if (!log) return;
    if (log.classList.contains("tp-log-empty")) {
      log.className = "tp-log-list";
      log.innerHTML = "";
    }
    const entry = document.createElement("article");
    entry.className = "tp-log-item " + (data.signal === "COMPRA" ? "tp-log-buy" : "tp-log-sell");
    entry.innerHTML =
      '<div class="tp-log-top"><b>' + esc(new Date(data.timestamp || Date.now()).toLocaleTimeString("pt-BR")) + ' · ' + esc(data.symbol) + '</b>' +
      '<span>' + esc(data.timeframe.toUpperCase()) + '</span></div>' +
      '<div class="tp-log-main"><strong>' + esc(data.signal) + '</strong><b>EXPIRAÇÃO: ' + esc(data.expiration_minutes) + ' MIN</b><b>' + esc(data.confluence) + '%</b></div>' +
      '<p>' + esc(data.reason) + '</p>';
    log.prepend(entry);
    while (log.children.length > 20) log.lastElementChild.remove();
  }

  function show(data) {
    const quality = data.data_quality || {};
    const stale = Boolean(quality.stale || data.status === "DADOS_DESATUALIZADOS");
    const hasSignal = !stale && ["COMPRA", "VENDA"].includes(data.signal);
    const direction = data.signal === "COMPRA" ? "tp-buy" : data.signal === "VENDA" ? "tp-sell" : "tp-neutral";
    $("tpSignalCard").className = "tp-card tp-signal " + direction;
    $("tpSignal").textContent = hasSignal ? data.signal : "SEM SINAL";
    $("tpSignalCaption").textContent = hasSignal
      ? "Sinal validado — " + data.confluence + "% de confluência."
      : stale
        ? "Entrada bloqueada porque os candles estão desatualizados."
        : "Filtros não confirmados simultaneamente. Veja abaixo o que bloqueou a entrada.";
    $("tpScore").textContent = Math.round(Number(data.confluence) || 0);
    $("tpMeter").style.width = Math.max(0, Math.min(100, Number(data.confluence) || 0)) + "%";
    $("tpThreshold").textContent = (data.threshold || 72) + "%";
    $("tpExpiration").textContent = hasSignal ? data.expiration_minutes + " MIN" : "—";
    $("tpExpiryCaption").textContent = hasSignal ? "Estimativa analítica, não uma ordem." : "Indefinida enquanto não houver sinal.";
    $("tpRegime").textContent = data.regime || "Sem classificação";
    $("tpMode").textContent = hasSignal ? "VALIDADO" : stale ? "DADOS ANTIGOS" : (data.regime || "SEM SINAL");
    $("tpMode").className = "tp-chip " + (hasSignal ? "tp-chip-ok" : "tp-chip-muted");
    $("tpReason").textContent = data.reason || "Sem justificativa disponível.";
    const market = data.market || {};
    const freshness = $("tpCandleFreshness");
    if (freshness) {
      if (quality.last_candle_age_seconds == null) {
        freshness.textContent = "Atualidade dos candles: não informada";
        freshness.className = "tp-candle-freshness";
      } else {
        const ageSeconds = Math.round(Number(quality.last_candle_age_seconds) || 0);
        const maximumAge = Number(quality.max_allowed_age_seconds) || 0;
        freshness.textContent = (stale ? "DADOS ANTIGOS" : "Candle atualizado") +
          " · último fechamento há " + ageSeconds + " s" +
          (maximumAge ? " · limite " + maximumAge + " s" : "");
        freshness.className = "tp-candle-freshness " + (stale ? "tp-freshness-stale" : "tp-freshness-ok");
      }
    }
    $("tpAdx").textContent = market.adx == null ? "—" : Number(market.adx).toFixed(1);
    $("tpAtr").textContent = market.atr_ratio == null ? "—" : Number(market.atr_ratio).toFixed(2) + "×";
    $("tpVolume").textContent = market.volume_ratio == null ? "—" : Number(market.volume_ratio).toFixed(2) + "×";
    $("tpVelocity").textContent = market.velocity_atr == null ? "—" : Number(market.velocity_atr).toFixed(2);
    const checkState = data.checks || {};
    const checks = [
      ["direction_detected", "Direção", checkState.direction_detected],
      ["trend_confirmed", "Tendência", market.trend_confirmed],
      ["volume_data_available", "Dados de volume", market.volume_data_available],
      ["volume_confirmed", "Volume", market.volume_confirmed],
      ["volatility_confirmed", "Volatilidade", market.volatility_confirmed],
      ["confluence_confirmed", "Confluência", checkState.confluence_confirmed],
      ["data_fresh", "Atualidade dos candles", !stale]
    ];
    $("tpChecks").innerHTML = checks.map(pair => {
      const ok = Boolean(pair[2]);
      return '<span class="' + (ok ? "tp-check-ok" : "tp-check-no") + '">' + (ok ? "✓ " : "× ") + pair[1] + (ok ? " confirmado" : " não confirmado") + '</span>';
    }).join("");
    const blockers = Array.isArray(data.blocking_reasons) ? data.blocking_reasons : [];
    $("tpBlockers").innerHTML = hasSignal
      ? '<strong>Filtros aprovados.</strong><span>Condições simultâneas confirmadas para este candle. Isso não representa garantia de resultado.</span>'
      : blockers.length
        ? '<strong>Por que não houve sinal</strong><ul>' + blockers.map(item => '<li>' + esc(item) + '</li>').join("") + '</ul>'
        : '<strong>Por que não houve sinal</strong><span>A API não retornou detalhes dos filtros nesta resposta. Execute uma nova análise.</span>';
    const scores = data.scores || {};
    displayScore("tpTrend", scores.trend);
    displayScore("tpVolume", scores.volume);
    displayScore("tpVolatility", scores.volatility);
    $("tpError").textContent = "";
    addLog(data);
  }

  async function analyze() {
    if (busy) return;
    const symbol = $("tpSymbol")?.value.trim();
    const timeframe = $("tpTimeframe")?.value || "1m";
    if (!symbol) {
      $("tpError").textContent = "Selecione um ativo no catálogo.";
      return;
    }
    busy = true;
    const button = $("tpAnalyze");
    if (button) {
      button.disabled = true;
      button.textContent = "ANALISANDO…";
    }
    if ($("tpError")) $("tpError").textContent = "";
    try {
      const data = await call("/analyze", {
        method: "POST",
        body: JSON.stringify({ symbol, timeframe })
      });
      show(data);
      $("tpConnectionStatus").textContent = "Última leitura " + new Date(data.timestamp || Date.now()).toLocaleTimeString("pt-BR") + " · " + symbol;
    } catch (error) {
      $("tpError").textContent = "⚠️ " + error.message;
      if (!sid()) login();
    } finally {
      busy = false;
      if ($("tpAnalyze")) {
        $("tpAnalyze").disabled = false;
        $("tpAnalyze").textContent = "ANALISAR AGORA";
      }
    }
  }

  async function render() {
    const host = $("tradeProToolHost");
    if (!host) return;
    stopAuto();
    if (!sid()) {
      login();
      return;
    }
    try {
      await call("/session");
    } catch (_) {
      login();
      return;
    }
    shell();
    $("tpLogout").onclick = async () => {
      stopAuto();
      try { await call("/logout", { method: "POST" }); } catch (_) {}
      clearSession();
      login();
    };
    $("tpAnalyze").onclick = analyze;
    $("tpAuto").onchange = () => {
      stopAuto();
      if ($("tpAuto").checked) {
        analyze();
        timer = setInterval(analyze, 20000);
      }
    };
    $("tpClearLog").onclick = () => {
      if ($("tpLog")) {
        $("tpLog").className = "tp-log-empty";
        $("tpLog").textContent = "Histórico desta sessão limpo. Os sinais futuros aparecerão aqui.";
      }
      lastUiSignalKey = "";
    };
    try { await loadAssets(); } catch (_) {}
  }

  function isTradeProRoute() {
    const pathRoute = location.pathname.match(/ferramenta\/([^/]+)/)?.[1];
    const hashRoute = location.hash.match(/ferramenta\/([^?]+)/)?.[1];
    return pathRoute === "trade-pro" || hashRoute === "trade-pro";
  }

  function boot() {
    if (isTradeProRoute()) render();
    else stopAuto();
  }

  window.renderTradePro = render;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  window.addEventListener("hashchange", boot);
})();