(() => {
  const API = "/api/consultor-senior";
  const KEY = "resolvei_consultor_senior_iq_session";
  let assetNames = [];
  let monitoring = false;
  let monitorCycle = 0;
  let monitorToken = 0;

  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;" }[c]));

  function sid() {
    return sessionStorage.getItem(KEY) || "";
  }

  function clearSession() {
    sessionStorage.removeItem(KEY);
  }

  async function call(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (sid()) headers["X-IQ-Session"] = sid();

    let response;
    try {
      response = await fetch(API + path, { ...options, headers });
    } catch (_) {
      throw new Error("Não foi possível alcançar a API do Consultor Sênior.");
    }

    let data = {};
    try { data = await response.json(); } catch (_) {}

    if (!response.ok) {
      if (response.status === 401) clearSession();
      throw new Error(data.detail || ("API HTTP " + response.status));
    }

    return data;
  }

  function loginView() {
    const h = $("consultorSeniorToolHost");
    if (!h) return;

    h.innerHTML =
      '<div class="cs-login">' +
        '<div class="cs-kicker">RESOLVEI / IQ OPTION</div>' +
        '<h1>consultor <span>sênior</span></h1>' +
        '<p>Leitura de mercado por contexto, estrutura, preço e confirmação. A sessão da IQ Option é própria desta ferramenta.</p>' +
        '<form id="csLoginForm">' +
          '<label>E-MAIL IQ OPTION<input id="csEmail" type="email" autocomplete="username" required></label>' +
          '<label>SENHA IQ OPTION<input id="csPassword" type="password" autocomplete="current-password" required></label>' +
          '<button id="csLoginBtn" type="submit">CONECTAR À IQ OPTION</button>' +
        '</form>' +
        '<div id="csLoginMsg" class="cs-msg"></div>' +
        '<div class="cs-note">O Consultor Sênior é somente analítico e não envia ordens.</div>' +
      '</div>';

    $("csLoginForm").onsubmit = async event => {
      event.preventDefault();
      const button = $("csLoginBtn");
      const message = $("csLoginMsg");
      button.disabled = true;
      button.textContent = "CONECTANDO…";
      message.textContent = "";

      try {
        const data = await call("/login", {
          method: "POST",
          body: JSON.stringify({
            email: $("csEmail").value.trim(),
            password: $("csPassword").value
          })
        });
        sessionStorage.setItem(KEY, data.session_id);
        await renderConnected();
      } catch (error) {
        message.textContent = "⚠️ " + error.message;
      } finally {
        button.disabled = false;
        button.textContent = "CONECTAR À IQ OPTION";
      }
    };
  }

  function appView() {
    const h = $("consultorSeniorToolHost");
    if (!h) return;

    h.innerHTML =
      '<div class="cs-app">' +
        '<header class="cs-header">' +
          '<div>' +
            '<div class="cs-kicker">RESOLVEI / MARKET INTELLIGENCE</div>' +
            '<h1>consultor <span>sênior</span></h1>' +
            '<p>O mercado é interpretado antes dos indicadores: contexto, estrutura, zonas, price action e gatilho.</p>' +
          '</div>' +
          '<div class="cs-header-right"><b>● IQ OPTION</b><button id="csLogout" type="button">SAIR</button></div>' +
        '</header>' +

        '<section class="cs-control card">' +
          '<div class="cs-field">' +
            '<label for="csAsset">ATIVO PARA CONSULTA</label>' +
            '<select id="csAsset"><option value="">SELECIONE UM ATIVO</option></select>' +
          '</div>' +
          '<button id="csConsult" type="button">CONSULTAR</button>' +
        '</section>' +
        '<div class="cs-ai-choice"><span>TIMEFRAME E EXPIRAÇÃO</span><b>DETERMINADOS PELO CONSULTOR</b><small>O sistema compara 1m, 5m e 15m e escolhe a combinação que apresentar o melhor gatilho.</small></div>' +

        '<div id="csProgress" class="cs-progress" hidden><span></span><b id="csProgressTitle">Monitorando o mercado…</b><small id="csProgressDetail">Comparando 15m → 5m → 1m · contexto → estrutura → gatilho</small></div>' +
        '<div id="csError" class="cs-msg"></div>' +
        '<main id="csResult"><div class="cs-empty"><strong>Escolha um ativo e clique em CONSULTAR.</strong><span>O Consultor Sênior fará uma leitura multi-timeframe e procurará o melhor gatilho disponível.</span></div></main>' +
        '<footer class="cs-foot"><span id="csMeta">Sessão IQ Option ativa</span><span>IA automática · sem execução de ordens</span></footer>' +
      '</div>';

    $("csLogout").onclick = async () => {
      try { await call("/logout", { method: "POST" }); } catch (_) {}
      clearSession();
      renderRoute();
    };

    $("csConsult").onclick = () => monitoring ? stopMonitoring() : consult();
  }

  function progress(show, cycle = 0) {
    const box = $("csProgress");
    const button = $("csConsult");
    const asset = $("csAsset")?.value || "";
    if (box) box.hidden = !show;

    if (show) {
      $("csProgressTitle").textContent = cycle
        ? "Analisando " + asset + " · ciclo " + cycle
        : "Monitorando o mercado…";
      $("csProgressDetail").textContent =
        "15m → 5m → 1m · contexto → estrutura → regiões → price action → gatilho";
    }

    if (button) {
      button.disabled = false;
      button.textContent = show ? "PARAR CONSULTA" : "CONSULTAR";
    }

    const select = $("csAsset");
    if (select) select.disabled = show;
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function stopMonitoring() {
    monitoring = false;
    monitorToken += 1;
    progress(false);
    const error = $("csError");
    if (error) error.textContent = "Monitoramento interrompido pelo usuário.";
  }

  async function loadAssets() {
    const select = $("csAsset");
    if (!select) return;

    try {
      const data = await call("/assets");
      assetNames = (data.assets || [])
        .map(x => x.symbol)
        .filter(Boolean)
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));

      select.innerHTML =
        '<option value="">SELECIONE UM ATIVO</option>' +
        assetNames.map(x => '<option value="' + esc(x) + '">' + esc(x) + '</option>').join("");

      $("csMeta").textContent = "IQ Option ativa · " + assetNames.length + " ativos disponíveis";
    } catch (error) {
      $("csMeta").textContent = "IQ Option ativa · catálogo indisponível";
      const err = $("csError");
      if (err) err.textContent = "⚠️ Não foi possível carregar o catálogo de ativos: " + error.message;
    }
  }

  function resultCard(a) {
    const isCall = a.decision === "CALL";
    const isPut = a.decision === "PUT";
    const cls = isCall ? "call" : isPut ? "put" : "neutral";
    const decision = isCall ? "COMPRA · CALL" : isPut ? "VENDA · PUT" : "SEM OPERAÇÃO";

    const statusMap = {
      AGORA: "ENTRADA AGORA",
      PROXIMO: "SINAL PRÓXIMO",
      AGUARDAR: "AGUARDAR GATILHO",
      "NAO OPERAR": "NÃO OPERAR"
    };

    const status = statusMap[a.status] || a.status || "AGUARDAR";
    const confidence = Number(a.confidence || 0);

    return (
      '<section class="cs-decision ' + cls + '">' +
        '<div>' +
          '<small>DECISÃO DO CONSULTOR</small>' +
          '<h2>' + decision + '</h2>' +
          '<p>' + esc(status) + '</p>' +
        '</div>' +
        '<div class="cs-confidence"><span>CONFIANÇA</span><strong>' + confidence.toFixed(1) + '%</strong></div>' +
      '</section>' +

      '<section class="cs-summary">' +
        '<strong>' + esc(a.summary || "Análise concluída.") + '</strong>' +
        '<div class="cs-summary-grid">' +
          summaryItem("EXPIRAÇÃO", (a.expiry_minutes || "—") + " min") +
          summaryItem("PREÇO OBSERVADO", a.current_price == null ? "—" : String(a.current_price)) +
          summaryItem("TIMEFRAME", a.timeframe || "—") +
          summaryItem("DADOS", a.data_quality || "moderada") +
        '</div>' +
      '</section>' +

      '<section class="cs-analysis-grid">' +
        metric("ESTRUTURA", a.structure) +
        metric("TENDÊNCIA", a.trend) +
        metric("ZONA", a.zone) +
        metric("GATILHO", a.trigger) +
        metric("MOMENTUM", a.momentum) +
        metric("VOLATILIDADE", a.volatility) +
        metric("PRICE ACTION", a.price_action) +
        metric("POR QUE AGORA?", a.why_now, true) +
      '</section>' +

      '<section class="cs-lists">' +
        '<div><h3>CONFLUÊNCIAS</h3><ul>' + listItems(a.confluences, "Nenhuma confluência destacada.") + '</ul></div>' +
        '<div><h3>RISCOS / CONTRADIÇÕES</h3><ul>' + listItems(a.risks, "Nenhum risco adicional informado.") + '</ul></div>' +
      '</section>' +

      (a.facts_warning ? '<div class="cs-facts">⚠️ <b>Fatos relevantes:</b> ' + esc(a.facts_warning) + '</div>' : '') +

      '<div class="cs-disclaimer">Somente análise informativa. O Consultor Sênior não envia ordens à IQ Option. A confiança é probabilística e não representa garantia de resultado.</div>'
    );
  }

  function summaryItem(title, value) {
    return '<div><small>' + title + '</small><b>' + esc(value) + '</b></div>';
  }

  function metric(title, value, wide) {
    return '<article class="cs-metric' + (wide ? ' wide' : '') + '"><small>' + title + '</small><p>' + esc(value || "—") + '</p></article>';
  }

  function listItems(items, empty) {
    const values = Array.isArray(items) ? items : [];
    return values.length
      ? values.map(x => '<li>' + esc(x) + '</li>').join("")
      : '<li class="muted">' + esc(empty) + '</li>';
  }

  async function consult() {
    const asset = ($("csAsset").value || "").trim().toUpperCase();
    const error = $("csError");
    const result = $("csResult");

    if (!asset) {
      error.textContent = "Selecione o ativo que será analisado.";
      return;
    }

    error.textContent = "";
    monitoring = true;
    monitorCycle = 0;
    const token = ++monitorToken;

    progress(true, 0);

    result.innerHTML =
      '<div class="cs-thinking">' +
        '<div class="cs-spinner"></div>' +
        '<strong>O Consultor está procurando um ponto de entrada…</strong>' +
        '<span>Ele vai continuar analisando o ativo até encontrar um gatilho confirmado. Timeframe e expiração serão escolhidos automaticamente.</span>' +
      '</div>';

    while (monitoring && token === monitorToken) {
      monitorCycle += 1;
      progress(true, monitorCycle);

      try {
        const data = await call("/consult", {
          method: "POST",
          body: JSON.stringify({ symbol: asset })
        });

        if (data.found && data.analysis) {
          monitoring = false;
          result.innerHTML = resultCard(data.analysis);

          const provider = data.analysis?.ai_provider || "IA";
          const model = data.analysis?.ai_model || data.analysis?.gemini_model || "";
          const tf = data.analysis?.timeframe || "—";
          const exp = data.analysis?.expiry_minutes || "—";
          $("csMeta").textContent =
            provider + (model ? " · " + model : "") +
            " · " + tf + " · expiração " + exp + " min · ENTRADA ENCONTRADA";

          progress(false);
          return;
        }

        error.textContent = "";
        result.innerHTML =
          '<div class="cs-thinking">' +
            '<div class="cs-spinner"></div>' +
            '<strong>Nenhum gatilho confirmado ainda.</strong>' +
            '<span>O Consultor continua monitorando ' + esc(asset) + ' e aguardará uma configuração de entrada com confiança suficiente.</span>' +
          '</div>';

        const waitSeconds = Math.max(15, Math.min(45, Number(data.next_check_seconds || 25)));
        $("csProgressDetail").textContent =
          "Próxima leitura em " + waitSeconds + "s · comparando 15m → 5m → 1m";

        await sleep(waitSeconds * 1000);
      } catch (ex) {
        if (!monitoring || token !== monitorToken) break;

        // Erros de provedor/candles podem ser transitórios. Não encerramos o
        // monitoramento: mostramos o problema e tentamos novamente.
        error.textContent = "⚠️ " + ex.message + " · nova tentativa automática.";
        result.innerHTML =
          '<div class="cs-thinking">' +
            '<div class="cs-spinner"></div>' +
            '<strong>Reconectando a análise…</strong>' +
            '<span>O Consultor continuará tentando enquanto a sessão da IQ Option estiver ativa.</span>' +
          '</div>';

        const retrySeconds = /429|rate limit|limite/i.test(ex.message) ? 30 : 15;
        $("csProgressDetail").textContent =
          "Nova tentativa em " + retrySeconds + "s · mantendo o monitoramento ativo";
        await sleep(retrySeconds * 1000);
      }
    }

    progress(false);
  }

  async function renderConnected() {
    try {
      await call("/session");
    } catch (_) {
      clearSession();
      loginView();
      return;
    }

    appView();
    await loadAssets();
  }

  async function renderRoute() {
    const hash = location.hash || "";
    const active = hash.includes("/ferramenta/consultor-senior");

    if (!active) {
      document.body.classList.remove("cs-tool-active");
      return;
    }

    document.body.classList.add("cs-tool-active");

    if (!$("consultorSeniorToolHost")) {
      setTimeout(renderRoute, 0);
      return;
    }

    if (sid()) await renderConnected();
    else loginView();

    document.title = "CONSULTOR SÊNIOR | Resolvei";
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function boot() {
    renderRoute();
  }

  window.renderConsultorSenior = renderRoute;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.addEventListener("hashchange", () => setTimeout(renderRoute, 0));
})();