"""Motor de backtesting por velas, solo largo (Spot, sin apalancamiento).

Recorre el histórico con el mismo `SimBroker` que usa el paper trading:
- Las señales se calculan con la vela cerrada `i` y se ejecutan en la apertura
  de la vela `i + 1`.
- El stop se fija al entrar y se revisa dentro de cada vela con su mínimo. Si la
  vela abre por debajo del stop (gap), se sale al precio de apertura, no al stop.
- Toda compra y venta paga comisión y deslizamiento.
- El tamaño se calcula para arriesgar `risk_per_trade` del capital hasta el
  stop, limitado a `max_position_fraction` del capital (sin apalancamiento).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from btcbot.backtest.broker import AccountState, SimBroker, Trade
from btcbot.timeframes import timeframe_delta

__all__ = ["SIGNAL_COLUMNS", "BacktestResult", "Trade", "run_backtest"]

SIGNAL_COLUMNS = ("entry", "exit", "stop_distance")


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    trades: list[Trade]
    exposure: float  # fracción de velas con posición abierta

    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ for t in self.trades])


def run_backtest(
    candles: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    timeframe: str,
    initial_capital: float,
    fee_rate: float,
    slippage_rate: float,
    risk_per_trade: float,
    max_position_fraction: float = 1.0,
) -> BacktestResult:
    missing = [c for c in SIGNAL_COLUMNS if c not in signals.columns]
    if missing:
        raise ValueError(f"Faltan columnas de señal: {missing}")
    if not signals.index.equals(candles.index):
        raise ValueError("Las señales deben tener el mismo índice que las velas")

    broker = SimBroker(fee_rate, slippage_rate, risk_per_trade, max_position_fraction)
    state = AccountState(cash=initial_capital)

    opens = candles["open"].to_numpy(float)
    lows = candles["low"].to_numpy(float)
    closes = candles["close"].to_numpy(float)
    times = candles.index
    entry_sig = signals["entry"].fillna(False).to_numpy(bool)
    exit_sig = signals["exit"].fillna(False).to_numpy(bool)
    stop_dist = signals["stop_distance"].to_numpy(float)

    n = len(candles)
    equity = np.empty(n)
    trades: list[Trade] = []
    for i in range(n):
        fills = broker.step(
            state, times[i], opens[i], lows[i], closes[i],
            bool(entry_sig[i]), bool(exit_sig[i]), float(stop_dist[i]),
            allow_new_orders=i < n - 1,
        )
        trades.extend(f.trade for f in fills if f.trade is not None)
        equity[i] = state.equity(closes[i])

    # Posición abierta al final: se liquida al último cierre con costes
    if state.in_position:
        fill = broker.liquidate(state, times[-1], closes[-1], "end")
        trades.append(fill.trade)
        equity[-1] = state.cash

    curve = pd.Series(equity, index=times + timeframe_delta(timeframe))
    start = pd.Series([initial_capital], index=[times[0]])
    return BacktestResult(
        equity=pd.concat([start, curve]).rename("equity"),
        trades=trades,
        exposure=state.bars_in_position / n if n else 0.0,
    )
