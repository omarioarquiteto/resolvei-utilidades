/* Resolvei — Gerador de Senhas
 * Geração exclusivamente local no navegador.
 * Não envia, salva ou registra as senhas geradas.
 */
(function(){
  const LOWER='abcdefghijklmnopqrstuvwxyz';
  const UPPER='ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const NUMBERS='0123456789';
  const SYMBOLS='!@#$%^&*()-_=+[]{};:,.?';
  const AMBIGUOUS='O0oIl1|';
  const SAFE_SYMBOLS='!@#$%^&*_-+=?';
  const PHRASE_WORDS=[
    'Casa','Nuvem','Ponte','Cacto','Rio','Verde','Sol','Lago','Fogo','Vento',
    'Pedra','Lua','Cobre','Azul','Jardim','Montanha','Café','Estrela','Praia','Floresta'
  ];

  function randomInt(max){
    if(!window.crypto?.getRandomValues) throw new Error('Seu navegador não oferece geração criptográfica segura.');
    if(max<=0) throw new Error('Limite inválido.');
    const limit=Math.floor(0x100000000/max)*max;
    const a=new Uint32Array(1);
    do{crypto.getRandomValues(a);}while(a[0]>=limit);
    return a[0]%max;
  }
  function randomChar(chars){ return chars[randomInt(chars.length)]; }
  function shuffle(chars){
    const a=chars.slice();
    for(let i=a.length-1;i>0;i--){const j=randomInt(i+1);[a[i],a[j]]=[a[j],a[i]];}
    return a;
  }
  function removeAmbiguous(chars){return chars.split('').filter(c=>!AMBIGUOUS.includes(c)).join('');}
  function getOptions(){
    return {
      length:Math.min(64,Math.max(8,Number(document.getElementById('pwdLength')?.value||20))),
      upper:!!document.getElementById('pwdUpper')?.checked,
      lower:!!document.getElementById('pwdLower')?.checked,
      numbers:!!document.getElementById('pwdNumbers')?.checked,
      symbols:!!document.getElementById('pwdSymbols')?.checked,
      avoid:!!document.getElementById('pwdAvoid')?.checked
    };
  }
  function entropy(o){
    let size=0;
    if(o.upper)size+=o.avoid?removeAmbiguous(UPPER).length:UPPER.length;
    if(o.lower)size+=o.avoid?removeAmbiguous(LOWER).length:LOWER.length;
    if(o.numbers)size+=o.avoid?removeAmbiguous(NUMBERS).length:NUMBERS.length;
    if(o.symbols)size+=o.avoid?removeAmbiguous(SYMBOLS).length:SYMBOLS.length;
    return size?Math.round(o.length*Math.log2(size)):0;
  }
  function strength(bits,length){
    if(!bits)return ['Escolha pelo menos um tipo de caractere','weak'];
    if(bits<50)return ['Fraca','weak'];
    if(bits<80)return ['Boa','medium'];
    if(bits<100)return ['Forte','strong'];
    return ['Muito forte','very-strong'];
  }
  function generate(){
    const o=getOptions();
    let pools=[];
    if(o.upper)pools.push(o.avoid?removeAmbiguous(UPPER):UPPER);
    if(o.lower)pools.push(o.avoid?removeAmbiguous(LOWER):LOWER);
    if(o.numbers)pools.push(o.avoid?removeAmbiguous(NUMBERS):NUMBERS);
    if(o.symbols)pools.push(o.avoid?removeAmbiguous(SYMBOLS):SYMBOLS);
    if(!pools.length){document.getElementById('pwdValue').value='';updateMeter(0,o.length);return;}
    const chars=[];
    pools.forEach(p=>chars.push(randomChar(p)));
    const all=pools.join('');
    while(chars.length<o.length)chars.push(randomChar(all));
    const password=shuffle(chars).join('');
    document.getElementById('pwdValue').value=password;
    updateMeter(entropy(o),o.length);
  }
  function generatePhrase(){
    const words=[];
    for(let i=0;i<4;i++)words.push(PHRASE_WORDS[randomInt(PHRASE_WORDS.length)]);
    const number=randomInt(100);
    const symbol=randomChar(SAFE_SYMBOLS);
    const phrase=shuffle(words).join('-')+symbol+String(number).padStart(2,'0');
    document.getElementById('pwdValue').value=phrase;
    updateMeter(4*4.3+6.6+Math.log2(SAFE_SYMBOLS.length),phrase.length);
  }
  function generatePin(){
    const len=Math.min(12,Math.max(4,Number(document.getElementById('pwdPinLength')?.value||6)));
    let pin='';
    for(let i=0;i<len;i++)pin+=randomChar(NUMBERS);
    document.getElementById('pwdValue').value=pin;
    updateMeter(Math.round(len*Math.log2(10)),len);
  }
  function updateMeter(bits,length){
    const meter=document.getElementById('pwdMeterFill'),label=document.getElementById('pwdMeterLabel'),detail=document.getElementById('pwdMeterDetail');
    if(!meter||!label)return;
    const [text,cls]=strength(bits,length);
    meter.className='password-meter-fill '+cls;
    meter.style.width=Math.max(4,Math.min(100,bits/1.28))+'%';
    label.textContent=text;
    if(detail)detail.textContent=bits?length+' caracteres · ~'+Math.round(bits)+' bits de entropia teórica':'Selecione as opções acima';
  }
  async function copyPassword(){
    const input=document.getElementById('pwdValue'),btn=document.getElementById('pwdCopy');
    if(!input?.value)return;
    try{await navigator.clipboard.writeText(input.value);btn.textContent='✓ Copiada';setTimeout(()=>btn.textContent='📋 Copiar',1200);}
    catch{input.focus();input.select();document.execCommand('copy');btn.textContent='✓ Copiada';setTimeout(()=>btn.textContent='📋 Copiar',1200);}
  }
  function toggleVisibility(){
    const input=document.getElementById('pwdValue'),btn=document.getElementById('pwdReveal');
    if(!input)return;
    input.type=input.type==='password'?'text':'password';
    if(btn)btn.textContent=input.type==='password'?'👁 Mostrar':'🙈 Ocultar';
  }
  function showMode(mode){
    document.querySelectorAll('[data-pwd-mode]').forEach(b=>b.classList.toggle('active',b.dataset.pwdMode===mode));
    document.querySelectorAll('.password-mode-panel').forEach(p=>p.hidden=p.dataset.pwdPanel!==mode);
    const options=document.getElementById('pwdOptions'); if(options)options.hidden=mode!=='password';
    if(mode==='password')generate();
    else if(mode==='phrase')generatePhrase();
    else generatePin();
  }
  function bind(){
    const root=document.getElementById('passwordGenerator');
    if(!root||root.dataset.bound==='1')return;
    root.dataset.bound='1';
    root.querySelectorAll('[data-pwd-mode]').forEach(b=>b.addEventListener('click',()=>showMode(b.dataset.pwdMode)));
    document.getElementById('pwdGenerate')?.addEventListener('click',generate);
    document.getElementById('pwdPhraseGenerate')?.addEventListener('click',generatePhrase);
    document.getElementById('pwdPinGenerate')?.addEventListener('click',generatePin);
    document.getElementById('pwdCopy')?.addEventListener('click',copyPassword);
    document.getElementById('pwdReveal')?.addEventListener('click',toggleVisibility);
    document.getElementById('pwdLength')?.addEventListener('input',e=>{document.getElementById('pwdLengthValue').textContent=e.target.value;generate();});
    document.getElementById('pwdPinLength')?.addEventListener('input',e=>{document.getElementById('pwdPinLengthValue').textContent=e.target.value;generatePin();});
    ['pwdUpper','pwdLower','pwdNumbers','pwdSymbols','pwdAvoid'].forEach(id=>document.getElementById(id)?.addEventListener('change',generate));
    showMode('password');
  }
  window.resolveiPasswordGeneratorUI=function(){
    return '<div id="passwordGenerator" class="password-generator">'+
      '<div class="password-tabs">'+
        '<button type="button" class="password-tab active" data-pwd-mode="password">🔐 Senha aleatória</button>'+
        '<button type="button" class="password-tab" data-pwd-mode="phrase">🧩 Frase-senha</button>'+
        '<button type="button" class="password-tab" data-pwd-mode="pin">🔢 PIN</button>'+
      '</div>'+
      '<section class="password-main-card">'+
        '<div class="password-output-label">Sua senha</div>'+
        '<div class="password-output-row"><input id="pwdValue" type="password" readonly aria-label="Senha gerada"><button type="button" id="pwdReveal" class="password-small-btn">👁 Mostrar</button><button type="button" id="pwdCopy" class="password-copy-btn">📋 Copiar</button></div>'+
        '<div class="password-meter"><div id="pwdMeterFill" class="password-meter-fill very-strong"></div></div>'+
        '<div class="password-meter-meta"><strong id="pwdMeterLabel">Muito forte</strong><span id="pwdMeterDetail"></span></div>'+
        '<div id="pwdOptions" class="password-mode-panel" data-pwd-panel="password">'+
          '<div class="password-option-head"><strong>Personalize sua senha</strong><span><b id="pwdLengthValue">20</b> caracteres</span></div>'+
          '<input id="pwdLength" class="password-range" type="range" min="8" max="64" value="20">'+
          '<div class="password-check-grid">'+
            '<label><input id="pwdUpper" type="checkbox" checked> Letras maiúsculas</label>'+
            '<label><input id="pwdLower" type="checkbox" checked> Letras minúsculas</label>'+
            '<label><input id="pwdNumbers" type="checkbox" checked> Números</label>'+
            '<label><input id="pwdSymbols" type="checkbox" checked> Símbolos</label>'+
            '<label class="full"><input id="pwdAvoid" type="checkbox"> Evitar caracteres ambíguos <small>(O, 0, o, I, l, 1, |)</small></label>'+
          '</div>'+
          '<button type="button" id="pwdGenerate" class="btn primary password-generate-btn">🔄 Gerar nova senha</button>'+
        '</div>'+
        '<section class="password-mode-panel" data-pwd-panel="phrase" hidden>'+
          '<div class="password-option-head"><strong>Frase-senha memorável</strong><span>4 palavras + número + símbolo</span></div>'+
          '<p class="password-help">Boa opção quando você precisa digitar a senha com frequência.</p>'+
          '<button type="button" id="pwdPhraseGenerate" class="btn primary password-generate-btn">🔄 Gerar frase-senha</button>'+
        '</section>'+
        '<section class="password-mode-panel" data-pwd-panel="pin" hidden>'+
          '<div class="password-option-head"><strong>PIN numérico</strong><span><b id="pwdPinLengthValue">6</b> dígitos</span></div>'+
          '<input id="pwdPinLength" class="password-range" type="range" min="4" max="12" value="6">'+
          '<button type="button" id="pwdPinGenerate" class="btn primary password-generate-btn">🔄 Gerar novo PIN</button>'+
        '</section>'+
      '</section>'+
      '<div class="password-privacy-note">🔒 <strong>Privacidade:</strong> a senha é gerada diretamente neste navegador. O Resolvei não envia nem armazena a senha gerada.</div>'+
      '<div class="password-tips"><strong>💡 Dica</strong><span>Use senhas diferentes para serviços diferentes e prefira autenticação em dois fatores quando disponível.</span></div>'+
    '</div>';
  };
  window.resolveiBindPasswordGenerator=bind;
})();