"""Punto de entrada de línea de comandos: `uv run btcbot <comando>`."""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from btcbot.backtest.baseline import buy_and_hold
from btcbot.backtest.engine import run_backtest
from btcbot.backtest.metrics import equity_metrics, trade_metrics, yearly_breakdown
from btcbot.backtest.report import (
    comparison_table,
    metrics_table,
    trades_table,
    yearly_comparison_table,
    yearly_table,
)
from btcbot.backtest.research import RunSettings, robustness, walk_forward
from btcbot.backtest.research_report import robustness_report, walkforward_report
from btcbot.config import REPORTS_DIR, Config, load_config
from btcbot.data.store import candles_path, load_candles, update_candles
from btcbot.data.validate import validate_candles
from btcbot.exchange.binance import fetch_klines
from btcbot.strategies import STRATEGIES, build_signals
from btcbot.timeframes import periods_per_year


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btcbot", description="Bot de trading BTC/USDT")
    parser.add_argument("--config", default=None, help="Ruta a un archivo .toml de configuración")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", help="Muestra la configuración activa")
    sub.add_parser("download", help="Descarga o actualiza el histórico de velas")
    sub.add_parser("validate", help="Revisa la calidad del histórico guardado")
    base = sub.add_parser("baseline", help="Backtest de referencia buy & hold con costes")
    base.add_argument("--start", default=None, help="Fecha inicial, p. ej. 2020-01-01")
    base.add_argument("--end", default=None, help="Fecha final (exclusiva)")
    base.add_argument("--save", action="store_true", help="Guarda el informe en reports/")

    bt = sub.add_parser("backtest", help="Backtest de una estrategia contra buy & hold")
    bt.add_argument("--strategy", default="ema_trend", choices=sorted(STRATEGIES))
    bt.add_argument("--start", default=None, help="Fecha inicial (por defecto, todo el histórico)")
    bt.add_argument("--end", default=None, help="Fecha final exclusiva (como máximo, el holdout)")
    bt.add_argument("--holdout", action="store_true",
                    help="Evalúa en el periodo reservado. Solo para la prueba final.")
    bt.add_argument("--risk", type=float, default=None,
                    help="Riesgo por operación (fracción), p. ej. 0.01. Por defecto, config.")
    bt.add_argument("--save", action="store_true", help="Guarda informe y operaciones en reports/")

    for name, text in (("robustness", "Rejilla de parámetros dentro de muestra"),
                       ("walkforward", "Validación walk-forward dentro de muestra")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--strategy", default="ema_trend", choices=sorted(STRATEGIES))
        p.add_argument("--save", action="store_true", help="Guarda el informe en reports/")

    pp = sub.add_parser("paper", help="Paper trading en vivo (dinero simulado)")
    pp.add_argument("action", choices=["run", "once", "status", "pause", "resume"],
                    help="run: loop continuo · once: una revisión · status/pause/resume")
    return parser


def build_paper_trader(cfg: Config):
    from btcbot.live.notifier import LogNotifier, MultiNotifier
    from btcbot.live.paper import PaperTrader
    from btcbot.live.store import PaperStore

    m = cfg.market

    def source() -> pd.DataFrame:
        df, _ = update_candles(m.symbol, m.timeframe, m.history_start,
                               lambda sym, tf, start: fetch_klines(sym, tf, start))
        return df

    store = PaperStore(cfg.paper.db_file())
    return PaperTrader(cfg, store, MultiNotifier(LogNotifier()), source)


def cmd_paper(cfg: Config, action: str) -> int:
    import logging
    import signal
    import threading

    from btcbot.live.paper import run_forever

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    trader = build_paper_trader(cfg)
    if action == "status":
        print(trader.status_text())
    elif action == "pause":
        print(trader.pause("CLI"))
    elif action == "resume":
        print(trader.resume("CLI"))
    elif action == "once":
        result = trader.tick()
        print(result.skipped or f"{result.processed} velas procesadas")
        print(trader.status_text())
    elif action == "run":
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        run_forever(trader, stop)
    return 0


def research_inputs(cfg: Config, strategy: str):
    """Velas anteriores al holdout, ajustes de corrida y rejilla. Nunca toca el holdout."""
    m, c = cfg.market, cfg.costs
    df = load_candles(candles_path(m.symbol, m.timeframe))
    if df.empty:
        raise SystemExit("No hay datos. Corre primero: uv run btcbot download")
    if strategy not in cfg.grid:
        raise SystemExit(f"Falta [grid.{strategy}] en la configuración")
    holdout = pd.Timestamp(cfg.validation.holdout_start, tz="UTC")
    settings = RunSettings(
        timeframe=m.timeframe, periods_per_year=periods_per_year(m.timeframe),
        initial_capital=cfg.backtest.initial_capital, fee_rate=c.fee_rate,
        slippage_rate=c.slippage_rate, risk_per_trade=cfg.risk.risk_per_trade,
        max_position_fraction=cfg.risk.max_position_fraction,
    )
    return df[df.index < holdout], holdout, settings, cfg.grid[strategy]


def save_report(text: str, name: str, save: bool) -> None:
    print(text)
    if save:
        out = REPORTS_DIR / name
        out.write_text(text + "\n", encoding="utf-8")
        print(f"\nInforme guardado en {out}")


def cmd_robustness(cfg: Config, args) -> int:
    df, holdout, s, grid = research_inputs(cfg, args.strategy)
    table = robustness(df, slice(None), args.strategy, grid, s)
    bh = buy_and_hold(df, s.timeframe, s.initial_capital, s.fee_rate, s.slippage_rate)
    bh_sharpe = equity_metrics(bh, s.periods_per_year).sharpe
    period = f"{df.index[0]:%Y-%m-%d} → {holdout:%Y-%m-%d}"
    text = robustness_report(
        table, cfg.strategy.get(args.strategy, {}), bh_sharpe, period,
        f"# Robustez de parámetros `{args.strategy}` — {cfg.market.symbol} {s.timeframe}",
    )
    save_report(text, f"robustness_{args.strategy}.md", args.save)
    return 0


def cmd_walkforward(cfg: Config, args) -> int:
    df, holdout, s, grid = research_inputs(cfg, args.strategy)
    w = cfg.walkforward
    result = walk_forward(
        df, args.strategy, grid, cfg.strategy.get(args.strategy, {}), s,
        first_test=pd.Timestamp(w["first_test"], tz="UTC"), end=holdout,
        train_months=w["train_months"], test_months=w["test_months"],
        min_train_trades=w["min_train_trades"],
    )
    ppy = s.periods_per_year
    settings = (
        f"Entrena {w['train_months']} meses, elige la combinación de mayor Sharpe "
        f"(mínimo {w['min_train_trades']} operaciones) entre las de la rejilla y la aplica "
        f"los {w['test_months']} meses siguientes. Riesgo {s.risk_per_trade:.2%} por operación. "
        "Todo antes del holdout."
    )
    text = walkforward_report(
        result.windows, equity_metrics(result.equity, ppy),
        equity_metrics(result.fixed_equity, ppy), equity_metrics(result.buy_hold_equity, ppy),
        result.trades,
        f"# Walk-forward `{args.strategy}` — {cfg.market.symbol} {s.timeframe}", settings,
    )
    save_report(text, f"walkforward_{args.strategy}.md", args.save)
    return 0


def select_period(df, cfg: Config, start, end, holdout: bool):
    """Recorta el periodo respetando el holdout. Devuelve (máscara, error)."""
    holdout_ts = pd.Timestamp(cfg.validation.holdout_start, tz="UTC")
    lo = pd.Timestamp(start, tz="UTC") if start else df.index[0]
    hi = pd.Timestamp(end, tz="UTC") if end else None
    if holdout:
        lo = max(lo, holdout_ts)
    else:
        if lo >= holdout_ts:
            return None, "Ese periodo está en el holdout. Usa --holdout solo para la prueba final."
        hi = min(hi, holdout_ts) if hi is not None else holdout_ts
    mask = df.index >= lo
    if hi is not None:
        mask &= df.index < hi
    return mask, None


def cmd_backtest(cfg: Config, args) -> int:
    m, c = cfg.market, cfg.costs
    df = load_candles(candles_path(m.symbol, m.timeframe))
    if df.empty:
        print("No hay datos. Corre primero: uv run btcbot download")
        return 1

    # Señales sobre todo el histórico (los indicadores solo miran atrás), luego se recorta:
    # así el periodo evaluado arranca con los indicadores ya calentados.
    signals, params = build_signals(args.strategy, df, cfg.strategy.get(args.strategy, {}))
    mask, error = select_period(df, cfg, args.start, args.end, args.holdout)
    if error:
        print(error)
        return 1
    candles, signals = df[mask], signals[mask]
    if len(candles) < 2:
        print("El periodo elegido tiene menos de 2 velas")
        return 1

    risk = args.risk if args.risk is not None else cfg.risk.risk_per_trade
    result = run_backtest(
        candles, signals, timeframe=m.timeframe, initial_capital=cfg.backtest.initial_capital,
        fee_rate=c.fee_rate, slippage_rate=c.slippage_rate, risk_per_trade=risk,
        max_position_fraction=cfg.risk.max_position_fraction,
    )
    bh = buy_and_hold(candles, m.timeframe, cfg.backtest.initial_capital, c.fee_rate,
                      c.slippage_rate)
    ppy = periods_per_year(m.timeframe)
    sm, bm = equity_metrics(result.equity, ppy), equity_metrics(bh, ppy)
    tm = trade_metrics([t.net_return for t in result.trades])
    stops = sum(t.exit_reason == "stop" for t in result.trades)
    label = "HOLDOUT (fuera de muestra)" if args.holdout else "dentro de muestra"

    text = "\n".join([
        f"# Backtest `{args.strategy}` — {m.symbol} {m.timeframe} — {label}",
        "",
        f"Periodo: {sm.start:%Y-%m-%d} → {sm.end:%Y-%m-%d}. Parámetros: `{params}`. "
        f"Riesgo por operación: {risk:.2%}. Costes por lado: comisión {c.fee_rate:.2%}, "
        f"deslizamiento {c.slippage_rate:.2%}. Señal al cierre, ejecución en la apertura "
        "siguiente.",
        "",
        "## Estrategia vs buy & hold",
        "",
        comparison_table(sm, bm, result.exposure),
        "",
        "## Operaciones",
        "",
        trades_table(tm, stops),
        "",
        "## Por año",
        "",
        yearly_comparison_table(yearly_breakdown(result.equity), yearly_breakdown(bh)),
        "",
        f"_Generado el {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC._",
        "",
    ])
    print(text)
    if args.save:
        suffix = "holdout" if args.holdout else "insample"
        out = REPORTS_DIR / f"backtest_{args.strategy}_{suffix}.md"
        out.write_text(text, encoding="utf-8")
        trades_csv = REPORTS_DIR / f"trades_{args.strategy}_{suffix}.csv"
        result.trades_frame().to_csv(trades_csv, index=False)
        print(f"Informe: {out}\nOperaciones: {trades_csv}")
    return 0


def cmd_baseline(cfg: Config, start: str | None, end: str | None, save: bool) -> int:
    m, c = cfg.market, cfg.costs
    df = load_candles(candles_path(m.symbol, m.timeframe))
    if df.empty:
        print("No hay datos. Corre primero: uv run btcbot download")
        return 1
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index < pd.Timestamp(end, tz="UTC")]
    if len(df) < 2:
        print("El periodo elegido tiene menos de 2 velas")
        return 1

    equity = buy_and_hold(df, m.timeframe, cfg.backtest.initial_capital, c.fee_rate,
                          c.slippage_rate)
    metrics = equity_metrics(equity, periods_per_year(m.timeframe))
    text = "\n".join([
        f"# Línea base: buy & hold {m.symbol} ({m.timeframe})",
        "",
        f"Comprar en la primera vela y vender en la última. Costes: comisión "
        f"{c.fee_rate:.2%} y deslizamiento {c.slippage_rate:.2%} por lado. "
        "Esta es la referencia que toda estrategia del bot debe superar.",
        "",
        metrics_table(metrics),
        "",
        "## Por año",
        "",
        yearly_table(yearly_breakdown(equity)),
        "",
        f"_Generado el {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC con "
        f"`uv run btcbot baseline`._",
        "",
    ])
    print(text)
    if save:
        out = REPORTS_DIR / "baseline_buy_hold.md"
        out.write_text(text, encoding="utf-8")
        print(f"Informe guardado en {out}")
    return 0


