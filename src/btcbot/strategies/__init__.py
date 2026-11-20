"""Registro de estrategias disponibles para el backtest."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from btcbot.strategies.ema_trend import EmaTrendParams, ema_trend_signals


@dataclass(frozen=True)
class StrategySpec:
    params_cls: type
    signals: Callable[[pd.DataFrame, object], pd.DataFrame]
    description: str


STRATEGIES: dict[str, StrategySpec] = {
    "ema_trend": StrategySpec(
        EmaTrendParams,
        ema_trend_signals,
        "Tendencia: cruce EMA rápida/lenta sobre EMA de régimen, stop por ATR",
    ),
}


def build_signals(name: str, candles: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, object]:
    if name not in STRATEGIES:
        raise ValueError(f"Estrategia desconocida: {name}. Disponibles: {list(STRATEGIES)}")
    spec = STRATEGIES[name]
    p = spec.params_cls(**params)
    return spec.signals(candles, p), p
