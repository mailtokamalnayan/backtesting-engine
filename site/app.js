"use strict";

let DATA = null;
let CURRENT = null;            // current strategy name
let SELECTED = new Set();      // selected run labels
let CHART = null;

const $ = (id) => document.getElementById(id);

async function init() {
  const res = await fetch("data.json");
  DATA = await res.json();
  $("meta").textContent = `Generated ${DATA.generated_at}`;
  const names = Object.keys(DATA.strategies);
  renderTabs(names);
  selectStrategy(names[0]);
}

function renderTabs(names) {
  $("strategies").innerHTML = "";
  names.forEach((name) => {
    const b = document.createElement("button");
    b.textContent = name;
    b.className = "tab";
    b.onclick = () => selectStrategy(name);
    b.dataset.name = name;
    $("strategies").appendChild(b);
  });
}

function selectStrategy(name) {
  CURRENT = name;
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.name === name));
  $("strat-title").textContent = `${name} — ${DATA.strategies[name].runs.length} run(s)`;
  renderRunsTable();
  // default-select the first two runs
  const labels = DATA.strategies[name].runs.map((r) => r.label);
  SELECTED = new Set(labels.slice(0, 2));
  renderPicker();
  renderSelection();
}

function table(columns, rows) {
  const t = document.createElement("table");
  const thead = t.createTHead().insertRow();
  columns.forEach((c) => { const th = document.createElement("th"); th.textContent = c; thead.appendChild(th); });
  const tb = t.createTBody();
  rows.forEach((row) => {
    const tr = tb.insertRow();
    columns.forEach((c) => {
      const td = tr.insertCell();
      const v = row[c];
      td.textContent = (v === undefined || v === null) ? "—" : v;
      if (typeof v === "string" && (v.startsWith("-") && v.endsWith("%"))) td.classList.add("neg");
    });
  });
  return t;
}

function renderRunsTable() {
  const s = DATA.strategies[CURRENT];
  $("runs-table").replaceChildren(table(s.columns, s.rows));
}

function renderPicker() {
  const wrap = $("run-picker");
  wrap.innerHTML = "";
  DATA.strategies[CURRENT].runs.forEach((r) => {
    const id = "pick-" + r.label.replace(/\W+/g, "_");
    const label = document.createElement("label");
    label.className = "chk";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = SELECTED.has(r.label);
    cb.onchange = () => {
      if (cb.checked) SELECTED.add(r.label); else SELECTED.delete(r.label);
      renderSelection();
    };
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + r.label));
    wrap.appendChild(label);
  });
}

function selectedRuns() {
  return DATA.strategies[CURRENT].runs.filter((r) => SELECTED.has(r.label));
}

function renderSelection() {
  const runs = selectedRuns();
  renderChart(runs);
  renderCompare(runs);
  renderOOS(runs);
  renderTrades(runs);
}

function renderCompare(runs) {
  if (!runs.length) { $("compare-table").innerHTML = "<p class='muted'>Select one or more runs.</p>"; return; }
  const cols = ["Metric", ...runs.map((r) => r.label)];
  const rows = DATA.stat_labels.map((metric) => {
    const row = { Metric: metric };
    runs.forEach((r) => { row[r.label] = r.full_stats[metric] ?? "—"; });
    return row;
  });
  $("compare-table").replaceChildren(table(cols, rows));
}

function renderOOS(runs) {
  const host = $("oos");
  host.innerHTML = "";
  const withSplit = runs.filter((r) => r.oos && r.oos.length);
  if (!withSplit.length) { $("oos-caption").textContent = ""; return; }
  $("oos-caption").textContent =
    "In-sample = first 70% of the range; out-of-sample = most-recent 30% (unseen). " +
    "An edge that holds out-of-sample is far more trustworthy.";
  withSplit.forEach((r) => {
    if (runs.length > 1) {
      const h = document.createElement("div"); h.className = "subhead"; h.textContent = r.label;
      host.appendChild(h);
    }
    const cols = Object.keys(r.oos[0]);
    const wrap = document.createElement("div"); wrap.className = "tablewrap";
    wrap.appendChild(table(cols, r.oos));
    host.appendChild(wrap);
  });
}

function renderTrades(runs) {
  const sec = $("trades-section");
  if (runs.length !== 1) {
    $("trades").innerHTML = "<p class='muted'>Select a single run to see its trade list.</p>";
    $("trades-caption").textContent = "";
    return;
  }
  const r = runs[0];
  $("trades-caption").textContent =
    "Latest first. 0.05% slippage per fill; commission not modeled. PnL is per 1 Nifty futures lot.";
  if (!r.trades.length) { $("trades").innerHTML = "<p class='muted'>No trades.</p>"; return; }
  const cols = Object.keys(r.trades[0]);
  $("trades").replaceChildren(table(cols, r.trades));
}

function renderChart(runs) {
  // Union of dates across selected runs -> aligned datasets (null where missing).
  const dateSet = new Set();
  runs.forEach((r) => r.equity.forEach(([d]) => dateSet.add(d)));
  const labels = [...dateSet].sort();
  const palette = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2"];
  const datasets = runs.map((r, i) => {
    const m = new Map(r.equity);
    return {
      label: r.label,
      data: labels.map((d) => (m.has(d) ? m.get(d) : null)),
      borderColor: palette[i % palette.length],
      borderWidth: 1.5, pointRadius: 0, spanGaps: true, tension: 0,
    };
  });
  if (CHART) CHART.destroy();
  CHART = new Chart($("equity"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { intersect: false, mode: "index" },
      scales: {
        x: { ticks: { maxTicksLimit: 10, autoSkip: true }, grid: { display: false } },
        y: { ticks: { callback: (v) => v + "%" } },
      },
      plugins: { legend: { position: "top" } },
    },
  });
}

init();
