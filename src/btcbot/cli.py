"""Punto de entrada de línea de comandos: `uv run btcbot <comando>`."""

from __future__ import annotations

import argparse
import sys

from btcbot.config import Config, load_config
from btcbot.data.store import candles_path, load_candles, update_candles
from btcbot.data.validate import validate_candles
from btcbot.exchange.binance import fetch_klines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btcbot", description="Bot de trading BTC/USDT")
    parser.add_argument("--config", default=None, help="Ruta a un archivo .toml de configuración")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", help="Muestra la configuración activa")
    sub.add_parser("download", help="Descarga o actualiza el histórico de velas")
    sub.add_parser("validate", help="Revisa la calidad del histórico guardado")
    return parser


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


if __name__ == "__main__":
    main()
