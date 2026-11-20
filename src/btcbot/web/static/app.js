"use strict";

const REFRESH_MS = 60_000;
let chart = null;
let tz = "America/Bogota";
let marketChart = null;
let lastDashboard = null;
const MARKET_MS = 30_000;

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
  $("k-equity-sub").textContent = `Empezó con ${usd(a.initial)}`;
  setValue("k-return", pct(a["return"]), a["return"]);
  $("k-bh").textContent = `Solo comprar BTC: ${pct(a.bh_return)}`;
  setValue("k-dd", pct(a.max_drawdown, false), a.max_drawdown);
  $("k-dd-bh").textContent = `Lo máximo que cayó desde su mejor punto. Solo BTC: ${pct(a.bh_max_drawdown, false)}`;
  setValue("k-trades", String(m.trades));
  if (m.trades) {
    const wins = Math.round(m.win_rate * m.trades);
    const pf = m.profit_factor == null ? "todo lo ganado" : `${num(m.profit_factor)} USDT`;
    $("k-trades-sub").textContent = `Ganó ${wins} de ${m.trades}. Por cada 1 USDT perdido, ganó ${pf}`;
  } else {
    $("k-trades-sub").textContent = "Todavía no ha cerrado ninguna";
  }
}

function para(...parts) {
  const node = el("p");
  for (const part of parts) {
    node.append(Array.isArray(part) ? el("strong", part[0]) : document.createTextNode(part));
  }
  return node;
}

const day = (iso) =>
  new Date(iso).toLocaleDateString("es-CO", { timeZone: tz, day: "numeric", month: "long" });

function renderPlain(d) {
  const a = d.account;
  const s = d.status;
  const m = d.snapshot || {};
  const p = a.position;
  const bhValue = a.initial * (1 + a.bh_return);
  const better = a["return"] > a.bh_return;
  const out = [
    para(
      `Desde el ${day(d.equity[0].t)} el bot pasó de ${usd(a.initial)} a `,
      [`${usd(a.equity)} (${pct(a["return"])})`],
      `. Si ese día hubieras comprado BTC y no lo tocaras, tendrías ${usd(bhValue)} (${pct(a.bh_return)}). `,
      [better ? "Va mejor que solo comprar BTC." : "Por ahora va peor que solo comprar BTC."],
    ),
  ];
  if (p) {
    const going = p.unrealized_pnl >= 0 ? "ganando" : "perdiendo";
    out.push(para(
      `Ahora tiene BTC: compró a ${num(p.entry_price)} y va ${going} `,
      [pct(Math.abs(p.unrealized_pct), false)],
      `. Si el precio baja a ${num(p.stop)}, vende solo para cortar la pérdida. `,
      "Si la tendencia se da vuelta antes, también vende.",
    ));
  } else if (s.pending_entry) {
    out.push(para(["Acaba de ver una señal de compra"], ": compra al abrir la próxima vela."));
  } else {
    const parts = ["Ahora ", ["no tiene BTC"], ": espera a que el mercado vuelva a subir con fuerza."];
    if (m.close != null && !m.regime_up) {
      parts.push(` Para eso, el precio tendría que subir alrededor de ${pct(m.ema_regime / m.close - 1)} (hasta ~${num(m.ema_regime, 0)}).`);
    }
    out.push(para(...parts));
  }
  out.push(para(
    s.paused ? "⏸ El bot está pausado: no comprará hasta que lo reanudes por Telegram. " : "",
    `Revisa el mercado cada 4 horas; la próxima revisión es el ${when(s.next_close)}.`,
  ));
  $("plain").replaceChildren(...out);
}

function renderPosition(d) {
  const p = d.account.position;
  const s = d.status;
  if (!p) {
    rows($("position"), [
      ["Respuesta", s.pending_entry ? "No, pero compra en la próxima apertura" : "No, está en efectivo"],
      ["Efectivo", usd(d.account.cash)],
      ["Tiempo que ha tenido BTC", pct(d.account.exposure, false)],
    ]);
    return;
  }
  rows($("position"), [
    ["Respuesta", "Sí"],
    ["Cantidad", `${num(p.units, 6)} BTC (${usd(p.value)})`],
    ["Compró a", `${num(p.entry_price)} · ${when(p.entry_time)}`],
    ["Precio ahora", num(p.last_price)],
    ["Va", `${pct(p.unrealized_pct)} (${num(p.unrealized_pnl)} USDT)`, cls(p.unrealized_pnl)],
    ["Vende solo si baja a", `${num(p.stop)} (${pct(p.stop_distance_pct)})`, "down"],
    s.pending_exit ? ["Orden", "Vende en la próxima apertura", "down"] : ["Próxima revisión", when(s.next_close)],
  ]);
}

