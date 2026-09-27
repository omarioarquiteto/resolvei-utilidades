(function () {
  const API = "/api/iq";
  const SESSION_KEY = "resolvei_iq_session";
  const CURRENT_ASSET_KEY = "resolvei_binary_current_asset";
  const STRATEGY_KEY = "resolvei_binary_strategy";
  const EXPIRY_KEY = "resolvei_binary_expiry";
  const MARKET_KEY = "resolvei_binary_market";
  const FLOATING_KEY = "resolvei_binary_floating";

  let session = sessionStorage.getItem(SESSION_KEY) || "";
  let pending2FA = "";
  let assets = [];
  let strategies = {};
  let currentAsset = localStorage.getItem(CURRENT_ASSET_KEY) || "EURUSD";
  let currentStrategy = localStorage.getItem(STRATEGY_KEY) || "smart_confluence";
  let currentExpiry = localStorage.getItem(EXPIRY_KEY) || "1min";
  let currentMarket = localStorage.getItem(MARKET_KEY) || (currentAsset.endsWith("-OTC") ? "OTC" : "REGULAR");
  let refreshTimer = null;
  let countdownTimer = null;
  let monitoringTimer = null;
  let signalHoldUntil = 0;
  let currentSignalRank = -1;
  let currentSignalDirection = "AGUARDAR";
  let currentEntryAt = 0;
  let analysisController = null;
  let analysisStageTimer = null;
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

  function stopAnalysisStageAnimation() {
    clearInterval(analysisStageTimer);
    analysisStageTimer = null;
  }

  function setAnalysisStage(stage, percent, label) {
    const title = document.getElementById("binaryAnalyzingTitle");
    const subtitle = document.getElementById("binaryAnalyzingSubtitle");
    const value = document.getElementById("binaryAnalysisThermometerValue");
    const fill = document.getElementById("binaryAnalysisThermometerFill");
    const labelEl = document.getElementById("binaryAnalyzingLabel");
    if (title) title.textContent = stage;
    if (subtitle) subtitle.textContent = "Coletando candles, calculando indicadores e avaliando a estrutura técnica do par.";
    if (value) value.textContent = stage;
    if (fill) fill.style.width = Math.max(0, Math.min(100, percent)) + "%";
    if (labelEl) labelEl.textContent = label;
  }

  function startAnalysisStageAnimation() {
    stopAnalysisStageAnimation();
    // O estado visual não simula progresso interno. A análise é executada no
    // backend e a interface só muda quando existe um resultado real.
    setAnalysisStage(
      "ANALISANDO MERCADO",
      42,
      "Lendo candles fechados, contexto multi-timeframe e confluência técnica..."
    );
  }

  function proximityStage(signal) {
    const percent = Math.max(0, Math.min(100, Number(signal?.proximity?.percent ?? 0)));
    if (signal?.signal === "CALL") {
      return {
        percent,
        title: "COMPRA",
        label: signal?.confirmed
          ? "Limiar técnico atingido para CALL."
          : "Direção técnica predominante em CALL; o score ainda está abaixo do limiar ideal."
      };
    }
    if (signal?.signal === "PUT") {
      return {
        percent,
        title: "VENDA",
        label: signal?.confirmed
          ? "Limiar técnico atingido para PUT."
          : "Direção técnica predominante em PUT; o score ainda está abaixo do limiar ideal."
      };
    }
    if (percent >= 75) return { percent, title: "SINAL MUITO PRÓXIMO", label: "A análise está próxima do limiar técnico configurado." };
    if (percent >= 50) return { percent, title: "ATENÇÃO", label: "Há confluência parcial, mas ainda não há direção confirmável." };
    return { percent, title: "ANALISANDO MERCADO", label: "Dados insuficientes para uma direção técnica." };
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
    localStorage.setItem(MARKET_KEY, currentMarket);
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
          <div id="bin2FABox" style="display:none;margin-top:16px;padding:14px;border:1px solid rgba(255,255,255,.12);border-radius:12px;">
            <strong>VERIFICAÇÃO EM DUAS ETAPAS</strong>
            <p style="margin:8px 0;">A IQ Option solicitou um código de verificação. Informe o código recebido.</p>
            <label>Código de verificação<input id="bin2FACode" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="12"></label>
            <button class="binary-primary-btn" id="bin2FAVerify" type="button" style="margin-top:10px;">✓ Verificar código</button>
            <button class="binary-secondary-btn" id="bin2FACancel" type="button" style="margin-top:8px;">Cancelar</button>
          </div>
        </div>
      </div>`;
  }

  function controlMarkup() {
    const marketAssets = assets.filter((asset) => currentMarket === "OTC" ? asset.endsWith("-OTC") : !asset.endsWith("-OTC"));
    const options = marketAssets.map((asset) =>
      `<option value="${esc(asset)}">${esc(asset.replace("-OTC", ""))}${asset.endsWith("-OTC") ? " — OTC" : ""}</option>`
    ).join("");

    const strategyOptions = Object.entries(strategies).map(([key, value]) =>
      `<option value="${esc(key)}">${esc(value.name)}</option>`
    ).join("");

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
            <div class="binary-market-label">Mercado</div>
            <div class="binary-market-switch">
              <button type="button" class="${currentMarket === "REGULAR" ? "active" : ""}" data-market="REGULAR">Mercado normal</button>
              <button type="button" class="${currentMarket === "OTC" ? "active" : ""}" data-market="OTC">OTC</button>
            </div>
            <label>Par atual<select id="binAsset">${options}</select></label>
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
          A análise considera somente o par atualmente selecionado.
        </div>
      </section>`;
  }

  function shellMarkup() {
    return `
      <div class="binary-analysis-page ${isFloating() ? "floating " : ""}settings-mode">
        <div class="binary-floating-grip binary-drag-handle" title="Clique e arraste com o botão esquerdo para mover a janela">⋮⋮ Arraste para mover</div>
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
    const reason = signal.signal === "AGUARDAR"
      ? (signal.accuracy_gate_reason || signal.reason || "Aguardando confirmação técnica.")
      : (signal.reason || "Aguardando confirmação técnica.");
    const payout = signal.payout ?? data.payout;
    const history = Array.isArray(accuracy.ultimos) ? accuracy.ultimos.slice(-12) : [];
    const indicatorVotes = Array.isArray(signal.votos) ? signal.votos : [];
    const strategyName = strategies[currentStrategy]?.name || currentStrategy;
    const action = direction === "CALL" ? "COMPRA" : direction === "PUT" ? "VENDA" : "ANALISANDO";
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

    const secondsToEntry = Math.max(0, Number(signal.seconds_to_entry ?? 0));
    const intervalSeconds = currentExpiry === "5min" ? 300 : 60;
    const expirationRemaining = Math.max(0, Number(signal.seconds_remaining ?? intervalSeconds));

    // Quando CALL/PUT já foi encontrado, o sinal vale a partir do instante
    // em que foi exibido, inclusive se a análise encontrou a condição no meio
    // da vela. O contador visual acompanha esse período, em vez de esperar
    // o próximo fechamento de vela para começar.
    const signalIsActive = direction === "CALL" || direction === "PUT";
    const timerNow = Date.now();
    // Nunca inicia contador enquanto a tela estiver em ANALISANDO/sem entrada.
    // O relógio só nasce quando CALL/PUT realmente foi emitido.
    currentEntryAt = signalIsActive ? timerNow : 0;
    currentExpiresAt = signalIsActive ? timerNow + intervalSeconds * 1000 : 0;

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
            <span class="binary-action-code">${direction === "CALL" ? "CALL" : direction === "PUT" ? "PUT" : "ANALISANDO"}</span>
          </div>
          <div class="binary-timer-block">
            <span id="binaryTimerLabel">${secondsToEntry > 0 ? "ENTRADA EM" : "EXPIRA EM"}</span>
            <div class="binary-timer" id="binaryTimer">${formatDuration(secondsToEntry > 0 ? secondsToEntry : expirationRemaining)}</div>
          </div>
        </div>
        <div class="binary-reason">${esc(reason)}
          <span class="binary-accuracy"> · acerto: <strong>${pct(accuracy.rate)}</strong> (${Number(accuracy.sample_size || 0)} sinais · ${Number(accuracy.wins || 0)} acertos)</span>
        </div>
        ${newsWarning ? "<div class=\"binary-news-warning\">⚠ " + esc(newsWarning) + "</div>" : ""}
        <div class="binary-history-row">${historyMarks}</div>

        <div class="binary-proximity-block">
          <div class="binary-proximity-head">
            <span>${proximityStage(signal).title}</span>
          </div>
          <div class="binary-proximity-track">
            <div class="binary-proximity-fill" style="width:${proximityPercent}%"></div>
          </div>
          <div class="binary-proximity-label">${esc(proximityLabel)}</div>
        </div>

        <div class="binary-divider"></div>

        <div class="binary-votes-row">
          <div class="binary-votes-counts">${countText}</div>
        </div>

        <div class="binary-indicators">${badges}</div>

        <div class="binary-signal-actions">
          <button class="binary-secondary-btn" id="binSignalSettings" type="button">⚙ Configurar</button>
          <button class="binary-primary-btn" id="binSignalAnalyze" type="button">🔎 Analisar novamente</button>
          ${direction === "AGUARDAR" ? '<button class="binary-secondary-btn" id="binCancelWaiting" type="button">✕ Cancelar análise</button>' : ""}
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

    document.getElementById("binCancelWaiting")?.addEventListener("click", cancelAnalysis);
  }

  function updateTimer() {
    const el = document.getElementById("binaryTimer");
    if (!el) return;
    const label = document.getElementById("binaryTimerLabel");
    const now = Date.now();

    // Sem sinal não existe entrada nem expiração. Portanto, sem contador.
    if (!currentExpiresAt || !currentEntryAt) {
      if (label) label.textContent = "SEM ENTRADA";
      el.textContent = "—";
      return;
    }

    if (currentEntryAt && now < currentEntryAt) {
      const seconds = Math.max(0, Math.ceil((currentEntryAt - now) / 1000));
      if (label) label.textContent = "ENTRADA EM";
      el.textContent = formatDuration(seconds);
      return;
    }

    const seconds = Math.max(0, Math.ceil((currentExpiresAt - now) / 1000));
    if (label) label.textContent = "EXPIRA EM";
    el.textContent = formatDuration(seconds);
    if (seconds <= 0) {
      clearInterval(countdownTimer);
      countdownTimer = null;
      const status = document.getElementById("binaryStatus");
      if (status) status.textContent = "⏱️ Expiração encerrada. Clique em “Analisar novamente” para gerar um novo sinal.";
    }
  }
  function show2FA(challengeId, message) {
    pending2FA = challengeId || "";
    const box = document.getElementById("bin2FABox");
    const msg = document.getElementById("binLoginMessage");
    const loginButton = document.getElementById("binLogin");
    if (box) box.style.display = "block";
    if (loginButton) loginButton.disabled = true;
    if (msg) msg.textContent = "🔐 " + (message || "Informe o código de verificação.");
    document.getElementById("bin2FACode")?.focus();
  }

  async function verify2FA() {
    const msg = document.getElementById("binLoginMessage");
    const button = document.getElementById("bin2FAVerify");
    const code = document.getElementById("bin2FACode")?.value.trim() || "";
    if (!pending2FA || !code) { if (msg) msg.textContent = "Informe o código recebido pela IQ Option."; return; }
    if (button) button.disabled = true;
    if (msg) msg.textContent = "⏳ Validando código...";
    try {
      const response = await fetch(API + "/login/2fa", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ challenge_id: pending2FA, code }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Código de verificação inválido.");
      session = data.session_id;
      sessionStorage.setItem(SESSION_KEY, session);
      pending2FA = "";
      await startConnected();
    } catch (error) {
      if (msg) msg.textContent = "🔴 " + error.message;
    } finally { if (button) button.disabled = false; }
  }

  async function cancel2FA() {
    if (pending2FA) { try { await fetch(API + "/login/2fa/cancel?challenge_id=" + encodeURIComponent(pending2FA), { method: "POST" }); } catch (_) {} }
    pending2FA = "";
    const box = document.getElementById("bin2FABox");
    const loginButton = document.getElementById("binLogin");
    if (box) box.style.display = "none";
    if (loginButton) loginButton.disabled = false;
    const msg = document.getElementById("binLoginMessage");
    if (msg) msg.textContent = "Verificação cancelada. Você pode tentar novamente.";
  }

  async function login() {
    const msg = document.getElementById("binLoginMessage");
    const button = document.getElementById("binLogin");
    if (!msg || !button) return;
    msg.textContent = "⏳ Conectando...";
    button.disabled = true;
    try {
      const response = await fetch(API + "/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: document.getElementById("binEmail").value.trim(), password: document.getElementById("binPassword").value, account: document.getElementById("binAccount").value })
      });
      const data = await response.json().catch(() => ({}));
      if (data.requires_2fa && data.challenge_id) { show2FA(data.challenge_id, data.message); return; }
      if (!response.ok) throw new Error(data.detail || "Não foi possível conectar.");
      session = data.session_id;
      sessionStorage.setItem(SESSION_KEY, session);
      await startConnected();
    } catch (error) { msg.textContent = "🔴 " + error.message; button.disabled = false; }
    finally { if (!pending2FA) button.disabled = false; }
  }
  async function logout() {
    resetSignalState();
    if (analysisController) {
      try { analysisController.abort(); } catch (_) {}
      analysisController = null;
    }
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

    const marketAssets = assets.filter((item) =>
      currentMarket === "OTC" ? item.endsWith("-OTC") : !item.endsWith("-OTC")
    );
    if (!marketAssets.includes(currentAsset)) {
      currentAsset = marketAssets[0] || assets[0] || "EURUSD";
    }
    if (!strategies[currentStrategy]) currentStrategy = Object.keys(strategies)[0] || "trend_pullback";
    if (!["1min", "5min"].includes(currentExpiry)) currentExpiry = "1min";
    saveState();
  }
  function selectedSignalFromData(data) {
    return data?.signals?.[currentExpiry] || {};
  }

  function signalRank(signal) {
    if (!signal || !["CALL", "PUT"].includes(signal.signal)) return -1;
    const proximity = Number(signal.proximity?.percent ?? 0);
    const confidence = Number(signal.confidence ?? 0);
    const score = Number(signal.score ?? 0);
    return proximity * 1000 + confidence * 10 + score;
  }

  function stopMonitoring() {
    clearInterval(monitoringTimer);
    monitoringTimer = null;
  }

  function resetSignalState() {
    stopMonitoring();
    currentSignalDirection = "AGUARDAR";
    currentSignalRank = -1;
    signalHoldUntil = 0;
  }

  function cancelAnalysis() {
    stopMonitoring();
    clearInterval(countdownTimer);
    countdownTimer = null;
    if (analysisController) {
      try { analysisController.abort(); } catch (_) {}
      analysisController = null;
    }
    currentExpiresAt = 0;
    currentSignalRank = -1;
    currentSignalDirection = "AGUARDAR";
    inFlight = false;
    resetSignalState();
    setSettingsScreen("Análise cancelada.");
    renderSettings();
    applyFloatingPosition();
    enableFloatingDrag();
  }

  function startSignalMonitoring() {
    stopMonitoring();
    signalHoldUntil = Date.now() + 60000;

    monitoringTimer = setInterval(async () => {
      if (!session || inFlight || !document.querySelector(".binary-analysis-page.signal-mode")) return;

      const now = Date.now();
      try {
        const candidate = await api(
          "/analyze/" + encodeURIComponent(currentAsset) +
          "?strategy=" + encodeURIComponent(currentStrategy) +
          "&expiry=" + encodeURIComponent(currentExpiry) +
          "&refresh=1"
        );
        const signal = selectedSignalFromData(candidate);
        const direction = signal.signal || "AGUARDAR";
        const rank = signalRank(signal);

        if (direction === "AGUARDAR") {
          const status = document.getElementById("binaryStatus");
          if (status && currentSignalDirection === "AGUARDAR") {
            status.textContent = "🔎 ANALISANDO MERCADO · aguardando dados técnicos válidos...";
          }
          return;
        }

            const canReplace = currentSignalDirection === "AGUARDAR"
          || now >= signalHoldUntil
          || rank > currentSignalRank + 0.5;

        if (canReplace) {
          currentSignalRank = rank;
          currentSignalDirection = direction;
          signalHoldUntil = Date.now() + 60000;
          renderCard(candidate);
          const holdSeconds = Math.max(0, Math.ceil((signalHoldUntil - Date.now()) / 1000));
          const status = document.getElementById("binaryStatus");
          if (status) {
            status.textContent = currentSignalDirection === "AGUARDAR"
              ? "🔎 ANALISANDO MERCADO..."
              : `✓ Sinal técnico ${currentSignalDirection} exibido. Proteção do sinal: ${formatDuration(holdSeconds)}.`;
          }
          saveState();
          clearInterval(countdownTimer);
          countdownTimer = setInterval(updateTimer, 250);
        }
      } catch (_) {
        // Falha transitória não substitui o sinal que já está na tela.
      }
    }, 5000);
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
      loadingHost.innerHTML = `<article class="binary-signal-card is-wait binary-analyzing-card"><div class="binary-card-top binary-drag-handle"><span>ANÁLISE EM ANDAMENTO</span><span>MONITORANDO</span></div><div class="binary-analyzing-icon">◌</div><div class="binary-analyzing-title" id="binaryAnalyzingTitle">ANALISANDO MERCADO</div><div class="binary-analyzing-subtitle" id="binaryAnalyzingSubtitle">Coletando candles, calculando indicadores e avaliando a estrutura técnica do par.</div><div class="binary-analysis-progress binary-thermometer"><div class="binary-thermometer-head"><span>PROGRESSO DA ANÁLISE</span><strong id="binaryAnalysisThermometerValue">ANALISANDO MERCADO</strong></div><div class="binary-proximity-track"><div class="binary-proximity-fill binary-analysis-thermometer-fill" id="binaryAnalysisThermometerFill" style="width:18%"></div></div></div><div class="binary-analyzing-label" id="binaryAnalyzingLabel">Lendo candles e preparando os indicadores...</div><div class="binary-signal-actions"><button class="binary-secondary-btn" id="binCancelAnalysis" type="button">✕ Cancelar análise</button></div></article>`;
      document.getElementById("binCancelAnalysis")?.addEventListener("click", cancelAnalysis);
      startAnalysisStageAnimation();
    }
    const manualButton = document.getElementById("binAnalyzeNow");
    if (manualButton) {
      manualButton.disabled = true;
      manualButton.textContent = "⏳ Analisando...";
    }
    try {
      if (status) status.textContent = `Verificando ${currentAsset} · ${expiryLabel(currentExpiry).toLowerCase()}...`;
      analysisController = new AbortController();
      const analysisTimeout = setTimeout(() => {
        try { analysisController?.abort(); } catch (_) {}
      }, 30000);
      const data = await api(
        "/analyze/" + encodeURIComponent(currentAsset) +
        "?strategy=" + encodeURIComponent(currentStrategy) +
        "&expiry=" + encodeURIComponent(currentExpiry) +
        "&refresh=1",
        { signal: analysisController.signal }
      );
      clearTimeout(analysisTimeout);
      analysisController = null;
      stopAnalysisStageAnimation();
      renderCard(data);
      renderSettings();
      if (status) {
        const candleCount = Number(data.selected_candle_count || 0);
        if (data.market === "fechado") {
          currentSignalDirection = "AGUARDAR";
          currentSignalRank = -1;
          stopMonitoring();
          status.textContent = `⏸️ ${currentAsset} está fechado. Se o equivalente OTC estiver disponível, selecione o mercado OTC.`;
        } else if (data.selected_data_ready) {
          const selected = selectedSignalFromData(data);
          currentSignalDirection = selected.signal || "AGUARDAR";
          currentSignalRank = signalRank(selected);
          status.textContent = currentSignalDirection === "AGUARDAR"
            ? `🔎 Dados processados (${candleCount} candles). ANALISANDO MERCADO...`
            : `✓ ${currentAsset} · ${expiryLabel(currentExpiry).toLowerCase()} · ${candleCount} candles processados · sinal técnico ${currentSignalDirection} · mercado ${data.market || "indisponível"}.`;
          startSignalMonitoring();
        } else {
          currentSignalDirection = "AGUARDAR";
          currentSignalRank = -1;
          stopMonitoring();
          status.textContent = `⚠️ ${currentAsset} · nenhum candle válido processado. Mercado ${data.market || "indisponível"}.`;
        }
      }
      saveState();
      clearInterval(countdownTimer);
      const selected = selectedSignalFromData(data);
      if (selected.signal === "CALL" || selected.signal === "PUT") {
        countdownTimer = setInterval(updateTimer, 250);
      } else {
        countdownTimer = null;
        currentEntryAt = 0;
        currentExpiresAt = 0;
      }
    } catch (error) {
      if (error?.name === "AbortError") {
        stopAnalysisStageAnimation();
        if (status) status.textContent = "⏱️ A análise excedeu 30 segundos ou foi cancelada. Verifique o par/mercado e tente novamente.";
        return;
      }
      if (loadingHost) {
        loadingHost.innerHTML = `
          <article class="binary-signal-card is-wait binary-error-card">
            <div class="binary-card-top binary-drag-handle">
              <span>ANÁLISE</span><span>ERRO</span>
            </div>
            <div class="binary-analyzing-title">Não foi possível concluir a análise</div>
            <div class="binary-reason">${esc(error.message)}</div>
            <div class="binary-signal-actions">
              <button class="binary-secondary-btn" id="binSignalSettingsError" type="button">⚙ Configurar</button>
              <button class="binary-primary-btn" id="binSignalRetry" type="button">🔎 Tentar novamente</button>
            </div>
          </article>`;
        document.getElementById("binSignalRetry")?.addEventListener("click", () => analyze());
        document.getElementById("binSignalSettingsError")?.addEventListener("click", () => {
          setSettingsScreen("Configuração carregada. Nenhuma nova análise foi executada.");
          renderSettings();
          applyFloatingPosition();
          enableFloatingDrag();
        });
      }
      if (status) status.textContent = "⚠️ " + error.message;
    } finally {
      stopAnalysisStageAnimation();
      analysisController = null;
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

    if (asset) {
      if ([...asset.options].some((option) => option.value === currentAsset)) {
        asset.value = currentAsset;
      } else if (asset.options.length) {
        currentAsset = asset.options[0].value;
        saveState();
      }
    }
    if (strategy) strategy.value = currentStrategy;

    document.querySelectorAll("[data-market]").forEach((button) => {
      button.addEventListener("click", () => {
        currentMarket = button.dataset.market === "OTC" ? "OTC" : "REGULAR";
        const marketAssets = assets.filter((item) => currentMarket === "OTC" ? item.endsWith("-OTC") : !item.endsWith("-OTC"));
        resetSignalState();
        currentAsset = marketAssets[0] || currentAsset;
        saveState();
        setSettingsScreen("Mercado " + currentMarket + " selecionado. Clique em “Analisar agora” para gerar o sinal.");
        renderSettings();
      });
    });

    asset?.addEventListener("change", () => {
      resetSignalState();
      currentAsset = asset.value;
      saveState();
      setSettingsScreen("Par alterado. Clique em “Analisar agora” para calcular o sinal.");
      renderSettings();
    });

    strategy?.addEventListener("change", () => {
      currentStrategy = strategy.value;
      saveState();
      setSettingsScreen("Estratégia alterada. Clique em “Analisar agora” para recalcular.");
    });

    document.querySelectorAll("[data-expiry]").forEach((button) => {
      button.addEventListener("click", () => {
        currentExpiry = button.dataset.expiry === "5min" ? "5min" : "1min";
        saveState();
        setSettingsScreen("Expiração selecionada. Clique em “Analisar agora” para calcular o sinal.");
        renderSettings();
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

  async function refreshCandlesOnly() {
    if (!session || inFlight) return;
    const btn = document.getElementById("binRefresh");
    const status = document.getElementById("binaryStatus");
    if (btn) { btn.disabled = true; btn.textContent = "⏳ Atualizando..."; }
    try {
      const data = await api("/candles/" + encodeURIComponent(currentAsset) + "?interval=60&count=120");
      const qtd = Array.isArray(data.candles) ? data.candles.length : 0;
      if (status) status.textContent = qtd > 0
        ? "✓ " + qtd + " candles recebidos para " + currentAsset + ". A conexão de mercado está respondendo."
        : "⚠️ Nenhum candle foi recebido para " + currentAsset + ". Verifique se o ativo está aberto (ou use OTC) e tente novamente.";
    } catch (error) {
      if (status) status.textContent = "⚠️ " + error.message;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "↻ Atualizar candles"; }
    }
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
    const handle = page?.querySelector(".binary-floating-grip") || page?.querySelector(".binary-drag-handle");
    if (!page || !handle || handle.dataset.dragBound === "1") return;
    handle.dataset.dragBound = "1";
    applyFloatingPosition();

    handle.addEventListener("pointerdown", (event) => {
      if (!isFloating() || event.button !== 0) return;
      if (event.target.closest("button, input, select, textarea, a")) return;
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
      page.classList.add("is-dragging");
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
      page.classList.remove("is-dragging");
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

      root.innerHTML = shellMarkup();
      await loadCatalog();
      setSettingsScreen("Conexão pronta. Clique em “Analisar agora” quando quiser iniciar.");
      renderSettings();
      enableFloatingDrag();

      clearInterval(refreshTimer);
    } catch (error) {
      renderLogin(error.message);
    }
  }

  function renderLogin(message = "") {
    const root = mount();
    if (!root) return;
    root.innerHTML = loginMarkup(message);
    document.getElementById("binLogin")?.addEventListener("click", login);
    document.getElementById("bin2FAVerify")?.addEventListener("click", verify2FA);
    document.getElementById("bin2FACancel")?.addEventListener("click", cancel2FA);
    document.getElementById("bin2FACode")?.addEventListener("keydown", (event) => { if (event.key === "Enter") verify2FA(); });
  }

  function init() {
    const root = mount();
    if (!root) return;
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