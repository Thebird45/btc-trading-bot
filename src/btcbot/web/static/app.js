"use strict";

const REFRESH_MS = 60_000;
let chart = null;
let tz = "America/Bogota";

const $ = (id) => document.getElementById(id);

const num = (x, d = 2) =>
  x == null ? "–" : x.toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d });
const usd = (x) => (x == null ? "–" : `${num(x)} USDT`);
const pct = (x, sign = true) =>
  x == null ? "–" : `${sign && x > 0 ? "+" : ""}${num(x * 100)} %`;
const cls = (x) => (x == null || x === 0 ? "" : x > 0 ? "up" : "down");

function when(iso, withYear = false) {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("es-CO", {
    timeZone: tz,
    year: withYear ? "numeric" : undefined,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function setValue(id, text, colorFrom) {
  const node = $(id);
  node.textContent = text;
  node.classList.remove("up", "down");
  const c = colorFrom === undefined ? "" : cls(colorFrom);
  if (c) node.classList.add(c);
}

function rows(container, pairs) {
  container.replaceChildren(
    ...pairs.map(([label, value, color]) => {
      const row = el("div", null, "row");
      row.append(el("span", label), el("span", value, color || ""));
      return row;
    }),
  );
}

function badge(id, text, kind) {
  const node = $(id);
  node.textContent = text;
  node.className = `badge ${kind}`;
}

function renderStatus(d) {
  const s = d.status;
  if (s.paused) badge("badge-run", "⏸ Pausado", "warn");
  else badge("badge-run", "● Activo", "ok");
  if (!s.alive) badge("badge-health", "Bot sin responder", "bad");
  else if (s.stale) badge("badge-health", "Datos atrasados", "warn");
  else badge("badge-health", "Datos al día", "ok");
}

function renderKpis(d) {
  const a = d.account;
  const m = d.metrics;
  setValue("k-equity", usd(a.equity));
  $("k-equity-sub").textContent = `Inicial ${usd(a.initial)}`;
  setValue("k-return", pct(a["return"]), a["return"]);
  $("k-bh").textContent = `Buy & hold: ${pct(a.bh_return)}`;
  setValue("k-dd", pct(a.max_drawdown, false), a.max_drawdown);
  $("k-dd-bh").textContent = `Buy & hold: ${pct(a.bh_max_drawdown, false)}`;
  setValue("k-trades", String(m.trades));
  $("k-trades-sub").textContent = m.trades
    ? `Acierto ${pct(m.win_rate, false)} · PF ${num(m.profit_factor)}`
    : `Tiempo invertido ${pct(a.exposure, false)}`;
}

function renderPosition(d) {
  const p = d.account.position;
  const s = d.status;
  if (!p) {
    const waiting = s.pending_entry
      ? "Compra programada para la próxima apertura"
      : "Sin posición: esperando señal de compra";
    rows($("position"), [
      ["Estado", waiting],
      ["Efectivo", usd(d.account.cash)],
      ["Próxima vela cierra", when(s.next_close)],
    ]);
    return;
  }
  rows($("position"), [
    ["BTC", num(p.units, 6)],
    ["Entrada", `${num(p.entry_price)} · ${when(p.entry_time)}`],
    ["Precio actual", num(p.last_price)],
    ["Resultado abierto", `${pct(p.unrealized_pct)} (${num(p.unrealized_pnl)} USDT)`, cls(p.unrealized_pnl)],
    ["Stop", `${num(p.stop)} (${pct(p.stop_distance_pct)})`, "down"],
    ["Valor", usd(p.value)],
    s.pending_exit ? ["Orden", "Venta programada para la próxima apertura", "down"] : ["Próxima vela", when(s.next_close)],
  ]);
}

function renderMarket(d) {
  const m = d.snapshot || {};
  if (m.close == null) {
    rows($("market"), [["Estado", "Sin datos todavía"]]);
    return;
  }
  const params = (d.strategy && d.strategy.params) || {};
  rows($("market"), [
    ["BTC (último cierre)", num(m.close)],
    ["Lectura", m.summary || "–"],
    [`EMA rápida (${params.fast ?? "?"})`, num(m.ema_fast), m.trend_up ? "up" : "down"],
    [`EMA lenta (${params.slow ?? "?"})`, num(m.ema_slow)],
    [`EMA régimen (${params.regime ?? "?"})`, num(m.ema_regime), m.regime_up ? "up" : "down"],
    ["Distancia de stop (ATR)", `${num(m.stop_distance)} (${pct(m.stop_distance / m.close, false)})`],
    ["Compraría si", "EMA rápida > lenta y precio > EMA régimen"],
  ]);
}

function renderChart(d) {
  const labels = d.equity.map((p) => when(p.t));
  const bot = d.equity.map((p) => p.equity);
  const bh = d.equity.map((p) => p.bh);
  if (chart) {
    chart.data.labels = labels;
    chart.data.datasets[0].data = bot;
    chart.data.datasets[1].data = bh;
    chart.update("none");
    return;
  }
  chart = new Chart($("chart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Bot", data: bot, borderColor: "#f7931a", borderWidth: 2, pointRadius: 0, tension: 0.15 },
        { label: "Buy & hold", data: bh, borderColor: "#6c7a96", borderWidth: 1.5, pointRadius: 0, tension: 0.15 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${usd(c.parsed.y)}` } },
      },
      scales: {
        x: { ticks: { color: "#8b93a7", maxTicksLimit: 6, maxRotation: 0 }, grid: { color: "#1c2333" } },
        y: { ticks: { color: "#8b93a7" }, grid: { color: "#1c2333" } },
      },
    },
  });
}

function renderTrades(d) {
  const reasons = { stop: "Stop", signal: "Señal", manual: "Manual", end: "Fin" };
  const body = $("trades");
  body.replaceChildren(
    ...d.trades.map((t) => {
      const tr = el("tr");
      tr.append(
        el("td", `${when(t.entry_time)}\n${num(t.entry_price)}`),
        el("td", `${when(t.exit_time)}\n${num(t.exit_price)}`),
        el("td", `${pct(t.net_return)} (${num(t.pnl)})`, cls(t.pnl)),
        el("td", reasons[t.exit_reason] || t.exit_reason),
      );
      return tr;
    }),
  );
  $("trades-empty").hidden = d.trades.length > 0;
}

function renderEvents(d) {
  $("events").replaceChildren(
    ...d.events.map((e) => {
      const li = el("li", null, e.level);
      li.append(el("time", when(e.ts, true)), document.createTextNode(e.message));
      return li;
    }),
  );
}

async function refresh() {
  try {
    const res = await fetch("/api/dashboard", { cache: "no-store" });
    if (res.status === 401) {
      location.href = "/login";
      return;
    }
    const d = await res.json();
    tz = d.tz || tz;
    $("title").textContent = `BTC Bot · ${d.symbol} ${d.timeframe}`;
    $("not-ready").hidden = d.ready;
    $("content").hidden = !d.ready;
    if (d.ready) {
      renderStatus(d);
      renderKpis(d);
      renderPosition(d);
      renderMarket(d);
      renderChart(d);
      renderTrades(d);
      renderEvents(d);
    }
    $("footer").textContent =
      `Actualizado ${when(d.now, true)} · riesgo ${pct(d.risk_per_trade, false)} por operación · se actualiza cada minuto`;
  } catch (err) {
    $("footer").textContent = `No se pudo actualizar (${err.message}). Reintentando…`;
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
