"""Carga de configuración desde config/*.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "default.toml"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"


@dataclass(frozen=True)
class MarketConfig:
    exchange: str
    symbol: str
    timeframe: str
    history_start: str


@dataclass(frozen=True)
class CostsConfig:
    fee_rate: float
    slippage_rate: float


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float


@dataclass(frozen=True)
class Config:
    market: MarketConfig
    costs: CostsConfig
    backtest: BacktestConfig


def load_config(path: Path | str = DEFAULT_CONFIG) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return Config(
        market=MarketConfig(**raw["market"]),
        costs=CostsConfig(**raw["costs"]),
        backtest=BacktestConfig(**raw["backtest"]),
    )
