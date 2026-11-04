(() => {
  const API = "/api/opcoes-digitais";
  const KEY = "resolvei_opcoes_digitais_session";
  const FAVORITES_KEY = "resolvei_opcoes_digitais_favorites";
  let clockTimer = null;
  let historyTimer = null;
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));

  function sid() { return sessionStorage.getItem(KEY) || ""; }
  function clearSession() { sessionStorage.removeItem(KEY); }

  function getFavorites() {
    try {
      const value = JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]");
      return Array.isArray(value)
        ? [...new Set(value.filter((item) => typeof item === "string" && item.trim()))]
        : [];
    } catch {
      return [];
    }
  }

  function saveFavorites(items) {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(items)); } catch {}
  }

  function syncFavoriteToggle() {
    const button = $("odFavoriteToggle");
    const select = $("odPair");
    if (!button || !select) return;
    const active = !!select.value && getFavorites().includes(select.value);
    button.textContent = active ? "★" : "☆";
    button.classList.toggle("is-favorite", active);
    button.setAttribute("aria-pressed", String(active));
    button.title = active ? "Remover dos favoritos" : "Favoritar este ativo";
    button.setAttribute("aria-label", button.title);
  }

  function renderFavorites() {
    const host = $("odFavorites");
    const select = $("odPair");
    if (!host || !select) return;
    const items = getFavorites();
    const active = select.value;
    host.hidden = !items.length;
    if (!items.length) {
      host.innerHTML = "";
      return;
    }
    host.innerHTML =
      '<div class="od-favorites-head"><strong>ATIVOS FAVORITOS</strong><small>' +
      items.length + " ATIVO" + (items.length === 1 ? "" : "S") +
      '</small></div><div class="od-favorite-list">' +
      items.map((symbol) => {
        const available = [...select.options].some((option) => option.value === symbol);
        return '<div class="od-favorite-card' + (symbol === active ? " active" : "") + '">' +
          '<button type="button" class="od-fav-select" data-symbol="' + esc(symbol) + '"' +
          (available ? "" : " disabled") + "><span>" + esc(symbol) +
          "</span><small>" + (symbol === active ? "SELECIONADO" : "TROCAR ATIVO") +
          '</small></button><button type="button" class="od-fav-remove" data-remove-symbol="' +
          esc(symbol) + '" aria-label="Remover ' + esc(symbol) +
          ' dos favoritos" title="Remover dos favoritos">×</button></div>';
      }).join("") + "</div>";

    host.querySelectorAll(".od-fav-select").forEach((button) => {
      button.onclick = () => {
        select.value = button.dataset.symbol;
        renderFavorites();
        syncFavoriteToggle();
      };
    });
    host.querySelectorAll(".od-fav-remove").forEach((button) => {
      button.onclick = () => {
        saveFavorites(getFavorites().filter((symbol) => symbol !== button.dataset.removeSymbol));
        renderFavorites();
        syncFavoriteToggle();
      };
    });
  }

  function toggleFavorite() {
    const select = $("odPair");
    if (!select || !select.value) return;
    const favorites = getFavorites();
    saveFavorites(favorites.includes(select.value)
      ? favorites.filter((symbol) => symbol !== select.value)
      : [...favorites, select.value]);
    renderFavorites();
    syncFavoriteToggle();
  }

  async function call(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (sid()) headers["X-IQ-Session"] = sid();
    let response;
    try {
      response = await fetch(API + path, { ...options, headers });
    } catch {
      throw new Error("Não foi possível alcançar a API do Opções Digitais. Verifique a conexão com o Resolvei.");
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
    const host = $("opcoesDigitaisToolHost");
    if (!host) return;
    clearInterval(clockTimer);
    host.innerHTML =
      '<div class="od-login"><small>RESOLVEI / IQ OPTION</small>' +
      '<h1>opções <span>digitais</span></h1>' +
      '<p>Este módulo possui <b>login próprio</b>. A sessão não é compartilhada com o Analista Bin, Guru, Visão Opções ou outras ferramentas.</p>' +
      '<form id="odLoginForm"><label>E-MAIL IQ OPTION<input id="odEmail" type="email" autocomplete="username" required></label>' +
      '<label>SENHA IQ OPTION<input id="odPassword" type="password" autocomplete="current-password" required></label>' +
      '<button id="odLoginBtn" type="submit">CONECTAR À IQ OPTION</button></form><div id="odLoginMsg"></div></div>';

    $("odLoginForm").onsubmit = async (event) => {
      event.preventDefault();
      const button = $("odLoginBtn");
      const message = $("odLoginMsg");
      button.disabled = true;
      button.textContent = "CONECTANDO…";
      message.textContent = "";
      try {
        const data = await call("/login", {
          method: "POST",
          body: JSON.stringify({
            email: $("odEmail").value.trim(),
            password: $("odPassword").value
          })
        });
        sessionStorage.setItem(KEY, data.session_id);
        await render();
      } catch (error) {
        message.textContent = "⚠️ " + error.message;
      } finally {
        if ($("odLoginBtn")) {
          $("odLoginBtn").disabled = false;
          $("odLoginBtn").textContent = "CONECTAR À IQ OPTION";
        }
      }
    };
  }

  async function loadAssets() {
    const select = $("odPair");
    if (!select) return;
    select.innerHTML = "<option>ATUALIZANDO ATIVOS…</option>";
    try {
      const data = await call("/assets");
      select.innerHTML = "";
      const labels = {
        binary: "BINÁRIA", turbo: "TURBO", digital: "DIGITAL",
        forex: "FOREX", cfd: "CFD / AÇÕES / COMMODITIES / ETFs",
        crypto: "CRIPTO", all: "TODOS OS ATIVOS"
      };
      Object.entries(data.groups || {}).forEach(([kind, assets]) => {
        const group = document.createElement("optgroup");
        group.label = (labels[kind] || kind.toUpperCase()) + " · " + assets.length + " ativos";
        assets.forEach((asset) => {
          const option = document.createElement("option");
          option.value = asset.symbol;
          option.textContent = asset.symbol + (asset.open === false ? " · FECHADO" : "");
          group.appendChild(option);
        });
        select.appendChild(group);
      });
      const first = [...select.options].find((option) =>
        option.value && !option.textContent.includes("FECHADO"));
      if (first) first.selected = true;
    } catch (error) {
      select.innerHTML = '<option value="">ERRO AO CARREGAR ATIVOS</option>';
      $("odError").textContent = "⚠️ " + error.message;
    }
    renderFavorites();
    syncFavoriteToggle();
  }

  function renderHistory(data) {
    const host = $("odHistory");
    if (!host) return;
    const rate = data.winRate == null ? "—" : Number(data.winRate).toFixed(1) + "%";
    const rows = (data.records || []).slice(0, 5);
    host.innerHTML =
      '<div class="od-history-head"><div><small>DESEMPENHO REGISTRADO</small><strong>' +
      rate + '</strong><span>taxa de acerto simulada</span></div><div class="od-history-count">' +
      '<b>' + Number(data.sampleSize || 0) + '</b><small>RESOLVIDOS</small></div></div>' +
      '<div class="od-history-stats"><span class="win">WIN <b>' + Number(data.wins || 0) +
      '</b></span><span class="loss">LOSS <b>' + Number(data.losses || 0) +
      '</b></span><span class="draw">DRAW <b>' + Number(data.draws || 0) +
      '</b></span><span class="pending">PENDENTES <b>' + Number(data.pending || 0) +
      '</b></span></div>' +
      (rows.length ? '<div class="od-history-list">' + rows.map((record) => {
        const status = record.outcome || "PENDENTE";
        const cls = status === "WIN" ? "win" : status === "LOSS" ? "loss" : status === "DRAW" ? "draw" : "pending";
        const time = record.createdAt
          ? new Date(Number(record.createdAt) * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
          : "--:--";
        return '<div class="od-history-row"><span><b>' + esc(record.symbol) +
          '</b><small>' + esc(record.timeframe) + " · " + esc(record.strategyLabel || "") +
          " · " + time + '</small></span><span class="' + cls + '">' + esc(status) + "</span></div>";
      }).join("") + "</div>" : '<p class="od-history-empty">Os resultados das próximas análises aparecerão aqui.</p>') +
      '<p class="od-history-note">' + esc(data.note || "Resultados simulados com candles fechados.") +
      (data.storage === "memoria" ? " Histórico temporário nesta instância do servidor." : " Histórico sincronizado na nuvem.") +
      "</p>";
  }

  async function loadHistory() {
    if (!sid() || !$("odHistory")) return;
    try {
      const data = await call("/history");
      renderHistory(data);
    } catch (error) {
      const host = $("odHistory");
      if (host) host.innerHTML = '<p class="od-history-empty">Histórico indisponível no momento.</p>';
      if (!sid()) login();
    }
  }

  async function render() {
    const host = $("opcoesDigitaisToolHost");
    if (!host) return;
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

    clearInterval(clockTimer);
    host.innerHTML =
      '<div class="od-app"><header><div><small>RESOLVEI / TRADING ANALYTICS</small>' +
      '<h1>opções <span>digitais</span></h1></div><div class="od-head-actions"><b>● IQ OPTION</b>' +
      '<button id="odLogout" type="button">SAIR</button></div></header>' +
      '<section class="od-config"><label>ATIVO<div class="od-asset-picker"><select id="odPair"><option>ATUALIZANDO ATIVOS…</option></select>' +
      '<button id="odFavoriteToggle" type="button" aria-pressed="false" aria-label="Favoritar este ativo" title="Favoritar este ativo">☆</button></div></label>' +
      '<label>ESTRATÉGIA<select id="odStrategy"><option value="auto">AUTOMÁTICA</option><option value="trend">TENDÊNCIA</option>' +
      '<option value="breakout">ROMPIMENTO</option><option value="reversion">REVERSÃO</option></select></label>' +
      '<label>TIMEFRAME<select id="odTf"><option value="1m">M1 · EXPIRAÇÃO 1 MIN</option><option value="5m">M5 · EXPIRAÇÃO 5 MIN</option></select></label>' +
      '<button id="odAnalyze" type="button">ANALISAR</button></section>' +
      '<section id="odFavorites" class="od-favorites" hidden aria-label="Ativos favoritos"></section>' +
      '<section class="od-grid"><article id="odSignal" class="od-card od-neutral"><small>DECISÃO</small>' +
      '<strong>AGUARDANDO</strong><span>Analise para identificar o regime e as confirmações.</span></article>' +
      '<article class="od-card"><small>CONFLUÊNCIA</small><div class="od-score"><b id="odScore">0</b>%</div>' +
      '<div class="od-meter"><i id="odMeter"></i></div><div class="od-clock">PRÓXIMA VELA <b id="odClock">--</b></div></article></section>' +
      '<section class="od-context"><div><small>REGIME DE MERCADO</small><b id="odRegime">Aguardando análise</b></div>' +
      '<div><small>CONFIRMAÇÃO SUPERIOR</small><b id="odHtf">--</b></div><div><small>GRUPOS CONFIRMADOS</small><b id="odGroups">--</b></div></section>' +
      '<section class="od-card"><div class="od-title">CONFLUÊNCIA POR GRUPO <span id="odStrategyName">Automática</span></div>' +
      '<div id="odGroupScores" class="od-group-scores"></div></section>' +
      '<section class="od-card"><div class="od-title">VERIFICAÇÕES TÉCNICAS <span id="odIndicatorCount">--</span></div>' +
      '<div id="odIndicators" class="od-indicators"></div><div id="odReasons" class="od-reasons"></div></section>' +
      '<section class="od-card od-history" id="odHistory"><p class="od-history-empty">Carregando histórico…</p></section>' +
      '<div id="odError"></div><p class="od-note">A pontuação representa confluência técnica, não probabilidade de acerto. Histórico baseado em simulação pela próxima vela fechada; não representa ordens executadas.</p></div>';

    $("odLogout").onclick = async () => {
      try { await call("/logout", { method: "POST" }); } catch {}
      clearSession();
      clearInterval(clockTimer);
      clearTimeout(historyTimer);
      login();
    };
    $("odAnalyze").onclick = analyze;
    $("odPair").onchange = () => { renderFavorites(); syncFavoriteToggle(); };
    $("odFavoriteToggle").onclick = toggleFavorite;

    void loadHistory();
    await loadAssets();
  }

  async function analyze() {
    const button = $("odAnalyze");
    const errorHost = $("odError");
    if (!button || !errorHost) return;
    button.disabled = true;
    button.textContent = "ANALISANDO…";
    errorHost.textContent = "";
    try {
      const symbol = $("odPair").value;
      if (!symbol) throw new Error("Nenhum ativo disponível para análise.");
      const data = await call("/analyze", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          timeframe: $("odTf").value,
          strategy: $("odStrategy").value
        })
      });
      show(data);
      clock(data.nextCandleAt);
      clearTimeout(historyTimer);
      historyTimer = setTimeout(loadHistory, 500);
    } catch (error) {
      errorHost.textContent = "⚠️ " + error.message;
      if (!sid()) login();
    } finally {
      if ($("odAnalyze")) {
        $("odAnalyze").disabled = false;
        $("odAnalyze").textContent = "ANALISAR";
      }
    }
  }

  function show(data) {
    const card = $("odSignal");
    const isCall = data.direction === "CALL";
    const isPut = data.direction === "PUT";
    card.className = "od-card " + (isCall ? "od-call" : isPut ? "od-put" : "od-neutral");
    card.querySelector("strong").textContent = isCall
      ? "COMPRAR · CALL" : isPut ? "VENDER · PUT" : "SEM SINAL";
    const description = data.signal + " · " + data.score + " pontos de confluência";
    card.querySelector("span").textContent = description;
    $("odScore").textContent = Number(data.score).toFixed(0);
    $("odMeter").style.width = Math.min(100, Number(data.score)) + "%";
    $("odRegime").textContent = data.marketRegimeLabel || "--";
    $("odHtf").textContent = (data.higherTimeframe || "--") + " · " + (data.higherDirection || "--");
    $("odGroups").textContent = Number(data.confirmedGroups || 0) + " de 3";
    $("odStrategyName").textContent = data.strategyLabel || "Automática";
    $("odIndicatorCount").textContent = (data.indicators || []).length + " verificações";

    const labels = {
      trend: "TENDÊNCIA · 30%",
      momentum: "MOMENTUM · 25%",
      structure: "ESTRUTURA · 25%",
      conditions: "CONDIÇÕES · FILTRO"
    };
    const groups = data.groupScores || {};
    $("odGroupScores").innerHTML = Object.entries(labels).map(([key, label]) => {
      const group = groups[key] || {};
      if (key === "conditions") {
        return '<div class="od-group-score"><span>' + label + '</span><b class="' +
          (group.activeVotes ? "win" : "loss") + '">' +
          (group.activeVotes ? "APROVADO" : "BLOQUEADO") +
          '</b><small>Filtro não soma pontos direcionais</small></div>';
      }
      return '<div class="od-group-score"><span>' + label + '</span><b>CALL ' +
        Number(group.call || 0).toFixed(0) + '</b><b>PUT ' +
        Number(group.put || 0).toFixed(0) + "</b></div>";
    }).join("");

    $("odIndicators").innerHTML = (data.indicators || []).map((indicator) => {
      const matches = indicator.active;
      const direction = indicator.direction === 1 ? "CALL" : indicator.direction === -1 ? "PUT" : "NEUTRO";
      const cls = indicator.direction === 1 ? "call" : indicator.direction === -1 ? "put" : "off";
      return '<div class="od-ind ' + (matches ? "on " : "") + cls + '"><b>' +
        (matches ? "✓" : indicator.direction === 0 ? "·" : "↔") + '</b><span>' +
        esc(indicator.name) + '<small>' + esc(indicator.group || "") + '</small></span><em>' +
        direction + "</em></div>";
    }).join("");

    const reasons = data.blockingReasons || [];
    const notes = [];
    if (!data.volumeDataAvailable) notes.push("Volume não fornecido pela corretora; indicadores de volume foram desconsiderados.");
    if (reasons.length) notes.push(...reasons);
    if (!notes.length) notes.push("Filtros de mercado e confirmação aprovados.");
    $("odReasons").innerHTML = notes.map((reason) => "<p>" + esc(reason) + "</p>").join("");
  }

  function clock(timestamp) {
    clearInterval(clockTimer);
    const update = () => {
      const element = $("odClock");
      if (element) element.textContent = Math.max(0, Math.ceil(Number(timestamp) - Date.now() / 1000)) + "s";
    };
    update();
    clockTimer = setInterval(update, 250);
  }

  window.renderAnalistaBin = render;
  function boot() {
    if ((location.hash || "").includes("/ferramenta/opcoes-digitais")) render();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  window.addEventListener("hashchange", () => {
    if ((location.hash || "").includes("/ferramenta/opcoes-digitais")) render();
    else clearInterval(clockTimer);
  });
})();