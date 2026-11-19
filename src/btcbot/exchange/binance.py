"""Descarga de velas (klines) desde la API pública de mercado de Binance.

No requiere claves: usa el endpoint de solo datos de mercado. Las velas se
devuelven con índice `open_time` en UTC y solo se incluyen velas ya cerradas.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
import pandas as pd

from btcbot.timeframes import timeframe_ms

MARKET_DATA_URL = "https://data-api.binance.vision"
MAX_LIMIT = 1000

CANDLE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
]


def parse_klines(rows: list[list]) -> pd.DataFrame:
    """Convierte la respuesta cruda de /api/v3/klines en un DataFrame tipado."""
    if not rows:
        return empty_candles()
    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
        ],
    )
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")[CANDLE_COLUMNS]
    df = df.astype(float)
    df["trades"] = df["trades"].astype("int64")
    return df


def empty_candles() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], tz="UTC", name="open_time")
    df = pd.DataFrame(columns=CANDLE_COLUMNS, index=idx, dtype=float)
    df["trades"] = df["trades"].astype("int64")
    return df


def _get_with_retry(client: httpx.Client, params: dict, retries: int = 5) -> list[list]:
    for attempt in range(retries):
        resp = client.get("/api/v3/klines", params=params)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (418, 429) or resp.status_code >= 500:
            wait = float(resp.headers.get("Retry-After", 2**attempt))
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Binance no respondió tras {retries} intentos: {params}")


def fetch_klines(
    symbol: str,
    timeframe: str,
    start: pd.Timestamp,
    end: pd.Timestamp | None = None,
    *,
    client: httpx.Client | None = None,
    now: Callable[[], pd.Timestamp] = lambda: pd.Timestamp.now(tz="UTC"),
    pause: float = 0.1,
    progress: Callable[[pd.Timestamp], None] | None = None,
) -> pd.DataFrame:
    """Descarga todas las velas cerradas en [start, end) paginando de a 1000."""
    step = timeframe_ms(timeframe)
    start_ms = int(pd.Timestamp(start).timestamp() * 1000)
    now_ms = int(now().timestamp() * 1000)
    end_ms = min(int(pd.Timestamp(end).timestamp() * 1000), now_ms) if end is not None else now_ms

    own_client = client is None
    client = client or httpx.Client(base_url=MARKET_DATA_URL, timeout=30)
    frames: list[pd.DataFrame] = []
    try:
        cursor = start_ms
        while cursor < end_ms:
            params = {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": MAX_LIMIT,
            }
            rows = _get_with_retry(client, params)
            if not rows:
                break
            frames.append(parse_klines(rows))
            last_open = rows[-1][0]
            cursor = last_open + step
            if progress:
                progress(pd.Timestamp(last_open, unit="ms", tz="UTC"))
            if len(rows) < MAX_LIMIT:
                break
            if pause:
                time.sleep(pause)
    finally:
        if own_client:
            client.close()

    if not frames:
        return empty_candles()
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    # Solo velas cerradas: su cierre debe ser anterior al momento actual
    closed = df.index + pd.Timedelta(milliseconds=step) <= pd.Timestamp(now_ms, unit="ms", tz="UTC")
    return df[closed]
