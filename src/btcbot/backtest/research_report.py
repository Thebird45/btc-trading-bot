"""Informes Markdown de robustez y walk-forward."""

from __future__ import annotations

import pandas as pd

from btcbot.backtest.metrics import EquityMetrics
from btcbot.backtest.report import calmar, num, pct


def robustness_report(
    table: pd.DataFrame, base: dict, bh_sharpe: float, period: str, header: str
) -> str:
    n = len(table)
    sharpe = table["sharpe"]
    is_base = pd.Series(True, index=table.index)
    for k, v in base.items():
        if k in table.columns:
            is_base &= table[k] == v
    base_row = table[is_base].iloc[0] if is_base.any() else None
    base_rank = (sharpe < base_row["sharpe"]).mean() if base_row is not None else float("nan")

    def share(cond) -> str:
        return f"{int(cond.sum())} de {n} ({cond.mean():.0%})"

    lines = [
        header,
        "",
        f"Periodo: {period} (dentro de muestra, sin holdout). {n} combinaciones de parámetros.",
        "",
        "## Resumen",
        "",
        "| Pregunta | Resultado |",
        "|---|---|",
        f"| Combinaciones con Sharpe mayor que buy & hold ({num(bh_sharpe)}) | "
        f"{share(sharpe > bh_sharpe)} |",
        f"| Combinaciones con profit factor > 1 | {share(table['profit_factor'] > 1)} |",
        f"| Combinaciones con CAGR > 0 | {share(table['cagr'] > 0)} |",
        f"| Sharpe: mínimo / p10 / mediana / p90 / máximo | {num(sharpe.min())} / "
        f"{num(sharpe.quantile(0.1))} / {num(sharpe.median())} / "
        f"{num(sharpe.quantile(0.9))} / {num(sharpe.max())} |",
    ]
    if base_row is not None:
        lines.append(f"| Parámetros base: Sharpe y percentil | {num(base_row['sharpe'])} "
                     f"(mejor que el {base_rank:.0%} de la rejilla) |")

    lines += ["", "## Sharpe mediano por EMA rápida × lenta", "",
              "(mediana sobre todos los valores de régimen y stop)", ""]
    pivot = table.pivot_table(index="fast", columns="slow", values="sharpe", aggfunc="median")
    lines.append("| rápida \\ lenta | " + " | ".join(str(c) for c in pivot.columns) + " |")
    lines.append("|---" * (len(pivot.columns) + 1) + "|")
    for fast, row in pivot.iterrows():
        lines.append(f"| {fast} | " + " | ".join(num(v) for v in row) + " |")

    for col, title in (("stop_atr", "stop (× ATR)"), ("regime", "EMA de régimen")):
        if col not in table.columns:
            continue
        g = table.groupby(col).agg(sharpe=("sharpe", "median"), dd=("max_drawdown", "median"),
                                   pf=("profit_factor", "median"), trades=("trades", "median"))
        lines += ["", f"## Por {title} (medianas)", "",
                  f"| {title} | Sharpe | Drawdown | Profit factor | Operaciones |",
                  "|---|---|---|---|---|"]
        for v, r in g.iterrows():
            lines.append(f"| {v} | {num(r['sharpe'])} | {pct(r['dd'])} | {num(r['pf'])} | "
                         f"{r['trades']:.0f} |")

    params = [c for c in ("fast", "slow", "regime", "stop_atr") if c in table.columns]
    for title, rows in (("Mejores 5", table.nlargest(5, "sharpe")),
                        ("Peores 5", table.nsmallest(5, "sharpe"))):
        lines += ["", f"## {title} combinaciones por Sharpe", "",
                  "| " + " | ".join(params) + " | Sharpe | CAGR | Drawdown | PF | Operaciones |",
                  "|---" * (len(params) + 5) + "|"]
        for _, r in rows.iterrows():
            lines.append("| " + " | ".join(f"{r[p]:g}" for p in params) +
                         f" | {num(r['sharpe'])} | {pct(r['cagr'])} | {pct(r['max_drawdown'])} | "
                         f"{num(r['profit_factor'])} | {r['trades']:.0f} |")
    return "\n".join(lines)


def walkforward_report(
    windows: pd.DataFrame,
    wf: EquityMetrics,
    fixed: EquityMetrics,
    bh: EquityMetrics,
    trades: int,
    header: str,
    settings: str,
) -> str:
    def row(name, f):
        return (f"| {name} | {f(wf)} | {f(fixed)} | {f(bh)} |")

    params = [c for c in ("fast", "slow", "regime", "stop_atr") if c in windows.columns]
    changes = sum(
        any(windows[p].iloc[i] != windows[p].iloc[i - 1] for p in params)
        for i in range(1, len(windows))
    )
    lines = [
        header,
        "",
        settings,
        "",
        "## Curva fuera de muestra encadenada",
        "",
        "| Métrica | Walk-forward (optimizado) | Parámetros base fijos | Buy & hold |",
        "|---|---|---|---|",
        row("Periodo", lambda m: f"{m.start:%Y-%m-%d} → {m.end:%Y-%m-%d}"),
        row("Capital final", lambda m: f"{m.final:,.2f} USDT"),
        row("CAGR", lambda m: pct(m.cagr)),
        row("Sharpe", lambda m: num(m.sharpe)),
        row("Drawdown máximo", lambda m: pct(m.max_drawdown)),
        row("Calmar", lambda m: num(calmar(m))),
        "",
        f"Operaciones del walk-forward: {trades}. La combinación elegida cambió en "
        f"{changes} de {len(windows) - 1} reentrenamientos.",
        "",
        "## Ventanas",
        "",
        "| Prueba | " + " | ".join(params) + " | Sharpe entreno | Retorno prueba |",
        "|---" * (len(params) + 3) + "|",
    ]
    for _, w in windows.iterrows():
        lines.append(
            f"| {w['test_start']:%Y-%m} → {w['test_end']:%Y-%m} | "
            + " | ".join(f"{w[p]:g}" for p in params)
            + f" | {num(w['train_sharpe'])} | {pct(w['test_return'])} |"
        )
    return "\n".join(lines)
