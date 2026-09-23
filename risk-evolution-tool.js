/* Resolvei — Gerenciamento de risco e evolução de capital
   Modelo baseado na planilha enviada pelo usuário:
   - cada seção começa com um capital-base;
   - a 1ª entrada usa uma porcentagem fixa do capital da seção;
   - o payout da vitória define o lucro necessário para avançar uma seção;
   - entradas seguintes são recalculadas para compensar perdas acumuladas e ainda alcançar o próximo alvo;
   - após uma vitória, o capital da seção vira o alvo da próxima seção e o contador de chances reinicia.
   Os cálculos são determinísticos e funcionam localmente no navegador.
*/

const RISK_STORAGE_KEY = 'resolvei_risk_evolution_v1';

const riskMoney = n => (typeof money === 'function' ? money(n) : `R$ ${Number(n || 0).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}`);
const riskNum = n => (typeof num === 'function' ? num(n) : Number(n || 0).toLocaleString('pt-BR',{maximumFractionDigits:2}));
const riskPct = n => (typeof pct === 'function' ? pct(n) : `${Number(n || 0).toLocaleString('pt-BR',{maximumFractionDigits:2})}%`);
const riskRead = id => Math.max(0, Number(document.getElementById(id)?.value || 0));

function riskDefaults(){
  return {
    config: {
      initialCapital: 500,
      entryPct: 0.5,
      payout: 85,
      chances: 7,
      goal: 10000
    },
    session: {
      capital: 500,
      section: 1,
      chance: 1,
      baseCapital: 500,
      accumulatedLoss: 0,
      status: 'active'
    },
    history: []
  };
}

function riskLoad(){
  try{
    const raw = JSON.parse(localStorage.getItem(RISK_STORAGE_KEY) || 'null');
    if(!raw) return riskDefaults();
    return {
      config: {...riskDefaults().config,...(raw.config||{})},
      session: {...riskDefaults().session,...(raw.session||{})},
      history: Array.isArray(raw.history) ? raw.history.slice(-80) : []
    };
  }catch{
    return riskDefaults();
  }
}

let resolveiRiskState = riskLoad();

function riskSave(){
  try{ localStorage.setItem(RISK_STORAGE_KEY, JSON.stringify(resolveiRiskState)); }catch{}
}

let resolveiRiskCloudUid = null;
let resolveiRiskHydratingUid = null;
let resolveiRiskCloudSaveTimer = null;

function riskLoggedInUser(){
  return (typeof resolveiUser !== 'undefined' && resolveiUser) ? resolveiUser : null;
}

async function riskCloudGet(){
  const user=riskLoggedInUser();
  if(!user) return {exists:false,state:null};
  const token=await resolveiToken();
  const response=await fetch('/api/risk/state',{headers:{Authorization:'Bearer '+token}});
  let data={};
  try{data=await response.json();}catch{}
  if(!response.ok) throw new Error(data.detail||'Não foi possível carregar seu progresso.');
  return data;
}

async function riskCloudPut(showStatus=false){
  const user=riskLoggedInUser();
  if(!user) return false;
  try{
    const token=await resolveiToken();
    const response=await fetch('/api/risk/state',{
      method:'PUT',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},
      body:JSON.stringify({state:resolveiRiskState})
    });
    let data={};
    try{data=await response.json();}catch{}
    if(!response.ok) throw new Error(data.detail||'Não foi possível salvar seu progresso.');
    resolveiRiskCloudUid=user.uid;
    const status=document.getElementById('riskCloudStatus');
    if(status) status.textContent='☁️ Salvo na sua conta';
    return !!data.saved;
  }catch(error){
    const status=document.getElementById('riskCloudStatus');
    if(status) status.textContent='⚠️ Salvo localmente; sincronização pendente';
    if(showStatus) console.warn('Resolvei risk cloud save:',error);
    return false;
  }
}

