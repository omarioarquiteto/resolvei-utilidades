const CATS = {
  dinheiro: { name:'Dinheiro', icon:'💰', desc:'Contas, juros, descontos e planejamento.' },
  casa: { name:'Casa & Construção', icon:'🏠', desc:'Obra, reforma, pintura, piso e instalações.' },
  energia: { name:'Energia & Solar', icon:'☀️', desc:'Energia fotovoltaica, orientação solar e estimativas de geração.' },
  carro: { name:'Carro & Viagem', icon:'🚗', desc:'Combustível, viagem, consumo e custos.' },
  tempo: { name:'Tempo & Datas', icon:'⏱️', desc:'Idades, datas, horários e contagens.' },
  medidas: { name:'Medidas & Conversores', icon:'📐', desc:'Unidades de comprimento, peso, volume e mais.' },
  cozinha: { name:'Cozinha', icon:'🍳', desc:'Receitas, porções, temperaturas e conversões.' },
  festas: { name:'Festas & Eventos', icon:'🎉', desc:'Planeje quantidades para receber pessoas.' },
  trabalho: { name:'Trabalho & Rotina', icon:'💼', desc:'Horas, produtividade e pequenas contas.' },
  outros: { name:'Outras utilidades', icon:'🧰', desc:'Ferramentas rápidas para problemas cotidianos.' }
};

const fmt = new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2});
const money = n => `R$ ${fmt.format(Number(n)||0)}`;
const num = n => fmt.format(Number(n)||0);
const pct = n => `${fmt.format(Number(n)||0)}%`;
const val = id => Number(document.getElementById(id)?.value || 0);
const esc = s => String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
const slug = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');

const tools = [
  {id:'porcentagem',cat:'dinheiro',icon:'%',title:'Calculadora de porcentagem',desc:'Descubra porcentagens, variações e valores rapidamente.',tags:'porcentagem percentual percentagem aumento redução'},
  {id:'regra-de-3',cat:'dinheiro',icon:'⅓',title:'Regra de 3',desc:'Resolva proporções simples em segundos.',tags:'regra de tres proporção proporcional'},
  {id:'desconto',cat:'dinheiro',icon:'🏷️',title:'Desconto',desc:'Calcule preço final, desconto e economia.',tags:'desconto promoção preço liquidação'},
  {id:'acrescimo',cat:'dinheiro',icon:'↗',title:'Acréscimo',desc:'Calcule preço final após aumento ou taxa.',tags:'acrescimo aumento taxa preço'},
  {id:'juros-simples',cat:'dinheiro',icon:'💵',title:'Juros simples',desc:'Veja juros, montante e crescimento linear.',tags:'juros simples financeiro'},
  {id:'juros-compostos',cat:'dinheiro',icon:'📈',title:'Juros compostos',desc:'Simule crescimento com juros sobre juros.',tags:'juros compostos investimento'},
  {id:'dividir-conta',cat:'dinheiro',icon:'🍽️',title:'Dividir conta',desc:'Divida a conta entre pessoas e inclua gorjeta.',tags:'dividir conta restaurante pessoas'},
  {id:'gorjeta',cat:'dinheiro',icon:'🤝',title:'Gorjeta',desc:'Calcule gorjeta e valor total da conta.',tags:'gorjeta serviço 10 15'},
  {id:'financiamento',cat:'dinheiro',icon:'🏦',title:'Parcela de financiamento',desc:'Estime parcela, total pago e juros.',tags:'financiamento financiamento carro apartamento parcela'},
  {id:'emprestimo',cat:'dinheiro',icon:'💳',title:'Custo de empréstimo',desc:'Estime quanto um empréstimo custa ao longo do tempo.',tags:'emprestimo crédito parcela juros'},
  {id:'meta-poupanca',cat:'dinheiro',icon:'🎯',title:'Meta de economia',desc:'Descubra quanto guardar por mês para chegar a uma meta.',tags:'guardar economizar poupar meta dinheiro'},
  {id:'poder-compra',cat:'dinheiro',icon:'🛒',title:'Poder de compra',desc:'Compare o valor nominal com uma inflação estimada.',tags:'inflação poder de compra dinheiro'},
  {id:'analise-opcoes',cat:'dinheiro',icon:'⏱️',title:'Análise de opções binárias',desc:'Estude pares de moedas para entradas com expiração de 1, 5 ou 15 minutos.',tags:'opções binárias binary options call put compra venda expiração 1 5 15 moedas'},
  {id:'combustivel-viagem',cat:'carro',icon:'⛽',title:'Combustível da viagem',desc:'Estime litros necessários e custo da viagem.',tags:'gasolina etanol combustível viagem litros km'},
  {id:'custo-km',cat:'carro',icon:'🛣️',title:'Custo por km',desc:'Descubra quanto seu carro custa a cada quilômetro.',tags:'custo km carro combustível consumo'},
  {id:'gasolina-etanol',cat:'carro',icon:'⚖️',title:'Gasolina × etanol',desc:'Compare preços pela eficiência energética do combustível.',tags:'gasolina etanol álcool abastecer'},
  {id:'consumo-carro',cat:'carro',icon:'🚘',title:'Consumo do carro',desc:'Calcule km/L e compare abastecimentos.',tags:'consumo km litro carro'},
  {id:'tempo-viagem',cat:'carro',icon:'🕒',title:'Tempo de viagem',desc:'Calcule duração aproximada pela distância e velocidade.',tags:'tempo viagem velocidade distância'},
  {id:'custo-viagem',cat:'carro',icon:'🧳',title:'Custo total da viagem',desc:'Combine combustível, pedágio e outros custos.',tags:'viagem pedágio combustível viagem carro'},
  {id:'tinta',cat:'casa',icon:'🎨',title:'Quantidade de tinta',desc:'Estime litros necessários para pintar paredes.',tags:'tinta pintura parede reforma'},
  {id:'piso',cat:'casa',icon:'▦',title:'Quantidade de piso',desc:'Calcule peças e caixas com margem de perda.',tags:'piso revestimento porcelanato ceramica'},
  {id:'rejunte',cat:'casa',icon:'▤',title:'Quantidade de rejunte',desc:'Estime consumo de rejunte para revestimentos.',tags:'rejunte revestimento junta piso'},
  {id:'argamassa',cat:'casa',icon:'🧱',title:'Argamassa',desc:'Estime quantidade de argamassa para assentamento.',tags:'argamassa piso revestimento obra'},
  {id:'concreto',cat:'casa',icon:'🧱',title:'Volume de concreto',desc:'Calcule volume e estimativa de materiais.',tags:'concreto laje fundação viga piso'},
  {id:'blocos',cat:'casa',icon:'🏗️',title:'Blocos ou tijolos',desc:'Estime quantidade de unidades para uma parede.',tags:'bloco tijolo parede alvenaria'},
  {id:'telhas',cat:'casa',icon:'🏡',title:'Quantidade de telhas',desc:'Estime telhas por área e inclinação.',tags:'telha cobertura telhado'},
  {id:'escada',cat:'casa',icon:'🪜',title:'Escada: espelho e piso',desc:'Estime uma relação confortável entre espelho e piso.',tags:'escada degrau espelho piso'},
  {id:'iluminacao',cat:'casa',icon:'💡',title:'Iluminação do ambiente',desc:'Estime fluxo luminoso total de um ambiente.',tags:'iluminação lumens lampada ambiente'},
  {id:'ar-condicionado',cat:'casa',icon:'❄️',title:'BTUs de ar-condicionado',desc:'Estimativa inicial da capacidade para um ambiente.',tags:'btu ar condicionado ar-condicionado calor'},
  {id:'caixa-dagua',cat:'casa',icon:'🚰',title:'Caixa d’água',desc:'Estime capacidade com base em pessoas e reserva.',tags:'caixa d agua água litros casa'},
  {id:'piscina',cat:'casa',icon:'🏊',title:'Volume da piscina',desc:'Calcule litros e volume de uma piscina retangular.',tags:'piscina agua volume litros'},
  {id:'cobertura',cat:'casa',icon:'📐',title:'Inclinação de cobertura',desc:'Calcule altura pela porcentagem de inclinação.',tags:'telhado inclinação cobertura altura'},
  {id:'placas-solares',cat:'energia',icon:'☀️',title:'Dimensionamento de placas solares',desc:'Estime módulos, potência, inversor, materiais, custo e payback.',tags:'solar fotovoltaica painel placa inversor energia conta luz kwh economia payback financiamento'},
  {id:'posicao-solar',cat:'energia',icon:'🧭',title:'Posicionamento dos módulos — integrado ao solar',desc:'Use a etapa visual dentro do dimensionamento para marcar telhados, obstáculos, escala e posição dos módulos.',tags:'posição solar insolação telhado norte azimute orientação sombra placas fotovoltaicas imagem drone satelite módulo painel'},
  {id:'conversor-arquivos',cat:'medidas',icon:'🔄',title:'Conversor de arquivos',desc:'Converta vídeos, imagens e PDFs entre formatos comuns.',tags:'converter arquivo mp4 avi mov webm jpg png webp pdf imagem video'},
  {id:'jpg-png-webp',cat:'medidas',icon:'🖼️',title:'JPG ↔ PNG ↔ WEBP',desc:'Converta imagens entre formatos populares.',tags:'jpg jpeg png webp converter imagem formato'},
  {id:'heic-jpg',cat:'medidas',icon:'📱',title:'HEIC → JPG',desc:'Converta fotos do iPhone para JPG.',tags:'heic iphone celular foto jpg converter'},
  {id:'imagem-pdf',cat:'medidas',icon:'📄',title:'Imagem → PDF',desc:'Transforme uma ou várias imagens em PDF.',tags:'imagem pdf jpg png celular documento'},
  {id:'pdf-imagens-zip',cat:'medidas',icon:'🗂️',title:'PDF → imagens ZIP',desc:'Exporte todas as páginas de um PDF para imagens em um ZIP.',tags:'pdf jpg png zip paginas converter'},
  {id:'mp4-mp3',cat:'medidas',icon:'🎵',title:'MP4 → MP3',desc:'Extraia o áudio de um vídeo.',tags:'mp4 mp3 audio video musica converter'},
  {id:'mp4-gif',cat:'medidas',icon:'🎞️',title:'MP4 → GIF',desc:'Transforme um trecho de vídeo em GIF animado.',tags:'mp4 gif video animado converter'},
  {id:'csv-xlsx',cat:'medidas',icon:'📊',title:'CSV ↔ XLSX',desc:'Converta planilhas CSV e Excel.',tags:'csv xlsx excel planilha converter'},
  {id:'zip-arquivos',cat:'medidas',icon:'🗜️',title:'Comprimir arquivos em ZIP',desc:'Junte vários arquivos em um único ZIP.',tags:'zip compactar comprimir arquivos pasta'},
  {id:'mov-mp4',cat:'medidas',icon:'📱',title:'MOV → MP4',desc:'Converta vídeos do iPhone para MP4.',tags:'mov mp4 iphone celular video converter'},
  {id:'jpg-heic',cat:'medidas',icon:'📱',title:'JPG → HEIC',desc:'Converta imagens para HEIC quando o servidor suportar esse formato.',tags:'jpg heic iphone celular imagem converter'},
  {id:'imagem-comprimir',cat:'medidas',icon:'🗜️',title:'Comprimir imagem',desc:'Reduza o tamanho de JPG, PNG e WEBP.',tags:'imagem comprimir reduzir tamanho jpg png webp'},
  {id:'docx-pdf',cat:'medidas',icon:'📝',title:'DOCX → PDF',desc:'Gere um PDF simples a partir do texto de um documento Word.',tags:'docx word pdf documento converter'},
  {id:'pdf-docx',cat:'medidas',icon:'📝',title:'PDF → DOCX',desc:'Extraia o texto de um PDF para um documento Word editável.',tags:'pdf docx word documento converter'},
  {id:'pdf-txt',cat:'medidas',icon:'📄',title:'PDF → TXT',desc:'Extraia o texto de um PDF para texto puro.',tags:'pdf txt texto documento'},
  {id:'txt-pdf',cat:'medidas',icon:'📄',title:'TXT → PDF',desc:'Transforme texto simples em PDF.',tags:'txt pdf texto documento'},
  {id:'pdf-xlsx',cat:'medidas',icon:'📊',title:'PDF → XLSX',desc:'Organize texto de páginas de PDF em uma planilha Excel.',tags:'pdf xlsx excel planilha documento'},
  {id:'xlsx-csv',cat:'medidas',icon:'📊',title:'XLSX → CSV',desc:'Exporte uma planilha Excel para CSV.',tags:'xlsx csv excel planilha'},
  {id:'audio-mp3-wav',cat:'medidas',icon:'🎵',title:'Áudio MP3 ↔ WAV',desc:'Converta formatos comuns de áudio.',tags:'mp3 wav audio converter'},
  {id:'audio-ogg',cat:'medidas',icon:'🎵',title:'Áudio → OGG',desc:'Converta áudio para OGG.',tags:'mp3 wav ogg audio converter'},
  {id:'video-webm',cat:'medidas',icon:'🎬',title:'Vídeo → WEBM',desc:'Converta vídeos para WEBM.',tags:'mp4 mov webm video converter'},
  {id:'video-avi',cat:'medidas',icon:'🎬',title:'Vídeo → AVI',desc:'Converta vídeos para AVI.',tags:'mp4 mov avi video converter'},
  {id:'video-audio',cat:'medidas',icon:'🎧',title:'Vídeo → áudio',desc:'Extraia o áudio de vídeos.',tags:'video mp3 audio extrair'},
  {id:'svg-png',cat:'medidas',icon:'🖼️',title:'SVG → PNG',desc:'Converta gráficos vetoriais SVG para PNG.',tags:'svg png imagem vetor'},
  {id:'png-ico',cat:'medidas',icon:'🔷',title:'PNG → ICO',desc:'Crie ícones ICO para sites e atalhos.',tags:'png ico favicon icon'},
  {id:'imagem-redimensionar',cat:'medidas',icon:'↔️',title:'Redimensionar imagem',desc:'Defina largura e altura de uma imagem.',tags:'redimensionar imagem pixels foto'},
  {id:'pdf-comprimir',cat:'medidas',icon:'🗜️',title:'Comprimir PDF',desc:'Reduza o tamanho de um PDF quando possível.',tags:'pdf comprimir reduzir tamanho'},
  {id:'arquivos-zip',cat:'medidas',icon:'🗜️',title:'ZIP de vários arquivos',desc:'Compacte vários arquivos em um único ZIP.',tags:'zip arquivos compactar'},
  {id:'area-retangulo',cat:'medidas',icon:'▭',title:'Área do retângulo',desc:'Calcule área a partir de largura e comprimento.',tags:'area retangulo terreno ambiente'},
  {id:'area-triangulo',cat:'medidas',icon:'△',title:'Área do triângulo',desc:'Calcule área de triângulos.',tags:'area triangulo'},
  {id:'area-circulo',cat:'medidas',icon:'○',title:'Área do círculo',desc:'Calcule área a partir do raio ou diâmetro.',tags:'area circulo círculo'},
  {id:'volume-caixa',cat:'medidas',icon:'▣',title:'Volume de uma caixa',desc:'Calcule litros e metros cúbicos.',tags:'volume caixa cubica litro'},
  {id:'temperatura',cat:'medidas',icon:'🌡️',title:'Temperatura °C ↔ °F',desc:'Converta Celsius e Fahrenheit.',tags:'celsius fahrenheit temperatura'},
  {id:'comprimento',cat:'medidas',icon:'📏',title:'Conversor de comprimento',desc:'Converta mm, cm, m, km, polegadas, pés e milhas.',tags:'comprimento metro centimetro polegada pés'},
  {id:'peso',cat:'medidas',icon:'⚖️',title:'Conversor de peso',desc:'Converta mg, g, kg, toneladas, lb e oz.',tags:'peso massa kg libra onça'},
  {id:'volume',cat:'medidas',icon:'🧪',title:'Conversor de volume',desc:'Converta ml, L, m³, galão e mais.',tags:'volume ml litro litro galão'},
  {id:'area',cat:'medidas',icon:'◫',title:'Conversor de área',desc:'Converta m², km², hectare, acre e ft².',tags:'area hectare acre metro quadrado'},
  {id:'velocidade',cat:'medidas',icon:'🏎️',title:'Conversor de velocidade',desc:'Converta km/h, mph e m/s.',tags:'velocidade kmh mph metro segundo'},
  {id:'dados',cat:'medidas',icon:'💾',title:'Conversor de dados',desc:'Converta KB, MB, GB e TB.',tags:'dados armazenamento kb mb gb tb'},
  {id:'energia',cat:'medidas',icon:'⚡',title:'Conversor de potência',desc:'Converta W, kW e cv.',tags:'potencia watt kw cavalo'},
  {id:'idade',cat:'tempo',icon:'🎂',title:'Idade exata',desc:'Calcule anos, meses e dias a partir da data de nascimento.',tags:'idade aniversario nascimento'},
  {id:'dias-entre-datas',cat:'tempo',icon:'📅',title:'Dias entre datas',desc:'Veja quantos dias existem entre duas datas.',tags:'dias datas calendario prazo'},
  {id:'data-futura',cat:'tempo',icon:'➕',title:'Data daqui a X dias',desc:'Descubra a data após um período.',tags:'data futura dias prazo'},
  {id:'dia-semana',cat:'tempo',icon:'🗓️',title:'Dia da semana',desc:'Descubra em que dia da semana caiu uma data.',tags:'dia semana calendario'},
  {id:'horas',cat:'tempo',icon:'⌚',title:'Diferença entre horários',desc:'Calcule horas e minutos entre dois horários.',tags:'horas tempo horario intervalo'},
  {id:'somar-horas',cat:'trabalho',icon:'➕',title:'Somar horas',desc:'Some vários períodos de trabalho ou estudo.',tags:'somar horas jornada trabalho'},
  {id:'rescisao-clt',cat:'trabalho',icon:'📄',title:'Cálculo de rescisão CLT',desc:'Estime verbas rescisórias conforme o tipo de desligamento.',tags:'rescisão clt demissão aviso prévio férias 13 salario fgts'},
  {id:'clt-vs-pj',cat:'trabalho',icon:'⚖️',title:'Quanto cobrar como PJ?',desc:'Compare a remuneração PJ com uma proposta CLT e veja o equivalente anual.',tags:'pj pessoa juridica clt salario contratação freelancer imposto benefícios 13 férias fgts'},
  {id:'receita',cat:'cozinha',icon:'🥣',title:'Ajustar receita',desc:'Escalone ingredientes para mais ou menos pessoas.',tags:'receita porções ingredientes'},
  {id:'temperatura-cozinha',cat:'cozinha',icon:'🔥',title:'Temperatura de forno',desc:'Converta °C, °F e marcações comuns de forno.',tags:'forno receita cozinha temperatura'},
  {id:'custo-receita',cat:'cozinha',icon:'🧾',title:'Custo da receita',desc:'Some ingredientes e descubra custo por porção.',tags:'custo receita comida ingredientes'},
  {id:'por-quanto-vender',cat:'cozinha',icon:'🏷️',title:'Por quanto devo vender?',desc:'Descubra um preço de venda para doces, salgados e comidas.',tags:'preço venda doces salgados comida bolo brigadeiro marmita preço lucro margem'},
  {id:'churrasco',cat:'festas',icon:'🥩',title:'Quantidade para churrasco',desc:'Estime carne, acompanhamentos e bebidas.',tags:'churrasco carne convidados festa'},
  {id:'festa',cat:'festas',icon:'🥳',title:'Planejador de festa',desc:'Estime comida, bebida, bolo e descartáveis.',tags:'festa aniversario convidados salgados'},
  {id:'bolo',cat:'festas',icon:'🍰',title:'Quantidade de bolo',desc:'Estime o peso do bolo pela quantidade de convidados.',tags:'bolo aniversário convidados festa'},
  {id:'gelo',cat:'festas',icon:'🧊',title:'Quantidade de gelo',desc:'Estime gelo para eventos e bebidas.',tags:'gelo festa bebida'},
  {id:'lista-compras',cat:'outros',icon:'🛒',title:'Lista de compras',desc:'Monte e organize uma lista simples no navegador.',tags:'lista compras mercado supermercado'},
  {id:'dividir-pessoas',cat:'outros',icon:'👥',title:'Dividir qualquer valor',desc:'Distribua um valor igualmente entre pessoas.',tags:'dividir pessoas dinheiro grupo'},
];

const popular = ['porcentagem','combustivel-viagem','piso','tinta','placas-solares','posicao-solar','juros-compostos','idade'];

const input = (id,label,opts={}) => {
  const type = opts.type || 'number';
  const step = opts.step || 'any';
  const def = opts.value ?? '';
  const suffix = opts.suffix ? `<span class="suffix">${opts.suffix}</span>` : '';
  const prefix = opts.prefix ? `<span class="prefix">${opts.prefix}</span>` : '';
  return `<div class="field ${opts.full?'full':''}"><label for="${id}">${label}</label><div class="input-wrap">${prefix}<input id="${id}" type="${type}" ${type==='number'?`step="${step}"`:''} value="${esc(def)}" placeholder="${esc(opts.placeholder||'')}" ${opts.min!==undefined?`min="${opts.min}"`:''}>${suffix}</div>${opts.help?`<small>${opts.help}</small>`:''}</div>`;
};
const select = (id,label,items,value) => `<div class="field"><label for="${id}">${label}</label><select id="${id}">${items.map(([v,t])=>`<option value="${v}" ${v===value?'selected':''}>${t}</option>`).join('')}</select></div>`;
const panel = (form, output='<div class="result-box"><div class="result-label">Resultado</div><div class="result-main">—</div><p>Preencha os campos e clique em calcular.</p></div>') => `<div class="tool-layout"><section class="card panel"><h2>Preencha os dados</h2><div class="form-grid">${form}</div><div class="actions"><button class="btn primary" id="calcBtn">Calcular</button><button class="btn ghost" id="resetBtn">Limpar</button></div></section><section id="result">${output}</section></div>`;


