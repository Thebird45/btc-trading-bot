# Criterios de la prueba final (holdout)

Fijados el 19 de noviembre de 2026, **antes** de ejecutar la estrategia sobre el periodo reservado.

## Configuración congelada

- Estrategia `ema_trend`: EMA 20/50, régimen EMA 200, stop 2,5×ATR(14). Son los parámetros base, fijados antes de cualquier resultado; el walk-forward mostró que optimizarlos no mejora.
- Riesgo por operación: 1 % del capital. Sin apalancamiento.
- Costes por lado: comisión 0,10 %, deslizamiento 0,05 %.
- Periodo reservado: desde el 1 de enero de 2025 hasta la última vela descargada.

## Para aprobar, la estrategia debe cumplir todo esto en el holdout

1. **Expectativa neta positiva**: profit factor > 1 después de costes.
2. **Mejor riesgo/retorno que buy & hold**: Sharpe mayor que el de buy & hold en el mismo periodo.
3. **Riesgo controlado**: drawdown máximo de −25 % o menos (dentro de muestra fue −17,3 %).
4. **Sin errores de ejecución** en el backtest (operaciones coherentes con las señales).

## Si no aprueba

Se vuelve a investigación. **No** se ajustan los parámetros mirando el holdout ni se sube el riesgo para compensar. Este periodo deja de ser una prueba limpia después de mirarlo.

## Limitación conocida

Son unos 23 meses: se esperan alrededor de 30 operaciones, una muestra chica. Aprobar significa "no hay evidencia en contra", no "está demostrado". Por eso después viene el paper trading.

---

# Resultado (ejecutado una sola vez, 20 de noviembre de 2026)

Periodo: 2025-01-01 → 2026-11-20. Informe completo en [`reports/backtest_ema_trend_holdout.md`](../reports/backtest_ema_trend_holdout.md).

| Criterio | Resultado | ¿Cumple? |
|---|---|---|
| 1. Profit factor > 1 | 1,18 | ✅ |
| 2. Sharpe > buy & hold | 0,28 vs −0,30 | ✅ |
| 3. Drawdown ≤ 25 % | −11,4 % (buy & hold: −53,5 %) | ✅ |
| 4. Sin errores de ejecución | 35 operaciones sin solapes, stops bajo la entrada, fechas coherentes | ✅ |

**Veredicto: aprueba, pero por poco.** Lectura honesta:

- **Su valor en este periodo fue proteger el capital, no ganar.** BTC cayó un 34 % y la estrategia terminó en +4,4 %, con una caída máxima de −11 % frente a −53 %.
- **La ganancia es débil.** Un CAGR de 2,3 % es menos de lo que rinde un CDT o USDT en un producto de ahorro. La expectativa por operación (+0,30 %) no se distingue estadísticamente de cero (t = 0,28 con 35 operaciones).
- **El patrón se mantuvo**: un 28,6 % de acierto, igual que dentro de muestra (28,3 %). Pero la ganancia media cayó de +23 % a +6,8 %, porque en un mercado bajista y lateral las tendencias son cortas.
- Este periodo ya está usado. Desde ahora, la única evidencia nueva es el paper trading con datos en vivo.