function riskCloudScheduleSave(){
  const user=riskLoggedInUser();
  if(!user) return;
  clearTimeout(resolveiRiskCloudSaveTimer);
  resolveiRiskCloudSaveTimer=setTimeout(()=>riskCloudPut(false),250);
}

async function riskHydrateFromCloud(){
  const user=riskLoggedInUser();
  if(!user || resolveiRiskHydratingUid===user.uid) return;
  resolveiRiskHydratingUid=user.uid;
  const status=document.getElementById('riskCloudStatus');
  if(status) status.textContent='☁️ Sincronizando…';
  try{
    const data=await riskCloudGet();
    const localOwner=localStorage.getItem(RISK_STORAGE_KEY+'_owner');
    if(data.exists && data.state && typeof data.state==='object'){
      resolveiRiskState={
        config:{...riskDefaults().config,...(data.state.config||{})},
        session:{...riskDefaults().session,...(data.state.session||{})},
        history:Array.isArray(data.state.history)?data.state.history.slice(-80):[]
      };
      localStorage.setItem(RISK_STORAGE_KEY,JSON.stringify(resolveiRiskState));
      localStorage.setItem(RISK_STORAGE_KEY+'_owner',user.uid);
    }else if(!localOwner || localOwner===user.uid){
      localStorage.setItem(RISK_STORAGE_KEY+'_owner',user.uid);
      await riskCloudPut(true);
    }else{
      resolveiRiskState=riskDefaults();
      localStorage.setItem(RISK_STORAGE_KEY,JSON.stringify(resolveiRiskState));
      localStorage.setItem(RISK_STORAGE_KEY+'_owner',user.uid);
      await riskCloudPut(true);
    }
  }catch(error){
    if(status) status.textContent='⚠️ Não foi possível sincronizar; usando cópia local';
    console.warn('Resolvei risk cloud hydrate:',error);
  }finally{
    riskHydratingDone();
  }
}

function riskHydratingDone(){
  riskRender();
  const status=document.getElementById('riskCloudStatus');
  if(status && riskLoggedInUser() && resolveiRiskCloudUid===riskLoggedInUser().uid) status.textContent='☁️ Sincronizado com sua conta';
}

function riskConfigFromDOM(){
  const initial = Math.max(0.01, riskRead('riskInitialCapital') || 500);
  const entryPct = Math.min(50, Math.max(0.001, riskRead('riskEntryPct') || 0.5));
  const payout = Math.min(100, Math.max(0.01, riskRead('riskPayout') || 85));
  const chances = Math.min(30, Math.max(1, Math.round(riskRead('riskChances') || 7)));
  const goal = Math.max(initial, riskRead('riskGoal') || initial);
  const winRate = Math.min(100, Math.max(0, riskRead('riskWinRate') || 80));
  const maxExposurePct = Math.min(100, Math.max(0.1, riskRead('riskMaxExposurePct') || 20));
  return {initialCapital:initial,entryPct,payout,chances,goal,winRate,maxExposurePct};
}

function riskMakeSection(baseCapital, cfg){
  const target = baseCapital * (1 + (cfg.entryPct/100) * (cfg.payout/100));
  const rows = [];
  let accumulated = 0;
  for(let i=1;i<=cfg.chances;i++){
    let stake;
    if(i === 1) stake = baseCapital * (cfg.entryPct/100);
    else stake = (target - (baseCapital - accumulated)) / (cfg.payout/100);
    stake = Math.max(0, stake);
    const capitalLoss = baseCapital - accumulated - stake;
    const capitalWin = baseCapital - accumulated + stake * (cfg.payout/100);
    accumulated += stake;
    rows.push({
      chance:i,
      stake,
      accumulatedExposure:accumulated,
      capitalWin,
      capitalLoss,
      profitOnWin:stake*(cfg.payout/100),
      stakePct:baseCapital ? stake/baseCapital*100 : 0,
      exposurePct:baseCapital ? accumulated/baseCapital*100 : 0
    });
  }
  return {
    baseCapital,
    target,
    growth: target-baseCapital,
    rows,
    totalExposure:accumulated,
    remainingAfterAllLosses:baseCapital-accumulated,
    maxDrawdownPct:baseCapital ? accumulated/baseCapital*100 : 0
  };
}

