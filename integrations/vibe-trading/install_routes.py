"""Install the Resolvei VIBE LUCRO review route into an upstream Vibe-Trading checkout."""
from __future__ import annotations

import py_compile
import shutil
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: install_routes.py VIBE_TRADING_ROOT ROUTE_SOURCE")

    root = Path(sys.argv[1]).resolve()
    route_source = Path(sys.argv[2]).resolve()
    api_server = root / "agent" / "api_server.py"
    route_target = root / "agent" / "src" / "api" / "vibe_lucro_routes.py"

    if not api_server.is_file() or not route_source.is_file():
        raise SystemExit("Vibe-Trading source or Resolvei route file is missing")

    route_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(route_source, route_target)

    source = api_server.read_text(encoding="utf-8")
    marker = "register_auth_routes(app)"
    registration = (
        "from src.api.vibe_lucro_routes import register_vibe_lucro_routes  # noqa: E402\n"
        "register_vibe_lucro_routes(app)"
    )

    if registration not in source:
        if source.count(marker) != 1:
            raise SystemExit("Could not safely locate the Vibe-Trading API route registration point")
        source = source.replace(marker, marker + "\n\n" + registration, 1)
        api_server.write_text(source, encoding="utf-8")

    py_compile.compile(str(route_target), doraise=True)
    compile(api_server.read_text(encoding="utf-8"), str(api_server), "exec")


if __name__ == "__main__":
    main()
