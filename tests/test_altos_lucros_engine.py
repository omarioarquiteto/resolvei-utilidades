from altos_lucros_engine import analyze_targets, _wilson_interval


def rising_candles(count: int = 600):
    rows = []
    start = 1.100000
    for index in range(count):
        close = start + index * 0.0001
        rows.append({
            "time": 1_700_000_000 + index * 60,
            "open": close - 0.00002,
            "high": close + 0.00004,
            "low": close - 0.00004,
            "close": close,
        })
    return rows


def test_wilson_interval_is_bounded_and_ordered():
    low, high = _wilson_interval(40, 50)
    assert 0 <= low <= 0.8 <= high <= 1


def test_selects_strike_with_200_percent_or_more_and_positive_edge():
    candles = rising_candles()
    current = candles[-1]["close"]
    strike = round(current * 1.00005, 6)
    quotes = {
        str(strike): {
            "call": {"profit": 250.0, "id": "sample-call"},
            "put": {"profit": 180.0, "id": "sample-put"},
        }
    }
    result = analyze_targets(candles, quotes, 5)
    assert result["status"] == "ALVO_VALIDADO"
    assert result["recommendation"]["direction"] == "ACIMA"
    assert result["recommendation"]["payout_percent"] == 250.0
    assert result["recommendation"]["samples"] >= 30


def test_does_not_treat_payout_below_200_as_eligible():
    candles = rising_candles()
    current = candles[-1]["close"]
    strike = round(current * 1.00005, 6)
    quotes = {str(strike): {"call": {"profit": 199.9}}}
    result = analyze_targets(candles, quotes, 5)
    assert result["status"] == "SEM_STRIKE_200"
    assert result["recommendation"] is None


def test_rejects_unsupported_horizon():
    try:
        analyze_targets(rising_candles(), {}, 10)
    except ValueError as exc:
        assert "5 ou 15" in str(exc)
    else:
        raise AssertionError("Expected unsupported horizon to fail")
