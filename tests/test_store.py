import pandas as pd
from conftest import make_candles

from btcbot.data.store import candles_path, load_candles, save_candles, update_candles


def test_save_load_roundtrip(tmp_path, candles):
    path = tmp_path / "x.csv"
    save_candles(candles, path)
    loaded = load_candles(path)
    pd.testing.assert_frame_equal(loaded, candles, check_freq=False)


def test_load_missing_file_is_empty(tmp_path):
    assert load_candles(tmp_path / "nope.csv").empty


def test_update_is_incremental(tmp_path):
    full = make_candles("2024-01-01", 30)
    starts = []

    def fetch(symbol, timeframe, start):
        starts.append(start)
        return full[full.index >= start]

    # Primera descarga: hasta la vela 20
    first = full.iloc[:20]
    save_candles(first, candles_path("BTCUSDT", "4h", tmp_path))

    df, added = update_candles("BTCUSDT", "4h", "2024-01-01", fetch, data_dir=tmp_path)
    assert added == 10
    assert len(df) == 30
    assert starts[0] == full.index[20]  # pidió desde la siguiente vela, no desde el inicio

    df, added = update_candles("BTCUSDT", "4h", "2024-01-01", fetch, data_dir=tmp_path)
    assert added == 0


def test_update_from_scratch_uses_history_start(tmp_path):
    starts = []

    def fetch(symbol, timeframe, start):
        starts.append(start)
        return make_candles("2024-01-01", 5)

    df, added = update_candles("BTCUSDT", "4h", "2024-01-01", fetch, data_dir=tmp_path)
    assert starts[0] == pd.Timestamp("2024-01-01", tz="UTC")
    assert added == 5
