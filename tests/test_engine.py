import numpy as np
import pandas as pd
import pytest
from conftest import make_candles

from btcbot.backtest.engine import run_backtest
from btcbot.strategies import build_signals
from btcbot.strategies.ema_trend import EmaTrendParams, ema_trend_signals


def bars(rows):
    """rows: lista de (open, high, low, close)."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="4h", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float)


def sigs(candles, entries=(), exits=(), dist=10.0):
    s = pd.DataFrame(
        {"entry": False, "exit": False, "stop_distance": dist}, index=candles.index
    )
    s.iloc[list(entries), 0] = True
    s.iloc[list(exits), 1] = True
    return s


def run(candles, signals, fee=0.0, slip=0.0, risk=1.0, max_frac=1.0):
    return run_backtest(candles, signals, timeframe="4h", initial_capital=1000.0,
                        fee_rate=fee, slippage_rate=slip, risk_per_trade=risk,
                        max_position_fraction=max_frac)


FLAT = (100, 101, 99, 100)


def test_entry_fills_at_next_open():
    c = bars([FLAT, (105, 106, 104, 105), (110, 111, 109, 110), FLAT])
    r = run(c, sigs(c, entries=[0], exits=[1]))
    t = r.trades[0]
    assert t.entry_time == c.index[1] and t.entry_price == 105
    assert t.exit_time == c.index[2] and t.exit_price == 110
    assert t.exit_reason == "signal"


def test_signal_on_last_candle_is_ignored():
    c = bars([FLAT, FLAT, FLAT])
    r = run(c, sigs(c, entries=[2]))
    assert r.trades == []
    assert r.equity.iloc[-1] == 1000


def test_stop_inside_candle():
    # Entra a 100 con stop a 90; la vela 2 toca 85 → sale a 90
    c = bars([FLAT, FLAT, (95, 96, 85, 88), FLAT])
    r = run(c, sigs(c, entries=[0]))
    t = r.trades[0]
    assert t.exit_reason == "stop" and t.exit_price == 90 and t.exit_time == c.index[2]


def test_stop_with_gap_fills_at_open():
    # Abre en 80, por debajo del stop de 90 → se sale a 80, no a 90
    c = bars([FLAT, FLAT, (80, 82, 78, 81), FLAT])
    r = run(c, sigs(c, entries=[0]))
    assert r.trades[0].exit_price == 80


def test_risk_based_sizing():
    # Riesgo 1 % de 1000 = 10 USDT; distancia al stop 10 → 1 unidad (100 USDT invertidos)
    c = bars([FLAT, FLAT, FLAT])
    r = run(c, sigs(c, entries=[0]), risk=0.01)
    assert r.trades[0].units == pytest.approx(1.0)


def test_sizing_capped_by_cash_no_leverage():
    # Riesgo 50 % con stop a 10 → pediría 50 unidades (5000 USDT); solo hay 1000
    c = bars([FLAT, FLAT, FLAT])
    r = run(c, sigs(c, entries=[0]), risk=0.5, fee=0.001)
    t = r.trades[0]
    assert t.units * t.entry_price * 1.001 == pytest.approx(1000)


def test_stop_loss_costs_about_the_risk():
    c = bars([FLAT, FLAT, (95, 96, 85, 88), FLAT])
    r = run(c, sigs(c, entries=[0]), risk=0.01)
    assert r.trades[0].pnl == pytest.approx(-10)
    assert r.equity.iloc[-1] == pytest.approx(990)


def test_costs_applied_on_both_sides():
    c = bars([FLAT, FLAT, FLAT, FLAT])
    r = run(c, sigs(c, entries=[0], exits=[1]), fee=0.001, slip=0.0005, risk=1.0)
    t = r.trades[0]
    assert t.entry_price == pytest.approx(100 * 1.0005)
    assert t.exit_price == pytest.approx(100 * 0.9995)
    assert t.pnl < 0  # precio plano: solo se pierden costes


def test_open_position_liquidated_at_end():
    c = bars([FLAT, FLAT, (120, 121, 119, 120)])
    r = run(c, sigs(c, entries=[0]))
    t = r.trades[-1]
    assert t.exit_reason == "end" and t.exit_price == 120
    assert r.equity.iloc[-1] == pytest.approx(1000 + t.pnl)


def test_equity_equals_initial_plus_pnl():
    c = make_candles("2020-01-01", 2000, seed=7)
    s, _ = build_signals("ema_trend", c, {"fast": 10, "slow": 30, "regime": 100})
    r = run(c, s, fee=0.001, slip=0.0005, risk=0.01)
    assert len(r.trades) > 5
    assert r.equity.iloc[-1] == pytest.approx(1000 + sum(t.pnl for t in r.trades))


def test_no_lookahead_in_engine_and_strategy():
    """Alterar el futuro no puede cambiar el pasado de la curva de capital."""
    c = make_candles("2020-01-01", 1500, seed=11)
    p = EmaTrendParams(fast=10, slow=30, regime=100)
    cut = 1000
    altered = c.copy()
    altered.iloc[cut:, :4] *= np.linspace(1, 3, len(c) - cut)[:, None]
    r1 = run(c, ema_trend_signals(c, p), risk=0.01)
    r2 = run(altered, ema_trend_signals(altered, p), risk=0.01)
    # Hasta el cierre de la vela cut-1 todo debe ser idéntico
    pd.testing.assert_series_equal(r1.equity.iloc[:cut], r2.equity.iloc[:cut])


def test_rejects_leverage():
    c = bars([FLAT, FLAT])
    with pytest.raises(ValueError):
        run(c, sigs(c), max_frac=2.0)


def test_strategy_entry_is_edge_triggered():
    c = make_candles("2020-01-01", 3000, seed=5)
    s = ema_trend_signals(c, EmaTrendParams(fast=10, slow=30, regime=100))
    assert not (s["entry"] & s["entry"].shift(1, fill_value=False)).any()
    assert not s["entry"].iloc[:100].any()  # calentamiento de la EMA de régimen
