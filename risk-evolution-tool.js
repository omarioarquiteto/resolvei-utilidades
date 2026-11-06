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
      <span>Registre um WIN ou LOSS para acompanhar a evolução real do capital, operação por operação.</span>
    </div>`;
  }

  const firstCapital=Number(history[0].before);
  const initial=Number.isFinite(firstCapital)?Math.max(0,firstCapital):(Number(resolveiRiskState.config.initialCapital)||0);
  const series=[{value:initial,result:'START',at:'Capital inicial'}];
  history.forEach(item=>{
    const value=Number(item.after);
    const previous=series[series.length-1].value;
    series.push({
      value:Number.isFinite(value)?Math.max(0,value):previous,
      result:String(item.result||'').toUpperCase(),
      at:item.at||'',
      section:item.section,
      chance:item.chance,
      stake:Number(item.stake)||0
    });
  });

  const values=series.map(item=>item.value);
  let min=Math.min(...values),max=Math.max(...values);
  const padding=Math.max((max-min)*0.16,Math.max(Math.abs(max),1)*0.015,1);
  min=Math.max(0,min-padding);
  max+=padding;
  if(max-min<0.01) max=min+1;

  const width=900,height=300,left=88,right=24,top=30,bottom=48;
  const plotW=width-left-right,plotH=height-top-bottom;
  const xAt=i=>left+(series.length===1?plotW/2:(i/(series.length-1))*plotW);
  const yAt=value=>top+((max-value)/(max-min))*plotH;
  const coords=series.map((item,i)=>({x:xAt(i),y:yAt(item.value)}));
  const axisMoney=value=>new Intl.NumberFormat('pt-BR',{
    style:'currency',currency:'BRL',notation:'compact',maximumFractionDigits:1
  }).format(value).replace(/\u00a0/g,' ');

  const grid=[0,1,2,3,4].map(i=>{
    const y=top+(i/4)*plotH;
    const value=max-((max-min)*(i/4));
    return `<line x1="${left}" y1="${y.toFixed(1)}" x2="${width-right}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="1" stroke-dasharray="3 7" opacity=".9"/>
      <text x="${left-13}" y="${(y+4).toFixed(1)}" fill="var(--muted)" text-anchor="end" font-size="12">${axisMoney(value)}</text>`;
  }).join('');

  const segmentPath=i=>{
    const p0=coords[i],p1=coords[i+1];
    const previous=coords[Math.max(0,i-1)];
    const next=coords[Math.min(coords.length-1,i+2)];
    const tension=1/6;
    const c1x=p0.x+(p1.x-previous.x)*tension;
    const c1y=p0.y+(p1.y-previous.y)*tension;
    const c2x=p1.x-(next.x-p0.x)*tension;
    const c2y=p1.y-(next.y-p0.y)*tension;
    return `M ${p0.x.toFixed(1)} ${p0.y.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p1.x.toFixed(1)} ${p1.y.toFixed(1)}`;
  };

  const smoothPath=coords.slice(1).map((_,i)=>segmentPath(i)).join(' ');
  const areaPath=`${smoothPath} L ${coords[coords.length-1].x.toFixed(1)} ${(height-bottom).toFixed(1)} L ${coords[0].x.toFixed(1)} ${(height-bottom).toFixed(1)} Z`;
  const segments=series.slice(1).map((item,i)=>{
    const win=item.result==='WIN';
    const color=win?'#07965b':'#e04455';
    return `<path class="risk-history-segment ${win?'risk-history-segment-win':'risk-history-segment-loss'}" d="${segmentPath(i)}" fill="none" stroke="${color}" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>`;
  }).join('');

  const points=series.map((item,i)=>{
    const color=item.result==='WIN'?'#07965b':item.result==='LOSS'?'#e04455':'#315cda';
    const x=coords[i].x.toFixed(1),y=coords[i].y.toFixed(1);
    const isLast=i===series.length-1;
    const title=item.result==='START'?'Capital inicial':`${item.result} · ${item.at}`;
    return `<g class="risk-history-point">
      <title>${title} — ${riskMoney(item.value)}</title>
      <circle cx="${x}" cy="${y}" r="${isLast?10:7}" fill="var(--surface)" stroke="${color}" stroke-width="2.5"/>
      <circle cx="${x}" cy="${y}" r="${isLast?4.5:3.2}" fill="${color}"/>
    </g>`;
  }).join('');

  const labels=series.map((item,i)=>{
    if(!(i===0||i===series.length-1||i%5===0)) return '';
    const label=i===0?'INÍCIO':i===series.length-1?`#${i} ${item.result}`:`#${i}`;
    const anchor=i===0?'start':i===series.length-1?'end':'middle';
    return `<text x="${coords[i].x.toFixed(1)}" y="${height-15}" fill="var(--muted)" text-anchor="${anchor}" font-size="11" font-weight="700">${label}</text>`;
  }).join('');

  const last=series[series.length-1];
  const lastPoint=coords[coords.length-1];
  const bubbleWidth=158,bubbleHeight=30;
  const bubbleX=Math.max(left,Math.min(width-right-bubbleWidth,lastPoint.x-bubbleWidth/2));
  const bubbleY=Math.max(top,lastPoint.y-43);
  const bubbleColor=last.result==='WIN'?'#087d50':last.result==='LOSS'?'#bd3445':'#315cda';

  return `<svg class="risk-chart risk-chart-real" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Evolução real do capital após cada operação, com vitórias em verde e perdas em vermelho">
    <defs>
      <linearGradient id="riskActualAreaGradient" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="#4268e8" stop-opacity=".19"/>
        <stop offset="100%" stop-color="#4268e8" stop-opacity=".012"/>
      </linearGradient>
    </defs>
    ${grid}
    <path d="${areaPath}" fill="url(#riskActualAreaGradient)"/>
    <line x1="${left}" y1="${yAt(initial).toFixed(1)}" x2="${width-right}" y2="${yAt(initial).toFixed(1)}" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="6 7" opacity=".55"/>
    ${segments}
    ${points}
    ${labels}
    <g>
      <rect x="${bubbleX.toFixed(1)}" y="${bubbleY.toFixed(1)}" width="${bubbleWidth}" height="${bubbleHeight}" rx="15" fill="${bubbleColor}"/>
      <text x="${(bubbleX+bubbleWidth/2).toFixed(1)}" y="${(bubbleY+20).toFixed(1)}" text-anchor="middle" fill="#fff" font-size="14" font-weight="800">${riskMoney(last.value)}</text>
    </g>
  </svg>`;
}

