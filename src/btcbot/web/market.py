"""Datos de mercado en vivo para la web (precio actual y velas recientes con promedios).

Se piden a la API pública de Binance desde el servidor (la web solo habla con su
propio origen) y se guardan en caché unos segundos para no abusar de la API.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import httpx
import pandas as pd

from btcbot.config import Config
from btcbot.exchange.binance import MARKET_DATA_URL, parse_klines
from btcbot.indicators.technical import ema

PRICE_TTL = 15  # segundos
CANDLES_TTL = 60
WARMUP = 300  # velas extra para que el promedio largo esté calculado
SHOW = 180  # velas que se muestran (30 días en 4h)


class MarketFeed:
    def __init__(self, cfg: Config, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.symbol = cfg.market.symbol
        self.timeframe = cfg.market.timeframe
        self.params = cfg.strategy.get("ema_trend", {})
        self.client = client or httpx.Client(base_url=MARKET_DATA_URL, timeout=10)
        self.clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, object]] = {}

    def _cached(self, key: str, ttl: float, fetch: Callable[[], object]):
        with self._lock:
            hit = self._cache.get(key)
            if hit and self.clock() - hit[0] < ttl:
                return hit[1]
        value = fetch()
        with self._lock:
            self._cache[key] = (self.clock(), value)
        return value

    def _ticker(self) -> dict:
        r = self.client.get("/api/v3/ticker/24hr", params={"symbol": self.symbol})
        r.raise_for_status()
        t = r.json()
        return {
            "price": float(t["lastPrice"]),
            "change_24h": float(t["priceChangePercent"]) / 100,
            "high_24h": float(t["highPrice"]),
            "low_24h": float(t["lowPrice"]),
        }

    def _candles(self) -> dict:
        r = self.client.get("/api/v3/klines", params={
            "symbol": self.symbol, "interval": self.timeframe, "limit": WARMUP + SHOW})
        r.raise_for_status()
        df = parse_klines(r.json())
        close = df["close"]
        lines = {
            "fast": ema(close, int(self.params.get("fast", 20))),
            "slow": ema(close, int(self.params.get("slow", 50))),
            "regime": ema(close, int(self.params.get("regime", 200))),
        }
        tail = df.iloc[-SHOW:]

        def series(s: pd.Series) -> list:
            return [None if pd.isna(v) else round(float(v), 2) for v in s.iloc[-SHOW:]]

        return {
            "t": [int(ts.timestamp() * 1000) for ts in tail.index],
            "close": [round(float(v), 2) for v in tail["close"]],
            "high": [round(float(v), 2) for v in tail["high"]],
            "low": [round(float(v), 2) for v in tail["low"]],
            **{k: series(v) for k, v in lines.items()},
            "periods": {k: int(self.params.get(k, d)) for k, d in
                        (("fast", 20), ("slow", 50), ("regime", 200))},
        }

    def snapshot(self) -> dict:
        try:
            ticker = self._cached("ticker", PRICE_TTL, self._ticker)
            candles = self._cached("candles", CANDLES_TTL, self._candles)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            return {"ok": False, "error": f"Sin conexión con Binance ({type(exc).__name__})"}
        return {"ok": True, "symbol": self.symbol, "timeframe": self.timeframe,
                **ticker, "candles": candles}
