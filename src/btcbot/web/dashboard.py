"""Arma los datos del panel de seguimiento a partir de la base del paper trading."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from btcbot.backtest.metrics import max_drawdown, trade_metrics
from btcbot.config import Config
from btcbot.live.store import PaperStore
from btcbot.timeframes import timeframe_delta

MAX_POINTS = 1500  # puntos máximos de la gráfica


def clean(x):
    """NaN/inf → None, para que el JSON sea válido."""
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def iso(ts) -> str | None:
    return pd.Timestamp(ts).isoformat() if ts is not None and not pd.isna(ts) else None


def build_dashboard(cfg: Config, db_path: Path, now: pd.Timestamp | None = None) -> dict:
    now = now or pd.Timestamp.now(tz="UTC")
    base = {
        "now": now.isoformat(),
        "tz": cfg.paper.display_tz,
        "symbol": cfg.market.symbol,
        "timeframe": cfg.market.timeframe,
        "risk_per_trade": cfg.risk.risk_per_trade,
        "ready": False,
    }
    if not db_path.exists():
        return base
    store = PaperStore(db_path)
    try:
        state = store.load_state()
        eq = store.equity()
        if state is None or eq.empty:
            return base

        step = timeframe_delta(cfg.market.timeframe)
        initial = store.get("initial_capital", cfg.paper.initial_capital)
        last_tick = store.get("last_tick")
        last_candle = store.last_candle()
        alive_window = pd.Timedelta(seconds=3 * cfg.paper.poll_seconds + 120)
        snapshot = store.get("snapshot", {}) or {}

        curve, closes = eq["equity"], eq["close"]
        bh = initial * closes / closes.iloc[0]
        last_price = snapshot.get("close") or float(closes.iloc[-1])
        equity_now = float(curve.iloc[-1])

        position = None
        if state.in_position:
            value = state.units * last_price
            position = {
                "units": state.units,
                "entry_price": state.entry_price,
                "entry_time": iso(state.entry_time),
                "stop": state.stop,
                "last_price": last_price,
                "value": value,
                "unrealized_pnl": value * (1 - cfg.costs.fee_rate) - state.cost_basis,
                "unrealized_pct": value / state.cost_basis - 1,
                "stop_distance_pct": state.stop / last_price - 1,
            }

        trades = store.trades()
        tm = trade_metrics(trades["net_return"].tolist())
        events = store.events(60)

        step_n = max(1, math.ceil(len(eq) / MAX_POINTS))
        idx = list(range(0, len(eq), step_n))
        if idx[-1] != len(eq) - 1:
            idx.append(len(eq) - 1)

        return {
            **base,
            "ready": True,
            "status": {
                "started_at": store.get("started_at"),
                "paused": store.paused,
                "stale": bool(store.get("stale", False)),
                "last_tick": last_tick,
                "alive": bool(last_tick) and now - pd.Timestamp(last_tick) < alive_window,
                "last_candle_close": iso(last_candle + step) if last_candle is not None else None,
                "next_close": iso(last_candle + 2 * step) if last_candle is not None else None,
                "pending_entry": state.pending_entry,
                "pending_exit": state.pending_exit,
            },
            "account": {
                "initial": initial,
                "equity": equity_now,
                "cash": state.cash,
                "return": equity_now / initial - 1,
                "bh_return": float(bh.iloc[-1] / initial - 1),
                "max_drawdown": max_drawdown(curve),
                "bh_max_drawdown": max_drawdown(closes),
                "exposure": state.bars_in_position / state.candles_seen if state.candles_seen
                else 0.0,
                "position": position,
            },
            "metrics": {k: clean(v) for k, v in tm.__dict__.items()},
            "snapshot": {k: clean(v) for k, v in snapshot.items()},
            "strategy": store.get("strategy"),
            "equity": [
                {"t": iso(eq.index[i]), "equity": float(curve.iloc[i]), "bh": float(bh.iloc[i]),
                 "close": float(closes.iloc[i])}
                for i in idx
            ],
            "trades": [
                {"entry_time": iso(t.entry_time), "exit_time": iso(t.exit_time),
                 "entry_price": t.entry_price, "exit_price": t.exit_price,
                 "pnl": t.pnl, "net_return": t.net_return, "exit_reason": t.exit_reason,
                 "bars": int(t.bars)}
                for t in trades.tail(50).iloc[::-1].itertuples()
            ],
            "events": [
                {"ts": iso(e.ts), "level": e.level, "kind": e.kind, "message": e.message}
                for e in events.itertuples()
            ],
        }
    finally:
        store.close()
