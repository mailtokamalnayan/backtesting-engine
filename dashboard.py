"""Read-only Streamlit dashboard: browse and compare saved runs.

    python -m streamlit run dashboard.py

Logic lives in small pure helpers (unit-tested); the Streamlit shell at the bottom
only wires them to widgets. The runs table is the comparison surface (one row per
run/variation). The detail view shows one run at a time — equity curve, metrics,
trades. Cross-run equity-curve overlay is deferred (see plan Scope Boundaries).
"""

import json

import pandas as pd

from engine import persistence

# Display column order for the runs table.
TABLE_COLUMNS = [
    "Run ID", "Strategy", "Instrument", "Params", "CAGR", "Return",
    "Max DD", "Win Rate", "Sharpe", "# Trades", "Created",
]


def _pct(v):
    return "—" if v is None or pd.isna(v) else f"{v:.2f}%"


def _num(v, places=2):
    return "—" if v is None or pd.isna(v) else f"{v:.{places}f}"


def _params(params_json):
    try:
        d = json.loads(params_json)
    except (TypeError, ValueError):
        return ""
    return ",".join(f"{k}={v}" for k, v in d.items())


def build_table(runs: pd.DataFrame) -> pd.DataFrame:
    """Format the raw runs frame into the display table (order preserved)."""
    if runs.empty:
        return pd.DataFrame(columns=TABLE_COLUMNS)
    rows = []
    for _, r in runs.iterrows():
        rows.append({
            "Run ID": r["run_id"],
            "Strategy": r["strategy"],
            "Instrument": r["instrument"],
            "Params": _params(r["params_json"]),
            "CAGR": _pct(r["cagr"]),
            "Return": _pct(r["return_pct"]),
            "Max DD": _pct(r["max_drawdown"]),
            "Win Rate": _pct(r["win_rate"]),
            "Sharpe": _num(r["sharpe"]),
            "# Trades": "—" if pd.isna(r["num_trades"]) else int(r["num_trades"]),
            "Created": r["created_at"],
        })
    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def filter_runs(runs: pd.DataFrame, strategy="All", instrument="All") -> pd.DataFrame:
    out = runs
    if strategy != "All":
        out = out[out["strategy"] == strategy]
    if instrument != "All":
        out = out[out["instrument"] == instrument]
    return out


def load_equity_series(run_id) -> pd.Series:
    """Equity curve for one run as a timestamp-indexed Series (raises if unknown)."""
    artifacts = persistence.load_run_artifacts(run_id)
    return artifacts["equity"]["Equity"]


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


def _options(runs, column):
    return ["All"] + sorted(runs[column].dropna().unique().tolist())


# --- Streamlit shell (runs only under `streamlit run`) ----------------------

if __name__ == "__main__":
    import streamlit as st

    st.set_page_config(page_title="Backtests", layout="wide")
    st.title("Backtests")

    runs = persistence.list_runs()  # already created_at DESC

    if runs.empty:
        st.info(
            "No runs yet. Run e.g.\n\n"
            "`python run.py ema_cross --instrument nifty --n1 10 --n2 20 "
            "--start 2018-01-01 --end 2024-12-31 --commission-pct 0.05`\n\n"
            "to record your first backtest."
        )
    else:
        c1, c2 = st.columns(2)
        strategy = c1.selectbox("Strategy", _options(runs, "strategy"))
        instrument = c2.selectbox("Instrument", _options(runs, "instrument"))
        filtered = filter_runs(runs, strategy, instrument)

        st.dataframe(build_table(filtered), width="stretch",
                     hide_index=True)

        if filtered.empty:
            st.info("No runs match the current filter.")
            st.stop()

        run_id = st.selectbox("Inspect run", filtered["run_id"].tolist())
        if run_id:
            try:
                artifacts = persistence.load_run_artifacts(run_id)
            except (KeyError, FileNotFoundError):
                st.warning(f"Artifacts for {run_id} are unavailable.")
            else:
                st.subheader("Equity curve")
                st.line_chart(downsample_equity(artifacts["equity"]["Equity"]))
                left, right = st.columns([1, 2])
                left.subheader("Metrics")
                left.json(artifacts["metrics"])
                right.subheader("Trades")
                right.dataframe(artifacts["trades"], width="stretch")
