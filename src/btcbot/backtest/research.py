"""Robustez de parámetros y validación walk-forward.

Ambas funciones trabajan solo con el periodo que se les pasa: el CLI les entrega
datos anteriores al holdout, que nunca se usa para elegir parámetros.

- Robustez: corre una rejilla de parámetros en el mismo periodo. Si solo una
  pequeña isla de combinaciones funciona, el resultado probablemente es suerte.
- Walk-forward: en cada ventana de entrenamiento elige la mejor combinación
  (por Sharpe) y la aplica en la ventana de prueba siguiente, que el selector no
  vio. Las ventanas de prueba encadenadas forman una curva fuera de muestra.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import pandas as pd

from btcbot.backtest.baseline import buy_and_hold
from btcbot.backtest.engine import run_backtest
from btcbot.backtest.metrics import equity_metrics, trade_metrics
from btcbot.strategies import STRATEGIES


@dataclass(frozen=True)
class RunSettings:
    timeframe: str
    periods_per_year: float
    initial_capital: float
    fee_rate: float
    slippage_rate: float
    risk_per_trade: float
    max_position_fraction: float


def param_grid(grid: dict[str, list]) -> list[dict]:
    """{'a': [1, 2], 'b': [3]} -> [{'a': 1, 'b': 3}, {'a': 2, 'b': 3}], descartando inválidas."""
    keys = list(grid)
    return [dict(zip(keys, values, strict=True)) for values in itertools.product(*grid.values())]


def valid_params(strategy: str, combos: list[dict]) -> list[tuple[dict, object]]:
    cls = STRATEGIES[strategy].params_cls
    out = []
    for combo in combos:
        try:
            out.append((combo, cls(**combo)))
        except ValueError:
            continue
    return out


def _run(candles: pd.DataFrame, signals: pd.DataFrame, s: RunSettings):
    return run_backtest(
        candles, signals, timeframe=s.timeframe, initial_capital=s.initial_capital,
        fee_rate=s.fee_rate, slippage_rate=s.slippage_rate, risk_per_trade=s.risk_per_trade,
        max_position_fraction=s.max_position_fraction,
    )


def summarize(result, s: RunSettings) -> dict:
    em = equity_metrics(result.equity, s.periods_per_year)
    tm = trade_metrics([t.net_return for t in result.trades])
    return {
        "sharpe": em.sharpe,
        "cagr": em.cagr,
        "max_drawdown": em.max_drawdown,
        "trades": tm.trades,
        "win_rate": tm.win_rate,
        "profit_factor": tm.profit_factor,
        "exposure": result.exposure,
    }


def robustness(
    candles: pd.DataFrame, mask, strategy: str, grid: dict[str, list], s: RunSettings
) -> pd.DataFrame:
    """Una fila por combinación válida, evaluada en `candles[mask]`.

    Las señales se calculan sobre todo `candles` (solo miran atrás) para que el
    periodo evaluado empiece con los indicadores ya calentados.
    """
    spec = STRATEGIES[strategy]
    rows = []
    for combo, params in valid_params(strategy, param_grid(grid)):
        signals = spec.signals(candles, params)
        result = _run(candles[mask], signals[mask], s)
        rows.append({**combo, **summarize(result, s)})
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class WalkForwardResult:
    windows: pd.DataFrame  # una fila por ventana de prueba
    equity: pd.Series  # curva fuera de muestra encadenada (parámetros elegidos)
    fixed_equity: pd.Series  # mismos tramos con los parámetros base fijos
    buy_hold_equity: pd.Series
    trades: int


def walk_forward(
    candles: pd.DataFrame,
    strategy: str,
    grid: dict[str, list],
    base_params: dict,
    s: RunSettings,
    *,
    first_test: pd.Timestamp,
    end: pd.Timestamp,
    train_months: int = 24,
    test_months: int = 6,
    min_train_trades: int = 10,
) -> WalkForwardResult:
    spec = STRATEGIES[strategy]
    combos = valid_params(strategy, param_grid(grid))
    all_signals = {tuple(c.items()): spec.signals(candles, p) for c, p in combos}

    starts = pd.date_range(first_test, end, freq=pd.DateOffset(months=test_months),
                           inclusive="left")
    if len(starts) == 0:
        raise ValueError("No hay ventanas de prueba entre first_test y end")

    pieces, rows = [], []
    for test_start in starts:
        test_end = min(test_start + pd.DateOffset(months=test_months), end)
        train_start = test_start - pd.DateOffset(months=train_months)
        train = (candles.index >= train_start) & (candles.index < test_start)
        test = (candles.index >= test_start) & (candles.index < test_end)
        if train.sum() < 2 or test.sum() < 2:
            continue

        best_key, best_sharpe = None, -math.inf
        for key, signals in all_signals.items():
            summ = summarize(_run(candles[train], signals[train], s), s)
            if summ["trades"] < min_train_trades or math.isnan(summ["sharpe"]):
                continue
            if summ["sharpe"] > best_sharpe:
                best_key, best_sharpe = key, summ["sharpe"]
        if best_key is None:
            raise ValueError(f"Ninguna combinación con {min_train_trades}+ operaciones "
                             f"en el entrenamiento que termina en {test_start:%Y-%m-%d}")

        pieces.append(all_signals[best_key][test])
        rows.append({
            "test_start": test_start, "test_end": test_end,
            **dict(best_key), "train_sharpe": best_sharpe,
        })

    windows = pd.DataFrame(rows)
    span = (candles.index >= windows["test_start"].iloc[0]) & (candles.index < end)
    oos_candles = candles[span]

    # Una sola corrida sobre todo el tramo fuera de muestra con las señales de
    # cada ventana pegadas: las posiciones cruzan de una ventana a otra sin
    # cierres artificiales.
    combined = pd.concat(pieces).reindex(oos_candles.index)
    combined["entry"] = combined["entry"].fillna(False).astype(bool)
    combined["exit"] = combined["exit"].fillna(False).astype(bool)
    result = _run(oos_candles, combined, s)

    base_signals = spec.signals(candles, spec.params_cls(**base_params))[span]
    fixed = _run(oos_candles, base_signals, s)
    bh = buy_and_hold(oos_candles, s.timeframe, s.initial_capital, s.fee_rate, s.slippage_rate)

    # Retorno de cada ventana de prueba dentro de la curva encadenada
    returns = []
    for _, w in windows.iterrows():
        seg = result.equity[(result.equity.index >= w["test_start"])
                            & (result.equity.index <= w["test_end"])]
        returns.append(seg.iloc[-1] / seg.iloc[0] - 1 if len(seg) > 1 else float("nan"))
    windows["test_return"] = returns

    return WalkForwardResult(windows, result.equity, fixed.equity, bh, len(result.trades))
