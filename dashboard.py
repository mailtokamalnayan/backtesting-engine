"""Read-only Streamlit dashboard: browse and compare saved runs.

    python -m streamlit run dashboard.py

Runs are clustered by strategy. Within a strategy, each run's params are broken into
their own columns so variations are easy to compare, and you can multi-select runs to
see their full backtesting.py stats side by side and their equity curves overlaid.
Logic lives in small pure helpers (unit-tested); the Streamlit shell only wires them.
"""

import json

import pandas as pd

import config
from engine import persistence


# --- formatters -------------------------------------------------------------

def _fmt_pct(v):
    return "—" if v is None or pd.isna(v) else f"{float(v):.2f}%"


def _fmt_num(v):
    return "—" if v is None or pd.isna(v) else f"{float(v):.2f}"


def _fmt_int(v):
    return "—" if v is None or pd.isna(v) else f"{int(float(v))}"


def _fmt_money(v):
    return "—" if v is None or pd.isna(v) else f"{float(v):,.0f}"


def run_label(params_json) -> str:
    """Short label of the params that vary (skip the constant lot size)."""
    try:
        d = json.loads(params_json)
    except (TypeError, ValueError):
        return ""
    parts = [f"{k}={v}" for k, v in d.items() if k != "lot"]
    return ", ".join(parts) if parts else "default"


def _param_keys(runs: pd.DataFrame) -> list:
    keys = []
    for pj in runs["params_json"]:
        for k in json.loads(pj):
            if k not in keys:
                keys.append(k)
    return keys


def _split_pf(split_json):
    if not isinstance(split_json, str) or not split_json:
        return None
    return (json.loads(split_json).get("out_sample") or {}).get("profit_factor")


def build_runs_table(runs: pd.DataFrame) -> pd.DataFrame:
    """One row per run with params broken into columns + headline metrics.

    Intended for a single strategy's runs (a cluster), so the param columns are
    consistent. CAGR is included; Total PnL is final equity minus the cash base
    (the per-lot rupee P&L for futures runs).
    """
    if runs.empty:
        return pd.DataFrame()
    pkeys = _param_keys(runs)
    rows = []
    for _, r in runs.iterrows():
        p = json.loads(r["params_json"])
        stats = json.loads(r["stats_json"]) if isinstance(r["stats_json"], str) else {}
        final_eq = r["final_equity"]
        pnl = None if pd.isna(final_eq) else final_eq - config.DEFAULT_CASH
        row = {k: p.get(k, "—") for k in pkeys}
        row.update({
            "CAGR": _fmt_pct(r["cagr"]),
            "Return": _fmt_pct(r["return_pct"]),
            "Total PnL": _fmt_money(pnl),
            "Win%": _fmt_pct(r["win_rate"]),
            "PF": _fmt_num(stats.get("Profit Factor")),
            "OOS PF": _fmt_num(_split_pf(r.get("split_json"))),
            "Max DD": _fmt_pct(r["max_drawdown"]),
            "Sharpe": _fmt_num(r["sharpe"]),
            "Trades": _fmt_int(r["num_trades"]),
            "Period": f"{r['start_date']} → {r['end_date']}",
        })
        rows.append(row)
    cols = pkeys + ["CAGR", "Return", "Total PnL", "Win%", "PF", "OOS PF",
                    "Max DD", "Sharpe", "Trades", "Period"]
    return pd.DataFrame(rows, columns=cols)


# Full backtesting.py stat set, in display order, for the comparison view.
_FULL_STATS = [
    "Start", "End", "Duration", "Exposure Time [%]", "Equity Final [$]",
    "Equity Peak [$]", "Return [%]", "Buy & Hold Return [%]", "Return (Ann.) [%]",
    "CAGR [%]", "Volatility (Ann.) [%]", "Sharpe Ratio", "Sortino Ratio",
    "Calmar Ratio", "Max. Drawdown [%]", "Avg. Drawdown [%]",
    "Max. Drawdown Duration", "# Trades", "Win Rate [%]", "Best Trade [%]",
    "Worst Trade [%]", "Avg. Trade [%]", "Max. Trade Duration",
    "Avg. Trade Duration", "Profit Factor", "Expectancy [%]", "SQN",
    "Kelly Criterion",
]


def _fmt_stat(key, v):
    if v is None:
        return "—"
    if isinstance(v, str):
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if pd.isna(f):
        return "—"
    if key == "# Trades":
        return str(int(f))
    if "[%]" in key:
        return f"{f:.2f}%"
    if "[$]" in key:
        return f"{f:,.0f}"
    return f"{f:.2f}"


