from __future__ import annotations

from vibe_lucro_engine import analyze


def make_rows(count: int, *, slope: float = 0.001, start: float = 1.0, period: int = 60):
    rows = []
    price = start
    base_time = 1_800_000_000
    for index in range(count):
        next_price = price * (1.0 + slope)
        rows.append({
            "open": price,
            "high": max(price, next_price) * 1.0002,
            "low": min(price, next_price) * 0.9998,
            "close": next_price,
            "volume": 100.0,
            "datetime": base_time + index * period,
        })
        price = next_price
    return rows


def test_analyze_returns_call_for_aligned_bullish_timeframes():
    now = 1_800_000_000 + 220 * 60
    frames = {
        "1m": make_rows(220, slope=0.0004, period=60),
        "5m": make_rows(160, slope=0.0015, period=300),
        "15m": make_rows(110, slope=0.003, period=900),
    }
    result = analyze(frames, "EURUSD", 1, now=now)
    assert result["signal"] == "CALL"
    assert result["buy_score"] >= 72
    assert result["data_quality"]["fresh"] is True


def test_analyze_waits_when_timeframes_are_stale():
    now = 1_900_000_000
    frames = {
        "1m": make_rows(220, period=60),
        "5m": make_rows(160, period=300),
        "15m": make_rows(110, period=900),
    }
    result = analyze(frames, "EURUSD", 5, now=now)
    assert result["signal"] == "WAIT"
    assert result["data_quality"]["fresh"] is False


def test_analyze_rejects_unsupported_expiry():
    frames = {
        "1m": make_rows(220, period=60),
        "5m": make_rows(160, period=300),
        "15m": make_rows(110, period=900),
    }
    try:
        analyze(frames, "EURUSD", 3, now=1_800_000_000)
    except ValueError as exc:
        assert "1, 5 ou 15" in str(exc)
    else:
        raise AssertionError("expiry 3 must be rejected")
