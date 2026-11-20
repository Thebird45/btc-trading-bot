import numpy as np
import pandas as pd
import pytest

from btcbot.indicators.technical import atr, ema, macd, rsi, sma, true_range, wilder_smooth

# Ejemplo clásico de RSI(14) de Wilder (tabla de StockCharts)
WILDER_CLOSES = [
    44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
    45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439,
]
WILDER_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97]


def s(values):
    return pd.Series(values, dtype=float)


def test_rsi_matches_reference():
    out = rsi(s(WILDER_CLOSES), 14)
    assert out.iloc[:14].isna().all()
    np.testing.assert_allclose(out.iloc[14:].to_numpy(), WILDER_RSI, atol=0.01)


def test_rsi_extremes():
    assert rsi(s(range(1, 40)), 14).dropna().eq(100).all()
    assert rsi(s(range(40, 1, -1)), 14).dropna().eq(0).all()


def test_rsi_bounded():
    rng = np.random.default_rng(1)
    out = rsi(s(100 + rng.normal(0, 1, 500).cumsum()), 14).dropna()
    assert out.between(0, 100).all()


def test_sma_and_ema_warmup_and_values():
    x = s([1, 2, 3, 4, 5])
    assert sma(x, 3).tolist()[2:] == [2, 3, 4]
    assert sma(x, 3).iloc[:2].isna().all()
    e = ema(x, 3)
    assert e.iloc[:2].isna().all()
    # alpha = 2/(3+1) = 0.5, sin ajuste
    pd.testing.assert_series_equal(e, x.ewm(span=3, adjust=False, min_periods=3).mean())


def test_ema_constant_series():
    assert ema(s([7] * 30), 10).dropna().eq(7).all()


def test_wilder_smooth_seed_and_recursion():
    out = wilder_smooth(s([np.nan, 2, 4, 6, 8]), 3)
    assert out.iloc[:3].isna().all()
    assert out.iloc[3] == pytest.approx(4)  # media de 2, 4, 6
    assert out.iloc[4] == pytest.approx((4 * 2 + 8) / 3)


def test_macd_columns_and_relation():
    rng = np.random.default_rng(2)
    close = s(100 + rng.normal(0, 1, 200).cumsum())
    m = macd(close)
    assert list(m.columns) == ["macd", "signal", "hist"]
    pd.testing.assert_series_equal(m["hist"], m["macd"] - m["signal"], check_names=False)
    assert m["macd"].iloc[:25].isna().all() and m["macd"].iloc[25:].notna().all()


def test_true_range_uses_previous_close():
    c = pd.DataFrame({"high": [10, 12], "low": [9, 11], "close": [9.5, 11.5]}, dtype=float)
    # Vela 2: high-low = 1, |high - close previo| = 2.5, |low - close previo| = 1.5
    assert true_range(c).tolist() == [1.0, 2.5]


def test_atr_constant_range():
    n = 40
    c = pd.DataFrame({"high": [101.0] * n, "low": [99.0] * n, "close": [100.0] * n})
    out = atr(c, 14)
    assert out.iloc[:13].isna().all()
    assert out.dropna().eq(2.0).all()


def test_no_lookahead():
    """Cambiar el futuro no puede alterar el valor de un indicador en el pasado."""
    rng = np.random.default_rng(3)
    close = s(100 + rng.normal(0, 1, 300).cumsum())
    altered = close.copy()
    altered.iloc[200:] *= 1.5
    candles = pd.DataFrame({"high": close + 1, "low": close - 1, "close": close})
    candles_alt = pd.DataFrame({"high": altered + 1, "low": altered - 1, "close": altered})
    for f in (lambda x: ema(x, 50), lambda x: rsi(x, 14), lambda x: macd(x)["hist"]):
        pd.testing.assert_series_equal(f(close).iloc[:200], f(altered).iloc[:200])
    pd.testing.assert_series_equal(atr(candles).iloc[:200], atr(candles_alt).iloc[:200])
