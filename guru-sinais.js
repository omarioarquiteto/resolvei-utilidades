(() => {
  const TOOL_ID = "guru-dos-sinais";
  const API = "/api/guru-sinais";

  const escapeHtml = (v) => String(v ?? "").replace(/[&<>"]/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"
  }[c]));

  function toolCard() {
    return `<article class="card tool-card guru-tool-card">
      <a href="#/ferramenta/${TOOL_ID}">
        <div class="tool-icon">🧙</div>
        <h3>GURÚ DOS SINAIS</h3>
        <p>Analise técnica por confluência de indicadores, gráficos e contexto de mercado.</p>
      </a>
    </article>`;
  }

  function ui() {
    return `
    <div class="guru-shell">
      <section class="card guru-hero-card">
        <div>
          <span class="eyebrow">ANÁLISE TÉCNICA</span>
          <h2>🧙 GURÚ DOS SINAIS</h2>
          <p>O TradingView fornece os dados técnicos; o Resolvei interpreta a confluência e apresenta CALL, PUT ou AGUARDAR para estudo.</p>
        </div>
        <div class="guru-status" id="guruStatus">Aguardando dados do TradingView</div>
      </section>

      <div class="tool-layout">
        <section class="card panel">
          <h2>Configuração e teste</h2>
          <div class="notice">Para usar em produção, crie um alerta no TradingView apontando para <code>/api/guru-sinais/webhook</code>. O botão abaixo permite testar o motor antes da integração.</div>
          <div class="form-grid">
            <div class="field"><label for="guruSymbol">Ativo</label><input id="guruSymbol" value="EURUSD"></div>
            <div class="field"><label for="guruTimeframe">Timeframe</label><select id="guruTimeframe"><option>1m</option><option>5m</option><option>15m</option><option>30m</option><option>1h</option></select></div>
            <div class="field"><label for="guruTrend">Tendência</label><select id="guruTrend"><option value="ALTA">Alta</option><option value="BAIXA">Baixa</option><option value="NEUTRA">Neutra</option></select></div>
            <div class="field"><label for="guruRsi">RSI</label><input id="guruRsi" type="number" step="0.1" value="55"></div>
            <div class="field"><label for="guruMacd">MACD</label><input id="guruMacd" type="number" step="0.00001" value="0.10"></div>
            <div class="field"><label for="guruMacdSignal">MACD sinal</label><input id="guruMacdSignal" type="number" step="0.00001" value="0.05"></div>
            <div class="field"><label for="guruEma9">EMA 9</label><input id="guruEma9" type="number" step="0.00001" value="1.101"></div>
            <div class="field"><label for="guruEma21">EMA 21</label><input id="guruEma21" type="number" step="0.00001" value="1.099"></div>
            <div class="field"><label for="guruEma50">EMA 50</label><input id="guruEma50" type="number" step="0.00001" value="1.095"></div>
            <div class="field"><label for="guruBb">Posição Bollinger (0-1)</label><input id="guruBb" type="number" step="0.01" min="0" max="1" value="0.45"></div>
            <div class="field"><label for="guruMomentum">Momentum</label><input id="guruMomentum" type="number" step="0.00001" value="0.10"></div>
            <div class="field"><label for="guruVolumeRatio">Volume / média</label><input id="guruVolumeRatio" type="number" step="0.01" value="1.20"></div>
            <div class="field"><label for="guruPattern">Padrão de candle</label><input id="guruPattern" value="bullish"></div>
            <label class="guru-check"><input id="guruSupport" type="checkbox" checked> Próximo de suporte</label>
            <label class="guru-check"><input id="guruResistance" type="checkbox"> Próximo de resistência</label>
            <label class="guru-check"><input id="guruBreakoutUp" type="checkbox"> Rompimento de alta</label>
            <label class="guru-check"><input id="guruBreakoutDown" type="checkbox"> Rompimento de baixa</label>
          </div>
          <div class="actions">
            <button class="btn primary" id="guruAnalyzeBtn">Analisar agora</button>
            <button class="btn ghost" id="guruLatestBtn">Último sinal</button>
          </div>
          <div id="guruMessage" class="notice" hidden></div>
        </section>
        <section id="guruResult">
          <div class="result-box"><div class="result-label">GURÚ DOS SINAIS</div><div class="result-main">—</div><p>Aguardando uma análise.</p></div>
        </section>
      </div>

      <section class="card panel guru-history">
        <div class="section-head"><div><h2>Histórico dos sinais</h2><p>Os últimos sinais recebidos nesta instância do servidor.</p></div><button class="btn" id="guruRefreshHistory">Atualizar</button></div>
        <div id="guruHistoryBody" class="guru-history-body">Nenhum sinal recebido.</div>
      </section>

      <section class="card panel">
        <h2>Como conectar o TradingView</h2>
        <ol class="guru-steps">
          <li>Abra o Pine Script fornecido pelo Resolvei no TradingView.</li>
          <li>Adicione o script ao gráfico e crie um alerta na condição de sinal.</li>
          <li>No campo Webhook URL, use <code>https://SEU-DOMINIO-RENDER/api/guru-sinais/webhook</code>.</li>
          <li>Use o JSON gerado pelo script como mensagem do alerta.</li>
          <li>O Resolvei recebe os dados, calcula a confluência e registra o resultado.</li>
        </ol>
        <div class="notice">O GURÚ DOS SINAIS é uma ferramenta de estudo. CALL/PUT representa a direção técnica sugerida pelo modelo e não uma garantia de resultado.</div>
      </section>
    </div>`;
  }

  function payload() {
    const n = id => {
      const v = document.getElementById(id)?.value;
      return v === "" ? null : Number(v);
    };
    return {
      symbol: document.getElementById("guruSymbol")?.value.trim(),
      timeframe: document.getElementById("guruTimeframe")?.value,
      trend: document.getElementById("guruTrend")?.value,
      rsi: n("guruRsi"), macd: n("guruMacd"), macdSignal: n("guruMacdSignal"),
      ema9: n("guruEma9"), ema21: n("guruEma21"), ema50: n("guruEma50"),
      bbPosition: n("guruBb"), momentum: n("guruMomentum"), volumeRatio: n("guruVolumeRatio"),
      candlePattern: document.getElementById("guruPattern")?.value,
      support: !!document.getElementById("guruSupport")?.checked,
      resistance: !!document.getElementById("guruResistance")?.checked,
      breakoutUp: !!document.getElementById("guruBreakoutUp")?.checked,
      breakoutDown: !!document.getElementById("guruBreakoutDown")?.checked
    };
  }

  function signalClass(s) {
    return s === "CALL" ? "guru-call" : s === "PUT" ? "guru-put" : "guru-wait";
  }

  function renderResult(a) {
    if (!a) return;
    const reasons = (a.reasons || []).map(x => `<li>✓ ${escapeHtml(x)}</li>`).join("");
    const warnings = (a.warnings || []).map(x => `<li>⚠ ${escapeHtml(x)}</li>`).join("");
    document.getElementById("guruResult").innerHTML = `
      <div class="result-box guru-result-card">
        <div class="result-label">SINAL TÉCNICO</div>
        <div class="guru-signal ${signalClass(a.signal)}">${escapeHtml(a.signal)}</div>
        <div class="guru-score"><span>Confluência técnica</span><strong>${Number(a.score || 0)}%</strong></div>
        <div class="guru-meter"><span style="width:${Math.max(0,Math.min(100,Number(a.score||0)))}%"></span></div>
        <div class="result-sub">
          <div class="result-row"><span>Ativo</span><strong>${escapeHtml(a.symbol)}</strong></div>
          <div class="result-row"><span>Timeframe</span><strong>${escapeHtml(a.timeframe)}</strong></div>
          <div class="result-row"><span>Qualidade</span><strong>${escapeHtml(a.quality)}</strong></div>
          <div class="result-row"><span>Score comprador</span><strong>${a.buyScore}</strong></div>
          <div class="result-row"><span>Score vendedor</span><strong>${a.sellScore}</strong></div>
        </div>
        <div class="guru-analysis-list"><h3>Por que o gurú chegou aqui</h3><ul>${reasons || "<li>Sem confirmação suficiente.</li>"}</ul></div>
        ${warnings ? `<div class="guru-analysis-list guru-warnings"><h3>Pontos de atenção</h3><ul>${warnings}</ul></div>` : ""}
        <div class="note">O índice de confluência mede alinhamento das condições técnicas configuradas; não é probabilidade de acerto.</div>
      </div>`;
    const st=document.getElementById("guruStatus");
    if(st) st.textContent = a.signal === "AGUARDAR" ? "Confluência insuficiente" : `Sinal ${a.signal} recebido`;
  }

  async function analyze() {
    const msg=document.getElementById("guruMessage"), btn=document.getElementById("guruAnalyzeBtn");
    if(btn) {btn.disabled=true;btn.textContent="Analisando…";}
    try {
      const r=await fetch(API+"/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
      const d=await r.json();
      if(!r.ok) throw new Error(d.detail || "Falha na análise.");
      renderResult(d.analysis); await history();
      if(msg){msg.hidden=false;msg.textContent="Análise concluída.";}
    } catch(e) {
      if(msg){msg.hidden=false;msg.textContent="⚠️ "+e.message;}
    } finally {if(btn){btn.disabled=false;btn.textContent="Analisar agora";}}
  }

  async function latest() {
    try { const r=await fetch(API+"/latest"); const d=await r.json(); renderResult(d.signal); }
    catch(e) { const m=document.getElementById("guruMessage"); if(m){m.hidden=false;m.textContent="⚠️ "+e.message;} }
  }

  async function history() {
    const box=document.getElementById("guruHistoryBody"); if(!box)return;
    try {
      const r=await fetch(API+"/history?limit=20"); const d=await r.json();
      if(!d.signals?.length){box.textContent="Nenhum sinal recebido.";return;}
      box.innerHTML=d.signals.map(s=>`<div class="guru-history-row"><strong class="${signalClass(s.signal)}">${escapeHtml(s.signal)}</strong><span>${escapeHtml(s.symbol)}</span><span>${escapeHtml(s.timeframe)}</span><span>${s.score}%</span><span>${escapeHtml(s.timestamp)}</span></div>`).join("");
    } catch(e) { box.textContent="Não foi possível carregar o histórico."; }
  }

  function bind() {
    document.getElementById("guruAnalyzeBtn")?.addEventListener("click", analyze);
    document.getElementById("guruLatestBtn")?.addEventListener("click", latest);
    document.getElementById("guruRefreshHistory")?.addEventListener("click", history);
    history();
  }

  function injectCard() {
    const grids=[...document.querySelectorAll(".grid")];
    if(!grids.length || document.querySelector(".guru-tool-card")) return;
    const target=grids[0];
    target.insertAdjacentHTML("beforeend",toolCard());
  }

  function renderRoute() {
    const hash=location.hash || "";
    if(!hash.includes("/ferramenta/"+TOOL_ID)) return false;
    const app=document.getElementById("app");
    if(!app) return false;
    app.innerHTML=`<div class="tool-page"><div class="breadcrumb"><a href="#/">Início</a> / GURÚ DOS SINAIS</div>${ui()}</div>`;
    bind();
    document.title="GURÚ DOS SINAIS | Resolvei";
    window.scrollTo({top:0,behavior:"auto"});
    return true;
  }

  function boot() {
    injectCard();
    renderRoute();
    window.addEventListener("hashchange",()=>setTimeout(()=>{injectCard();renderRoute();},0));
    setTimeout(injectCard,300);
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",boot); else boot();
})();