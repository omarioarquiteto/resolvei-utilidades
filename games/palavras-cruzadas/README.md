# Palavras Cruzadas

Jogo de palavras cruzadas em português com visual inspirado em páginas impressas de revistas e livros de passatempos.

## Como jogar

1. Abra o arquivo `index.html` em um navegador moderno.
2. Escolha a dificuldade: **Fácil**, **Médio** ou **Difícil**.
3. Clique em uma pista horizontal ou vertical e digite as letras nos quadrinhos.
4. Use **Conferir respostas**, **Revelar palavra**, **Limpar** e **Novo diagrama** quando precisar.

## Recursos

- Visual editorial inspirado em livro de passatempos: papel marfim, títulos serifados, filetes de impressão, diagrama preto e branco e pistas organizadas em colunas.
- Interface responsiva para computador e celular, com quadrinhos dimensionados para toque.
- Botão **Tela cheia** com modo imersivo: usa a tela cheia do navegador quando suportada e um layout visual sem cabeçalho/rodapé como alternativa.
- Pode ser instalado como aplicativo web (PWA), com ícones próprios, abertura em modo `standalone` e cache dos arquivos principais para reutilização offline após a primeira carga.
- Layout adaptado para orientação retrato e paisagem; no celular, os controles ficam compactos e as pistas são organizadas lado a lado.
- Diagramas gerados aleatoriamente a cada nova partida.
- Três níveis de dificuldade, com quantidade e comprimento de palavras diferentes.
- Destaque visual da palavra selecionada e foco automático na primeira célula ao escolher uma pista.
- Navegação por setas do teclado e alternância entre horizontal/vertical com Enter nos cruzamentos.
- Conferência com destaque visual de letras corretas e incorretas; revelação da palavra selecionada e limpeza da partida.
- Banco local com mais de **1.700 entradas** de vocabulário e plurais comuns gerados automaticamente, com respostas normalizadas sem acentos.
- Não exige instalação, conta, servidor ou bibliotecas externas.

## Abrir em tela cheia no celular

O botão **Tela cheia** reduz a interface ao espaço de jogo nos navegadores compatíveis. Para abrir sem as barras do navegador no celular, publique em HTTPS e adicione o site à tela inicial:

- **iPhone:** abra no Safari, toque em **Compartilhar → Adicionar à Tela de Início**, habilite **Abrir como app** e toque em **Adicionar**.
- **Android:** abra no Chrome, abra o menu **⋮** e selecione **Instalar app** ou **Adicionar à tela inicial**.

## Executar e publicar

É um site estático: basta abrir `index.html`; nesse caso, a instalação e o cache offline não ficam disponíveis. Para publicar com GitHub Pages, entre em **Settings → Pages** e selecione a branch `main` e a pasta `/(root)` como origem. A instalação como app e o service worker precisam de uma origem HTTPS, como GitHub Pages.

## Observação sobre as pistas

As palavras principais possuem pistas descritivas, e os plurais gerados recebem pistas do tipo “Plural de …”. Parte do vocabulário adicional ainda usa uma pista genérica; revisar e enriquecer essas pistas editorialmente continua sendo uma melhoria importante.
