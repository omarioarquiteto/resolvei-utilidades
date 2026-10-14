# Resolvei — Comparador de Preços

Extensão Manifest V3 para Chrome, Microsoft Edge e navegadores compatíveis com Chromium. Ela funciona no popup da extensão: não é necessário abrir o site do Resolvei para comparar produtos.

## Instalação para teste

1. Baixe o ZIP do repositório e extraia-o.
2. Acesse `chrome://extensions` no Chrome ou `edge://extensions` no Edge.
3. Ative o **Modo do desenvolvedor**.
4. Clique em **Carregar sem compactação** e escolha a pasta `extension/monitor-precos`.
5. Abra a página de detalhes de um produto numa loja e clique no ícone do Resolvei.
6. Entre com o mesmo e-mail e senha da conta Resolvei. Se costuma entrar com Google, clique em **Continuar com Google** e conclua a autenticação na janela oficial do Resolvei.
7. A extensão captura o produto, consulta a base comunitária, pesquisa outras lojas e mostra as ofertas no próprio popup.

## O que faz

- Captura nome, preço, marca, modelo, código EAN e imagem quando publicados pela loja.
- Tenta identificar frete grátis, condições de parcelamento (incluindo sem juros/com juros) e códigos de cupom visíveis na página.
- Consulta ofertas externas e registros de outras lojas enviados pela comunidade Resolvei.
- Compartilha automaticamente preço e condições reconhecidos com a base comunitária de preços e histórico.
- Mostra a menor oferta anunciada, a loja, condições de frete e parcelamento e cupons encontrados. Os códigos de cupom podem ser copiados clicando neles.
- Mantém uma sessão da extensão revogável no servidor por até 30 dias. O botão **Sair** encerra essa sessão.
- Exibe gráfico de histórico comunitário com janelas de 40 dias, 6 meses e 1 ano, incluindo mínimo, máximo e última observação.
- O histórico comunitário é atualizado pela rotina agendada do servidor; as verificações independem de alguém abrir a página do produto.

## Dados comunitários e precisão

Os dados da base de comunidade são compartilhados entre usuários autenticados da extensão. O banco registra a loja, o link do produto, observações de preço e a data/hora, além de frete, parcelamento e cupons quando essas informações são identificadas. A contribuição não inclui senha, e-mail ou nome do usuário na ficha pública do produto.

A captura é iniciada somente quando você clica no ícone da extensão. O reconhecimento depende do HTML e do texto publicados pela loja; algumas páginas podem esconder preço, parcelamento ou cupom. A comparação externa e as verificações agendadas dependem da configuração de `SERPAPI_KEY` no Render e do serviço de rotina agendada `Monitor de Preços - Atualização automática`. Se o provedor externo não responder ou a chave não estiver configurada, as ofertas já registradas pela comunidade continuam disponíveis. A frequência depende do agendamento configurado e da cota de consultas disponível.

**Importante:** preço, disponibilidade, frete, juros e cupons podem mudar. O Resolvei não confirma validade de cupom nem custo final; confira os detalhes no carrinho/checkout antes de comprar. A extensão não faz compras nem aplica cupons automaticamente.

## Privacidade

- A extensão não varre abas em segundo plano.
- Lê a aba ativa somente quando você abre o popup da extensão.
- Não guarda a senha.
- Para login por e-mail, o Firebase valida as credenciais; depois disso, a extensão usa uma sessão de API aleatória e revogável, que expira em até 30 dias.
- Para login Google, a autenticação ocorre na página oficial do Resolvei; apenas um token de autenticação de curta duração é trocado por uma sessão da extensão.

## Limitações conhecidas

- Algumas lojas usam páginas dinâmicas ou conteúdo carregado depois de vários segundos, o que pode impedir a extração automática de preço e condições.
- Frete e parcelamento podem variar por CEP, cartão, banco, cliente ou valor do carrinho; as condições não são necessariamente iguais para todos.
- A pesquisa externa não cobre todas as lojas da internet e pode exibir variações de modelo. Confira a descrição, capacidade, cor e versão antes de comparar.
- Cupons identificados na página ou na comunidade podem estar expirados ou sujeitos a regras.
- A extensão ainda não está publicada na Chrome Web Store nem no Microsoft Edge Add-ons.
