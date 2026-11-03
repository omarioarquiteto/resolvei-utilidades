"""Optional read-only VIBE LUCRO review endpoint for Vibe-Trading.

Install this module in agent/src/api/vibe_lucro_routes.py and register it from
agent/api_server.py. The route deliberately calls ChatLLM without tool schemas.
It receives sanitized candles only; it has no IQ Option credentials, broker
connector selection, order tools, or execution path.
"""
from __future__ import annotations

import asyncio
import json
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api.security import require_auth
from src.providers.chat import ChatLLM


class CandleSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(ge=0, allow_inf_nan=False)
    timestamp: float = Field(gt=0, allow_inf_nan=False)


class TimeframeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trend: int = Field(ge=-1, le=1)
    momentum: int = Field(ge=-1, le=1)
    rsi14: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    macd_histogram: float | None = Field(default=None, allow_inf_nan=False)
    atr_percent: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    last_close: float = Field(gt=0, allow_inf_nan=False)
    candles: int = Field(ge=0, le=500)
    age_seconds: float = Field(ge=0, le=86400, allow_inf_nan=False)
    fresh: bool


CandleList = Annotated[list[CandleSnapshot], Field(max_length=30)]


class VibeLucroReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=3, max_length=32, pattern=r"^[A-Z0-9._-]+$")
    expiry_minutes: Literal[1, 5, 15]
    signal: Literal["CALL", "PUT", "WAIT"]
    score: int = Field(ge=0, le=100)
    buy_score: int = Field(ge=0, le=100)
    sell_score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list, max_length=8)
    timeframes: dict[str, TimeframeSnapshot] = Field(max_length=3)
    candles: dict[str, CandleList] = Field(max_length=3)


def _review_sync(payload: VibeLucroReviewRequest) -> dict[str, str]:
    """Run a tool-less LLM review and always release the provider adapter."""
    evidence = payload.model_dump(mode="json")
    prompt = (
        "Você é o revisor independente do VIBE LUCRO, um módulo de análise "
        "técnica de opções de curtíssimo prazo. Analise apenas a evidência "
        "OHLCV e o resumo quantitativo abaixo. Responda em português do Brasil, "
        "com: (1) leitura do contexto M1/M5/M15; (2) convergências; "
        "(3) divergências e riscos; (4) uma conclusão curta sobre a qualidade "
        "da leitura. Não transforme score em probabilidade de acerto. "
        "Não invente preços, eventos, dados ou horários. Não recomende valor "
        "de aposta, martingale ou progressão. Não sugira executar ordens. "
        "O campo signal é uma indicação determinística do motor local: você "
        "pode apontar contradições, mas NÃO pode substituí-lo nem emitir outro "
        "CALL/PUT. Se a amostra for insuficiente, diga isso explicitamente.\n\n"
        "EVIDÊNCIA JSON (dados de mercado públicos/anonimizados):\n"
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )
    llm = ChatLLM()
    try:
        # Intentionally omit the tools argument. This endpoint is an analysis
        # review only and cannot invoke the AgentLoop registry or broker tools.
        response = llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Você é um analista técnico cuidadoso. Seja objetivo, "
                        "explícito sobre incerteza e não invente dados."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            timeout=28,
        )
        if getattr(response, "has_tool_calls", False) or getattr(response, "tool_calls", []):
            raise RuntimeError("A resposta do modelo tentou solicitar ferramentas; revisão bloqueada.")
        review = str(getattr(response, "content", "") or "").strip()
        if not review:
            raise RuntimeError("O modelo não retornou uma revisão textual.")
        snapshot = getattr(llm, "runtime_snapshot", None)
        return {
            "review": review[:6000],
            "provider": str(getattr(snapshot, "provider", "") or ""),
            "model": str(getattr(snapshot, "configured_model", "") or getattr(llm, "model_name", "")),
        }
    finally:
        llm.close()


def register_vibe_lucro_routes(app: FastAPI) -> None:
    """Register a narrowly scoped read-only VIBE LUCRO endpoint."""
    @app.post("/api/vibe-lucro/analyze", dependencies=[Depends(require_auth)])
    async def vibe_lucro_review(request: VibeLucroReviewRequest):
        total_candles = sum(len(rows) for rows in request.candles.values())
        if total_candles > 90:
            raise HTTPException(status_code=413, detail="O limite é de 90 candles por revisão.")
        if set(request.candles) - {"1m", "5m", "15m"} or set(request.timeframes) - {"1m", "5m", "15m"}:
            raise HTTPException(status_code=400, detail="Período de candle não suportado.")
        if not request.candles:
            raise HTTPException(status_code=400, detail="A revisão precisa conter candles.")
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_review_sync, request),
                timeout=32,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail="O Vibe-Trading excedeu o tempo da revisão.") from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Falha na revisão do Vibe-Trading: {type(exc).__name__}: {str(exc)[:180]}",
            ) from exc
        return {
            "ok": True,
            "read_only": True,
            "direction_override": False,
            **result,
        }
