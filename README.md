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
| 2. Datos e indicadores | ⏳ Pendiente |
| 3. Estrategia base | ⏳ Pendiente |
| 4. Backtesting | ⏳ Pendiente |
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
