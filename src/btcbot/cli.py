"""Punto de entrada de línea de comandos: `uv run btcbot <comando>`."""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from btcbot.backtest.baseline import buy_and_hold
from btcbot.backtest.metrics import equity_metrics, yearly_breakdown
from btcbot.backtest.report import metrics_table, yearly_table
from btcbot.config import REPORTS_DIR, Config, load_config
from btcbot.data.store import candles_path, load_candles, update_candles
from btcbot.data.validate import validate_candles
from btcbot.exchange.binance import fetch_klines
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
    return parser


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


if __name__ == "__main__":
    main()
