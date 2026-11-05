(() => {
  const API = "/api/heikin-ashi";
  const KEY = "resolvei_heikin_ashi_session";
  const FAVORITES_KEY = "resolvei_heikin_ashi_favorites";
  let scanTimer = null;
  let scanClock = null;
  let scanActive = false;
  let requestBusy = false;
  let lastData = null;
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
  const sid = () => sessionStorage.getItem(KEY) || "";
  const clearSession = () => sessionStorage.removeItem(KEY);

  function getFavorites() {
    try {
      const value = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
      return Array.isArray(value) ? [...new Set(value.filter((item) => typeof item === "string" && item.trim()))] : [];
    } catch {
      return [];
    }
  }
  function saveFavorites(items) {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(items)); } catch {}
  }
  function stopTimers() {
    clearTimeout(scanTimer);
    clearInterval(scanClock);
    scanTimer = null;
    scanClock = null;
    scanActive = false;
    requestBusy = false;
  }
  async function call(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (sid()) headers["X-IQ-Session"] = sid();
    let response;
    try {
      response = await fetch(API + path, { ...options, headers });
    } catch {
      throw new Error("Não foi possível alcançar a API do Heikin-Ashi Digital. Verifique a conexão com o Resolvei.");
    }
    let data = null;
    try { data = await response.json(); } catch {}
    if (!response.ok) {
      if (response.status === 401) clearSession();
      throw new Error((data && data.detail) || ("API HTTP " + response.status));
    }
    return data || {};
  }

  function login() {
    stopTimers();
    const host = $("heikinAshiToolHost");
    if (!host) return;
    host.innerHTML = [
      '<div class="ha-login">',
      '<small>RESOLVEI / IQ OPTION</small>',
      '<h1>Heikin-Ashi <span>Digital</span></h1>',
      '<p>Entre com sua conta da IQ Option. Esta ferramenta mantém uma sessão exclusiva, separada das demais ferramentas do Resolvei.</p>',
      '<form id="haLoginForm">',
      '<label>E-MAIL IQ OPTION<input id="haEmail" type="email" autocomplete="username" required></label>',
      '<label>SENHA IQ OPTION<input id="haPassword" type="password" autocomplete="current-password" required></label>',
      '<button id="haLoginBtn" type="submit">CONECTAR À IQ OPTION</button>',
      '</form><div id="haLoginMsg" role="status"></div>',
      '<p class="ha-login-note">A ferramenta consulta cotações e candles para gerar sinais. Ela não envia ordens à corretora.</p>',
      '</div>'
    ].join("");
    $("haLoginForm").onsubmit = async (event) => {
      event.preventDefault();
      const button = $("haLoginBtn");
      const message = $("haLoginMsg");
      button.disabled = true;
      button.textContent = "CONECTANDO…";
      message.textContent = "";
      try {
        const data = await call("/login", {
          method: "POST",
          body: JSON.stringify({ email: $("haEmail").value.trim(), password: $("haPassword").value })
        });
        sessionStorage.setItem(KEY, data.session_id);
        await render();
      } catch (error) {
        message.textContent = "⚠️ " + error.message;
      } finally {
        if ($("haLoginBtn")) {
          $("haLoginBtn").disabled = false;
          $("haLoginBtn").textContent = "CONECTAR À IQ OPTION";
        }
      }
    };
  }

  function renderFavorites() {
    const host = $("haFavorites");
    const select = $("haPair");
    if (!host || !select) return;
    const favorites = getFavorites();
    const active = select.value;
    host.hidden = !favorites.length;
    if (!favorites.length) {
      host.innerHTML = "";
      return;
    }
    host.innerHTML = '<div class="ha-favorites-head"><strong>ATIVOS FAVORITOS</strong><small>' +
      favorites.length + " ATIVO" + (favorites.length === 1 ? "" : "S") +
      '</small></div><div class="ha-favorite-list">' +
      favorites.map((symbol) => {
        const available = [...select.options].some((option) => option.value === symbol);
        return '<div class="ha-favorite-card' + (symbol === active ? " active" : "") + '">' +
          '<button type="button" class="ha-fav-select" data-symbol="' + esc(symbol) + '"' +
          (available ? "" : " disabled") + "><span>" + esc(symbol) +
          "</span><small>" + (symbol === active ? "SELECIONADO" : "TROCAR ATIVO") +
          '</small></button><button type="button" class="ha-fav-remove" data-remove-symbol="' +
          esc(symbol) + '" aria-label="Remover ' + esc(symbol) +
          ' dos favoritos" title="Remover dos favoritos">×</button></div>';
      }).join("") + "</div>";
    host.querySelectorAll(".ha-fav-select").forEach((button) => {
      button.onclick = () => {
        select.value = button.dataset.symbol;
        renderFavorites();
        syncFavoriteToggle();
        if (scanActive) analyze(true);
      };
    });
    host.querySelectorAll(".ha-fav-remove").forEach((button) => {
      button.onclick = () => {
        saveFavorites(getFavorites().filter((symbol) => symbol !== button.dataset.removeSymbol));
        renderFavorites();
        syncFavoriteToggle();
      };
    });
  }
  function syncFavoriteToggle() {
    const button = $("haFavoriteToggle");
    const select = $("haPair");
    if (!button || !select) return;
    const active = !!select.value && getFavorites().includes(select.value);
    button.textContent = active ? "★" : "☆";
    button.classList.toggle("is-favorite", active);
    button.setAttribute("aria-pressed", String(active));
    button.title = active ? "Remover dos favoritos" : "Favoritar este ativo";
  }
  function toggleFavorite() {
    const select = $("haPair");
    if (!select || !select.value) return;
    const favorites = getFavorites();
    saveFavorites(favorites.includes(select.value)
      ? favorites.filter((symbol) => symbol !== select.value)
      : [...favorites, select.value]);
    renderFavorites();
    syncFavoriteToggle();
  }

  async function loadAssets() {
    const select = $("haPair");
    const message = $("haError");
    if (!select) return;
    const selected = select.value;
    select.innerHTML = '<option value="">CARREGANDO ATIVOS…</option>';
    try {
      const data = await call("/assets");
      const assets = (data.groups && data.groups.all) || [];
      select.innerHTML = "";
      assets.forEach((asset) => {
        const option = document.createElement("option");
        option.value = asset.symbol;
        option.textContent = asset.symbol + (asset.open === false ? " · FECHADO" : "");
        select.appendChild(option);
      });
      if (!assets.length) throw new Error("A IQ Option não retornou ativos para esta sessão.");
      if (selected && [...select.options].some((option) => option.value === selected)) select.value = selected;
      else {
        const firstOpen = [...select.options].find((option) => option.textContent.indexOf("FECHADO") < 0);
        if (firstOpen) firstOpen.selected = true;
      }
      renderFavorites();
      syncFavoriteToggle();
      if (message) message.textContent = "";
    } catch (error) {
      select.innerHTML = '<option value="">ERRO AO CARREGAR ATIVOS</option>';
      if (message) message.textContent = "⚠️ " + error.message;
    }
  }

  async function render() {
    const host = $("heikinAshiToolHost");
    if (!host) return;
    stopTimers();
    if (!sid()) {
      login();
      return;
    }
    try {
      await call("/session");
    } catch {
      login();
      return;
    }
    host.innerHTML = [
      '<div class="ha-app">',
      '<header class="ha-header"><div><small>RESOLVEI / IQ OPTION · SESSÃO EXCLUSIVA</small><h1>Heikin-Ashi <span>Digital</span></h1><p>Leitura de tendência, reversão e ponto de entrada</p></div>',
      '<div class="ha-head-actions"><b>● CONECTADO</b><button id="haLogout" type="button">SAIR</button></div></header>',
      '<section class="ha-config">',
      '<label>ATIVO<div class="ha-asset-picker"><select id="haPair"><option>CARREGANDO ATIVOS…</option></select><button id="haFavoriteToggle" type="button" aria-label="Favoritar ativo" title="Favoritar ativo">☆</button></div></label>',
      '<label>EXPIRAÇÃO<select id="haTf"><option value="1m">1 MINUTO · M1</option><option value="5m">5 MINUTOS · M5</option><option value="15m">15 MINUTOS · M15</option></select></label>',
      '<label>ESTRATÉGIA<select id="haStrategy"><option value="auto">AUTOMÁTICA</option><option value="trend">CONTINUAÇÃO DE TENDÊNCIA</option><option value="reversal">REVERSÃO DE TENDÊNCIA</option></select></label>',
      '<button id="haAnalyze" type="button">ANALISAR AGORA</button>',
      '</section>',
      '<p class="ha-scan-hint">Ao clicar em “Analisar agora”, o Resolvei analisa o gráfico e monitora os próximos candles até encontrar uma entrada validada.</p>',
      '<section id="haFavorites" class="ha-favorites" hidden aria-label="Ativos favoritos"></section>',
      '<div id="haError" class="ha-error" role="status"></div>',
      '<section class="ha-top-grid">',
      '<article id="haSignal" class="ha-signal ha-neutral"><small>DECISÃO DO MOTOR</small><strong>AGUARDANDO ANÁLISE</strong><span>Selecione o ativo e inicie a leitura técnica.</span><div class="ha-signal-foot" id="haSignalFoot">Sem sinal ativo</div></article>',
      '<article class="ha-score-card"><small>CONFLUÊNCIA TÉCNICA</small><div class="ha-score"><b id="haScore">--</b><span>/ 100</span></div><div class="ha-meter"><i id="haMeter"></i></div><div class="ha-min-score">MÍNIMO PARA SINAL: 76 PONTOS</div><div class="ha-entry-clock" id="haClock">JANELA DE ENTRADA: --</div></article>',
      '</section>',
      '<section class="ha-chart-card"><div class="ha-section-head"><div><small>GRÁFICO PRINCIPAL</small><h2>Heikin-Ashi</h2><p id="haChartMeta">Candles fechados · aguardando dados</p></div><span class="ha-chart-legend"><i></i> Alta <i></i> Baixa</span></div><canvas id="haChart" aria-label="Gráfico de candles Heikin-Ashi"></canvas></section>',
      '<section class="ha-metrics" aria-label="Indicadores de contexto">',
      '<article><small>REGIME DE MERCADO</small><b id="haRegime">--</b></article>',
      '<article><small>FORÇA ADX</small><b id="haAdx">--</b></article>',
      '<article><small>RSI 14</small><b id="haRsi">--</b></article>',
      '<article><small>TIMEFRAME SUPERIOR</small><b id="haHigher">--</b></article>',
      '</section>',
      '<section class="ha-analysis-grid">',
      '<article class="ha-panel"><div class="ha-section-head"><div><small>LEITURA TÉCNICA</small><h2>Confluência dos indicadores</h2></div><span id="haStrategyLabel">--</span></div><div id="haIndicators" class="ha-indicators"><p>Os indicadores serão exibidos após a análise.</p></div></article>',
      '<article class="ha-panel"><div class="ha-section-head"><div><small>PLANO DE ENTRADA</small><h2>Momento e expiração</h2></div></div><div id="haEntryPlan" class="ha-entry-plan">Aguardando análise.</div><div class="ha-reasons-head">FILTROS E OBSERVAÇÕES</div><div id="haReasons" class="ha-reasons"></div></article>',
      '</section>',
      '<p class="ha-disclaimer">A pontuação mede confluência técnica e não representa percentual de acerto ou probabilidade de lucro. Heikin-Ashi suaviza os movimentos e pode atrasar a leitura. Nenhum sinal garante resultado. A ferramenta é informativa e não envia ordens à IQ Option.</p>',
      '</div>'
    ].join("");

    $("haLogout").onclick = async () => {
      try { await call("/logout", { method: "POST" }); } catch {}
      clearSession();
      stopTimers();
      login();
    };
    $("haPair").onchange = () => {
      renderFavorites();
      syncFavoriteToggle();
      clearAnalysis("Ativo alterado. Faça uma nova leitura.");
      if (scanActive) analyze(true);
    };
    $("haTf").onchange = () => {
      clearAnalysis("Expiração alterada. Faça uma nova leitura.");
      if (scanActive) analyze(true);
    };
    $("haStrategy").onchange = () => {
      clearAnalysis("Estratégia alterada. Faça uma nova leitura.");
      if (scanActive) analyze(true);
    };
    $("haFavoriteToggle").onclick = toggleFavorite;
    $("haAnalyze").onclick = toggleAnalysis;
    await loadAssets();
  }

  function clearAnalysis(message) {
    lastData = null;
    const card = $("haSignal");
    if (card) {
      card.className = "ha-signal ha-neutral";
      card.querySelector("strong").textContent = "AGUARDANDO ANÁLISE";
      card.querySelector("span").textContent = message;
    }
    if ($("haScore")) $("haScore").textContent = "--";
    if ($("haMeter")) $("haMeter").style.width = "0%";
    if ($("haEntryPlan")) $("haEntryPlan").textContent = "Aguardando nova análise.";
    if ($("haClock")) $("haClock").textContent = "JANELA DE ENTRADA: --";
    drawChart(null);
  }

  async function analyze(silent) {
    if (requestBusy || !$("haPair")) return;
    clearTimeout(scanTimer);
    scanTimer = null;
    requestBusy = true;
    const button = $("haAnalyze");
    const error = $("haError");
    if (button && !silent && !scanActive) {
      button.disabled = true;
      button.textContent = "ANALISANDO…";
    }
    if (error) error.textContent = "";
    try {
      const symbol = $("haPair").value;
      if (!symbol) throw new Error("Nenhum ativo disponível para análise.");
      const data = await call("/analyze", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          timeframe: $("haTf").value,
          strategy: $("haStrategy").value
        })
      });
      show(data);
      if (data.direction !== "NONE" && scanActive) {
        stopScan("Sinal identificado. Monitoramento pausado para evitar sinais repetidos.");
      }
    } catch (exception) {
      if (error) error.textContent = "⚠️ " + exception.message;
      if (!sid()) login();
    } finally {
      requestBusy = false;
      if (button) {
        button.disabled = false;
        if (!scanActive) {
          button.textContent = "ANALISAR AGORA";
          button.classList.remove("is-scanning");
        }
      }
      // Enquanto não houver sinal, continua verificando candles fechados.
      // Se ocorrer uma falha transitória, tenta novamente enquanto a sessão estiver válida.
      if (scanActive && sid() && (!lastData || lastData.direction === "NONE")) {
        clearTimeout(scanTimer);
        scanTimer = setTimeout(() => analyze(true), 9000);
      }
    }
  }

  function toggleAnalysis() {
    if (scanActive) {
      stopScan("Busca de entrada interrompida pelo usuário.");
      return;
    }
    scanActive = true;
    const button = $("haAnalyze");
    if (button) {
      button.textContent = "PARAR ANÁLISE";
      button.classList.add("is-scanning");
    }
    clearAnalysis("Analisando o gráfico e procurando uma entrada validada...");
    const foot = $("haSignalFoot");
    if (foot) foot.textContent = "Analisando candles fechados e buscando confluência...";
    if ($("haError")) $("haError").textContent = "";
    analyze(true);
  }

  function stopScan(message) {
    clearTimeout(scanTimer);
    scanTimer = null;
    scanActive = false;
    const button = $("haAnalyze");
    if (button) {
      button.disabled = false;
      button.textContent = "ANALISAR AGORA";
      button.classList.remove("is-scanning");
    }
    if (message && $("haSignalFoot") && (!lastData || lastData.direction === "NONE")) {
      $("haSignalFoot").textContent = message;
    }
  }

  function show(data) {
    lastData = data;
    const isCall = data.direction === "CALL";
    const isPut = data.direction === "PUT";
    const card = $("haSignal");
    card.className = "ha-signal " + (isCall ? "ha-call" : isPut ? "ha-put" : "ha-neutral");
    card.querySelector("strong").textContent = isCall ? "COMPRA · CALL" : isPut ? "VENDA · PUT" : "AGUARDAR";
    card.querySelector("span").textContent = data.signal + " · " + data.strategyLabel;
    $("haSignalFoot").textContent = data.direction === "NONE"
      ? "Nenhuma entrada validada neste fechamento"
      : "Sinal válido somente na janela indicada abaixo";
    $("haScore").textContent = Number(data.score).toFixed(0);
    $("haMeter").style.width = Math.min(100, Number(data.score)) + "%";
    $("haRegime").textContent = data.marketRegimeLabel || "--";
    $("haAdx").textContent = Number(data.adx).toFixed(1);
    $("haRsi").textContent = Number(data.rsi).toFixed(1);
    $("haHigher").textContent = (data.higherTimeframe || "--") + " · " + (data.higherDirection || "--");
    $("haStrategyLabel").textContent = data.strategyLabel || "Automática";
    $("haChartMeta").textContent = data.symbol + " · " + data.timeframe.toUpperCase() +
      " · " + data.candlesAnalyzed + " candles fechados";
    drawChart(data);

    $("haIndicators").innerHTML = (data.indicators || []).map((indicator) => {
      const cls = indicator.direction === 1 ? "bull" : indicator.direction === -1 ? "bear" : "flat";
      const direction = indicator.direction === 1 ? "ALTA" : indicator.direction === -1 ? "BAIXA" : "NEUTRO";
      return '<div class="ha-indicator ' + cls + (indicator.active ? " active" : "") + '">' +
        '<b>' + (indicator.active ? "✓" : "·") + '</b><span><strong>' + esc(indicator.name) +
        '</strong><small>' + esc(indicator.detail || indicator.group || "") +
        '</small></span><em>' + direction + '</em></div>';
    }).join("");

    const entryPlan = $("haEntryPlan");
    if (data.direction === "NONE") {
      entryPlan.innerHTML = '<strong class="ha-wait">SEM PONTO DE ENTRADA</strong><p>Não opere por antecipação. Aguarde novo fechamento e confirmação do gatilho.</p>';
    } else {
      entryPlan.innerHTML = '<strong class="' + (isCall ? "ha-green" : "ha-red") + '">' +
        (isCall ? "CALL · COMPRA" : "PUT · VENDA") + '</strong>' +
        '<dl><div><dt>Expiração</dt><dd>' + data.expiryMinutes + ' minuto(s)</dd></div>' +
        '<div><dt>Abertura prevista</dt><dd>' + formatTime(data.entryAt) + '</dd></div>' +
        '<div><dt>Vencimento estimado</dt><dd>' + formatTime(data.expiryAt) + '</dd></div>' +
        '<div><dt>Preço de referência</dt><dd>' + formatPrice(data.referencePrice) + '</dd></div></dl>' +
        '<p>O ponto de referência é o fechamento do candle analisado. A entrada só deve ser considerada na abertura da próxima vela e enquanto a janela estiver aberta.</p>';
    }
    const reasons = (data.blockingReasons || []);
    $("haReasons").innerHTML = reasons.map((reason) => "<p>" + esc(reason) + "</p>").join("");
    startEntryClock(data.entryWindowEndsAt, data.direction !== "NONE");
  }

  function formatTime(timestamp) {
    if (!timestamp) return "--";
    return new Date(Number(timestamp) * 1000).toLocaleTimeString("pt-BR", {
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
  }
  function formatPrice(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("pt-BR", { maximumFractionDigits: 6 }) : "--";
  }
  function startEntryClock(timestamp, hasSignal) {
    clearInterval(scanClock);
    const update = () => {
      const element = $("haClock");
      if (!element) return;
      if (!hasSignal) {
        element.textContent = "JANELA DE ENTRADA: sem sinal";
        return;
      }
      const seconds = Math.max(0, Math.ceil(Number(timestamp) - Date.now() / 1000));
      element.textContent = seconds > 0 ? "JANELA DE ENTRADA: " + seconds + "s" : "JANELA ENCERRADA · AGUARDE NOVO GATILHO";
      if (seconds === 0 && $("haSignal")) {
        $("haSignal").classList.add("ha-expired");
        $("haSignalFoot").textContent = "Janela de entrada encerrada. Não use este sinal atrasado.";
      }
    };
    update();
    scanClock = setInterval(update, 500);
  }

  function drawChart(data) {
    const canvas = $("haChart");
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width || canvas.parentElement.clientWidth || 800));
    const height = Math.max(220, Math.floor(rect.height || 300));
    const ratio = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#0b111b";
    ctx.fillRect(0, 0, width, height);
    const candles = data && data.candles ? data.candles.slice(-64) : [];
    if (!candles.length) {
      ctx.fillStyle = "#8290a3";
      ctx.font = "12px system-ui";
      ctx.textAlign = "center";
      ctx.fillText("Aguardando candles da IQ Option", width / 2, height / 2);
      return;
    }
    const left = 12, right = 66, top = 14, bottom = 24;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const values = candles.flatMap((candle) => [Number(candle.high), Number(candle.low)]).filter(Number.isFinite);
    let minimum = Math.min(...values), maximum = Math.max(...values);
    const padding = Math.max((maximum - minimum) * 0.08, Math.abs(maximum) * 0.00003, 1e-8);
    minimum -= padding;
    maximum += padding;
    const y = (value) => top + ((maximum - value) / (maximum - minimum)) * plotHeight;
    ctx.strokeStyle = "#1b2939";
    ctx.lineWidth = 1;
    ctx.font = "10px system-ui";
    ctx.textAlign = "left";
    for (let row = 0; row <= 4; row++) {
      const yy = top + plotHeight * row / 4;
      ctx.beginPath();
      ctx.moveTo(left, yy);
      ctx.lineTo(width - right + 4, yy);
      ctx.stroke();
      const price = maximum - (maximum - minimum) * row / 4;
      ctx.fillStyle = "#718096";
      ctx.fillText(formatPrice(price), width - right + 9, yy + 3);
    }
    const slot = plotWidth / candles.length;
    const bodyWidth = Math.max(2, Math.min(10, slot * 0.62));
    candles.forEach((candle, index) => {
      const x = left + slot * (index + 0.5);
      const bullish = Number(candle.color) >= 0;
      const color = bullish ? "#28d99a" : "#ff647c";
      const openY = y(Number(candle.open));
      const closeY = y(Number(candle.close));
      const highY = y(Number(candle.high));
      const lowY = y(Number(candle.low));
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();
      const bodyTop = Math.min(openY, closeY);
      const bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
      ctx.fillRect(x - bodyWidth / 2, bodyTop, bodyWidth, bodyHeight);
    });
    ctx.fillStyle = "#718096";
    ctx.textAlign = "left";
    ctx.fillText("MAIS ANTIGO", left, height - 7);
    ctx.textAlign = "right";
    ctx.fillText("ÚLTIMA VELA FECHADA", width - right + 4, height - 7);
  }

  window.renderHeikinAshiDigital = render;
  function boot() {
    if ((location.hash || "").includes("/ferramenta/heikin-ashi")) render();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  window.addEventListener("hashchange", () => {
    if ((location.hash || "").includes("/ferramenta/heikin-ashi")) render();
    else stopTimers();
  });
  window.addEventListener("resize", () => { if (lastData) drawChart(lastData); });
})();