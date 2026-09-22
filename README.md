# Resolvei — pacote 2.2

Portal de utilidades para o dia a dia. O projeto pode funcionar localmente sem banco de dados e, quando configuradas as chaves de API no arquivo `.env`, ativa recursos de IA e cotações regionais.

## O que foi atualizado

### 🔥 Quantidade para churrasco
Agora pergunta:
- adultos;
- crianças;
- duração;
- quantidade de pessoas que bebem álcool;
- tipo de bebida alcoólica;
- perfil de compra das carnes.

O resultado calcula um mix de carnes, água, bebidas, pão de alho e acompanhamentos. Abaixo do resultado o site mostra receitas completas e fáceis para as carnes e os principais acompanhamentos.

### 🎉 Planejador de festa
Tipos principais incluídos:
- aniversário infantil;
- aniversário adulto;
- casamento;
- festa da firma/confraternização;
- chá de bebê;
- chá revelação;
- noivado;
- formatura;
- bodas;
- comemoração familiar;
- festa junina;
- happy hour;
- outra comemoração.

Nos aniversários, a idade do aniversariante é solicitada e usada no contexto do planejamento. O plano-base fornece alimentos, bebidas, gelo, utensílios e infraestrutura; o botão de IA refina o evento com base no perfil, duração, público e orçamento informado.

### 💼 Trabalho — rescisão CLT
A ferramenta foi atualizada com referência às regras vigentes em 2026 e inclui:
- dispensa sem justa causa;
- pedido de demissão;
- acordo do art. 484-A;
- justa causa;
- término de contrato por prazo determinado.

Inclui saldo de salário, aviso prévio quando aplicável, férias, 1/3, 13º proporcional, multas do FGTS, descontos informados e observações legais. A multa do FGTS deve preferencialmente usar o saldo/base real do extrato, por isso o campo aceita esse dado.

### ⚖️ Quanto cobrar como PJ
A comparação transforma a remuneração CLT em uma meta de caixa anual e cria reservas para:
- 13º;
- férias + 1/3;
- equivalente ao FGTS;
- benefícios que precisam ser preservados;
- intervalo sem faturamento;
- reserva de risco;
- previdência;
- custos fixos do PJ;
- tributo informado pelo usuário.

O resultado mostra o cálculo passo a passo, não somente um número final.

### 🛒 Lista de compras
Campos:
- nome;
- quantidade;
- unidade;
- valor opcional.

A lista é persistida no navegador e pode ser copiada para o WhatsApp em texto com emojis e total dos itens que possuem valor. Também existe exportação `.txt`.

### 🪜 Escada — espelho e piso
O usuário informa apenas a altura piso a piso. O Resolvei procura a combinação de número de espelhos, altura do espelho e piso que melhor atende simultaneamente à fórmula de Blondel e às faixas de referência usadas na NBR 9050:2020 para escadas em rotas acessíveis.

A ferramenta mostra:
- quantidade de espelhos;
- altura de cada espelho;
- profundidade do piso;
- valor de 2e + p;
- número de pisadas horizontais;
- desenvolvimento horizontal estimado;
- alerta normativo para conferir largura, patamares, corrimãos, guarda-corpos, legislação local e demais normas aplicáveis.

## IA de receitas e preços regionais
A ferramenta **Custo da receita** aceita URL de uma página de receita, tenta localizar ingredientes estruturados, normaliza/classifica os itens e, quando a chave de preços está configurada, consulta o Google Shopping por cidade/UF.

Sem `SERPAPI_KEY`, o sistema não inventa preços: ele apenas organiza os ingredientes e informa que a cotação ao vivo não está disponível.

Sem `OPENAI_API_KEY`, o sistema usa um classificador/parser local simples como fallback.

## Configuração sem editar código

No Windows, faça:

1. Dê duplo clique em `configurar_resolvei.bat`.
2. Informe `OPENAI_API_KEY` e `SERPAPI_KEY` quando disponíveis.
3. Dê duplo clique em `iniciar_resolvei.bat`.
4. O navegador será aberto em `http://127.0.0.1:8080`.

O script cria o ambiente Python e instala as dependências automaticamente.

Também é possível iniciar pelo PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8080
```

## Variáveis de ambiente

```text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-luna
SERPAPI_KEY=
```

As chaves ficam somente no servidor. Nunca coloque essas chaves em `app.js`.

## Produção

Publique `index.html`, `app.js`, `styles.css` e os arquivos estáticos junto com o backend Python. O backend fornece os endpoints `/api/recipe/analyze`, `/api/party/suggest`, `/api/prices/search`, `/api/address/cep/{cep}`, `/api/solar/resource`, `/api/solar/prices`, `/api/solar/image-analyze` e `/api/health`.

Para uma implantação pública, recomenda-se usar HTTPS e manter as variáveis de ambiente fora do controle de versão.

O endpoint `POST /api/address/search` combina ViaCEP (quando há CEP) e OpenStreetMap/Nominatim para devolver latitude/longitude. A aplicação mantém cache em memória e respeita o limite operacional de uma consulta por segundo da instância pública do Nominatim.


## Novidades 3.0 — Energia & Solar

- Dimensionamento de sistema fotovoltaico: consumo, módulos, kWp, inversor, materiais, preços de referência editáveis, custo total, parcelamento e payback.
- Consulta opcional a dados solares do PVGIS por endereço/CEP.
- Estudo de posição solar com endereço, dimensões do terreno/telhado, orientação e trajetória aparente do Sol.
- Upload de print do Google Maps/satélite e simulação interativa dos módulos sobre a imagem.
- Análise visual opcional do telhado por IA, com zonas aproximadas de instalação.
- API de CEP via ViaCEP e geocodificação via OpenStreetMap/Nominatim.

### Fontes técnicas usadas

A etapa visual de módulos agora é integrada ao dimensionamento. O usuário pode carregar uma imagem superior do imóvel, marcar polígonos de planos de telhado, informar azimute/inclinação/altura, marcar obstáculos e calibrar uma distância real. O Resolvei então testa a disposição de módulos em portrait/landscape, respeita afastamento das bordas, considera uma zona conservadora de sombra pelos obstáculos e informa quantos módulos encontraram posição. A escala pode ser calibrada na própria imagem; sem calibração, a área útil informada produz apenas uma escala aproximada.

A calculadora usa PVGIS quando a consulta externa está disponível; o PVGIS é um serviço do Joint Research Centre da Comissão Europeia para estimar radiação solar e produção fotovoltaica por localização. Como referência brasileira, o CRESESB/SunData fornece dados de irradiação e sugestões de inclinação e orientação. Para custos e payback, os preços padrão são apenas parâmetros editáveis e não representam cotação garantida.

A parte regulatória da geração distribuída deve ser conferida na ANEEL e na legislação aplicável à unidade consumidora. O Resolvei não substitui projeto de profissional habilitado, memorial de cálculo, análise estrutural, ART/RRT ou procedimento de conexão da distribuidora.