function renderMarket(d) {
  const m = d.snapshot || {};
  if (m.close == null) {
    $("checks").replaceChildren();
    rows($("market"), [["Estado", "Sin datos todavía"]]);
    return;
  }
  const params = (d.strategy && d.strategy.params) || {};
  const days = (n) => (n ? `≈${Math.round((n * 4) / 24)} días` : "");
  const check = (ok, title, detail) => {
    const li = el("li", `${ok ? "✅" : "❌"} ${title}`);
    li.append(el("small", detail));
    return li;
  };
  const gap = m.ema_regime / m.close - 1;
  $("checks").replaceChildren(
    check(
      m.trend_up,
      "El precio viene subiendo en los últimos días",
      `Promedio corto (${days(params.fast)}): ${num(m.ema_fast, 0)} ${m.trend_up ? ">" : "<"} promedio medio (${days(params.slow)}): ${num(m.ema_slow, 0)}`,
    ),
    check(
      m.regime_up,
      "La tendencia de fondo es alcista",
      `Precio ${num(m.close, 0)} ${m.regime_up ? ">" : "<"} promedio largo (${days(params.regime)}): ${num(m.ema_regime, 0)}` +
        (m.regime_up ? "" : ` → falta subir ${pct(gap)}`),
    ),
  );
  rows($("market"), [
    ["BTC (último cierre)", num(m.close)],
    ["Si comprara ahora, vendería si baja", `${pct(m.stop_distance / m.close, false)} (a ${num(m.close - m.stop_distance, 0)})`],
    ["Cuándo compra", "Cuando las dos se cumplen a la vez"],
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
        { label: "Con el bot", data: bot, borderColor: "#f7931a", borderWidth: 2, pointRadius: 0, tension: 0.15 },
        { label: "Solo BTC", data: bh, borderColor: "#6c7a96", borderWidth: 1.5, pointRadius: 0, tension: 0.15 },
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
  const reasons = { stop: "vendió por stop", signal: "vendió por señal", manual: "venta manual", end: "fin" };
  const cell = (...lines) => {
    const td = el("td");
    lines.forEach(([text, className]) => td.append(el("span", text, className)));
    return td;
  };
  $("trades").replaceChildren(
    ...d.trades.map((t) => {
      const tr = el("tr");
      tr.append(
        cell([when(t.entry_time), "line"], [num(t.entry_price, 0), "line"]),
        cell([when(t.exit_time), "line"], [num(t.exit_price, 0), "line"]),
        cell([`${pct(t.net_return)} (${num(t.pnl)})`, `line ${cls(t.pnl)}`],
             [reasons[t.exit_reason] || t.exit_reason, "line"]),
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
    lastDashboard = d.ready ? d : null;
    if (d.ready) {
      renderStatus(d);
      renderPlain(d);
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

function tradeMarkers(t0) {
  const d = lastDashboard;
  const buys = [];
  const sells = [];
  let stop = null;
  if (!d) return { buys, sells, stop };
  for (const t of d.trades) {
    const entry = Date.parse(t.entry_time);
    const exit = Date.parse(t.exit_time);
    if (entry >= t0) buys.push({ x: entry, y: t.entry_price });
    if (exit >= t0) sells.push({ x: exit, y: t.exit_price });
  }
  const p = d.account.position;
  if (p) {
    const entry = Date.parse(p.entry_time);
    if (entry >= t0) buys.push({ x: entry, y: p.entry_price });
    stop = p.stop;
  }
  return { buys, sells, stop };
}

function renderMarketChart(m) {
  const c = m.candles;
  const pts = (arr) => c.t.map((x, i) => ({ x, y: arr[i] }));
  const { buys, sells, stop } = tradeMarkers(c.t[0]);
  const last = c.t[c.t.length - 1];
  const datasets = [
    { label: "Precio", data: pts(c.close), borderColor: "#e6e9ef", borderWidth: 2, pointRadius: 0, tension: 0.1, order: 2 },
    { label: `Promedio corto (${c.periods.fast})`, data: pts(c.fast), borderColor: "#4fc3f7", borderWidth: 1.2, pointRadius: 0, order: 3 },
    { label: `Promedio medio (${c.periods.slow})`, data: pts(c.slow), borderColor: "#b388ff", borderWidth: 1.2, pointRadius: 0, order: 3 },
    { label: `Promedio largo (${c.periods.regime})`, data: pts(c.regime), borderColor: "#f5c542", borderWidth: 1.5, pointRadius: 0, order: 3 },
    { type: "scatter", label: "Compró", data: buys, backgroundColor: "#2ecc71", pointStyle: "triangle", pointRadius: 8, order: 1 },
    { type: "scatter", label: "Vendió", data: sells, backgroundColor: "#ff5c5c", pointStyle: "triangle", rotation: 180, pointRadius: 8, order: 1 },
  ];
  if (stop) {
    datasets.push({ label: "Stop", data: [{ x: c.t[0], y: stop }, { x: last, y: stop }],
      borderColor: "#ff5c5c", borderDash: [6, 4], borderWidth: 1, pointRadius: 0, order: 4 });
  }
  if (marketChart) {
    marketChart.data.datasets = datasets;
    marketChart.update("none");
    return;
  }
  marketChart = new Chart($("market-chart"), {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => item.parsed.y != null,
          callbacks: {
            title: (items) => (items.length ? when(new Date(items[0].parsed.x).toISOString()) : ""),
            label: (item) => `${item.dataset.label}: ${num(item.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          ticks: {
            color: "#8b93a7", maxTicksLimit: 6, maxRotation: 0,
            callback: (v) => new Date(v).toLocaleDateString("es-CO", { timeZone: tz, day: "numeric", month: "short" }),
          },
          grid: { color: "#1c2333" },
        },
        y: { ticks: { color: "#8b93a7" }, grid: { color: "#1c2333" } },
      },
    },
  });
}

async function refreshMarket() {
  try {
    const res = await fetch("/api/market", { cache: "no-store" });
    if (res.status === 401) {
      location.href = "/login";
      return;
    }
    const m = await res.json();
    const dot = document.querySelector(".pulse");
    if (!m.ok) {
      dot.classList.add("off");
      $("live-hint").textContent = m.error;
      return;
    }
    dot.classList.remove("off");
    $("live-price").textContent = `${num(m.price)} USDT`;
    setValue("live-change", `${pct(m.change_24h)} en 24 h`, m.change_24h);
    renderMarketChart(m);
  } catch (err) {
    $("live-hint").textContent = `No se pudo actualizar el precio (${err.message}).`;
  }
}

refresh().then(refreshMarket);
setInterval(refresh, REFRESH_MS);
setInterval(refreshMarket, MARKET_MS);
