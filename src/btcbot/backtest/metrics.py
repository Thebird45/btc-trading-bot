"""Métricas de desempeño sobre curvas de capital y operaciones cerradas."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EquityMetrics:
    start: pd.Timestamp
    end: pd.Timestamp
    initial: float
    final: float
    total_return: float
    cagr: float
    volatility: float  # anualizada
    sharpe: float  # sin tasa libre de riesgo
    sortino: float
    max_drawdown: float  # valor negativo, p. ej. -0.77
    max_drawdown_days: float  # duración de la peor racha bajo el máximo previo


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    return float((equity / peak - 1).min())


def longest_drawdown_days(equity: pd.Series) -> float:
    """Duración más larga, en días, desde un máximo hasta recuperarlo (o hasta el final)."""
    underwater = equity < equity.cummax()
    longest = pd.Timedelta(0)
    peak_ts = equity.index[0]
    in_drawdown = False
    for ts, under in underwater.items():
        if under:
            in_drawdown = True
        else:
            if in_drawdown:
                longest = max(longest, ts - peak_ts)
                in_drawdown = False
            peak_ts = ts
    if in_drawdown:
        longest = max(longest, equity.index[-1] - peak_ts)
    return longest / pd.Timedelta(days=1)


def equity_metrics(equity: pd.Series, periods_per_year: float) -> EquityMetrics:
    if len(equity) < 2:
        raise ValueError("Se necesitan al menos 2 puntos de capital")
    returns = equity.pct_change().dropna()
    years = (equity.index[-1] - equity.index[0]) / pd.Timedelta(days=365)
    total = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else float("nan")

    std = returns.std()
    downside = returns[returns < 0]
    down_std = np.sqrt((downside**2).sum() / len(returns)) if len(returns) else 0.0
    ann = np.sqrt(periods_per_year)
    mean = returns.mean()

    return EquityMetrics(
        start=equity.index[0],
        end=equity.index[-1],
        initial=float(equity.iloc[0]),
        final=float(equity.iloc[-1]),
        total_return=float(total),
        cagr=float(cagr),
        volatility=float(std * ann),
        sharpe=float(mean / std * ann) if std > 0 else float("nan"),
        sortino=float(mean / down_std * ann) if down_std > 0 else float("nan"),
        max_drawdown=max_drawdown(equity),
        max_drawdown_days=longest_drawdown_days(equity),
    )


@dataclass(frozen=True)
class TradeMetrics:
    trades: int
    win_rate: float
    profit_factor: float
    expectancy: float  # retorno neto medio por operación
    avg_win: float
    avg_loss: float


def trade_metrics(net_returns: Sequence[float]) -> TradeMetrics:
    """Métricas por operación a partir de retornos netos (después de costes)."""
    r = np.asarray(net_returns, dtype=float)
    if r.size == 0:
        nan = float("nan")
        return TradeMetrics(0, nan, nan, nan, nan, nan)
    wins, losses = r[r > 0], r[r <= 0]
    gross_loss = -losses.sum()
    return TradeMetrics(
        trades=int(r.size),
        win_rate=float(wins.size / r.size),
        profit_factor=float(wins.sum() / gross_loss) if gross_loss > 0 else float("inf"),
        expectancy=float(r.mean()),
        avg_win=float(wins.mean()) if wins.size else 0.0,
        avg_loss=float(losses.mean()) if losses.size else 0.0,
    )


def yearly_breakdown(equity: pd.Series) -> pd.DataFrame:
    """Retorno y drawdown máximo por año calendario."""
    rows = []
    for year, chunk in equity.groupby(equity.index.year):
        # El año arranca desde el cierre del año anterior para no perder la primera vela
        prev = equity[equity.index < chunk.index[0]]
        base = pd.concat([prev.iloc[-1:], chunk]) if len(prev) else chunk
        rows.append({
            "year": int(year),
            "return": float(base.iloc[-1] / base.iloc[0] - 1),
            "max_drawdown": max_drawdown(base),
        })
    return pd.DataFrame(rows).set_index("year")