function riskPlan(){
  const cfg=resolveiRiskState.config;
  const sections=[];
  let capital=Math.max(0.01,cfg.initialCapital);
  let guard=0;
  while(capital < cfg.goal && guard < 2000){
    const s=riskMakeSection(capital,cfg);
    sections.push(s);
    capital=s.target;
    guard++;
  }
  return {cfg,sections,goalReached:capital>=cfg.goal,goalCapital:capital,sectionsNeeded:sections.length};
}

function riskCurrentSection(){
  const cfg=resolveiRiskState.config;
  return riskMakeSection(Math.max(0.01,resolveiRiskState.session.baseCapital),cfg);
}

function riskCurrentRow(){
  const s=riskCurrentSection();
  return s.rows[Math.min(Math.max(1,resolveiRiskState.session.chance),s.rows.length)-1];
}

function riskSyncSessionToConfig(cfg, keepProgress=false){
  const old=resolveiRiskState.session;
  resolveiRiskState.config=cfg;
  if(!keepProgress){
    resolveiRiskState.session={
      capital:cfg.initialCapital,
      section:1,
      chance:1,
      baseCapital:cfg.initialCapital,
      accumulatedLoss:0,
      status:'active'
    };
    resolveiRiskState.history=[];
    riskSave();
    return;
  }
  const invalidBase = !Number.isFinite(old.baseCapital) || old.baseCapital<=0;
  if(invalidBase || Math.abs(old.baseCapital-cfg.initialCapital) < 1e-9 && old.section===1 && old.chance===1){
    old.baseCapital=cfg.initialCapital;
    old.capital=cfg.initialCapital;
  }
  old.chance=Math.min(Math.max(1,Math.round(old.chance||1)),cfg.chances);
  old.status=old.status==='busted'?'busted':'active';
  riskSave();
}

function riskFormatDate(){
  return new Date().toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}

function riskRegister(result){
  const state=resolveiRiskState;
  const cfg=state.config;
  if(state.session.status!=='active') return;
  const section=riskCurrentSection();
  const row=section.rows[state.session.chance-1];
  if(!row) return;
  const before=state.session.capital;
  let after;
  if(result==='win'){
    after=row.capitalWin;
    state.history.push({
      at:riskFormatDate(),section:state.session.section,chance:row.chance,result:'WIN',
      stake:row.stake,before,after
    });
    state.session={
      capital:after,
      section:state.session.section+1,
      chance:1,
      baseCapital:after,
      accumulatedLoss:0,
      status:'active'
    };
  }else{
    after=Math.max(0,before-row.stake);
    state.history.push({
      at:riskFormatDate(),section:state.session.section,chance:row.chance,result:'LOSS',
      stake:row.stake,before,after
    });
    const last=state.session.chance>=cfg.chances;
    state.session.capital=after;
    state.session.accumulatedLoss += row.stake;
    if(last){
      state.session.status='busted';
    }else{
      state.session.chance++;
    }
  }
  state.history=state.history.slice(-80);
  riskSave();
  riskCloudScheduleSave();
  riskRender();
}

function riskResetAll(){
  resolveiRiskState=riskDefaults();
  riskSave();
  riskCloudScheduleSave();
  riskRender();
}

function riskRestartFromRemaining(){
  const c=Math.max(0,resolveiRiskState.session.capital);
  const min=0.01;
  if(c<min){ riskResetAll(); return; }
  resolveiRiskState.session={
    capital:c,section:resolveiRiskState.session.section+1,chance:1,
    baseCapital:c,accumulatedLoss:0,status:'active'
  };
  riskSave();
  riskCloudScheduleSave();
  riskRender();
}

