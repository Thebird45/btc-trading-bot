"""Broker simulado que procesa una vela a la vez.

Es la única implementación de las reglas de ejecución: la usan tanto el
backtest (recorriendo el histórico) como el paper trading (vela a vela en vivo),
para que ambos se comporten exactamente igual.

Orden dentro de cada vela cerrada:
1. Se ejecutan las órdenes decididas al cierre anterior, a la apertura.
2. Se revisa el stop con el mínimo de la vela (con gap, se sale a la apertura).
3. Se valora la cuenta al cierre.
4. Se leen las señales de esta vela → órdenes para la próxima apertura.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd


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
    exit_reason: str  # "stop", "signal", "end" o "manual"
    bars: int


@dataclass
class AccountState:
    """Estado completo de la cuenta simulada. Serializable para guardarlo en disco."""

    cash: float
    units: float = 0.0
    entry_price: float = 0.0
    entry_time: pd.Timestamp | None = None
    stop: float = 0.0
    cost_basis: float = 0.0
    bars_held: int = 0
    pending_entry: bool = False
    pending_dist: float = math.nan
    pending_exit: bool = False
    bars_in_position: int = 0
    candles_seen: int = 0

    @property
    def in_position(self) -> bool:
        return self.units > 0

    def equity(self, price: float) -> float:
        return self.cash + self.units * price

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_time"] = self.entry_time.isoformat() if self.entry_time is not None else None
        d["pending_dist"] = None if math.isnan(self.pending_dist) else self.pending_dist
        return d

    @classmethod
    def from_dict(cls, d: dict) -> AccountState:
        d = dict(d)
        d["entry_time"] = pd.Timestamp(d["entry_time"]) if d.get("entry_time") else None
        d["pending_dist"] = math.nan if d.get("pending_dist") is None else d["pending_dist"]
        return cls(**d)


@dataclass(frozen=True)
class Fill:
    """Algo que pasó durante una vela: una compra o una venta."""

    kind: str  # "buy" o "sell"
    time: pd.Timestamp
    price: float
    units: float
    reason: str  # "signal", "stop", "end" o "manual"
    trade: Trade | None = None  # en las ventas, la operación cerrada


@dataclass(frozen=True)
class SimBroker:
    fee_rate: float
    slippage_rate: float
    risk_per_trade: float
    max_position_fraction: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.max_position_fraction <= 1:
            raise ValueError("max_position_fraction debe estar en (0, 1]: no hay apalancamiento")

    def _sell(self, s: AccountState, time: pd.Timestamp, raw_price: float, reason: str) -> Fill:
        price = raw_price * (1 - self.slippage_rate)
        proceeds = s.units * price * (1 - self.fee_rate)
        pnl = proceeds - s.cost_basis
        trade = Trade(
            entry_time=s.entry_time, entry_price=s.entry_price, exit_time=time,
            exit_price=price, units=s.units, stop=s.stop, pnl=pnl,
            net_return=pnl / s.cost_basis, exit_reason=reason, bars=s.bars_held,
        )
        fill = Fill("sell", time, price, s.units, reason, trade)
        s.cash += proceeds
        s.units = 0.0
        s.cost_basis = 0.0
        s.bars_held = 0
        return fill

    def _buy(self, s: AccountState, time: pd.Timestamp, raw_price: float) -> Fill | None:
        price = raw_price * (1 + self.slippage_rate)
        stop = price - s.pending_dist
        if not stop > 0:
            return None
        by_risk = s.cash * self.risk_per_trade / (price - stop)
        by_cash = s.cash * self.max_position_fraction / (price * (1 + self.fee_rate))
        units = min(by_risk, by_cash)
        s.cost_basis = units * price * (1 + self.fee_rate)
        s.cash -= s.cost_basis
        s.units, s.entry_price, s.entry_time, s.stop, s.bars_held = units, price, time, stop, 1
        return Fill("buy", time, price, units, "signal")

    def step(
        self,
        s: AccountState,
        time: pd.Timestamp,
        open_: float,
        low: float,
        close: float,
        entry_signal: bool,
        exit_signal: bool,
        stop_distance: float,
        allow_new_orders: bool = True,
        allow_entries: bool = True,
    ) -> list[Fill]:
        """Procesa una vela cerrada y modifica `s`. Devuelve las ejecuciones.

        allow_new_orders=False: no se programan órdenes para la siguiente vela
        (última vela del backtest). allow_entries=False: no se programan compras
        (bot pausado o límite de pérdida diaria), pero sí ventas y stops.
        """
        fills: list[Fill] = []
        if s.in_position:
            s.bars_held += 1

        # 1) Órdenes pendientes, a la apertura
        if s.pending_exit and s.in_position:
            fills.append(self._sell(s, time, open_, "signal"))
        if s.pending_entry and not s.in_position:
            buy = self._buy(s, time, open_)
            if buy:
                fills.append(buy)
        s.pending_entry = s.pending_exit = False
        s.pending_dist = math.nan

        # 2) Stop dentro de la vela
        if s.in_position and low <= s.stop:
            fills.append(self._sell(s, time, min(open_, s.stop), "stop"))

        # 3) Contabilidad al cierre
        s.candles_seen += 1
        if s.in_position:
            s.bars_in_position += 1

        # 4) Señales de esta vela → órdenes para la próxima apertura
        if allow_new_orders:
            if s.in_position and exit_signal:
                s.pending_exit = True
            elif (not s.in_position and allow_entries and entry_signal
                  and math.isfinite(stop_distance) and stop_distance > 0):
                s.pending_entry = True
                s.pending_dist = stop_distance
        return fills

    def liquidate(self, s: AccountState, time: pd.Timestamp, price: float, reason: str) -> Fill:
        """Cierra la posición a `price` (fin del backtest o cierre manual)."""
        return self._sell(s, time, price, reason)
