# Ponte VIBE LUCRO ↔ Vibe-Trading

Este diretório constrói um serviço Render separado com o código oficial de
[HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading), adiciona uma rota
de revisão exclusiva e mantém o Resolvei como cliente da API.

O Dockerfile baixa uma revisão upstream fixada, instala as dependências com os
arquivos de lock oficiais e injeta o adaptador durante o build. O repositório
original HKUDS não é alterado.

## Arquitetura

1. O usuário entra na IQ Option pelo formulário exclusivo do VIBE LUCRO.
2. O backend Resolvei obtém os candles M1/M5/M15 usando somente a sessão IQ
   Option pertencente ao VIBE LUCRO.
3. O Resolvei envia ao serviço Vibe-Trading apenas símbolo, expiração,
   indicadores, scores e até 90 candles OHLCV.
4. A rota adicionada usa o `ChatLLM` do Vibe-Trading diretamente, sem iniciar
   AgentLoop e sem anexar ferramentas. Portanto, não há ferramentas de corretora,
   ordens, shell ou execução disponíveis nessa revisão.
5. O texto do Vibe-Trading explica convergências, divergências e riscos; ele não
   pode alterar o sinal quantitativo CALL/PUT/AGUARDAR do motor do Resolvei.

A senha, o token da IQ Option, o identificador da sessão, a identidade e os
dados da conta nunca são enviados ao Vibe-Trading.

## Criar o serviço Render

Crie um novo Web Service no mesmo workspace do Resolvei:

- Repository: `https://github.com/omarioarquiteto/resolvei-utilidades`
- Branch: `main`
- Runtime: `Docker`
- Dockerfile Path: `integrations/vibe-trading/Dockerfile`
- Docker Context: `.`
- Region: `Oregon` (mesma região do Resolvei)
- Plan: `Free` para evitar custos sem aprovação
- Service name sugerido: `resolvei-vibe-trading`

Configure as variáveis no serviço Vibe-Trading:

| Variável | Valor |
| --- | --- |
| `API_AUTH_KEY` | Chave aleatória forte, compartilhada somente entre os dois serviços |
| `LANGCHAIN_PROVIDER` | Provedor escolhido, por exemplo `gemini` |
| `LANGCHAIN_MODEL_NAME` | Modelo disponível no provedor |
| `GEMINI_API_KEY` | Necessária somente quando `LANGCHAIN_PROVIDER=gemini` |
| `OPENROUTER_API_KEY` | Necessária somente quando `LANGCHAIN_PROVIDER=openrouter` |
| `DEEPSEEK_API_KEY` | Necessária somente quando `LANGCHAIN_PROVIDER=deepseek` |
| `VIBE_TRADING_ENABLE_SHELL_TOOLS` | `0` |

Use somente a chave do provedor correspondente ao `LANGCHAIN_PROVIDER`
selecionado. Nunca coloque chaves no frontend, no Git ou em mensagens de chat.

## Conectar o Resolvei

No serviço Render `resolvei`, defina:

- `VIBE_TRADING_API_URL`: URL pública do novo serviço Vibe-Trading.
- `VIBE_TRADING_API_KEY`: o mesmo valor de `API_AUTH_KEY` configurado no
  Vibe-Trading.

O Resolvei já possui o cliente HTTP para chamar
`POST /api/vibe-lucro/analyze`. A rota retorna `available=false` quando o
serviço externo está inacessível; a análise quantitativa local continua
disponível e não é substituída por uma resposta de IA.

## Segurança e operação

- A rota exige `Authorization: Bearer <API_AUTH_KEY>`.
- O adaptador recebe somente dados de mercado anonimizados.
- O adaptador chama `ChatLLM.chat(...)` sem argumento `tools` e rejeita
  respostas com tool calls.
- Não registra rotas de AgentLoop, broker, paper/live trading ou execução.
- O shell do Vibe-Trading permanece explicitamente desativado.
- O plano Free do Render pode suspender o serviço por inatividade. A primeira
  chamada após suspensão pode demorar mais; o Resolvei mantém o sinal local se
  o serviço não responder.

## Sessão IQ Option

O login, token, cliente websocket, TTL e logout continuam isolados em
`vibe_lucro_auth.py`. O Vibe-Trading recebe somente candles/indicadores: nunca
recebe a sessão nem as credenciais da IQ Option.
