# Robustez de parámetros `ema_trend` — BTCUSDT 4h

Periodo: 2017-08-17 → 2025-01-01 (dentro de muestra, sin holdout). 300 combinaciones de parámetros.

## Resumen

| Pregunta | Resultado |
|---|---|
| Combinaciones con Sharpe mayor que buy & hold (0.94) | 300 de 300 (100%) |
| Combinaciones con profit factor > 1 | 300 de 300 (100%) |
| Combinaciones con CAGR > 0 | 300 de 300 (100%) |
| Sharpe: mínimo / p10 / mediana / p90 / máximo | 1.29 / 1.41 / 1.49 / 1.58 / 1.68 |
| Parámetros base: Sharpe y percentil | 1.46 (mejor que el 34% de la rejilla) |

## Sharpe mediano por EMA rápida × lenta

(mediana sobre todos los valores de régimen y stop)

| rápida \ lenta | 40 | 50 | 60 | 80 |
|---|---|---|---|---|
| 10 | 1.57 | 1.56 | 1.48 | 1.54 |
| 15 | 1.55 | 1.52 | 1.48 | 1.49 |
| 20 | 1.41 | 1.47 | 1.47 | 1.50 |
| 25 | 1.45 | 1.45 | 1.49 | 1.49 |
| 30 | 1.51 | 1.49 | 1.51 | 1.38 |

## Por stop (× ATR) (medianas)

| stop (× ATR) | Sharpe | Drawdown | Profit factor | Operaciones |
|---|---|---|---|---|
| 1.5 | 1.51 | -12.87 % | 2.73 | 140 |
| 2.0 | 1.54 | -10.35 % | 2.68 | 122 |
| 2.5 | 1.50 | -9.13 % | 2.49 | 118 |
| 3.0 | 1.47 | -8.03 % | 2.47 | 114 |
| 3.5 | 1.45 | -6.81 % | 2.59 | 112 |

## Por EMA de régimen (medianas)

| EMA de régimen | Sharpe | Drawdown | Profit factor | Operaciones |
|---|---|---|---|---|
| 150 | 1.47 | -9.88 % | 2.48 | 129 |
| 200 | 1.49 | -9.34 % | 2.60 | 118 |
| 250 | 1.51 | -8.19 % | 2.81 | 114 |

## Mejores 5 combinaciones por Sharpe

| fast | slow | regime | stop_atr | Sharpe | CAGR | Drawdown | PF | Operaciones |
|---|---|---|---|---|---|---|---|---|
| 15 | 40 | 150 | 1.5 | 1.68 | 19.49 % | -13.91 % | 2.56 | 178 |
| 10 | 40 | 150 | 1.5 | 1.66 | 18.51 % | -14.65 % | 2.47 | 193 |
| 15 | 40 | 200 | 1.5 | 1.66 | 19.02 % | -14.38 % | 2.50 | 170 |
| 10 | 40 | 200 | 1.5 | 1.65 | 18.17 % | -14.05 % | 2.44 | 180 |
| 10 | 50 | 150 | 1.5 | 1.64 | 18.86 % | -14.86 % | 2.55 | 178 |

## Peores 5 combinaciones por Sharpe

| fast | slow | regime | stop_atr | Sharpe | CAGR | Drawdown | PF | Operaciones |
|---|---|---|---|---|---|---|---|---|
| 30 | 80 | 150 | 2.5 | 1.29 | 10.09 % | -10.45 % | 2.41 | 96 |
| 30 | 80 | 150 | 1.5 | 1.30 | 15.61 % | -16.23 % | 2.71 | 119 |
| 30 | 80 | 150 | 3.5 | 1.32 | 7.57 % | -7.52 % | 2.65 | 86 |
| 30 | 80 | 150 | 2 | 1.33 | 12.64 % | -12.14 % | 2.60 | 103 |
| 30 | 80 | 150 | 3 | 1.34 | 8.95 % | -8.74 % | 2.64 | 89 |
