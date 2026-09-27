(function () {
  const API = "/api/iq";
  const SESSION_KEY = "resolvei_iq_session";
  let session = sessionStorage.getItem(SESSION_KEY) || "";
  let assets = [];
  let strategies = {};
  let currentAsset = localStorage.getItem("resolvei_binary_asset") || "EURUSD";
  let currentStrategy = localStorage.getItem("resolvei_binary_strategy") || "trend_pullback";
  let refreshTimer = null;
  let countdownTimer = null;
  let currentExpiresAt = 0;

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"
  }[c]));

  const pct = (v) => v == null ? "—" : Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  }) + "%";

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
    const assetOptions = assets.map(a => `<option value="${esc(a)}">${esc(a)}</option>`).join("");
    const strategyOptions = Object.entries(strategies).map(([key, value]) =>
      `<option value="${esc(key)}">${esc(value.name)}</option>`).join("");
    return `
      <details class="binary-settings">
        <summary>⚙ Configuração da análise</summary>
        <div class="binary-settings-grid">
          <label>Ativo<select id="binAsset">${assetOptions}</select></label>
          <label>Estratégia<select id="binStrategy">${strategyOptions}</select></label>
          <button class="binary-secondary-btn" id="binRefresh">↻ Atualizar</button>
          <button class="binary-secondary-btn" id="binLogout">Desconectar</button>
        </div>
        <div class="binary-disclaimer">Integração com a API comunitária não oficial da IQ Option. Somente análise; nenhuma ordem é enviada.</div>
      </details>`;
  }

  function shellMarkup() {
    return `
      <div class="binary-analysis-page">
        <div id="binaryCardHost"></div>
        <div id="binaryStatus" class="binary-status-line"></div>
        <div id="binarySettingsHost"></div>
      </div>`;
  }

  function renderCard(data) {
    const signal = data?.signals?.["1min"] || {};
    const accuracy = signal.historical_accuracy || {};
    const votes = signal.resumo_votos || {};
    const direction = signal.signal || "AGUARDAR";
    const stateClass = direction === "CALL" ? "is-call" : direction === "PUT" ? "is-put" : "is-wait";
    const locked = signal.locked || signal.seconds_remaining > 0;
    const reason = signal.reason || "Aguardando confirmação técnica.";
    const payout = signal.payout ?? data.payout;
    const voteConfidence = votes.confianca ?? signal.confidence ?? null;
    const history = Array.isArray(accuracy.ultimos) ? accuracy.ultimos.slice(-12) : [];
    const indicatorVotes = Array.isArray(signal.votos) ? signal.votos : [];

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

    const countText = `▲ ${Number(votes.bulls || 0)} CALL <span class="vote-red">▼ ${Number(votes.bears || 0)} PUT</span> <span class="vote-blue">● ${Number(votes.neutros || votes.neutrals || 0)} neutros</span>`;

    const remaining = Math.max(0, Number(signal.seconds_remaining || 0));
    currentExpiresAt = Date.now() + remaining * 1000;

    const formattedDirection = direction === "CALL" ? "CALL" : direction === "PUT" ? "PUT" : "AGUARDAR";
    const lockText = locked ? "SINAL FIXADO" : "ANÁLISE";

    const host = document.getElementById("binaryCardHost");
    if (!host) return;

    host.innerHTML = `
      <article class="binary-signal-card ${stateClass}">
        <div class="binary-card-top">
          <span>EXPIRAÇÃO 1 MINUTO</span>
          <span>${lockText}</span>
        </div>

        <div class="binary-card-main">
          <div class="binary-direction">${formattedDirection}</div>
          <div class="binary-timer" id="binaryTimer">${formatSeconds(remaining)}</div>
        </div>

        <div class="binary-payout">Payout ${payout == null ? "—" : pct(payout)}</div>

        <div class="binary-reason">${esc(reason)}
          <span class="binary-accuracy"> · acerto: <strong>${pct(accuracy.rate)}</strong> (${Number(accuracy.sample_size || 0)} sinais · ${Number(accuracy.wins || 0)} acertos)</span>
        </div>

        <div class="binary-history-row">${historyMarks}</div>

        <div class="binary-divider"></div>

        <div class="binary-votes-row">
          <div class="binary-votes-counts">${countText}</div>
          <div class="binary-confidence">confiança ${pct(voteConfidence)}</div>
        </div>

        <div class="binary-indicators">${badges}</div>
      </article>`;

    updateTimer();
  }

  function formatSeconds(seconds) {
    const s = Math.max(0, Math.floor(Number(seconds || 0)));
    return `00:${String(s).padStart(2, "0")}`;
  }

  function updateTimer() {
    const el = document.getElementById("binaryTimer");
    if (!el) return;
    const seconds = Math.max(0, Math.ceil((currentExpiresAt - Date.now()) / 1000));
    el.textContent = formatSeconds(seconds);
    if (seconds <= 0) {
      clearInterval(countdownTimer);
      countdownTimer = null;
      analyze(true);
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
    if (countdownTimer) clearInterval(countdownTimer);
    if (refreshTimer) clearInterval(refreshTimer);
    renderLogin();
  }

  async function loadCatalog() {
    const [assetData, strategyData] = await Promise.all([api("/assets"), api("/strategies")]);
    assets = Array.isArray(assetData.assets) ? assetData.assets : [];
    strategies = strategyData.strategies || {};
    if (!assets.includes(currentAsset)) currentAsset = assets[0] || "EURUSD";
    if (!strategies[currentStrategy]) currentStrategy = Object.keys(strategies)[0] || "trend_pullback";
  }

  async function analyze(force = false) {
    if (!session) return;
    const cardHost = document.getElementById("binaryCardHost");
    const status = document.getElementById("binaryStatus");
    if (!cardHost) return;
    if (!force && currentExpiresAt > Date.now() + 1000) return;

    try {
      if (status) status.textContent = "Atualizando sinal...";
      const data = await api("/analyze/" + encodeURIComponent(currentAsset) + "?strategy=" + encodeURIComponent(currentStrategy));
      renderCard(data);
      renderSettings();
      if (status) status.textContent = `${currentAsset} · mercado ${data.market || "indisponível"}`;
      localStorage.setItem("resolvei_binary_asset", currentAsset);
      localStorage.setItem("resolvei_binary_strategy", currentStrategy);
      if (countdownTimer) clearInterval(countdownTimer);
      countdownTimer = setInterval(updateTimer, 250);
    } catch (error) {
      if (status) status.textContent = "⚠️ " + error.message;
    }
  }

  function renderSettings() {
    const host = document.getElementById("binarySettingsHost");
    if (!host) return;
    host.innerHTML = controlMarkup();
    const asset = document.getElementById("binAsset");
    const strategy = document.getElementById("binStrategy");
    asset.value = currentAsset;
    strategy.value = currentStrategy;
    asset.onchange = () => { currentAsset = asset.value; analyze(true); };
    strategy.onchange = () => { currentStrategy = strategy.value; analyze(true); };
    document.getElementById("binRefresh").onclick = () => analyze(true);
    document.getElementById("binLogout").onclick = logout;
  }

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
      await analyze(true);
      if (refreshTimer) clearInterval(refreshTimer);
      refreshTimer = setInterval(() => analyze(false), 1000);
    } catch (error) {
      renderLogin(error.message);
    }
  }

  function renderLogin(message = "") {
    const root = mount();
    if (!root) return;
    root.innerHTML = loginMarkup(message);
    document.getElementById("binLogin").onclick = login;
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
