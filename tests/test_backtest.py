import math

import pandas as pd
import pytest

from btcbot.backtest.baseline import buy_and_hold
from btcbot.backtest.metrics import (
    equity_metrics,
    longest_drawdown_days,
    max_drawdown,
    trade_metrics,
    yearly_breakdown,
)


def series(values, start="2024-01-01", freq="1D"):
    idx = pd.date_range(start, periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


def flat_candles(prices, freq="4h"):
    idx = pd.date_range("2024-01-01", periods=len(prices), freq=freq, tz="UTC")
    return pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices},
                        index=idx, dtype=float)


def test_buy_and_hold_without_costs_tracks_price():
    eq = buy_and_hold(flat_candles([100, 110, 120, 150]), "4h", 1000, 0, 0)
    assert eq.iloc[0] == 1000
    assert eq.iloc[-1] == pytest.approx(1500)
    assert len(eq) == 5


def test_buy_and_hold_charges_costs_on_both_sides():
    eq = buy_and_hold(flat_candles([100, 100]), "4h", 1000, fee_rate=0.001, slippage_rate=0.0005)
    expected = 1000 * 0.999 / 1.0005 * 0.9995 * 0.999
    assert eq.iloc[-1] == pytest.approx(expected)
    assert eq.iloc[-1] < 1000  # precio plano: solo se pierden costes


def test_buy_and_hold_indexes_at_candle_close():
    eq = buy_and_hold(flat_candles([100, 100, 100]), "4h", 1000, 0, 0)
    assert eq.index[1] - eq.index[0] == pd.Timedelta(hours=4)
    assert eq.index.is_monotonic_increasing


def test_max_drawdown():
    assert max_drawdown(series([100, 120, 60, 90, 130])) == pytest.approx(-0.5)
    assert max_drawdown(series([1, 2, 3])) == 0


def test_longest_drawdown_days():
    # Bajo el máximo del día 1 al día 4 (recupera el día 4): 3 días
    assert longest_drawdown_days(series([100, 120, 90, 110, 125, 130])) == pytest.approx(3)


def test_equity_metrics_doubling_in_one_year():
    eq = series([100, 200], start="2023-01-01", freq="365D")
    m = equity_metrics(eq, periods_per_year=1)
    assert m.total_return == pytest.approx(1.0)
    assert m.cagr == pytest.approx(1.0)


def test_equity_metrics_needs_two_points():
    with pytest.raises(ValueError):
        equity_metrics(series([100]), 365)


def test_trade_metrics_high_win_rate_can_lose():
    # 80 % de acierto ganando 1 % y perdiendo 5 %: expectativa negativa
    r = [0.01] * 8 + [-0.05] * 2
    m = trade_metrics(r)
    assert m.win_rate == pytest.approx(0.8)
    assert m.expectancy < 0
    assert m.profit_factor == pytest.approx(0.8)


def test_trade_metrics_empty():
    m = trade_metrics([])
    assert m.trades == 0 and math.isnan(m.win_rate)


def test_yearly_breakdown_chains_years():
    eq = pd.Series(
        [100.0, 150.0, 120.0, 180.0],
        index=pd.to_datetime(["2023-06-01", "2023-12-31", "2024-06-01", "2024-12-31"], utc=True),
    )
    y = yearly_breakdown(eq)
    assert y.loc[2023, "return"] == pytest.approx(0.5)
    assert y.loc[2024, "return"] == pytest.approx(0.2)  # 150 → 180
    assert y.loc[2024, "max_drawdown"] == pytest.approx(-0.2)  # 150 → 120


def test_yearly_breakdown_close_at_new_year_belongs_to_previous_year():
    eq = pd.Series(
        [100.0, 110.0, 121.0],
        index=pd.to_datetime(["2024-12-31 16:00", "2024-12-31 20:00", "2025-01-01 00:00"],
                             utc=True),
    )
    y = yearly_breakdown(eq)
    assert list(y.index) == [2024]
    assert y.loc[2024, "return"] == pytest.approx(0.21)
