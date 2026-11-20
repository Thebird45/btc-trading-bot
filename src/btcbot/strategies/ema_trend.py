"""Estrategia base de seguimiento de tendencia con EMAs.

- Entrada: la EMA rápida pasa por encima de la lenta mientras el precio está
  sobre la EMA de régimen (tendencia de fondo alcista). Solo se entra cuando la
  condición se activa, no en cada vela en que sigue activa.
- Salida: la EMA rápida cae por debajo de la lenta, o salta el stop.
- Stop: `stop_atr` veces el ATR al momento de la señal, por debajo de la entrada.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from btcbot.indicators.technical import atr, ema


@dataclass(frozen=True)
class EmaTrendParams:
    fast: int = 20
    slow: int = 50
    regime: int = 200
    atr_period: int = 14
    stop_atr: float = 2.5

    def __post_init__(self) -> None:
        if not 0 < self.fast < self.slow:
            raise ValueError("Se requiere 0 < fast < slow")
        if self.stop_atr <= 0:
            raise ValueError("stop_atr debe ser positivo")


def ema_trend_signals(candles: pd.DataFrame, params: EmaTrendParams) -> pd.DataFrame:
    close = candles["close"]
    fast = ema(close, params.fast)
    slow = ema(close, params.slow)
    regime = ema(close, params.regime)
    stop_distance = params.stop_atr * atr(candles, params.atr_period)

    ready = fast.notna() & slow.notna() & regime.notna() & stop_distance.notna()
    condition = ready & (fast > slow) & (close > regime)
    entry = condition & ~condition.shift(1, fill_value=False)
    exit_ = ready & (fast < slow)
    return pd.DataFrame(
        {"entry": entry, "exit": exit_, "stop_distance": stop_distance},
        index=candles.index,
    )


def ema_trend_snapshot(candles: pd.DataFrame, params: EmaTrendParams) -> dict:
    """Valores de la última vela cerrada, para explicar qué está viendo el bot."""
    close = candles["close"]
    fast = ema(close, params.fast).iloc[-1]
    slow = ema(close, params.slow).iloc[-1]
    regime = ema(close, params.regime).iloc[-1]
    atr_now = atr(candles, params.atr_period).iloc[-1]
    price = float(close.iloc[-1])
    return {
        "close": price,
        "ema_fast": float(fast),
        "ema_slow": float(slow),
        "ema_regime": float(regime),
        "atr": float(atr_now),
        "stop_distance": float(params.stop_atr * atr_now),
        "trend_up": bool(fast > slow),
        "regime_up": bool(price > regime),
        "summary": (
            ("Tendencia corta alcista" if fast > slow else "Tendencia corta bajista")
            + " · "
            + ("precio sobre la EMA de régimen" if price > regime
               else "precio bajo la EMA de régimen")
        ),
    }
