# Ponte VIBE LUCRO ↔ Vibe-Trading

Esta pasta contém o adaptador de integração que deve ser instalado no repositório
`HKUDS/Vibe-Trading`. A conexão GitHub usada nesta implementação não autorizou
a criação de uma branch no repositório original, portanto o arquivo está
preparado aqui, mas ainda **não está instalado nem ativo no servidor Vibe-Trading**.

## Instalação no Vibe-Trading

1. Copie `vibe_lucro_routes.py` para `agent/src/api/vibe_lucro_routes.py`.
2. Em `agent/api_server.py`, acrescente após o registro dos conectores:

```python
from src.api.vibe_lucro_routes import register_vibe_lucro_routes  # noqa: E402
register_vibe_lucro_routes(app)
```

3. Publique o Vibe-Trading com sua autenticação de API já configurada
   (`API_AUTH_KEY` / `VIBE_TRADING_API_KEY`).
4. No ambiente do Resolvei, configure:

```text
VIBE_TRADING_API_URL=https://SEU-SERVIDOR-VIBE
VIBE_TRADING_API_KEY=SUA_CHAVE_DE_API_DO_VIBE
```

Não coloque a chave no frontend, no Git ou no navegador.

## Sessão da IQ Option no Resolvei

O VIBE LUCRO abre uma autenticação exclusiva da IQ Option em seu próprio
módulo `vibe_lucro_auth.py`. O token fica em uma chave própria do
`sessionStorage`, e o servidor mantém um cliente IQ Option separado.
O logout do VIBE LUCRO encerra apenas esse cliente, sem consultar nem remover
sessões da Visão Opções, Analista Bin, TRADE-PRÓ ou Consultor Sênior.

## Contrato e segurança

- Endpoint: `POST /api/vibe-lucro/analyze`.
- Autenticação: `Authorization: Bearer <API key do Vibe-Trading>`.
- O payload contém apenas símbolo, expiração, score, indicadores e até 90 candles
  OHLCV. Não contém login, senha, session ID, dados de conta ou token da IQ Option.
- A rota chama `ChatLLM` diretamente, **sem fornecer esquemas de ferramentas**,
  sem iniciar AgentLoop e sem usar conectores de corretora.
- Respostas que tentem solicitar ferramentas são rejeitadas.
- A revisão de IA é explicativa. Ela não pode substituir CALL/PUT/AGUARDAR nem
  alterar o score quantitativo do Resolvei.
- Sem essa ponte instalada, o motor quantitativo do Resolvei continua operando
  e a interface informa que a revisão do Vibe-Trading está indisponível.
