from __future__ import annotations

from typing import Any

from analista_bin_engine import STRATEGIES as ANALISTA_BIN_STRATEGIES
from analista_bin_engine import analyze as analyze_analista_bin

# Classificação visual dos mesmos dez indicadores do Analista Bin.
# Ela não altera votos nem pesos do motor original.
INDICATOR_GROUPS = {
    "trend": [
        "trend", "trend", "trend", "momentum", "trend",
        "momentum", "momentum", "structure", "momentum", "momentum",
    ],
    "breakout": [
        "structure", "conditions", "structure", "momentum", "structure",
        "structure", "structure", "momentum", "structure", "momentum",
    ],
    "reversion": [
        "structure", "momentum", "momentum", "structure", "momentum",
        "structure", "momentum", "momentum", "momentum", "structure",
    ],
}

AUTO_CONFLICT_MARGIN = 12.0


def _volume_available(rows: list[dict[str, Any]]) -> bool:
    values: list[float] = []
    for row in rows[-30:]:
        try:
            value = float(row.get("volume"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    if len(values) < 25:
        return False
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance > 1e-18


def _group_scores(indicators: list[dict[str, Any]], direction: str) -> dict[str, dict[str, float]]:
    scores = {
        key: {"call": 0.0, "put": 0.0, "activeVotes": 0}
        for key in ("trend", "momentum", "structure")
    }
    for item in indicators:
        group = item.get("group")
        if group not in scores:
            continue
        target = scores[group]
        vote = int(item.get("direction") or 0)
        weight = float(item.get("weight") or 0)
        if vote == 1:
            target["call"] += weight
            target["activeVotes"] += 1
        elif vote == -1:
            target["put"] += weight
            target["activeVotes"] += 1

    for group in scores.values():
        group["call"] = round(group["call"], 1)
        group["put"] = round(group["put"], 1)

    scores["conditions"] = {
        "call": 0.0,
        "put": 0.0,
        "activeVotes": 1 if direction in ("CALL", "PUT") else 0,
    }
    return scores


def _decorate(
    base: dict[str, Any],
    requested_strategy: str,
    rows: list[dict[str, Any]],
    *,
    conflict_reason: str | None = None,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = dict(base)
    strategy = str(result.get("strategy") or requested_strategy)
    direction = str(result.get("direction") or "NONE")
    grouped = []
    groups = INDICATOR_GROUPS.get(strategy, [])
    for index, source in enumerate(result.get("indicators") or []):
        item = dict(source)
        item["group"] = groups[index] if index < len(groups) else "structure"
        item["active"] = bool(item.get("active")) and direction in ("CALL", "PUT")
        grouped.append(item)

    reasons = []
    if conflict_reason:
        direction = "NONE"
        result["direction"] = direction
        result["signal"] = "SEM SINAL"
        for item in grouped:
            item["active"] = False
        reasons.append(conflict_reason)
    elif direction == "NONE":
        reasons.append(
            "A estratégia não atingiu o mínimo de confluência do Analista Bin "
            "ou apresentou conflito entre os indicadores."
        )

    # O front-end mantém a leitura por grupos, mas os votos e pesos são os
    # originais do Analista Bin, sem recalcular ou substituir sua pontuação.
    result["indicators"] = grouped
    result["groupScores"] = _group_scores(grouped, direction)
    result["blockingReasons"] = reasons
    result["requestedStrategy"] = requested_strategy
    result["engine"] = "Analista Bin"
    result["analysisVersion"] = "analista-bin-shared-v1"
    result["volumeDataAvailable"] = _volume_available(rows)
    result["marketRegime"] = strategy
    result["marketRegimeLabel"] = result.get("strategyLabel", strategy.title())
    result["confirmedGroups"] = sum(
        1
        for key in ("trend", "momentum", "structure")
        if (
            result["groupScores"][key]["call"] > result["groupScores"][key]["put"]
            if direction == "CALL"
            else result["groupScores"][key]["put"] > result["groupScores"][key]["call"]
            if direction == "PUT"
            else False
        )
    )
    if candidates is not None:
        result["strategyCandidates"] = candidates
    return result


def analyze_opcoes_signal(
    rows: list[dict[str, Any]],
    strategy: str = "auto",
) -> dict[str, Any]:
    """Executa o motor compartilhado do Analista Bin para Opções Digitais."""
    if strategy not in ("auto", *ANALISTA_BIN_STRATEGIES.keys()):
        raise ValueError("Estratégia inválida.")

    if strategy != "auto":
        result = analyze_analista_bin(rows, strategy)
        return _decorate(result, strategy, rows)

    analyses = [
        analyze_analista_bin(rows, key)
        for key in ANALISTA_BIN_STRATEGIES
    ]
    candidates = [
        {
            "strategy": item["strategy"],
            "strategyLabel": item["strategyLabel"],
            "direction": item["direction"],
            "score": item["score"],
            "signal": item["signal"],
            "callScore": item["callScore"],
            "putScore": item["putScore"],
        }
        for item in analyses
    ]

    eligible = [
        item for item in analyses
        if item.get("direction") in ("CALL", "PUT")
    ]
    conflict_reason = None
    if eligible:
        selected = max(eligible, key=lambda item: float(item.get("score") or 0))
        opposing = [
            item for item in eligible
            if item.get("direction") != selected.get("direction")
        ]
        if opposing:
            strongest_opposing = max(
                opposing, key=lambda item: float(item.get("score") or 0)
            )
            difference = abs(
                float(selected.get("score") or 0)
                - float(strongest_opposing.get("score") or 0)
            )
            if difference < AUTO_CONFLICT_MARGIN:
                conflict_reason = (
                    "As estratégias do Analista Bin apontaram direções opostas "
                    "com pontuações próximas. A entrada foi bloqueada por conflito."
                )
    else:
        selected = max(
            analyses, key=lambda item: float(item.get("score") or 0)
        )

    return _decorate(
        selected,
        "auto",
        rows,
        conflict_reason=conflict_reason,
        candidates=candidates,
    )
