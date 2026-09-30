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
          <span class="eyebrow">ANALISTA TÉCNICO + IA</span>
          <h1>🧙 GURÚ DOS SINAIS</h1>
          <p>Confluência de indicadores + estratégias específicas + validação do Gemini.</p>
        </section>

        <section class="card guru-control-card">
          <div class="guru-control-grid guru-control-grid-3">
            <div class="field">
              <label for="guruPair">Par de moedas</label>
              <select id="guruPair">${pairs.map(([v,t]) => `<option value="${v}">${t}</option>`).join("")}</select>
            </div>
            <div class="field">
              <label for="guruTimeframe">Timeframe</label>
              <select id="guruTimeframe">${timeframes.map(([v,t]) => `<option value="${v}">${t}</option>`).join("")}</select>
            </div>
            <div class="field">
              <label for="guruStrategy">Estratégia</label>
              <select id="guruStrategy">
                <option value="automatica">🤖 Automática — maior confluência</option>
                <option value="tendencia">📈 Tendência + confluência</option>
                <option value="reversao">↩️ Reversão à média</option>
                <option value="rompimento">🚀 Rompimento + momentum</option>
              </select>
            </div>
          </div>
          <button class="guru-analyze-btn" id="guruAnalyzeBtn">🔍 ANALISAR MERCADO</button>
          <div id="guruMessage" class="notice" hidden></div>
        </section>

        <section id="guruResult">
          <div class="card guru-empty">
            <div class="guru-empty-icon">📊</div>
            <strong>Pronto para analisar</strong>
            <span>O motor calcula as estratégias antes de consultar o Gemini, reduzindo o tempo de resposta.</span>
          </div>
        </section>

        <section class="guru-foot-note">
          <span>Ferramenta de estudo. Indicadores técnicos não garantem resultado futuro e o sistema não executa operações.</span>
        </section>
      </div>
    `;
  }

  function classFor(signal) {
    return signal === "CALL" ? "guru-call" : signal === "PUT" ? "guru-put" : "guru-wait";
  }

  function resultHtml(a) {
    const reasons = (a.reasons || []).slice(0,7).map(x => `<li>✓ ${esc(x)}</li>`).join("");
    const warnings = (a.warnings || []).slice(0,5).map(x => `<li>⚠ ${esc(x)}</li>`).join("");
    const score = Math.max(0, Math.min(100, Number(a.score || 0)));
    const strategyRows = (a.strategies || []).map(s => `
      <div class="guru-strategy-card ${s.direction === "CALL" ? "guru-strategy-call" : s.direction === "PUT" ? "guru-strategy-put" : ""}">
        <div><strong>${esc(s.strategyLabel)}</strong><span>${esc(s.direction)}</span></div>
        <small>${Number(s.confidence || 0).toFixed(0)}% · ${Number(s.indicators?.length || 0)} indicadores</small>
      </div>`).join("");
    const indicators = (a.strategies || []).find(s => s.strategy === a.strategy)?.indicators || [];
    const indicatorRows = indicators.map(i => `
      <div class="guru-indicator-row">
        <span>${esc(i.name)}</span><strong>${esc(i.signal)}</strong>
      </div>`).join("");
    const gemini = a.gemini || {};
    return `
      <div class="card guru-result">
        <div class="guru-result-top">
          <div>
            <span class="eyebrow">${esc(a.symbol)} · ${esc(a.timeframe)} · ${esc(a.strategyLabel || "estratégia")}</span>
            <div class="guru-result-title">SINAL DE ENTRADA</div>
          </div>
          <div class="guru-price">${a.price != null ? esc(Number(a.price).toFixed(5)) : "—"}</div>
        </div>

        <div class="guru-big-signal ${classFor(a.signal)}">${esc(a.signal)}</div>
        <div class="guru-quality">${esc(a.quality)}</div>

        <div class="guru-score-line">
          <span>Confluência final</span>
          <strong>${score}%</strong>
        </div>
        <div class="guru-meter"><span style="width:${score}%"></span></div>

        <div class="guru-ai-box">
          <strong>✨ Gemini</strong>
          <span>${gemini.available ? "Validação da leitura técnica concluída." : "Validação IA indisponível; sinal calculado pelo motor técnico."}</span>
          ${gemini.reason ? `<small>${esc(gemini.reason)}</small>` : ""}
        </div>

        <div class="guru-strategy-grid">${strategyRows}</div>

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

        <details class="guru-indicators-details">
          <summary>Ver os indicadores da estratégia (${indicatorRows ? indicators.length : 0})</summary>
          <div class="guru-indicator-list">${indicatorRows}</div>
        </details>

        <div class="guru-mini-grid">
          <div><span>RSI</span><strong>${a.indicators?.RSI != null ? Number(a.indicators.RSI).toFixed(1) : "—"}</strong></div>
          <div><span>ADX</span><strong>${a.indicators?.ADX != null ? Number(a.indicators.ADX).toFixed(1) : "—"}</strong></div>
          <div><span>Stochastic</span><strong>${a.indicators?.StochasticK != null ? Number(a.indicators.StochasticK).toFixed(1) : "—"}</strong></div>
          <div><span>ATR</span><strong>${a.indicators?.ATRpct != null ? Number(a.indicators.ATRpct).toFixed(3) + "%" : "—"}</strong></div>
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
    const strategy = document.getElementById("guruStrategy")?.value || "automatica";
    if (!symbol || !timeframe) return;

    btn.disabled = true;
    btn.textContent = "⏳ CALCULANDO…";
    if(msg){msg.hidden=true;msg.textContent="";}

    result.innerHTML = `
      <div class="card guru-loading">
        <div class="guru-spinner"></div>
        <strong>Analisando ${esc(symbol)}</strong>
        <span>12 indicadores por estratégia + múltiplas estratégias + validação Gemini.</span>
      </div>`;

    try {
      const headers = {"Content-Type":"application/json"};
      try {
        if (typeof resolveiUser !== "undefined" && resolveiUser) {
          headers.Authorization = "Bearer " + await resolveiUser.getIdToken();
        }
      } catch(_) {}

      const r = await fetch(API + "/market-analysis", {
        method:"POST",
        headers,
        body:JSON.stringify({symbol,timeframe,strategy})
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
    renderRoute();
    window.addEventListener("hashchange", () => setTimeout(() => {
      renderRoute();
    }, 0));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();