function riskGoalText(plan){
  if(plan.cfg.goal<=plan.cfg.initialCapital+1e-9) return 'Meta já atingida pelo capital inicial.';
  if(!plan.goalReached) return 'Meta não alcançada com os parâmetros atuais.';
  return `${riskNum(plan.sectionsNeeded)} seções completas para chegar a ${riskMoney(plan.goalCapital)} ou mais.`;
}

function riskSectionRowsHtml(section,cfg,highlightChance){
  return section.rows.map(r => {
    const cls=r.chance===highlightChance ? ' risk-row-current' : '';
    return `<div class="risk-entry-row${cls}">
      <div class="risk-chance"><strong>${r.chance}</strong><span>${r.chance===1?'Base':'Recuperação'}</span></div>
      <div><span>Entrada</span><strong>${riskMoney(r.stake)}</strong></div>
      <div><span>Exposição</span><strong>${riskPct(r.exposurePct)}</strong></div>
      <div><span>Capital se WIN</span><strong>${riskMoney(r.capitalWin)}</strong></div>
      <div><span>Capital se LOSS</span><strong>${riskMoney(r.capitalLoss)}</strong></div>
    </div>`;
  }).join('');
}

function riskEvolutionRowsHtml(plan){
  const maxRows=14;
  let arr=plan.sections.slice(0,maxRows);
  const currentSec=resolveiRiskState.session.section;
  if(currentSec>maxRows){
    const current=plan.sections[currentSec-1];
    if(current){
      arr=arr.concat([null,current]);
    }
  }
  return arr.map((s)=>s ? `<div class="risk-section-row">
    <div><strong>Seção ${plan.sections.indexOf(s)+1}</strong>${s===plan.sections[currentSec-1]?'<span class="risk-tag">Atual</span>':''}</div>
    <div>${riskMoney(s.baseCapital)}</div>
    <div>+${riskMoney(s.growth)}</div>
    <div>${riskMoney(s.target)}</div>
    <div>${riskMoney(s.totalExposure)}</div>
  </div>` : '<div class="risk-section-more">…</div>').join('');
}

