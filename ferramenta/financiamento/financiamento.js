/* Resolvei — módulo de financiamento e comparação */
(function(){
  "use strict";

  var ENDPOINT="/api/financiamento/dados";
  var state={tipo:"imovel",linha:"tr",dados:null,lastSimulation:null};

  function escF(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function moneyF(n){return new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:2}).format(Number(n)||0);}
  function pctF(n){return new Intl.NumberFormat("pt-BR",{maximumFractionDigits:2}).format(Number(n)||0)+"%";}
  function get(id){return document.getElementById(id);}
  function value(id){return Number(get(id)?get(id).value:0)||0;}
  function selected(id){return get(id)?get(id).value:"";}
  function annualFromMonthly(i){return (Math.pow(1+(Number(i)||0)/100,12)-1)*100;}
  function monthlyFromAnnual(a){return (Math.pow(1+(Number(a)||0)/100,1/12)-1)*100;}

  function simulate(pv,ratePct,n,system){
    var rate=Math.max(0,Number(ratePct)||0)/100;
    var months=Math.max(1,Math.round(Number(n)||1));
    var principal=Math.max(0,Number(pv)||0);
    if(!principal)return null;
    var rows=[],balance=principal,totalInterest=0,totalPaid=0,m,interest,payment,amort,actual;
    if(system==="SAC"){
      amort=principal/months;
      for(m=1;m<=months;m++){
        interest=balance*rate; payment=amort+interest; balance=Math.max(0,balance-amort);
        rows.push({month:m,payment:payment,interest:interest,amortization:amort,balance:balance});
        totalInterest+=interest; totalPaid+=payment;
      }
    }else{
      payment=rate?principal*rate/(1-Math.pow(1+rate,-months)):principal/months;
      for(m=1;m<=months;m++){
        interest=balance*rate; amort=Math.min(balance,Math.max(0,payment-interest)); actual=amort+interest; balance=Math.max(0,balance-amort);
        rows.push({month:m,payment:actual,interest:interest,amortization:amort,balance:balance});
        totalInterest+=interest; totalPaid+=actual;
      }
    }
    return {first:rows[0]?rows[0].payment:0,last:rows[rows.length-1]?rows[rows.length-1].payment:0,totalInterest:totalInterest,totalPaid:totalPaid,rows:rows,financed:principal,effectiveAnnual:annualFromMonthly(ratePct)};
  }

  function financingUI(){
    return '<div class="financing-tool">'+
      '<div class="financing-hero"><div><h2>Calculadora & Comparador de Financiamentos</h2><p>Simule veículos e imóveis, compare bancos, SAC e PRICE e veja quanto a operação pode custar. As taxas de mercado usam dados públicos do Banco Central.</p></div>'+
      '<div class="financing-tabs" role="tablist"><button id="finTabImovel" class="active" type="button">🏠 Imóvel</button><button id="finTabVeiculo" type="button">🚗 Veículo</button></div></div>'+
      '<div id="financingStatus" class="financing-status">Carregando referências de mercado…</div>'+
      '<div class="financing-grid">'+
      '<section class="financing-card"><h3>Dados da operação</h3><div class="financing-form">'+
      '<div class="field full"><label>Valor do bem</label><input id="finAsset" type="number" min="0" step="0.01" value="500000"></div>'+
      '<div class="field"><label>Entrada</label><input id="finDown" type="number" min="0" step="0.01" value="100000"></div>'+
      '<div class="field"><label>Prazo (meses)</label><input id="finTerm" type="number" min="1" step="1" value="360"></div>'+
      '<div class="field full"><label>Valor financiado</label><input id="finPV" type="number" min="0" step="0.01" value="400000"></div>'+
      '<div id="propertyFields" class="field full"><div class="financing-form">'+
      '<div class="field"><label>Banco de referência</label><select id="finBankRefProperty"></select></div>'+
      '<div class="field"><label>Modalidade / indexador</label><select id="finLine"><option value="tr">Mercado — TR</option><option value="prefixado">Mercado — prefixado</option><option value="poupanca">Juros da poupança</option><option value="tr_regulado">Regulado — TR</option><option value="prefixado_regulado">Regulado — prefixado</option></select></div>'+
      '<div class="field"><label>Sistema de amortização</label><select id="finSystem"><option value="SAC">SAC</option><option value="PRICE">PRICE</option></select></div>'+
      '<div class="field"><label>Tipo de imóvel</label><select id="finPropertyType"><option>Residencial</option><option>Comercial</option></select></div>'+
      '<div class="field"><label>Renda familiar mensal (opcional)</label><input id="finIncome" type="number" min="0" step="0.01" placeholder="Ex.: 12000"></div>'+
      '<div class="field"><label>FGTS disponível (opcional)</label><input id="finFGTS" type="number" min="0" step="0.01" placeholder="Ex.: 50000"></div>'+
      '<div class="field"><label>Correção mensal de cenário (opcional)</label><input id="finIndexer" type="number" min="0" step="0.0001" value="0" placeholder="Ex.: 0,10"><div class="financing-help">A correção futura não é conhecida. Este campo é apenas informativo para um cenário indicado por você.</div></div>'+
      '</div></div>'+
      '<div id="vehicleFields" class="field full" hidden><div class="financing-form">'+
      '<div class="field"><label>Veículo</label><select id="finVehicleType"><option>Carro</option><option>Motocicleta</option><option>Utilitário</option><option>Caminhão</option></select></div>'+
      '<div class="field"><label>Condição</label><select id="finVehicleAge"><option>Novo</option><option>Usado</option></select></div>'+
      '<div class="field"><label>Ano do veículo (opcional)</label><input id="finVehicleYear" type="number" min="1980" max="2100" placeholder="Ex.: 2024"></div>'+
      '<div class="field"><label>Banco de referência</label><select id="finBankRef"></select></div>'+
      '<div class="field full"><div class="financing-help">Para veículos, o Resolvei usa parcelas fixas/PRICE como aproximação matemática de uma operação prefixada. A contratação real pode ter regras e custos próprios.</div></div>'+
      '</div></div>'+
      '<div class="field"><label>Taxa mensal da sua proposta (opcional)</label><input id="finManualRate" type="number" min="0" step="0.0001" placeholder="Ex.: 1,39"></div>'+
      '<div class="field"><label>CET anual da sua proposta (opcional)</label><input id="finCET" type="number" min="0" step="0.0001" placeholder="Ex.: 19,50"></div>'+
      '<div class="field full"><label>Custos adicionais únicos (opcional)</label><input id="finFees" type="number" min="0" step="0.01" value="0" placeholder="IOF, registro, cartório etc."></div>'+
      '<div class="field full"><label>Custo mensal adicional (opcional)</label><input id="finMonthlyCosts" type="number" min="0" step="0.01" value="0" placeholder="Seguro, tarifa mensal etc."></div>'+
      '</div><div class="financing-actions"><button class="financing-btn primary" id="finCalcBtn">Calcular minha simulação</button><button class="financing-btn secondary" id="finCompareBtn">Comparar bancos</button><button class="financing-btn secondary" id="finRefreshBtn">↻ Atualizar taxas</button></div></section>'+
      '<section class="financing-results">'+
      '<div id="finSummary" class="financing-card"><h3>Resultado da sua simulação</h3><div class="financing-kpis" id="finKpis"></div><div id="finSummaryNote" class="financing-note" style="margin-top:12px">Preencha os dados e calcule para ver a estimativa.</div></div>'+
      '<div id="finSchedule"></div>'+
      '<div id="finCompareBox" class="financing-card"><h3>Comparação por banco</h3><div class="financing-note">A comparação usa o benchmark médio do Banco Central. Para decidir uma proposta real, compare o CET do contrato.</div><div id="finCompareContent" style="margin-top:12px"></div></div>'+
      '<div id="finRulesBox" class="financing-card"><h3>Regras públicas e fontes oficiais</h3><div id="finRules" class="financing-rule-grid"></div></div>'+
      '</section></div></div>';
  }

  function populateBankSelect(){
    var sel=get("finBankRef");if(!sel)return;
    var banks=(state.dados&&state.dados.banks)||[];
    sel.innerHTML=banks.map(function(b){return '<option value="'+escF(b.id)+'">'+escF(b.name)+'</option>';}).join("")||"<option value=''>Selecione</option>";
    if((state.dados&&state.dados.market&&state.dados.market.rates||[]).some(function(x){return x.id==="caixa";}))sel.value="caixa";
    var prop=get("finBankRefProperty"); if(prop){prop.innerHTML=banks.map(function(b){return '<option value="'+escF(b.id)+'">'+escF(b.name)+'</option>';}).join("")||"<option value=''>Selecione</option>"; if((state.dados&&state.dados.market&&state.dados.market.rates||[]).some(function(x){return x.id==="caixa";}))prop.value="caixa";}
  }

  function renderRules(){
    var box=get("finRules");if(!box)return;
    var banks=(state.dados&&state.dados.banks)||[];
    var field=state.tipo==="veiculo"?"vehicle":"real_estate";
    box.innerHTML=banks.map(function(b){
      var desc=b[field]||"Condições não resumidas nesta versão.";
      var source=b[state.tipo==="veiculo"?"source_vehicle":"source_real_estate"]||"#";
      return '<article class="financing-rule"><strong>'+escF(b.name)+'</strong><p>'+escF(desc)+'</p><a href="'+escF(source)+'" target="_blank" rel="noopener noreferrer">Fonte oficial ↗</a></article>';
    }).join("");
  }

  function currentRate(){
    var cet=value("finCET"),manual=value("finManualRate");
    if(cet>0)return {rate:monthlyFromAnnual(cet),source:"CET informado pelo usuário (taxa mensal equivalente aproximada)"};
    if(manual>0)return {rate:manual,source:"taxa mensal informada pelo usuário"};
    var ref=state.tipo==="veiculo"?selected("finBankRef"):(selected("finBankRefProperty")||"caixa");
    var rates=(state.dados&&state.dados.market&&state.dados.market.rates)||[];
    var r=null;
    rates.some(function(x){if(x.id===ref){r=x;return true;}return false;});
    if(!r)r=rates.find(function(x){return x.monthly_rate>0;});
    if(r)return {rate:r.monthly_rate,source:r.name+" — média BCB ("+(r.start_date||r.month||(state.dados.market.reference_period||""))+")"};
    return {rate:0,source:"sem taxa de referência disponível"};
  }

  function calculateCurrent(){
    var asset=value("finAsset"),down=value("finDown"),pv=value("finPV");
    if(asset>0 && down>asset){alert("A entrada não pode ser maior que o valor do bem.");return;}
    if(pv<=0)pv=Math.max(0,asset-down);
    var term=Math.max(1,Math.round(value("finTerm")||1));
    var system=state.tipo==="veiculo"?"PRICE":(selected("finSystem")||"SAC");
    var r=currentRate();
    if(r.rate<=0){get("finSummaryNote").innerHTML="Informe uma taxa ou use uma linha com referência do Banco Central.";return;}
    var sim=simulate(pv,r.rate,term,system);if(!sim)return;
    state.lastSimulation={sim:sim,rate:r.rate,system:system};
    var totalWithCosts=sim.totalPaid+value("finFees")+value("finMonthlyCosts")*term;
    get("finKpis").innerHTML=[["Primeira parcela",moneyF(sim.first)],["Última parcela",moneyF(sim.last)],["Juros totais",moneyF(sim.totalInterest)],["Total estimado",moneyF(totalWithCosts)]].map(function(x){return '<div class="financing-kpi"><span>'+x[0]+'</span><strong>'+x[1]+'</strong></div>';}).join("");
    get("finSummaryNote").innerHTML="<strong>Taxa usada:</strong> "+pctF(r.rate)+" a.m. ("+pctF(annualFromMonthly(r.rate))+" a.a. efetivos). Fonte: "+escF(r.source)+". <strong>Importante:</strong> seguros, tarifas, impostos, indexadores futuros e critérios de crédito podem alterar o valor real.";
    renderSchedule(sim);
    get("financingStatus").textContent="Simulação de "+(state.tipo==="veiculo"?"veículo":"imóvel")+" usando "+system+".";
  }

  function renderSchedule(sim){
    var box=get("finSchedule");if(!box)return;
    var rows=sim.rows, sample=[].concat(rows.slice(0,3),rows.slice(Math.max(0,rows.length-3))),seen={},unique=[];
    sample.forEach(function(r){if(!seen[r.month]){seen[r.month]=true;unique.push(r);}});
    box.innerHTML='<div class="financing-schedule"><div class="financing-schedule-box"><h4>Evolução selecionada</h4><table class="financing-mini-table">'+unique.map(function(r){return '<tr><td>'+r.month+'ª parcela</td><td>'+moneyF(r.payment)+'</td></tr>';}).join("")+'</table></div><div class="financing-schedule-box"><h4>Composição</h4><table class="financing-mini-table"><tr><td>Principal financiado</td><td>'+moneyF(sim.financed)+'</td></tr><tr><td>Juros totais</td><td>'+moneyF(sim.totalInterest)+'</td></tr><tr><td>Taxa anual equivalente</td><td>'+pctF(sim.effectiveAnnual)+'</td></tr><tr><td>Prazo</td><td>'+rows.length+' meses</td></tr></table></div></div>';
  }

  function compareBanks(){
    var rates=(state.dados&&state.dados.market&&state.dados.market.rates)||[],box=get("finCompareContent");if(!box)return;
    if(!rates.length){box.innerHTML='<div class="financing-note"><strong>Comparação automática indisponível para esta linha.</strong> O BCB não publica nesta API um benchmark equivalente para juros da poupança. Informe a taxa/CET das propostas para comparação.</div>';return;}
    var asset=value("finAsset"),down=value("finDown"),pv=Math.max(0,value("finPV")||asset-down),term=Math.max(1,Math.round(value("finTerm")||1)),system=state.tipo==="veiculo"?"PRICE":(selected("finSystem")||"SAC");
    if(!pv){box.innerHTML='<div class="financing-note">Informe o valor financiado.</div>';return;}
    var items=rates.filter(function(x){return x.monthly_rate>0;}).sort(function(a,b){return a.monthly_rate-b.monthly_rate;});
    var best=items[0];
    box.innerHTML='<div class="financing-table-wrap"><table class="financing-table"><thead><tr><th>Banco / instituição</th><th>Taxa a.m.</th><th>Taxa a.a.</th><th>1ª parcela</th><th>Última</th><th>Juros</th><th>Total</th></tr></thead><tbody>'+
      items.slice(0,30).map(function(b,i){var sim=simulate(pv,b.monthly_rate,term,system);if(!sim)return "";return '<tr class="'+(b.id===best.id?"best":"")+'"><td><span class="financing-bank-name">'+escF(b.name)+'</span>'+(i===0?'<span class="financing-badge good">menor taxa</span>':"")+'<span class="financing-sub">'+escF(b.start_date||b.month||(state.dados.market.reference_period||""))+'</span></td><td>'+pctF(b.monthly_rate)+'</td><td>'+pctF(annualFromMonthly(b.monthly_rate))+'</td><td>'+moneyF(sim.first)+'</td><td>'+moneyF(sim.last)+'</td><td>'+moneyF(sim.totalInterest)+'</td><td>'+moneyF(sim.totalPaid)+'</td></tr>';}).join("")+
      '</tbody></table></div><div class="financing-note" style="margin-top:10px"><strong>Como interpretar:</strong> a menor taxa média não garante a menor proposta final. Quando tiver as propostas reais, compare o <strong>CET</strong>, as tarifas, seguros, entrada, prazo e o total contratado.</div>';
  }

  async function loadData(force){
    var st=get("financingStatus");
    if(st)st.textContent="Atualizando referências do Banco Central…";
    if(force){try{await fetch("/api/financiamento/atualizar?tipo="+(state.tipo==="veiculo"?"veiculo":"imovel")+"&linha="+encodeURIComponent(state.linha),{method:"POST"});}catch(e){}}
    try{
      var rr=await fetch(ENDPOINT+"?tipo="+(state.tipo==="veiculo"?"veiculo":"imovel")+"&linha="+encodeURIComponent(state.tipo==="veiculo"?"veiculo":state.linha));
      var data=await rr.json();if(!rr.ok)throw new Error(data.detail||"Falha ao carregar dados.");
      state.dados=data;populateBankSelect();renderRules();
      var market=data.market||{};
      if(st)st.textContent="Referência BCB atualizada: "+(market.reference_start||market.reference_period||"dados atuais")+(market.reference_end?" a "+market.reference_end:"")+".";
    }catch(e){
      state.dados=null;if(st)st.innerHTML="⚠️ "+escF(e.message||"Não foi possível atualizar as taxas.");
      renderRules();
    }
  }

  function switchType(tipo){
    state.tipo=tipo;
    get("finTabImovel").classList.toggle("active",tipo==="imovel");get("finTabVeiculo").classList.toggle("active",tipo==="veiculo");
    get("propertyFields").hidden=tipo!=="imovel";get("vehicleFields").hidden=tipo!=="veiculo";
    if(tipo==="veiculo"){get("finTerm").value=60;get("finAsset").value=80000;get("finDown").value=20000;get("finPV").value=60000;}
    else{get("finTerm").value=360;get("finAsset").value=500000;get("finDown").value=100000;get("finPV").value=400000;}
    get("finCompareContent").innerHTML='<div class="financing-note">Clique em “Comparar bancos” para carregar as instituições.</div>';
    loadData(false);
  }

  function bind(){
    get("finTabImovel").addEventListener("click",function(){switchType("imovel");});
    get("finTabVeiculo").addEventListener("click",function(){switchType("veiculo");});
    get("finLine").addEventListener("change",function(e){state.linha=e.target.value;loadData(false);});
    get("finCalcBtn").addEventListener("click",calculateCurrent);
    get("finCompareBtn").addEventListener("click",compareBanks);
    get("finRefreshBtn").addEventListener("click",function(){loadData(true);});
    ["finAsset","finDown"].forEach(function(id){get(id).addEventListener("input",function(){var a=value("finAsset"),d=value("finDown");if(a>=d)get("finPV").value=(a-d).toFixed(2);});});
  }

  function init(){
    var host=get("financiamentoToolHost");if(!host)return;
    if(!get("financiamentoCss")){var link=document.createElement("link");link.id="financiamentoCss";link.rel="stylesheet";link.href="/ferramenta/financiamento/financiamento.css?v=20261006";document.head.appendChild(link);}
    host.className="financing-host";host.innerHTML=financingUI();bind();loadData(false);
  }

  window.resolveiFinanciamentoInit=init;
})();
