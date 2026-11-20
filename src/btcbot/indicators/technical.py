"""Indicadores técnicos implementados con pandas/numpy.

Todos usan solo datos hasta la vela actual (sin mirar el futuro) y devuelven
NaN durante el periodo de calentamiento, en lugar de valores poco fiables.
RSI y ATR usan el suavizado de Wilder, como en su definición original.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Media móvil de Wilder: arranca con la media simple de los primeros `period`
    valores y luego avg = (avg_anterior * (period - 1) + valor) / period."""
    values = series.to_numpy(dtype=float)
    out = np.full(values.shape, np.nan)
    valid = np.flatnonzero(~np.isnan(values))
    if valid.size < period:
        return pd.Series(out, index=series.index)
    start = valid[0]
    seed_end = start + period
    if np.isnan(values[start:seed_end]).any():
        raise ValueError("wilder_smooth requiere valores contiguos sin NaN")
    out[seed_end - 1] = values[start:seed_end].mean()
    for i in range(seed_end, values.size):
        out[i] = (out[i - 1] * (period - 1) + values[i]) / period
    return pd.Series(out, index=series.index)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    avg_gain = wilder_smooth(delta.clip(lower=0), period)
    avg_loss = wilder_smooth(-delta.clip(upper=0), period)
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # Sin pérdidas en la ventana: RSI = 100
    out[(avg_loss == 0) & avg_gain.notna()] = 100.0
    return out.rename("rsi")


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def true_range(candles: pd.DataFrame) -> pd.Series:
    prev_close = candles["close"].shift(1)
    ranges = pd.concat(
        [
            candles["high"] - candles["low"],
            (candles["high"] - prev_close).abs(),
            (candles["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1, skipna=True).rename("tr")


def atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    return wilder_smooth(true_range(candles), period).rename("atr")
