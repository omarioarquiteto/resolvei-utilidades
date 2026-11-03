"""Minimal public API for the Resolvei VIBE LUCRO read-only bridge.

This intentionally does not import the full Vibe-Trading API assembler:
no sessions, AgentLoop, MCP, broker, paper/live trading, or shell routes are
mounted on this service. The only public functional route is the authenticated
VIBE LUCRO market-review endpoint.
"""
from __future__ import annotations

from fastapi import FastAPI

from src.api.vibe_lucro_routes import register_vibe_lucro_routes

app = FastAPI(
    title="Vibe-Trading · VIBE LUCRO review API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/live", include_in_schema=False)
async def live() -> dict[str, str]:
    """Public liveness probe; contains no account or configuration data."""
    return {"status": "live", "service": "vibe-lucro-review"}


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Health alias for generic HTTP monitors."""
    return {"status": "ok"}


register_vibe_lucro_routes(app)
