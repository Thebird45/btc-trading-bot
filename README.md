# btc-trading-bot

Bot de trading para **BTC/USDT** en Binance Spot, escrito en Python. Va por fases: primero datos, backtesting y simulación. Solo pasará a operar con dinero real si supera los criterios de validación del [plan de desarrollo](docs/Plan_Desarrollo_Bot_Trading_Bitcoin.pdf).

> ⚠️ **Advertencia.** Este proyecto no es asesoría financiera ni promete rentabilidad. Ninguna estrategia elimina el riesgo de pérdida, y el rendimiento pasado no garantiza resultados futuros.

## Principios

- **Simulación primero.** No se conecta a una cuenta con fondos hasta pasar backtest fuera de muestra y paper trading.
- **Sin apalancamiento.** Solo Spot.
- **La métrica que importa es la expectativa neta después de costes**, no el porcentaje de aciertos. Toda estrategia debe ganarle a *buy & hold* en datos no usados para diseñarla.
- **Claves API sin permiso de retiro**, fuera del código y del repositorio.

## Estado actual

| Fase | Estado |
|---|---|
| 1. Alcance y entorno | ✅ Estructura, configuración, CI |
| 2. Datos e indicadores | ✅ Descarga, validación e indicadores (EMA, SMA, RSI, MACD, ATR) |
| 3. Estrategia base | ✅ `ema_trend`: tendencia con EMAs + stop por ATR |
| 4. Backtesting | ✅ Motor con stops y costes, robustez de parámetros y walk-forward; holdout pendiente |
| 5. Machine Learning | ⏳ Pendiente |
| 6. Paper trading | ⏳ Pendiente |
| 7. Revisión y piloto | ⏳ Pendiente |

## Instalación

