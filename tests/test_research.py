import pandas as pd
import pytest
from conftest import make_candles

from btcbot.backtest.research import (
    RunSettings,
    param_grid,
    robustness,
    valid_params,
    walk_forward,
)

S = RunSettings(timeframe="4h", periods_per_year=2190, initial_capital=1000.0, fee_rate=0.001,
                slippage_rate=0.0005, risk_per_trade=0.01, max_position_fraction=1.0)
GRID = {"fast": [5, 10], "slow": [20, 30], "regime": [50], "stop_atr": [2.0, 3.0]}
BASE = {"fast": 10, "slow": 30, "regime": 50, "stop_atr": 2.0}


@pytest.fixture(scope="module")
def candles():
    # ~3 años de velas 4h sintéticas
    return make_candles("2020-01-01", 6 * 365 * 3, seed=21)


def test_param_grid_cartesian_product():
    combos = param_grid({"a": [1, 2], "b": [3, 4, 5]})
    assert len(combos) == 6
    assert {"a": 2, "b": 5} in combos


def test_valid_params_drops_invalid_combos():
    combos = param_grid({"fast": [10, 50], "slow": [30]})
    valid = valid_params("ema_trend", combos)
    assert [c for c, _ in valid] == [{"fast": 10, "slow": 30}]


def test_robustness_one_row_per_combo(candles):
    table = robustness(candles, slice(None), "ema_trend", GRID, S)
    assert len(table) == 8
    assert {"sharpe", "cagr", "max_drawdown", "trades", "profit_factor"} <= set(table.columns)


def wf(candles):
    return walk_forward(candles, "ema_trend", GRID, BASE, S,
                        first_test=pd.Timestamp("2021-01-01", tz="UTC"),
                        end=pd.Timestamp("2022-07-01", tz="UTC"),
                        train_months=12, test_months=6, min_train_trades=3)


def test_walk_forward_windows(candles):
    r = wf(candles)
    assert list(r.windows["test_start"].dt.strftime("%Y-%m")) == ["2021-01", "2021-07", "2022-01"]
    assert r.equity.index[0] == pd.Timestamp("2021-01-01", tz="UTC")
    assert r.equity.index[-1] <= pd.Timestamp("2022-07-01", tz="UTC")
    assert r.windows["test_return"].notna().all()


def test_walk_forward_selection_ignores_test_data(candles):
    """Cambiar los datos de la ventana de prueba no puede cambiar los parámetros elegidos
    para esa ventana (solo se eligen con el entrenamiento)."""
    altered = candles.copy()
    test_period = altered.index >= pd.Timestamp("2021-01-01", tz="UTC")
    altered.loc[test_period, ["open", "high", "low", "close"]] *= 0.5
    a, b = wf(candles), wf(altered)
    cols = ["fast", "slow", "regime", "stop_atr", "train_sharpe"]
    pd.testing.assert_series_equal(a.windows.iloc[0][cols], b.windows.iloc[0][cols])


def test_walk_forward_end_is_respected(candles):
    r = wf(candles)
    for curve in (r.equity, r.fixed_equity, r.buy_hold_equity):
        assert curve.index.max() <= pd.Timestamp("2022-07-01", tz="UTC")
