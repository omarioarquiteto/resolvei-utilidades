(() => {
  const TOOL_ID = "guru-dos-sinais";
  const API = "/api/guru-sinais";

  const pairs = [
    ["EUR/USD","EUR/USD"],["GBP/USD","GBP/USD"],["USD/JPY","USD/JPY"],
    ["USD/CHF","USD/CHF"],["AUD/USD","AUD/USD"],["USD/CAD","USD/CAD"],
    ["NZD/USD","NZD/USD"],["EUR/GBP","EUR/GBP"],["EUR/JPY","EUR/JPY"],
    ["GBP/JPY","GBP/JPY"],["AUD/JPY","AUD/JPY"],["USD/BRL","USD/BRL"]
  ];
  const timeframes = [["1m","1 minuto"],["5m","5 minutos"],["15m","15 minutos"],["30m","30 minutos"],["1h","1 hora"]];

  const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"
  }[c]));

  function card() {
    return `<article class="card tool-card guru-tool-card">
      <a href="#/ferramenta/${TOOL_ID}">
        <div class="tool-icon">🧙</div>
        <h3>GURÚ DOS SINAIS</h3>
        <p>Analise técnica automática do mercado.</p>
      </a>
    </article>`;
  }

  function shell() {
    return `
      <div class="guru-simple">
        <section class="guru-simple-head">
          <span class="eyebrow">ANALISTA TÉCNICO</span>
          <h1>🧙 GURÚ DOS SINAIS</h1>
          <p>Escolha o par e o timeframe. O GURÚ faz o restante.</p>
        </section>

        <section class="card guru-control-card">
          <div class="guru-control-grid">
            <div class="field">
              <label for="guruPair">Par de moedas</label>
              <select id="guruPair">${pairs.map(([v,t]) => `<option value="${v}">${t}</option>`).join("")}</select>
            </div>
            <div class="field">
              <label for="guruTimeframe">Timeframe</label>
              <select id="guruTimeframe">${timeframes.map(([v,t]) => `<option value="${v}">${t}</option>`).join("")}</select>
            </div>
          </div>
          <button class="guru-analyze-btn" id="guruAnalyzeBtn">🔍 ANALISAR MERCADO</button>
          <div id="guruMessage" class="notice" hidden></div>
        </section>

        <section id="guruResult">
          <div class="card guru-empty">
            <div class="guru-empty-icon">📊</div>
            <strong>Pronto para analisar</strong>
            <span>Escolha o par e o timeframe acima.</span>
          </div>
        </section>

        <section class="guru-foot-note">
          <span>O resultado é uma leitura técnica de mercado para estudo. O sistema não executa operações.</span>
        </section>
      </div>
    `;
  }

  function classFor(signal) {
    return signal === "CALL" ? "guru-call" : signal === "PUT" ? "guru-put" : "guru-wait";
  }

  function resultHtml(a) {
    const reasons = (a.reasons || []).slice(0,6).map(x => `<li>✓ ${esc(x)}</li>`).join("");
    const warnings = (a.warnings || []).slice(0,4).map(x => `<li>⚠ ${esc(x)}</li>`).join("");
    const score = Math.max(0, Math.min(100, Number(a.score || 0)));
    return `
      <div class="card guru-result">
        <div class="guru-result-top">
          <div>
            <span class="eyebrow">${esc(a.symbol)} · ${esc(a.timeframe)}</span>
            <div class="guru-result-title">SINAL DE ENTRADA</div>
          </div>
          <div class="guru-price">${a.price != null ? esc(Number(a.price).toFixed(5)) : "—"}</div>
        </div>

        <div class="guru-big-signal ${classFor(a.signal)}">${esc(a.signal)}</div>
        <div class="guru-quality">${esc(a.quality)}</div>

        <div class="guru-score-line">
          <span>Força da confluência técnica</span>
          <strong>${score}%</strong>
        </div>
        <div class="guru-meter"><span style="width:${score}%"></span></div>

        <div class="guru-columns">
          <div>
            <h3>Leitura do GURÚ</h3>
            <ul>${reasons || "<li>Sem confirmação suficiente.</li>"}</ul>
          </div>
          <div>
            <h3>Pontos de atenção</h3>
            <ul>${warnings || "<li>Nenhum alerta relevante detectado.</li>"}</ul>
          </div>
        </div>

        <div class="guru-mini-grid">
          <div><span>Tendência</span><strong>${esc(a.indicators?.trend || "—")}</strong></div>
          <div><span>RSI</span><strong>${a.indicators?.rsi ?? "—"}</strong></div>
          <div><span>MACD</span><strong>${a.indicators?.macd != null ? (a.indicators.macd > a.indicators.macdSignal ? "Positivo" : "Negativo") : "—"}</strong></div>
          <div><span>Candle</span><strong>${esc(a.indicators?.candlePattern || "—")}</strong></div>
        </div>

        <div class="guru-result-bottom">
          <button class="btn primary" id="guruNewAnalysis">Nova análise</button>
          <span>Atualizado: ${esc(a.timestamp)}</span>
        </div>
      </div>
    `;
  }

  async function analyze() {
    const btn = document.getElementById("guruAnalyzeBtn");
    const result = document.getElementById("guruResult");
    const msg = document.getElementById("guruMessage");
    const symbol = document.getElementById("guruPair")?.value;
    const timeframe = document.getElementById("guruTimeframe")?.value;

    if (!symbol || !timeframe) return;
    btn.disabled = true;
    btn.textContent = "⏳ ANALISANDO MERCADO…";
    if(msg){msg.hidden=true;msg.textContent="";}

    result.innerHTML = `
      <div class="card guru-loading">
        <div class="guru-spinner"></div>
        <strong>Analisando ${esc(symbol)}</strong>
        <span>O GURÚ está cruzando tendência, momentum, indicadores e estrutura de preço.</span>
      </div>`;

    try {
      const r = await fetch(API + "/market-analysis", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({symbol,timeframe})
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Não foi possível analisar o mercado.");
      result.innerHTML = resultHtml(d.analysis);
      document.getElementById("guruNewAnalysis")?.addEventListener("click", () => window.scrollTo({top:0,behavior:"smooth"}));
    } catch (e) {
      result.innerHTML = `
        <div class="card guru-error">
          <strong>Não foi possível concluir a análise.</strong>
          <span>${esc(e.message)}</span>
        </div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "🔍 ANALISAR MERCADO";
    }
  }

  function injectCard() {
    if (document.querySelector(".guru-tool-card")) return;
    const grids = [...document.querySelectorAll(".grid")];
    if (grids.length) grids[0].insertAdjacentHTML("beforeend", card());
  }

  function renderRoute() {
    const hash = location.hash || "";
    if (!hash.includes("/ferramenta/" + TOOL_ID)) return;
    const app = document.getElementById("app");
    if (!app) return;
    app.innerHTML = `<div class="tool-page"><div class="breadcrumb"><a href="#/">Início</a> / GURÚ DOS SINAIS</div>${shell()}</div>`;
    document.getElementById("guruAnalyzeBtn")?.addEventListener("click", analyze);
    document.title = "GURÚ DOS SINAIS | Resolvei";
    window.scrollTo({top:0,behavior:"auto"});
  }

  function boot() {
    injectCard();
    renderRoute();
    window.addEventListener("hashchange", () => setTimeout(() => {
      injectCard();
      renderRoute();
    }, 0));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();