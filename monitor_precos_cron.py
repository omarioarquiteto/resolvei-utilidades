"""Invoca a rotina automática do Monitor de Preços a partir do Render Cron Job."""
from __future__ import annotations

import json
import os
import sys

import requests


def main() -> int:
    base_url = os.getenv("PRICE_MONITOR_BASE_URL", "https://resolvei-utilidades.onrender.com").strip().rstrip("/")
    secret = os.getenv("PRICE_MONITOR_CRON_KEY", "").strip()
    if not base_url.startswith("https://") or not secret:
        print("Configuração incompleta: defina PRICE_MONITOR_BASE_URL e PRICE_MONITOR_CRON_KEY.", file=sys.stderr)
        return 2

    endpoint = base_url + "/api/price-monitor/admin/refresh-community"
    try:
        response = requests.post(
            endpoint,
            headers={"X-Price-Monitor-Cron-Key": secret, "Accept": "application/json"},
            timeout=(15, 600),
        )
    except requests.RequestException as exc:
        # Não imprimir cabeçalhos nem o segredo na saída do serviço.
        print("Falha de rede ao acionar a atualização automática: " + type(exc).__name__, file=sys.stderr)
        return 1

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 400:
        detail = data.get("detail") if isinstance(data, dict) else ""
        print(json.dumps({
            "ok": False,
            "status": response.status_code,
            "error": str(detail or "A API do Monitor de Preços recusou a atualização.")[:240],
        }, ensure_ascii=False), file=sys.stderr)
        return 1

    summary = {
        key: data.get(key)
        for key in ("ok", "totalProducts", "dueProducts", "processed", "offersUpdated",
                    "priceChanges", "errors", "remainingDue", "checkedAt")
    } if isinstance(data, dict) else {"ok": True}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if response.status_code == 200 and summary.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