function riskProjectionSvg(plan){
  const vals=plan.sections.slice(0,24).map(s=>s.target);
  const start=plan.cfg.initialCapital;
  const max=Math.max(...vals,start);
  const width=700,height=170,pad=18;
  const points=vals.map((v,i)=>{
    const x=pad + (vals.length===1?0:(i/(vals.length-1))*(width-pad*2));
    const y=height-pad - ((v-start)/Math.max(1,max-start))*(height-pad*2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg class="risk-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Projeção do capital por seção">
    <line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" stroke="var(--line)"/>
    <polyline fill="none" stroke="var(--accent)" stroke-width="3" points="${points}"/>
    <text x="${pad}" y="${height-2}" fill="var(--muted)">Início</text>
    <text x="${width-pad}" y="${height-2}" fill="var(--muted)" text-anchor="end">Seções</text>
  </svg>`;
}

function riskSummaryHtml(plan,current){
  const worst=current.remainingAfterAllLosses;
  const worstPct=current.maxDrawdownPct;
  const growthPct=plan.cfg.entryPct/100*(plan.cfg.payout/100)*100;
  const target=plan.sections[Math.max(0,resolveiRiskState.session.section-1)] || current;
  const status=resolveiRiskState.session.status;
  const pLossAll=Math.pow(Math.max(0,Math.min(1,1-plan.cfg.winRate/100)),plan.cfg.chances);
  const pAdvance=1-pLossAll;
  const exposureFlag=worstPct>plan.cfg.maxExposurePct;
  return `<div class="risk-kpis">
    <div class="risk-kpi"><span>Capital atual</span><strong>${riskMoney(resolveiRiskState.session.capital)}</strong><small>Seção ${resolveiRiskState.session.section} · chance ${status==='busted'?'encerrada':resolveiRiskState.session.chance}</small></div>
    <div class="risk-kpi"><span>Próximo alvo</span><strong>${riskMoney(current.target)}</strong><small>Lucro-alvo da seção: ${riskMoney(current.growth)}</small></div>
    <div class="risk-kpi"><span>Exposição em ${plan.cfg.chances} perdas</span><strong>${riskPct(worstPct)}</strong><small>Sobra: ${riskMoney(worst)}</small></div>
  </div>
  <div class="risk-alert ${exposureFlag?'risk-alert-high':'risk-alert-low'}">
    <strong>${exposureFlag?'⚠️ Acima do limite de exposição':'✓ Dentro do limite configurado'}</strong>
    <span>O plano pode expor até ${riskPct(worstPct)} do capital-base nesta seção. Seu limite de referência está em ${riskPct(plan.cfg.maxExposurePct)}.</span>
  </div>
  <div class="risk-mini-grid">
    <div><span>Crescimento por seção</span><strong>+${riskPct(growthPct)}</strong></div>
    <div><span>Chance estimada de avançar</span><strong>${riskPct(pAdvance*100)}</strong><small>Com taxa de acerto de ${riskPct(plan.cfg.winRate)}</small></div>
    <div><span>7 perdas consecutivas</span><strong>${riskPct(pLossAll*100)}</strong><small>Modelo probabilístico, não previsão</small></div>
  </div>
  <div class="risk-note"><strong>Como a planilha trabalha:</strong> a vitória em qualquer chance leva o capital da seção ao mesmo próximo alvo. As probabilidades acima são apenas aritmética baseada na taxa de acerto que você informou; elas não estimam desempenho futuro nem garantem resultados.</div>`;
}

function riskEvolutionUI(){
  const cfg=resolveiRiskState.config || riskDefaults().config;
  return `<div class="risk-tool-shell">
    <section class="risk-control-card card">
      <h2>⚙️ Configuração do plano</h2>
      <div class="notice"><strong>Modelo da sua planilha.</strong> Cada seção tem um número definido de chances. A primeira entrada é calculada sobre o capital da seção; as demais crescem para recuperar as perdas anteriores e ainda atingir o próximo alvo.</div>
      <div class="form-grid risk-form-grid">
        <div class="field"><label for="riskInitialCapital">Capital inicial</label><div class="input-wrap"><span class="prefix">R$</span><input id="riskInitialCapital" type="number" step="0.01" min="0.01" value="${cfg.initialCapital}"></div></div>
        <div class="field"><label for="riskEntryPct">Entrada-base</label><div class="input-wrap"><input id="riskEntryPct" type="number" step="0.01" min="0.001" max="50" value="${cfg.entryPct}"><span class="suffix">%</span></div></div>
        <div class="field"><label for="riskPayout">Payout / retorno líquido da vitória</label><div class="input-wrap"><input id="riskPayout" type="number" step="0.1" min="0.1" max="100" value="${cfg.payout}"><span class="suffix">%</span></div><small>85% significa lucro de R$ 0,85 para cada R$ 1,00 de entrada vencedora.</small></div>
        <div class="field"><label for="riskChances">Chances por seção</label><div class="input-wrap"><input id="riskChances" type="number" step="1" min="1" max="30" value="${cfg.chances}"></div><small>O padrão da sua planilha é 7.</small></div>
        <div class="field"><label for="riskWinRate">Taxa de acerto para simulação</label><div class="input-wrap"><input id="riskWinRate" type="number" step="0.1" min="0" max="100" value="${cfg.winRate}"><span class="suffix">%</span></div><small>Usada somente para calcular probabilidades matemáticas da seção.</small></div>
        <div class="field"><label for="riskMaxExposurePct">Limite de exposição de referência</label><div class="input-wrap"><input id="riskMaxExposurePct" type="number" step="1" min="0.1" max="100" value="${cfg.maxExposurePct}"><span class="suffix">%</span></div><small>Não altera as entradas; serve para sinalizar quando o modelo ultrapassa seu limite.</small></div>
        <div class="field full"><label for="riskGoal">Meta de patrimônio</label><div class="input-wrap"><span class="prefix">R$</span><input id="riskGoal" type="number" step="0.01" min="0.01" value="${cfg.goal}"></div></div>
      </div>
      <div class="actions">
        <button class="btn primary" id="riskApplyBtn" type="button">Recalcular plano</button>
        <button class="btn ghost" id="riskResetBtn" type="button">Zerar plano</button>
      </div>
      <div class="risk-formula">
        <strong>Fórmula central</strong>
        <span>Entrada 1 = capital × entrada-base</span>
        <span>Entrada seguinte = (alvo − capital restante após perdas) ÷ payout</span>
        <span>Alvo da seção = capital + lucro da entrada-base vencedora</span>
      </div>
    </section>

    <section class="risk-dashboard card" id="riskDashboard"></section>

    <section class="risk-section-card card">
      <div class="risk-section-head">
        <div><h2>🎯 Seção atual · ${resolveiRiskState.session.section}</h2><p>Chances calculadas para este ciclo. Registre o resultado real de cada entrada para acompanhar o capital.</p></div>
        <div class="risk-status-pill" id="riskStatusPill">${resolveiRiskState.session.status==='active'?'EM ANDAMENTO':'SEÇÃO ENCERRADA'}</div>
      </div>
      <div id="riskCurrentSection"></div>
      <div class="actions risk-actions">
        <button class="btn primary" id="riskWinBtn" type="button">✅ Registrar WIN</button>
        <button class="btn" id="riskLossBtn" type="button">❌ Registrar LOSS</button>
        <button class="btn ghost" id="riskRestartBtn" type="button">↻ Recomeçar com capital restante</button>
      </div>
      <div class="risk-note">O histórico funciona no navegador e, quando você está logado, o mesmo progresso é sincronizado com sua conta do Resolvei.</div>
      <div class="notice" id="riskCloudStatus">💾 Aguardando sincronização</div>
    </section>

    <section class="risk-section-card card">
      <div class="risk-section-head"><div><h2>📈 Evolução projetada do patrimônio</h2><p>O gráfico usa apenas os alvos sucessivos do modelo.</p></div></div>
      <div id="riskProjection"></div>
      <div class="risk-evolution-table">
        <div class="risk-section-row risk-section-header"><div>Seção</div><div>Capital-base</div><div>Lucro alvo</div><div>Próximo capital</div><div>Exposição máxima</div></div>
        <div id="riskEvolutionRows"></div>
      </div>
    </section>

    <section class="risk-section-card card">
      <div class="risk-section-head"><div><h2>🧾 Histórico de entradas</h2><p>Últimos registros deste plano neste navegador.</p></div><button class="btn ghost" id="riskClearHistoryBtn" type="button">Limpar histórico</button></div>
      <div id="riskHistory"></div>
      <div class="actions"><button class="btn" id="riskExportBtn" type="button">⬇ Exportar CSV</button></div>
    </section>
  </div>`;
}

function riskRender(){
  const dash=document.getElementById('riskDashboard');
  if(!dash) return;
  const plan=riskPlan();
  const current=riskCurrentSection();
  const currentRow=riskCurrentRow();
  dash.innerHTML=riskSummaryHtml(plan,current);

  const sectionBox=document.getElementById('riskCurrentSection');
  const pill=document.getElementById('riskStatusPill');
  if(pill) pill.textContent=resolveiRiskState.session.status==='active'?'EM ANDAMENTO':'SEÇÃO ENCERRADA';
  if(sectionBox){
    const status=resolveiRiskState.session.status;
    const subtitle=status==='active'
      ? `Chance ${resolveiRiskState.session.chance} de ${plan.cfg.chances}. Entrada planejada: <strong>${riskMoney(currentRow.stake)}</strong>.`
      : `As ${plan.cfg.chances} chances desta seção foram perdidas. Capital restante: <strong>${riskMoney(resolveiRiskState.session.capital)}</strong>.`;
    sectionBox.innerHTML=`<div class="risk-live-box">
      <div><span class="result-label">Capital-base da seção</span><strong>${riskMoney(current.baseCapital)}</strong></div>
      <div><span class="result-label">Capital atual</span><strong>${riskMoney(resolveiRiskState.session.capital)}</strong></div>
      <div><span class="result-label">Próximo alvo</span><strong>${riskMoney(current.target)}</strong></div>
      <div><span class="result-label">Situação</span><strong>${subtitle}</strong></div>
    </div>
    <div class="risk-entry-list">${riskSectionRowsHtml(current,plan.cfg,resolveiRiskState.session.status==='active'?resolveiRiskState.session.chance:0)}</div>`;
  }

  const projection=document.getElementById('riskProjection');
  if(projection) projection.innerHTML=riskProjectionSvg(plan)+`<div class="notice">${riskGoalText(plan)}</div>`;
  const rows=document.getElementById('riskEvolutionRows');
  if(rows) rows.innerHTML=riskEvolutionRowsHtml(plan);

  const history=document.getElementById('riskHistory');
  if(history){
    const items=resolveiRiskState.history.slice().reverse();
    history.innerHTML=items.length
      ? items.map(x=>`<div class="risk-history-row"><div><strong>${x.result==='WIN'?'✅ WIN':'❌ LOSS'}</strong><span>${x.at}</span></div><div>Seção ${x.section} · chance ${x.chance}</div><div>${riskMoney(x.stake)}</div><div>${riskMoney(x.after)}</div></div>`).join('')
      : '<div class="empty">Nenhuma entrada registrada ainda.</div>';
  }

  const active=statusActive();
  const winBtn=document.getElementById('riskWinBtn'), lossBtn=document.getElementById('riskLossBtn');
  if(winBtn) winBtn.disabled=!active;
  if(lossBtn) lossBtn.disabled=!active;
  const restart=document.getElementById('riskRestartBtn');
  if(restart) restart.disabled=resolveiRiskState.session.capital<=0;
}

function statusActive(){return resolveiRiskState.session.status==='active';}

function riskApplyConfig(){
  const cfg=riskConfigFromDOM();
  riskSyncSessionToConfig(cfg,false);
  riskRender();
}

function riskClearHistory(){
  resolveiRiskState.history=[];
  riskSave();
  riskCloudScheduleSave();
  riskRender();
}

function riskExportCsv(){
  const rows=[['Data','Seção','Chance','Resultado','Entrada','Capital antes','Capital depois']];
  resolveiRiskState.history.forEach(x=>rows.push([x.at,x.section,x.chance,x.result,x.stake,x.before,x.after]));
  const csv=rows.map(r=>r.map(v=>`"${String(v).replace(/"/g,'""')}"`).join(';')).join('\n');
  const blob=new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='resolvei-gerenciamento-risco.csv';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),500);
}

function bindRiskEvolutionTool(){
  const apply=document.getElementById('riskApplyBtn');
  if(apply) apply.addEventListener('click',riskApplyConfig);
  const reset=document.getElementById('riskResetBtn');
  if(reset) reset.addEventListener('click',riskResetAll);
  const win=document.getElementById('riskWinBtn');
  if(win) win.addEventListener('click',()=>riskRegister('win'));
  const loss=document.getElementById('riskLossBtn');
  if(loss) loss.addEventListener('click',()=>riskRegister('loss'));
  const restart=document.getElementById('riskRestartBtn');
  if(restart) restart.addEventListener('click',riskRestartFromRemaining);
  const clear=document.getElementById('riskClearHistoryBtn');
  if(clear) clear.addEventListener('click',riskClearHistory);
  const exportBtn=document.getElementById('riskExportBtn');
  if(exportBtn) exportBtn.addEventListener('click',riskExportCsv);
  riskRender();
  riskHydrateFromCloud();
}
