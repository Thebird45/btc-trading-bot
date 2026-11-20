import dataclasses

import numpy as np
import pandas as pd
import pytest
from conftest import make_candles

from btcbot.backtest.broker import AccountState
from btcbot.backtest.engine import run_backtest
from btcbot.config import load_config
from btcbot.live.notifier import MemoryNotifier
from btcbot.live.paper import PaperTrader
from btcbot.live.store import PaperStore
from btcbot.strategies import build_signals

STEP = pd.Timedelta(hours=4)
PARAMS = {"fast": 10, "slow": 30, "regime": 100, "atr_period": 14, "stop_atr": 2.0}


def make_cfg(tmp_path, daily_loss_limit=1.0):
    cfg = load_config()
    paper = dataclasses.replace(cfg.paper, db_path=str(tmp_path / "paper.db"),
                                daily_loss_limit=daily_loss_limit)
    return dataclasses.replace(cfg, paper=paper, strategy={"ema_trend": PARAMS})


def make_trader(tmp_path, candles, **kw):
    cfg = make_cfg(tmp_path, **kw)
    store = PaperStore(cfg.paper.db_file())
    notifier = MemoryNotifier()
    return PaperTrader(cfg, store, notifier, lambda: candles), store, notifier


def after_close(candles, i, minutes=1):
    """Momento justo después de que cierra la vela i."""
    return candles.index[i] + STEP + pd.Timedelta(minutes=minutes)


@pytest.fixture(scope="module")
def candles():
    return make_candles("2023-01-01", 1500, seed=42)


def test_paper_matches_backtest(tmp_path, candles):
    """Vela a vela en vivo debe dar lo mismo que el backtest desde el mismo punto."""
    k = 300
    trader, store, _ = make_trader(tmp_path, candles)
    for i in range(k, len(candles)):
        trader.tick(after_close(candles, i))

    cfg = make_cfg(tmp_path)
    signals, _ = build_signals("ema_trend", candles, PARAMS)
    bt = run_backtest(candles.iloc[k:], signals.iloc[k:], timeframe="4h",
                      initial_capital=cfg.paper.initial_capital, fee_rate=cfg.costs.fee_rate,
                      slippage_rate=cfg.costs.slippage_rate,
                      risk_per_trade=cfg.risk.risk_per_trade,
                      max_position_fraction=cfg.risk.max_position_fraction)

    paper_trades = store.trades()
    bt_trades = [t for t in bt.trades if t.exit_reason != "end"]
    assert len(bt_trades) > 5
    assert len(paper_trades) == len(bt_trades)
    for row, t in zip(paper_trades.itertuples(), bt_trades, strict=True):
        assert row.entry_time == t.entry_time and row.exit_time == t.exit_time
        assert row.pnl == pytest.approx(t.pnl) and row.exit_reason == t.exit_reason
        assert row.bars == t.bars

    paper_eq = store.equity()["equity"]
    # El backtest liquida la posición en la última vela; se compara todo lo anterior
    np.testing.assert_allclose(paper_eq.iloc[:-1].to_numpy(), bt.equity.iloc[:-1].to_numpy())
    assert list(paper_eq.index[:-1]) == list(bt.equity.index[:-1])


def test_restart_continues_without_reprocessing(tmp_path, candles):
    trader, store, _ = make_trader(tmp_path, candles)
    for i in range(300, 400):
        trader.tick(after_close(candles, i))
    rows_before = len(store.equity())

    # "Reinicio": nueva instancia con la misma base de datos
    trader2 = PaperTrader(trader.cfg, PaperStore(store.path), MemoryNotifier(), lambda: candles)
    assert trader2.tick(after_close(candles, 399)).processed == 0
    assert trader2.tick(after_close(candles, 400)).processed == 1
    assert len(trader2.store.equity()) == rows_before + 1


