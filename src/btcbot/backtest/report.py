"""Informes de backtesting en Markdown."""

from __future__ import annotations

import math

import pandas as pd

from btcbot.backtest.metrics import EquityMetrics


def pct(x: float) -> str:
    return "n/d" if math.isnan(x) else f"{x * 100:,.2f} %"


def num(x: float) -> str:
    return "n/d" if math.isnan(x) else f"{x:,.2f}"


def metrics_table(m: EquityMetrics) -> str:
    rows = [
        ("Periodo", f"{m.start:%Y-%m-%d} → {m.end:%Y-%m-%d}"),
        ("Capital inicial", f"{m.initial:,.2f} USDT"),
        ("Capital final (neto)", f"{m.final:,.2f} USDT"),
        ("Retorno total", pct(m.total_return)),
        ("CAGR", pct(m.cagr)),
        ("Volatilidad anualizada", pct(m.volatility)),
        ("Sharpe", num(m.sharpe)),
        ("Sortino", num(m.sortino)),
        ("Drawdown máximo", pct(m.max_drawdown)),
        ("Racha más larga bajo el máximo", f"{m.max_drawdown_days:,.0f} días"),
    ]
    lines = ["| Métrica | Valor |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def yearly_table(yearly: pd.DataFrame) -> str:
    lines = ["| Año | Retorno | Drawdown máx. |", "|---|---|---|"]
    for year, r in yearly.iterrows():
        lines.append(f"| {year} | {pct(r['return'])} | {pct(r['max_drawdown'])} |")
    return "\n".join(lines)
