(function () {
  const API = "/api/iq";
  const SESSION_KEY = "resolvei_iq_session";
  const ASSETS_KEY = "resolvei_binary_assets";
  const CURRENT_ASSET_KEY = "resolvei_binary_current_asset";
  const STRATEGY_KEY = "resolvei_binary_strategy";
  const EXPIRY_KEY = "resolvei_binary_expiry";
  const FLOATING_KEY = "resolvei_binary_floating";

  let session = sessionStorage.getItem(SESSION_KEY) || "";
  let assets = [];
  let strategies = {};
  let monitoredAssets = [];
  let currentAsset = localStorage.getItem(CURRENT_ASSET_KEY) || "EURUSD";
  let currentStrategy = localStorage.getItem(STRATEGY_KEY) || "trend_pullback";
  let currentExpiry = localStorage.getItem(EXPIRY_KEY) || "1min";
  let refreshTimer = null;
  let countdownTimer = null;
  let currentExpiresAt = 0;
  let inFlight = false;
  let dragState = null;

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
  }[c]));

  const pct = (v) => v == null ? "—" : Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  }) + "%";

  const normalizeAssets = (list) => {
    const unique = [...new Set((list || []).map(String).filter(Boolean))];
    return unique;
  };

  async function api(path, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    if (session) headers["X-IQ-Session"] = session;
    const response = await fetch(API + path, Object.assign({}, options, { headers }));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Erro no servidor.");
    return data;
  }

  function mount() {
    return document.getElementById("binaryAnalysisRoot");
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Math.ceil(Number(seconds || 0)));
    const mm = Math.floor(total / 60);
    const ss = total % 60;
    return String(mm).padStart(2, "0") + ":" + String(ss).padStart(2, "0");
  }

  function expiryLabel(expiry) {
    return expiry === "5min" ? "5 MINUTOS" : "1 MINUTO";
  }

  function saveState() {
    localStorage.setItem(CURRENT_ASSET_KEY, currentAsset);
    localStorage.setItem(STRATEGY_KEY, currentStrategy);
    localStorage.setItem(EXPIRY_KEY, currentExpiry);
    localStorage.setItem(ASSETS_KEY, JSON.stringify(monitoredAssets));
  }

  function loadSavedAssets() {
    try {
      const parsed = JSON.parse(localStorage.getItem(ASSETS_KEY) || "[]");
      monitoredAssets = Array.isArray(parsed) ? normalizeAssets(parsed) : [];
    } catch (_) {
      monitoredAssets = [];
    }
  }

  function loginMarkup(message = "") {
    return `
      <div class="binary-login-screen">
        <div class="binary-login-card">
          <div class="binary-login-title">ANÁLISE DE OPÇÕES BINÁRIAS</div>
          <h1>Conectar à IQ Option</h1>
          <p>Use sua conta para receber candles e sinais técnicos. A ferramenta não envia ordens.</p>
          <div class="binary-login-grid">
            <label>Usuário / e-mail<input id="binEmail" type="email" autocomplete="username"></label>
            <label>Senha<input id="binPassword" type="password" autocomplete="current-password"></label>
            <label>Conta<select id="binAccount"><option value="PRACTICE">PRACTICE — Demo</option><option value="REAL">REAL — Conta real</option></select></label>
          </div>
          <button class="binary-primary-btn" id="binLogin">🔐 Conectar</button>
          <div class="binary-login-message" id="binLoginMessage">${esc(message)}</div>
        </div>
      </div>`;
  }

  function controlMarkup() {
    const options = assets.map((asset) =>
      `<option value="${esc(asset)}">${esc(asset)}</option>`
    ).join("");

    const strategyOptions = Object.entries(strategies).map(([key, value]) =>
      `<option value="${esc(key)}">${esc(value.name)}</option>`
    ).join("");

    const chips = monitoredAssets.length
      ? monitoredAssets.map((asset) => `
          <button class="binary-pair-chip ${asset === currentAsset ? "active" : ""}" type="button" data-pair-chip="${esc(asset)}">
            ${esc(asset)} <span aria-hidden="true">×</span>
          </button>`).join("")
      : '<span class="binary-no-pairs">Nenhum par adicionado. O par atual será usado.</span>';

    return `
      <section class="binary-controls">
        <div class="binary-controls-header">
          <div>
            <div class="binary-controls-kicker">CONFIGURAÇÃO</div>
            <h2>Como você quer analisar?</h2>
          </div>
          <button class="binary-floating-btn ${isFloating() ? "active" : ""}" id="binFloating" type="button">${isFloating() ? "↙ Voltar à página" : "↗ Janela flutuante"}</button>
        </div>

        <div class="binary-controls-grid">
          <div class="binary-control-card">
            <label>Par atual<select id="binAsset">${options}</select></label>
            <button class="binary-add-pair" id="binAddPair" type="button">＋ Adicionar aos pares monitorados</button>
            <div class="binary-pairs-label">Pares monitorados</div>
            <div class="binary-pairs">${chips}</div>
          </div>

          <div class="binary-control-card">
            <label>Estratégia<select id="binStrategy">${strategyOptions}</select></label>
            <div class="binary-expiry-label">Tempo de expiração</div>
            <div class="binary-expiry">
              <button type="button" class="${currentExpiry === "1min" ? "active" : ""}" data-expiry="1min">1 minuto</button>
              <button type="button" class="${currentExpiry === "5min" ? "active" : ""}" data-expiry="5min">5 minutos</button>
            </div>
          </div>

          <div class="binary-control-actions">
            <button class="binary-primary-btn" id="binAnalyzeNow" type="button">🔎 Analisar agora</button>
            <button class="binary-secondary-btn" id="binRefresh" type="button">↻ Atualizar candles</button>
            <button class="binary-secondary-btn" id="binLogout" type="button">Desconectar</button>
          </div>
        </div>

        <div class="binary-disclaimer">
          API comunitária não oficial da IQ Option. A ferramenta somente analisa dados e não envia ordens.
          Você pode monitorar vários pares e trocar o par exibido sem perder sua configuração.
        </div>
      </section>`;
  }

  function shellMarkup() {
    return `
      <div class="binary-analysis-page ${isFloating() ? "floating " : ""}settings-mode">
        <div id="binaryCardHost"></div>
        <div id="binaryStatus" class="binary-status-line"></div>
        <div id="binarySettingsHost"></div>
      </div>`;
  }

  function isFloating() {
    return localStorage.getItem(FLOATING_KEY) === "1";
  }

  function setScreen(mode) {
    const page = document.querySelector(".binary-analysis-page");
    if (!page) return;
    page.classList.toggle("settings-mode", mode === "settings");
    page.classList.toggle("signal-mode", mode === "signal");
  }

  function setSignalScreen(statusText = "") {
    setScreen("signal");
    const status = document.getElementById("binaryStatus");
    if (status) status.textContent = statusText;
  }

  function setSettingsScreen(statusText = "") {
    setScreen("settings");
    const status = document.getElementById("binaryStatus");
    if (status) status.textContent = statusText;
  }

  function setFloating(value) {
    localStorage.setItem(FLOATING_KEY, value ? "1" : "0");
    const page = document.querySelector(".binary-analysis-page");
    if (page) page.classList.toggle("floating", value);
    renderSettings();
    updateFloatingButton();
    setTimeout(() => {
      applyFloatingPosition();
      enableFloatingDrag();
    }, 0);
  }

  function updateFloatingButton() {
    const button = document.getElementById("binFloating");
    if (!button) return;
    const active = isFloating();
    button.classList.toggle("active", active);
    button.textContent = active ? "↙ Voltar à página" : "↗ Janela flutuante";
  }

  function renderCard(data) {
    const signal = data?.signals?.[currentExpiry] || {};
    const accuracy = signal.historical_accuracy || {};
    const votes = signal.resumo_votos || {};
    const direction = data?.selected_signal || signal.signal || "AGUARDAR";
    const stateClass = direction === "CALL" ? "is-call" : direction === "PUT" ? "is-put" : "is-wait";
    const locked = Boolean(signal.locked);
    const reason = signal.reason || "Aguardando confirmação técnica.";
    const payout = signal.payout ?? data.payout;
    const voteConfidence = votes.confianca ?? signal.confidence ?? null;
    const history = Array.isArray(accuracy.ultimos) ? accuracy.ultimos.slice(-12) : [];
    const indicatorVotes = Array.isArray(signal.votos) ? signal.votos : [];
    const strategyName = strategies[currentStrategy]?.name || currentStrategy;
    const action = direction === "CALL" ? "COMPRA" : direction === "PUT" ? "VENDA" : "AGUARDAR";
    const actionClass = direction === "CALL" ? "buy" : direction === "PUT" ? "sell" : "wait";
    const newsWarning = signal.news_warning || data.warning || "";
    const proximity = signal.proximity || {};
    const proximityPercent = Math.max(0, Math.min(100, Number(proximity.percent ?? 0)));
    const proximityLabel = proximity.label || (proximityPercent >= 100 ? "LIMIAR TÉCNICO ATINGIDO" : "APROXIMAÇÃO");

    const badges = [
      ["rsi", "RSI (14)"], ["stoch", "Stochastic"], ["stochrsi", "Stoch RSI"],
      ["macd", "MACD"], ["ema510", "EMA 5/10"], ["ema1020", "EMA 10/20"],
      ["bollinger", "Bollinger"], ["adx", "ADX / DI"], ["cci", "CCI"], ["williams", "Williams %R"]
    ].map(([id, label]) => {
      const vote = indicatorVotes.find(item => item.id === id || item.nome === label || item.name === label);
      const voteValue = Number(vote?.vote ?? vote?.voto ?? 0);
      const cls = voteValue > 0 ? "vote-call" : voteValue < 0 ? "vote-put" : "vote-neutral";
      return `<span class="binary-indicator ${cls}">${esc(label)}</span>`;
    }).join("");

    const historyMarks = history.length
      ? history.map(item => `<span class="binary-history ${item === "OK" ? "win" : "loss"}">${item === "OK" ? "✓" : "✕"}</span>`).join("")
      : '<span class="binary-history-empty">sem amostra</span>';

    const countText = `▲ ${Number(votes.bulls || 0)} CALL <span class="vote-red">▼ ${Number(votes.bears || 0)} PUT</span> <span class="vote-blue">● ${Number(votes.neutros ?? votes.neutrals ?? 0)} neutros</span>`;

    const remaining = Math.max(0, Number(signal.seconds_remaining || 0));
    currentExpiresAt = Date.now() + remaining * 1000;

    const host = document.getElementById("binaryCardHost");
    if (!host) return;

    host.innerHTML = `
      <article class="binary-signal-card ${stateClass}">
        <div class="binary-card-top binary-drag-handle" title="Arraste por aqui para mover a janela flutuante">
          <span>EXPIRAÇÃO ${expiryLabel(currentExpiry)}</span>
          <span>${locked ? "SINAL FIXADO" : "ANÁLISE"}</span>
        </div>

        <div class="binary-current-meta">
          <span class="binary-pair-name">${esc(data.asset || currentAsset)}</span>
          <span class="binary-strategy-name">${esc(strategyName)}</span>
        </div>

        <div class="binary-card-main">
          <div class="binary-action-block ${actionClass}">
            <span class="binary-action-label">${actionClass === "buy" ? "SINAL DE COMPRA" : actionClass === "sell" ? "SINAL DE VENDA" : "SEM ENTRADA"}</span>
            <div class="binary-direction">${action}</div>
            <span class="binary-action-code">${direction === "CALL" ? "CALL" : direction === "PUT" ? "PUT" : "AGUARDAR"}</span>
          </div>
          <div class="binary-timer-block">
            <span>EXPIRA EM</span>
            <div class="binary-timer" id="binaryTimer">${formatDuration(remaining)}</div>
          </div>
        </div>
        <div class="binary-payout">Payout ${payout == null ? "—" : pct(payout)}</div>

        <div class="binary-reason">${esc(reason)}
          <span class="binary-accuracy"> · acerto: <strong>${pct(accuracy.rate)}</strong> (${Number(accuracy.sample_size || 0)} sinais · ${Number(accuracy.wins || 0)} acertos)</span>
        </div>
        ${newsWarning ? "<div class=\"binary-news-warning\">⚠ " + esc(newsWarning) + "</div>" : ""}
        <div class="binary-history-row">${historyMarks}</div>

        <div class="binary-proximity-block">
          <div class="binary-proximity-head">
            <span>PROXIMIDADE DO SINAL</span>
            <strong>${proximityPercent.toFixed(0)}%</strong>
          </div>
          <div class="binary-proximity-track">
            <div class="binary-proximity-fill" style="width:${proximityPercent}%"></div>
          </div>
          <div class="binary-proximity-label">${esc(proximityLabel)} · baseada no score técnico, não é probabilidade de acerto.</div>
        </div>

        <div class="binary-divider"></div>

        <div class="binary-votes-row">
          <div class="binary-votes-counts">${countText}</div>
          <div class="binary-confidence">confiança ${pct(voteConfidence)}</div>
        </div>

        <div class="binary-indicators">${badges}</div>

        <div class="binary-signal-actions">
          <button class="binary-secondary-btn" id="binSignalSettings" type="button">⚙ Configurar</button>
          <button class="binary-primary-btn" id="binSignalAnalyze" type="button">🔎 Analisar novamente</button>
        </div>
      </article>`;

    setScreen("signal");
    updateTimer();

    document.getElementById("binSignalSettings")?.addEventListener("click", () => {
      setSettingsScreen("Configuração carregada. Nenhuma nova análise foi executada.");
      renderSettings();
      applyFloatingPosition();
      enableFloatingDrag();
    });

    document.getElementById("binSignalAnalyze")?.addEventListener("click", () => {
      currentExpiresAt = 0;
      analyze();
    });
  }

  function updateTimer() {
    const el = document.getElementById("binaryTimer");
    if (!el) return;
    const seconds = Math.max(0, Math.ceil((currentExpiresAt - Date.now()) / 1000));
    el.textContent = formatDuration(seconds);
    if (seconds <= 0) {
      clearInterval(countdownTimer);
      countdownTimer = null;
      const status = document.getElementById("binaryStatus");
      if (status) status.textContent = "⏱️ Expiração encerrada. Clique em “Analisar novamente” para gerar um novo sinal.";
    }
  }

  async function login() {
    const msg = document.getElementById("binLoginMessage");
    const button = document.getElementById("binLogin");
    if (!msg || !button) return;
    msg.textContent = "⏳ Conectando...";
    button.disabled = true;
    try {
      const response = await fetch(API + "/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: document.getElementById("binEmail").value.trim(),
          password: document.getElementById("binPassword").value,
          account: document.getElementById("binAccount").value
        })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Não foi possível conectar.");
      session = data.session_id;
      sessionStorage.setItem(SESSION_KEY, session);
      loadSavedAssets();
      await startConnected();
    } catch (error) {
      msg.textContent = "🔴 " + error.message;
    } finally {
      button.disabled = false;
    }
  }

  async function logout() {
    try { await api("/logout", { method: "POST" }); } catch (_) {}
    session = "";
    sessionStorage.removeItem(SESSION_KEY);
    clearInterval(countdownTimer);
    clearInterval(refreshTimer);
    renderLogin();
  }

  async function loadCatalog() {
    const [assetData, strategyData] = await Promise.all([
      api("/assets"),
      api("/strategies")
    ]);
    assets = normalizeAssets(assetData.assets);
    strategies = strategyData.strategies || {};

    if (!assets.includes(currentAsset)) currentAsset = assets[0] || "EURUSD";
    monitoredAssets = monitoredAssets.filter((item) => assets.includes(item));
    if (!monitoredAssets.length && currentAsset) monitoredAssets = [currentAsset];
    if (!strategies[currentStrategy]) currentStrategy = Object.keys(strategies)[0] || "trend_pullback";
    if (!["1min", "5min"].includes(currentExpiry)) currentExpiry = "1min";
    saveState();
  }

  async function analyze(trigger = "manual") {
    if (!session || inFlight) return;
    const cardHost = document.getElementById("binaryCardHost");
    const status = document.getElementById("binaryStatus");
    if (!cardHost) return;

    if (trigger !== "manual") return;

    inFlight = true;
    currentExpiresAt = 0;
    setSignalScreen("🔎 Iniciando análise...");
    const loadingHost = document.getElementById("binaryCardHost");
    if (loadingHost) {
      loadingHost.innerHTML = `<article class="binary-signal-card is-wait binary-analyzing-card"><div class="binary-card-top binary-drag-handle"><span>ANÁLISE EM ANDAMENTO</span><span>AGUARDE</span></div><div class="binary-analyzing-icon">◌</div><div class="binary-analyzing-title">Calculando o sinal</div><div class="binary-analyzing-subtitle">Coletando candles, calculando indicadores e verificando a proximidade do sinal.</div><div class="binary-analysis-progress"><div class="binary-analysis-progress-track"><div class="binary-analysis-progress-fill"></div></div></div><div class="binary-analyzing-label">Processando dados do mercado...</div></article>`;
    }
    const manualButton = document.getElementById("binAnalyzeNow");
    if (manualButton) {
      manualButton.disabled = true;
      manualButton.textContent = "⏳ Analisando...";
    }
    try {
      if (status) status.textContent = `Atualizando ${currentAsset} · ${expiryLabel(currentExpiry).toLowerCase()}...`;
      const data = await api(
        "/analyze/" + encodeURIComponent(currentAsset) +
        "?strategy=" + encodeURIComponent(currentStrategy) +
        "&expiry=" + encodeURIComponent(currentExpiry) +
        "&refresh=" + (force ? "1" : "0")
      );
      renderCard(data);
      renderSettings();
      if (status) {
        status.textContent = `${currentAsset} · ${expiryLabel(currentExpiry).toLowerCase()} · mercado ${data.market || "indisponível"}`;
      }
      saveState();
      clearInterval(countdownTimer);
      countdownTimer = setInterval(updateTimer, 250);
    } catch (error) {
      if (status) status.textContent = "⚠️ " + error.message;
    } finally {
      inFlight = false;
      const doneButton = document.getElementById("binAnalyzeNow");
      if (doneButton) {
        doneButton.disabled = false;
        doneButton.textContent = "🔎 Analisar agora";
      }
      enableFloatingDrag();
    }
  }

  function renderSettings() {
    const host = document.getElementById("binarySettingsHost");
    if (!host) return;
    host.innerHTML = controlMarkup();

    const asset = document.getElementById("binAsset");
    const strategy = document.getElementById("binStrategy");

    if (asset) asset.value = currentAsset;
    if (strategy) strategy.value = currentStrategy;

    asset?.addEventListener("change", () => {
      currentAsset = asset.value;
      if (!monitoredAssets.includes(currentAsset)) monitoredAssets.push(currentAsset);
      saveState();
      setSettingsScreen("Par alterado. Clique em “Analisar agora” para calcular o sinal.");
      renderSettings();
    });

    strategy?.addEventListener("change", () => {
      currentStrategy = strategy.value;
      saveState();
      setSettingsScreen("Estratégia alterada. Clique em “Analisar agora” para recalcular.");
    });

    document.getElementById("binAddPair")?.addEventListener("click", () => {
      if (!monitoredAssets.includes(currentAsset)) monitoredAssets.push(currentAsset);
      saveState();
      setSettingsScreen("Par adicionado aos monitorados. Nenhuma análise foi executada.");
      renderSettings();
    });

    document.querySelectorAll("[data-pair-chip]").forEach((button) => {
      button.addEventListener("click", () => {
        const pair = button.dataset.pairChip;
        if (!pair) return;
        currentAsset = pair;
        saveState();
        renderSettings();
        analyze(true);
      });
      button.querySelector("span")?.addEventListener("click", (event) => {
        event.stopPropagation();
        monitoredAssets = monitoredAssets.filter((item) => item !== pair);
        if (!monitoredAssets.length) monitoredAssets = [currentAsset];
        if (!monitoredAssets.includes(currentAsset)) currentAsset = monitoredAssets[0];
        saveState();
        renderSettings();
        analyze(true);
      });
    });

    document.querySelectorAll("[data-expiry]").forEach((button) => {
      button.addEventListener("click", () => {
        currentExpiry = button.dataset.expiry === "5min" ? "5min" : "1min";
        saveState();
        renderSettings();
        analyze(true);
      });
    });

    document.getElementById("binAnalyzeNow")?.addEventListener("click", () => {
      if (inFlight) return;
      currentExpiresAt = 0;
      analyze();
    });
    document.getElementById("binRefresh")?.addEventListener("click", refreshCandlesOnly);
    document.getElementById("binLogout")?.addEventListener("click", logout);
    document.getElementById("binFloating")?.addEventListener("click", () => setFloating(!isFloating()));
  }

  function applyFloatingPosition() {
    if (!isFloating()) return;
    const page = document.querySelector(".binary-analysis-page.floating");
    if (!page) return;
    const savedLeft = Number(localStorage.getItem("resolvei_binary_float_left"));
    const savedTop = Number(localStorage.getItem("resolvei_binary_float_top"));
    if (Number.isFinite(savedLeft) && Number.isFinite(savedTop)) {
      const maxLeft = Math.max(10, window.innerWidth - page.offsetWidth - 10);
      const maxTop = Math.max(10, window.innerHeight - page.offsetHeight - 10);
      page.style.left = Math.min(Math.max(10, savedLeft), maxLeft) + "px";
      page.style.top = Math.min(Math.max(10, savedTop), maxTop) + "px";
      page.style.right = "auto";
      page.style.bottom = "auto";
    }
  }

  function enableFloatingDrag() {
    const page = document.querySelector(".binary-analysis-page.floating");
    const handle = page?.querySelector(".binary-drag-handle");
    if (!page || !handle || handle.dataset.dragBound === "1") return;
    handle.dataset.dragBound = "1";
    applyFloatingPosition();

    handle.addEventListener("pointerdown", (event) => {
      if (!isFloating() || event.button !== 0) return;
      const rect = page.getBoundingClientRect();
      dragState = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        left: rect.left,
        top: rect.top
      };
      page.style.left = rect.left + "px";
      page.style.top = rect.top + "px";
      page.style.right = "auto";
      page.style.bottom = "auto";
      handle.classList.add("dragging");
      handle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });

    handle.addEventListener("pointermove", (event) => {
      if (!dragState || dragState.pointerId !== event.pointerId) return;
      const maxLeft = Math.max(10, window.innerWidth - page.offsetWidth - 10);
      const maxTop = Math.max(10, window.innerHeight - page.offsetHeight - 10);
      const left = Math.min(Math.max(10, dragState.left + event.clientX - dragState.startX), maxLeft);
      const top = Math.min(Math.max(10, dragState.top + event.clientY - dragState.startY), maxTop);
      page.style.left = left + "px";
      page.style.top = top + "px";
    });

    const release = (event) => {
      if (!dragState || dragState.pointerId !== event.pointerId) return;
      const rect = page.getBoundingClientRect();
      localStorage.setItem("resolvei_binary_float_left", String(Math.round(rect.left)));
      localStorage.setItem("resolvei_binary_float_top", String(Math.round(rect.top)));
      dragState = null;
      handle.classList.remove("dragging");
      try { handle.releasePointerCapture?.(event.pointerId); } catch (_) {}
    };

    handle.addEventListener("pointerup", release);
    handle.addEventListener("pointercancel", release);
  }

  window.addEventListener("resize", () => {
    if (!isFloating()) return;
    const page = document.querySelector(".binary-analysis-page.floating");
    if (!page) return;
    const rect = page.getBoundingClientRect();
    const maxLeft = Math.max(10, window.innerWidth - page.offsetWidth - 10);
    const maxTop = Math.max(10, window.innerHeight - page.offsetHeight - 10);
    page.style.left = Math.min(Math.max(10, rect.left), maxLeft) + "px";
    page.style.top = Math.min(Math.max(10, rect.top), maxTop) + "px";
  });

  async function startConnected() {
    try {
      const status = await api("/status");
      if (!status.connected) {
        session = "";
        sessionStorage.removeItem(SESSION_KEY);
        renderLogin();
        return;
      }

      const root = mount();
      if (!root) return;

      loadSavedAssets();
      root.innerHTML = shellMarkup();
      await loadCatalog();
      renderSettings();
      await analyze(true);
      enableFloatingDrag();

      clearInterval(refreshTimer);
      refreshTimer = setInterval(() => analyze(false), 1000);
    } catch (error) {
      renderLogin(error.message);
    }
  }

  function renderLogin(message = "") {
    const root = mount();
    if (!root) return;
    root.innerHTML = loginMarkup(message);
    document.getElementById("binLogin")?.addEventListener("click", login);
  }

  function init() {
    const root = mount();
    if (!root) return;
    loadSavedAssets();
    if (session) startConnected();
    else renderLogin();
  }

  window.addEventListener("hashchange", () => {
    if ((location.hash || "").includes("analise-opcoes")) {
      setTimeout(init, 0);
    }
  });

  if ((location.hash || "").includes("analise-opcoes")) {
    setTimeout(init, 0);
  }
})();