function porQuantoVenderUI(){
  return `<div class="tool-layout"><section class="card panel">
    <h2>Por quanto devo vender?</h2>
    <div class="notice"><strong>Seu preço precisa pagar a conta.</strong> Esta ferramenta funciona como um pequeno consultor de negócio: calcula seu custo real, ponto de equilíbrio, margem, preços por estratégia e quanto você precisa vender para atingir uma meta.</div>
    <div class="form-grid">
      <div class="field full"><label for="sellProduct">O que você vende?</label><input id="sellProduct" placeholder="Ex.: bolo de chocolate, brigadeiro, coxinha, marmita..."></div>
      <div class="field"><label for="sellType">Tipo</label><select id="sellType"><option value="doce">Doce</option><option value="salgado">Salgado</option><option value="comida">Comida / refeição</option><option value="bebida">Bebida</option><option value="outro">Outro</option></select></div>
      <div class="field"><label for="sellCity">Cidade</label><input id="sellCity" value="Cuiabá" placeholder="Ex.: Cuiabá"></div>
      <div class="field"><label for="sellState">UF</label><input id="sellState" value="MT" maxlength="2" placeholder="MT"></div>
      <div class="field"><label for="sellQuantity">Unidades produzidas no lote</label><input id="sellQuantity" type="number" min="1" step="1" value="10"></div>
      <div class="field"><label for="sellCost">Ingredientes + preparo do lote</label><input id="sellCost" type="number" min="0" step="0.01" placeholder="Ex.: 80,00"><small>Quanto você realmente gasta para produzir o lote.</small></div>
      <div class="field"><label for="sellPackaging">Embalagem por unidade</label><input id="sellPackaging" type="number" min="0" step="0.01" value="0" placeholder="Ex.: 1,50"></div>
      <div class="field"><label for="sellOther">Outros gastos do lote</label><input id="sellOther" type="number" min="0" step="0.01" value="0" placeholder="Gás, energia, perdas..."></div>
      <div class="field"><label for="sellHours">Horas de trabalho no lote</label><input id="sellHours" type="number" min="0" step="0.25" value="0" placeholder="Ex.: 4"></div>
      <div class="field"><label for="sellHourly">Quanto vale sua hora de trabalho?</label><input id="sellHourly" type="number" min="0" step="0.01" value="0" placeholder="Ex.: 20,00"><small>Se não souber, deixe 0 para não incluir mão de obra.</small></div>
      <div class="field"><label for="sellFixed">Custos fixos por mês</label><input id="sellFixed" type="number" min="0" step="0.01" value="0" placeholder="Ex.: 500,00"><small>Aluguel, internet, equipamentos, contador etc.</small></div>
      <div class="field"><label for="sellMonthlyQty">Unidades que pretende vender por mês</label><input id="sellMonthlyQty" type="number" min="1" step="1" value="100" placeholder="Ex.: 100"></div>
      <div class="field"><label for="sellFees">Taxas sobre a venda (%)</label><input id="sellFees" type="number" min="0" max="100" step="0.1" value="0" placeholder="Ex.: 5"><small>Cartão, marketplace, comissão ou delivery.</small></div>
      <div class="field"><label for="sellTax">Impostos sobre a venda (%)</label><input id="sellTax" type="number" min="0" max="100" step="0.1" value="0" placeholder="Ex.: 6"></div>
      <div class="field"><label for="sellMargin">Lucro desejado (%)</label><input id="sellMargin" type="number" min="0" max="90" step="0.5" value="30" placeholder="Ex.: 30"><small>Percentual do preço de venda que você quer que sobre como lucro.</small></div>
      <div class="field"><label for="sellMarket">Preço praticado por concorrentes (opcional)</label><input id="sellMarket" type="number" min="0" step="0.01" value="0" placeholder="Ex.: 12,00"><small>Use apenas se você já pesquisou sua região.</small></div>
      <div class="field"><label for="sellGoal">Quanto quer ganhar por mês? (opcional)</label><input id="sellGoal" type="number" min="0" step="0.01" value="0" placeholder="Ex.: 2000,00"></div>
    </div>
    <div class="notice"><strong>Como usar:</strong> primeiro informe seus gastos. Depois, se quiser uma análise mais completa, preencha custos fixos, taxas, impostos, preço dos concorrentes e sua meta mensal.</div>
    <div class="actions"><button class="btn primary" type="button" id="sellCalcBtn">📊 Analisar meu preço</button><button class="btn ghost" type="button" id="sellResetBtn">Limpar</button></div>
  </section><section id="result"><div id="sellResult"><div class="result-box"><div class="result-label">Resultado</div><div class="result-main">—</div><p>Preencha os dados e clique em “Analisar meu preço”.</p></div></div></section></div>`;
}
function receitaCustoUI(){
  return `<div class="tool-layout"><section class="card panel">
    <h2>Ingredientes</h2>
    <div class="form-grid"><div class="field"><label for="servings">Porções</label><input id="servings" type="number" min="1" step="1" value="6"></div></div>
    <div class="notice"><strong>Adicione quantos ingredientes quiser.</strong><br>Informe o preço que você pagaria/estimaria para a quantidade usada na receita. Para preços de embalagens, use o valor proporcional à quantidade consumida.</div>
    <div id="recipeItems" class="dynamic-list"></div>
    <div class="actions"><button class="btn" type="button" id="addRecipeItem">＋ Adicionar ingrediente</button><button class="btn primary" type="button" id="calcBtn">Calcular custo</button><button class="btn ghost" type="button" id="resetBtn">Limpar</button></div>
    <hr class="sep">
    <h2>Receita pela internet</h2>
    <div class="form-grid"><div class="field full"><label for="recipeUrl">Endereço da receita</label><input id="recipeUrl" type="url" placeholder="https://exemplo.com/receita/bolo-de-chocolate"><small>A IA pode localizar e organizar os ingredientes da página.</small></div><div class="field"><label for="recipeCity">Cidade</label><input id="recipeCity" value="Cuiabá"></div><div class="field"><label for="recipeState">UF</label><input id="recipeState" value="MT" maxlength="2"></div></div>
    <div class="notice"><strong>Preços com IA:</strong> para estimar o custo dos ingredientes conforme cidade e UF, conecte sua própria API Key em <a href="#/conectar-api">✨ Usar minha IA</a>. Sem chave, o Resolvei ainda encontra e organiza os ingredientes.</div>
    <div class="actions"><button class="btn primary" type="button" id="analyzeRecipeBtn">✨ Analisar receita com IA</button></div>
    <div id="recipeAiStatus" class="notice">Sem análise ainda.</div>
  </section><section id="result"><div class="result-box"><div class="result-label">Resultado</div><div class="result-main">—</div><p>Adicione ingredientes e clique em calcular.</p></div></section></div>`;
}
function churrascoUI(){
  return `<div class="tool-layout"><section class="card panel"><h2>Perfil do churrasco</h2><div class="form-grid">
    ${input('adults','Adultos',{value:'10',step:'1',min:0})}
    ${input('kids','Crianças',{value:'3',step:'1',min:0})}
    ${input('hours','Duração',{suffix:'h',value:'4',step:'0.5',min:1})}
    ${input('drinkers','Pessoas que bebem álcool',{value:'6',step:'1',min:0,help:'Informe somente quem realmente beberá bebida alcoólica.'})}
    ${select('alcoholType','Bebida alcoólica principal',[['cerveja','Cerveja'],['vinho','Vinho'],['drinks','Drinks/coquetéis'],['misto','Misto']],'cerveja')}
    ${select('meatStyle','Perfil de compra',[['equilibrado','Equilibrado'],['economico','Mais econômico'],['carnes-nobres','Com mais carnes bovinas nobres']],'equilibrado')}
  </div><div class="actions"><button class="btn primary" id="calcBtn">Calcular churrasco</button><button class="btn ghost" id="resetBtn">Limpar</button></div>
  <div class="notice"><strong>Regra-base:</strong> o cálculo usa uma referência prática de consumo e depois distribui as carnes. Ajuste conforme o perfil dos convidados.</div>
  </section><section id="result"></section></div><section class="card panel recipe-section"><h2>🥩 Sugestões de carnes fáceis para churrasco</h2><div class="recipe-grid">${CHURRASCO_RECS.carnes.map(recipeCard).join('')}</div><h2>🥗 Acompanhamentos que combinam</h2><div class="recipe-grid">${CHURRASCO_RECS.acompanhamentos.map(recipeCard).join('')}</div></section>`;
}
const CHURRASCO_RECS={
  carnes:[
    {title:'Picanha',icon:'🥩',desc:'Clássica, fácil de acertar com sal e brasa forte.',ingredients:'1 peça de picanha · sal grosso a gosto',steps:'1. Mantenha a capa de gordura. 2. Corte em bifes altos ou asse a peça. 3. Tempere com sal grosso. 4. Sele em brasa forte e finalize até o ponto desejado.'},
    {title:'Fraldinha',icon:'🥩',desc:'Maciez, preparo simples e boa relação entre sabor e custo.',ingredients:'1 peça de fraldinha · sal · alho opcional',steps:'1. Limpe apenas excessos. 2. Tempere com sal. 3. Sele dos dois lados. 4. Finalize em fogo médio e fatie contra as fibras.'},
    {title:'Alcatra/contra-filé',icon:'🥩',desc:'Bifes fáceis, rápidos e versáteis.',ingredients:'Bifes de 2–3 cm · sal · pimenta opcional',steps:'1. Seque a carne. 2. Tempere pouco antes de ir à grelha. 3. Sele em brasa quente. 4. Descanse por 3–5 min antes de servir.'},
    {title:'Linguiça toscana',icon:'🌭',desc:'Prática, agrada muita gente e ajuda a diversificar.',ingredients:'Linguiça toscana · água opcional para cocção inicial',steps:'1. Coloque em calor médio. 2. Vire várias vezes. 3. Evite furar para preservar os sucos. 4. Doure no final em brasa mais forte.'},
    {title:'Asa/coxa de frango',icon:'🍗',desc:'Opção fácil e normalmente mais econômica.',ingredients:'Frango · sal · alho · limão · páprica opcional',steps:'1. Marine por 30–120 min. 2. Comece em calor médio. 3. Vire até cozinhar por completo. 4. Finalize para dourar a pele.'}
  ],
  acompanhamentos:[
    {title:'Vinagrete',icon:'🍅',desc:'Fresco e ácido para equilibrar as carnes.',ingredients:'Tomate · cebola · pimentão · cheiro-verde · vinagre · azeite · sal',steps:'1. Pique tudo pequeno. 2. Misture vinagre e azeite. 3. Tempere com sal. 4. Descanse 20 min na geladeira.'},
    {title:'Mandioca cozida',icon:'🥔',desc:'Barata, simples e combina muito com carne.',ingredients:'Mandioca · água · sal · manteiga opcional',steps:'1. Descasque e corte. 2. Cozinhe em água com sal até ficar macia. 3. Escorra. 4. Sirva pura ou com manteiga.'},
    {title:'Arroz branco',icon:'🍚',desc:'Neutro e fácil de preparar em grande quantidade.',ingredients:'Arroz · alho · óleo · sal · água',steps:'1. Refogue alho no óleo. 2. Junte o arroz. 3. Adicione água e sal. 4. Cozinhe tampado até secar e descanse 5 min.'},
    {title:'Maionese de batata',icon:'🥗',desc:'Acompanhamento clássico e simples.',ingredients:'Batata · cenoura · ervilha opcional · maionese · sal · cheiro-verde',steps:'1. Cozinhe batata e cenoura em cubos. 2. Esfrie completamente. 3. Misture com maionese. 4. Ajuste o sal e leve à geladeira.'},
    {title:'Farofa crocante',icon:'🌽',desc:'Barata, rende bem e absorve os sucos da carne.',ingredients:'Farinha de mandioca · manteiga/óleo · cebola · bacon opcional · sal',steps:'1. Doure cebola e bacon. 2. Junte farinha. 3. Mexa até dourar levemente. 4. Acerte o sal.'},
    {title:'Pão de alho',icon:'🥖',desc:'Fácil, rápido e ótimo para abrir o churrasco.',ingredients:'Pães · manteiga · alho · cheiro-verde · queijo opcional',steps:'1. Misture manteiga, alho e ervas. 2. Faça cortes no pão. 3. Recheie. 4. Leve à grelha até dourar.'}
  ]
};
function recipeCard(r){return `<article class="recipe-card card"><div class="recipe-title"><span>${r.icon}</span><div><h3>${esc(r.title)}</h3><p>${esc(r.desc)}</p></div></div><strong>Ingredientes</strong><p>${esc(r.ingredients)}</p><strong>Como preparar</strong><p>${esc(r.steps)}</p></article>`}

function festaUI(){
  return `<div class="tool-layout"><section class="card panel"><h2>Perfil da festa</h2><div class="form-grid">
    ${select('partyType','Tipo de festa',[['aniversario-infantil','Aniversário infantil'],['aniversario-adulto','Aniversário adulto'],['casamento','Casamento'],['firma','Festa da firma / confraternização'],['cha-bebe','Chá de bebê'],['cha-revelacao','Chá revelação'],['noivado','Noivado / noivado + jantar'],['formatura','Formatura'],['bodas','Bodas / aniversário de casamento'],['familiar','Comemoração familiar'],['junina','Festa junina'],['happy-hour','Happy hour'],['outro','Outra comemoração']],'aniversario-adulto')}
    ${input('age','Idade do aniversariante',{value:'30',step:'1',min:0,help:'Aparece e influencia o plano somente nos tipos de aniversário.'})}
    ${input('adults','Adultos',{value:'20',step:'1',min:0})}
    ${input('kids','Crianças',{value:'10',step:'1',min:0})}
    ${input('hours','Duração',{suffix:'h',value:'4',step:'0.5',min:1})}
    ${input('partyDrinkers','Pessoas que bebem álcool',{value:'8',step:'1',min:0})}
    ${select('partyAlcohol','Principal bebida alcoólica',[['none','Nenhuma'],['beer','Cerveja'],['wine','Vinho'],['drinks','Drinks'],['mixed','Misto']],'beer')}
    ${input('budgetPerPerson','Orçamento por pessoa (opcional)',{prefix:'R$',value:'0',help:'A IA usará como sinal de prioridade, não como orçamento garantido.'})}
  </div><div class="actions"><button class="btn primary" id="calcBtn">Gerar planejamento</button><button class="btn ghost" id="aiPartyBtn">✨ Refinar com IA</button><button class="btn ghost" id="resetBtn">Limpar</button></div>
  <div id="partyAiStatus" class="notice">O plano-base funciona sem IA. O botão “Refinar com IA” usa o backend para adaptar comidas, bebidas, utensílios e observações ao seu evento.</div>
  </section><section id="result"></section></div>`;
}
function rescisaoUI(){
  return panel(
    select('termination','Tipo de desligamento',[['sem-justa-causa','Dispensa sem justa causa'],['pedido-demissao','Pedido de demissão'],['acordo-484a','Acordo entre as partes (CLT art. 484-A)'],['justa-causa','Dispensa por justa causa'],['prazo-determinado','Término de contrato por prazo determinado']],'sem-justa-causa')+
    input('salary','Salário bruto mensal',{prefix:'R$',value:'5000',min:0})+
    input('admission','Data de admissão',{type:'date',value:'2023-01-10'})+
    input('terminationDate','Data de desligamento',{type:'date',value:new Date().toISOString().slice(0,10)})+
    input('workedDays','Dias trabalhados no mês da saída',{value:'15',step:'1',min:0,max:31,help:'Use os dias efetivamente trabalhados no último mês para o saldo de salário.'})+
    input('noticeDiscountDays','Dias de aviso não cumpridos no pedido de demissão',{value:'0',step:'1',min:0,max:30,help:'Use somente quando houver desconto do aviso não cumprido. A ferramenta não presume automaticamente esse desconto.'})+
    input('vacProMonths','Avos de férias do período atual',{value:'6',step:'1',min:0,max:12,help:'Meses/avos adquiridos no período em curso. Regra prática: mês ou fração de 15 dias ou mais conta como 1/12.'})+
    input('vacExpired','Períodos de férias vencidas simples',{value:'0',step:'1',min:0})+
    input('vacDouble','Períodos de férias vencidas em dobro',{value:'0',step:'1',min:0})+
    input('thirteenthAvos','Avos de 13º no ano da saída',{value:'9',step:'1',min:0,max:12})+
    input('fgtsBalance','Saldo de FGTS para a multa (opcional)',{prefix:'R$',value:'0',min:0,help:'Para 40%/20%, prefira informar o saldo-base do FGTS conforme extrato; sem isso o site faz uma aproximação.'})+
    input('otherDeductions','Outros descontos/adiantamentos',{prefix:'R$',value:'0',min:0})
  );
}
function cltVsPJUI(){
  return panel(
    input('cltGross','Salário CLT bruto mensal',{prefix:'R$',value:'8000',min:0})+
    input('cltDependents','Dependentes no IR',{value:'0',step:'1',min:0})+
    input('cltOtherDeductions','Outras deduções mensais de IR (opcional)',{prefix:'R$',value:'0',min:0})+
    input('cltBenefits','Benefícios CLT mensais',{prefix:'R$',value:'0',help:'VR/VA, plano de saúde e outros valores que você quer preservar na comparação.'})+
    input('pjTax','Taxa efetiva total do PJ sobre faturamento',{suffix:'%',value:'6',help:'Não existe uma alíquota única: depende de atividade, município, regime tributário, CNAE e estrutura. Confirme com contador.'})+
    input('pjFixed','Custos fixos mensais do PJ',{prefix:'R$',value:'300',help:'Contabilidade, sistema, certificado, banco, seguros etc.'})+
    input('pjBenefits','Benefícios/custos pessoais que o PJ precisará bancar',{prefix:'R$',value:'0',help:'Ex.: plano de saúde ou benefícios que desaparecerão com a CLT.'})+
    input('pjVacationDays','Dias sem faturamento por ano',{value:'30',step:'1',min:0,max:120,help:'Tempo que você pretende tirar sem receber de cliente.'})+
    input('pjRiskReserve','Reserva mensal para risco/intervalos entre contratos',{suffix:'%',value:'5',help:'Percentual sobre a base mensal para criar uma reserva de segurança.'})+
    input('pjRetirementReserve','Reserva previdenciária pessoal mensal',{suffix:'%',value:'8',help:'Reserva indicativa; adapte ao seu plano previdenciário.'})+
    input('pjProfitBuffer','Margem extra desejada no PJ',{suffix:'%',value:'0',help:'Ex.: 10% acima da equivalência calculada.'})
  );
}
function listaComprasUI(){
  return `<div class="tool-layout"><section class="card panel"><h2>Adicionar item</h2><div class="form-grid">
    <div class="field full"><label for="itemName">Nome do item</label><input id="itemName" placeholder="Ex.: Arroz"></div>
    <div class="field"><label for="itemQty">Quantidade</label><input id="itemQty" type="number" min="0" step="any" value="1"></div>
    <div class="field"><label for="itemUnit">Unidade</label><select id="itemUnit"><option>un.</option><option>kg</option><option>g</option><option>L</option><option>ml</option><option>pacote</option><option>caixa</option><option>garrafa</option><option>lata</option><option>maço</option><option>outro</option></select></div>
    <div class="field"><label for="itemPrice">Valor <span class="muted">(opcional)</span></label><input id="itemPrice" type="number" min="0" step="0.01" placeholder="0,00"></div>
  </div><div class="actions"><button class="btn primary" id="addItem">＋ Adicionar à lista</button><button class="btn ghost" id="clearList">Limpar tudo</button></div>
  <div class="notice">Os itens ficam salvos no navegador. Use “Copiar para WhatsApp” para gerar um texto organizado com emojis e total.</div><div id="list" class="shopping-list-box"></div></section><section class="card panel"><h2>📲 Texto para WhatsApp</h2><textarea id="shoppingText" class="whatsapp-text" rows="22" readonly></textarea><div class="actions"><button class="btn primary" id="copyShopping">📋 Copiar lista</button><button class="btn ghost" id="downloadShopping">⬇️ Baixar TXT</button></div><div id="shoppingTotal" class="shopping-total">Total: R$ 0,00</div></section></div>`;
}
function calcEscadaBlondel(alturaCm){
  const h=Math.max(1,Number(alturaCm)||0);
  const minN=Math.max(2,Math.ceil(h/18));
  const maxN=Math.max(minN,Math.floor(h/16));
  let candidates=[];
  for(let n=minN;n<=Math.min(maxN,40);n++){
    const e=h/n; const p=64-2*e; const blond=2*e+p;
    const score=Math.abs(e-17)+Math.abs(p-29.5)*0.35;
    if(p>=28 && p<=32) candidates.push({n,e,p,blond,score});
  }
  if(!candidates.length){
    for(let n=minN;n<=Math.min(maxN,40);n++){const e=h/n,p=64-2*e;candidates.push({n,e,p,blond:2*e+p,score:Math.abs(e-17)+Math.abs(p-29.5)});}
  }
  candidates.sort((a,b)=>a.score-b.score);
  const c=candidates[0]||{n:Math.round(h/17),e:h/Math.round(h/17),p:64-2*(h/Math.round(h/17)),blond:64};
  const ok=c.e>=16&&c.e<=18&&c.p>=28&&c.p<=32&&c.blond>=63&&c.blond<=65;
  let note=ok?'A solução encontrada fica na faixa de referência de conforto: espelho entre 16 e 18 cm, piso entre 28 e 32 cm e 2e+p entre 63 e 65 cm.': 'A altura informada não encontrou uma combinação integral dentro de todos os intervalos de referência. Revise a geometria e o espaço disponível no projeto.';
  note+=' A ABNT NBR 9050:2020 traz, para escadas, pisos de 28–32 cm, espelhos de 16–18 cm e 0,63–0,65 m para p+2e; rotas acessíveis têm requisitos adicionais. A NBR 9077 trata de saídas de emergência. Verifique a norma aplicável, legislação local e projeto profissional antes da execução.';
  return {altura:h,espelhos:c.n,espelho:c.e,piso:c.p,blondel:c.blond,note};
}
function getRecipeItemsFromDOM(){
  return [...document.querySelectorAll('#recipeItems .recipe-item')].map(el=>({
    name:el.querySelector('[data-name]')?.value?.trim()||'', qty:Number(el.querySelector('[data-qty]')?.value||0), unit:el.querySelector('[data-unit]')?.value||'un.', price:Number(el.querySelector('[data-price]')?.value||0)
  })).filter(x=>x.name);
}
function addRecipeItemRow(item={name:'',qty:1,unit:'g',price:0}){
  const box=document.getElementById('recipeItems'); if(!box)return;
  const div=document.createElement('div'); div.className='recipe-item card'; div.innerHTML=`<div class="form-grid"><div class="field"><label>Ingrediente</label><input data-name value="${esc(item.name)}" placeholder="Ex.: farinha de trigo"></div><div class="field"><label>Quantidade</label><input data-qty type="number" min="0" step="any" value="${item.qty}"></div><div class="field"><label>Unidade</label><select data-unit>${['g','kg','ml','L','un.','xícara','colher','pacote','lata','garrafa'].map(u=>`<option ${u===item.unit?'selected':''}>${u}</option>`).join('')}</select></div><div class="field"><label>Preço usado na receita</label><input data-price type="number" min="0" step="0.01" value="${item.price||''}" placeholder="0,00"></div></div><button class="btn ghost remove-recipe" type="button">Remover</button>`;
  div.querySelector('.remove-recipe').addEventListener('click',()=>div.remove()); box.appendChild(div);
}
function calcChurrasco(){
  const a=Math.max(0,val('adults')), k=Math.max(0,val('kids')), hours=Math.max(1,val('hours'));
  const drinkers=Math.min(a+k,Math.max(0,val('drinkers')));
  const style=document.getElementById('meatStyle')?.value||'equilibrado';
  const alcohol=document.getElementById('alcoholType')?.value||'cerveja';
  const basePerAdult=style==='economico'?0.42:style==='carnes-nobres'?0.55:0.50;
  const child=basePerAdult*0.50;
  const total=a*basePerAdult+k*child;
  const mix=style==='economico'
    ?[['Acém/contra-filé',0.24],['Fraldinha',0.20],['Linguiça toscana',0.24],['Frango',0.18],['Pernil suíno',0.14]]
    :style==='carnes-nobres'
      ?[['Picanha',0.32],['Contra-filé/alcatra',0.24],['Fraldinha',0.16],['Linguiça toscana',0.16],['Frango',0.12]]
      :[['Picanha/alcatra',0.25],['Fraldinha',0.20],['Contra-filé',0.18],['Linguiça toscana',0.20],['Frango',0.17]];
  const mixKg=mix.map(([name,ratio])=>[name,total*ratio]);
  const sausage=total*0.20, garlicBread=Math.max(1,Math.ceil((a+k)*0.8));
  const vinagreteKg=(a+k)*0.06, mandiocaKg=(a+k)*0.12, arrozKg=(a+k)*0.06, mayoKg=(a+k)*0.10, farofaKg=(a+k)*0.05;
  const cerveja=alcohol==='cerveja'||alcohol==='misto'?drinkers*(hours/4)*1.5:0;
  const vinhoGarrafas=alcohol==='vinho'||alcohol==='misto'?Math.ceil(drinkers*(hours/4)*0.25):0;
  const drinks=alcohol==='drinks'||alcohol==='misto'?Math.ceil(drinkers*(hours/4)*4):0;
  const alcoholTotal=alcohol==='cerveja'?cerveja:alcohol==='vinho'?vinhoGarrafas*0.75:alcohol==='drinks'?drinks*0.2:drinkers*(hours/4)*1.2;
  const agua=(a+k)*0.75*(hours/4), naoAlcoolicas=(a+k)*0.6*(hours/4);
  return {adultos:a,criancas:k,bebedores:drinkers,horas:hours,carneTotal:total,carneAdulto:basePerAdult,carneCrianca:child,mix,mixKg,sausage,garlicBread,vinagreteKg,mandiocaKg,arrozKg,mayoKg,farofaKg,alcohol,cerveja,vinhoGarrafas,drinks,alcoholTotal,agua,naoAlcoolicas};
}

