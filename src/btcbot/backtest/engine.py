"""Motor de backtesting por velas, solo largo (Spot, sin apalancamiento).

Reglas para no mirar el futuro:
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

from btcbot.timeframes import timeframe_delta

SIGNAL_COLUMNS = ("entry", "exit", "stop_distance")


@dataclass(frozen=True)
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    units: float
    stop: float
    pnl: float  # USDT neto, después de costes
    net_return: float  # pnl / capital invertido (incluida la comisión de compra)
    exit_reason: str  # "stop", "signal" o "end"
    bars: int


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
    if not 0 < max_position_fraction <= 1:
        raise ValueError("max_position_fraction debe estar en (0, 1]: no hay apalancamiento")

    opens = candles["open"].to_numpy(float)
    lows = candles["low"].to_numpy(float)
    closes = candles["close"].to_numpy(float)
    times = candles.index
    entry_sig = signals["entry"].fillna(False).to_numpy(bool)
    exit_sig = signals["exit"].fillna(False).to_numpy(bool)
    stop_dist = signals["stop_distance"].to_numpy(float)

    n = len(candles)
    equity = np.empty(n)
    cash = initial_capital
    units = 0.0
    stop = entry_price = cost_basis = 0.0
    entry_idx = -1
    pending_entry = pending_exit = False
    pending_dist = np.nan
    bars_in_position = 0
    trades: list[Trade] = []

    def close_position(i: int, raw_price: float, reason: str) -> None:
        nonlocal cash, units
        exit_price = raw_price * (1 - slippage_rate)
        proceeds = units * exit_price * (1 - fee_rate)
        cash += proceeds
        pnl = proceeds - cost_basis
        trades.append(Trade(
            entry_time=times[entry_idx], entry_price=entry_price,
            exit_time=times[i], exit_price=exit_price, units=units, stop=stop,
            pnl=pnl, net_return=pnl / cost_basis, exit_reason=reason,
            bars=i - entry_idx + 1,
        ))
        units = 0.0

    for i in range(n):
        # 1) Órdenes decididas al cierre anterior se ejecutan en esta apertura
        if pending_exit and units > 0:
            close_position(i, opens[i], "signal")
        if pending_entry and units == 0:
            fill = opens[i] * (1 + slippage_rate)
            new_stop = fill - pending_dist
            if new_stop > 0:
                budget = cash * max_position_fraction
                by_risk = cash * risk_per_trade / (fill - new_stop)
                by_cash = budget / (fill * (1 + fee_rate))
                units = min(by_risk, by_cash)
                cost_basis = units * fill * (1 + fee_rate)
                cash -= cost_basis
                entry_price, stop, entry_idx = fill, new_stop, i
        pending_entry = pending_exit = False

        # 2) Stop dentro de la vela (con gap: se sale a la apertura)
        if units > 0 and lows[i] <= stop:
            close_position(i, min(opens[i], stop), "stop")

        # 3) Valoración al cierre
        if units > 0:
            bars_in_position += 1
        equity[i] = cash + units * closes[i]

        # 4) Señales de esta vela cerrada → órdenes para la próxima apertura
        if i < n - 1:
            if units > 0 and exit_sig[i]:
                pending_exit = True
            elif units == 0 and entry_sig[i] and np.isfinite(stop_dist[i]) and stop_dist[i] > 0:
                pending_entry = True
                pending_dist = stop_dist[i]

    # Posición abierta al final: se liquida al último cierre con costes
    if units > 0:
        close_position(n - 1, closes[-1], "end")
        equity[-1] = cash

    curve = pd.Series(equity, index=times + timeframe_delta(timeframe))
    start = pd.Series([initial_capital], index=[times[0]])
    return BacktestResult(
        equity=pd.concat([start, curve]).rename("equity"),
        trades=trades,
        exposure=bars_in_position / n if n else 0.0,
    )
