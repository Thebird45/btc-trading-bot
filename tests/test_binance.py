import httpx
import pandas as pd
import pytest

from btcbot.exchange import binance
from btcbot.exchange.binance import fetch_klines, parse_klines

H4 = 4 * 3_600_000
T0 = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp() * 1000)


def raw_row(open_ms: int, price: float = 100.0) -> list:
    return [
        open_ms, str(price), str(price + 1), str(price - 1), str(price), "1.5",
        open_ms + H4 - 1, "150.0", 10, "0.7", "70.0", "0",
    ]


def fake_exchange(total: int):
    """Simula /api/v3/klines con `total` velas desde T0, respetando startTime/endTime/limit."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.params
        start, end, limit = int(p["startTime"]), int(p["endTime"]), int(p["limit"])
        calls.append(start)
        rows = [
            raw_row(T0 + i * H4)
            for i in range(total)
            if start <= T0 + i * H4 <= end
        ][:limit]
        return httpx.Response(200, json=rows)

    client = httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler))
    return client, calls


def test_parse_klines_types():
    df = parse_klines([raw_row(T0), raw_row(T0 + H4)])
    assert list(df.columns) == binance.CANDLE_COLUMNS
    assert df.index.tz is not None
    assert df.index[0] == pd.Timestamp("2024-01-01", tz="UTC")
    assert df["close"].dtype == float
    assert df["trades"].dtype == "int64"


def test_parse_empty():
    assert parse_klines([]).empty


def test_fetch_paginates(monkeypatch):
    monkeypatch.setattr(binance, "MAX_LIMIT", 10)
    client, calls = fake_exchange(total=25)
    now = lambda: pd.Timestamp(T0 + 100 * H4, unit="ms", tz="UTC")  # noqa: E731
    df = fetch_klines("BTCUSDT", "4h", pd.Timestamp(T0, unit="ms", tz="UTC"),
                      client=client, now=now, pause=0)
    assert len(df) == 25
    assert len(calls) == 3
    assert df.index.is_monotonic_increasing and not df.index.duplicated().any()


def test_fetch_drops_unclosed_candle():
    client, _ = fake_exchange(total=5)
    # "Ahora" está a mitad de la 5.ª vela: esa todavía no cerró
    now = lambda: pd.Timestamp(T0 + 4 * H4 + H4 // 2, unit="ms", tz="UTC")  # noqa: E731
    df = fetch_klines("BTCUSDT", "4h", pd.Timestamp(T0, unit="ms", tz="UTC"),
                      client=client, now=now, pause=0)
    assert len(df) == 4


def test_retries_on_rate_limit(monkeypatch):
    monkeypatch.setattr(binance.time, "sleep", lambda s: None)
    responses = [httpx.Response(429, headers={"Retry-After": "0"}),
                 httpx.Response(200, json=[raw_row(T0)])]
    client = httpx.Client(base_url="https://test",
                          transport=httpx.MockTransport(lambda r: responses.pop(0)))
    now = lambda: pd.Timestamp(T0 + 10 * H4, unit="ms", tz="UTC")  # noqa: E731
    df = fetch_klines("BTCUSDT", "4h", pd.Timestamp(T0, unit="ms", tz="UTC"),
                      client=client, now=now, pause=0)
    assert len(df) == 1


def test_client_error_raises():
    client = httpx.Client(base_url="https://test",
                          transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_klines("BTCUSDT", "4h", pd.Timestamp(T0, unit="ms", tz="UTC"),
                     client=client, now=lambda: pd.Timestamp("2025-01-01", tz="UTC"), pause=0)