def build_comparison_table(runs: pd.DataFrame, run_ids) -> pd.DataFrame:
    """Full backtesting.py stats for the selected runs, side by side."""
    # Relabel "# Trades" -> "Trades": st.table renders the Metric cell as markdown,
    # and a leading '#' becomes an H1 heading.
    data = {"Metric": ["Trades" if k == "# Trades" else k for k in _FULL_STATS]}
    used = {}
    for rid in run_ids:
        sub = runs[runs["run_id"] == rid]
        if sub.empty:
            continue
        r = sub.iloc[0]
        stats = json.loads(r["stats_json"]) if isinstance(r["stats_json"], str) else {}
        base = run_label(r["params_json"]) or str(rid)[:8]
        used[base] = used.get(base, 0) + 1
        label = base if used[base] == 1 else f"{base} (#{used[base]})"
        data[label] = [_fmt_stat(k, stats.get(k)) for k in _FULL_STATS]
    return pd.DataFrame(data)


def build_oos_table(split: dict) -> pd.DataFrame:
    """In-sample vs out-of-sample comparison from a run's split summary."""
    def col(seg):
        seg = seg or {}
        return [
            _fmt_int(seg.get("trades")),
            _fmt_money(seg.get("total_pnl")),
            _fmt_money(seg.get("avg_pnl")),
            _fmt_pct(seg.get("win_rate")),
            _fmt_num(seg.get("profit_factor")),
        ]

    return pd.DataFrame({
        "Metric": ["Trades", "Total PnL", "Avg PnL/trade", "Win Rate",
                   "Profit Factor"],
        "In-Sample": col(split.get("in_sample")),
        "Out-of-Sample": col(split.get("out_sample")),
    })


# --- equity + trades --------------------------------------------------------

def load_equity_series(run_id) -> pd.Series:
    """Equity curve for one run as a timestamp-indexed Series (raises if unknown)."""
    artifacts = persistence.load_run_artifacts(run_id)
    return artifacts["equity"]["Equity"]


def equity_return_curve(series: pd.Series, max_points=2000) -> pd.Series:
    """Equity as % return from the start (begins at 0), downsampled for charting."""
    base = series.iloc[0]
    pct = (series / base - 1.0) * 100.0 if base else series * 0.0
    return downsample_equity(pct, max_points)


