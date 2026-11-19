"""Estrategia de referencia pasiva: comprar al inicio y mantener (buy & hold).

Cualquier estrategia del bot debe superar esta referencia después de costes
para justificar su existencia.
"""

from __future__ import annotations

import pandas as pd

from btcbot.timeframes import timeframe_delta


def buy_and_hold(
    candles: pd.DataFrame,
    timeframe: str,
    initial_capital: float,
    fee_rate: float,
    slippage_rate: float,
) -> pd.Series:
    """Capital de comprar en la apertura de la primera vela y vender al cierre de la última.

    - Compra: precio de apertura + deslizamiento, pagando comisión.
    - Cada vela: el capital se valora al precio de cierre.
    - Última vela: se descuenta la venta (deslizamiento + comisión), para que el
      valor final sea lo que realmente quedaría en USDT.
    """
    if candles.empty:
        raise ValueError("No hay velas")
    entry_price = candles["open"].iloc[0] * (1 + slippage_rate)
    units = initial_capital * (1 - fee_rate) / entry_price

    equity = units * candles["close"]
    exit_value = units * candles["close"].iloc[-1] * (1 - slippage_rate) * (1 - fee_rate)
    equity.iloc[-1] = exit_value

    # Cada valor se fecha al cierre de su vela; el primer punto es el capital
    # antes de comprar, en la apertura de la primera vela.
    equity.index = equity.index + timeframe_delta(timeframe)
    start = pd.Series([initial_capital], index=[candles.index[0]])
    return pd.concat([start, equity]).rename("equity")
