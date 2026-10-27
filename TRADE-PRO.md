# TRADE-PRÓ — arquitetura e operação

## Objetivo

O TRADE-PRÓ é um módulo de análise de candles da IQ Option. Ele classifica o regime, valida confluência de tendência, volume e volatilidade e, se todos os filtros passarem, emite um sinal informativo de `COMPRA` ou `VENDA` com duração sugerida de 1, 5 ou 15 minutos.

O módulo não envia ordens, não altera saldo e não implementa auto-trading.

## Base conceitual: guia CME Group anexado

A adaptação usa as descrições do guia como inspiração para classificar o contexto:

- **Long Call** (página impressa 7; página 12 do PDF): referência conceitual para cenário altista.
- **Long Put** (página impressa 9; página 14 do PDF): referência conceitual para cenário baixista.
- **Long Straddle** (página impressa 17; página 22 do PDF) e **Long Strangle** (página impressa 19; página 24 do PDF): referência para compressão seguida por possível expansão de volatilidade. Como essas posições não definem, por si sós, uma direção, o sinal direcional só é considerado após rompimento confirmado.
- **Short Straddle** (página impressa 18; página 23 do PDF) e **Short Strangle** (página impressa 20; página 25 do PDF): usadas exclusivamente como analogia para detectar estabilidade e pausar sinais direcionais. O sistema não recomenda nem abre posições vendidas nessas estruturas.

O documento do CME descreve opções sobre futuros com payoff, prêmio e vencimento próprios. A IQ Option e seus contratos têm características diferentes. Portanto, esta implementação é uma **heurística adaptada**, não uma reprodução matemática das estratégias do CME, não uma estratégia validada pelo CME e não uma alegação de rentabilidade.

## Componentes

- `trade_pro_auth.py`: login IQ Option e sessões isoladas do TRADE-PRÓ. Não reutiliza nem modifica a sessão do Analista Bin.
- `trade_pro_api.py`: endpoints de ativos, configuração e análise de candles.
- `trade_pro_engine.py`: cálculo de EMAs, MACD, ATR, ADX, largura de Bollinger, rompimentos, relação de volume, confluência e duração sugerida.
- `trade-pro.js` / `trade-pro.css`: interface, login, análise manual ou periódica e histórico de sinais confirmados.
- `server.py`: registra os dois routers da ferramenta.
- `index.html` / `app.js`: inclui os arquivos e adiciona a ferramenta ao catálogo Investimentos.

## Critérios do protótipo

1. Apenas candles fechados entram no cálculo.
2. O ativo deve pertencer ao catálogo obtido pela IQ Option.
3. A emissão exige confirmação de tendência/direção, volume com variação real e volatilidade suficiente, além de confluência mínima de 72%.
4. A confluência dá peso de 50% à direção/tendência e 25% a cada um dos filtros de volume e volatilidade. Volume e volatilidade continuam sendo requisitos independentes: a pontuação, sozinha, não aprova uma entrada.
5. Volume ausente, zero ou constante é tratado como dado insuficiente; nesse caso, nenhum sinal é autorizado. A interface informa os motivos de bloqueio em vez de mostrar apenas `SEM SINAL`.
6. A API mede a idade do último candle fechado. Se passar de `max(90 segundos, metade do timeframe)`, bloqueia o sinal por dados potencialmente atrasados e informa a idade encontrada.
7. Em consolidação ou transição, a API retorna `signal: null` com diagnóstico dos filtros que não foram satisfeitos.
8. A expiração é uma estimativa heurística baseada no timeframe dos candles, velocidade relativa do movimento e ATR. Não é previsão de que a operação termine no lucro.
9. Os logs registram status, regime, confluência, idade do candle, filtros e motivos de bloqueio. Cada sinal validado é registrado no máximo uma vez por candle.

## Endpoints

- `POST /api/trade-pro/login`
- `GET /api/trade-pro/session`
- `POST /api/trade-pro/logout`
- `GET /api/trade-pro/assets`
- `GET /api/trade-pro/config`
- `POST /api/trade-pro/analyze`

Para endpoints exceto login, envie o cabeçalho `X-IQ-Session` com o identificador retornado no login.

## Testes locais

Com as dependências do projeto instaladas:

```bash
python -m unittest discover -s tests -p "test_trade_pro_engine.py"
```

Os testes automatizados cobrem rejeição de candles insuficientes, timeframes inválidos, bloqueio de volume constante, explicação de ausência de sinal e cenários sintéticos altista/baixista com filtros satisfeitos. Antes de qualquer uso real, verifique a qualidade de candles/volume e execute avaliações históricas fora da amostra. Confluência é apenas a saída de regras determinísticas, não uma probabilidade estatística calibrada de acerto; nenhuma mudança garante rentabilidade.
