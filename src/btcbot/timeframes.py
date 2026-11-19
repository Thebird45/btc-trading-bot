"""Conversión de marcos temporales de Binance a milisegundos / pandas."""

from __future__ import annotations

import pandas as pd

_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}


def timeframe_ms(timeframe: str) -> int:
    """'4h' -> 14_400_000. Soporta m, h, d, w (no '1M' porque los meses no son fijos)."""
    try:
        amount, unit = int(timeframe[:-1]), timeframe[-1]
        return amount * _UNIT_MS[unit]
    except (ValueError, KeyError) as exc:
        raise ValueError(f"Marco temporal no soportado: {timeframe!r}") from exc


def timeframe_delta(timeframe: str) -> pd.Timedelta:
    return pd.Timedelta(milliseconds=timeframe_ms(timeframe))


def periods_per_year(timeframe: str) -> float:
    """Velas por año (cripto opera 24/7, 365 días)."""
    return 365 * 86_400_000 / timeframe_ms(timeframe)