def test_catches_up_after_downtime(tmp_path, candles):
    trader, store, _ = make_trader(tmp_path, candles)
    trader.tick(after_close(candles, 300))
    # Estuvo apagado 1 vela: al volver procesa las 2 pendientes
    assert trader.tick(after_close(candles, 302)).processed == 2


def test_no_work_before_next_close(tmp_path, candles):
    trader, _, _ = make_trader(tmp_path, candles)
    trader.tick(after_close(candles, 300))
    r = trader.tick(after_close(candles, 300, minutes=200))
    assert r.processed == 0 and r.skipped == "sin vela nueva"


def test_stale_data_blocks_and_notifies_once(tmp_path, candles):
    trader, store, notifier = make_trader(tmp_path, candles.iloc[:301])
    trader.tick(after_close(candles, 300))
    later = after_close(candles, 300) + 5 * STEP  # no llegaron velas nuevas
    assert trader.tick(later).skipped == "datos atrasados"
    assert trader.tick(later + STEP).skipped == "datos atrasados"
    assert sum("Datos atrasados" in m for m in notifier.messages) == 1


def test_pause_blocks_entries_but_not_exits(tmp_path, candles):
    trader, store, notifier = make_trader(tmp_path, candles)
    trader.pause("test")
    for i in range(300, len(candles)):
        trader.tick(after_close(candles, i))
    assert store.trades().empty
    assert store.load_state().units == 0
    assert any("Señal de compra ignorada" in m for m in notifier.messages)


def test_pause_keeps_stop_active(tmp_path, candles):
    trader, store, _ = make_trader(tmp_path, candles)
    i = 300
    while store.load_state() is None or not store.load_state().in_position:
        trader.tick(after_close(candles, i))
        i += 1
    trader.pause("test")
    while store.load_state().in_position:
        trader.tick(after_close(candles, i))
        i += 1
    assert len(store.trades()) == 1  # la posición abierta se cerró aun en pausa


def test_daily_loss_limit_blocks_entries(tmp_path):
    # Cae 10 % en una vela con posición abierta → límite diario del 0,1 % alcanzado
    c = make_candles("2023-01-01", 400, seed=3)
    trader, store, notifier = make_trader(tmp_path, c, daily_loss_limit=0.001)
    for i in range(150, 400):
        trader.tick(after_close(c, i))
    assert any("Límite de pérdida diaria" in m for m in notifier.messages)


def test_notifications_after_trades(tmp_path, candles):
    trader, store, notifier = make_trader(tmp_path, candles)
    for i in range(300, len(candles)):
        trader.tick(after_close(candles, i))
    text = "\n".join(notifier.messages)
    assert "Paper trading iniciado" in text
    assert "COMPRA" in text
    assert "Resumen del" in text


def test_status_text(tmp_path, candles):
    trader, _, _ = make_trader(tmp_path, candles)
    assert "todavía" in trader.status_text()
    trader.tick(after_close(candles, 300))
    assert "Capital" in trader.status_text()


def test_account_state_roundtrip():
    s = AccountState(cash=500, units=0.1, entry_price=100, stop=90,
                     entry_time=pd.Timestamp("2024-01-01", tz="UTC"), bars_held=3)
    assert AccountState.from_dict(s.to_dict()) == s
    empty = AccountState(cash=1000)
    restored = AccountState.from_dict(empty.to_dict())
    assert restored.entry_time is None and np.isnan(restored.pending_dist)


def test_store_transaction_rolls_back(tmp_path):
    store = PaperStore(tmp_path / "x.db")
    with pytest.raises(RuntimeError), store.transaction():
        store.set("a", 1)
        raise RuntimeError("fallo a mitad")
    assert store.get("a") is None


def test_performance_and_trades_text(tmp_path, candles):
    trader, store, _ = make_trader(tmp_path, candles)
    assert "Todavía" in trader.trades_text()
    for i in range(300, len(candles)):
        trader.tick(after_close(candles, i))
    perf = trader.performance_text()
    assert "Buy & hold" in perf and "Profit factor" in perf
    assert trader.trades_text().startswith("Últimas 5 operaciones")