const FESTA_PACKAGES={
  'aniversario-infantil':{
    foco:'Lanches fáceis, doces, bebidas sem álcool, entretenimento e segurança para circulação.',
    itens:[['🥪 Salgadinhos/mini-lanches',g=>`${Math.ceil(g*12)} unidades`],['🍬 Doces',g=>`${Math.ceil(g*6)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(1,g*0.12))} kg`],['🧃 Bebidas sem álcool',g=>`${fmt.format(g*0.8)} L`],['💧 Água',g=>`${fmt.format(g*0.5)} L`],['🪑 Cadeiras',g=>`${g} unidades`],['🥤 Copos',g=>`${Math.ceil(g*4)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*1.5)} unidades`],['🎈 Decoração/entretenimento','Planejar conforme tema e idade'],['🎁 Lembrancinhas','Opcional; ajustar ao orçamento']],
    extras:'Para crianças, vale priorizar alimentos de porção pequena, uma área livre para brincadeiras e itens de apoio ao tema da festa.'
  },
  'aniversario-adulto':{
    foco:'Comida de fácil serviço, bolo, bebidas e itens de mesa; idade ajuda a orientar o perfil do evento.',
    itens:[['🥪 Salgadinhos/mini-lanches',g=>`${Math.ceil(g*12)} unidades`],['🍬 Doces',g=>`${Math.ceil(g*4)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(1,g*0.12))} kg`],['🥤 Bebidas sem álcool',g=>`${fmt.format(g*0.7)} L`],['💧 Água',g=>`${fmt.format(g*0.6)} L`],['🪑 Cadeiras',g=>`${g} unidades`],['🥤 Copos',g=>`${Math.ceil(g*5)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*1.5)} unidades`],['🧊 Gelo','Dimensionar conforme bebidas']],
    extras:'A partir da idade, o plano muda de perfil infantil para adulto e pode receber bebidas alcoólicas somente quando apropriado ao evento e aos convidados.'
  },
  'casamento':{
    foco:'Serviço mais completo, apresentação, bebidas, sobremesas e logística.',
    itens:[['🥪 Coquetel/finger foods',g=>`${Math.ceil(g*14)} unidades`],['🍬 Doces finos',g=>`${Math.ceil(g*6)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(2,g*0.12))} kg`],['🥤 Bebidas sem álcool',g=>`${fmt.format(g*0.7)} L`],['💧 Água',g=>`${fmt.format(g*0.7)} L`],['🍷 Bebidas alcoólicas','Dimensionar por perfil de consumo'],['🧊 Gelo','Dimensionar para o serviço'],['🍽️ Pratos',g=>`${Math.ceil(g*3)} unidades`],['🥤 Copos/taças',g=>`${Math.ceil(g*6)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*2)} unidades`],['🪑 Cadeiras',g=>`${g} unidades`],['🧻 Guardanapos',g=>`${Math.ceil(g*3)} unidades`],['🪑 Mesas','Definir pelo layout e formato do serviço'],['🔊 Som/iluminação','Conforme local e programação']],
    extras:'Casamentos exigem planejamento de serviço, circulação, mobiliário, mesa posta e equipe; a IA pode detalhar o menu por estilo e horário.'
  },
  'firma':{
    foco:'Confraternização corporativa: serviço eficiente, bebidas variadas e logística de circulação.',
    itens:[['🥪 Finger foods/salgados',g=>`${Math.ceil(g*10)} unidades`],['🍰 Bolo/sobremesa',g=>`${fmt.format(Math.max(1,g*0.08))} kg`],['☕ Café/água',g=>`${fmt.format(g*0.7)} L`],['🥤 Refrigerantes/sucos',g=>`${fmt.format(g*0.8)} L`],['🍺 Bebida alcoólica','Somente conforme política e perfil do evento'],['🥤 Copos',g=>`${Math.ceil(g*4)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*1.5)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g)} unidades`],['🧻 Guardanapos',g=>`${Math.ceil(g*2)} unidades`],['🪑 Cadeiras',g=>`${g} unidades`],['🗑️ Lixeiras/sacos','Prever pontos de descarte']],
    extras:'Em eventos corporativos, considere horário, público interno/externo, duração e política da empresa para bebidas alcoólicas.'
  },
  'cha-bebe':{
    foco:'Evento diurno, leve, acolhedor e predominantemente sem álcool.',
    itens:[['🥪 Salgadinhos',g=>`${Math.ceil(g*10)} unidades`],['🍬 Doces',g=>`${Math.ceil(g*5)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(1,g*0.1))} kg`],['🧃 Bebidas sem álcool',g=>`${fmt.format(g*0.7)} L`],['💧 Água',g=>`${fmt.format(g*0.7)} L`],['🥤 Copos',g=>`${Math.ceil(g*4)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🎁 Lembrancinhas','Opcional'],['🎈 Decoração','Tema e cores do evento']],
    extras:'Prefira opções fáceis de comer em pé e bebidas sem álcool. Para gestantes e convidados com restrições alimentares, mantenha alternativas disponíveis.'
  },
  'cha-revelacao':{
    foco:'Momento curto e descontraído, com doces, salgados, bebidas sem álcool e decoração temática.',
    itens:[['🥪 Salgadinhos',g=>`${Math.ceil(g*10)} unidades`],['🍬 Doces',g=>`${Math.ceil(g*5)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(1,g*0.1))} kg`],['🧃 Bebidas sem álcool',g=>`${fmt.format(g*0.7)} L`],['💧 Água',g=>`${fmt.format(g*0.7)} L`],['🥤 Copos',g=>`${Math.ceil(g*4)} unidades`],['🎈 Decoração temática','Balões, mesa e elementos da revelação'],['📸 Registro','Planejar fotos/vídeo']],
    extras:'O roteiro e a decoração podem ser mais relevantes que uma refeição completa; concentre o orçamento no tema e no momento da revelação.'
  },
  'noivado':{
    foco:'Celebração íntima com apresentação, mesa posta e bebidas.',
    itens:[['🥪 Finger foods',g=>`${Math.ceil(g*12)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(1,g*0.1))} kg`],['🍬 Doces',g=>`${Math.ceil(g*5)} unidades`],['🍷 Vinho/espumante','Dimensionar pelo perfil de consumo'],['💧 Água',g=>`${fmt.format(g*0.7)} L`],['🥤 Copos/taças',g=>`${Math.ceil(g*5)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*1.5)} unidades`],['🌸 Flores/decoração','Conforme estilo']],
    extras:'Priorize um menu coerente com o horário e a ambientação. Para jantar completo, aumente a quantidade de pratos principais e acompanhamentos.'
  },
  'formatura':{
    foco:'Recepção, circulação, fotos, finger foods e bebidas para um público misto.',
    itens:[['🥪 Salgadinhos/finger foods',g=>`${Math.ceil(g*14)} unidades`],['🍬 Doces',g=>`${Math.ceil(g*5)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(1.5,g*0.1))} kg`],['🥤 Bebidas sem álcool',g=>`${fmt.format(g*0.7)} L`],['💧 Água',g=>`${fmt.format(g*0.7)} L`],['🍺 Bebidas alcoólicas','Conforme idade/perfil dos convidados e regras do local'],['🥤 Copos',g=>`${Math.ceil(g*6)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*2)} unidades`],['📸 Espaço para fotos','Prever circulação e iluminação'],['🔊 Som','Conforme programação']],
    extras:'Considere convidados de várias idades e destaque uma área de recepção/fotos. Bebidas alcoólicas devem ser planejadas somente para adultos.'
  },
  'bodas':{
    foco:'Comemoração de casal: menu elegante, mesa posta, sobremesa e bebidas.',
    itens:[['🥪 Canapés/finger foods',g=>`${Math.ceil(g*12)} unidades`],['🍰 Bolo',g=>`${fmt.format(Math.max(1,g*0.1))} kg`],['🍬 Doces',g=>`${Math.ceil(g*5)} unidades`],['🍷 Vinho/espumante','Dimensionar pelo perfil de consumo'],['💧 Água',g=>`${fmt.format(g*0.7)} L`],['🥤 Copos/taças',g=>`${Math.ceil(g*5)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*1.5)} unidades`],['🌸 Flores/decoração','Conforme tema da comemoração']],
    extras:'Pode funcionar como coquetel, jantar ou almoço. O planejamento deve mudar de acordo com o formato e o horário.'
  },
  'familiar':{
    foco:'Comida mais substancial e flexível, com opção de pratos de panela ou churrasco.',
    itens:[['🍚 Arroz',g=>`${fmt.format(g*0.06)} kg`],['🥗 Salada/maionese',g=>`${fmt.format(g*0.08)} kg`],['🥘 Prato principal','Escolher conforme cardápio'],['🥖 Farofa/pão',g=>`${fmt.format(g*0.05)} kg`],['🍰 Bolo/sobremesa',g=>`${fmt.format(Math.max(1,g*0.1))} kg`],['🥤 Bebidas sem álcool',g=>`${fmt.format(g*0.6)} L`],['💧 Água',g=>`${fmt.format(g*0.6)} L`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🥤 Copos',g=>`${Math.ceil(g*4)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*1.5)} unidades`]],
    extras:'Almoço em família costuma aproveitar melhor pratos de maior rendimento do que uma mesa baseada apenas em salgados.'
  },
  'junina':{
    foco:'Comidas típicas, bebidas quentes/frias, decoração e serviço simples.',
    itens:[['🌽 Milho/pamonha','Dimensionar por porções'],['🥣 Canjica/curau','Dimensionar por porções'],['🥜 Paçoca/pé-de-moleque',g=>`${Math.ceil(g*2)} unidades`],['🌭 Cachorro-quente',g=>`${Math.ceil(g*1)} unidades`],['🍰 Bolos típicos','Milho, fubá etc.'],['🥤 Bebidas sem álcool',g=>`${fmt.format(g*0.7)} L`],['☕ Bebidas quentes','Café, quentão sem álcool etc.'],['🎈 Decoração junina','Bandeirinhas, iluminação e mesa temática'],['🥤 Copos',g=>`${Math.ceil(g*4)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`]],
    extras:'O cardápio típico é parte central do evento; distribua opções doces e salgadas e dimensione o serviço para a duração.'
  },
  'happy-hour':{
    foco:'Petiscos, porções, bebidas e ambiente de conversa.',
    itens:[['🍢 Petiscos/porções',g=>`${Math.ceil(g*10)} unidades/porções equivalentes`],['🧀 Tábua de frios','Conforme formato'],['🍺 Cerveja/vinho/drinks','Dimensionar por bebedores'],['💧 Água',g=>`${fmt.format(g*0.7)} L`],['🥤 Bebidas sem álcool',g=>`${fmt.format(g*0.5)} L`],['🧊 Gelo','Dimensionar conforme bebida'],['🥤 Copos',g=>`${Math.ceil(g*6)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*1.5)} unidades`],['🧻 Guardanapos',g=>`${Math.ceil(g*2)} unidades`]],
    extras:'Para happy hour, a duração pesa bastante: mais horas significam mais bebida e mais consumo de petiscos.'
  },
  'outro':{
    foco:'Plano geral que pode ser refinado por IA conforme o objetivo do evento.',
    itens:[['🥪 Comidas de entrada',g=>`${Math.ceil(g*10)} unidades`],['🍰 Sobremesa/bolo',g=>`${fmt.format(Math.max(1,g*0.1))} kg`],['🥤 Bebidas sem álcool',g=>`${fmt.format(g*0.6)} L`],['💧 Água',g=>`${fmt.format(g*0.6)} L`],['🥤 Copos',g=>`${Math.ceil(g*4)} unidades`],['🍽️ Pratos',g=>`${Math.ceil(g*2)} unidades`],['🍴 Talheres',g=>`${Math.ceil(g*1.5)} unidades`],['🪑 Cadeiras',g=>`${g} unidades`]],
    extras:'Use o botão de IA para adaptar o plano ao tipo de evento, local, duração e orçamento.'
  }
};
function festaPackage(type,g){
  const pack=FESTA_PACKAGES[type]||FESTA_PACKAGES.outro;
  const itens=pack.itens.map(([name,qty])=>[name,typeof qty==='function'?qty(g):qty]);
  return {...pack,itens};
}
function calcFesta(){
  const type=document.getElementById('partyType')?.value||'outro';
  const a=Math.max(0,val('adults')), k=Math.max(0,val('kids')), g=a+k, h=Math.max(1,val('hours'));
  const drinkers=Math.min(g,Math.max(0,val('partyDrinkers'))), age=(type.startsWith('aniversario-')?Math.max(0,val('age')):null);
  const labels={
    'aniversario-infantil':'Aniversário infantil','aniversario-adulto':'Aniversário adulto','casamento':'Casamento','firma':'Festa da firma / confraternização','cha-bebe':'Chá de bebê','cha-revelacao':'Chá revelação','noivado':'Noivado','formatura':'Formatura','bodas':'Bodas','familiar':'Comemoração familiar','junina':'Festa junina','happy-hour':'Happy hour','outro':'Outra comemoração'};
  const pack=festaPackage(type,g);
  let base={salgados:Math.ceil(g*10),doces:Math.ceil(g*4),boloKg:Math.max(1,g*0.1),agua:g*0.5,naoAlcoolicas:g*0.6,cadeiras:g,copos:Math.ceil(g*4),pratos:Math.ceil(g*2),talheres:Math.ceil(g*1.5)};
  if(type==='aniversario-infantil')base={...base,salgados:Math.ceil(g*12),doces:Math.ceil(g*6),boloKg:Math.max(1,g*0.12),agua:g*0.5,naoAlcoolicas:g*0.8,copos:Math.ceil(g*4)};
  if(type==='aniversario-adulto')base={...base,salgados:Math.ceil(g*12),doces:Math.ceil(g*4),boloKg:Math.max(1,g*0.12),agua:g*0.6,naoAlcoolicas:g*0.7,copos:Math.ceil(g*5)};
  if(type==='casamento')base={...base,salgados:Math.ceil(g*14),doces:Math.ceil(g*6),boloKg:Math.max(2,g*0.12),agua:g*0.7,naoAlcoolicas:g*0.7,copos:Math.ceil(g*6),pratos:Math.ceil(g*3),talheres:Math.ceil(g*2)};
  if(type==='firma')base={...base,salgados:Math.ceil(g*10),doces:Math.ceil(g*2),boloKg:Math.max(1,g*0.08),agua:g*0.7,naoAlcoolicas:g*0.8,copos:Math.ceil(g*4),pratos:Math.ceil(g*1.5),talheres:Math.ceil(g)};
  if(type==='cha-bebe'||type==='cha-revelacao')base={...base,salgados:Math.ceil(g*10),doces:Math.ceil(g*5),boloKg:Math.max(1,g*0.1),agua:g*0.7,naoAlcoolicas:g*0.7,copos:Math.ceil(g*4)};
  if(type==='noivado'||type==='bodas')base={...base,salgados:Math.ceil(g*12),doces:Math.ceil(g*5),boloKg:Math.max(1,g*0.1),agua:g*0.7,naoAlcoolicas:g*0.6,copos:Math.ceil(g*5)};
  if(type==='formatura')base={...base,salgados:Math.ceil(g*14),doces:Math.ceil(g*5),boloKg:Math.max(1.5,g*0.1),agua:g*0.7,naoAlcoolicas:g*0.7,copos:Math.ceil(g*6),pratos:Math.ceil(g*2),talheres:Math.ceil(g*2)};
  if(type==='familiar')base={...base,salgados:Math.ceil(g*8),doces:Math.ceil(g*3),boloKg:Math.max(1,g*0.1)};
  if(type==='junina')base={...base,salgados:Math.ceil(g*6),doces:Math.ceil(g*5),boloKg:Math.max(1,g*0.08),agua:g*0.5,naoAlcoolicas:g*0.7,copos:Math.ceil(g*4)};
  if(type==='happy-hour')base={...base,salgados:Math.ceil(g*10),doces:Math.ceil(g*1),boloKg:0,agua:g*0.7,naoAlcoolicas:g*0.5,copos:Math.ceil(g*6),pratos:Math.ceil(g*1.5)};
  let note=pack.extras;
  if(type==='aniversario-adulto'&&age!==null&&age<18)note='Como o aniversariante é menor de 18 anos, o plano prioriza opções sem álcool e a festa deve ser organizada de acordo com a legislação e responsabilidade dos adultos presentes. '+pack.extras;
  else if(type==='aniversario-adulto'&&age!==null)note=`Aniversariante com ${age} anos: ${pack.extras}`;
  const alcohol=document.getElementById('partyAlcohol')?.value||'none';
  const beerL=(alcohol==='beer'||alcohol==='mixed')?drinkers*(h/4)*1.5:0;
  const wineBottles=(alcohol==='wine'||alcohol==='mixed')?Math.ceil(drinkers*(h/4)*0.25):0;
  const drinkDoses=(alcohol==='drinks'||alcohol==='mixed')?Math.ceil(drinkers*(h/4)*4):0;
  return {...base,guests:g,adultos:a,criancas:k,bebedores:drinkers,horas:h,typeLabel:labels[type]||type,age,package:pack,note,alcohol,beerL,wineBottles,drinkDoses};
}
function calcRescisao(){
  const salary=Math.max(0,val('salary')); const type=document.getElementById('termination')?.value||'sem-justa-causa';
  const admRaw=document.getElementById('admission')?.value||'', outRaw=document.getElementById('terminationDate')?.value||'';
  const adm=admRaw?new Date(admRaw+'T00:00:00'):null, outDate=outRaw?new Date(outRaw+'T00:00:00'):null;
  const worked=Math.max(0,Math.min(31,val('workedDays'))), noticeDiscountDays=Math.max(0,Math.min(30,val('noticeDiscountDays'))), vacAvos=Math.max(0,Math.min(12,val('vacProMonths'))), vacExpired=Math.max(0,val('vacExpired')), vacDouble=Math.max(0,val('vacDouble')), thirteenth=Math.max(0,Math.min(12,val('thirteenthAvos'))), fgts=val('fgtsBalance'), other=Math.max(0,val('otherDeductions'));
  const ms=salary/30, balance=ms*worked;
  const daysService=adm&&outDate&&!Number.isNaN(outDate-adm)?Math.max(0,Math.floor((outDate-adm)/86400000)):0;
  const completedYears=Math.floor(daysService/365.2425);
  const noticeDays=(type==='sem-justa-causa'||type==='acordo-484a')?Math.min(90,30+Math.max(0,completedYears-1)*3):0;
  const noticeValue=type==='sem-justa-causa'?ms*noticeDays:(type==='acordo-484a'?ms*noticeDays*0.5:0);
  const vacationProportional=salary*(vacAvos/12)*(1+1/3), vacationExpiredSimple=salary*(1+1/3)*vacExpired, vacationExpiredDouble=salary*2*(1+1/3)*vacDouble;
  const thirteenthValue=salary*(thirteenth/12);
  let fgtsFine=0, rows=[];
  let positive=balance+vacationProportional+vacationExpiredSimple+vacationExpiredDouble+thirteenthValue+noticeValue;
  const baseFgts=fgts>0?fgts:salary*0.08*(Math.max(1,Math.round(daysService/30))+thirteenth/12);
  if(type==='sem-justa-causa'){
    fgtsFine=baseFgts*0.40;
    rows=[['Saldo de salário',money(balance)],['Aviso prévio indenizado (estimado)',money(noticeValue)],['Férias proporcionais + 1/3',money(vacationProportional)],['Férias vencidas simples + 1/3',money(vacationExpiredSimple)],['Férias vencidas em dobro + 1/3',money(vacationExpiredDouble)],['13º proporcional',money(thirteenthValue)],['Multa rescisória do FGTS — 40%',money(fgtsFine)],['Outros descontos',`- ${money(other)}`]];
  } else if(type==='pedido-demissao'){
    const noticeDiscount=ms*noticeDiscountDays;
    rows=[['Saldo de salário',money(balance)],['Desconto de aviso não cumprido',noticeDiscount?`- ${money(noticeDiscount)}`:money(0)],['Férias proporcionais + 1/3',money(vacationProportional)],['Férias vencidas simples + 1/3',money(vacationExpiredSimple)],['Férias vencidas em dobro + 1/3',money(vacationExpiredDouble)],['13º proporcional',money(thirteenthValue)],['Outros descontos',`- ${money(other)}`]];
    positive=balance+vacationProportional+vacationExpiredSimple+vacationExpiredDouble+thirteenthValue-noticeDiscount;
  } else if(type==='acordo-484a'){
    fgtsFine=baseFgts*0.20;
    rows=[['Saldo de salário',money(balance)],['50% do aviso prévio indenizado',money(noticeValue)],['Férias proporcionais + 1/3',money(vacationProportional)],['Férias vencidas simples + 1/3',money(vacationExpiredSimple)],['Férias vencidas em dobro + 1/3',money(vacationExpiredDouble)],['13º proporcional',money(thirteenthValue)],['Multa do FGTS — 20%',money(fgtsFine)],['Outros descontos',`- ${money(other)}`]];
  } else if(type==='justa-causa'){
    rows=[['Saldo de salário',money(balance)],['Férias vencidas simples + 1/3',money(vacationExpiredSimple)],['Férias vencidas em dobro + 1/3',money(vacationExpiredDouble)],['Outros descontos',`- ${money(other)}`]];
  } else {
    rows=[['Saldo de salário',money(balance)],['Férias proporcionais + 1/3',money(vacationProportional)],['Férias vencidas simples + 1/3',money(vacationExpiredSimple)],['Férias vencidas em dobro + 1/3',money(vacationExpiredDouble)],['13º proporcional',money(thirteenthValue)],['Outros descontos',`- ${money(other)}`]];
  }
  positive=positive+fgtsFine;
  if(type==='pedido-demissao')positive=balance+vacationProportional+vacationExpiredSimple+vacationExpiredDouble+thirteenthValue-(ms*noticeDiscountDays);
  else if(type==='justa-causa')positive=balance+vacationExpiredSimple+vacationExpiredDouble;
  const total=Math.max(0,positive-other);
  const sourceLinks=`Fontes oficiais: <a href="https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm" target="_blank" rel="noopener">CLT</a> · <a href="https://planalto.gov.br/ccivil_03/leis/l8036compilada.htm" target="_blank" rel="noopener">FGTS</a> · <a href="https://planalto.gov.br/ccivil_03/leis/l4090.htm" target="_blank" rel="noopener">13º salário</a>.`;
  let note=`Estimativa para trabalhador CLT, com referência às regras vigentes em 2026. O aviso prévio proporcional é calculado pela Lei 12.506/2011, quando aplicável. Em dispensa sem justa causa, a multa do FGTS é, em regra, 40% da base legal; no acordo do art. 484-A, o aviso indenizado e a indenização do FGTS são devidos pela metade. O pagamento das verbas rescisórias deve observar o prazo legal de 10 dias corridos após o término do contrato. ${sourceLinks}`;
  if(type==='acordo-484a')note+=` Nesse acordo, a movimentação do FGTS é limitada a 80% e não há seguro-desemprego.`;
  if(type==='pedido-demissao')note+=` No pedido de demissão, o aviso prévio não cumprido pode ser descontado; informe os dias no campo específico para estimar esse abatimento.`;
  if(type==='justa-causa')note+=` Na justa causa, as verbas devidas dependem do enquadramento concreto; esta ferramenta mostra apenas parcelas mais comuns do cálculo simplificado.`;
  if(fgts<=0 && (type==='sem-justa-causa'||type==='acordo-484a'))note+=` A multa do FGTS foi aproximada porque você não informou o saldo/base do extrato.`;
  return {total,rows,note,noticeDays,completedYears,baseFgts,fgtsFine};
}
function calcCLTVsPJ(){
  const gross=Math.max(0,val('cltGross')), dep=Math.max(0,val('cltDependents')), otherDed=Math.max(0,val('cltOtherDeductions')), benefits=Math.max(0,val('cltBenefits'));
  const tax=Math.min(0.99,Math.max(0,val('pjTax'))/100), fixed=Math.max(0,val('pjFixed')), pjBenefits=Math.max(0,val('pjBenefits'));
  const vacationDays=Math.min(120,Math.max(0,val('pjVacationDays'))), risk=Math.max(0,val('pjRiskReserve'))/100, previdReserve=Math.max(0,val('pjRetirementReserve'))/100, profitBuffer=Math.max(0,val('pjProfitBuffer'))/100;
  const billableMonths=Math.max(1,12-Math.ceil(vacationDays/30));
  const inss=calcINSS2026(gross), ir=calcIRPF2026(gross,inss,dep,otherDed), cltNet=Math.max(0,gross-inss-ir.tax);
  const thirteenthReserve=gross/12, vacationReserve=(gross*4/3)/12, fgtsReserve=(gross*13*0.08)/12;
  const riskReserve=cltNet*risk, retirementReserve=gross*previdReserve;
  const benefitsReserve=benefits+pjBenefits;
  const equivalenceMonthlyBeforePJTax=cltNet+thirteenthReserve+vacationReserve+fgtsReserve+benefitsReserve+riskReserve+retirementReserve+fixed;
  const pjGrossMonthlyBilling=(equivalenceMonthlyBeforePJTax/(1-tax));
  const pjGrossAnnual=pjGrossMonthlyBilling*billableMonths*(1+profitBuffer);
  const pjMonthly=pjGrossAnnual/billableMonths;
  const cltAnnualValue=cltNet*12+gross+gross/3*0.75+benefits*12;
  const note=`A equivalência usa o líquido CLT como ponto de partida e cria reservas para 13º, férias + 1/3, equivalente ao FGTS, benefícios, intervalos sem faturamento, previdência e custos do PJ. A taxa do PJ é uma premissa: o custo tributário real depende da atividade, regime, município e estrutura da empresa e deve ser validado com contador. O resultado não é uma recomendação jurídica ou tributária.`;
  return {cltNet,cltAnnualValue,inss,ir:ir.tax,irBase:ir.base,tax:tax*100,fixed,billableMonths,pjMonthly, pjAnnual:pjGrossAnnual, equivalenceMonthlyBeforePJTax, thirteenthReserve,vacationReserve,fgtsReserve,benefitsReserve,riskReserve,retirementReserve,note};
}
function calcINSS2026(s){let remaining=Math.max(0,s),prev=0,total=0;const bands=[[1621,0.075],[2902.84,0.09],[4354.27,0.12],[8475.55,0.14]]; for(const [limit,rate] of bands){const chunk=Math.max(0,Math.min(remaining,limit-prev)); total+=chunk*rate; remaining-=chunk; prev=limit; if(remaining<=0)break;} return Math.min(total,8475.55*0.14);}
function calcIRPF2026(gross,inss,dep,other){const simplified=607.20; const deductions=Math.max(simplified,inss+dep*189.59+other); const base=Math.max(0,gross-deductions); let rate=0,ded=0;if(base<=2428.80){rate=0;}else if(base<=2826.65){rate=.075;ded=182.16;}else if(base<=3751.05){rate=.15;ded=394.16;}else if(base<=4664.68){rate=.225;ded=675.49;}else{rate=.275;ded=908.73;} let tax=Math.max(0,base*rate-ded); if(gross<=5000)tax=0;else if(gross<=7350)tax=Math.max(0,tax-(978.62-0.133145*gross)); return {tax,base,netTaxedBase:base};}


const SOLAR_DEFAULT_PRICES = {
  panel: 750,
  inverter: 4800,
  mounting: 130,
  dcCableM: 6,
  acCableM: 8,
  dcProtection: 520,
  acProtection: 390,
  grounding: 450,
  mc4: 28,
  conduit: 12,
  labels: 70,
  monitoring: 280,
  engineering: 1200,
  labor: 1600,
};
const SOLAR_INVERTERS=[1.5,2,3,4,5,6,8,10,12,15,20,25,30,40,50];
const solarInverterSuggest = kWp => SOLAR_INVERTERS.find(x=>x>=kWp/1.2) || Math.ceil(kWp/1.2);
const solarBearingName = b => { const dirs=['N','NE','L','SE','S','SO','O','NO']; const i=Math.round((((Number(b)||0)%360+360)%360)/45)%8; return dirs[i]; };
const normalizeBearing = b => ((Number(b)||0)%360+360)%360;
function solarPrice(n, fallback){ return Number.isFinite(Number(n))&&Number(n)>0?Number(n):fallback; }
function solarPriceField(id,label,value,help='') { return input(id,label,{prefix:'R$',value,step:'0.01',help}); }
function formatMonths(m){ const n=Math.max(0,Math.ceil(Number(m)||0)); const y=Math.floor(n/12),mo=n%12; return y?`${y} ano${y>1?'s':''}${mo?` e ${mo} mês${mo>1?'es':''}`:''}`:`${n} mês${n!==1?'es':''}`; }


function solarCalculatorUI(){
  return `<div class="tool-layout solar-tool-layout"><section class="card panel solar-main-panel">
    <h2>☀️ Dimensionamento fotovoltaico + posicionamento</h2>
    <div class="notice"><strong>Agora é uma única ferramenta.</strong> O Resolvei dimensiona a quantidade de módulos e, usando uma imagem superior do imóvel, permite desenhar os planos de telhado, obstáculos e uma escala para testar automaticamente a posição dos módulos. A etapa visual é preliminar e não substitui levantamento, projeto ou análise estrutural.</div>

    <h3 class="subhead">⚡ 1. Consumo e sistema</h3>
    <div class="form-grid">
      ${input('solarConsumption','Consumo médio mensal',{suffix:'kWh/mês',value:'500',help:'Prefira a média dos últimos 12 meses.'})}
      ${input('solarTariff','Tarifa efetiva',{prefix:'R$',value:'0.95',step:'0.01',help:'Valor usado somente na simulação financeira.'})}
      ${input('solarPSH','Horas de sol pico',{suffix:'h/dia',value:'5',step:'0.1',help:'O botão de dados solares pode substituir este valor.'})}
      ${input('solarPR','Performance global',{suffix:'%',value:'80',step:'1',help:'Perdas globais estimadas do sistema.'})}
      ${input('solarPanelPower','Potência do módulo',{suffix:'Wp',value:'550',step:'5'})}
      ${input('solarPanelArea','Área do módulo',{suffix:'m²',value:'2.6',step:'0.01'})}
      ${input('solarPanelLength','Comprimento do módulo',{suffix:'m',value:'2.28',step:'0.01',help:'Use a medida real do fabricante.'})}
      ${input('solarPanelWidth','Largura do módulo',{suffix:'m',value:'1.13',step:'0.01',help:'Use a medida real do fabricante.'})}
      ${input('solarPanelGap','Espaço entre módulos',{suffix:'m',value:'0.02',step:'0.01'})}
      ${input('solarEdgeClearance','Afastamento das bordas',{suffix:'m',value:'0.20',step:'0.05',help:'Margem geométrica preliminar. Verifique a estrutura e recomendações do fabricante.'})}
      ${input('solarRoofArea','Área útil disponível',{suffix:'m²',value:'30',step:'0.1',help:'Use uma estimativa; a área desenhada na imagem pode refinar a análise.'})}
      ${select('solarPhase','Ligação elétrica',[['monofasico','Monofásica'],['bifasico','Bifásica'],['trifasico','Trifásica']],'bifasico')}
      ${input('solarConsumptionCoverage','Cobertura alvo',{suffix:'%',value:'100',step:'1'})}
      ${input('solarEconomyFactor','Fator de economia',{suffix:'%',value:'90',step:'1'})}
      ${input('solarExtraCost','Outros custos',{prefix:'R$',value:'0',step:'0.01'})}
    </div>

    <h3 class="subhead">📍 2. Endereço e dados solares</h3>
    <div class="form-grid">
      ${input('solarCep','CEP',{value:'',placeholder:'78000-000',help:'Digite o CEP para preencher rua, bairro, cidade e UF automaticamente.'})}
      ${input('solarAddress','Rua / número',{value:'',placeholder:'Ex.: Rua das Flores, 100'})}
      ${input('solarNeighborhood','Bairro',{value:''})}
      ${input('solarCity','Cidade',{value:'Cuiabá'})}
      ${input('solarState','UF',{value:'MT',maxlength:'2'})}
    </div>
    <div class="actions">
      <button class="btn" id="solarCepBtn" type="button">📍 Preencher pelo CEP</button>
      <button class="btn" id="solarAddressBtn" type="button">🧭 Localizar endereço</button>
      <button class="btn" id="solarResourceBtn" type="button">☀️ Atualizar dados solares</button>
      <button class="btn" id="solarPricesBtn" type="button">💰 Atualizar preços</button>
    </div>
    <div id="solarResourceStatus" class="notice">Informe o endereço e, quando necessário, use “Localizar endereço”.</div>

    <hr class="sep">
    <h3 class="subhead">💰 3. Preços de referência — editáveis</h3>
    <div class="form-grid solar-price-grid">
      ${solarPriceField('pricePanel','Módulo fotovoltaico (un.)',SOLAR_DEFAULT_PRICES.panel,'Valor de referência.') }
      ${solarPriceField('priceInverter','Inversor (un.)',SOLAR_DEFAULT_PRICES.inverter)}
      ${solarPriceField('priceMounting','Estrutura por módulo',SOLAR_DEFAULT_PRICES.mounting)}
      ${solarPriceField('priceDcCable','Cabo solar por metro',SOLAR_DEFAULT_PRICES.dcCableM)}
      ${solarPriceField('priceAcCable','Cabo AC por metro',SOLAR_DEFAULT_PRICES.acCableM)}
      ${solarPriceField('priceDcProtection','Proteção DC/string box',SOLAR_DEFAULT_PRICES.dcProtection)}
      ${solarPriceField('priceAcProtection','Proteção AC/quadro',SOLAR_DEFAULT_PRICES.acProtection)}
      ${solarPriceField('priceGrounding','Aterramento/equipotencialização',SOLAR_DEFAULT_PRICES.grounding)}
      ${solarPriceField('priceMc4','Conectores MC4 — par',SOLAR_DEFAULT_PRICES.mc4)}
      ${solarPriceField('priceConduit','Eletroduto/eletrocalha por metro',SOLAR_DEFAULT_PRICES.conduit)}
      ${solarPriceField('priceLabels','Identificação/placas',SOLAR_DEFAULT_PRICES.labels)}
      ${solarPriceField('priceMonitoring','Monitoramento/Wi-Fi',SOLAR_DEFAULT_PRICES.monitoring)}
      ${solarPriceField('priceEngineering','Projeto + engenharia/homologação',SOLAR_DEFAULT_PRICES.engineering)}
      ${solarPriceField('priceLabor','Mão de obra',SOLAR_DEFAULT_PRICES.labor)}
    </div>

    <hr class="sep">
    <h3 class="subhead">🗺️ 4. Imagem superior do imóvel</h3>
    <div class="notice">Use uma imagem realmente superior (satélite, drone, ortofoto ou implantação). Quanto mais perpendicular a imagem estiver ao terreno, melhor. Caso exista uma seta Norte, mantenha-a visível.</div>
    <div class="field full"><label for="solarMapImage">Imagem do imóvel</label><input id="solarMapImage" type="file" accept="image/*"><small>O arquivo é carregado no navegador. A imagem só é enviada ao servidor quando você escolher a análise por IA.</small></div>

    <div class="solar-mark-toolbar">
      <button class="btn solar-mode active" id="solarRoofModeBtn" type="button">⌂ Marcar plano de telhado</button>
      <button class="btn solar-mode" id="solarObstacleModeBtn" type="button">▴ Marcar obstáculo</button>
      <button class="btn solar-mode" id="solarCalibrateBtn" type="button">📏 Calibrar escala</button>
      <button class="btn" id="solarFinishMarkBtn" type="button">✓ Concluir marcação</button>
      <button class="btn" id="solarUndoBtn" type="button">↶ Desfazer</button>
      <button class="btn ghost" id="solarClearMarksBtn" type="button">Limpar marcações</button>
    </div>

    <div class="form-grid solar-mark-fields">
      ${input('solarMarkRoofAzimuth','Azimute do plano de telhado',{suffix:'°',value:'0',step:'1',help:'0° Norte · 90° Leste · 180° Sul · 270° Oeste.'})}
      ${input('solarMarkRoofTilt','Inclinação do plano',{suffix:'°',value:'15',step:'1'})}
      ${input('solarMarkRoofHeight','Altura do plano',{suffix:'m',value:'3',step:'0.1',help:'Altura aproximada do telhado em relação ao piso/terreno.'})}
      ${input('solarObstacleHeight','Altura do obstáculo',{suffix:'m',value:'1',step:'0.1',help:'Use altura relativa acima do plano dos módulos quando possível.'})}
      ${input('solarShadowAltitude','Ângulo solar mínimo usado na sombra',{suffix:'°',value:'20',step:'1',help:'Modelo conservador: quanto menor este ângulo, maior a zona excluída ao redor do obstáculo.'})}
      ${input('solarKnownDistance','Distância conhecida para escala',{suffix:'m',value:'10',step:'0.1',help:'Informe uma distância real que você consiga identificar na imagem; depois clique em “Calibrar escala”.'})}
    </div>

    <div id="solarImageStatus" class="notice">1) Envie a imagem. 2) Marque os planos de telhado. 3) Marque obstáculos. 4) Calibre a escala. 5) Calcule o posicionamento.</div>
    <div class="solar-canvas-wrap" id="solarCanvasWrap">
      <img id="solarMapPreview" alt="Imagem superior do imóvel">
      <canvas id="solarOverlay"></canvas>
    </div>
    <div class="solar-legend">
      <span><i class="legend-swatch roof"></i> Plano de telhado</span>
      <span><i class="legend-swatch obstacle"></i> Obstáculo / barreira</span>
      <span><i class="legend-swatch panel"></i> Módulo proposto</span>
      <span><i class="legend-swatch shadow"></i> Zona conservadora de sombra</span>
    </div>
    <div class="actions">
      <button class="btn primary" id="solarAutoLayoutBtn" type="button">▦ Calcular posição dos módulos</button>
      <button class="btn" id="solarAiImageBtn" type="button">✨ Sugerir áreas com IA</button>
      <button class="btn" id="solarLayoutClearBtn" type="button">Limpar somente layout</button>
    </div>
    <div id="solarLayoutResult"></div>

    <div class="notice"><strong>Como interpretar:</strong> o Resolvei procura caber a quantidade de módulos calculada nos planos marcados, respeitando orientação, inclinação, bordas, dimensão física do módulo e zonas de sombra aproximadas dos obstáculos. Em projeto real, ainda precisam ser verificados espaçamentos técnicos, acesso, carga de vento, fixação, estrutura, strings, tensão/corrente e requisitos da distribuidora.</div>

    <div class="actions"><button class="btn primary" id="calcBtn">Calcular sistema completo</button><button class="btn ghost" id="resetBtn">Limpar</button></div>
  </section><section id="result"></section></div>

  <section class="card panel solar-path-section"><h2>☀️ Trajetória aparente do Sol</h2><canvas id="solarPathCanvas" width="900" height="340"></canvas><div class="note">Visualização aproximada da trajetória solar para a latitude localizada. A análise de sombra do imóvel usa os obstáculos que você marcou na imagem.</div></section>`;
}

function positionSolarUI(){
  return solarCalculatorUI();
}

function solarConfigFromDOM(){
  const panelLength=Math.max(.2,val('solarPanelLength')||2.28);
  const panelWidth=Math.max(.2,val('solarPanelWidth')||1.13);
  return {
    consumption:Math.max(0,val('solarConsumption')),
    tariff:Math.max(0,val('solarTariff')),
    psh:Math.max(1,val('solarPSH')),
    pr:Math.min(1,Math.max(.1,val('solarPR')/100)),
    panelW:Math.max(100,val('solarPanelPower')),
    panelLength,panelWidth,panelArea:panelLength*panelWidth,
    panelGap:Math.max(0,val('solarPanelGap')),
    edgeClearance:Math.max(0,val('solarEdgeClearance')),
    shadowAltitude:Math.max(5,Math.min(80,val('solarShadowAltitude')||20)),
    roofArea:Math.max(0,val('solarRoofArea')),
    coverage:Math.min(2,Math.max(.1,val('solarConsumptionCoverage')/100)),
    economyFactor:Math.min(1,Math.max(.1,val('solarEconomyFactor')/100)),
    extra:Math.max(0,val('solarExtraCost')),
    phase:document.getElementById('solarPhase')?.value||'bifasico',
  };
}

function calcSolarLocal(){
  const c=solarConfigFromDOM();
  const panelKW=c.panelW/1000;
  const requiredKwh=Math.max(0,c.consumption*c.coverage);
  const panelMonthly= c.psh*30*c.pr*panelKW;
  const panels=panelMonthly?Math.ceil(requiredKwh/panelMonthly):0;
  const dcKW=panels*panelKW;
  const inverter=solarInverterSuggest(dcKW);
  const genMonthly=panels*panelMonthly;
  const annual=genMonthly*12;
  const price={
    panel:solarPrice(val('pricePanel'),SOLAR_DEFAULT_PRICES.panel),
    inverter:solarPrice(val('priceInverter'),SOLAR_DEFAULT_PRICES.inverter),
    mounting:solarPrice(val('priceMounting'),SOLAR_DEFAULT_PRICES.mounting),
    dcCableM:solarPrice(val('priceDcCable'),SOLAR_DEFAULT_PRICES.dcCableM),
    acCableM:solarPrice(val('priceAcCable'),SOLAR_DEFAULT_PRICES.acCableM),
    dcProtection:solarPrice(val('priceDcProtection'),SOLAR_DEFAULT_PRICES.dcProtection),
    acProtection:solarPrice(val('priceAcProtection'),SOLAR_DEFAULT_PRICES.acProtection),
    grounding:solarPrice(val('priceGrounding'),SOLAR_DEFAULT_PRICES.grounding),
    mc4:solarPrice(val('priceMc4'),SOLAR_DEFAULT_PRICES.mc4),
    conduit:solarPrice(val('priceConduit'),SOLAR_DEFAULT_PRICES.conduit),
    labels:solarPrice(val('priceLabels'),SOLAR_DEFAULT_PRICES.labels),
    monitoring:solarPrice(val('priceMonitoring'),SOLAR_DEFAULT_PRICES.monitoring),
    engineering:solarPrice(val('priceEngineering'),SOLAR_DEFAULT_PRICES.engineering),
    labor:solarPrice(val('priceLabor'),SOLAR_DEFAULT_PRICES.labor),
  };
  const dcCableM=panels*12, acCableM=Math.max(15,panels*2), mc4Pairs=Math.max(2,Math.ceil(panels/2));
  const items=[
    ['Módulos fotovoltaicos',panels,'un.',panels*price.panel],
    [`Inversor ${num(inverter)} kW`,1,'un.',price.inverter],
    ['Estrutura de fixação',panels,'un.',panels*price.mounting],
    ['Cabo solar DC',dcCableM,'m',dcCableM*price.dcCableM],
    ['Cabo AC',acCableM,'m',acCableM*price.acCableM],
    ['Proteção DC / string box',1,'conj.',price.dcProtection],
    ['Proteção AC / quadro',1,'conj.',price.acProtection],
    ['Aterramento/equipotencialização',1,'conj.',price.grounding],
    ['Conectores MC4',mc4Pairs,'pares',mc4Pairs*price.mc4],
    ['Eletroduto/eletrocalha',Math.ceil(Math.max(15,panels*2)),'m',Math.ceil(Math.max(15,panels*2))*price.conduit],
    ['Identificação e sinalização',1,'conj.',price.labels],
    ['Monitoramento/Wi-Fi',1,'conj.',price.monitoring],
    ['Projeto + engenharia/homologação',1,'serv.',price.engineering],
    ['Mão de obra',1,'serv.',price.labor],
  ];
  const materials=items.reduce((s,x)=>s+x[3],0); const total=materials+c.extra;
  const savings=genMonthly*c.tariff*c.economyFactor;
  const cashPayback=savings?total/savings:Infinity;
  const roofNeed=panels*c.panelArea*1.12;
  const down=Math.max(0,val('solarDownPayment')||0); const finance=Math.max(0,total-down); const rate=Math.max(0,val('solarFinanceRate')||0)/100; const n=Math.max(1,Math.round(val('solarFinanceMonths')||60));
  const installment=rate?finance*rate/(1-Math.pow(1+rate,-n)):finance/n;
  const financedTotal=down+installment*n;
  let cum=-down, financedPayback=Infinity;
  for(let m=1;m<=360;m++){ cum += savings - (m<=n?installment:0); if(cum>=0){ financedPayback=m; break; } }
  return {c,panels,dcKW,inverter,panelMonthly,genMonthly,annual,items,materials,total,savings,cashPayback,roofNeed,down,finance,rate,n,installment,financedTotal,financedPayback,mc4Pairs,dcCableM,acCableM};
}
function solarResultHTML(r, sourceLabel='cálculo local'){
  const roofOk=!r.c.roofArea || r.roofNeed<=r.c.roofArea;
  const cashText=Number.isFinite(r.cashPayback)?formatMonths(r.cashPayback):'não calculável';
  const finText=Number.isFinite(r.financedPayback)?formatMonths(r.financedPayback):'não recupera em até 30 anos na simulação';
  const itemHtml=r.items.map(x=>`<div class="result-row"><span>${esc(x[0])} <small>${num(x[1])} ${esc(x[2])}</small></span><strong>${money(x[3])}</strong></div>`).join('');
  return `<div class="result-box"><div class="result-label">Dimensionamento estimado · ${esc(sourceLabel)}</div><div class="result-main">${r.panels} placas</div>
    <div class="result-sub">
      <div class="result-row"><span>Potência de cada placa</span><strong>${num(r.c.panelW)} Wp</strong></div>
      <div class="result-row"><span>Potência total do campo</span><strong>${num(r.dcKW)} kWp</strong></div>
      <div class="result-row"><span>Inversor sugerido</span><strong>${num(r.inverter)} kW</strong></div>
      <div class="result-row"><span>Geração média estimada</span><strong>${num(r.genMonthly)} kWh/mês</strong></div>
      <div class="result-row"><span>Geração anual estimada</span><strong>${num(r.annual)} kWh/ano</strong></div>
      <div class="result-row"><span>Área útil estimada para módulos</span><strong>${num(r.roofNeed)} m²</strong></div>
    </div>
    <div class="solar-price-summary"><h3>💰 Estimativa de materiais e instalação</h3>${itemHtml}<div class="result-row"><span>Outros custos informados</span><strong>${money(r.c.extra)}</strong></div><div class="result-row total-row"><span>Total estimado do sistema</span><strong>${money(r.total)}</strong></div></div>
    <div class="solar-payback"><h3>📆 Simulação financeira</h3><div class="result-row"><span>Economia mensal modelada</span><strong>${money(r.savings)}</strong></div><div class="result-row"><span>Payback comprando à vista</span><strong>${cashText}</strong></div><div class="result-row"><span>Entrada</span><strong>${money(r.down)}</strong></div><div class="result-row"><span>Parcelamento</span><strong>${r.n} × ${money(r.installment)}</strong></div><div class="result-row"><span>Total desembolsado financiado</span><strong>${money(r.financedTotal)}</strong></div><div class="result-row"><span>Payback considerando parcelas</span><strong>${finText}</strong></div></div>
    <div class="note">${roofOk?'✅ A área informada de telhado comporta a estimativa de módulos, em termos puramente geométricos.':'⚠️ A área útil informada parece insuficiente para a quantidade calculada; considere outro plano de telhado, outro módulo ou reduzir a cobertura alvo.'} O dimensionamento final de strings, tensão/corrente, proteções, cabos, estrutura, compatibilidade do inversor e conexão à rede deve ser validado em projeto.</div></div>`;
}


let solarLayoutState={mode:'roof',tempPoints:[],roofs:[],obstacles:[],calibration:{points:[],metersPerPixel:null,meters:0},placements:[],lat:0,lon:0,optimalAzimuth:0,optimalTilt:15};

function daylightHours(latDeg,declDeg){const lat=Number(latDeg||0)*Math.PI/180,dec=Number(declDeg||0)*Math.PI/180,c=-Math.tan(lat)*Math.tan(dec),h0=Math.acos(Math.max(-1,Math.min(1,c)));return 2*h0*12/Math.PI;}
function solarNoonAltitude(latDeg,declDeg){return 90-Math.abs(Number(latDeg||0)-Number(declDeg||0));}
function solarPathDraw(canvas,lat){if(!canvas)return;const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);const pad=38;ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue('--line')||'#ddd';ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--muted')||'#667085';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(pad,h-pad);ctx.lineTo(w-pad,h-pad);ctx.moveTo(pad,h-pad);ctx.lineTo(pad,pad);ctx.stroke();ctx.font='12px system-ui';ctx.fillText('Leste',w-pad-34,h-14);ctx.fillText('Sul',w/2-10,h-14);ctx.fillText('Oeste',pad,h-14);ctx.fillText('altura solar',pad+7,pad-9);const sets=[-23.44,0,23.44];for(const dec of sets){let first=true;ctx.beginPath();for(let hour=-6;hour<=6;hour+=.1){const la=(Number(lat)||0)*Math.PI/180,de=dec*Math.PI/180,H=hour*15*Math.PI/180,sinAlt=Math.sin(la)*Math.sin(de)+Math.cos(la)*Math.cos(de)*Math.cos(H),deg=Math.asin(Math.max(-1,Math.min(1,sinAlt)))*180/Math.PI;if(deg<=0){first=true;continue;}const x=w/2+(H/(6*Math.PI/180))*(w/2-pad),y=h-pad-(deg/90)*(h-pad*2);if(first){ctx.moveTo(x,y);first=false;}else ctx.lineTo(x,y);}ctx.stroke();}ctx.fillText('Latitude '+num(lat)+'°',pad+7,h-pad-8);}

function solarCanvasPoint(e){const c=document.getElementById('solarOverlay'),img=document.getElementById('solarMapPreview');if(!c||!img||!img.naturalWidth)return null;const r=c.getBoundingClientRect();return{x:Math.max(0,Math.min(img.naturalWidth,(e.clientX-r.left)*(img.naturalWidth/r.width))),y:Math.max(0,Math.min(img.naturalHeight,(e.clientY-r.top)*(img.naturalHeight/r.height)))};}
function solarDist(a,b){return Math.hypot(a.x-b.x,a.y-b.y);}
function solarPolygonArea(poly){let a=0;for(let i=0;i<poly.length;i++){const j=(i+1)%poly.length;a+=poly[i].x*poly[j].y-poly[j].x*poly[i].y;}return Math.abs(a/2);}
function solarPointInPolygon(p,poly){let inside=false;for(let i=0,j=poly.length-1;i<poly.length;j=i++){const xi=poly[i].x,yi=poly[i].y,xj=poly[j].x,yj=poly[j].y;const hit=((yi>p.y)!=(yj>p.y))&&(p.x<(xj-xi)*(p.y-yi)/(yj-yi||1e-12)+xi);if(hit)inside=!inside;}return inside;}
function solarBearingVector(b){const a=normalizeBearing(b)*Math.PI/180;return{x:Math.sin(a),y:-Math.cos(a)};}
function solarPerpVector(b){const a=normalizeBearing(b)*Math.PI/180;return{x:Math.cos(a),y:Math.sin(a)};}
function solarScaleInfo(){if(solarLayoutState.calibration.metersPerPixel>0)return{value:solarLayoutState.calibration.metersPerPixel,approx:false};const area=Math.max(0,val('solarRoofArea')),roof=solarLayoutState.roofs[0];if(area>0&&roof&&roof.points.length>=3){const px=solarPolygonArea(roof.points);if(px>10)return{value:Math.sqrt(area/px),approx:true};}return{value:0,approx:true};}
function solarSolarStatus(msg){const e=document.getElementById('solarImageStatus');if(e)e.textContent=msg;}
function solarSetSolarMode(mode){solarLayoutState.mode=mode;if(mode!=='roof')solarLayoutState.tempPoints=[];document.getElementById('solarRoofModeBtn')?.classList.toggle('active',mode==='roof');document.getElementById('solarObstacleModeBtn')?.classList.toggle('active',mode==='obstacle');document.getElementById('solarCalibrateBtn')?.classList.toggle('active',mode==='calibrate');}
function solarFinishRoof(){if(solarLayoutState.tempPoints.length<3){solarSolarStatus('Marque pelo menos 3 pontos para fechar o telhado.');return;}const roof={points:solarLayoutState.tempPoints.splice(0),azimuth:normalizeBearing(val('solarMarkRoofAzimuth')),tilt:Math.max(0,Math.min(60,val('solarMarkRoofTilt'))),height:Math.max(0,val('solarMarkRoofHeight')),name:'Telhado '+(solarLayoutState.roofs.length+1)};solarLayoutState.roofs.push(roof);solarSetSolarMode('roof');solarSolarStatus('Plano de telhado salvo. Marque outro plano ou calcule o posicionamento.');solarLayoutRender();}
function solarFinishCalibration(){if(solarLayoutState.tempPoints.length!==2){solarSolarStatus('Clique em dois pontos conhecidos para calibrar.');return;}const meters=Math.max(0,val('solarKnownDistance')),px=solarDist(solarLayoutState.tempPoints[0],solarLayoutState.tempPoints[1]);if(!meters||px<1){solarSolarStatus('Informe a distância real e escolha dois pontos separados.');return;}solarLayoutState.calibration={points:solarLayoutState.tempPoints.splice(0),metersPerPixel:meters/px,meters};solarSetSolarMode('roof');solarSolarStatus('Escala calibrada: '+num(meters/px)+' m/pixel.');solarLayoutRender();}
function solarAddObstacle(p){solarLayoutState.obstacles.push({point:p,height:Math.max(0,val('solarObstacleHeight')),name:'Obstáculo '+(solarLayoutState.obstacles.length+1)});solarSolarStatus('Obstáculo '+solarLayoutState.obstacles.length+' marcado.');solarLayoutRender();}
function solarUndo(){if(solarLayoutState.tempPoints.length)solarLayoutState.tempPoints.pop();else if(solarLayoutState.obstacles.length)solarLayoutState.obstacles.pop();else if(solarLayoutState.roofs.length)solarLayoutState.roofs.pop();solarLayoutRender();}
function solarClearMarks(){solarLayoutState.tempPoints=[];solarLayoutState.roofs=[];solarLayoutState.obstacles=[];solarLayoutState.placements=[];solarLayoutState.calibration={points:[],metersPerPixel:null,meters:0};document.getElementById('solarLayoutResult')?.replaceChildren();solarSolarStatus('Marcações limpas. Desenhe o primeiro plano de telhado.');solarLayoutRender();}
function solarClearLayout(){solarLayoutState.placements=[];document.getElementById('solarLayoutResult')?.replaceChildren();solarLayoutRender();}
function solarLayoutRect(center,u,v,length,width,scale){const a=u.x*length/(2*scale),b=u.y*length/(2*scale),c=v.x*width/(2*scale),d=v.y*width/(2*scale);return[{x:center.x-a-c,y:center.y-b-d},{x:center.x+a-c,y:center.y+b-d},{x:center.x+a+c,y:center.y+b+d},{x:center.x-a+c,y:center.y-b+d}];}
function solarRectInside(poly,rect){return rect.every(p=>solarPointInPolygon(p,poly));}
function solarRectBlocked(rect){const center={x:rect.reduce((s,p)=>s+p.x,0)/4,y:rect.reduce((s,p)=>s+p.y,0)/4};const diag=solarDist(rect[0],rect[2])/2;const scale=solarScaleInfo().value;const angle=Math.max(5,Math.min(80,val('solarShadowAltitude')||20))*Math.PI/180;return solarLayoutState.obstacles.some(o=>{const radius=(Math.max(0,o.height)/Math.tan(angle))/Math.max(scale,1e-9);return solarDist(center,o.point)<=radius+diag;});}
function solarGeneratePlacements(roof,target,scale,landscape){const baseL=Math.max(.2,val('solarPanelLength')),baseW=Math.max(.2,val('solarPanelWidth')),gap=Math.max(0,val('solarPanelGap')),edge=Math.max(0,val('solarEdgeClearance'));const L=(landscape?baseW:baseL)+2*edge,W=(landscape?baseL:baseW)+2*edge;const u0=solarBearingVector(roof.azimuth),v0=solarPerpVector(roof.azimuth),u=landscape?v0:u0,v=landscape?u0:v0;const us=roof.points.map(p=>p.x*u.x+p.y*u.y),vs=roof.points.map(p=>p.x*v.x+p.y*v.y);const minU=Math.min(...us)+L/(2*scale),maxU=Math.max(...us)-L/(2*scale),minV=Math.min(...vs)+W/(2*scale),maxV=Math.max(...vs)-W/(2*scale);if(maxU<minU||maxV<minV)return[];const stepU=(L+gap)/scale,stepV=(W+gap)/scale,out=[];let loops=0;for(let vv=minV;vv<=maxV+1e-8&&out.length<target&&loops<15000;vv+=stepV){for(let uu=minU;uu<=maxU+1e-8&&out.length<target;uu+=stepU){loops++;const center={x:u.x*uu+v.x*vv,y:u.y*uu+v.y*vv},rect=solarLayoutRect(center,u,v,L,W,scale);if(!solarRectInside(roof.points,rect)||solarRectBlocked(rect))continue;out.push({rect,roof:roof.name,orientation:landscape?'landscape':'portrait',azimuth:roof.azimuth,tilt:roof.tilt});}}return out;}
function solarRoofScore(roof){const ideal=normalizeBearing(solarLayoutState.optimalAzimuth||0),diff=Math.abs(((roof.azimuth-ideal+180)%360)-180),orient=1-diff/180,tiltIdeal=Math.max(5,Number(solarLayoutState.optimalTilt||15)),tilt=Math.max(0,1-Math.abs(roof.tilt-tiltIdeal)/60);return orient*.65+tilt*.35;}
function solarComputeModuleLayout(target){const si=solarScaleInfo();if(!solarLayoutState.roofs.length)return{placements:[],reason:'Marque pelo menos um plano de telhado.'};if(!si.value)return{placements:[],reason:'Calibre a escala ou informe uma área útil de telhado maior que zero.'};const roofs=solarLayoutState.roofs.map(roof=>{const p=solarGeneratePlacements(roof,target,si.value,false),l=solarGeneratePlacements(roof,target,si.value,true),best=l.length>p.length?l:p;return{roof,score:solarRoofScore(roof),placements:best,capacity:best.length};}).sort((a,b)=>b.score-a.score);let remaining=target,placements=[],details=[];for(const x of roofs){const chosen=x.placements.slice(0,remaining);placements=placements.concat(chosen);remaining-=chosen.length;details.push({name:x.roof.name,count:chosen.length,capacity:x.capacity,score:x.score,azimuth:x.roof.azimuth,tilt:x.roof.tilt});if(remaining<=0)break;}return{placements,roofs:details,remaining,scale:si.value,scaleApprox:si.approx};}
function solarLayoutResultHTML(target,layout){const rows=(layout.roofs||[]).map(r=>'<div class="result-row"><span>'+esc(r.name)+' · '+num(r.azimuth)+'° / '+num(r.tilt)+'°</span><strong>'+r.count+' de '+r.capacity+'</strong></div>').join('');const missing=Math.max(0,target-layout.placements.length);return '<div class="solar-layout-result"><div class="result-label">Pré-dimensionamento geométrico</div><div class="result-main">'+layout.placements.length+' / '+target+'</div><div class="result-sub"><div class="result-row"><span>Orientação de referência</span><strong>'+num(solarLayoutState.optimalAzimuth)+'° — '+esc(solarBearingName(solarLayoutState.optimalAzimuth))+'</strong></div><div class="result-row"><span>Inclinação de referência</span><strong>'+num(solarLayoutState.optimalTilt)+'°</strong></div><div class="result-row"><span>Escala usada</span><strong>'+num(layout.scale||0)+' m/pixel '+(layout.scaleApprox?'(aprox.)':'')+'</strong></div><div class="result-row"><span>Módulos sem posição</span><strong>'+missing+'</strong></div>'+rows+'</div><div class="note">'+(missing?'⚠️ Não foi possível acomodar todos os módulos nos planos marcados.':'✅ A quantidade dimensionada encontrou posições geométricas nos planos marcados.')+' A sombra é uma aproximação conservadora baseada na altura dos obstáculos e no ângulo solar mínimo informado.</div></div>';}
function solarLayoutAuto(){const target=Math.max(0,Math.round(calcSolarLocal().panels));if(!target){solarSolarStatus('Calcule o sistema com consumo maior que zero antes do posicionamento.');return;}if(!solarLayoutState.roofs.length){const box=document.getElementById('solarLayoutResult');if(box)box.innerHTML='<div class="notice">Marque pelo menos um plano de telhado na imagem para calcular as posições.</div>';return;}const layout=solarComputeModuleLayout(target);if(!layout.placements.length){const box=document.getElementById('solarLayoutResult');if(box)box.innerHTML='<div class="notice">⚠️ '+esc(layout.reason||'Não encontrei posições.')+'</div>';solarLayoutState.placements=[];solarLayoutRender();return;}solarLayoutState.placements=layout.placements;const box=document.getElementById('solarLayoutResult');if(box)box.innerHTML=solarLayoutResultHTML(target,layout);solarLayoutRender();solarSolarStatus('Posicionamento calculado: '+layout.placements.length+' de '+target+' módulos.');}
function solarLayoutRender(){const img=document.getElementById('solarMapPreview'),canvas=document.getElementById('solarOverlay'),wrap=document.getElementById('solarCanvasWrap');if(!img||!canvas||!wrap||!img.naturalWidth)return;const w=Math.max(260,Math.round(img.clientWidth)),h=Math.max(160,Math.round(img.clientHeight));canvas.width=w;canvas.height=h;wrap.style.height=h+'px';const sx=w/img.naturalWidth,sy=h/img.naturalHeight,ctx=canvas.getContext('2d'),p=q=>({x:q.x*sx,y:q.y*sy});ctx.clearRect(0,0,w,h);function poly(pts,fill,stroke,dash){ctx.save();ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].x,pts[i].y);ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=stroke;ctx.lineWidth=2;if(dash)ctx.setLineDash(dash);ctx.stroke();ctx.restore();}solarLayoutState.roofs.forEach(r=>{poly(r.points.map(p),'rgba(16,185,129,.14)','rgba(5,150,105,.95)',[]);});const a=Math.max(5,Math.min(80,val('solarShadowAltitude')||20))*Math.PI/180;solarLayoutState.obstacles.forEach(o=>{const q=p(o.point),rad=(o.height/Math.tan(a))*Math.min(sx,sy);ctx.save();ctx.beginPath();ctx.arc(q.x,q.y,Math.max(8,rad),0,Math.PI*2);ctx.fillStyle='rgba(245,158,11,.12)';ctx.fill();ctx.strokeStyle='rgba(217,119,6,.95)';ctx.setLineDash([6,5]);ctx.stroke();ctx.restore();});solarLayoutState.placements.forEach(pl=>poly(pl.rect.map(p),'rgba(59,130,246,.45)','rgba(30,64,175,.95)',[]));if(solarLayoutState.tempPoints.length){const pts=solarLayoutState.tempPoints.map(p);ctx.save();ctx.strokeStyle='rgba(220,38,38,.95)';ctx.fillStyle='rgba(220,38,38,.95)';ctx.beginPath();ctx.moveTo(pts[0].x*sx,pts[0].y*sy);for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].x*sx,pts[i].y*sy);ctx.stroke();pts.forEach(q=>{ctx.beginPath();ctx.arc(q.x*sx,q.y*sy,4,0,Math.PI*2);ctx.fill();});ctx.restore();}if(solarLayoutState.calibration.points.length===2){const q=solarLayoutState.calibration.points.map(p);ctx.save();ctx.strokeStyle='rgba(124,58,237,.95)';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(q[0].x*sx,q[0].y*sy);ctx.lineTo(q[1].x*sx,q[1].y*sy);ctx.stroke();ctx.restore();}ctx.save();ctx.fillStyle='rgba(255,255,255,.92)';ctx.strokeStyle='rgba(17,24,39,.8)';ctx.beginPath();ctx.arc(34,34,23,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#111827';ctx.font='bold 12px system-ui';ctx.textAlign='center';ctx.fillText('N',34,25);ctx.fillText('S',34,47);ctx.fillText('L',46,37);ctx.fillText('O',22,37);ctx.restore();}
function solarImageRead(){const input=document.getElementById('solarMapImage'),img=document.getElementById('solarMapPreview');if(!input||!img||!input.files?.[0])return;const file=input.files[0],reader=new FileReader();reader.onload=()=>{img.src=reader.result;img.onload=()=>{document.getElementById('solarCanvasWrap')?.classList.add('visible');solarLayoutRender();};solarSolarStatus('Imagem carregada: '+file.name+'. Comece pelos planos de telhado.');};reader.readAsDataURL(file);}
function solarAddressPayload(){const address=document.getElementById('solarAddress')?.value||'';return{cep:document.getElementById('solarCep')?.value||'',address,street:address,neighborhood:document.getElementById('solarNeighborhood')?.value||'',city:document.getElementById('solarCity')?.value||'',state:document.getElementById('solarState')?.value||'',roofAzimuth:solarLayoutState.roofs[0]?.azimuth||0,roofTilt:solarLayoutState.roofs[0]?.tilt||15};}
async function fetchCepForSolar(){const cep=(document.getElementById('solarCep')?.value||'').replace(/\D/g,'');const st=document.getElementById('solarResourceStatus');if(cep.length!==8){if(st)st.textContent='Informe um CEP com 8 dígitos.';return;}try{const res=await fetch('/api/address/cep/'+cep),d=await res.json();if(!res.ok)throw new Error(d.detail||'CEP não encontrado.');document.getElementById('solarAddress').value=[d.logradouro,d.complemento].filter(Boolean).join(', ');document.getElementById('solarNeighborhood').value=d.bairro||'';document.getElementById('solarCity').value=d.localidade||'';document.getElementById('solarState').value=d.uf||'';if(st)st.textContent='✅ Endereço preenchido. Clique em “Localizar endereço”.';}catch(e){if(st)st.textContent='⚠️ '+esc(e.message);}}
async function searchSolarAddress(){const st=document.getElementById('solarResourceStatus');if(st)st.textContent='🧭 Localizando endereço...';try{const res=await fetch('/api/address/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(solarAddressPayload())}),d=await res.json();if(!res.ok)throw new Error(d.detail||'Não foi possível localizar o endereço.');solarLayoutState.lat=Number(d.lat||0);solarLayoutState.lon=Number(d.lon||0);solarPathDraw(document.getElementById('solarPathCanvas'),solarLayoutState.lat);if(st)st.innerHTML='✅ '+esc(d.displayName||'Endereço localizado')+' · lat '+num(d.lat)+' · lon '+num(d.lon);solarSolarStatus('Endereço localizado.');}catch(e){if(st)st.innerHTML='⚠️ '+esc(e.message);}}
async function updateSolarResource(){const st=document.getElementById('solarResourceStatus');if(st)st.textContent='☀️ Consultando dados solares...';try{const res=await fetch('/api/solar/resource',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(solarAddressPayload())}),d=await res.json();if(!res.ok)throw new Error(d.detail||'Não foi possível obter os dados solares.');solarLayoutState.lat=Number(d.lat||0);solarLayoutState.lon=Number(d.lon||0);solarLayoutState.optimalAzimuth=normalizeBearing(Number(d.optimalAzimuth||0));solarLayoutState.optimalTilt=Number(d.optimalTilt||15);const annual=Number(d.roof?.annualKwhPerKwp||d.annualKwhPerKwp||0),pr=Math.max(.1,Math.min(1,val('solarPR')/100||.8));if(annual>0)document.getElementById('solarPSH').value=Math.max(1,Math.min(8,(annual/(365*pr))).toFixed(2));if(st)st.innerHTML='✅ '+esc(d.displayName||'Localização')+' · '+esc(d.source||'modelo local')+' · referência '+num(d.optimalAzimuth)+'° / '+num(d.optimalTilt)+'°';solarPathDraw(document.getElementById('solarPathCanvas'),solarLayoutState.lat);solarLayoutRender();}catch(e){if(st)st.innerHTML='⚠️ '+esc(e.message)+' O cálculo continuará com as horas de sol informadas.';}}
async function updateSolarPrices(){const st=document.getElementById('solarResourceStatus');try{const q=new URLSearchParams({city:document.getElementById('solarCity')?.value||'Cuiabá',state:document.getElementById('solarState')?.value||'MT'}),res=await fetch('/api/solar/prices?'+q.toString()),d=await res.json();if(!res.ok)throw new Error(d.detail||'Falha na consulta de preços.');if(!d.configured){if(st)st.textContent='⚠️ Consulta online desativada. Os preços editáveis continuam disponíveis.';return;}const map={panel:'pricePanel',inverter:'priceInverter',mounting:'priceMounting',dcProtection:'priceDcProtection',acProtection:'priceAcProtection'};let changed=0;for(const item of d.items||[]){const id=map[item.key];if(id&&item.best?.price){document.getElementById(id).value=Number(item.best.price).toFixed(2);changed++;}}if(st)st.textContent='✅ '+changed+' preços atualizados.';}catch(e){if(st)st.textContent='⚠️ '+esc(e.message);}}
function bindSolarCalculatorInteractions(){solarLayoutState={mode:'roof',tempPoints:[],roofs:[],obstacles:[],calibration:{points:[],metersPerPixel:null,meters:0},placements:[],lat:0,lon:0,optimalAzimuth:0,optimalTilt:15};document.getElementById('solarMapImage')?.addEventListener('change',solarImageRead);document.getElementById('solarOverlay')?.addEventListener('click',e=>{const p=solarCanvasPoint(e);if(!p)return;if(solarLayoutState.mode==='calibrate'){if(solarLayoutState.tempPoints.length<2)solarLayoutState.tempPoints.push(p);if(solarLayoutState.tempPoints.length===2)solarFinishCalibration();return;}if(solarLayoutState.mode==='obstacle'){solarAddObstacle(p);return;}solarLayoutState.tempPoints.push(p);solarLayoutRender();solarSolarStatus('Ponto '+solarLayoutState.tempPoints.length+' marcado. Clique em “Concluir marcação”.');});document.getElementById('solarRoofModeBtn')?.addEventListener('click',()=>solarSetSolarMode('roof'));document.getElementById('solarObstacleModeBtn')?.addEventListener('click',()=>solarSetSolarMode('obstacle'));document.getElementById('solarCalibrateBtn')?.addEventListener('click',()=>{solarLayoutState.tempPoints=[];solarSetSolarMode('calibrate');solarSolarStatus('Clique em dois pontos cuja distância real você conhece.');});document.getElementById('solarFinishMarkBtn')?.addEventListener('click',()=>solarLayoutState.mode==='calibrate'?solarFinishCalibration():solarFinishRoof());document.getElementById('solarUndoBtn')?.addEventListener('click',solarUndo);document.getElementById('solarClearMarksBtn')?.addEventListener('click',solarClearMarks);document.getElementById('solarAutoLayoutBtn')?.addEventListener('click',solarLayoutAuto);document.getElementById('solarLayoutClearBtn')?.addEventListener('click',solarClearLayout);document.getElementById('solarCepBtn')?.addEventListener('click',fetchCepForSolar);document.getElementById('solarAddressBtn')?.addEventListener('click',searchSolarAddress);document.getElementById('solarResourceBtn')?.addEventListener('click',updateSolarResource);document.getElementById('solarPricesBtn')?.addEventListener('click',updateSolarPrices);['solarPanelLength','solarPanelWidth','solarPanelGap','solarEdgeClearance','solarShadowAltitude','solarMarkRoofAzimuth','solarMarkRoofTilt','solarObstacleHeight'].forEach(id=>document.getElementById(id)?.addEventListener('input',solarLayoutRender));window.addEventListener('resize',()=>setTimeout(solarLayoutRender,60));solarSetSolarMode('roof');solarPathDraw(document.getElementById('solarPathCanvas'),solarLayoutState.lat);}
function converterArquivosUI(){return `<div class="tool-layout"><section class="card panel"><h2>Conversor de arquivos</h2><div class="notice"><strong>Converta no Resolvei.</strong><br>Vídeos usam FFmpeg; imagens e PDFs são processados pelo servidor.</div><div class="field full"><label for="convertFile">Arquivo</label><input id="convertFile" type="file" accept=".mp4,.avi,.mov,.mkv,.webm,.jpg,.jpeg,.png,.webp,.bmp,.pdf"></div><div class="form-grid"><div class="field"><label for="convertFormat">Formato de saída</label><select id="convertFormat"><option value="">Selecione o arquivo primeiro</option></select></div><div class="field"><label>Limite</label><div class="notice" style="margin:0">Até 200 MB.</div></div></div><div class="actions"><button class="btn primary" id="convertBtn" disabled>Converter arquivo</button><button class="btn ghost" id="convertResetBtn" type="button">Limpar</button></div><div id="convertProgress" class="notice" style="display:none">⏳ Convertendo...</div><div id="convertStatus" class="notice">Nenhum arquivo selecionado.</div></section><section id="convertResult"><div class="result-box"><div class="result-label">Resultado</div><div class="result-main">—</div><p>O arquivo convertido aparecerá aqui.</p></div></section></div>`;}
function toolUI(id){
  switch(id){
    case 'jpg-png-webp': return universalFileConverterUI(id);
    case 'heic-jpg': return universalFileConverterUI(id);
    case 'imagem-pdf': return universalFileConverterUI(id);
    case 'pdf-imagens-zip': return universalFileConverterUI(id);
    case 'mp4-mp3': return universalFileConverterUI(id);
    case 'mp4-gif': return universalFileConverterUI(id);
    case 'csv-xlsx': return universalFileConverterUI(id);
    case 'zip-arquivos': return universalFileConverterUI(id);
    case 'mov-mp4': return universalFileConverterUI(id);
    case 'jpg-heic': return universalFileConverterUI(id);
    case 'imagem-comprimir': return universalFileConverterUI(id);
    case 'docx-pdf': return universalFileConverterUI(id);
    case 'pdf-docx': return universalFileConverterUI(id);
    case 'pdf-txt': return universalFileConverterUI(id);
    case 'txt-pdf': return universalFileConverterUI(id);
    case 'pdf-xlsx': return universalFileConverterUI(id);
    case 'xlsx-csv': return universalFileConverterUI(id);
    case 'audio-mp3-wav': return universalFileConverterUI(id);
    case 'audio-ogg': return universalFileConverterUI(id);
    case 'video-webm': return universalFileConverterUI(id);
    case 'video-avi': return universalFileConverterUI(id);
    case 'video-audio': return universalFileConverterUI(id);
    case 'svg-png': return universalFileConverterUI(id);
    case 'png-ico': return universalFileConverterUI(id);
    case 'imagem-redimensionar': return universalFileConverterUI(id);
    case 'pdf-comprimir': return universalFileConverterUI(id);
    case 'arquivos-zip': return universalFileConverterUI(id);
    case 'jpg-png-webp': case 'heic-jpg': case 'imagem-pdf': case 'pdf-imagens-zip': case 'mp4-mp3': case 'mp4-gif': case 'csv-xlsx': case 'zip-arquivos': case 'mov-mp4': case 'jpg-heic': case 'imagem-comprimir': return universalFileConverterUI(id);
    case 'conversor-arquivos': return converterArquivosUI();
    case 'porcentagem': return panel(input('p1','Porcentagem',{value:'15'})+input('p2','Valor',{value:'200',prefix:'R$'}),); 
    case 'regra-de-3': return panel(input('a','A','',{value:'2'})+input('b','B','',{value:'10'})+input('c','C','',{value:'5'}));
    case 'desconto': return panel(input('price','Preço original', {prefix:'R$',value:'199.90'})+input('discount','Desconto',{suffix:'%',value:'10'}));
    case 'acrescimo': return panel(input('price','Preço original',{prefix:'R$',value:'199.90'})+input('increase','Acréscimo',{suffix:'%',value:'10'}));
    case 'juros-simples': return panel(input('capital','Capital',{prefix:'R$',value:'1000'})+input('rate','Taxa ao período',{suffix:'%',value:'2'})+input('time','Períodos',{value:'12',step:'1'}));
    case 'juros-compostos': return panel(input('capital','Capital inicial',{prefix:'R$',value:'1000'})+input('rate','Taxa por período',{suffix:'%',value:'1'})+input('time','Número de períodos',{value:'24',step:'1'})+input('aporte','Aporte por período',{prefix:'R$',value:'200'}));
    case 'dividir-conta': return panel(input('bill','Valor da conta',{prefix:'R$',value:'200'})+input('people','Número de pessoas',{value:'4',step:'1',min:1})+input('service','Serviço/gorjeta',{suffix:'%',value:'10'}));
    case 'gorjeta': return panel(input('bill','Valor da conta',{prefix:'R$',value:'150'})+input('tip','Gorjeta',{suffix:'%',value:'10'}));
    case 'financiamento': return panel(input('pv','Valor financiado',{prefix:'R$',value:'50000'})+input('rate','Juros ao mês',{suffix:'%',value:'1'})+input('n','Número de parcelas',{value:'48',step:'1',min:1}));
    case 'emprestimo': return panel(input('pv','Valor do empréstimo',{prefix:'R$',value:'10000'})+input('rate','Juros ao mês',{suffix:'%',value:'2'})+input('n','Parcelas',{value:'24',step:'1',min:1}));
    case 'meta-poupanca': return panel(input('target','Meta',{prefix:'R$',value:'10000'})+input('current','Já tenho',{prefix:'R$',value:'1000'})+input('months','Prazo em meses',{value:'24',step:'1',min:1})+input('rate','Rendimento mensal estimado',{suffix:'%',value:'0.6'}));
    case 'poder-compra': return panel(input('value','Valor de hoje',{prefix:'R$',value:'1000'})+input('inflation','Inflação acumulada',{suffix:'%',value:'30'}));
    case 'combustivel-viagem': return panel(input('distance','Distância da viagem',{suffix:'km',value:'800'})+input('consumption','Consumo do veículo',{suffix:'km/L',value:'10'})+input('fuel','Preço do combustível',{prefix:'R$',value:'6.20'})+input('tolls','Pedágios',{prefix:'R$',value:'0'}));
    case 'custo-km': return panel(input('fuel','Preço do combustível',{prefix:'R$',value:'6.20'})+input('consumption','Consumo',{suffix:'km/L',value:'10'})+input('maintenance','Outros custos por km',{prefix:'R$',value:'0.10'}));
    case 'gasolina-etanol': return panel(input('gas','Preço da gasolina',{prefix:'R$',value:'6.20'})+input('eth','Preço do etanol',{prefix:'R$',value:'4.20'})+input('gas_eff','Consumo na gasolina',{suffix:'km/L',value:'12'})+input('eth_eff','Consumo no etanol',{suffix:'km/L',value:'8'}));
    case 'consumo-carro': return panel(input('distance','Distância percorrida',{suffix:'km',value:'420'})+input('liters','Litros abastecidos',{suffix:'L',value:'38'})+input('fuel','Preço por litro',{prefix:'R$',value:'6.20'}));
    case 'tempo-viagem': return panel(input('distance','Distância',{suffix:'km',value:'800'})+input('speed','Velocidade média',{suffix:'km/h',value:'100'}));
    case 'custo-viagem': return panel(input('distance','Distância total',{suffix:'km',value:'800'})+input('consumption','Consumo',{suffix:'km/L',value:'10'})+input('fuel','Preço do combustível',{prefix:'R$',value:'6.20'})+input('tolls','Pedágios',{prefix:'R$',value:'120'})+input('other','Outros custos',{prefix:'R$',value:'50'}));
    case 'tinta': return panel(input('length','Comprimento das paredes',{suffix:'m',value:'20'})+input('height','Altura média',{suffix:'m',value:'2.8'})+input('openings','Portas e janelas',{suffix:'m²',value:'8'})+input('coats','Número de demãos',{value:'2',step:'1'})+input('yield','Rendimento da tinta',{suffix:'m²/L por demão',value:'10'}));
    case 'piso': return panel(input('roomL','Comprimento do ambiente',{suffix:'m',value:'4.20'})+input('roomW','Largura do ambiente',{suffix:'m',value:'3.80'})+input('tileL','Comprimento da peça',{suffix:'cm',value:'60'})+input('tileW','Largura da peça',{suffix:'cm',value:'60'})+input('waste','Perda',{suffix:'%',value:'10'}));
    case 'rejunte': return panel(input('area','Área de revestimento',{suffix:'m²',value:'20'})+input('tileL','Comprimento da peça',{suffix:'cm',value:'60'})+input('tileW','Largura da peça',{suffix:'cm',value:'60'})+input('joint','Largura da junta',{suffix:'mm',value:'2'})+input('depth','Profundidade da junta',{suffix:'mm',value:'8'}));
    case 'argamassa': return panel(input('area','Área a revestir',{suffix:'m²',value:'20'})+input('consumption','Consumo',{suffix:'kg/m²',value:'5'}));
    case 'concreto': return panel(input('length','Comprimento',{suffix:'m',value:'5'})+input('width','Largura',{suffix:'m',value:'3'})+input('height','Espessura/altura',{suffix:'m',value:'0.10'}));
    case 'blocos': return panel(input('wallL','Comprimento da parede',{suffix:'m',value:'10'})+input('wallH','Altura da parede',{suffix:'m',value:'2.8'})+input('blockL','Comprimento do bloco',{suffix:'cm',value:'39'})+input('blockH','Altura do bloco',{suffix:'cm',value:'19'})+input('waste','Perda',{suffix:'%',value:'10'}));
    case 'telhas': return panel(input('area','Área da cobertura',{suffix:'m²',value:'100'})+input('coverage','Rendimento',{suffix:'telhas/m²',value:'12'})+input('waste','Perda',{suffix:'%',value:'10'}));
    case 'escada': return panel(input('floor','Altura piso a piso',{suffix:'m',value:'2.80',help:'Digite somente o desnível entre o piso acabado inferior e o piso acabado superior.'}));
    case 'iluminacao': return panel(input('area','Área do ambiente',{suffix:'m²',value:'20'})+input('lux','Nível de iluminância',{suffix:'lux',value:'150'})+input('util','Fator de utilização',{suffix:'%',value:'70'})+input('maint','Fator de manutenção',{suffix:'%',value:'80'}));
    case 'ar-condicionado': return panel(input('area','Área do ambiente',{suffix:'m²',value:'20'})+input('people','Pessoas',{value:'2',step:'1'})+input('electronics','Eletrônicos relevantes',{value:'1',step:'1'})+input('sun','Exposição solar',{help:'0 = baixa; 1 = média; 2 = alta',value:'1',step:'1',min:0}));
    case 'caixa-dagua': return panel(input('people','Número de pessoas',{value:'4',step:'1',min:1})+input('perperson','Reserva por pessoa',{suffix:'L',value:'200'})+input('days','Dias de reserva',{value:'1',step:'1',min:1}));
    case 'piscina': return panel(input('length','Comprimento',{suffix:'m',value:'5'})+input('width','Largura',{suffix:'m',value:'3'})+input('depth','Profundidade média',{suffix:'m',value:'1.3'}));
    case 'cobertura': return panel(input('span','Vão horizontal considerado',{suffix:'m',value:'5'})+input('slope','Inclinação',{suffix:'%',value:'30'}));
    case 'placas-solares': return solarCalculatorUI();
    case 'posicao-solar': return solarCalculatorUI();
    case 'area-retangulo': return panel(input('length','Comprimento',{suffix:'m',value:'5'})+input('width','Largura',{suffix:'m',value:'4'}));
    case 'area-triangulo': return panel(input('base','Base',{suffix:'m',value:'5'})+input('height','Altura',{suffix:'m',value:'3'}));
    case 'area-circulo': return panel(input('radius','Raio',{suffix:'m',value:'2'}));
    case 'volume-caixa': return panel(input('length','Comprimento',{suffix:'m',value:'2'})+input('width','Largura',{suffix:'m',value:'1'})+input('height','Altura',{suffix:'m',value:'0.5'}));
    case 'temperatura': return panel(input('temp','Temperatura',{suffix:'°',value:'30'})+select('direction','Converter de',[['c2f','°C para °F'],['f2c','°F para °C']],'c2f'));
    case 'comprimento': return panel(input('value','Valor',{value:'1'})+select('from','De',[['mm','milímetro'],['cm','centímetro'],['m','metro'],['km','quilômetro'],['in','polegada'],['ft','pé'],['yd','jarda'],['mi','milha']],'m')+select('to','Para',[['mm','milímetro'],['cm','centímetro'],['m','metro'],['km','quilômetro'],['in','polegada'],['ft','pé'],['yd','jarda'],['mi','milha']],'cm'));
    case 'peso': return panel(input('value','Valor',{value:'1'})+select('from','De',[['mg','mg'],['g','g'],['kg','kg'],['t','tonelada'],['oz','oz'],['lb','lb']],'kg')+select('to','Para',[['mg','mg'],['g','g'],['kg','kg'],['t','tonelada'],['oz','oz'],['lb','lb']],'g'));
    case 'volume': return panel(input('value','Valor',{value:'1'})+select('from','De',[['ml','ml'],['l','L'],['m3','m³'],['gal','galão US'],['cup','xícara US']],'l')+select('to','Para',[['ml','ml'],['l','L'],['m3','m³'],['gal','galão US'],['cup','xícara US']],'ml'));
    case 'area': return panel(input('value','Valor',{value:'1'})+select('from','De',[['m2','m²'],['km2','km²'],['ha','hectare'],['acre','acre'],['ft2','ft²']],'m2')+select('to','Para',[['m2','m²'],['km2','km²'],['ha','hectare'],['acre','acre'],['ft2','ft²']],'ha'));
    case 'velocidade': return panel(input('value','Valor',{value:'100'})+select('from','De',[['kmh','km/h'],['mph','mph'],['ms','m/s']],'kmh')+select('to','Para',[['kmh','km/h'],['mph','mph'],['ms','m/s']],'ms'));
    case 'dados': return panel(input('value','Valor',{value:'1'})+select('from','De',[['KB','KB'],['MB','MB'],['GB','GB'],['TB','TB']],'GB')+select('to','Para',[['KB','KB'],['MB','MB'],['GB','GB'],['TB','TB']],'MB'));
    case 'energia': return panel(input('value','Valor',{value:'1'})+select('from','De',[['w','W'],['kw','kW'],['cv','cv']],'kw')+select('to','Para',[['w','W'],['kw','kW'],['cv','cv']],'cv'));
    case 'idade': return panel(input('birth','Data de nascimento',{type:'date',value:'1990-01-01',help:'Resultado aproximado em anos, meses e dias.'}));
    case 'dias-entre-datas': return panel(input('start','Data inicial',{type:'date',value:new Date().toISOString().slice(0,10)})+input('end','Data final',{type:'date',value:new Date(Date.now()+30*86400000).toISOString().slice(0,10)}));
    case 'data-futura': return panel(input('date','Data de referência',{type:'date',value:new Date().toISOString().slice(0,10)})+input('days','Adicionar dias',{value:'30',step:'1'}));
    case 'dia-semana': return panel(input('date','Data',{type:'date',value:new Date().toISOString().slice(0,10)}));
    case 'horas': return panel(input('start','Horário inicial',{type:'time',value:'08:00'})+input('end','Horário final',{type:'time',value:'17:30'}));
    case 'somar-horas': return panel(input('h1','Período 1 (horas)',{value:'8',step:'0.25'})+input('h2','Período 2 (horas)',{value:'1.5',step:'0.25'})+input('h3','Período 3 (horas)',{value:'0',step:'0.25'}));
    case 'rescisao-clt': return rescisaoUI();
    case 'clt-vs-pj': return cltVsPJUI();
    case 'receita': return panel(input('from','Porções originais',{value:'4',step:'1'})+input('to','Porções desejadas',{value:'10',step:'1'})+input('ingredient','Quantidade do ingrediente',{value:'500'})+select('unit','Unidade',[['g','g'],['ml','ml'],['un','unidades'],['xicaras','xícaras'],['colheres','colheres']],'g'));
    case 'temperatura-cozinha': return panel(input('temp','Temperatura',{value:'180'})+select('direction','Converter de',[['c2f','°C para °F'],['f2c','°F para °C']],'c2f'));
    case 'custo-receita': return receitaCustoUI();
    case 'por-quanto-vender': return porQuantoVenderUI();
    case 'churrasco': return churrascoUI();
    case 'festa': return festaUI();
    case 'bolo': return panel(input('guests','Convidados',{value:'30',step:'1'})+select('event','Tipo',[['normal','Festa comum'],['principal','Bolo como sobremesa principal']],'normal'));
    case 'gelo': return panel(input('people','Pessoas',{value:'30',step:'1'})+input('hours','Duração',{suffix:'h',value:'4'}));
    case 'lista-compras': return listaComprasUI();
    case 'dividir-pessoas': return panel(input('amount','Valor total',{prefix:'R$',value:'100'})+input('people','Pessoas',{value:'3',step:'1',min:1}));
    default: return `<div class="empty">Ferramenta não encontrada.</div>`;
  }
}

function calculate(id){
  const out=document.getElementById('result'); if(!out)return;
  let main='—',label='Resultado',rows=[],note='',extraHtml='';
  const row=(l,v)=>rows.push(`<div class="result-row"><span>${l}</span><strong>${v}</strong></div>`);
  switch(id){
    case 'porcentagem': {const p=val('p1'),v=val('p2'),r=v*p/100;main=num(r);label=`${pct(p)} de ${num(v)}`;row('Valor original',num(v));row('Porcentagem',pct(p));break;}
    case 'regra-de-3': {const a=val('a'),b=val('b'),c=val('c'),r=a?b*c/a:0;main=num(r);label='Resultado proporcional';row('A',num(a));row('B',num(b));row('C',num(c));note='Fórmula usada: A/B = C/X.';break;}
    case 'desconto': {const p=val('price'),d=val('discount'),r=p*(1-d/100);main=money(r);label='Preço final';row('Desconto',money(p*d/100));row('Economia',pct(d));break;}
    case 'acrescimo': {const p=val('price'),d=val('increase'),r=p*(1+d/100);main=money(r);label='Preço final';row('Acréscimo',money(p*d/100));break;}
    case 'juros-simples': {const c=val('capital'),i=val('rate')/100,n=val('time'),j=c*i*n;main=money(c+j);label='Montante';row('Juros',money(j));row('Capital',money(c));break;}
    case 'juros-compostos': {const c=val('capital'),i=val('rate')/100,n=val('time'),a=val('aporte');const fv=c*Math.pow(1+i,n)+(i?a*(Math.pow(1+i,n)-1)/i:a*n);main=money(fv);label='Valor final estimado';row('Capital inicial',money(c));row('Aportes',money(a*n));row('Crescimento',money(fv-c-a*n));note='Estimativa matemática; não inclui impostos, taxas ou variações reais.';break;}
    case 'dividir-conta': {const b=val('bill'),p=val('people'),s=val('service')/100,total=b*(1+s);main=money(total/p);label='Por pessoa';row('Total com serviço',money(total));row('Serviço',money(b*s));break;}
    case 'gorjeta': {const b=val('bill'),t=val('tip')/100,x=b*t;main=money(b+x);label='Total com gorjeta';row('Gorjeta',money(x));row('Conta',money(b));break;}
    case 'financiamento': case 'emprestimo': {const pv=val('pv'),i=val('rate')/100,n=val('n');const pay=i?pv*i/(1-Math.pow(1+i,-n)):pv/n;main=money(pay);label='Parcela estimada';row('Total pago',money(pay*n));row('Juros totais',money(pay*n-pv));break;}
    case 'meta-poupanca': {const target=val('target'),current=val('current'),n=val('months'),i=val('rate')/100,gap=Math.max(0,target-current),pay=i?gap*i/(Math.pow(1+i,n)-1):gap/n;main=money(pay);label='Aporte mensal estimado';row('Meta restante',money(gap));row('Total de aportes',money(pay*n));break;}
    case 'poder-compra': {const v=val('value'),inf=val('inflation')/100,future=v*(1+inf),real=v/(1+inf);main=money(real);label='Poder de compra equivalente';row('Valor nominal após inflação',money(future));row('Perda de poder de compra',pct((1-real/v)*100));break;}
    case 'combustivel-viagem': {const d=val('distance'),c=val('consumption'),f=val('fuel'),t=val('tolls'),l=c?d/c:0;main=money(l*f+t);label='Custo estimado da viagem';row('Litros',`${num(l)} L`);row('Combustível',money(l*f));row('Pedágios',money(t));break;}
    case 'custo-km': {const f=val('fuel'),c=val('consumption'),o=val('maintenance'),x=c?f/c+o:o;main=money(x);label='Custo por km';row('Só combustível',money(c?f/c:0));row('Outros custos',money(o));break;}
    case 'gasolina-etanol': {const g=val('gas'),e=val('eth'),ge=val('gas_eff'),ee=val('eth_eff'),cg=ge?g/ge:0,ce=ee?e/ee:0;main=cg<=ce?'Gasolina':'Etanol';label='Menor custo por km';row('Custo/km gasolina',money(cg));row('Custo/km etanol',money(ce));note='A comparação depende do consumo real do veículo.';break;}
    case 'consumo-carro': {const d=val('distance'),l=val('liters'),f=val('fuel');main=`${num(l?d/l:0)} km/L`;label='Consumo médio';row('Custo do abastecimento',money(l*f));row('Custo por km',money(l?f/(d/l):0));break;}
    case 'tempo-viagem': {const d=val('distance'),sp=val('speed'),h=sp?d/sp:0;main=formatHours(h);label='Duração estimada';row('Horas decimais',`${num(h)} h`);break;}
    case 'custo-viagem': {const d=val('distance'),c=val('consumption'),f=val('fuel'),t=val('tolls'),o=val('other'),fuel=c?d/c*f:0;main=money(fuel+t+o);label='Custo total estimado';row('Combustível',money(fuel));row('Pedágios',money(t));row('Outros',money(o));break;}
    case 'tinta': {const area=Math.max(0,val('length')*val('height')-val('openings')),coats=val('coats'),yv=val('yield'),lit=yv?area*coats/yv:0;main=`${num(Math.ceil(lit))} L`;label='Tinta estimada';row('Área líquida',`${num(area)} m²`);row('Área com demãos',`${num(area*coats)} m²`);note='Adicione margem conforme fabricante, textura e absorção.';break;}
    case 'piso': {const area=val('roomL')*val('roomW'),ta=(val('tileL')/100)*(val('tileW')/100),pieces=ta?area/ta*(1+val('waste')/100):0;main=`${Math.ceil(pieces)} peças`;label='Quantidade aproximada';row('Área',`${num(area)} m²`);row('Com perda',`${num(area*(1+val('waste')/100))} m²`);break;}
    case 'rejunte': {const area=val('area'),a=val('tileL')/10,b=val('tileW')/10,j=val('joint'),d=val('depth');const kg=area*((a+b)/(a*b))*j*d*0.0015;main=`${num(kg)} kg`;label='Rejunte aproximado';note='Estimativa simplificada; confira a ficha técnica do produto.';break;}
    case 'argamassa': {const a=val('area'),c=val('consumption');main=`${num(a*c)} kg`;label='Argamassa estimada';row('Sacos de 20 kg',`${Math.ceil(a*c/20)} sacos`);break;}
    case 'concreto': {const v=val('length')*val('width')*val('height');main=`${num(v)} m³`;label='Volume de concreto';row('Litros',`${num(v*1000)} L`);break;}
    case 'blocos': {const area=val('wallL')*val('wallH'),ba=(val('blockL')/100)*(val('blockH')/100),q=ba?area/ba*(1+val('waste')/100):0;main=`${Math.ceil(q)} unidades`;label='Blocos/tijolos';row('Área da parede',`${num(area)} m²`);break;}
    case 'telhas': {const q=val('area')*val('coverage')*(1+val('waste')/100);main=`${Math.ceil(q)} telhas`;label='Quantidade estimada';break;}
    case 'escada': {const r=calcEscadaBlondel(val('floor')*100);main=`${num(r.espelho)} cm`;label=`${r.espelhos} espelhos`;row('Altura piso a piso',`${num(r.altura/100)} m`);row('Espelhos',String(r.espelhos));row('Altura de cada espelho',`${num(r.espelho)} cm`);row('Profundidade do piso',`${num(r.piso)} cm`);row('Blondel',`${num(r.blondel)} cm (2e + p)`);row('Pisadas horizontais',String(Math.max(0,r.espelhos-1)));row('Desenvolvimento horizontal',`${num(((r.espelhos-1)*r.piso)/100)} m`);note=r.note;extraHtml=`<div class="standards-box"><h3>📐 Referência normativa</h3><p>Na ABNT NBR 9050:2020, o dimensionamento citado para escadas em rotas acessíveis usa simultaneamente: <strong>0,63 m ≤ p + 2e ≤ 0,65 m</strong>, <strong>piso de 28 a 32 cm</strong> e <strong>espelho de 16 a 18 cm</strong>. Essas faixas são referência da norma de acessibilidade; o projeto ainda precisa verificar largura, patamares, corrimãos, guarda-corpos, legislação local e demais normas aplicáveis.</p></div>`;break;}
    case 'iluminacao': {const a=val('area'),lux=val('lux'),u=val('util')/100,m=val('maint')/100,lm=(a*lux)/(u*m||1);main=`${num(lm)} lm`;label='Fluxo luminoso estimado';break;}
    case 'ar-condicionado': {const a=val('area'),p=val('people'),e=val('electronics'),sun=val('sun'),btu=a*600+p*600+e*500+sun*600;main=`${Math.ceil(btu/500)*500} BTU/h`;label='Capacidade estimada';note='Estimativa inicial; ambientes com alta carga térmica exigem avaliação técnica.';break;}
    case 'caixa-dagua': {const liters=val('people')*val('perperson')*val('days');main=`${num(liters)} L`;label='Capacidade estimada';row('m³',`${num(liters/1000)} m³`);break;}
    case 'piscina': {const v=val('length')*val('width')*val('depth');main=`${num(v*1000)} L`;label='Volume aproximado';row('Volume',`${num(v)} m³`);break;}
    case 'cobertura': {const h=val('span')*val('slope')/100;main=`${num(h)} m`;label='Desnível';row('Inclinação',pct(val('slope')));break;}
    case 'placas-solares':
    case 'posicao-solar': {const r=calcSolarLocal(); out.innerHTML=solarResultHTML(r, 'cálculo local'); solarAutoLayout(); return;}
    case 'area-retangulo': main=`${num(val('length')*val('width'))} m²`;label='Área';break;
    case 'area-triangulo': main=`${num(val('base')*val('height')/2)} m²`;label='Área';break;
    case 'area-circulo': main=`${num(Math.PI*val('radius')**2)} m²`;label='Área';break;
    case 'volume-caixa': {const v=val('length')*val('width')*val('height');main=`${num(v)} m³`;label='Volume';row('Litros',`${num(v*1000)} L`);break;}
    case 'temperatura': case 'temperatura-cozinha': {const x=val('temp'),d=document.getElementById('direction').value,r=d==='c2f'?x*9/5+32:(x-32)*5/9;main=`${num(r)}°`;label=d==='c2f'?'Fahrenheit':'Celsius';break;}
    case 'comprimento': main=`${num(convert(val('value'),document.getElementById('from').value,document.getElementById('to').value,{mm:.001,cm:.01,m:1,km:1000,in:.0254,ft:.3048,yd:.9144,mi:1609.344}))}`;label=document.getElementById('to').options[document.getElementById('to').selectedIndex].text;break;
    case 'peso': main=`${num(convert(val('value'),document.getElementById('from').value,document.getElementById('to').value,{mg:.001,g:1,kg:1000,t:1e6,oz:28.349523125,lb:453.59237}))}`;label=document.getElementById('to').value;break;
    case 'volume': main=`${num(convert(val('value'),document.getElementById('from').value,document.getElementById('to').value,{ml:.001,l:1,m3:1000,gal:3.785411784,cup:.2365882365}))}`;label=document.getElementById('to').value;break;
    case 'area': main=`${num(convert(val('value'),document.getElementById('from').value,document.getElementById('to').value,{m2:1,km2:1e6,ha:1e4,acre:4046.8564224,ft2:.09290304}))}`;label=document.getElementById('to').value;break;
    case 'velocidade': main=`${num(convert(val('value'),document.getElementById('from').value,document.getElementById('to').value,{kmh:1,mph:1.609344,ms:3.6}))}`;label=document.getElementById('to').value;break;
    case 'dados': main=`${num(convert(val('value'),document.getElementById('from').value,document.getElementById('to').value,{KB:1,MB:1024,GB:1048576,TB:1073741824}))}`;label=document.getElementById('to').value;break;
    case 'energia': main=`${num(convert(val('value'),document.getElementById('from').value,document.getElementById('to').value,{w:1,kw:1000,cv:735.49875}))}`;label=document.getElementById('to').value;break;
    case 'idade': {const d=new Date(document.getElementById('birth').value+'T00:00:00'),now=new Date();let y=now.getFullYear()-d.getFullYear(),m=now.getMonth()-d.getMonth(),day=now.getDate()-d.getDate();if(day<0){m--;day+=new Date(now.getFullYear(),now.getMonth(),0).getDate();}if(m<0){y--;m+=12;}main=`${y} anos`;label='Idade exata aproximada';row('Meses adicionais',`${m} meses`);row('Dias adicionais',`${day} dias`);break;}
    case 'dias-entre-datas': {const a=new Date(document.getElementById('start').value+'T00:00:00'),b=new Date(document.getElementById('end').value+'T00:00:00'),days=Math.round((b-a)/86400000);main=`${Math.abs(days)} dias`;label=days>=0?'Intervalo':'Intervalo (datas invertidas)';break;}
    case 'data-futura': {const d=new Date(document.getElementById('date').value+'T00:00:00');d.setDate(d.getDate()+val('days'));main=d.toLocaleDateString('pt-BR',{weekday:'long',day:'2-digit',month:'2-digit',year:'numeric'});label='Nova data';break;}
    case 'dia-semana': {const d=new Date(document.getElementById('date').value+'T00:00:00');main=d.toLocaleDateString('pt-BR',{weekday:'long'});label=d.toLocaleDateString('pt-BR');break;}
    case 'horas': {const [sh,sm]=document.getElementById('start').value.split(':').map(Number),[eh,em]=document.getElementById('end').value.split(':').map(Number);let mins=eh*60+em-sh*60-sm;if(mins<0)mins+=1440;main=formatMinutes(mins);label='Tempo decorrido';break;}
    case 'somar-horas': {const h=val('h1')+val('h2')+val('h3');main=formatHours(h);label='Total';break;}
    case 'receita': {const r=val('to')/val('from'),q=val('ingredient')*r;main=`${num(q)} ${document.getElementById('unit').options[document.getElementById('unit').selectedIndex].text}`;label='Quantidade ajustada';break;}
    case 'custo-receita': {const items=getRecipeItemsFromDOM(),servings=Math.max(1,val('servings')),total=items.reduce((s,x)=>s+(x.price||0),0);main=money(total);label='Custo total da receita';row('Custo por porção',money(total/servings));row('Ingredientes contabilizados',String(items.length));row('Itens sem preço',String(items.filter(x=>!x.price).length));note=items.some(x=>x.price===0)?'Itens sem preço foram considerados como R$ 0,00.': 'Os valores informados representam o custo considerado para a quantidade usada.';break;}
    case 'churrasco': {const r=calcChurrasco();main=`${num(r.carneTotal)} kg`;label='Carne total recomendada';row('Adultos',String(r.adultos));row('Crianças',String(r.criancas));row('Pessoas que bebem álcool',String(r.bebedores));row('Carne por adulto',`${num(r.carneAdulto*1000)} g`);row('Carne por criança',`${num(r.carneCrianca*1000)} g`);r.mixKg.forEach(x=>row(x[0],`${num(x[1])} kg`));row('Água',`${num(r.agua)} L`);row('Refrigerantes/sucos',`${num(r.naoAlcoolicas)} L`);row('Vinagrete',`${num(r.vinagreteKg)} kg`);row('Mandioca cozida',`${num(r.mandiocaKg)} kg`);row('Arroz cru',`${num(r.arrozKg)} kg`);row('Maionese de batata',`${num(r.mayoKg)} kg`);row('Farofa',`${num(r.farofaKg)} kg`);row('Pão de alho',`${r.garlicBread} unidades`);if(r.alcohol==='cerveja')row('Cerveja',`${num(r.cerveja)} L (≈ ${Math.ceil(r.cerveja/0.35)} un. de 350 ml)`);else if(r.alcohol==='vinho')row('Vinho',`${r.vinhoGarrafas} garrafas de 750 ml`);else if(r.alcohol==='drinks')row('Drinks',`${r.drinks} doses`);else row('Bebida alcoólica mista',`${num(r.alcoholTotal)} L/equivalente`);extraHtml=`<div class="suggestion-grid"><div class="suggestion-box"><h3>🥩 Mix de carnes</h3><ul>${r.mixKg.map(x=>`<li>${esc(x[0])}: <strong>${num(x[1])} kg</strong></li>`).join('')}</ul></div><div class="suggestion-box"><h3>🥗 Complementos sugeridos</h3><ul><li>Vinagrete</li><li>Mandioca cozida</li><li>Arroz branco</li><li>Maionese de batata</li><li>Farofa</li><li>Pão de alho</li></ul></div></div>`;note='As receitas completas de cada carne e acompanhamento aparecem abaixo do cálculo. As quantidades são referências práticas e devem ser ajustadas ao perfil dos convidados, horário e duração.';break;}
    case 'festa': {const r=calcFesta();main=`${r.guests} convidados`;label='Plano base da festa';row('Tipo',r.typeLabel);if(r.age!==null)row('Idade do aniversariante',`${r.age} anos`);row('Adultos',String(r.adultos));row('Crianças',String(r.criancas));row('Bebedores de álcool',String(r.bebedores));row('Salgados/pratos individuais',String(r.salgados));row('Doces',String(r.doces));row('Bolo',r.boloKg?`${num(r.boloKg)} kg`:'Não é prioridade no perfil');row('Bebidas não alcoólicas',`${num(r.naoAlcoolicas)} L`);row('Água',`${num(r.agua)} L`);if(r.alcohol==='beer')row('Cerveja',`${num(r.beerL)} L`);else if(r.alcohol==='wine')row('Vinho',`${r.wineBottles} garrafas de 750 ml`);else if(r.alcohol==='drinks')row('Drinks',`${r.drinkDoses} doses`);else if(r.alcohol==='mixed')row('Bebidas alcoólicas mistas',`${r.beerL?num(r.beerL)+' L de cerveja; ':''}${r.wineBottles?r.wineBottles+' garrafas de vinho; ':''}${r.drinkDoses?r.drinkDoses+' doses de drinks':''}`);row('Copos',String(r.copos));row('Pratos',String(r.pratos));row('Talheres',String(r.talheres));row('Cadeiras',String(r.cadeiras));extraHtml=`<div class="suggestion-box"><h3>🎯 Foco recomendado</h3><p>${esc(r.package.foco)}</p></div><div class="suggestion-grid">${r.package.itens.map(x=>`<div class="mini-suggestion"><strong>${esc(x[0])}</strong><span>${esc(x[1])}</span></div>`).join('')}</div>`;note=r.note;break;}
    case 'bolo': {const g=val('guests'),kg=g*(document.getElementById('event').value==='principal'?0.15:0.10);main=`${num(kg)} kg`;label='Bolo estimado';break;}
    case 'gelo': {const g=val('people'),h=val('hours');main=`${num(g*h*0.3)} kg`;label='Gelo estimado';note='Regra prática aproximada.';break;}
    case 'rescisao-clt': {const r=calcRescisao();main=money(r.total);label='Total estimado das verbas rescisórias';r.rows.forEach(x=>row(x[0],x[1]));row('Dias de aviso prévio considerados',String(r.noticeDays));if(r.fgtsFine)row('Base de FGTS usada na multa',money(r.baseFgts));note=r.note;break;}
    case 'clt-vs-pj': {const r=calcCLTVsPJ();main=money(r.pjMonthly);label='Faturamento PJ mensal de equivalência';row('CLT líquido mensal estimado',money(r.cltNet));row('INSS CLT estimado',money(r.inss));row('IRPF CLT estimado',money(r.ir));row('CLT anual de referência',money(r.cltAnnualValue));row('Reserva para 13º',money(r.thirteenthReserve));row('Reserva para férias + 1/3',money(r.vacationReserve));row('Equivalente mensal de FGTS',money(r.fgtsReserve));row('Benefícios preservados',money(r.benefitsReserve));row('Reserva de risco',money(r.riskReserve));row('Reserva previdenciária',money(r.retirementReserve));row('Custos fixos PJ',money(r.fixed));row('Impostos PJ informados',pct(r.tax));row('Meses com faturamento',String(r.billableMonths));row('Faturamento PJ anual alvo',money(r.pjAnnual));extraHtml=`<div class="breakdown-card"><h3>🧮 Como o Resolvei chegou ao valor</h3><p>O objetivo não é comparar somente “salário líquido”. A ferramenta transforma a remuneração CLT em uma <strong>meta anual de caixa</strong> e acrescenta as reservas que, no PJ, precisam ser financiadas pelo próprio profissional.</p><div class="result-sub"><div class="result-row"><span>Base mensal antes do imposto PJ</span><strong>${money(r.equivalenceMonthlyBeforePJTax)}</strong></div><div class="result-row"><span>Faturamento mensal necessário</span><strong>${money(r.pjMonthly)}</strong></div></div></div>`;note=r.note;break;}
    case 'dividir-pessoas': {const a=val('amount'),p=val('people');main=money(a/p);label='Por pessoa';row('Total',money(a));break;}
    default:return;
  }
  out.innerHTML=`<div class="result-box"><div class="result-label">${label}</div><div class="result-main">${main}</div>${rows.length?`<div class="result-sub">${rows.join('')}</div>`:''}${extraHtml?extraHtml:''}${note?`<div class="note">${note}</div>`:''}</div>`;
}
function kmSafe(x){return Number(x)||1;}
function convert(value,from,to,map){const base=value*map[from];return base/map[to];}
function formatHours(h){const total=Math.round(h*60),hh=Math.floor(total/60),mm=total%60;return `${hh}h ${String(mm).padStart(2,'0')}min`;}
function formatMinutes(min){return `${Math.floor(min/60)}h ${String(min%60).padStart(2,'0')}min`;}

function saveState(){ localStorage.setItem('resolvei_favs',JSON.stringify(getFavs())); }
function getFavs(){try{return JSON.parse(localStorage.getItem('resolvei_favs')||'[]')}catch{return[]}}
function isFav(id){return getFavs().includes(id)}
function toggleFav(id){const f=getFavs();const i=f.indexOf(id);if(i>=0)f.splice(i,1);else f.push(id);localStorage.setItem('resolvei_favs',JSON.stringify(f));updateFavCount();render();}
function updateFavCount(){const el=document.getElementById('favCount');if(el)el.textContent=getFavs().length}

function card(t){return `<article class="card tool-card"><button class="fav ${isFav(t.id)?'active':''}" data-fav="${t.id}" aria-label="Favoritar">${isFav(t.id)?'★':'☆'}</button><a href="#/ferramenta/${t.id}"><div class="tool-icon">${t.icon}</div><h3>${t.title}</h3><p>${t.desc}</p></a></article>`}
function categoryCard([id,c]){const count=tools.filter(t=>t.cat===id).length;return `<a class="card category-card" href="#/categoria/${id}"><div class="tool-icon">${c.icon}</div><h3>${c.name}</h3><p>${c.desc}</p><span class="chip">${count} ferramentas</span></a>`}
function home(){
  const p=popular.map(id=>tools.find(t=>t.id===id)).filter(Boolean);
  return `<section class="hero"><div class="brand" style="justify-content:center;margin-bottom:22px"><span class="brand-mark">✓</span><span>Resolvei</span></div><h1>Pequenas ferramentas para resolver grandes dúvidas.</h1><p>Calcule, compare, converta e planeje coisas do dia a dia sem cadastro e sem complicação.</p><div class="search-box"><span class="search-icon">⌕</span><input id="globalSearch" autocomplete="off" placeholder="Ex.: quanto vou gastar de gasolina numa viagem de 800 km?"></div><div class="quick-tags">${['porcentagem','tinta','combustível','piso','idade','churrasco'].map(x=>`<button class="tag" data-search="${x}">${x}</button>`).join('')}</div></section>
  <div class="kpi-row"><div class="card kpi"><strong>${tools.length}+</strong><span>ferramentas</span></div><div class="card kpi"><strong>${Object.keys(CATS).length}</strong><span>categorias</span></div><div class="card kpi"><strong>0</strong><span>cadastro obrigatório</span></div></div>
  <div class="section-head"><div><h2>Mais usadas</h2><p>Atalhos para resolver as dúvidas mais comuns.</p></div><a class="btn" href="#/ferramentas">Ver todas</a></div><div class="grid">${p.map(card).join('')}</div>
  <div class="section-head"><div><h2>Categorias</h2><p>Encontre ferramentas por assunto.</p></div></div><div class="category-grid">${Object.entries(CATS).map(categoryCard).join('')}</div>`;
}
function toolsPage(list=tools,title='Todas as ferramentas',sub='Escolha uma ferramenta ou pesquise pelo que você precisa.'){
  return `<div class="section-head"><div><h1 style="margin:0;letter-spacing:-.04em">${esc(title)}</h1><p>${esc(sub)}</p></div></div><div class="search-box" style="max-width:none;margin-bottom:20px"><span class="search-icon">⌕</span><input id="listSearch" placeholder="Buscar entre as ferramentas..."></div><div id="toolGrid" class="grid">${list.map(card).join('')}</div>`;
}
function categoriesPage(){return `<div class="section-head"><div><h1 style="margin:0;letter-spacing:-.04em">Categorias</h1><p>Explore o Resolvei por assunto.</p></div></div><div class="category-grid">${Object.entries(CATS).map(categoryCard).join('')}</div>`}
function toolPage(id){
  const t=tools.find(x=>x.id===id);if(!t)return `<div class="empty"><strong>Ferramenta não encontrada</strong><a class="btn" href="#/ferramentas">Voltar às ferramentas</a></div>`;
  if(id==='lista-compras') return `<div class="tool-page"><div class="breadcrumb"><a href="#/">Início</a> / <a href="#/categoria/outros">Outras utilidades</a> / ${esc(t.title)}</div><div class="tool-top"><div class="tool-icon">${t.icon}</div><div><h1>${esc(t.title)}</h1><p>${esc(t.desc)}</p></div></div>${toolUI(id)}</div>`;
  return `<div class="tool-page"><div class="breadcrumb"><a href="#/">Início</a> / <a href="#/categoria/${t.cat}">${CATS[t.cat].name}</a> / ${esc(t.title)}</div><div class="tool-top"><div class="tool-icon">${t.icon}</div><div><h1>${esc(t.title)}</h1><p>${esc(t.desc)}</p></div><button class="fav ${isFav(id)?'active':''}" data-fav="${id}" aria-label="Favoritar">${isFav(id)?'★':'☆'}</button></div>${toolUI(id)}<div class="notice"><strong>Sobre esta ferramenta:</strong> o Resolvei apresenta estimativas matemáticas para facilitar decisões cotidianas. Para obras, finanças, instalações ou situações que exijam responsabilidade técnica, use profissionais habilitados.</div><div class="section-head"><div><h2>Ferramentas relacionadas</h2></div></div><div class="grid">${tools.filter(x=>x.cat===t.cat&&x.id!==id).slice(0,4).map(card).join('')}</div></div>`;
}
function aboutPage(){return `<div class="tool-page"><div class="section-head"><div><h1>Sobre o Resolvei</h1><p>Um portal de microferramentas para tornar tarefas cotidianas mais rápidas.</p></div></div><section class="card panel"><h2>O conceito</h2><p>O Resolvei foi pensado como um "canivete digital": você entra, encontra uma ferramenta simples e sai com uma resposta clara. A prioridade é velocidade, legibilidade e utilidade.</p><h2>Como os resultados funcionam</h2><p>As ferramentas usam fórmulas e conversões explícitas no navegador. Os resultados são apresentados como estimativas quando fatores reais podem alterar o valor.</p><h2>Privacidade por padrão</h2><p>Favoritos, tema e a lista de compras são armazenados localmente no navegador. O projeto não exige cadastro para usar as ferramentas.</p></section></div>`}
function privacyPage(){return `<div class="tool-page"><div class="section-head"><div><h1>Privacidade</h1><p>Política inicial do site.</p></div></div><section class="card panel"><p>O Resolvei foi estruturado para funcionar sem cadastro. Dados de uso local, como favoritos e lista de compras, ficam no armazenamento do navegador. Caso sejam adicionados analytics, publicidade ou recursos externos no futuro, esta página deverá ser atualizada para descrever esses serviços e suas opções de privacidade.</p></section></div>`}
function favoritesPage(){const fav=getFavs(), list=tools.filter(t=>fav.includes(t.id)); return `<div class="section-head"><div><h1>Favoritos</h1><p>Suas ferramentas salvas neste navegador.</p></div></div>${list.length?`<div class="grid">${list.map(card).join('')}</div>`:`<div class="card empty"><strong>Nenhum favorito ainda.</strong>Clique na estrela de uma ferramenta para adicioná-la aqui.</div>`}`}
function render(){
  const hash=location.hash||'';
  let route=location.pathname.replace(/^\/+|\/+$/g,'');
  if(!route || route==='index.html') route=hash.replace(/^#\/?/,'');
  const routePath=route.split('?')[0];
  const parts=(routePath||'').split('/').filter(Boolean);
  let html='';
  if(!parts[0]) html=home();
  else if(parts[0]==='ferramentas') html=toolsPage();
  else if(parts[0]==='categorias') html=categoriesPage();
  else if(parts[0]==='categoria') {const id=parts[1];const c=CATS[id];html=c?toolsPage(tools.filter(t=>t.cat===id),`${c.icon} ${c.name}`,c.desc):`<div class="empty">Categoria não encontrada.</div>`;}
  else if(parts[0]==='ferramenta') html=toolPage(parts[1]);
  else if(parts[0]==='favoritos') html=favoritesPage();
  else if(parts[0]==='conta') html=resolveiAccountPage();
  else if(parts[0]==='conectar-api') html=resolveiApiPage();
  else if(parts[0]==='sobre') html=aboutPage();
  else if(parts[0]==='privacidade') html=privacyPage();
  else html=home();
  document.getElementById('app').innerHTML=html; updateFavCount(); bind();
  const t=parts[0]==='ferramenta'?tools.find(x=>x.id===parts[1]):null;
  document.title=t?`${t.title} | Resolvei`:parts[0]==='categoria'&&CATS[parts[1]]?`${CATS[parts[1]].name} | Resolvei`:'Resolvei — Ferramentas úteis para o dia a dia';
  window.scrollTo({top:0,behavior:'auto'});
}
function smartSearch(q){
  const s=q.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  const parts=s.split(/\s+/).filter(Boolean); 
  const scored=tools.map(t=>{const hay=`${t.title} ${t.desc} ${t.tags}`.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');let score=0;parts.forEach(w=>{if(hay.includes(w))score+=w.length>3?2:1});return{t,score}}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).map(x=>x.t);
  if(/gasolina|etanol|combustivel|viagem/.test(s)){
    const m=s.match(/(\d+(?:[.,]\d+)?)\s*(km|quilometros|quilometro)/); if(m){const target=location.origin+location.pathname+'#/ferramenta/combustivel-viagem'; return `<div class="notice">Parece que você quer calcular uma viagem de <strong>${m[1]} km</strong>. <a href="#/ferramenta/combustivel-viagem">Abrir calculadora de combustível →</a></div>`;}
  }
  return scored.length?`<div class="grid">${scored.slice(0,12).map(card).join('')}</div>`:`<div class="card empty"><strong>Nenhuma ferramenta encontrada.</strong>Tente termos como “piso”, “gasolina”, “juros” ou “idade”.</div>`;
}
function universalFileConverterUI(id){
  const cfg={
    'jpg-png-webp':{title:'Converter imagem',accept:'.jpg,.jpeg,.png,.webp,.bmp'},'heic-jpg':{title:'HEIC → JPG',accept:'.heic,.heif'},'imagem-pdf':{title:'Imagem → PDF',accept:'.jpg,.jpeg,.png,.webp,.bmp',multiple:true},
    'pdf-imagens-zip':{title:'PDF → imagens ZIP',accept:'.pdf'},'mp4-mp3':{title:'MP4 → MP3',accept:'.mp4,.mov,.avi,.mkv,.webm'},'mp4-gif':{title:'MP4 → GIF',accept:'.mp4,.mov,.webm,.avi'},
    'csv-xlsx':{title:'CSV ↔ XLSX',accept:'.csv,.xlsx'},'zip-arquivos':{title:'Comprimir arquivos',accept:'*/*',multiple:true},'mov-mp4':{title:'MOV → MP4',accept:'.mov,.mp4'},
    'jpg-heic':{title:'JPG → HEIC',accept:'.jpg,.jpeg,.png,.webp'},'imagem-comprimir':{title:'Comprimir imagem',accept:'.jpg,.jpeg,.png,.webp'},
    'docx-pdf':{title:'DOCX → PDF',accept:'.docx'},'pdf-docx':{title:'PDF → DOCX',accept:'.pdf'},'pdf-txt':{title:'PDF → TXT',accept:'.pdf'},'txt-pdf':{title:'TXT → PDF',accept:'.txt'},
    'pdf-xlsx':{title:'PDF → XLSX',accept:'.pdf'},'xlsx-csv':{title:'XLSX → CSV',accept:'.xlsx'},'audio-mp3-wav':{title:'Áudio MP3 ↔ WAV',accept:'.mp3,.wav'},
    'audio-ogg':{title:'Áudio → OGG',accept:'.mp3,.wav,.ogg'},'video-webm':{title:'Vídeo → WEBM',accept:'.mp4,.mov,.avi,.mkv,.webm'},
    'video-avi':{title:'Vídeo → AVI',accept:'.mp4,.mov,.mkv,.webm'},'video-audio':{title:'Vídeo → áudio',accept:'.mp4,.mov,.avi,.mkv,.webm'},
    'svg-png':{title:'SVG → PNG',accept:'.svg'},'png-ico':{title:'PNG → ICO',accept:'.png'},'imagem-redimensionar':{title:'Redimensionar imagem',accept:'.jpg,.jpeg,.png,.webp'},
    'pdf-comprimir':{title:'Comprimir PDF',accept:'.pdf'},'arquivos-zip':{title:'ZIP de vários arquivos',accept:'*/*',multiple:true}
  }[id]||{};
  const dims=['imagem-redimensionar'].includes(id)?'<div class="form-grid"><div class="field"><label for="uWidth">Largura (px)</label><input id="uWidth" type="number" min="1" value="1600"></div><div class="field"><label for="uHeight">Altura (px)</label><input id="uHeight" type="number" min="1" value="1200"></div></div>':'';
  return `<div class="tool-layout"><section class="card panel"><h2>${cfg.title||'Conversor'}</h2><div class="notice">Processamento automático do Resolvei. Para vídeo/áudio, o servidor precisa ter FFmpeg. Conversões de documentos priorizam o texto e podem não preservar todo o layout.</div><div class="field full"><label for="uFile">Arquivo</label><input id="uFile" type="file" accept="${cfg.accept||'*/*'}" ${cfg.multiple?'multiple':''}></div>${dims}<div class="form-grid"><div class="field"><label for="uFormat">Formato de saída</label><select id="uFormat"><option value="">Selecione o arquivo</option></select></div><div class="field"><label for="uQuality">Qualidade</label><input id="uQuality" type="number" min="10" max="100" value="85"></div></div><div class="actions"><button class="btn primary" id="uBtn" disabled>Converter</button><button class="btn ghost" id="uReset" type="button">Limpar</button></div><div id="uStatus" class="notice">Nenhum arquivo selecionado.</div></section><section id="uResult"><div class="result-box"><div class="result-label">Resultado</div><div class="result-main">—</div><p>O arquivo convertido aparecerá aqui.</p></div></section></div>`;
}
function bindUniversalFileConverter(id){
  const f=document.getElementById('uFile'),fmt=document.getElementById('uFormat'),btn=document.getElementById('uBtn'),st=document.getElementById('uStatus'),res=document.getElementById('uResult');
  const maps={
    'jpg-png-webp':[['jpg','JPG'],['png','PNG'],['webp','WEBP']],'heic-jpg':[['jpg','JPG']],'imagem-pdf':[['pdf','PDF']],'pdf-imagens-zip':[['zip','ZIP']],
    'mp4-mp3':[['mp3','MP3']],'mp4-gif':[['gif','GIF']],'csv-xlsx':[['xlsx','XLSX'],['csv','CSV']],'zip-arquivos':[['zip','ZIP']],'mov-mp4':[['mp4','MP4']],
    'jpg-heic':[['heic','HEIC']],'imagem-comprimir':[['jpg','JPG'],['png','PNG'],['webp','WEBP']],'docx-pdf':[['pdf','PDF']],'pdf-docx':[['docx','DOCX']],
    'pdf-txt':[['txt','TXT']],'txt-pdf':[['pdf','PDF']],'pdf-xlsx':[['xlsx','XLSX']],'xlsx-csv':[['csv','CSV']],'audio-mp3-wav':[['mp3','MP3'],['wav','WAV']],
    'audio-ogg':[['ogg','OGG']],'video-webm':[['webm','WEBM']],'video-avi':[['avi','AVI']],'video-audio':[['mp3','MP3']],
    'svg-png':[['png','PNG']],'png-ico':[['ico','ICO']],'imagem-redimensionar':[['jpg','JPG'],['png','PNG'],['webp','WEBP']],
    'pdf-comprimir':[['pdf','PDF']],'arquivos-zip':[['zip','ZIP']]
  };
  const update=()=>{const files=[...(f?.files||[])];if(!files.length)return;const ext=(files[0].name.split('.').pop()||'').toLowerCase();let opts=maps[id]||[];if(id==='csv-xlsx')opts=ext==='csv'?[['xlsx','XLSX']]:[['csv','CSV']];if(id==='audio-mp3-wav')opts=ext==='mp3'?[['wav','WAV']]:[['mp3','MP3']];if(id==='jpg-png-webp'||id==='imagem-comprimir'||id==='imagem-redimensionar')opts=opts.filter(x=>x[0]!==ext.replace('jpeg','jpg'));fmt.innerHTML=opts.map(x=>'<option value="'+x[0]+'">'+x[1]+'</option>').join('');btn.disabled=!opts.length;st.innerHTML=files.length>1?files.length+' arquivos selecionados.':('Arquivo: <strong>'+esc(files[0].name)+'</strong> · '+num(files[0].size/1024/1024)+' MB');};
  f?.addEventListener('change',update);
  btn?.addEventListener('click',async()=>{const files=[...(f?.files||[])],out=fmt?.value;if(!files.length||!out)return;btn.disabled=true;st.textContent='Enviando e convertendo...';try{const fd=new FormData();files.forEach(x=>fd.append('files',x));fd.append('output_format',out);fd.append('quality',document.getElementById('uQuality')?.value||85);fd.append('tool_id',id);fd.append('width',document.getElementById('uWidth')?.value||0);fd.append('height',document.getElementById('uHeight')?.value||0);const rr=await fetch('/api/files/convert-plus',{method:'POST',body:fd});if(!rr.ok){let d={};try{d=await rr.json()}catch{}throw new Error(d.detail||'Não foi possível converter.');}const blob=await rr.blob(),cd=rr.headers.get('content-disposition')||'',m=cd.match(/filename="?([^"]+)"?/i),name=m?m[1]:'resolvei-convertido.'+out,url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.className='btn primary';res.innerHTML='<div class="result-box"><div class="result-label">Conversão concluída</div><div class="result-main">✓</div><p>'+esc(name)+'</p></div>';res.querySelector('.result-box').appendChild(a);st.textContent='✅ Concluído.';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){st.innerHTML='⚠️ '+esc(e.message);}finally{btn.disabled=false;}});document.getElementById('uReset')?.addEventListener('click',()=>{f.value='';fmt.innerHTML='<option>Selecione o arquivo</option>';btn.disabled=true;st.textContent='Nenhum arquivo selecionado.';});
}

function bind(){
  document.querySelectorAll('[data-fav]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();toggleFav(b.dataset.fav)}));
  const gs=document.getElementById('globalSearch'); if(gs){gs.addEventListener('keydown',e=>{if(e.key==='Enter'){const q=gs.value.trim(); if(q){location.hash='#/ferramentas?q='+encodeURIComponent(q)}}});}
  document.querySelectorAll('[data-search]').forEach(b=>b.addEventListener('click',()=>{location.hash='#/ferramentas?q='+encodeURIComponent(b.dataset.search)}));
  const ls=document.getElementById('listSearch'); if(ls){const q=new URLSearchParams((location.search||'').replace(/^\?/,'') || location.hash.split('?')[1] || '').get('q')||'';ls.value=q; const grid=document.getElementById('toolGrid'); if(q)grid.innerHTML=smartSearch(q).replace(/^<div class="notice">/, '<div class="notice">'); ls.addEventListener('input',()=>{const r=smartSearch(ls.value);grid.innerHTML=r;document.querySelectorAll('[data-fav]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();toggleFav(b.dataset.fav)}));});}
  const calc=document.getElementById('calcBtn'); const rid=location.pathname.match(/ferramenta\/([^/]+)/)?.[1] || location.hash.match(/ferramenta\/([^?]+)/)?.[1]; if(calc&&rid)calc.addEventListener('click',()=>calculate(rid));
  if(rid==='conversor-arquivos')bindFileConverter();
  if(['jpg-png-webp','heic-jpg','imagem-pdf','pdf-imagens-zip','mp4-mp3','mp4-gif','csv-xlsx','zip-arquivos','mov-mp4','jpg-heic','imagem-comprimir'].includes(rid))bindUniversalFileConverter(rid);
  if(rid==='por-quanto-vender'){
    const btn=document.getElementById('sellCalcBtn'), reset=document.getElementById('sellResetBtn');
    if(btn)btn.addEventListener('click',()=>{
      const n=id=>Math.max(0,Number(document.getElementById(id)?.value)||0);
      const product=document.getElementById('sellProduct')?.value.trim();
      const qty=Math.max(1,n('sellQuantity'));
      const production=n('sellCost'), packaging=n('sellPackaging'), other=n('sellOther');
      const hours=n('sellHours'), hourly=n('sellHourly'), fixed=n('sellFixed');
      const monthlyQty=Math.max(1,n('sellMonthlyQty')||100);
      const fees=Math.min(100,n('sellFees')), tax=Math.min(100,n('sellTax')), margin=Math.min(90,n('sellMargin')||30);
      const market=n('sellMarket'), goal=n('sellGoal');
      const city=document.getElementById('sellCity')?.value.trim()||'';
      const state=(document.getElementById('sellState')?.value.trim()||'').toUpperCase();
      const out=document.getElementById('sellResult');
      if(!product){out.innerHTML='<div class="notice">Digite o produto que você vende.</div>';return;}
      const labor=hours*hourly;
      const fixedBatch=(fixed/monthlyQty)*qty;
      const totalBatch=production+packaging*qty+other+labor+fixedBatch;
      const unitCost=totalBatch/qty;
      const rate=(fees+tax)/100;
      const breakEven=rate<1?unitCost/(1-rate):Infinity;
      const target=rate+(margin/100);
      const suggested=target<1?unitCost/(1-target):Infinity;
      const price20=rate<0.8?unitCost/(1-rate-0.20):Infinity;
      const price40=rate<0.6?unitCost/(1-rate-0.40):Infinity;
      const contribution=suggested*(1-rate)-unitCost;
      const unitsForGoal=contribution>0?Math.ceil(goal/contribution):0;
      const monthlyRevenue=suggested*monthlyQty;
      const monthlyProfit=contribution*monthlyQty;
      const marginReal=suggested>0?(contribution/suggested)*100:0;
      const marketNote=market>0?(suggested>market?`Seu preço calculado fica ${pct((suggested/market-1)*100)} acima do preço informado.`:`Seu preço calculado fica ${pct((1-suggested/market)*100)} abaixo do preço informado.`):'';
      const cityNote=city?` Referência informada: ${esc(city)}/${esc(state)}. A cidade não altera a matemática; use-a para comparar seus custos e concorrentes locais.`:'';
      out.innerHTML=`<div class="result-box">
        <div class="result-label">Preço recomendado</div><div class="result-main">${money(suggested)}</div>
        <p><strong>Margem calculada: ${pct(marginReal)}.</strong>${cityNote}</p>
        <div class="form-grid" style="margin-top:14px">
          <div><strong>Custo real por unidade</strong><br>${money(unitCost)}</div>
          <div><strong>Ponto de equilíbrio</strong><br>${money(breakEven)}<br><small>Preço para não ter prejuízo.</small></div>
          <div><strong>Preço com 20% de lucro</strong><br>${money(price20)}</div>
          <div><strong>Preço com 40% de lucro</strong><br>${money(price40)}</div>
          <div><strong>Lucro por unidade</strong><br>${money(contribution)}</div>
          <div><strong>Lucro no lote</strong><br>${money(contribution*qty)}</div>
        </div>
        <div class="notice" style="margin-top:16px"><strong>📊 Visão de negócio</strong><br>Seu lote custa <strong>${money(totalBatch)}</strong>. Vendendo ${num(qty)} unidades a ${money(suggested)}, o faturamento do lote será <strong>${money(suggested*qty)}</strong> e o resultado após custos e taxas será <strong>${money(contribution*qty)}</strong>.</div>
        <div class="notice" style="margin-top:12px"><strong>🎯 Meta mensal</strong><br>Com ${num(monthlyQty)} unidades/mês, o faturamento estimado é <strong>${money(monthlyRevenue)}</strong> e o lucro estimado é <strong>${money(monthlyProfit)}</strong>.${goal>0?(unitsForGoal?` Para buscar ${money(goal)} de lucro por mês, venda aproximadamente <strong>${num(unitsForGoal)} unidades/mês</strong>.`:' A meta não é atingível com os parâmetros atuais; revise preço, margem ou custos.') : ''}</div>
        ${market>0?`<div class="notice" style="margin-top:12px"><strong>🏪 Comparação local</strong><br>Você informou ${money(market)} como referência. ${marketNote} Se o mercado não aceitar seu preço, revise tamanho, embalagem, custo ou valor percebido antes de simplesmente cortar sua margem.</div>`:''}
        <div style="margin-top:14px"><strong>Checklist do consultor</strong><ul>
          <li>${production>0?'✓':'⚠️'} Ingredientes/preparo: ${money(production)} por lote.</li>
          <li>${labor>0?'✓':'⚠️'} Mão de obra: ${money(labor)} por lote.</li>
          <li>${fixed>0?'✓':'⚠️'} Custos fixos rateados: ${money(fixedBatch)} por lote.</li>
          <li>${fees+tax>0?'✓':'⚠️'} Taxas + impostos: ${pct(fees+tax)} da venda.</li>
          <li>${market>0?'✓':'ℹ️'} Concorrentes: ${market>0?'preço informado':'não informado'}.</li>
        </ul></div>
        <small><strong>Importante:</strong> o preço recomendado é uma referência matemática. Se o público não aceitar o valor, os caminhos são reduzir custos, aumentar valor percebido ou ajustar produto/porção. ${esc('Análise para '+product+'.')}</small>
      </div>`;
    });
    if(reset)reset.addEventListener('click',()=>{
      ['sellProduct','sellCost','sellPackaging','sellOther','sellHours','sellHourly','sellFixed','sellFees','sellTax','sellMarket','sellGoal'].forEach(id=>{const e=document.getElementById(id);if(e)e.value='';});
      document.getElementById('sellQuantity').value='10';document.getElementById('sellMonthlyQty').value='100';document.getElementById('sellMargin').value='30';document.getElementById('sellCity').value='Cuiabá';document.getElementById('sellState').value='MT';document.getElementById('sellResult').innerHTML='';
    });
  }
  if(rid==='custo-receita'){const box=document.getElementById('recipeItems');if(box&&!box.children.length){addRecipeItemRow({name:'',qty:1,unit:'g',price:0});addRecipeItemRow({name:'',qty:1,unit:'g',price:0});addRecipeItemRow({name:'',qty:1,unit:'g',price:0});} const ar=document.getElementById('addRecipeItem');if(ar)ar.addEventListener('click',()=>addRecipeItemRow()); const ai=document.getElementById('analyzeRecipeBtn');if(ai)ai.addEventListener('click',analyzeRecipeAI);}
  if(rid==='churrasco'){/* sugestões são renderizadas junto da ferramenta */}
  if(['placas-solares','posicao-solar'].includes(rid)){bindSolarCalculatorInteractions();}
  if(rid==='festa'){const type=document.getElementById('partyType');if(type)type.addEventListener('change',()=>{const a=document.getElementById('age'); if(a)a.closest('.field').style.display=type.value.startsWith('aniversario-')?'':'none';}); if(type&&!type.value.startsWith('aniversario-')){const a=document.getElementById('age');if(a)a.closest('.field').style.display='none';} const ai=document.getElementById('aiPartyBtn');if(ai)ai.addEventListener('click',refinePartyAI); }
  const reset=document.getElementById('resetBtn'); if(reset)reset.addEventListener('click',()=>{location.reload();});
  const add=document.getElementById('addItem');if(add)add.addEventListener('click',addShoppingItem);
  const clear=document.getElementById('clearList');if(clear)clear.addEventListener('click',()=>{localStorage.removeItem('resolvei_list');renderList();});
  const copy=document.getElementById('copyShopping');if(copy)copy.addEventListener('click',async()=>{const txt=document.getElementById('shoppingText')?.value||'';try{await navigator.clipboard.writeText(txt);copy.textContent='✅ Copiado!';setTimeout(()=>copy.textContent='📋 Copiar lista',1200)}catch{alert('Não foi possível copiar automaticamente. Selecione e copie o texto.')}});
  const dl=document.getElementById('downloadShopping');if(dl)dl.addEventListener('click',downloadShoppingTxt);
  if(document.getElementById('list'))renderList();
}

async function analyzeRecipeAI(){
  const url=document.getElementById('recipeUrl')?.value?.trim(); const status=document.getElementById('recipeAiStatus'); if(!url){if(status)status.textContent='Informe a URL da receita.';return;} if(status)status.textContent='🔎 Lendo a receita, organizando ingredientes e estimando preços locais...';
  const aiSession=window.resolveiAiSession||{}; const provider=aiSession.provider||''; const apiKey=aiSession.apiKey||''; const model=aiSession.model||'';
  try{const headers={'Content-Type':'application/json'};if(typeof resolveiUser!=='undefined'&&resolveiUser)headers.Authorization='Bearer '+await resolveiToken();const res=await fetch('/api/recipe/analyze',{method:'POST',headers,body:JSON.stringify({url,city:document.getElementById('recipeCity')?.value||'',state:document.getElementById('recipeState')?.value||'',provider,api_key:apiKey,model})}); const data=await res.json(); if(!res.ok)throw new Error(data.detail||'Falha ao analisar receita'); const box=document.getElementById('recipeItems');box.innerHTML='';(data.ingredients||[]).forEach(x=>addRecipeItemRow({name:x.name||'',qty:x.quantity||1,unit:x.unit||'un.',price:x.recipe_price||0})); if(status)status.innerHTML=`✅ Receita analisada. ${data.ingredients?.length||0} ingredientes encontrados.${data.price_note?`<br>${esc(data.price_note)}`:''}`; const result=document.getElementById('result');if(result&&data.price_summary){result.innerHTML=`<div class="result-box"><div class="result-label">Estimativa da compra</div><div class="result-main">${money(data.price_summary.total||0)}</div><div class="result-sub">${(data.price_summary.items||[]).map(x=>`<div class="result-row"><span>${esc(x.name)}</span><strong>${x.price?money(x.price):'sem preço'}</strong></div>`).join('')}</div><div class="note">Os preços regionais dependem da disponibilidade e da fonte consultada. Confirme no estabelecimento antes de comprar.</div></div>`;} }catch(e){if(status)status.innerHTML=`⚠️ ${esc(e.message)}<br>Você ainda pode inserir os ingredientes manualmente.`;}
}
async function refinePartyAI(){
  const status=document.getElementById('partyAiStatus'); if(status)status.textContent='✨ Consultando a IA para adaptar o planejamento ao perfil da festa...';
  const payload={type:document.getElementById('partyType')?.value,age:val('age'),adults:val('adults'),kids:val('kids'),hours:val('hours'),drinkers:val('partyDrinkers'),alcohol:document.getElementById('partyAlcohol')?.value,budgetPerPerson:val('budgetPerPerson')};
  try{const headers={'Content-Type':'application/json'};if(typeof resolveiUser!=='undefined'&&resolveiUser)headers.Authorization='Bearer '+await resolveiToken();const res=await fetch('/api/party/suggest',{method:'POST',headers,body:JSON.stringify(payload)});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Falha na IA');renderPartyAI(data);if(status)status.textContent='✅ Plano refinado pela IA, mantendo as quantidades-base do Resolvei como referência.';}catch(e){if(status)status.textContent=`⚠️ ${e.message} O cálculo base continua disponível.`;}
}
function renderPartyAI(data){const result=document.getElementById('result');if(!result)return;const sections=(data.sections||[]).map(sec=>`<div class="ai-section"><h3>${esc(sec.title||'Sugestões')}</h3><ul>${(sec.items||[]).map(x=>`<li><strong>${esc(x.name||'Item')}</strong> — ${esc(x.quantity||'')} ${x.reason?`<span>${esc(x.reason)}</span>`:''}</li>`).join('')}</ul></div>`).join('');result.innerHTML=`<div class="result-box"><div class="result-label">Planejamento inteligente</div><div class="result-main">${esc(data.summary||'Plano personalizado')}</div>${sections}<div class="note">A IA auxilia na organização e sugestões; confira quantidades e restrições reais do local/evento.</div></div>`;}
function addShoppingItem(){const name=document.getElementById('itemName')?.value?.trim();const qty=Number(document.getElementById('itemQty')?.value||0);const unit=document.getElementById('itemUnit')?.value||'un.';const priceRaw=document.getElementById('itemPrice')?.value;const price=priceRaw===''?null:Number(priceRaw);if(!name||qty<=0)return;const s=loadShopping();s.push({name,qty,unit,price,done:false});localStorage.setItem('resolvei_list',JSON.stringify(s));document.getElementById('itemName').value='';document.getElementById('itemQty').value='1';document.getElementById('itemPrice').value='';renderList();}
function loadShopping(){try{const arr=JSON.parse(localStorage.getItem('resolvei_list')||'[]');return arr.map(x=>x.name?x:{name:String(x.text||''),qty:1,unit:'un.',price:null,done:!!x.done});}catch{return[]}}
function shoppingText(s){const lines=['🛒 *LISTA DE COMPRAS*',''];let total=0;const active=s.filter(x=>!x.done);active.forEach((x,i)=>{const p=Number(x.price||0);if(x.price!==null&&x.price!==undefined)total+=p;lines.push(`${i+1}. 🛍️ ${x.name} — ${num(x.qty)} ${x.unit}${x.price!==null&&x.price!==undefined?` — ${money(p)}`:''}`)});lines.push('');lines.push(`💰 *TOTAL: ${money(total)}*`);lines.push('');lines.push('📝 Valores marcados são os preços informados/estimados. Itens sem valor não entram no total.');return lines.join('\n');}
function renderList(){const box=document.getElementById('list');if(!box)return;const s=loadShopping();box.innerHTML=s.length?`<div class="shopping-rows">${s.map((x,i)=>`<div class="shopping-row ${x.done?'done':''}"><label><input type="checkbox" ${x.done?'checked':''} data-item="${i}"><span>🛍️ <strong>${esc(x.name)}</strong><small>${num(x.qty)} ${esc(x.unit)}${x.price!==null&&x.price!==undefined?` · ${money(x.price)}`:''}</small></span></label><button class="btn" data-del="${i}">×</button></div>`).join('')}</div>`:'Sua lista está vazia. Adicione itens acima.';const txt=document.getElementById('shoppingText');if(txt)txt.value=shoppingText(s);const total=s.reduce((sum,x)=>sum+(x.done?0:(x.price!=null?Number(x.price)||0:0)),0);const totalEl=document.getElementById('shoppingTotal');if(totalEl)totalEl.textContent=`Total: ${money(total)}`;box.querySelectorAll('[data-item]').forEach(c=>c.addEventListener('change',()=>{s[c.dataset.item].done=c.checked;localStorage.setItem('resolvei_list',JSON.stringify(s));renderList()}));box.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click',()=>{s.splice(Number(b.dataset.del),1);localStorage.setItem('resolvei_list',JSON.stringify(s));renderList()}));}
function downloadShoppingTxt(){const text=document.getElementById('shoppingText')?.value||'';const blob=new Blob([text],{type:'text/plain;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='lista-de-compras-resolvei.txt';a.click();URL.revokeObjectURL(a.href);}
document.getElementById('year').textContent=new Date().getFullYear();
const savedTheme=localStorage.getItem('resolvei_theme');if(savedTheme)document.documentElement.dataset.theme=savedTheme;
document.getElementById('themeToggle').addEventListener('click',()=>{const dark=document.documentElement.dataset.theme==='dark';document.documentElement.dataset.theme=dark?'':'dark';localStorage.setItem('resolvei_theme',dark?'light':'dark');});
window.addEventListener('hashchange',render); render();

/* =========================
   Resolvei — Firebase Auth + Minhas IAs
   ========================= */
const RESOLVEI_FIREBASE_CONFIG = {
  apiKey:"AIzaSyBox8tior0HX5T6ox2ZNNo9fbzUkHxw8go",authDomain:"resolvei-c95d1.firebaseapp.com",
  projectId:"resolvei-c95d1",storageBucket:"resolvei-c95d1.firebasestorage.app",
  messagingSenderId:"671425023175",appId:"1:671425023175:web:deb8ce2174b07e6c16c2e2"
};
let resolveiAuth=null,resolveiDb=null,resolveiUser=null;
function resolveiFirebaseInit(){
  if(!window.firebase||resolveiAuth)return;
  if(!firebase.apps.length)firebase.initializeApp(RESOLVEI_FIREBASE_CONFIG);
  resolveiAuth=firebase.auth();resolveiDb=firebase.firestore();
  resolveiAuth.onAuthStateChanged(user=>{resolveiUser=user||null;const n=document.getElementById("accountNav");if(n)n.textContent=user?"👤 Minha conta":"👤 Entrar";if((location.hash||"").includes("conta")||(location.hash||"").includes("conectar-api"))render();});
}
async function resolveiToken(){if(!resolveiUser)throw new Error("Faça login no Resolvei.");return resolveiUser.getIdToken();}
function resolveiAccountPage(){
 if(!resolveiUser)return `<div class="tool-layout"><section class="card panel auth-card"><span class="eyebrow">CONTA RESOLVEI</span><h1>Entre para usar as funções de IA</h1><p>Use Google ou seu e-mail e senha. Ao entrar com Google, o Gemini do Resolvei fica disponível sem você precisar colar uma chave pessoal.</p><button class="btn primary full" id="googleLogin">Continuar com Google</button><div class="auth-divider"><span>ou</span></div><div class="form-grid"><div class="field"><label for="authEmail">E-mail</label><input id="authEmail" type="email"></div><div class="field"><label for="authPassword">Senha</label><input id="authPassword" type="password" autocomplete="current-password"></div></div><div class="row-actions"><button class="btn primary" id="emailLogin">Entrar</button><button class="btn" id="emailSignup">Criar conta</button></div><div id="authMsg" class="notice" hidden></div></section></div>`;
 return `<div class="tool-layout"><section class="card panel"><span class="eyebrow">MINHA CONTA</span><h1>${esc(resolveiUser.displayName||"Minha conta")}</h1><p>${esc(resolveiUser.email||"")}</p><div class="account-grid"><a class="card account-card" href="#/conectar-api"><strong>🔌 Conectar API</strong><span>Gerencie suas conexões de IA.</span></a></div><div class="row-actions"><button class="btn" id="logoutBtn">Sair</button></div></section></div>`;
}
const RESOLVEI_PROVIDERS={gemini:{name:"Google Gemini",icon:"✨",defaultModel:"gemini-3.8-flash"},openai:{name:"OpenAI",icon:"◉",defaultModel:"gpt-4.1-mini"},anthropic:{name:"Anthropic Claude",icon:"◆",defaultModel:"claude-3-5-haiku-latest"},openrouter:{name:"OpenRouter",icon:"↗",defaultModel:"openai/gpt-4.1-mini"}};
function resolveiApiPage(){
 if(!resolveiUser)return `<div class="tool-layout"><section class="card panel"><h1>🔌 Conectar API</h1><p>Entre no Resolvei para conectar uma IA.</p><a class="btn primary" href="#/conta">Entrar / Criar conta</a></section></div>`;
 return `<div class="tool-layout"><section class="card panel"><span class="eyebrow">MINHAS IAS</span><h1>🔌 Conectar API</h1><p>Suas chaves são enviadas ao servidor por HTTPS e armazenadas criptografadas. Elas não ficam no código do site.</p><div class="notice"><strong>Gemini:</strong> usuários autenticados podem usar o Gemini do Resolvei sem cadastrar uma chave própria.</div><div class="provider-grid">${Object.entries(RESOLVEI_PROVIDERS).map(([id,p])=>`<div class="provider-card"><div class="provider-title"><span class="provider-icon">${p.icon}</span><strong>${p.name}</strong><span class="provider-status" id="status-${id}">Verificando…</span></div><label class="field"><span>API Key</span><input id="key-${id}" type="password" autocomplete="off" placeholder="Cole sua chave (opcional no Gemini)"></label><label class="field"><span>Modelo (opcional)</span><input id="model-${id}" value="${p.defaultModel}"></label><div class="row-actions"><button class="btn primary" data-connect-ai="${id}">Conectar</button><button class="btn" data-remove-ai="${id}">Desconectar</button></div></div>`).join("")}</div><div id="aiMsg" class="notice" hidden></div></section></div>`;
}
async function resolveiRefreshStatuses(){
 try{const token=await resolveiToken();const r=await fetch("/api/ai/connections",{headers:{Authorization:"Bearer "+token}});if(!r.ok)throw new Error("Backend Firebase não configurado no servidor.");const d=await r.json();const map={};d.connections.forEach(x=>map[x.provider]=x);Object.keys(RESOLVEI_PROVIDERS).forEach(id=>{const e=document.getElementById("status-"+id);if(e)e.textContent=map[id]?.connected?"🟢 Conectada":"Não conectada";});}
 catch(e){document.querySelectorAll(".provider-status").forEach(x=>x.textContent="⚠️ Servidor não configurado");}
}
function resolveiBindAuth(){
 if(!resolveiAuth)return;
 document.getElementById("googleLogin")?.addEventListener("click",async()=>{try{await resolveiAuth.signInWithPopup(new firebase.auth.GoogleAuthProvider());location.hash="#/conta";}catch(e){const m=document.getElementById("authMsg");if(m){m.hidden=false;m.textContent=e.message;}}});
 const email=()=>document.getElementById("authEmail")?.value.trim(),pass=()=>document.getElementById("authPassword")?.value||"";
 document.getElementById("emailLogin")?.addEventListener("click",async()=>{try{await resolveiAuth.signInWithEmailAndPassword(email(),pass());location.hash="#/conta";}catch(e){const m=document.getElementById("authMsg");if(m){m.hidden=false;m.textContent=e.message;}}});
 document.getElementById("emailSignup")?.addEventListener("click",async()=>{try{await resolveiAuth.createUserWithEmailAndPassword(email(),pass());location.hash="#/conta";}catch(e){const m=document.getElementById("authMsg");if(m){m.hidden=false;m.textContent=e.message;}}});
 document.getElementById("logoutBtn")?.addEventListener("click",async()=>{await resolveiAuth.signOut();location.hash="#/conta";});
 document.querySelectorAll("[data-connect-ai]").forEach(b=>b.addEventListener("click",async()=>{try{const provider=b.dataset.connectAi,key=document.getElementById("key-"+provider)?.value.trim()||"",model=document.getElementById("model-"+provider)?.value.trim();if(!key&&provider==="gemini"){const m=document.getElementById("aiMsg");if(m){m.hidden=false;m.textContent="✅ O Gemini do Resolvei já está disponível para sua conta. Para usar sua própria chave do Gemini, cole-a no campo acima.";};await resolveiRefreshStatuses();return;}if(!key)throw new Error("Informe a API Key.");const token=await resolveiToken();const r=await fetch("/api/ai/connections",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({provider,api_key:key,model})});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Não foi possível conectar.");document.getElementById("aiMsg").hidden=false;document.getElementById("aiMsg").textContent="IA conectada com segurança.";await resolveiRefreshStatuses();}catch(e){const m=document.getElementById("aiMsg");m.hidden=false;m.textContent=e.message;}}));
 document.querySelectorAll("[data-remove-ai]").forEach(b=>b.addEventListener("click",async()=>{try{const token=await resolveiToken(),r=await fetch("/api/ai/connections/"+b.dataset.removeAi,{method:"DELETE",headers:{Authorization:"Bearer "+token}});if(!r.ok)throw new Error("Não foi possível desconectar.");await resolveiRefreshStatuses();}catch(e){const m=document.getElementById("aiMsg");m.hidden=false;m.textContent=e.message;}}));
}

const resolveiOldRender=render;
render=function(){
  resolveiOldRender();
  if(resolveiUser && ((location.hash||'').includes('conta')||(location.hash||'').includes('conectar-api'))) {
    resolveiBindAuth(); resolveiRefreshStatuses();
  } else if(!resolveiUser && (location.hash||'').includes('conta')) resolveiBindAuth();
};
resolveiFirebaseInit();
