from btcbot.config import load_config


def test_default_config_loads():
    cfg = load_config()
    assert cfg.market.symbol == "BTCUSDT"
    assert cfg.market.timeframe == "4h"
    assert 0 < cfg.costs.fee_rate < 0.01
    assert cfg.backtest.initial_capital > 0
