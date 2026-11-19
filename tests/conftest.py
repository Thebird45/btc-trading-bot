import numpy as np
import pandas as pd
import pytest

from btcbot.exchange.binance import CANDLE_COLUMNS


def make_candles(start: str, periods: int, freq: str = "4h", seed: int = 0) -> pd.DataFrame:
    """Velas sintéticas coherentes (high >= open/close >= low)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC", name="open_time")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, periods)))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * 1.005
    low = np.minimum(open_, close) * 0.995
    volume = rng.uniform(1, 10, periods)
    df = pd.DataFrame(
        {
            "open": open_, "high": high, "low": low, "close": close, "volume": volume,
            "quote_volume": volume * close, "trades": rng.integers(1, 100, periods),
            "taker_buy_base": volume / 2, "taker_buy_quote": volume * close / 2,
        },
        index=idx,
    )
    return df[CANDLE_COLUMNS]


@pytest.fixture
def candles() -> pd.DataFrame:
    return make_candles("2024-01-01", 50)
