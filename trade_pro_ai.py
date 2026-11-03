"""Segunda leitura do Gemini para o TRADE-PRÓ.

O Gemini interpreta a leitura técnica produzida a partir dos candles da IQ Option.
A recomendação passa por uma validação local que impede a IA de inverter o sinal
determinístico ou liberar entradas sem uma direção previamente confirmada.
"""
from __future__ import annotations

import json
import re
from typing import Any


def build_trade_pro_ai_prompt(base: dict[str, Any]) -> str:
    """Monta um prompt compacto com dados técnicos reais do Trade Pro."""
    payload = {
        "symbol": base.get("symbol"),
        "timeframe": base.get("timeframe"),
        "candle_time": base.get("candle_time"),
        "base_signal": base.get("signal"),
        "base_status": base.get("status"),
        "regime": base.get("regime"),
        "base_reason": base.get("reason"),
        "confluence": base.get("confluence"),
        "minimum_confluence": base.get("threshold"),
        "expiration_minutes": base.get("expiration_minutes"),
        "market": base.get("market") or {},
        "scores": base.get("scores") or {},
        "checks": base.get("checks") or {},
        "blocking_reasons": base.get("blocking_reasons") or [],
        "data_quality": base.get("data_quality") or {},
        "recent_closed_candles": base.get("recent_candles") or [],
    }
    return (
        "Você é um analista técnico de mercado especializado em leitura de candles. "
        "Faça uma segunda leitura crítica dos dados reais fornecidos pelo módulo TRADE-PRÓ. "
        "Não invente cotações, notícias, indicadores, volume ou fatos que não estejam no objeto. "
        "Não prometa lucro e não trate a convicção como probabilidade estatística.\n\n"
        "REGRAS OBRIGATÓRIAS DE DECISÃO:\n"
        "1. Se base_signal não for COMPRA nem VENDA, a recomendação TEM de ser AGUARDAR. "
        "Não crie direção por conta própria quando os filtros-base não confirmaram uma entrada.\n"
        "2. Se algum filtro obrigatório estiver falso, se houver bloqueios relevantes ou dados "
        "desatualizados, prefira AGUARDAR.\n"
        "3. Se base_signal for COMPRA, você só pode responder COMPRA ou AGUARDAR. "
        "Se for VENDA, só pode responder VENDA ou AGUARDAR. Nunca inverta a direção.\n"
        "4. A IA pode vetar um sinal, mas não pode liberar uma entrada que o motor-base não validou.\n"
        "5. Não invente preço de entrada, stop, payout ou alvo. A expiração, quando houver sinal, "
        "deve permanecer igual à expiração sugerida pelo motor-base.\n"
        "6. Analise também a sequência dos últimos candles fechados: estrutura de máximas/mínimas, "
        "corpos, sombras, continuidade, rejeições e rompimentos falsos quando os dados permitirem. "
        "Não trate um padrão isolado como confirmação suficiente.\n"
        "7. Seja conservador. Diferencie tendência, impulso, volume, volatilidade, risco de reversão "
        "e ausência de confirmação.\n\n"
        "Retorne SOMENTE JSON válido, sem markdown, com este formato: "
        '{"recommendation":"COMPRA|VENDA|AGUARDAR","confidence":0,'
        '"summary":"resumo direto em português","reasons":["fator 1","fator 2"],'
        '"risks":["risco 1"],"entry_condition":"condição objetiva ou aguardar"}'
        "\n\nCONVICÇÃO: número inteiro de 0 a 100 que representa apenas a clareza qualitativa "
        "da leitura, nunca chance de lucro.\n\nDADOS DO TRADE-PRÓ:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    )


def parse_trade_pro_ai_response(raw: str, base: dict[str, Any]) -> dict[str, Any]:
    """Valida a resposta da IA e aplica os bloqueios de direção e atualidade."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Resposta vazia do Gemini.")

    cleaned = raw.strip()
    cleaned = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", cleaned, flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON inválido retornado pelo Gemini.") from exc
    if not isinstance(data, dict):
        raise ValueError("A resposta do Gemini não é um objeto JSON.")

    recommendation = str(data.get("recommendation", "")).strip().upper()
    if recommendation not in {"COMPRA", "VENDA", "AGUARDAR"}:
        raise ValueError("O Gemini não retornou uma recomendação reconhecida.")

    summary = str(data.get("summary", "")).strip()[:700]
    reasons = data.get("reasons") if isinstance(data.get("reasons"), list) else []
    risks = data.get("risks") if isinstance(data.get("risks"), list) else []
    reasons = [str(item).strip()[:240] for item in reasons if str(item).strip()][:5]
    risks = [str(item).strip()[:240] for item in risks if str(item).strip()][:5]
    entry_condition = str(data.get("entry_condition", "")).strip()[:400]

    confidence_raw = data.get("confidence", 0)
    try:
        confidence = int(round(float(confidence_raw)))
    except (TypeError, ValueError, OverflowError):
        confidence = 0
    confidence = max(0, min(100, confidence))

    base_signal = base.get("signal")
    stale = bool((base.get("data_quality") or {}).get("stale"))
    safety_note = ""
    if stale:
        recommendation = "AGUARDAR"
        safety_note = "Entrada bloqueada: o candle mais recente está desatualizado."
    elif base_signal not in {"COMPRA", "VENDA"}:
        recommendation = "AGUARDAR"
        safety_note = "O motor do Trade Pro não validou uma direção; a IA não pode liberar uma entrada."
    elif recommendation not in {base_signal, "AGUARDAR"}:
        recommendation = "AGUARDAR"
        safety_note = "A IA divergiu da direção validada pelo motor-base; por segurança, a recomendação final é aguardar."

    if safety_note:
        if safety_note not in reasons:
            reasons.insert(0, safety_note)
        summary = safety_note if not summary or recommendation == "AGUARDAR" else summary
        if recommendation == "AGUARDAR" and not entry_condition:
            entry_condition = "Aguarde uma nova leitura com todos os filtros confirmados."
    if not summary:
        summary = "Aguarde confirmação dos filtros antes de considerar uma entrada."
    if not reasons:
        reasons = ["Leitura técnica interpretada pelo Gemini a partir dos indicadores do Trade Pro."]
    if not risks:
        risks = ["Operações de curto prazo podem resultar em perda; a análise não garante resultado."]
    if not entry_condition:
        entry_condition = "Aguarde uma nova leitura antes de considerar uma entrada."

    expiration = base.get("expiration_minutes") if recommendation == base_signal else None
    if recommendation == "AGUARDAR":
        expiration = None

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "summary": summary,
        "reasons": reasons,
        "risks": risks,
        "entry_condition": entry_condition,
        "expiration_minutes": expiration,
    }
