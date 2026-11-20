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
