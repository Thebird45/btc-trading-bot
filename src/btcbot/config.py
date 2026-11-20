"""Carga de configuración desde config/*.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
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
class ValidationConfig:
    holdout_start: str


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float
    max_position_fraction: float


@dataclass(frozen=True)
class PaperConfig:
    db_path: str
    initial_capital: float
    daily_loss_limit: float
    max_stale_candles: int
    poll_seconds: int
    display_tz: str

    def db_file(self) -> Path:
        path = Path(self.db_path)
        return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class Config:
    market: MarketConfig
    costs: CostsConfig
    backtest: BacktestConfig
    validation: ValidationConfig
    risk: RiskConfig
    strategy: dict[str, dict] = field(default_factory=dict)
    grid: dict[str, dict] = field(default_factory=dict)
    walkforward: dict = field(default_factory=dict)
    paper: PaperConfig | None = None


def load_config(path: Path | str = DEFAULT_CONFIG) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return Config(
        market=MarketConfig(**raw["market"]),
        costs=CostsConfig(**raw["costs"]),
        backtest=BacktestConfig(**raw["backtest"]),
        validation=ValidationConfig(**raw["validation"]),
        risk=RiskConfig(**raw["risk"]),
        strategy=raw.get("strategy", {}),
        grid=raw.get("grid", {}),
        walkforward=raw.get("walkforward", {}),
        paper=PaperConfig(**raw["paper"]) if "paper" in raw else None,
    )
