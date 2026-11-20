# Walk-forward `ema_trend` — BTCUSDT 4h

Entrena 24 meses, elige la combinación de mayor Sharpe (mínimo 10 operaciones) entre las de la rejilla y la aplica los 6 meses siguientes. Riesgo 0.50% por operación. Todo antes del holdout.

## Curva fuera de muestra encadenada

| Métrica | Walk-forward (optimizado) | Parámetros base fijos | Buy & hold |
|---|---|---|---|
| Periodo | 2019-07-01 → 2025-01-01 | 2019-07-01 → 2025-01-01 | 2019-07-01 → 2025-01-01 |
| Capital final | 2,083.40 USDT | 1,630.02 USDT | 8,595.42 USDT |
| CAGR | 14.25 % | 9.27 % | 47.76 % |
| Sharpe | 1.37 | 1.38 | 0.93 |
| Drawdown máximo | -10.99 % | -9.32 % | -77.04 % |
| Calmar | 1.30 | 0.99 | 0.62 |

Operaciones del walk-forward: 126. La combinación elegida cambió en 9 de 10 reentrenamientos.

## Ventanas

| Prueba | fast | slow | regime | stop_atr | Sharpe entreno | Retorno prueba |
|---|---|---|---|---|---|---|
| 2019-07 → 2020-01 | 15 | 40 | 200 | 1.5 | 2.06 | -2.56 % |
| 2020-01 → 2020-07 | 15 | 40 | 200 | 1.5 | 1.31 | 7.14 % |
| 2020-07 → 2021-01 | 10 | 50 | 200 | 1.5 | 1.48 | 38.45 % |
| 2021-01 → 2021-07 | 15 | 40 | 150 | 1.5 | 2.47 | 1.57 % |
| 2021-07 → 2022-01 | 10 | 40 | 150 | 1.5 | 1.86 | 3.54 % |
| 2022-01 → 2022-07 | 25 | 80 | 250 | 1.5 | 2.07 | -0.80 % |
| 2022-07 → 2023-01 | 30 | 60 | 250 | 1.5 | 1.93 | -4.81 % |
| 2023-01 → 2023-07 | 30 | 80 | 200 | 1.5 | 0.39 | 20.78 % |
| 2023-07 → 2024-01 | 30 | 40 | 250 | 1.5 | 1.45 | 5.22 % |
| 2024-01 → 2024-07 | 10 | 80 | 200 | 1.5 | 1.52 | 13.21 % |
| 2024-07 → 2025-01 | 15 | 40 | 250 | 1.5 | 1.96 | 0.89 % |
