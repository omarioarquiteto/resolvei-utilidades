# Radar de Ofertas — Resolvei

## Funcionamento

- Cada usuário configura monitoramentos independentes, com loja, até cinco palavras-chave, desconto mínimo, preço máximo, intervalo e modo de publicação.
- A descoberta usa a busca Google Shopping do SerpApi, filtrando resultados identificados na loja escolhida. Não representa cobertura integral de todos os anúncios do marketplace.
- A consulta do Radar usa `no_cache=true` para evitar resultados deliberadamente em cache. Cada palavra-chave dispara uma consulta nova e consome cota da conta SerpApi.
- O intervalo padrão é de 60 minutos. A frequência mínima configurável é de 15 minutos.
- Se a fonte fornecer preço anterior, o Radar calcula o desconto na primeira consulta. Caso contrário, registra o primeiro preço e identifica reduções nas consultas seguintes.
- O sistema exclui anúncios identificados como usados, seminovos ou recondicionados.
- As ofertas ficam vinculadas ao monitor no Firestore do usuário.

## Modos de publicação

### Com aprovação
O Radar salva as oportunidades na fila. O usuário gera o link de afiliado no programa da loja, cola o link na oportunidade e usa **Aprovar e publicar**.

### Automático
O Radar publica sozinho quando uma oportunidade atende aos critérios e já possui link de afiliado salvo. Para um produto novo, é necessário cadastrar o link pelo menos uma vez. Quando o preço cai novamente, o mesmo link poderá ser reutilizado.

O sistema só repete uma publicação quando o preço atual fica abaixo do último preço publicado.

## Telegram

1. Criar um bot pelo @BotFather.
2. Adicionar o bot como administrador de um canal público, com permissão para publicar.
3. Informar o token do bot e o @username do canal na ferramenta.
4. O backend valida o bot e o canal, cifra o token com RESOLVEI_CREDENTIAL_ENCRYPTION_KEY e nunca o devolve ao navegador.
5. A ferramenta oferece uma mensagem de teste.

As publicações incluem aviso de link de afiliado e botão para abrir a oferta.

## Variáveis necessárias no Render

- `SERPAPI_KEY`: chave da SerpApi usada para pesquisas no Google Shopping.
- `RESOLVEI_CREDENTIAL_ENCRYPTION_KEY`: chave Base64URL de 32 bytes já usada pelo Resolvei para criptografar credenciais.
- Firebase Admin já configurado, pois os monitores e a configuração do Telegram são persistidos por usuário no Firestore.

O agendador do Radar inicia junto ao backend FastAPI e consulta monitores vencidos a cada 60 segundos. Cada monitor mantém o seu próprio nextScanAt. A variável opcional `DEAL_RADAR_SCAN_BATCH` controla quantos monitores são processados por ciclo (padrão 5).

## Limitações da primeira versão

- A descoberta depende de resultados do Google Shopping/SerpApi e pode não encontrar todos os anúncios disponíveis no Mercado Livre.
- A geração dos links de afiliado do Mercado Livre continua sendo feita pelo Portal ou Barra de Afiliados; o Resolvei guarda e reutiliza o link fornecido.
- A comparação de desconto começa no primeiro preço visto quando a fonte não informa um preço anterior. O sistema não inventa histórico retroativo.
- Amazon, Shopee e Magalu estão previstas na seleção de lojas; a qualidade do resultado depende de a pesquisa externa identificar corretamente a loja e de o usuário fornecer um link válido de afiliado para ela.