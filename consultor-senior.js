(() => {
  const API = "/api/consultor-senior";
  const KEY = "resolvei_consultor_senior_iq_session";
  let assetNames = [];
  let monitoring = false;
  let monitorCycle = 0;
  let monitorToken = 0;
  let liveTimer = null;
  let liveBusy = false;
  let chartTimeframe = "1m";

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
        '<section id="csLive" class="cs-live-layout" hidden>' +
          '<div class="cs-live-chart card">' +
            '<div class="cs-live-head">' +
              '<div><small>MONITORAMENTO EM TEMPO REAL</small><h2 id="csChartTitle">—</h2></div>' +
              '<div class="cs-live-price"><strong id="csLivePrice">—</strong><span id="csLiveClock">—</span></div>' +
            '</div>' +
            '<div class="cs-chart-tabs">' +
              '<button type="button" data-tf="1m" class="active">1M</button>' +
              '<button type="button" data-tf="5m">5M</button>' +
              '<button type="button" data-tf="15m">15M</button>' +
              '<span>visualização · o Consultor continua escolhendo o timeframe de entrada automaticamente</span>' +
            '</div>' +
            '<div id="csChart" class="cs-chart"></div>' +
          '</div>' +
          '<aside class="cs-trace card">' +
            '<div class="cs-trace-head"><small>O QUE O CONSULTOR ESTÁ LENDO</small><b id="csTraceCycle">CICLO 0</b></div>' +
            '<div id="csTraceList" class="cs-trace-list">' +
              traceItem("context", "CONTEXTO", "Aguardando leitura…") +
              traceItem("structure", "ESTRUTURA", "Aguardando leitura…") +
              traceItem("regions", "REGIÕES", "Aguardando leitura…") +
              traceItem("price", "PRICE ACTION", "Aguardando leitura…") +
              traceItem("momentum", "MOMENTUM", "Aguardando leitura…") +
              traceItem("volatility", "VOLATILIDADE", "Aguardando leitura…") +
              traceItem("trigger", "GATILHO", "Aguardando confirmação…") +
            '</div>' +
            '<div id="csTraceFooter" class="cs-trace-footer">A leitura é baseada nos dados objetivos recebidos da IQ Option. O raciocínio interno da IA não é exposto.</div>' +
          '</aside>' +
        '</section>' +
        '<main id="csResult"><div class="cs-empty"><strong>Escolha um ativo e clique em CONSULTAR.</strong><span>O Consultor Sênior fará uma leitura multi-timeframe e procurará o melhor gatilho disponível.</span></div></main>' +
        '<footer class="cs-foot"><span id="csMeta">Sessão IQ Option ativa</span><span>IA automática · sem execução de ordens</span></footer>' +
      '</div>';

    $("csLogout").onclick = async () => {
      stopLiveMarket();
      try { await call("/logout", { method: "POST" }); } catch (_) {}
      clearSession();
      renderRoute();
    };

    $("csConsult").onclick = () => monitoring ? stopMonitoring() : consult();

    document.querySelectorAll(".cs-chart-tabs button").forEach(button => {
      button.onclick = () => {
        chartTimeframe = button.dataset.tf || "1m";
        document.querySelectorAll(".cs-chart-tabs button").forEach(b => b.classList.toggle("active", b === button));
        refreshLiveMarket(true);
      };
    });
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

  function stopLiveMarket() {
    if (liveTimer) {
      clearInterval(liveTimer);
      liveTimer = null;
    }
    liveBusy = false;
  }

  function startLiveMarket() {
    const box = $("csLive");
    if (box) box.hidden = false;
    stopLiveMarket();
    refreshLiveMarket(true);
    liveTimer = setInterval(() => refreshLiveMarket(false), 4000);
  }

  function traceItem(id, title, value) {
    return '<article class="cs-trace-item" id="csTrace-' + id + '">' +
      '<span class="cs-trace-dot"></span>' +
      '<div><small>' + title + '</small><p>' + esc(value) + '</p></div>' +
      '</article>';
  }

  function traceSet(id, value, state = "reading") {
    const item = $("csTrace-" + id);
    if (!item) return;
    item.classList.remove("reading", "waiting", "confirmed", "warning");
    item.classList.add(state);
    const p = item.querySelector("p");
    if (p) p.textContent = value || "—";
  }

  function formatPct(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(2) + "%" : "—";
  }

  function updateTrace(snapshot, cycle) {
    const f = snapshot?.frames || {};
    const s15 = f["15m"]?.summary || {};
    const s5 = f["5m"]?.summary || {};
    const s1 = f["1m"]?.summary || {};
    $("csTraceCycle") && ($("csTraceCycle").textContent = "CICLO " + (cycle || 0));

    traceSet("context", "15m · " + (s15.trend || "indefinido"), "reading");
    traceSet("structure", "5m · " + (s5.structure || "indefinida"), "reading");

    const sup = s5.support?.nearest;
    const res = s5.resistance?.nearest;
    traceSet("regions",
      "Suporte " + (sup == null ? "—" : sup) + " · resistência " + (res == null ? "—" : res),
      "reading"
    );

    const lc = s1.last_candle || {};
    traceSet("price",
      "1m · " + (lc.direction || "neutro") +
      " · corpo " + formatPct(lc.body_pct) +
      " · sombras " + formatPct((Number(lc.upper_wick_pct) || 0) + (Number(lc.lower_wick_pct) || 0)),
      "reading"
    );

    const mom = s1.momentum || {};
    traceSet("momentum",
      "RSI " + (mom.rsi14 == null ? "—" : Number(mom.rsi14).toFixed(1)) +
      " · MACD hist " + (mom.macd_hist == null ? "—" : Number(mom.macd_hist).toFixed(5)),
      "reading"
    );

    const vol = s1.volatility || {};
    traceSet("volatility",
      "ATR " + (vol.atr_pct_price == null ? "—" : Number(vol.atr_pct_price).toFixed(3) + "%") +
      " · faixa " + (vol.recent_range_pct == null ? "—" : Number(vol.recent_range_pct).toFixed(3) + "%"),
      "reading"
    );

    traceSet("trigger", "Aguardando evento objetivo e confirmação no 1m.", "waiting");
  }

  function updateTraceFromAnalysis(a, found) {
    traceSet("context", a.trend || "Contexto avaliado", "reading");
    traceSet("structure", a.structure || "Estrutura avaliada", "reading");
    traceSet("regions", a.zone || "Região avaliada", "reading");
    traceSet("price", a.price_action || "Price action avaliado", "reading");
    traceSet("momentum", a.momentum || "Momentum avaliado", "reading");
    traceSet("volatility", a.volatility || "Volatilidade avaliada", "reading");
    traceSet("trigger",
      found
        ? ((a.trigger || "Gatilho confirmado") + " · " + (a.status || "AGORA"))
        : (a.trigger || "Nenhum gatilho confirmado neste ciclo."),
      found ? "confirmed" : "waiting"
    );
  }

  function emaSeries(values, period) {
    if (!values.length) return [];
    const k = 2 / (period + 1);
    const out = [values[0]];
    for (let i = 1; i < values.length; i++) out.push(values[i] * k + out[i - 1] * (1 - k));
    return out;
  }

  function drawChart(payload) {
    const host = $("csChart");
    if (!host) return;
    const candles = Array.isArray(payload?.candles) ? payload.candles : [];
    if (!candles.length) {
      host.innerHTML = '<div class="cs-chart-empty">Sem candles disponíveis.</div>';
      return;
    }

    const data = candles.slice(-90);
    const closes = data.map(x => Number(x[4]));
    const highs = data.map(x => Number(x[2]));
    const lows = data.map(x => Number(x[3]));
    const width = 1000, height = 390, left = 58, right = 18, top = 20, bottom = 34;
    const pw = width - left - right, ph = height - top - bottom;
    let min = Math.min(...lows), max = Math.max(...highs);
    const range = Math.max(max - min, Math.abs(max) * 0.0001);
    min -= range * 0.06; max += range * 0.06;
    const xStep = pw / Math.max(data.length, 1);
    const candleW = Math.max(2.4, Math.min(10, xStep * 0.62));
    const y = p => top + (max - p) / (max - min) * ph;
    const x = i => left + xStep * i + xStep / 2;

    const sup = payload.summary?.support?.nearest;
    const res = payload.summary?.resistance?.nearest;
    const ema9 = emaSeries(closes, 9);
    const ema21 = emaSeries(closes, 21);

    let svg = '<svg viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none" role="img" aria-label="Gráfico de candles">';
    for (let i = 0; i < 5; i++) {
      const gy = top + (ph / 4) * i;
      const price = max - (max - min) * (i / 4);
      svg += '<line class="cs-grid-line" x1="' + left + '" y1="' + gy + '" x2="' + (width-right) + '" y2="' + gy + '"></line>';
      svg += '<text class="cs-axis-label" x="4" y="' + (gy + 4) + '">' + price.toFixed(5) + '</text>';
    }

    const pathFor = series => series.map((value,i) => (i ? "L" : "M") + x(i).toFixed(2) + " " + y(value).toFixed(2)).join(" ");
    svg += '<path class="cs-ema ema9" d="' + pathFor(ema9) + '"></path>';
    svg += '<path class="cs-ema ema21" d="' + pathFor(ema21) + '"></path>';

    if (sup != null && sup >= min && sup <= max) {
      svg += '<line class="cs-level support" x1="' + left + '" y1="' + y(sup) + '" x2="' + (width-right) + '" y2="' + y(sup) + '"></line>';
      svg += '<text class="cs-level-label" x="' + (width-right-6) + '" y="' + (y(sup)-5) + '">SUPORTE</text>';
    }
    if (res != null && res >= min && res <= max) {
      svg += '<line class="cs-level resistance" x1="' + left + '" y1="' + y(res) + '" x2="' + (width-right) + '" y2="' + y(res) + '"></line>';
      svg += '<text class="cs-level-label" x="' + (width-right-6) + '" y="' + (y(res)-5) + '">RESISTÊNCIA</text>';
    }

    data.forEach((c, i) => {
      const o = Number(c[1]), hi = Number(c[2]), lo = Number(c[3]), cl = Number(c[4]);
      const up = cl >= o;
      const cls = up ? "up" : "down";
      const xx = x(i), yyO = y(o), yyC = y(cl);
      svg += '<line class="cs-wick ' + cls + '" x1="' + xx + '" y1="' + y(hi) + '" x2="' + xx + '" y2="' + y(lo) + '"></line>';
      svg += '<rect class="cs-candle ' + cls + '" x="' + (xx-candleW/2) + '" y="' + Math.min(yyO,yyC) + '" width="' + candleW + '" height="' + Math.max(1.5,Math.abs(yyC-yyO)) + '" rx="1"></rect>';
    });

    const last = closes[closes.length-1];
    svg += '<line class="cs-current-line" x1="' + left + '" y1="' + y(last) + '" x2="' + (width-right) + '" y2="' + y(last) + '"></line>';
    svg += '</svg>';
    host.innerHTML = svg;

    const selected = chartTimeframe.toUpperCase();
    $("csChartTitle").textContent = payload.asset + " · " + selected;
    $("csLivePrice").textContent = Number(last).toFixed(5);
    $("csLiveClock").textContent = payload.timestamp ? new Date(payload.timestamp).toLocaleTimeString("pt-BR") : "—";
  }

  async function refreshLiveMarket(force) {
    if (!monitoring || liveBusy) return;
    const asset = ($("csAsset")?.value || "").trim().toUpperCase();
    if (!asset) return;
    liveBusy = true;
    try {
      const data = await call("/market?symbol=" + encodeURIComponent(asset) + "&timeframe=" + encodeURIComponent(chartTimeframe));
      drawChart(data);
      updateTrace(data, monitorCycle);
    } catch (error) {
      if (force) {
        const err = $("csError");
        if (err) err.textContent = "⚠️ Gráfico ao vivo: " + error.message;
      }
    } finally {
      liveBusy = false;
    }
  }

  function stopMonitoring() {
    monitoring = false;
    monitorToken += 1;
    stopLiveMarket();
    progress(false);
    const live = $("csLive");
    if (live) live.hidden = true;
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
    startLiveMarket();

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
          stopLiveMarket();
          const live = $("csLive");
          if (live) live.hidden = false;
          updateTraceFromAnalysis(data.analysis, true);
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
        if (data.analysis) updateTraceFromAnalysis(data.analysis, false);
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
    stopLiveMarket();
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