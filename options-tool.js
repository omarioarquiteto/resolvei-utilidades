(function(){
var SYMBOLS=[
  ["EUR/USD","EUR/USD"],["GBP/USD","GBP/USD"],["USD/JPY","USD/JPY"],["AUD/USD","AUD/USD"],
  ["USD/CAD","USD/CAD"],["USD/CHF","USD/CHF"],["NZD/USD","NZD/USD"],["EUR/GBP","EUR/GBP"],
  ["EUR/JPY","EUR/JPY"],["GBP/JPY","GBP/JPY"]
];
var EXPIRIES=[[1,"1 minuto"],[5,"5 minutos"],[15,"15 minutos"]];
var ui='<div class="tool-layout options-binary-layout">'+
  '<section class="card panel">'+
    '<span class="eyebrow">ESTUDO DE OPÇÕES BINÁRIAS</span>'+
    '<h2>📊 Análise de opções binárias</h2>'+
    '<div class="notice"><strong>Como funciona:</strong> selecione o par, escolha a expiração e clique no gráfico para definir o ponto de entrada. O valor investido e o payout servem para simular o resultado financeiro. O Resolvei não envia ordens para corretoras.</div>'+
    '<div class="form-grid">'+
      '<div class="field"><label for="optSymbol">Par de moedas</label><select id="optSymbol">'+SYMBOLS.map(function(x){return "<option value=\""+x[0]+"\">"+x[1]+"</option>";}).join("")+'</select></div>'+
      '<div class="field"><label for="optExpiry">Tempo de expiração</label><select id="optExpiry">'+EXPIRIES.map(function(x){return "<option value=\\""+x[0]+"\\">"+x[1]+"</option>";}).join("")+'</select></div>'+
      '<div class="field"><label for="optInvestment">Valor da entrada</label><div class="input-wrap"><span class="prefix">R$</span><input id="optInvestment" type="number" min="1" step="0.01" value="100"></div></div>'+
      '<div class="field"><label for="optPayout">Payout da operação</label><div class="input-wrap"><input id="optPayout" type="number" min="1" max="100" step="0.1" value="80"><span class="suffix">%</span></div><small>Informe o payout oferecido pela sua corretora.</small></div>'+
      '<div class="field full"><label for="optDirection">Direção estudada</label><select id="optDirection"><option value="call">CALL — Alta</option><option value="put">PUT — Baixa</option></select></div>'+
    '</div>'+
    '<div class="actions"><button class="btn primary" id="optAnalyzeBtn">🔎 Analisar ponto de entrada</button><button class="btn" id="optLatestBtn">Usar último ponto</button></div>'+
    '<div id="optStatus" class="notice">Carregando dados de mercado…</div>'+
  '</section>'+
  '<section class="card panel options-chart-panel">'+
    '<div class="section-head" style="margin:0 0 10px"><div><span class="eyebrow">GRÁFICO</span><h2 style="margin:4px 0 0">Clique no candle para escolher a entrada</h2></div><div class="chip" id="optPointLabel">Último candle</div></div>'+
    '<canvas id="optChart" height="330" style="width:100%;cursor:crosshair"></canvas>'+
  '</section>'+
  '<section id="optResult"><div class="result-box"><div class="result-label">Entrada</div><div class="result-main">—</div><p>Escolha um ponto no gráfico e analise a entrada.</p></div></section>'+
  '<section class="card panel">'+
    '<div class="section-head" style="margin:0 0 10px"><div><span class="eyebrow">HISTÓRICO</span><h2 style="margin:4px 0 0">Backtest por expiração</h2></div></div>'+
    '<div id="optBacktest"><div class="result-box"><div class="result-label">Backtest</div><div class="result-main">—</div><p>O resultado aparecerá ao analisar.</p></div></div>'+
  '</section>'+
'</div>';

function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c];});}
function money(v){return "R$ "+Number(v||0).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2});}
function n(v,d){return Number(v||0).toLocaleString("pt-BR",{minimumFractionDigits:d||4,maximumFractionDigits:d||4});}
function pct(v){return Number(v||0).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2})+"%";}

var state={candles:[],entryIndex:-1};

