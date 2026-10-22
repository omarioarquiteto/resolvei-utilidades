/* Resolvei — Tabela FIPE com série histórica consultada na BrasilAPI */
(function(){
  const API = "/api/fipe";
  const VEHICLE_TYPES = [
    {value:"carros",label:"Carros"},
    {value:"motos",label:"Motos"},
    {value:"caminhoes",label:"Caminhões"}
  ];
  const currency = new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",minimumFractionDigits:2,maximumFractionDigits:2});
  const currencyAxis = new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0});
  const number = new Intl.NumberFormat("pt-BR",{maximumFractionDigits:2});
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  const money = value => currency.format(Number(value) || 0);
  const parsePrice = value => {
    if (typeof value === "number") return value;
    const raw = String(value ?? "").replace(/R\$|\s|\u00a0/g,"");
    if (!raw) return 0;
    const parsed = Number(raw.includes(",") ? raw.replace(/\./g,"").replace(",",".") : raw);
    return Number.isFinite(parsed) ? parsed : 0;
  };

  async function fetchJson(path){
    const response = await fetch(path,{headers:{"Accept":"application/json"}});
    let body;
    try { body = await response.json(); } catch { body = null; }
    if(!response.ok){
      const detail = body && (body.detail || body.message);
      throw new Error(detail || "Não foi possível consultar a BrasilAPI. Tente novamente.");
    }
    return body;
  }

  function selectOptions(select, items, placeholder, nameKey, valueKey){
    select.innerHTML = '<option value="">'+escapeHtml(placeholder)+'</option>' + items.map(item =>
      '<option value="'+escapeHtml(item[valueKey])+'">'+escapeHtml(item[nameKey])+'</option>'
    ).join("");
  }

  function monthShort(raw){
    const value = String(raw || "").trim().replace(/\s+de\s+/i,"/");
    const parts = value.split("/");
    if(parts.length >= 2){
      const month = parts[0].trim();
      const year = parts[1].trim();
      return (month.slice(0,3).charAt(0).toUpperCase()+month.slice(1,3).toLowerCase())+"/"+year.slice(-2);
    }
    return value;
  }

  function buildChart(history){
    if(!history || history.length < 1){
      return '<div class="fipe-chart-empty">Não há histórico de preço suficiente para este veículo e período nas referências disponíveis.</div>';
    }
    if(history.length === 1){
      return '<div class="fipe-chart-empty">A BrasilAPI retornou apenas uma referência válida para este ano-modelo. Selecione outro período ou tente novamente mais tarde.</div>';
    }
    const W=840,H=330,L=82,R=20,T=20,B=58;
    const plotW=W-L-R, plotH=H-T-B;
    const values=history.map(p=>Number(p.valor)).filter(v=>Number.isFinite(v));
    let min=Math.min(...values),max=Math.max(...values);
    if(min===max){const pad=Math.max(1,min*.04);min-=pad;max+=pad;}
    else {const pad=(max-min)*.12;min=Math.max(0,min-pad);max+=pad;}
    const x=i=>L+(i/(history.length-1))*plotW;
    const y=v=>T+((max-v)/(max-min))*plotH;
    const ticks=4;
    const grid=Array.from({length:ticks+1},(_,i)=>{
      const v=max-(max-min)*i/ticks,yy=T+plotH*i/ticks;
      return '<line class="gridline" x1="'+L+'" y1="'+yy.toFixed(2)+'" x2="'+(W-R)+'" y2="'+yy.toFixed(2)+'"></line>'+
        '<text class="axis-label" x="'+(L-12)+'" y="'+(yy+4).toFixed(2)+'" text-anchor="end">'+escapeHtml(currencyAxis.format(v))+'</text>';
    }).join("");
    const coords=history.map((p,i)=>({x:x(i),y:y(Number(p.valor)),p}));
    const line=coords.map(p=>p.x.toFixed(2)+","+p.y.toFixed(2)).join(" ");
    const area="M "+coords[0].x.toFixed(2)+" "+(T+plotH)+" L "+coords.map(p=>p.x.toFixed(2)+" "+p.y.toFixed(2)).join(" L ")+" L "+coords[coords.length-1].x.toFixed(2)+" "+(T+plotH)+" Z";
    const points=coords.map(p=>'<circle class="price-point" cx="'+p.x.toFixed(2)+'" cy="'+p.y.toFixed(2)+'" r="4"><title>'+escapeHtml(p.p.mes)+': '+escapeHtml(money(p.p.valor))+'</title></circle>').join("");
    const labelEvery=Math.max(1,Math.ceil(history.length/6));
    const xLabels=history.map((p,i)=>({p,i})).filter(({i})=>i%labelEvery===0||i===history.length-1).map(({p,i})=>
      '<text class="axis-label" x="'+x(i).toFixed(2)+'" y="'+(H-26)+'" text-anchor="'+(i===0?"start":i===history.length-1?"end":"middle")+'">'+escapeHtml(monthShort(p.mes))+'</text>'
    ).join("");
    return '<svg class="fipe-chart" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Gráfico de evolução mensal do preço FIPE">'+grid+
      '<path class="price-area" d="'+area+'"></path><polyline class="price-line" points="'+line+'"></polyline>'+points+xLabels+'</svg>';
  }

  function init(){
    const host=document.getElementById("tabelaFipeToolHost");
    if(!host || host.dataset.fipeReady==="1") return;
    host.dataset.fipeReady="1";
    const state={type:"carros",brands:[],models:[],years:[],detail:null,history:[],requestId:0};
    host.innerHTML=
      '<div class="fipe-tool">'+
        '<div class="breadcrumb"><a href="#/">Início</a> / <a href="#/categoria/carro">Carro &amp; Viagem</a> / Tabela FIPE</div>'+
        '<header class="fipe-head"><div><div class="fipe-eyebrow">CONSULTA VEICULAR</div><h1>Tabela FIPE</h1><p>Consulte o valor de referência de carros, motos e caminhões e acompanhe a evolução mensal do preço do modelo escolhido.</p></div><div class="fipe-source-pill"><span class="fipe-source-dot"></span>Dados da BrasilAPI / FIPE</div></header>'+
        '<section class="fipe-panel"><h2>Encontre seu veículo</h2><p class="fipe-panel-intro">Selecione tipo, marca, modelo e ano-modelo para consultar o valor e o histórico disponível.</p>'+
          '<form id="fipe-search-form">'+
            '<div class="fipe-fields">'+
              '<div class="fipe-field"><label for="fipe-type">Tipo de veículo</label><select id="fipe-type">'+VEHICLE_TYPES.map(v=>'<option value="'+v.value+'">'+v.label+'</option>').join("")+'</select></div>'+
              '<div class="fipe-field"><label for="fipe-brand">Marca</label><select id="fipe-brand" disabled><option value="">Carregando marcas…</option></select></div>'+
              '<div class="fipe-field"><label for="fipe-model">Modelo</label><select id="fipe-model" disabled><option value="">Selecione a marca primeiro</option></select></div>'+
              '<div class="fipe-field"><label for="fipe-year">Ano-modelo e combustível</label><select id="fipe-year" disabled><option value="">Selecione o modelo primeiro</option></select></div>'+
            '</div>'+
            '<div class="fipe-actions"><button class="fipe-btn fipe-btn-primary" type="submit" id="fipe-query" disabled>Consultar valor e evolução</button><button class="fipe-btn" type="button" id="fipe-reset">Limpar seleção</button></div>'+
            '<div class="fipe-status" id="fipe-form-status" role="status" aria-live="polite">Carregando marcas da FIPE…</div>'+
          '</form>'+
        '</section>'+
        '<section id="fipe-results" class="fipe-results" hidden aria-live="polite"></section>'+
        '<p class="fipe-legal">Os valores são referências médias da Tabela FIPE, não uma oferta de compra ou venda. A evolução reflete as referências mensais disponibilizadas pela fonte; meses sem dados para a versão selecionada não são estimados nem preenchidos artificialmente.</p>'+
      '</div>';

    const typeEl=host.querySelector("#fipe-type");
    const brandEl=host.querySelector("#fipe-brand");
    const modelEl=host.querySelector("#fipe-model");
    const yearEl=host.querySelector("#fipe-year");
    const queryBtn=host.querySelector("#fipe-query");
    const resetBtn=host.querySelector("#fipe-reset");
    const formStatus=host.querySelector("#fipe-form-status");
    const results=host.querySelector("#fipe-results");

    function status(message,kind){
      formStatus.textContent=message||"";
      formStatus.dataset.kind=kind||"";
    }
    function setLoading(button,loading,label){
      if(!button) return;
      button.disabled=Boolean(loading);
      if(loading){button.dataset.originalText=button.textContent;button.innerHTML='<span class="fipe-spinner" aria-hidden="true"></span> '+escapeHtml(label||"Consultando…");}
      else if(button.dataset.originalText){button.textContent=button.dataset.originalText;delete button.dataset.originalText;}
    }
    async function loadBrands(){
      state.type=typeEl.value;
      brandEl.disabled=true;modelEl.disabled=true;yearEl.disabled=true;queryBtn.disabled=true;
      modelEl.innerHTML='<option value="">Selecione a marca primeiro</option>';
      yearEl.innerHTML='<option value="">Selecione o modelo primeiro</option>';
      status("Carregando marcas…");
      try{
        state.brands=await fetchJson(API+"/brands/"+encodeURIComponent(state.type));
        selectOptions(brandEl,state.brands,"Selecione a marca","nome","valor");
        brandEl.disabled=false;
        status("Selecione a marca do veículo.");
      }catch(error){
        status(error.message,"error");
        brandEl.innerHTML='<option value="">Não foi possível carregar as marcas</option>';
      }
    }
    async function loadModels(){
      const brandId=brandEl.value;
      state.models=[];state.years=[];state.detail=null;state.history=[];
      modelEl.disabled=true;yearEl.disabled=true;queryBtn.disabled=true;
      modelEl.innerHTML='<option value="">Carregando modelos…</option>';
      yearEl.innerHTML='<option value="">Selecione o modelo primeiro</option>';
      results.hidden=true;
      if(!brandId){modelEl.innerHTML='<option value="">Selecione a marca primeiro</option>';return;}
      status("Carregando modelos da marca…");
      try{
        state.models=await fetchJson(API+"/models/"+encodeURIComponent(state.type)+"/"+encodeURIComponent(brandId));
        selectOptions(modelEl,state.models,"Selecione o modelo","modelo","valor");
        modelEl.disabled=false;
        status("Agora escolha o modelo.");
      }catch(error){
        modelEl.innerHTML='<option value="">Não foi possível carregar os modelos</option>';
        status(error.message,"error");
      }
    }
    async function loadYears(){
      const brandId=brandEl.value,modelId=modelEl.value;
      state.years=[];state.detail=null;state.history=[];
      yearEl.disabled=true;queryBtn.disabled=true;
      yearEl.innerHTML='<option value="">Carregando anos-modelo…</option>';
      results.hidden=true;
      if(!brandId||!modelId){yearEl.innerHTML='<option value="">Selecione o modelo primeiro</option>';return;}
      status("Carregando anos e combustíveis disponíveis…");
      try{
        state.years=await fetchJson(API+"/years/"+encodeURIComponent(state.type)+"/"+encodeURIComponent(brandId)+"/"+encodeURIComponent(modelId));
        selectOptions(yearEl,state.years,"Selecione o ano-modelo","nome","valor");
        yearEl.disabled=false;
        status("Selecione o ano-modelo e consulte.");
      }catch(error){
        yearEl.innerHTML='<option value="">Não foi possível carregar os anos</option>';
        status(error.message,"error");
      }
    }

    function renderResults(details,history,months){
      const current=parsePrice(details.valor ?? details.price);
      const first=history.length?history[0]:null;
      const last=history.length?history[history.length-1]:null;
      const change=first&&last&&first.valor>0?((last.valor-first.valor)/first.valor)*100:null;
      const delta=first&&last?last.valor-first.valor:null;
      const deltaClass=delta===null?"":delta>0?"fipe-up":delta<0?"fipe-down":"";
      const changeText=change===null?"Sem série suficiente":(change>0?"+":"")+number.format(change)+"%";
      const deltaText=delta===null?"—":(delta>0?"+":"")+money(delta);
      const fuel=details.combustivel||"Combustível não informado";
      const code=details.codigoFipe||details.codeFipe||"—";
      const reference=String(details.mesReferencia||details.referenceMonth||"Referência atual").trim();
      results.innerHTML=
        '<section class="fipe-panel">'+
          '<div class="fipe-vehicle-line"><div><div class="fipe-eyebrow">VEÍCULO SELECIONADO</div><h2>'+escapeHtml((details.marca||details.brand||"")+" "+(details.modelo||details.model||""))+'</h2><div class="fipe-vehicle-subtitle">'+escapeHtml(String(details.anoModelo ?? details.modelYear ?? ""))+' · '+escapeHtml(fuel)+' · Código FIPE '+escapeHtml(code)+'</div></div>'+
            '<div class="fipe-current-price"><span>Valor de referência</span><strong>'+escapeHtml(money(current))+'</strong><small>Referência: '+escapeHtml(reference)+'</small></div></div>'+
          '<div class="fipe-metrics">'+
            '<div class="fipe-metric"><span class="fipe-metric-label">Variação no período observado</span><strong class="'+deltaClass+'">'+escapeHtml(changeText)+'</strong><small>'+(first&&last?escapeHtml(monthShort(first.mes)+" a "+monthShort(last.mes)):"Histórico não disponível")+'</small></div>'+
            '<div class="fipe-metric"><span class="fipe-metric-label">Diferença de preço no período</span><strong class="'+deltaClass+'">'+escapeHtml(deltaText)+'</strong><small>Primeira e última referência retornadas</small></div>'+
            '<div class="fipe-metric"><span class="fipe-metric-label">Pontos no gráfico</span><strong>'+history.length+'</strong><small>Referências mensais válidas · até '+months+' meses</small></div>'+
          '</div>'+
        '</section>'+
        '<section class="fipe-panel"><div class="fipe-chart-head"><div><h2>Evolução do preço FIPE</h2><p class="fipe-panel-intro">Histórico mensal do mesmo código FIPE e ano-modelo.</p></div><div class="fipe-range"><label for="fipe-range">Período do gráfico</label><select id="fipe-range"><option value="6" '+(months===6?"selected":"")+'>6 meses</option><option value="12" '+(months===12?"selected":"")+'>12 meses</option><option value="24" '+(months===24?"selected":"")+'>24 meses</option></select></div></div>'+
          '<div id="fipe-chart-container">'+buildChart(history)+'</div>'+
          '<p class="fipe-chart-note">Cada ponto representa uma referência mensal encontrada na BrasilAPI. Lacunas são omitidas quando a versão não está disponível naquele mês.</p>'+
        '</section>'+
        '<section class="fipe-panel"><h2>Histórico por referência</h2><p class="fipe-panel-intro">Valores apresentados do mais recente para o mais antigo.</p>'+
          (history.length?'<div class="fipe-table-wrap"><table class="fipe-table"><thead><tr><th>Referência</th><th>Valor FIPE</th><th>Variação mensal</th></tr></thead><tbody>'+
            history.slice().reverse().map((item,reverseIndex)=>{
              const index=history.length-1-reverseIndex;
              const previous=index>0?history[index-1]:null;
              const monthChange=previous&&previous.valor>0?((item.valor-previous.valor)/previous.valor)*100:null;
              const cls=monthChange===null?"":monthChange>0?"fipe-up":monthChange<0?"fipe-down":"";
              const ch=monthChange===null?"—":(monthChange>0?"+":"")+number.format(monthChange)+"%";
              return '<tr><td>'+escapeHtml(item.mes)+'</td><td>'+escapeHtml(money(item.valor))+'</td><td class="'+cls+'">'+escapeHtml(ch)+'</td></tr>';
            }).join("")+
          '</tbody></table></div>':'<div class="fipe-chart-empty">Ainda não há valores históricos suficientes para a versão escolhida. O valor de referência atual está disponível acima.</div>')+
        '</section>';
      const range=results.querySelector("#fipe-range");
      range?.addEventListener("change",()=>loadHistory(Number(range.value)));
    }

    async function loadHistory(months){
      if(!state.detail) return;
      const details=state.detail;
      const code=details.codigoFipe||details.codeFipe;
      const year=Number(details.anoModelo ?? details.modelYear);
      const chartContainer=results.querySelector("#fipe-chart-container");
      if(chartContainer) chartContainer.innerHTML='<div class="fipe-chart-empty"><span class="fipe-spinner" aria-hidden="true"></span> Consultando as referências mensais…</div>';
      try{
        const data=await fetchJson(API+"/history/"+encodeURIComponent(code)+"?year_model="+encodeURIComponent(year)+"&months="+encodeURIComponent(months));
        state.history=Array.isArray(data.historico)?data.historico:[];
        renderResults(details,state.history,months);
        status("Consulta concluída. Histórico com "+state.history.length+" referências válidas.","success");
      }catch(error){
        state.history=[];
        renderResults(details,[],months);
        const empty=results.querySelector("#fipe-chart-container");
        if(empty)empty.innerHTML='<div class="fipe-chart-empty">'+escapeHtml(error.message)+' O valor FIPE atual continua disponível; tente atualizar o histórico mais tarde.</div>';
        status("Valor atual consultado; não foi possível carregar a série histórica.","error");
      }
    }

    async function consult(){
      const brandId=brandEl.value,modelId=modelEl.value,yearCode=yearEl.value;
      if(!brandId||!modelId||!yearCode){status("Selecione tipo, marca, modelo e ano-modelo.","error");return;}
      const myRequest=++state.requestId;
      setLoading(queryBtn,true,"Consultando veículo…");
      status("Consultando valor atual da FIPE…");
      results.hidden=false;
      results.innerHTML='<section class="fipe-panel"><div class="fipe-chart-empty"><span class="fipe-spinner" aria-hidden="true"></span> Consultando preço e preparando o histórico…</div></section>';
      try{
        const url=API+"/details/"+encodeURIComponent(state.type)+"/"+encodeURIComponent(brandId)+"/"+encodeURIComponent(modelId)+"/"+encodeURIComponent(yearCode);
        const details=await fetchJson(url);
        if(myRequest!==state.requestId)return;
        state.detail=details;
        const months=Number(host.querySelector("#fipe-range")?.value||12);
        renderResults(details,[],months);
        await loadHistory(months);
      }catch(error){
        if(myRequest!==state.requestId)return;
        results.hidden=false;
        results.innerHTML='<section class="fipe-panel"><h2>Não foi possível concluir a consulta</h2><p class="fipe-status" data-kind="error">'+escapeHtml(error.message)+'</p><p class="fipe-panel-intro">Confira a seleção e tente novamente. A consulta usa as informações públicas fornecidas pela BrasilAPI.</p></section>';
        status(error.message,"error");
      }finally{
        if(myRequest===state.requestId)setLoading(queryBtn,false);
      }
    }

    typeEl.addEventListener("change",()=>{results.hidden=true;loadBrands();});
    brandEl.addEventListener("change",loadModels);
    modelEl.addEventListener("change",loadYears);
    yearEl.addEventListener("change",()=>{queryBtn.disabled=!yearEl.value;results.hidden=true;status(yearEl.value?"Pronto para consultar o valor e o histórico.":"Selecione o ano-modelo.");});
    host.querySelector("#fipe-search-form").addEventListener("submit",event=>{event.preventDefault();consult();});
    resetBtn.addEventListener("click",()=>{
      state.detail=null;state.history=[];state.requestId++;
      typeEl.value="carros";brandEl.innerHTML='<option value="">Carregando marcas…</option>';modelEl.innerHTML='<option value="">Selecione a marca primeiro</option>';yearEl.innerHTML='<option value="">Selecione o modelo primeiro</option>';
      modelEl.disabled=true;yearEl.disabled=true;queryBtn.disabled=true;results.hidden=true;
      loadBrands();
    });
    loadBrands();
  }

  window.resolveiTabelaFipeInit=init;
})();