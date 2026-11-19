import pandas as pd

from btcbot.data.validate import validate_candles


def test_clean_data_is_ok(candles):
    r = validate_candles(candles, "4h")
    assert r.ok
    assert r.rows == 50 and not r.gaps


def test_detects_gap(candles):
    r = validate_candles(candles.drop(candles.index[10:13]), "4h")
    assert r.ok  # un hueco es aviso, no error
    assert len(r.gaps) == 1 and r.missing_candles == 3


def test_detects_duplicates(candles):
    r = validate_candles(pd.concat([candles, candles.iloc[[5]]]).sort_index(), "4h")
    assert r.duplicates == 1 and not r.ok


def test_detects_invalid_ohlc(candles):
    bad = candles.copy()
    bad.iloc[3, bad.columns.get_loc("high")] = bad["low"].iloc[3] - 1
    r = validate_candles(bad, "4h")
    assert r.invalid_ohlc == 1 and not r.ok


def test_detects_misaligned(candles):
    bad = candles.copy()
    bad.index = bad.index + pd.Timedelta(minutes=30)
    r = validate_candles(bad, "4h")
    assert r.misaligned == 50 and not r.ok


def test_detects_non_positive_price(candles):
    bad = candles.copy()
    bad.iloc[0, bad.columns.get_loc("low")] = 0
    assert not validate_candles(bad, "4h").ok


def test_empty():
    r = validate_candles(pd.DataFrame(), "4h")
    assert r.rows == 0
