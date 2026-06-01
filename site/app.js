"use strict";

let DATA = null;
let CURRENT = null;            // current strategy name
let SELECTED = new Set();      // selected run labels
let CHART = null;
let GLOSSARY = {};             // column/metric label -> plain-English help

const $ = (id) => document.getElementById(id);

async function init() {
  const res = await fetch("data.json");
  DATA = await res.json();
  GLOSSARY = DATA.glossary || {};
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
  const strat = DATA.strategies[name];
  $("strat-title").textContent = `${name} — ${strat.runs.length} run(s)`;
  const src = $("strat-source");
  if (strat.source) {
    src.innerHTML = `Source: <a href="${strat.source}" target="_blank" rel="noopener">${strat.source}</a>`;
  } else {
    src.textContent = "";
  }
  renderRunsTable();
  // default-select the first two runs
  const labels = DATA.strategies[name].runs.map((r) => r.label);
  SELECTED = new Set(labels.slice(0, 2));
  renderPicker();
  renderSelection();
}

function isNumericVal(v) {
  if (typeof v === "number") return true;
  if (typeof v !== "string") return false;
  return /^[-+]?[₹$]?[\d,]+(\.\d+)?%?$/.test(v.trim());
}

// Colour signed *performance* cells only: negatives red, positive %/money green.
// Structural numbers (PF, Sharpe, counts, params) stay neutral.
function colorClass(v) {
  if (typeof v !== "string") return "";
  const s = v.trim();
  if (s.startsWith("-") && s !== "—") return "neg";
  const perf = s.endsWith("%") || /\d,\d/.test(s);
  return perf && /[1-9]/.test(s) ? "pos" : "";
}

function table(columns, rows) {
  // A column is right-aligned when most of its values are numeric.
  const rightCol = {};
  columns.forEach((c) => {
    const vals = rows.map((r) => r[c]).filter((v) => v != null && v !== "—" && v !== "");
    const n = vals.filter(isNumericVal).length;
    rightCol[c] = vals.length > 0 && n / vals.length >= 0.5;
  });
  const t = document.createElement("table");
  const htr = t.createTHead().insertRow();
  columns.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    const cls = rightCol[c] ? ["num"] : [];
    if (GLOSSARY[c]) { th.title = GLOSSARY[c]; cls.push("tip"); }  // hover help
    if (cls.length) th.className = cls.join(" ");
    htr.appendChild(th);
  });
  const tb = t.createTBody();
  rows.forEach((row) => {
    const tr = tb.insertRow();
    columns.forEach((c, ci) => {
      const td = tr.insertCell();
      const v = row[c];
      td.textContent = (v === undefined || v === null) ? "—" : v;
      const cls = [];
      if (rightCol[c]) cls.push("num");
      if (isNumericVal(v)) cls.push("figure");
      const col = colorClass(v);
      if (col) cls.push(col);
      // First column is a row label (e.g. a metric name): give it the same hover help.
      if (ci === 0 && GLOSSARY[v]) { td.title = GLOSSARY[v]; cls.push("tip"); }
      if (cls.length) td.className = cls.join(" ");
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

const PALETTE = ["#126b62", "#c0392b", "#3b6ea5", "#b07d2b", "#7d5ba6", "#1f7a47"];

function renderChart(runs) {
  // Union of dates across selected runs -> aligned datasets (null where missing).
  const dateSet = new Set();
  runs.forEach((r) => r.equity.forEach(([d]) => dateSet.add(d)));
  const labels = [...dateSet].sort();
  const datasets = runs.map((r, i) => ({
    label: r.label,
    data: (() => { const m = new Map(r.equity); return labels.map((d) => (m.has(d) ? m.get(d) : null)); })(),
    borderColor: PALETTE[i % PALETTE.length],
    borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 3, spanGaps: true, tension: 0,
  }));
  if (CHART) CHART.destroy();
  CHART = new Chart($("equity"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      font: { family: "'IBM Plex Mono', monospace", size: 11 },
      color: "#6c7178",
      interaction: { intersect: false, mode: "index" },
      scales: {
        x: {
          ticks: { maxTicksLimit: 9, autoSkip: true, color: "#9aa0a6",
                   font: { family: "'IBM Plex Mono', monospace", size: 10 } },
          grid: { display: false }, border: { color: "#e9e7e1" },
        },
        y: {
          ticks: { callback: (v) => v + "%", color: "#9aa0a6",
                   font: { family: "'IBM Plex Mono', monospace", size: 10 } },
          grid: { color: (c) => (c.tick.value === 0 ? "#cdcabf" : "#f1efe9") },
          border: { display: false },
        },
      },
      plugins: {
        legend: {
          position: "top", align: "start",
          labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true,
                    pointStyle: "line", color: "#1c2024",
                    font: { family: "'IBM Plex Mono', monospace", size: 11.5 } },
        },
        tooltip: {
          backgroundColor: "#1c2024", padding: 10, cornerRadius: 6,
          titleFont: { family: "'IBM Plex Mono', monospace", size: 11 },
          bodyFont: { family: "'IBM Plex Mono', monospace", size: 11.5 },
          callbacks: { label: (x) => ` ${x.dataset.label}: ${x.parsed.y > 0 ? "+" : ""}${x.parsed.y}%` },
        },
      },
    },
  });
}

init();
