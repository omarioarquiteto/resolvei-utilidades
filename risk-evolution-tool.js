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

function riskNormalizeConfig(raw={}){
  const config={...riskDefaults().config,...(raw||{})};
  delete config.winRate;
  delete config.maxExposurePct;
  return config;
}

function riskLoad(){
  try{
    const raw = JSON.parse(localStorage.getItem(RISK_STORAGE_KEY) || 'null');
    if(!raw) return riskDefaults();
    return {
      config: riskNormalizeConfig(raw.config||{}),
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

async function riskFillConfigInputs(){
  const cfg=resolveiRiskState.config || riskDefaults().config;
  const values={
    riskInitialCapital:cfg.initialCapital,
    riskEntryPct:cfg.entryPct,
    riskPayout:cfg.payout,
    riskChances:cfg.chances,
    riskGoal:cfg.goal
  };
  Object.entries(values).forEach(([id,value])=>{
    const el=document.getElementById(id);
    if(el && value!==undefined && value!==null) el.value=value;
  });
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
        config:riskNormalizeConfig(data.state.config||{}),
        session:{...riskDefaults().session,...(data.state.session||{})},
        history:Array.isArray(data.state.history)?data.state.history.slice(-80):[]
      };
      localStorage.setItem(RISK_STORAGE_KEY,JSON.stringify(resolveiRiskState));
      localStorage.setItem(RISK_STORAGE_KEY+'_owner',user.uid);
      riskFillConfigInputs();
    }else if(!localOwner || localOwner===user.uid){
      localStorage.setItem(RISK_STORAGE_KEY+'_owner',user.uid);
      await riskCloudPut(true);
    }else{
      resolveiRiskState=riskDefaults();
      localStorage.setItem(RISK_STORAGE_KEY,JSON.stringify(resolveiRiskState));
      localStorage.setItem(RISK_STORAGE_KEY+'_owner',user.uid);
      riskFillConfigInputs();
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
  const entryPct = Math.min(100, Math.max(1e-120, riskRead('riskEntryPct') || 0.5));
  const payout = Math.min(100, Math.max(0.01, riskRead('riskPayout') || 85));
  const chances = Math.min(30, Math.max(1, Math.round(riskRead('riskChances') || 7)));
  const goal = Math.max(initial, riskRead('riskGoal') || initial);
  return {initialCapital:initial,entryPct,payout,chances,goal};
}

function riskEntryPctForChances(chances,payoutPct){
  const count=Math.min(30,Math.max(1,Math.round(Number(chances)||1)));
  const payout=Math.min(1,Math.max(0.0001,(Number(payoutPct)||85)/100));
  let accumulated=1;
  for(let i=2;i<=count;i++) accumulated += 1 + accumulated/payout;
  return 100/accumulated;
}

function riskChancesForEntryPct(entryPct,payoutPct){
  const basePct=Math.min(100,Math.max(1e-120,Number(entryPct)||0.5));
  const base=basePct/100;
  const payout=Math.min(1,Math.max(0.0001,(Number(payoutPct)||85)/100));
  let accumulated=0;
  let count=0;
  for(let i=1;i<=30;i++){
    const stake=i===1?base:(base+accumulated/payout);
    const next=accumulated+Math.max(0,stake);
    if(next>1+1e-9) break;
    accumulated=next;
    count=i;
    if(accumulated>=1-1e-9) break;
  }
  return Math.max(1,count);
}

function riskFormatInputNumber(value){
  return Number.isFinite(value)?Number(value.toPrecision(12)).toString():'';
}

let riskLastEditedField='entry';

function riskReconcileInputs(source){
  const entry=document.getElementById('riskEntryPct');
  const chances=document.getElementById('riskChances');
  const payoutEl=document.getElementById('riskPayout');
  if(!entry||!chances||!payoutEl) return false;
  const payout=Number(payoutEl.value);
  if(!Number.isFinite(payout)||payout<=0) return false;

  if(source==='entry'){
    const value=Number(entry.value);
    if(!Number.isFinite(value)||value<=0) return false;
    const normalized=Math.min(100,Math.max(1e-120,value));
    entry.value=riskFormatInputNumber(normalized);
    chances.value=String(riskChancesForEntryPct(normalized,payout));
    riskLastEditedField='entry';
  }else if(source==='chances'){
    const value=Number(chances.value);
    if(!Number.isFinite(value)||value<=0) return false;
    const normalized=Math.min(30,Math.max(1,Math.round(value)));
    chances.value=String(normalized);
    entry.value=riskFormatInputNumber(riskEntryPctForChances(normalized,payout));
    riskLastEditedField='chances';
  }else if(riskLastEditedField==='entry'){
    const value=Number(entry.value);
    if(!Number.isFinite(value)||value<=0) return false;
    chances.value=String(riskChancesForEntryPct(value,payout));
  }else{
    const value=Number(chances.value);
    if(!Number.isFinite(value)||value<=0) return false;
    entry.value=riskFormatInputNumber(riskEntryPctForChances(value,payout));
  }
  return true;
}

function riskMakeSection(baseCapital, cfg){
  const target = baseCapital * (1 + (cfg.entryPct/100) * (cfg.payout/100));
  const rows = [];
  let accumulated = 0;
  for(let i=1;i<=cfg.chances;i++){
    let stake;
    if(i === 1) stake = baseCapital * (cfg.entryPct/100);
    else stake = baseCapital * (cfg.entryPct/100) + accumulated / (cfg.payout/100);
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
  riskFillConfigInputs();
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

function riskActualEvolutionSvg(){
  const history=Array.isArray(resolveiRiskState.history)?resolveiRiskState.history.slice(-30):[];
  if(!history.length){
    return `<div class="risk-chart-empty">
      <div class="risk-chart-empty-icon">↗</div>
      <strong>Seu gráfico começa aqui</strong>
      <span>Registre o primeiro WIN ou LOSS para visualizar a evolução real do capital.</span>
    </div>`;
  }
  const series=[
    {value:Number(resolveiRiskState.config.initialCapital)||0,result:'START',at:'Capital inicial'},
    ...history.map(x=>({value:Number(x.after)||0,result:x.result,at:x.at,section:x.section,chance:x.chance,stake:Number(x.stake)||0}))
  ];
  const values=series.map(x=>x.value);
  let min=Math.min(...values),max=Math.max(...values);
  if(Math.abs(max-min)<0.01){min=Math.max(0,min-1);max=max+1;}
  else{
    const pad=Math.max(1,(max-min)*0.12);
    min=Math.max(0,min-pad);max+=pad;
  }
  const width=760,height=260,left=48,right=22,top=20,bottom=42;
  const innerW=width-left-right,innerH=height-top-bottom;
  const xAt=i=>left+(series.length===1?innerW/2:(i/(series.length-1))*innerW);
  const yAt=v=>top+((max-v)/(max-min))*innerH;
  const grid=[0,1,2,3,4].map(i=>{
    const y=top+(i/4)*innerH;
    const value=max-((max-min)*(i/4));
    return `<line x1="${left}" y1="${y.toFixed(1)}" x2="${width-right}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-dasharray="3 5"/>
      <text x="${left-8}" y="${(y+4).toFixed(1)}" fill="var(--muted)" text-anchor="end" font-size="10">${riskMoney(value)}</text>`;
  }).join('');
  const segments=series.slice(1).map((item,i)=>{
    const a=series[i],b=item;
    const stroke=item.result==='WIN'?'var(--success)':'var(--danger)';
    return `<line x1="${xAt(i).toFixed(1)}" y1="${yAt(a.value).toFixed(1)}" x2="${xAt(i+1).toFixed(1)}" y2="${yAt(b.value).toFixed(1)}" stroke="${stroke}" stroke-width="4" stroke-linecap="round"/>`;
  }).join('');
  const points=series.map((item,i)=>{
    const color=item.result==='WIN'?'var(--success)':item.result==='LOSS'?'var(--danger)':'var(--accent)';
    const label=item.result==='START'?'Capital inicial':`${item.result} · ${item.at}`;
    return `<circle cx="${xAt(i).toFixed(1)}" cy="${yAt(item.value).toFixed(1)}" r="${i===series.length-1?6:4.5}" fill="${color}" stroke="var(--surface)" stroke-width="2"><title>${label} — ${riskMoney(item.value)}</title></circle>`;
  }).join('');
  const labels=series.map((item,i)=>{
    if(!(i===0 || i===series.length-1 || i%5===0)) return '';
    const textLabel=i===0?'Início':`#${i}`;
    return `<text x="${xAt(i).toFixed(1)}" y="${height-14}" fill="var(--muted)" text-anchor="${i===0?'start':i===series.length-1?'end':'middle'}" font-size="10">${textLabel}</text>`;
  }).join('');
  const last=series[series.length-1];
  const delta=last.value-series[0].value;
  return `<svg class="risk-chart risk-chart-real" viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolução real do capital, com ganhos em verde e perdas em vermelho">
    ${grid}
    <line x1="${left}" y1="${yAt(series[0].value).toFixed(1)}" x2="${width-right}" y2="${yAt(series[0].value).toFixed(1)}" stroke="var(--muted)" stroke-dasharray="6 6" opacity=".45"/>
    ${segments}${points}${labels}
  </svg>`;
}

function riskProjectionSvg(plan){
  const vals=plan.sections.slice(0,24).map(s=>s.target);
  const start=plan.cfg.initialCapital;
  const max=Math.max(...vals,start);
  const width=700,height=150,pad=18;
  const points=vals.map((v,i)=>{
    const x=pad + (vals.length===1?0:(i/(vals.length-1))*(width-pad*2));
    const y=height-pad - ((v-start)/Math.max(1,max-start))*(height-pad*2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg class="risk-chart risk-chart-projection" viewBox="0 0 ${width} ${height}" role="img" aria-label="Projeção do capital por seção">
    <line x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}" stroke="var(--line)"/>
    <polyline fill="none" stroke="var(--accent)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${points}"/>
    <text x="${pad}" y="${height-2}" fill="var(--muted)">Início</text>
    <text x="${width-pad}" y="${height-2}" fill="var(--muted)" text-anchor="end">Seções</text>
  </svg>`;
}

function riskSummaryHtml(plan,current,currentRow){
  const remaining=current.remainingAfterAllLosses;
  const exposurePct=current.maxDrawdownPct;
  const growthPct=plan.cfg.entryPct/100*(plan.cfg.payout/100)*100;
  const status=resolveiRiskState.session.status;
  const history=resolveiRiskState.history||[];
  const last=history.length?history[history.length-1]:null;
  const latestLabel=last?`${last.result==='WIN'?'✅ WIN':'❌ LOSS'} registrado em ${last.at} · capital ${riskMoney(last.after)}`:'Nenhum resultado registrado ainda.';
  return `<div class="risk-kpis">
    <div class="risk-kpi risk-kpi-primary"><span>Capital atual</span><strong>${riskMoney(resolveiRiskState.session.capital)}</strong><small>Seção ${resolveiRiskState.session.section} · chance ${status==='busted'?'encerrada':resolveiRiskState.session.chance}</small></div>
    <div class="risk-kpi"><span>Entrada agora</span><strong>${status==='active'&&currentRow?riskMoney(currentRow.stake):'—'}</strong><small>${status==='active'?(`Chance ${resolveiRiskState.session.chance} de ${plan.cfg.chances}`):'Seção encerrada'}</small></div>
    <div class="risk-kpi"><span>Próximo alvo</span><strong>${riskMoney(current.target)}</strong><small>Lucro-alvo: ${riskMoney(current.growth)}</small></div>
    <div class="risk-kpi"><span>Exposição da seção</span><strong>${riskPct(exposurePct)}</strong><small>Saldo após ${plan.cfg.chances} LOSS: ${riskMoney(remaining)}</small></div>
  </div>
  <div class="risk-latest-result"><span>Último movimento</span><strong>${latestLabel}</strong></div>
  <div class="risk-mini-grid">
    <div><span>Crescimento por seção</span><strong>+${riskPct(growthPct)}</strong></div>
    <div><span>Entrada-base</span><strong>${riskPct(plan.cfg.entryPct)}</strong></div>
    <div><span>Payout considerado</span><strong>${riskPct(plan.cfg.payout)}</strong></div>
  </div>
  <div class="risk-note"><strong>Calculadora de banca:</strong> ao alterar a entrada-base, a ferramenta calcula quantas entradas completas cabem no capital atual. Ao alterar as chances por seção, calcula a entrada-base para que a última perda utilize o saldo disponível. Não há estimativa de probabilidade ou simulação de resultados.</div>`;
}

function riskEvolutionRowsHtml(plan){
  const maxRows=14;
  let arr=plan.sections.slice(0,maxRows);
  const currentSec=resolveiRiskState.session.section;
  if(currentSec>maxRows){
    const current=plan.sections[currentSec-1];
    if(current) arr=arr.concat([null,current]);
  }
  return arr.map((s)=>s ? `<div class="risk-section-row">
    <div><strong>Seção ${plan.sections.indexOf(s)+1}</strong>${s===plan.sections[currentSec-1]?'<span class="risk-tag">Atual</span>':''}</div>
    <div>${riskMoney(s.baseCapital)}</div>
    <div>+${riskMoney(s.growth)}</div>
    <div>${riskMoney(s.target)}</div>
    <div>${riskMoney(s.totalExposure)}</div>
  </div>` : '<div class="risk-section-more">…</div>').join('');
}

function riskEvolutionUI(){
  const cfg=resolveiRiskState.config || riskDefaults().config;
  return [
    "<div class='risk-tool-shell'>",
    "<section class='risk-hero-banner'>",
      "<div class='risk-hero-copy'><span class='risk-hero-kicker'>GESTÃO INTELIGENTE DE BANCA</span><h1>Gerenciamento de risco <em>e evolução de capital</em></h1><p>Visualize sua estratégia, registre cada resultado e acompanhe a evolução do seu capital com clareza.</p></div>",
      "<div class='risk-hero-art' aria-hidden='true'><div class='risk-hero-shield'>↗</div><div class='risk-hero-bars'><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><div class='risk-hero-arrow'>↗</div></div>",
    "</section>",
    "<div class='risk-reference-grid'>",
      "<div class='risk-primary-column'>",
        "<section class='risk-overview-card card'><div class='risk-section-head'><div><span class='risk-eyebrow'>SEU PAINEL</span><h2>Sua estratégia em números</h2><p>Indicadores atualizados a cada resultado registrado.</p></div><div class='risk-status-pill' id='riskStatusPill'>" + (resolveiRiskState.session.status==='active'?'EM ANDAMENTO':'SEÇÃO ENCERRADA') + "</div></div><div id='riskDashboard'></div><div id='riskCurrentSection'></div></section>",
        "<section class='risk-chart-card card'><div class='risk-section-head'><div><span class='risk-eyebrow'>DESEMPENHO REAL</span><h2>Evolução do seu capital</h2><p>Veja como seu saldo se comporta a cada WIN ou LOSS.</p></div><div class='risk-chart-legend'><span><i class='risk-dot risk-dot-win'></i> WIN</span><span><i class='risk-dot risk-dot-loss'></i> LOSS</span></div></div><div id='riskActualEvolution'></div></section>",
        "<section class='risk-control-card card'><div class='risk-control-heading'><div><span class='risk-eyebrow'>REGISTRO DE OPERAÇÕES</span><h2>Qual foi o resultado da sua entrada?</h2><p>Registre somente o resultado real da operação para atualizar seu histórico.</p></div><span class='risk-control-live'>● Ao vivo</span></div><div class='actions risk-actions'><button class='btn risk-result-btn risk-win-btn' id='riskWinBtn' type='button'><span>↗</span> WIN</button><button class='btn risk-result-btn risk-loss-btn' id='riskLossBtn' type='button'><span>↘</span> LOSS</button></div><div class='risk-control-bottom'><button class='btn ghost' id='riskRestartBtn' type='button'>↻ Recomeçar com capital restante</button><div class='notice risk-cloud-status' id='riskCloudStatus'>💾 Aguardando sincronização</div></div></section>",
      "</div>",
      "<aside class='risk-aside-column'>",
        "<details class='risk-config-card card'><summary><div><strong>⚙ Configuração do plano</strong><small>Capital, entrada-base, payout, chances e meta</small></div><span class='risk-summary-action'>Editar</span></summary><div class='risk-config-content'><div class='notice'><strong>Calculadora da sua planilha.</strong> A primeira entrada usa a entrada-base sobre o capital atual; as seguintes consideram as perdas anteriores e buscam o próximo alvo.</div><div class='form-grid risk-form-grid'>",
          "<div class='field'><label for='riskInitialCapital'>Capital inicial</label><div class='input-wrap'><span class='prefix'>R$</span><input id='riskInitialCapital' type='number' step='0.01' min='0.01' value='" + cfg.initialCapital + "'></div></div>",
          "<div class='field'><label for='riskEntryPct'>Entrada-base</label><div class='input-wrap'><input id='riskEntryPct' type='number' step='any' min='0' max='100' value='" + cfg.entryPct + "'><span class='suffix'>%</span></div><small>Ao alterar, a quantidade de chances é recalculada para caber no capital atual.</small></div>",
          "<div class='field'><label for='riskPayout'>Payout / retorno líquido</label><div class='input-wrap'><input id='riskPayout' type='number' step='0.1' min='0.1' max='100' value='" + cfg.payout + "'><span class='suffix'>%</span></div><small>85% = lucro de R$ 0,85 por R$ 1,00 em uma vitória.</small></div>",
          "<div class='field'><label for='riskChances'>Chances por seção</label><div class='input-wrap'><input id='riskChances' type='number' step='1' min='1' max='30' value='" + cfg.chances + "'></div><small>A entrada-base é recalculada para utilizar o capital disponível.</small></div>",
          "<div class='field full'><label for='riskGoal'>Meta de patrimônio</label><div class='input-wrap'><span class='prefix'>R$</span><input id='riskGoal' type='number' step='0.01' min='0.01' value='" + cfg.goal + "'></div></div>",
        "</div><div class='actions'><button class='btn primary' id='riskApplyBtn' type='button'>Aplicar configurações</button><button class='btn ghost' id='riskResetBtn' type='button'>Zerar plano</button></div><div class='risk-formula'><strong>Fórmula central</strong><span>Entrada 1 = capital atual × entrada-base</span><span>Entrada seguinte = (alvo − capital restante após perdas) ÷ payout</span><span>Ao definir as chances, a entrada-base ajusta a exposição total ao capital disponível</span></div></div></details>",
        "<section class='risk-tip-card'><span class='risk-tip-icon'>✦</span><div><small>DICA DE OURO</small><h3>Consistência antes da pressa.</h3><p>Respeite os limites da sua estratégia e use o histórico para avaliar seu desempenho, não para prever o próximo resultado.</p></div></section>",
        "<section class='risk-ready-card'><div class='risk-ready-rocket'>↗</div><h3>Pronto para acompanhar?</h3><p>Registre cada operação e veja os indicadores se atualizarem em tempo real.</p><button type='button' id='riskReadyStartBtn'>Começar agora <span>→</span></button></section>",
        "<section class='risk-chart-card risk-projection-card card'><div class='risk-section-head'><div><span class='risk-eyebrow'>PROJEÇÃO DO PLANO</span><h2>Próximos alvos</h2><p>Valores calculados conforme as configurações atuais.</p></div></div><div id='riskProjection'></div></section>",
      "</aside>",
    "</div>",
    "<div class='risk-bottom-grid'>",
      "<details class='risk-extra-card card'><summary><div><strong>📋 Plano completo das seções</strong><small>Capital-base, lucro alvo e exposição de cada seção</small></div><span>Mostrar</span></summary><div class='risk-evolution-table'><div class='risk-section-row risk-section-header'><div>Seção</div><div>Capital-base</div><div>Lucro alvo</div><div>Próximo capital</div><div>Exposição máxima</div></div><div id='riskEvolutionRows'></div></div><div class='risk-note' id='riskGoalMessage'></div></details>",
      "<details class='risk-extra-card risk-history-card card' open><summary><div><strong>🧾 Histórico e resultado</strong><small>Seus registros mais recentes</small></div><span>Ver histórico completo →</span></summary><div class='risk-history-toolbar'><button class='btn ghost' id='riskClearHistoryBtn' type='button'>Limpar histórico</button></div><div id='riskHistory'></div><div class='actions'><button class='btn' id='riskExportBtn' type='button'>⬇ Exportar CSV</button></div></details>",
    "</div>",
    "</div>"
  ].join("");
}
function riskRender(){
  const dash=document.getElementById('riskDashboard');
  if(!dash) return;
  const plan=riskPlan();
  const current=riskCurrentSection();
  const currentRow=riskCurrentRow();
  dash.innerHTML=riskSummaryHtml(plan,current,currentRow);

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
      <div><span class="result-label">Lucro alvo da seção</span><strong>+${riskMoney(current.growth)}</strong></div>
      <div><span class="result-label">Exposição até aqui</span><strong>${riskPct(resolveiRiskState.session.baseCapital ? (resolveiRiskState.session.accumulatedLoss / resolveiRiskState.session.baseCapital * 100) : 0)}</strong></div>
      <div><span class="result-label">Situação</span><strong>${subtitle}</strong></div>
    </div>
    <details class="risk-section-plan">
      <summary><strong>Ver as ${plan.cfg.chances} entradas desta seção</strong><span>Mostrar plano</span></summary>
      <div class="risk-entry-list">${riskSectionRowsHtml(current,plan.cfg,resolveiRiskState.session.status==='active'?resolveiRiskState.session.chance:0)}</div>
    </details>`;
  }

  const actual=document.getElementById('riskActualEvolution');
  if(actual) actual.innerHTML=riskActualEvolutionSvg();

  const projection=document.getElementById('riskProjection');
  if(projection) projection.innerHTML=riskProjectionSvg(plan)+`<div class="notice">${riskGoalText(plan)}</div>`;

  const goalMessage=document.getElementById('riskGoalMessage');
  if(goalMessage) goalMessage.textContent=riskGoalText(plan);

  const rows=document.getElementById('riskEvolutionRows');
  if(rows) rows.innerHTML=riskEvolutionRowsHtml(plan);

  const history=document.getElementById('riskHistory');
  if(history){
    const items=resolveiRiskState.history.slice().reverse();
    history.innerHTML=items.length
      ? items.map(x=>`<div class="risk-history-row"><div><strong class="${x.result==='WIN'?'risk-history-win':'risk-history-loss'}">${x.result==='WIN'?'✅ WIN':'❌ LOSS'}</strong><span>${x.at}</span></div><div>Seção ${x.section} · chance ${x.chance}</div><div>Entrada ${riskMoney(x.stake)}</div><div>Capital ${riskMoney(x.after)}</div></div>`).join('')
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
  const previous=resolveiRiskState.session||riskDefaults().session;
  const hasProgress=(resolveiRiskState.history||[]).length>0
    || Number(previous.section)>1
    || Number(previous.chance)>1
    || Math.abs((Number(previous.capital)||0)-(Number(previous.baseCapital)||0))>1e-9;
  const capital=hasProgress?Math.max(0,Number(previous.capital)||0):cfg.initialCapital;
  const section=hasProgress?Math.max(1,Math.round(Number(previous.section)||1)):1;
  resolveiRiskState.config=cfg;
  resolveiRiskState.session={
    capital,section,chance:1,baseCapital:capital,accumulatedLoss:0,
    status:capital>0?'active':'busted'
  };
  riskSave();
  riskCloudScheduleSave();
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
  const entry=document.getElementById('riskEntryPct');
  if(entry) entry.addEventListener('change',()=>{
    if(riskReconcileInputs('entry')) riskApplyConfig();
  });
  const chances=document.getElementById('riskChances');
  if(chances) chances.addEventListener('change',()=>{
    if(riskReconcileInputs('chances')) riskApplyConfig();
  });
  const payout=document.getElementById('riskPayout');
  if(payout) payout.addEventListener('change',()=>{
    if(riskReconcileInputs('payout')) riskApplyConfig();
  });
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
  const ready=document.getElementById('riskReadyStartBtn');
  if(ready) ready.addEventListener('click',()=>document.querySelector('.risk-control-card')?.scrollIntoView({behavior:'smooth',block:'center'}));
  riskRender();
  riskHydrateFromCloud();
}
