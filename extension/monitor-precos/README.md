# Extensão Monitor de Preços — Resolvei

Extensão Manifest V3 para Chrome, Microsoft Edge e navegadores compatíveis com Chromium.

## Instalação para teste

1. Baixe o repositório Resolvei como ZIP e extraia os arquivos.
2. Abra chrome://extensions no Google Chrome ou edge://extensions no Microsoft Edge.
3. Ative o **Modo do desenvolvedor**.
4. Clique em **Carregar sem compactação** e selecione a pasta extension/monitor-precos.
5. Abra uma página HTTPS de detalhes de produto, clique no ícone da extensão e depois em **Enviar ao Resolvei**.
6. Revise nome, preço e link no Monitor de Preços. Clique em **Monitorar produto** para salvar.

## Privacidade

A extensão não varre abas em segundo plano. Ela lê os dados da página ativa somente quando o usuário abre a extensão e aciona esse fluxo. Os dados são enviados à interface do Resolvei para revisão antes de serem salvos na conta.

## Limitações atuais

- Os melhores resultados vêm de páginas que publicam informações estruturadas de produto (JSON-LD, metadados Open Graph ou itemprop).
- A captura tenta reconhecer nome, preço em BRL, marca, modelo, GTIN/EAN e imagem, mas alguns sites podem exigir preenchimento manual.
- A extensão abre o Monitor de Preços hospedado no Resolvei. Ela ainda não está publicada na Chrome Web Store nem no Microsoft Edge Add-ons.
