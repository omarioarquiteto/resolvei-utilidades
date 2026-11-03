"""Install only the VIBE LUCRO route and minimal API in an upstream Vibe-Trading checkout."""
from __future__ import annotations

import py_compile
import shutil
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: install_routes.py VIBE_TRADING_ROOT ROUTE_SOURCE SERVER_SOURCE"
        )

    root = Path(sys.argv[1]).resolve()
    route_source = Path(sys.argv[2]).resolve()
    server_source = Path(sys.argv[3]).resolve()
    route_target = root / "agent" / "src" / "api" / "vibe_lucro_routes.py"
    server_target = root / "vibe_lucro_server.py"

    for path in (route_source, server_source, root / "agent" / "src" / "api"):
        if not path.exists():
            raise SystemExit(f"Required Vibe-Trading bridge input is missing: {path}")

    route_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(route_source, route_target)
    shutil.copy2(server_source, server_target)

    py_compile.compile(str(route_target), doraise=True)
    py_compile.compile(str(server_target), doraise=True)


if __name__ == "__main__":
    main()
