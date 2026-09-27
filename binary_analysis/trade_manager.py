from __future__ import annotations
# Minimal Resolvei persistence adapter for the Market Insight analysis engine.
# Strategy settings are kept in memory; no IQ credentials are stored here.
_CONFIG: dict[str,str] = {}
def set_config_raw(key: str, value: str) -> None:
    _CONFIG[str(key)] = str(value)
def get_config_valor(key: str, default=None):
    return _CONFIG.get(str(key), default)