Requiere [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Thebird45/btc-trading-bot.git
cd btc-trading-bot
uv sync
uv run btcbot config   # muestra la configuración activa
uv run pytest          # corre los tests
```

## Datos

```bash
uv run btcbot download   # descarga BTC/USDT 4h desde 2017 (la 1.ª vez ~15 s); luego solo lo nuevo
uv run btcbot validate   # revisa duplicados, huecos, OHLC incoherente y alineación
```

Las velas salen de la API pública de datos de mercado de Binance (no requiere claves) y se guardan en `data/BTCUSDT_4h.csv` con hora UTC. Solo se guardan velas cerradas.

El histórico tiene 8 huecos conocidos (16 velas de 4h), por mantenimientos de Binance en 2018–2020. Se reportan como aviso y **no se rellenan**: inventar velas falsearía el backtest.

## Línea base (buy & hold)

```bash
uv run btcbot baseline                      # todo el histórico
uv run btcbot baseline --start 2022-01-01   # un periodo concreto
uv run btcbot baseline --save               # guarda reports/baseline_buy_hold.md
```

Comprar BTC y no tocarlo, con comisiones y deslizamiento incluidos. **Es la vara contra la que se mide el bot**: si una estrategia no le gana en retorno ajustado por riesgo (Sharpe, drawdown) fuera de muestra, no tiene sentido usarla. Resultado actual en [`reports/baseline_buy_hold.md`](reports/baseline_buy_hold.md).

## Backtest de estrategias

```bash
uv run btcbot backtest                 # ema_trend, 2017 → 2024 (dentro de muestra)
uv run btcbot backtest --risk 0.01     # probar otro riesgo por operación
uv run btcbot backtest --save          # guarda informe .md y operaciones .csv en reports/
uv run btcbot backtest --holdout       # SOLO para la prueba final (ver abajo)
```

El motor calcula la señal al cierre de cada vela y la ejecuta en la **apertura siguiente**. Revisa el stop dentro de la vela; si hay un gap por debajo del stop, sale a la apertura. Cobra comisión y deslizamiento en cada lado y dimensiona la posición para arriesgar un % fijo del capital, sin apalancamiento.

**Periodo reservado (holdout): desde el 1 de enero de 2025.** No se usa para diseñar ni ajustar estrategias, solo para la evaluación final. Si se mira mientras se diseña, deja de ser una prueba honesta.

### Primer resultado: `ema_trend` 2017–2024 (dentro de muestra)

Parámetros estándar fijados antes de ver resultados (EMA 20/50, régimen EMA 200, stop 2,5×ATR), sin optimizar. Riesgo 0,5 % por operación. Informe completo en [`reports/backtest_ema_trend_insample.md`](reports/backtest_ema_trend_insample.md).

| | Estrategia | Buy & hold |
|---|---|---|
| CAGR | 10,4 % | 51,9 % |
| Sharpe | 1,46 | 0,94 |
| Drawdown máximo | −9,3 % | −83,9 % |
| Acierto | 28 % | — |
| Profit factor | 2,31 | — |

Gana menos en total, pero con mucho menos riesgo (mejor Sharpe y Calmar). Acierta solo el 28 % de las veces y aun así es rentable: las pérdidas son pequeñas (−4 %) y las ganancias grandes (+23 %). Con riesgo del 2 % por operación: CAGR 38,7 % y drawdown −30,5 %. Por sí solo esto no prueba nada; ver la validación de abajo.

## Validación: robustez y walk-forward

```bash
uv run btcbot robustness --save    # 300 combinaciones de parámetros, 2017–2024
uv run btcbot walkforward --save   # entrena 24 meses, prueba 6, avanza; 2019–2024
```

La rejilla y las ventanas están en `config/default.toml` y se fijaron antes de ver resultados. Ninguno de los dos comandos toca el holdout.

**Robustez** ([informe](reports/robustness_ema_trend.md)): las 300 combinaciones (EMA rápida 10–30, lenta 40–80, régimen 150–250, stop 1,5–3,5×ATR) tienen Sharpe entre 1,29 y 1,68, todas por encima de buy & hold (0,94) y todas con profit factor > 1. Es una meseta amplia, no una isla de suerte.

**Walk-forward** ([informe](reports/walkforward_ema_trend.md)), julio 2019 → diciembre 2024, siempre fuera de muestra:

| | Walk-forward | Parámetros base fijos | Buy & hold |
|---|---|---|---|
| CAGR | 14,3 % | 9,3 % | 47,8 % |
| Sharpe | 1,37 | 1,38 | 0,93 |
| Drawdown máximo | −11,0 % | −9,3 % | −77,0 % |

Optimizar no mejora el Sharpe frente a los parámetros fijos, y la combinación elegida cambia en casi cada reentrenamiento. Conclusión: **mantener parámetros fijos y simples**; reoptimizar solo agrega riesgo de sobreajuste. El optimizador siempre eligió el stop más ajustado de la rejilla (1,5×ATR): sube el CAGR porque, con el mismo riesgo, permite posiciones más grandes.

## Configuración

Los parámetros están en [`config/default.toml`](config/default.toml): par, marco temporal (4h), comisión (0,1 % por lado), deslizamiento (0,05 % por lado) y capital inicial simulado. Las claves API, cuando hagan falta, van en `.env` (ver `.env.example`).

## Estructura

```
config/          Configuración y parámetros
data/            Datos históricos descargados (no se suben al repo)
docs/            Plan de desarrollo
notebooks/       Investigación exploratoria
reports/         Informes de backtesting
src/btcbot/
  exchange/      Adaptador de datos / API de Binance
  data/          Almacenamiento y validación de datos
  indicators/    Indicadores y variables
  strategies/    Estrategias y reglas
  models/        Entrenamiento e inferencia ML
  risk/          Gestión de riesgo
  backtest/      Motor de backtesting y métricas
  execution/     Simulación y órdenes
  monitoring/    Logs, métricas y alertas
tests/           Pruebas
```

## Licencia

[MIT](LICENSE)