def cmd_download(cfg: Config) -> None:
    m = cfg.market

    def fetch(symbol, timeframe, start):
        print(f"Descargando {symbol} {timeframe} desde {start}...")
        return fetch_klines(
            symbol, timeframe, start,
            progress=lambda ts: print(f"  hasta {ts:%Y-%m-%d}", end="\r", flush=True),
        )

    df, added = update_candles(m.symbol, m.timeframe, m.history_start, fetch)
    print(f"\n{added} velas nuevas. Total: {len(df)} en {candles_path(m.symbol, m.timeframe)}")


def cmd_validate(cfg: Config) -> int:
    m = cfg.market
    path = candles_path(m.symbol, m.timeframe)
    df = load_candles(path)
    if df.empty:
        print(f"No hay datos en {path}. Corre primero: uv run btcbot download")
        return 1
    report = validate_candles(df, m.timeframe)
    print(report.summary())
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config) if args.config else load_config()

    if args.command == "config":
        print(cfg)
    elif args.command == "download":
        cmd_download(cfg)
    elif args.command == "validate":
        sys.exit(cmd_validate(cfg))
    elif args.command == "baseline":
        sys.exit(cmd_baseline(cfg, args.start, args.end, args.save))
    elif args.command == "backtest":
        sys.exit(cmd_backtest(cfg, args))
    elif args.command == "robustness":
        sys.exit(cmd_robustness(cfg, args))
    elif args.command == "walkforward":
        sys.exit(cmd_walkforward(cfg, args))
    elif args.command == "paper":
        sys.exit(cmd_paper(cfg, args.action))


if __name__ == "__main__":
    main()
