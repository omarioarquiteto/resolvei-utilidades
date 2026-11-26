# Resolvei — Comparador de Preços

Extensão Manifest V3 para Chrome, Microsoft Edge e navegadores compatíveis com Chromium. A extensão compara produtos no popup e acompanha metas de preço em segundo plano.

## Instalação

1. Baixe o ZIP do repositório e extraia-o.
2. Acesse `chrome://extensions` no Chrome ou `edge://extensions` no Edge.
3. Ative o **Modo do desenvolvedor**.
4. Clique em **Carregar sem compactação** e escolha `extension/monitor-precos`.
5. Abra a página de detalhes de um produto e clique no ícone do Resolvei.
6. Entre com a mesma conta usada no site do Resolvei.
7. Informe uma **palavra-chave de busca** (ex.: `console PlayStation 5`), defina meta, frequência e alcance de busca e clique em **Monitorar**.

## Monitoramento ativo

Ao monitorar um produto, escolha:

- **Meta de preço:** por exemplo, R$ 3.500,00 para um PlayStation.
- **Palavra-chave:** orienta a pesquisa nacional e permite encontrar anúncios com descrições diferentes, desde que correspondam aos termos escolhidos.
- **Frequência:** 1, 5, 10, 30 ou 60 minutos.
- **Onde procurar — Somente esta loja:** o servidor consulta a URL original e tenta extrair o preço de dados estruturados (JSON-LD/Offer), metadados ou campos de preço semântico publicados pela loja. Não depende do SerpApi, mas pode falhar quando a loja bloqueia acessos automáticos ou só renderiza o preço com JavaScript.
- **Onde procurar — Internet brasileira:** consulta o Google Shopping Brasil e tenta confirmar o modelo antes de atualizar o menor preço. Essa busca depende de `SERPAPI_KEY` configurada no Render e da cota disponível. Não equivale a rastrear literalmente todos os sites da internet.

Quando a meta é atingida, o serviço registra o evento. A extensão gera uma notificação do sistema e abre uma nova aba do Resolvei com o preço, a meta e o link direto para a oferta. Clicar na notificação também abre a oferta. O mesmo evento não gera notificações repetidas; um novo alerta acontece quando a meta for editada/atingida novamente.

**Requisitos para alerta no computador:** o Chrome/Edge e a extensão precisam estar ativos, com uma sessão válida do Resolvei e permissão de notificações. O computador não pode estar desligado. Os alarmes do navegador podem atrasar e não acordam o computador quando ele está em suspensão; a verificação do servidor continua sujeita à disponibilidade do serviço hospedado e ao processamento do provedor.

## Cota da busca nacional

A modalidade nacional faz uma pesquisa externa por produto a cada ciclo configurado. No plano gratuito do SerpApi, a franquia publicada é de 250 pesquisas por mês. Assim, uma única busca por hora já representa cerca de 720 pesquisas em 30 dias; frequências menores consomem a franquia ainda mais rapidamente. A cota é compartilhada com outras pesquisas que usem a mesma chave. Verifique o plano e o uso em [SerpApi Pricing](https://serpapi.com/pricing).

Para monitorar vários produtos com frequência alta, pode ser necessário um plano SerpApi superior. O modo **Somente esta loja** não consome essa cota.

## Comparação e dados comunitários

- Captura nome, preço, marca, modelo, código EAN e imagem quando publicados pela loja.
- Tenta identificar frete, parcelamento e cupons visíveis.
- Combina ofertas pesquisadas com registros compartilhados pela comunidade Resolvei.
- Mostra histórico de preços, menor oferta, origem e link da loja.
- Os dados da base comunitária não expõem a senha, o e-mail ou o nome do usuário que contribuiu.

Preço, disponibilidade, frete, juros e cupons podem mudar. Confira o modelo, vendedor, frete, condições e valor final no checkout. A extensão não compra produtos nem aplica cupons automaticamente.

## Privacidade

- A extensão não varre nem lê todas as abas abertas.
- A página da loja só é lida quando você aciona a extensão.
- A senha não é armazenada pela extensão.
- Após o login Firebase, a extensão usa uma sessão de API aleatória e revogável, válida por até 30 dias.
- O serviço em segundo plano consulta somente a lista de produtos da conta autenticada para verificar metas de preço.

## Limitações conhecidas

- Algumas lojas escondem preços, bloqueiam acessos automatizados ou só exibem o preço após executar JavaScript.
- A pesquisa Google Shopping Brasil pode não listar todas as lojas e pode apresentar variações de modelo. Confira capacidade, cor, versão e vendedor.
- Frete e parcelamento podem depender do CEP, cartão, banco, cliente ou valor do carrinho.
- Cupons podem expirar ou ter regras específicas.
- A extensão ainda não está publicada na Chrome Web Store nem no Microsoft Edge Add-ons.

## Carrinho e base administrativa

- O botão **Monitorar** salva o produto na lista pessoal e também o adiciona ao carrinho do Resolvei.
- O total do carrinho usa o menor preço conhecido por produto; itens sem preço confirmado são contabilizados separadamente.
- A base comunitária completa permanece restrita aos administradores autorizados pela variável `PRICE_MONITOR_ADMIN_EMAILS` no Render.
- O controle de acesso administrativo é validado no servidor, não apenas ocultado na interface.
