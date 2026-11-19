"""Punto de entrada de línea de comandos: `uv run btcbot <comando>`."""

from __future__ import annotations

import argparse

from btcbot.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btcbot", description="Bot de trading BTC/USDT")
    parser.add_argument("--config", default=None, help="Ruta a un archivo .toml de configuración")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", help="Muestra la configuración activa")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config) if args.config else load_config()

    if args.command == "config":
        print(cfg)


if __name__ == "__main__":
    main()
