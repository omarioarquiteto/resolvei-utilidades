# Ponte VIBE LUCRO ↔ Vibe-Trading

Este diretório constrói um serviço Render separado com o código oficial de
[HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading), fixado em uma
revisão específica. O repositório original HKUDS não é alterado.

O build instala as dependências upstream com os arquivos de lock oficiais e
usa o `ChatLLM` e a configuração de provedores do próprio Vibe-Trading. A
aplicação pública, porém, é uma API mínima: publica somente health check e a
rota autenticada de revisão do VIBE LUCRO. Não importa nem monta o servidor
geral do Vibe-Trading.

## Arquitetura

1. O usuário entra na IQ Option pelo formulário exclusivo do VIBE LUCRO.
2. O backend Resolvei obtém os candles M1/M5/M15 usando somente a sessão IQ
   Option pertencente ao VIBE LUCRO.
3. O Resolvei envia ao serviço Vibe-Trading apenas símbolo, expiração,
   indicadores, scores e até 90 candles OHLCV.
4. O adaptador usa o `ChatLLM` oficial do Vibe-Trading diretamente, sem iniciar
   AgentLoop e sem anexar ferramentas. Portanto, a instância publicada não
   disponibiliza sessões gerais, MCP, ferramentas de corretora, ordens, shell
   ou execução.
5. A revisão explica convergências, divergências e riscos; não pode alterar o
   sinal quantitativo CALL/PUT/AGUARDAR do motor do Resolvei.

A senha, o token da IQ Option, o identificador da sessão, a identidade e os
dados da conta nunca são enviados ao Vibe-Trading.

## Serviço Render

Foi criado o serviço:

- Nome: `resolvei-vibe-trading`
- URL: `https://resolvei-vibe-trading.onrender.com`
- Runtime: Docker
- Dockerfile: `integrations/vibe-trading/Dockerfile`
- Região: Oregon
- Plano: Free

O serviço usa `uvicorn vibe_lucro_server:app`, não `vibe-trading serve`.
Isso restringe a superfície pública às duas rotas de health e à revisão
autenticada do VIBE LUCRO.

## Variáveis do serviço Vibe-Trading

| Variável | Valor |
| --- | --- |
| `API_AUTH_KEY` | Chave aleatória forte, compartilhada somente entre os dois serviços |
| `LANGCHAIN_PROVIDER` | `gemini` |
| `LANGCHAIN_MODEL_NAME` | `gemini-3.5-flash` |
| `GEMINI_API_KEY` | Chave Gemini necessária para gerar a revisão |
| `VIBE_TRADING_ENABLE_SHELL_TOOLS` | `0` |

Nunca coloque chaves no frontend, no Git ou em mensagens de chat. A chave de
API de serviço já foi criada e conectada entre o Vibe-Trading e o Resolvei.

## Variáveis do serviço Resolvei

O backend Resolvei já foi configurado com:

- `VIBE_TRADING_API_URL=https://resolvei-vibe-trading.onrender.com`
- `VIBE_TRADING_API_KEY`: chave compartilhada correspondente a `API_AUTH_KEY`.

O cliente chama `POST /api/vibe-lucro/analyze`. Quando o serviço externo
está indisponível, a análise quantitativa local continua disponível.

## Segurança

- A rota de revisão exige `Authorization: Bearer <API_AUTH_KEY>`.
- O adaptador recebe somente dados de mercado anonimizados.
- O adaptador chama `ChatLLM.chat(...)` sem argumento `tools` e rejeita
  respostas com tool calls.
- A aplicação pública não monta `/sessions`, AgentLoop, MCP, opções, corretora
  ou rotas gerais do Vibe-Trading.
- O shell permanece explicitamente desativado.
- O plano Free do Render pode suspender o serviço por inatividade. A primeira
  chamada após suspensão pode demorar mais.

## Sessão IQ Option

O login, token, cliente websocket, TTL e logout continuam isolados em
`vibe_lucro_auth.py`. O Vibe-Trading recebe somente candles/indicadores: nunca
recebe a sessão nem as credenciais da IQ Option.