function chart(){
  var c=document.getElementById("optChart");if(!c||!state.candles.length)return;
  var rows=state.candles,w=c.clientWidth||900,h=330,d=window.devicePixelRatio||1;
  c.width=w*d;c.height=h*d;var ctx=c.getContext("2d");ctx.scale(d,d);ctx.clearRect(0,0,w,h);
  var vals=rows.map(function(x){return Number(x.close);}),mn=Math.min.apply(Math,vals),mx=Math.max.apply(Math,vals),range=mx-mn||1;
  var pad={l:44,r:16,t:18,b:30};
  ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue("--line")||"#555";ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(pad.l,pad.t);ctx.lineTo(pad.l,h-pad.b);ctx.lineTo(w-pad.r,h-pad.b);ctx.stroke();
  ctx.beginPath();
  vals.forEach(function(v,i){var x=pad.l+i*(w-pad.l-pad.r)/Math.max(1,vals.length-1),y=pad.t+(mx-v)/range*(h-pad.t-pad.b);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});
  ctx.stroke();
  if(state.entryIndex>=0&&state.entryIndex<rows.length){
    var ex=pad.l+state.entryIndex*(w-pad.l-pad.r)/Math.max(1,vals.length-1),ey=pad.t+(mx-vals[state.entryIndex])/range*(h-pad.t-pad.b);
    ctx.setLineDash([5,5]);ctx.beginPath();ctx.moveTo(ex,pad.t);ctx.lineTo(ex,h-pad.b);ctx.stroke();ctx.setLineDash([]);
    ctx.beginPath();ctx.arc(ex,ey,5,0,Math.PI*2);ctx.fill();
  }
}
function pointFromEvent(ev){
  var c=document.getElementById("optChart");if(!c||!state.candles.length)return;
  var rect=c.getBoundingClientRect(),x=ev.clientX-rect.left,padL=44,padR=16;
  var idx=Math.round((x-padL)/Math.max(1,rect.width-padL-padR)*(state.candles.length-1));
  idx=Math.max(0,Math.min(state.candles.length-1,idx));state.entryIndex=idx;
  var p=state.candles[idx];
  document.getElementById("optPointLabel").textContent="Entrada · "+esc(p.datetime||"")+" · "+n(p.close,5);
  chart();
}
function loadChart(){
  var c=document.getElementById("optChart");if(!c)return;
  c.addEventListener("click",pointFromEvent);
  chart();
}
async function getData(entryIndex){
  var symbol=document.getElementById("optSymbol").value,expiry=document.getElementById("optExpiry").value;
  var output=5000;
  var url="/api/options/analyze?symbol="+encodeURIComponent(symbol)+"&expiry="+encodeURIComponent(expiry)+"&outputsize="+output;
  if(Number.isInteger(entryIndex)&&entryIndex>=0)url+="&entry_index="+entryIndex;
  var r=await fetch(url),d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao consultar o mercado.");return d;
}
function renderResult(d){
  var a=d.entry||d.analysis||{},ind=a.indicators||{},dir=d.direction||(a.direction||"neutro"),chosen=document.getElementById("optDirection").value;
  var selected=chosen==="call"?"CALL":"PUT";
  var validDir=(selected==="CALL"&&dir==="alta")||(selected==="PUT"&&dir==="baixa");
  var investment=Number(document.getElementById("optInvestment").value||0),payout=Number(document.getElementById("optPayout").value||0),win=investment*(payout/100),breakEven=payout>0?100/(100+payout)*100:0;
  var cls=dir==="alta"?"opt-up":dir==="baixa"?"opt-down":"opt-neutral";
  var html='<div class="result-box">'+
    '<div class="result-label">Ponto de entrada · '+esc(d.symbol||"")+' · expiração '+esc(String(d.expiry||document.getElementById("optExpiry").value))+' min</div>'+
    '<div class="result-main '+cls+'">'+esc(dir.toUpperCase())+'</div>'+
    '<p><strong>'+selected+'</strong> · Entrada '+money(investment)+' · Payout '+pct(payout)+'</p>'+
    '<div class="result-sub">'+
      '<div class="result-row"><span>Preço de entrada</span><strong>'+n(a.entryPrice||ind.price,5)+'</strong></div>'+
      '<div class="result-row"><span>Preço no vencimento histórico</span><strong>'+(a.expiryPrice? n(a.expiryPrice,5):"—")+'</strong></div>'+
      '<div class="result-row"><span>Score técnico</span><strong>'+n(a.score,0)+'/100</strong></div>'+
      '<div class="result-row"><span>Concordância com a direção escolhida</span><strong>'+ (validDir?"SIM":"NÃO / NEUTRO") +'</strong></div>'+
      '<div class="result-row"><span>Lucro líquido se vencer</span><strong>'+money(win)+'</strong></div>'+
      '<div class="result-row"><span>Ponto de equilíbrio teórico</span><strong>'+pct(breakEven)+'</strong></div>'+
    '</div>'+
    '<div class="suggestion-grid"><div class="suggestion-box"><h3>Confirmações</h3><ul>'+(a.reasons||[]).map(function(x){return "<li>"+esc(x)+"</li>";}).join("")+'</ul></div><div class="suggestion-box"><h3>Pontos de atenção</h3><ul>'+(a.risks||[]).map(function(x){return "<li>"+esc(x)+"</li>";}).join("")+'</ul></div></div>'+
    '<div class="note">O score é uma medida de regras técnicas e não representa probabilidade garantida de acerto. Em opções binárias, o resultado real também depende de cotação, payout, latência e regras da corretora.</div>'+
  '</div>';
  document.getElementById("optResult").innerHTML=html;
}
function renderBacktest(d){
  var b=d.backtest||{},expiry=d.expiry||document.getElementById("optExpiry").value;
  var html='<div class="result-box">'+
    '<div class="result-label">'+esc(d.symbol||"")+" · "+esc(String(expiry))+' min</div>'+
    '<div class="form-grid">'+
      '<div><strong>CALL</strong><br>'+pct(b.callHitRate)+'</div>'+
      '<div><strong>PUT</strong><br>'+pct(b.putHitRate)+'</div>'+
      '<div><strong>Amostras</strong><br>'+Number(b.samples||0)+'</div>'+
      '<div><strong>Empates</strong><br>'+Number(b.ties||0)+'</div>'+
    '</div>'+
    '<div class="note">'+esc(b.note||"Backtest histórico.")+'</div>'+
  '</div>';
  document.getElementById("optBacktest").innerHTML=html;
}
async function analyze(entryIndex){
  var st=document.getElementById("optStatus");
  try{
    st.textContent="⏳ Consultando candles de 1 minuto e calculando o ponto escolhido…";
    var d=await getData(entryIndex);
    state.candles=d.candles||[];
    state.entryIndex=Number.isInteger(d.entryIndex)?d.entryIndex:state.candles.length-1;
    chart();
    var label=document.getElementById("optPointLabel"),p=state.candles[state.entryIndex];if(p)label.textContent="Entrada · "+(p.datetime||"")+" · "+n(p.close,5);
    renderResult(d);renderBacktest(d);
    st.textContent="✅ Dados atualizados. O gráfico usa candles de 1 minuto para medir exatamente a expiração.";
  }catch(e){st.textContent="⚠️ "+e.message;}
}
function bind(){
  var a=document.getElementById("optAnalyzeBtn");if(!a)return;
  loadChart();
  document.getElementById("optLatestBtn").addEventListener("click",function(){state.entryIndex=state.candles.length-1;var p=state.candles[state.entryIndex];if(p)document.getElementById("optPointLabel").textContent="Último candle · "+(p.datetime||"")+" · "+n(p.close,5);chart();analyze(state.entryIndex);});
  a.addEventListener("click",function(){analyze(state.entryIndex>=0?state.entryIndex:-1);});
  document.getElementById("optSymbol").addEventListener("change",function(){state={candles:[],entryIndex:-1};document.getElementById("optStatus").textContent="Par alterado. Clique em analisar.";document.getElementById("optPointLabel").textContent="Último candle";});
  document.getElementById("optExpiry").addEventListener("change",function(){if(state.candles.length)analyze(state.entryIndex);});
}
function route(){
  if((location.hash||"").indexOf("analise-opcoes")<0)return false;
  var app=document.getElementById("app");if(!app)return false;app.innerHTML=ui;bind();analyze(-1);return true;
}
var oldRender=window.render;
window.render=function(){if(!route()&&oldRender)oldRender();};
if((location.hash||"").indexOf("analise-opcoes")>=0)route();
var nav=document.querySelector(".nav-links");
if(nav&&!document.getElementById("binaryOptionsNav")){
  var link=document.createElement("a");link.id="binaryOptionsNav";link.href="#/ferramenta/analise-opcoes";link.textContent="📊 Opções binárias";nav.insertBefore(link,nav.firstChild);
}
var s=document.createElement("style");
s.textContent='.options-binary-layout{grid-template-columns:1fr 1fr}.options-chart-panel{grid-column:1/-1}.opt-up{color:var(--success)}.opt-down{color:var(--danger)}.opt-neutral{color:var(--muted)}@media(max-width:920px){.options-binary-layout{grid-template-columns:1fr}.options-chart-panel{grid-column:auto}}';
document.head.appendChild(s);
})();