"""Almacenamiento local de velas en CSV y actualización incremental."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from btcbot.config import DATA_DIR
from btcbot.exchange.binance import empty_candles
from btcbot.timeframes import timeframe_delta


def candles_path(symbol: str, timeframe: str, data_dir: Path = DATA_DIR) -> Path:
    return data_dir / f"{symbol}_{timeframe}.csv"


def save_candles(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.index = out.index.strftime("%Y-%m-%dT%H:%M:%SZ")
    out.to_csv(path, index_label="open_time")


def load_candles(path: Path) -> pd.DataFrame:
    if not path.exists():
        return empty_candles()
    df = pd.read_csv(path, index_col="open_time")
    df.index = pd.to_datetime(df.index, utc=True)
    df["trades"] = df["trades"].astype("int64")
    return df


Fetcher = Callable[[str, str, pd.Timestamp], pd.DataFrame]


def update_candles(
    symbol: str,
    timeframe: str,
    history_start: str,
    fetch: Fetcher,
    data_dir: Path = DATA_DIR,
) -> tuple[pd.DataFrame, int]:
    """Descarga solo lo que falta desde la última vela guardada.

    Devuelve (velas completas, cantidad de velas nuevas).
    """
    path = candles_path(symbol, timeframe, data_dir)
    existing = load_candles(path)
    if existing.empty:
        start = pd.Timestamp(history_start, tz="UTC")
    else:
        start = existing.index[-1] + timeframe_delta(timeframe)

    new = fetch(symbol, timeframe, start)
    if new.empty:
        return existing, 0

    combined = pd.concat([existing, new]) if not existing.empty else new
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    save_candles(combined, path)
    return combined, len(combined) - len(existing)