def downsample_equity(series: pd.Series, max_points=2000) -> pd.Series:
    """Shrink a large equity curve for charting.

    An intraday run's curve has one point per minute bar (~280k over 3 years),
    which makes the browser chart unresponsive. Collapse to daily closes first, then
    evenly sample if still large. Daily-run curves (already small) pass through.
    """
    if len(series) <= max_points:
        return series
    if isinstance(series.index, pd.DatetimeIndex):
        series = series.resample("D").last().dropna()
        if len(series) <= max_points:
            return series
    step = max(1, len(series) // max_points)
    return series.iloc[::step]


TRADE_COLUMNS = ["Entry", "Exit", "Duration", "Entry Price", "Exit Price",
                 "PnL", "Return %"]


def _fmt_dt(ts):
    if pd.isna(ts):
        return "—"
    s = pd.Timestamp(ts).strftime("%a, %b %d %y %I:%M%p")  # Tue, Feb 01 25 09:45AM
    return s.replace("AM", "am").replace("PM", "pm")


def _fmt_duration(td):
    if pd.isna(td):
        return "—"
    td = pd.Timedelta(td)
    hours, rem = divmod(td.seconds, 3600)
    minutes = rem // 60
    parts = []
    if td.days:
        parts.append(f"{td.days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def build_trades_table(trades: pd.DataFrame) -> pd.DataFrame:
    """Curated, human-formatted trade list, latest entry first."""
    if trades.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    t = trades.copy()
    t["_entry"] = pd.to_datetime(t["EntryTime"])
    t = t.sort_values("_entry", ascending=False)  # latest first
    return pd.DataFrame({
        "Entry": t["_entry"].map(_fmt_dt),
        "Exit": pd.to_datetime(t["ExitTime"]).map(_fmt_dt),
        "Duration": pd.to_timedelta(t["Duration"]).map(_fmt_duration),
        "Entry Price": t["EntryPrice"].map(lambda v: f"{v:,.2f}"),
        "Exit Price": t["ExitPrice"].map(lambda v: f"{v:,.2f}"),
        "PnL": t["PnL"].map(lambda v: f"{v:,.0f}"),
        "Return %": t["ReturnPct"].map(lambda v: f"{v * 100:.2f}%"),
    }, columns=TRADE_COLUMNS).reset_index(drop=True)


# --- Streamlit shell (runs only under `streamlit run`) ----------------------

if __name__ == "__main__":
    import streamlit as st

    st.set_page_config(page_title="Backtests", layout="wide")
    # Light, targeted styling to match the exported static site (IBM Plex type,
    # serif title, tabular monospace figures in tables). Robust selectors only —
    # the app structure is unchanged.
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@600&display=swap');
        .stApp, .stApp p, .stApp label, [class*="st-"] { font-family: 'IBM Plex Sans', sans-serif; }
        .stApp h1 { font-family: 'IBM Plex Serif', Georgia, serif; letter-spacing: -0.01em; }
        .stApp h2, .stApp h3 { letter-spacing: -0.01em; }
        [data-testid="stTable"] table { font-size: 13px; font-variant-numeric: tabular-nums; }
        [data-testid="stTable"] td { font-family: 'IBM Plex Mono', monospace; }
        [data-testid="stTable"] th {
            text-transform: uppercase; font-size: 11px; letter-spacing: 0.04em; color: #6c7178;
        }
        [data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Backtests")

    runs = persistence.list_runs()  # newest first

    if runs.empty:
        st.info(
            "No runs yet. Run e.g.\n\n"
            "`python run.py turnaround_tuesday_intraday --instrument nifty "
            "--start 2015-01-01`\n\n"
            "to record your first backtest."
        )
        st.stop()

    # Cluster by strategy.
    strategy = st.selectbox("Strategy", sorted(runs["strategy"].unique()))
    sub = runs[runs["strategy"] == strategy].reset_index(drop=True)

    st.subheader(f"{strategy} — {len(sub)} run(s)")
    st.dataframe(build_runs_table(sub), width="stretch", hide_index=True)
    st.caption(
        "CAGR is annualized return on the fixed cash base (10M); for 1-lot futures "
        "compare **Total PnL** and **PF / OOS PF** across rows. Each row is one "
        "parameter variation."
    )

    # Build unique labels -> run_id for selection.
    label_to_id = {}
    for _, r in sub.iterrows():
        base = run_label(r["params_json"]) or str(r["run_id"])[:8]
        label, i = base, 2
        while label in label_to_id:
            label, i = f"{base} (#{i})", i + 1
        label_to_id[label] = r["run_id"]

    picked = st.multiselect(
        "Select run(s) to compare / inspect",
        list(label_to_id), default=list(label_to_id)[:2],
    )
    if not picked:
        st.info("Select one or more runs above.")
        st.stop()
    picked_ids = [label_to_id[p] for p in picked]

    st.subheader("Full metrics (backtesting.py)")
    st.table(build_comparison_table(sub, picked_ids))

    st.subheader("Equity curves (% return from start)")
    curves = {}
    for p in picked:
        try:
            curves[p] = equity_return_curve(load_equity_series(label_to_id[p]))
        except (KeyError, FileNotFoundError):
            pass
    if curves:
        st.line_chart(pd.DataFrame(curves))

    # In-sample / out-of-sample, one table per selected run.
    st.subheader("Out-of-sample validation")
    splits = [(p, sub[sub["run_id"] == label_to_id[p]].iloc[0].get("split_json"))
              for p in picked]
    if any(isinstance(sj, str) and sj for _, sj in splits):
        first_split = next(json.loads(sj) for _, sj in splits
                           if isinstance(sj, str) and sj)
        st.caption(
            f"Split at {first_split['split_date']} — in-sample is the first "
            f"{first_split['fraction'] * 100:.0f}% of the range; out-of-sample is the "
            f"most-recent {(1 - first_split['fraction']) * 100:.0f}% (unseen). An edge "
            f"that holds here is far more trustworthy."
        )
        for label, sj in splits:
            if isinstance(sj, str) and sj:
                if len(picked) > 1:
                    st.markdown(f"**{label}**")
                st.table(build_oos_table(json.loads(sj)))

    # Trade list for a single selected run.
    if len(picked_ids) == 1:
        rid = picked_ids[0]
        row = sub[sub["run_id"] == rid].iloc[0]
        try:
            artifacts = persistence.load_run_artifacts(rid)
            st.subheader("Trades")
            st.caption(
                f"{row['slippage'] * 100:.2f}% slippage applied per fill; commission "
                f"not modeled. PnL is per the strategy's position size (Nifty futures "
                f"= 1 lot)."
            )
            st.dataframe(build_trades_table(artifacts["trades"]),
                         width="stretch", hide_index=True)
        except (KeyError, FileNotFoundError):
            st.warning("Trades for this run are unavailable.")
    else:
        st.caption("Select a single run to also see its trade list.")