function riskProjectionSvg(plan){
  const cfg=plan.cfg;
  const values=[Math.max(0.01,Number(resolveiRiskState.session.capital)||cfg.initialCapital)];
  let capital=values[0];
  for(let i=0;i<7;i++){
    const section=riskMakeSection(capital,cfg);
    capital=section.target;
    values.push(capital);
  }
  let min=Math.min(...values),max=Math.max(...values);
  const spread=Math.max(1,max-min),padValue=Math.max(spread*.32,Math.max(1,max)*.012);
  min=Math.max(0,min-padValue);max+=padValue;
  const width=760,height=190,left=62,right=18,top=34,bottom=30;
  const plotW=width-left-right,plotH=height-top-bottom;
  const xAt=i=>left+(i/(values.length-1))*plotW;
  const yAt=v=>top+((max-v)/(max-min))*plotH;
  const grid=[0,1,2,3].map(i=>{
    const y=top+(i/3)*plotH,value=max-((max-min)*(i/3));
    return `<line x1="${left}" y1="${y.toFixed(1)}" x2="${width-right}" y2="${y.toFixed(1)}" stroke="#dce3fa" stroke-width="1"/>
      <text x="${left-9}" y="${(y+4).toFixed(1)}" fill="var(--muted)" text-anchor="end" font-size="12">${riskMoney(value)}</text>`;
  }).join('');
  const points=values.map((v,i)=>`${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ');
  const circles=values.map((v,i)=>`<circle cx="${xAt(i).toFixed(1)}" cy="${yAt(v).toFixed(1)}" r="${i===values.length-1?7:4.7}" fill="#145cff" stroke="#fff" stroke-width="2"><title>${i===0?'Capital atual':'Alvo da seção '+i} — ${riskMoney(v)}</title></circle>`).join('');
  const area=`${left},${height-bottom} ${points} ${width-right},${height-bottom}`;
  const lastX=xAt(values.length-1),lastY=yAt(values[values.length-1]);
  const bubbleX=Math.min(width-142,Math.max(left,lastX-62)),bubbleY=Math.max(3,lastY-34);
  return `<svg class="risk-chart risk-chart-projection" viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolução projetada do capital ao longo das próximas sete seções">
    <defs><linearGradient id="riskCapitalArea" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#1b63ff" stop-opacity=".28"/><stop offset="100%" stop-color="#1b63ff" stop-opacity=".025"/></linearGradient></defs>
    ${grid}
    <polygon points="${area}" fill="url(#riskCapitalArea)"/>
    <polyline points="${points}" fill="none" stroke="#145cff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>
    ${circles}
    <rect x="${bubbleX}" y="${bubbleY}" width="132" height="27" rx="14" fill="#145cff"/>
    <text x="${bubbleX+66}" y="${bubbleY+18}" text-anchor="middle" fill="#fff" font-size="15" font-weight="800">${riskMoney(values[values.length-1])}</text>
    <text x="${left}" y="${height-7}" fill="var(--text)" font-size="12">Início</text>
    <text x="${width-right}" y="${height-7}" fill="var(--text)" text-anchor="end" font-size="12">Final</text>
  </svg>`;
}
function riskSummaryHtml(plan,current,currentRow){
  const status=resolveiRiskState.session.status;
  const history=resolveiRiskState.history||[];
  const last=history.length?history[history.length-1]:null;
  const latestLabel=last?(last.result==='WIN'?'✅ WIN':'❌ LOSS')+' registrado em '+last.at+' · capital '+riskMoney(last.after):'Nenhum resultado registrado ainda.';
  const initial=Math.max(0.01,Number(resolveiRiskState.config.initialCapital)||0.01);
  const changePct=((resolveiRiskState.session.capital-initial)/initial)*100;
  return `<div class="risk-kpis">
    <div class="risk-kpi risk-kpi-primary"><span class="risk-kpi-icon">▣</span><span class="risk-kpi-label">Capital atual</span><strong>${riskMoney(resolveiRiskState.session.capital)}</strong><small class="${changePct>=0?'risk-positive':'risk-negative'}">${changePct>=0?'↑':'↓'} ${riskPct(Math.abs(changePct))}</small></div>
    <div class="risk-kpi risk-kpi-entry"><span class="risk-kpi-icon">ϟ</span><span class="risk-kpi-label">Entrada agora</span><strong>${status==='active'&&currentRow?riskMoney(currentRow.stake):'—'}</strong><small>${status==='active'?'Chance: '+resolveiRiskState.session.chance+' de '+plan.cfg.chances:'Seção encerrada'}</small></div>
    <div class="risk-kpi risk-kpi-target"><span class="risk-kpi-icon">♜</span><span class="risk-kpi-label">Próximo alvo</span><strong>${riskMoney(current.target)}</strong><small>Lucro-alvo: ${riskMoney(current.growth)}</small></div>
    <div class="risk-kpi risk-kpi-exposure"><span class="risk-kpi-icon">◆</span><span class="risk-kpi-label">Exposição da seção</span><strong>${riskPct(current.maxDrawdownPct)}</strong><small>${riskMoney(current.totalExposure)} de ${riskMoney(current.baseCapital)}</small></div>
  </div>
  <details class="risk-indicator-details">
    <summary>Mais detalhes da estratégia <span>＋</span></summary>
    <div class="risk-latest-result"><span>Último movimento</span><strong>${latestLabel}</strong></div>
    <div class="risk-mini-grid">
      <div><span>Crescimento por seção</span><strong>+${riskPct(plan.cfg.entryPct/100*(plan.cfg.payout/100)*100)}</strong></div>
      <div><span>Entrada-base</span><strong>${riskPct(plan.cfg.entryPct)}</strong></div>
      <div><span>Payout considerado</span><strong>${riskPct(plan.cfg.payout)}</strong></div>
    </div>
    <div class="risk-note"><strong>Calculadora de banca:</strong> ao alterar a entrada-base, a ferramenta calcula quantas entradas completas cabem no capital atual. Ao alterar as chances por seção, calcula a entrada-base para que a última perda utilize o saldo disponível. Não há estimativa de probabilidade ou simulação de resultados.</div>
  </details>`;
}

function riskPlanTilesHtml(plan,current,currentRow){
  const status=resolveiRiskState.session.status;
  return `<div class="risk-plan-tiles">
    <div><span>Capital</span><strong>${riskMoney(resolveiRiskState.session.capital)}</strong></div>
    <div><span>Entrada</span><strong>${status==='active'&&currentRow?riskMoney(currentRow.stake):'—'}</strong></div>
    <div><span>Lucro-alvo</span><strong>${riskMoney(current.growth)}</strong></div>
    <div><span>Seção</span><strong>${riskPct(current.maxDrawdownPct)}</strong></div>
  </div>`;
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
  return `<div class="risk-tool-shell risk-reference-layout">
    <section class="risk-hero-banner">
      <div class="risk-hero-copy">
        <h1>Gerenciamento de risco<br><em>e evolução de capital</em></h1>
        <p>Calcule entradas, visualize seu desempenho<br class="risk-banner-break"> e evolua com segurança no mercado.</p>
      </div>
      <div class="risk-hero-art" aria-hidden="true">
        <div class="risk-hero-shield">↗</div>
        <div class="risk-hero-bars"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
        <div class="risk-hero-arrow">↗</div>
      </div>
    </section>

    <div class="risk-reference-grid">
      <div class="risk-primary-column">
        <section class="risk-overview-card card">
          <div class="risk-reference-heading">
            <div class="risk-reference-heading-icon">◎</div>
            <h2>Sua estratégia em números</h2>
            <span class="risk-period-pill">Últimas 30 operações</span>
          </div>
          <div id="riskDashboard"></div>
          <span id="riskStatusPill" class="risk-status-pill" hidden>${resolveiRiskState.session.status==='active'?'EM ANDAMENTO':'SEÇÃO ENCERRADA'}</span>
          <details class="risk-section-detail">
            <summary>Detalhes da seção atual <span>＋</span></summary>
            <div id="riskCurrentSection"></div>
          </details>
        </section>

        <section class="risk-chart-card risk-main-chart-card card">
          <div class="risk-reference-heading risk-chart-heading">
            <div class="risk-chart-heading-icon">▥</div>
            <div><h2>Evolução do seu capital</h2></div>
            <div class="risk-chart-legend"><span><i class="risk-legend-win"></i>WIN</span><span><i class="risk-legend-loss"></i>LOSS</span></div>
          </div>
          <div id="riskActualEvolution"></div>
        </section>

        <section class="risk-control-card card">
          <div class="actions risk-actions">
            <button class="btn risk-result-btn risk-win-btn" id="riskWinBtn" type="button"><span>↗</span> WIN</button>
            <button class="btn risk-result-btn risk-loss-btn" id="riskLossBtn" type="button"><span>↘</span> LOSS</button>
          </div>
          <div class="risk-control-subline">
            <span>Registre o resultado real de cada operação.</span>
            <span class="risk-cloud-status" id="riskCloudStatus">💾 Aguardando sincronização</span>
          </div>
        </section>
      </div>

      <aside class="risk-aside-column">
        <section class="risk-config-card card">
          <div class="risk-config-heading">
            <div class="risk-config-heading-icon">⚙</div>
            <h2>Configuração do plano</h2>
            <button type="button" class="risk-summary-action" id="riskConfigEditBtn" aria-expanded="false">Editar</button>
          </div>
          <div id="riskPlanTiles"></div>
          <div id="riskConfigFields" class="risk-config-fields" hidden>
            <div class="notice"><strong>Calculadora da sua planilha.</strong> A primeira entrada usa a entrada-base sobre o capital atual; as seguintes consideram as perdas anteriores e buscam o próximo alvo.</div>
            <div class="form-grid risk-form-grid">
              <div class="field"><label for="riskInitialCapital">Capital inicial</label><div class="input-wrap"><span class="prefix">R$</span><input id="riskInitialCapital" type="number" step="0.01" min="0.01" value="${cfg.initialCapital}"></div></div>
              <div class="field"><label for="riskEntryPct">Entrada-base</label><div class="input-wrap"><input id="riskEntryPct" type="number" step="any" min="0" max="100" value="${cfg.entryPct}"><span class="suffix">%</span></div><small>Ao alterar, a quantidade de chances é recalculada para caber no capital atual.</small></div>
              <div class="field"><label for="riskPayout">Payout / retorno líquido</label><div class="input-wrap"><input id="riskPayout" type="number" step="0.1" min="0.1" max="100" value="${cfg.payout}"><span class="suffix">%</span></div><small>85% = lucro de R$ 0,85 por R$ 1,00 em uma vitória.</small></div>
              <div class="field"><label for="riskChances">Chances por seção</label><div class="input-wrap"><input id="riskChances" type="number" step="1" min="1" max="30" value="${cfg.chances}"></div><small>A entrada-base é recalculada para utilizar o capital disponível.</small></div>
              <div class="field full"><label for="riskGoal">Meta de patrimônio</label><div class="input-wrap"><span class="prefix">R$</span><input id="riskGoal" type="number" step="0.01" min="0.01" value="${cfg.goal}"></div></div>
            </div>
            <div class="actions">
              <button class="btn primary" id="riskApplyBtn" type="button">Aplicar configurações</button>
              <button class="btn ghost" id="riskResetBtn" type="button">Zerar plano</button>
            </div>
            <div class="risk-formula"><strong>Fórmula central</strong><span>Entrada 1 = capital atual × entrada-base</span><span>Entrada seguinte = (alvo − capital restante após perdas) ÷ payout</span><span>Ao definir as chances, a entrada-base ajusta a exposição total ao capital disponível</span></div>
          </div>
        </section>

        <section class="risk-tip-card">
          <span class="risk-tip-icon">💡</span>
          <div><small>DICAS DE OURO</small><h3>Disciplina é sua maior vantagem.</h3><p>Mantenha sua exposição dentro do limite recomendado para maior consistência.</p></div>
          <span class="risk-tip-arrow">→</span>
        </section>

        <section class="risk-ready-card">
          <div class="risk-ready-rocket">🚀</div>
          <h3>Pronto para operar?</h3>
          <p>Aplique sua estratégia e acompanhe os resultados em tempo real.</p>
          <button type="button" id="riskReadyStartBtn">Começar agora <span>→</span></button>
        </section>
      </aside>
    </div>

    <section class="risk-history-card card">
      <div class="risk-history-heading">
        <div class="risk-history-title-icon">◷</div>
        <h2>Histórico e resultado</h2>
        <button type="button" id="riskViewFullHistoryBtn">Ver histórico completo <span>→</span></button>
      </div>
      <div id="riskHistory"></div>
      <details class="risk-advanced-details" id="riskAdvancedDetails">
        <summary>Mais ferramentas e informações <span>＋</span></summary>
        <div class="risk-advanced-grid">
          <section><h3>Plano completo das seções</h3><div class="risk-evolution-table"><div class="risk-section-row risk-section-header"><div>Seção</div><div>Capital-base</div><div>Lucro alvo</div><div>Próximo capital</div><div>Exposição máxima</div></div><div id="riskEvolutionRows"></div></div><div class="risk-note" id="riskGoalMessage"></div></section>
          <section><h3>Projeção de capital</h3><div id="riskProjection"></div></section>
        </div>
        <div class="risk-advanced-actions">
          <button class="btn ghost" id="riskRestartBtn" type="button">↻ Recomeçar com capital restante</button>
          <button class="btn ghost" id="riskClearHistoryBtn" type="button">Limpar histórico</button>
          <button class="btn" id="riskExportBtn" type="button">⬇ Exportar CSV</button>
        </div>
      </details>
    </section>
  </div>`;
}
function riskRender(){
  const dash=document.getElementById('riskDashboard');
  if(!dash) return;
  const plan=riskPlan();
  const current=riskCurrentSection();
  const currentRow=riskCurrentRow();
  dash.innerHTML=riskSummaryHtml(plan,current,currentRow);
  const planTiles=document.getElementById('riskPlanTiles');
  if(planTiles) planTiles.innerHTML=riskPlanTilesHtml(plan,current,currentRow);

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
  if(projection) projection.innerHTML=riskProjectionSvg(plan);

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
  const editConfig=document.getElementById('riskConfigEditBtn');
  const configFields=document.getElementById('riskConfigFields');
  if(editConfig&&configFields) editConfig.addEventListener('click',()=>{
    const opening=configFields.hidden;
    configFields.hidden=!opening;
    editConfig.textContent=opening?'Fechar':'Editar';
    editConfig.setAttribute('aria-expanded',opening?'true':'false');
    if(opening) configFields.scrollIntoView({behavior:'smooth',block:'nearest'});
  });
  const viewHistory=document.getElementById('riskViewFullHistoryBtn');
  const advanced=document.getElementById('riskAdvancedDetails');
  if(viewHistory) viewHistory.addEventListener('click',()=>{
    const history=document.getElementById('riskHistory');
    if(history) history.classList.toggle('is-expanded');
    if(advanced) advanced.open=!!history?.classList.contains('is-expanded');
    viewHistory.innerHTML=history?.classList.contains('is-expanded')?'Recolher histórico <span>↑</span>':'Ver histórico completo <span>→</span>';
    if(advanced) advanced.scrollIntoView({behavior:'smooth',block:'nearest'});
  });
  riskRender();
  riskHydrateFromCloud();
}
