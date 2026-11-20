"""Paper trading en vivo: opera con dinero simulado sobre datos reales.

Usa exactamente el mismo `SimBroker` y las mismas señales que el backtest, vela
a vela. Así, lo que pase en vivo se puede comparar directamente con lo que
predice el backtest.

Protecciones (sección 7 del plan):
- Pausa manual (interruptor de emergencia): bloquea compras nuevas; las ventas
  y los stops siguen funcionando para no dejar una posición desprotegida.
- Límite de pérdida diaria: si el capital cae `daily_loss_limit` desde el inicio
  del día UTC, no se compra más ese día.
- Datos atrasados: si la última vela cerrada llega tarde, no se opera y se avisa.
- Cada vela se guarda en una transacción: estado, operaciones y curva quedan
  coherentes aunque el proceso muera a mitad.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import pandas as pd

from btcbot.backtest.broker import AccountState, Fill, SimBroker
from btcbot.config import Config
from btcbot.live.notifier import Notifier
from btcbot.live.store import PaperStore
from btcbot.strategies import STRATEGIES
from btcbot.timeframes import timeframe_delta

log = logging.getLogger("btcbot")

CandleSource = Callable[[], pd.DataFrame]


def usd(x: float) -> str:
    return f"{x:,.2f} USDT"


def price_fmt(x: float) -> str:
    return f"{x:,.2f}"


def pct(x: float) -> str:
    return f"{x * 100:+.2f} %"


@dataclass
class TickResult:
    processed: int = 0
    fills: list[Fill] = field(default_factory=list)
    skipped: str | None = None


class PaperTrader:
    def __init__(
        self,
        cfg: Config,
        store: PaperStore,
        notifier: Notifier,
        candle_source: CandleSource,
        strategy: str = "ema_trend",
    ):
        if cfg.paper is None:
            raise ValueError("Falta la sección [paper] en la configuración")
        self.cfg = cfg
        self.p = cfg.paper
        self.store = store
        self.notifier = notifier
        self.candle_source = candle_source
        self.strategy = strategy
        self.spec = STRATEGIES[strategy]
        self.params = self.spec.params_cls(**cfg.strategy.get(strategy, {}))
        self.broker = SimBroker(cfg.costs.fee_rate, cfg.costs.slippage_rate,
                                cfg.risk.risk_per_trade, cfg.risk.max_position_fraction)
        self.step = timeframe_delta(cfg.market.timeframe)
        self.tz = ZoneInfo(self.p.display_tz)

    # --- utilidades ------------------------------------------------------------
    def local(self, ts: pd.Timestamp) -> str:
        return pd.Timestamp(ts).tz_convert(self.tz).strftime("%Y-%m-%d %H:%M")

    def due(self, now: pd.Timestamp) -> bool:
        """¿Ya cerró una vela que no hemos procesado?"""
        last = self.store.last_candle()
        return last is None or now >= last + 2 * self.step

    # --- ciclo principal ----------------------------------------------------------
    def tick(self, now: pd.Timestamp | None = None) -> TickResult:
        now = now or pd.Timestamp.now(tz="UTC")
        self.store.set("last_tick", now.isoformat())
        if not self.due(now):
            return TickResult(skipped="sin vela nueva")

        candles = self.candle_source()
        closed = candles[candles.index + self.step <= now]
        if closed.empty:
            raise RuntimeError("No hay velas cerradas disponibles")
        latest = closed.index[-1]

        lag = (now - (latest + self.step)) / self.step
        if lag > self.p.max_stale_candles:
            if not self.store.get("stale", False):
                self.store.set("stale", True)
                msg = (f"⚠️ Datos atrasados: la última vela cerrada es de {self.local(latest)}. "
                       "No se opera hasta que lleguen datos al día.")
                self.store.add_event(now, "error", "stale", msg)
                self.notifier.send(msg)
            return TickResult(skipped="datos atrasados")
        if self.store.get("stale", False):
            self.store.set("stale", False)
            msg = "✅ Los datos volvieron a llegar al día. El bot sigue operando."
            self.store.add_event(now, "info", "stale", msg)
            self.notifier.send(msg)

        state = self.store.load_state()
        messages: list[str] = []
        if state is None:
            state = AccountState(cash=self.p.initial_capital)
            new = closed.iloc[-1:]
            with self.store.transaction():
                self._start(now, new.index[0], float(new["open"].iloc[0]), messages)
        else:
            new = closed[closed.index > self.store.last_candle()]
        if new.empty:
            return TickResult(skipped="sin vela nueva")

        signals = self.spec.signals(closed, self.params)
        result = TickResult()
        for ts in new.index:
            with self.store.transaction():
                fills = self._process(state, ts, closed.loc[ts], signals.loc[ts], messages)
                self.store.save_state(state)
                self.store.set_last_candle(ts)
            result.processed += 1
            result.fills.extend(fills)

        if self.spec.snapshot:
            snap = self.spec.snapshot(closed, self.params)
            snap["time"] = (latest + self.step).isoformat()
            self.store.set("snapshot", snap)

        # Avisos solo después de guardar: nunca se avisa algo que no quedó registrado
        for msg in messages:
            self.notifier.send(msg)
        return result

    # --- piezas -------------------------------------------------------------------
    def _start(self, now: pd.Timestamp, first: pd.Timestamp, open_price: float,
               messages: list[str]) -> None:
        self.store.set("started_at", now.isoformat())
        self.store.set("initial_capital", self.p.initial_capital)
        self.store.set("strategy", {"name": self.strategy, "params": self.params.__dict__})
        self.store.set("last_equity", self.p.initial_capital)
        self.store.add_equity(first, self.p.initial_capital, open_price, False)
        msg = (f"🚀 Paper trading iniciado ({self.cfg.market.symbol} {self.cfg.market.timeframe})\n"
               f"Capital simulado: {usd(self.p.initial_capital)}\n"
               f"Riesgo por operación: {self.cfg.risk.risk_per_trade:.1%}")
        self.store.add_event(now, "info", "start", msg)
        messages.append(msg)

    def _process(self, state: AccountState, ts: pd.Timestamp, candle: pd.Series,
                 sig: pd.Series, messages: list[str]) -> list[Fill]:
        close_time = ts + self.step
        day = str((close_time - pd.Timedelta(microseconds=1)).date())
        day_info = self.store.get("day")
        if day_info is None or day_info["date"] != day:
            day_info = {"date": day, "start_equity": self.store.get("last_equity"),
                        "limit_hit": False}

        fills = self.broker.step(
            state, ts, float(candle["open"]), float(candle["low"]), float(candle["close"]),
            bool(sig["entry"]), bool(sig["exit"]), float(sig["stop_distance"]),
        )
        for f in fills:
            msg = self._fill_message(f, state)
            kind = "buy" if f.kind == "buy" else f"sell_{f.reason}"
            if f.trade is not None:
                self.store.add_trade(f.trade)
            self.store.add_event(f.time, "trade", kind, msg)
            messages.append(msg)

        close = float(candle["close"])
        equity = state.equity(close)
        self.store.add_equity(close_time, equity, close, state.in_position)
        self.store.set("last_equity", equity)

        limit = self.p.daily_loss_limit
        if not day_info["limit_hit"] and equity <= day_info["start_equity"] * (1 - limit):
            day_info["limit_hit"] = True
            msg = (f"⛔ Límite de pérdida diaria alcanzado ({limit:.0%}). "
                   "No se abren compras hasta mañana (UTC). Ventas y stops siguen activos.")
            self.store.add_event(close_time, "warning", "daily_limit", msg)
            messages.append(msg)

        next_open = self.local(close_time)
        if state.pending_entry:
            reason = ("el bot está pausado" if self.store.paused
                      else "se alcanzó el límite de pérdida diaria" if day_info["limit_hit"]
                      else None)
            if reason:
                state.pending_entry = False
                state.pending_dist = float("nan")
                msg = f"⏸️ Señal de compra ignorada porque {reason}."
                self.store.add_event(close_time, "warning", "entry_blocked", msg)
                messages.append(msg)
            else:
                msg = (f"📈 Señal de compra al cierre de {self.local(close_time)}. "
                       f"Se compra en la apertura ({next_open}).")
                self.store.add_event(close_time, "info", "entry_signal", msg)
        if state.pending_exit:
            msg = (f"📉 Señal de venta al cierre de {self.local(close_time)}. "
                   f"Se vende en la apertura ({next_open}).")
            self.store.add_event(close_time, "info", "exit_signal", msg)

        self.store.set("day", day_info)
        # Último cierre del día UTC → resumen diario
        if (close_time + self.step - pd.Timedelta(microseconds=1)).date() != (
                close_time - pd.Timedelta(microseconds=1)).date():
            messages.append(self._daily_summary(day, day_info["start_equity"], equity, state,
                                                close))
        return fills

    def _fill_message(self, f: Fill, state: AccountState) -> str:
        if f.kind == "buy":
            dist = (f.price - state.stop) / f.price
            return (f"🟢 COMPRA (simulada)\n"
                    f"Precio: {price_fmt(f.price)}\n"
                    f"Cantidad: {f.units:.6f} BTC ({usd(f.units * f.price)})\n"
                    f"Stop: {price_fmt(state.stop)} (−{dist:.2%})\n"
                    f"Hora: {self.local(f.time)}")
        t = f.trade
        icon, label = {"stop": ("🛑", "STOP"), "signal": ("🔴", "VENTA por señal"),
                       "manual": ("✋", "VENTA manual")}.get(f.reason, ("🔴", "VENTA"))
        return (f"{icon} {label} (simulada)\n"
                f"Precio: {price_fmt(f.price)}\n"
                f"Resultado: {pct(t.net_return)} ({t.pnl:+,.2f} USDT)\n"
                f"Duración: {t.bars} velas\n"
                f"Capital: {usd(state.cash)}")

    def _daily_summary(self, day: str, start_equity: float, equity: float,
                       state: AccountState, close: float) -> str:
        change = equity / start_equity - 1 if start_equity else 0.0
        initial = self.store.get("initial_capital", self.p.initial_capital)
        position = (f"abierta desde {self.local(state.entry_time)}, stop {price_fmt(state.stop)}"
                    if state.in_position else "sin posición")
        snap = ""
        if self.spec.snapshot:
            snap = f"\nMercado: {self.store.get('snapshot', {}).get('summary', '')}"
        return (f"📊 Resumen del {day}\n"
                f"Capital: {usd(equity)} ({pct(change)} hoy, "
                f"{pct(equity / initial - 1)} total)\n"
                f"BTC: {price_fmt(close)}\n"
                f"Posición: {position}"
                f"{' · ⏸️ PAUSADO' if self.store.paused else ''}{snap}")

    # --- control manual -----------------------------------------------------------
    def pause(self, who: str = "manual") -> str:
        self.store.set_paused(True)
        msg = f"⏸️ Bot pausado ({who}). No abrirá compras nuevas; ventas y stops siguen activos."
        self.store.add_event(pd.Timestamp.now(tz="UTC"), "warning", "pause", msg)
        return msg

    def resume(self, who: str = "manual") -> str:
        self.store.set_paused(False)
        msg = f"▶️ Bot reanudado ({who})."
        self.store.add_event(pd.Timestamp.now(tz="UTC"), "info", "resume", msg)
        return msg

    def performance_text(self) -> str:
        from btcbot.backtest.metrics import max_drawdown, trade_metrics

        eq = self.store.equity()
        if len(eq) < 2:
            return "Todavía no hay suficiente historial para un resumen."
        trades = self.store.trades()
        tm = trade_metrics(trades["net_return"].tolist())
        curve, closes = eq["equity"], eq["close"]
        bh = closes.iloc[-1] / closes.iloc[0] - 1
        days = (eq.index[-1] - eq.index[0]) / pd.Timedelta(days=1)
        lines = [
            f"📊 Desempeño desde {self.local(eq.index[0])} ({days:.0f} días)",
            f"Capital: {usd(curve.iloc[-1])} ({pct(curve.iloc[-1] / curve.iloc[0] - 1)})",
            f"Buy & hold en el mismo periodo: {pct(bh)}",
            f"Caída máxima: {max_drawdown(curve) * 100:.2f} % "
            f"(buy & hold: {max_drawdown(closes) * 100:.2f} %)",
            f"Operaciones cerradas: {tm.trades}",
        ]
        if tm.trades:
            lines += [
                f"Acierto: {tm.win_rate:.0%} · Profit factor: {tm.profit_factor:.2f}",
                f"Ganancia media: {pct(tm.avg_win)} · Pérdida media: {pct(tm.avg_loss)}",
            ]
        return "\n".join(lines)

    def trades_text(self, n: int = 5) -> str:
        trades = self.store.trades()
        if trades.empty:
            return "Todavía no hay operaciones cerradas."
        reasons = {"stop": "🛑 stop", "signal": "🔴 señal", "manual": "✋ manual"}
        lines = [f"Últimas {min(n, len(trades))} operaciones:"]
        for t in trades.tail(n).iloc[::-1].itertuples():
            lines.append(f"{self.local(t.entry_time)} → {self.local(t.exit_time)}: "
                         f"{pct(t.net_return)} ({t.pnl:+,.2f} USDT) · "
                         f"{reasons.get(t.exit_reason, t.exit_reason)}")
        return "\n".join(lines)

    def status_text(self) -> str:
        state = self.store.load_state()
        if state is None:
            return "El bot todavía no ha procesado ninguna vela."
        snap = self.store.get("snapshot", {})
        price = snap.get("close")
        initial = self.store.get("initial_capital", self.p.initial_capital)
        equity = self.store.get("last_equity", state.cash)
        lines = [
            f"🤖 Estado ({'⏸️ PAUSADO' if self.store.paused else '🟢 activo'})",
            f"Capital: {usd(equity)} ({pct(equity / initial - 1)} desde el inicio)",
        ]
        if price:
            lines.append(f"BTC (último cierre): {price_fmt(price)}")
        if state.in_position:
            lines.append(f"Posición: {state.units:.6f} BTC desde {self.local(state.entry_time)}, "
                         f"entrada {price_fmt(state.entry_price)}, stop {price_fmt(state.stop)}")
        else:
            lines.append("Posición: ninguna")
        if snap.get("summary"):
            lines.append(f"Mercado: {snap['summary']}")
        last = self.store.last_candle()
        if last is not None:
            lines.append(f"Próxima vela cierra: {self.local(last + 2 * self.step)}")
        return "\n".join(lines)


def run_forever(trader: PaperTrader, stop: threading.Event | None = None) -> None:
    """Ejecuta `tick` cada `poll_seconds` hasta que `stop` se active."""
    stop = stop or threading.Event()
    last_error: str | None = None
    log.info("Paper trading en marcha. Revisando cada %ss.", trader.p.poll_seconds)
    while not stop.is_set():
        try:
            result = trader.tick()
            if result.processed:
                log.info("Procesadas %d velas nuevas", result.processed)
            if last_error is not None:
                trader.notifier.send("✅ El bot se recuperó del error anterior.")
                last_error = None
        except Exception as exc:  # el loop nunca debe morir por un error puntual
            log.exception("Error en el ciclo del bot")
            text = f"{type(exc).__name__}: {exc}"
            if text != last_error:  # no repetir el mismo aviso en cada intento
                msg = f"⚠️ Error en el bot: {text}. Reintentando."
                trader.store.add_event(pd.Timestamp.now(tz="UTC"), "error", "exception", msg)
                trader.notifier.send(msg)
                last_error = text
        stop.wait(trader.p.poll_seconds)
