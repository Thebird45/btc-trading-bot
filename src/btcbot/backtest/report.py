"""Informes de backtesting en Markdown."""

from __future__ import annotations

import math

import pandas as pd

from btcbot.backtest.metrics import EquityMetrics, TradeMetrics


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


def calmar(m: EquityMetrics) -> float:
    return m.cagr / abs(m.max_drawdown) if m.max_drawdown < 0 else float("nan")


def comparison_table(strat: EquityMetrics, bh: EquityMetrics, exposure: float) -> str:
    rows = [
        ("Capital final (neto)", f"{strat.final:,.2f} USDT", f"{bh.final:,.2f} USDT"),
        ("Retorno total", pct(strat.total_return), pct(bh.total_return)),
        ("CAGR", pct(strat.cagr), pct(bh.cagr)),
        ("Volatilidad anualizada", pct(strat.volatility), pct(bh.volatility)),
        ("Sharpe", num(strat.sharpe), num(bh.sharpe)),
        ("Sortino", num(strat.sortino), num(bh.sortino)),
        ("Drawdown máximo", pct(strat.max_drawdown), pct(bh.max_drawdown)),
        ("Calmar (CAGR / DD)", num(calmar(strat)), num(calmar(bh))),
        ("Racha más larga bajo el máximo",
         f"{strat.max_drawdown_days:,.0f} días", f"{bh.max_drawdown_days:,.0f} días"),
        ("Tiempo invertido", pct(exposure), "100,00 %"),
    ]
    lines = ["| Métrica | Estrategia | Buy & hold |", "|---|---|---|"]
    lines += [f"| {k} | {a} | {b} |" for k, a, b in rows]
    return "\n".join(lines)


def trades_table(tm: TradeMetrics, stops: int) -> str:
    rows = [
        ("Operaciones", f"{tm.trades}"),
        ("Acierto (win rate)", pct(tm.win_rate)),
        ("Profit factor", num(tm.profit_factor)),
        ("Expectativa por operación", pct(tm.expectancy)),
        ("Ganancia media", pct(tm.avg_win)),
        ("Pérdida media", pct(tm.avg_loss)),
        ("Salidas por stop", f"{stops}"),
    ]
    lines = ["| Métrica | Valor |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def yearly_comparison_table(strat: pd.DataFrame, bh: pd.DataFrame) -> str:
    lines = ["| Año | Estrategia | DD estrategia | Buy & hold | DD buy & hold |",
             "|---|---|---|---|---|"]
    for year in strat.index:
        s, b = strat.loc[year], bh.loc[year]
        lines.append(f"| {year} | {pct(s['return'])} | {pct(s['max_drawdown'])} | "
                     f"{pct(b['return'])} | {pct(b['max_drawdown'])} |")
    return "\n".join(lines)


def yearly_table(yearly: pd.DataFrame) -> str:
    lines = ["| Año | Retorno | Drawdown máx. |", "|---|---|---|"]
    for year, r in yearly.iterrows():
        lines.append(f"| {year} | {pct(r['return'])} | {pct(r['max_drawdown'])} |")
    return "\n".join(lines)
