"""Read-only Streamlit dashboard: browse and compare saved runs.

    python -m streamlit run dashboard.py

Runs are clustered by strategy. Within a strategy, each run's params are broken into
their own columns so variations are easy to compare, and you can multi-select runs to
see their full backtesting.py stats side by side and their equity curves overlaid.
Logic lives in small pure helpers (unit-tested); the Streamlit shell only wires them.
"""

import datetime
import json
import os

import pandas as pd

import config
import glossary
import strategies
from engine import persistence


def _column_config(columns):
    """Per-column header tooltips (st.column_config) from the shared glossary."""
    import streamlit as st

    return {c: st.column_config.Column(help=glossary.help_for(c))
            for c in columns if glossary.help_for(c)}

# Shared line palette — kept in sync with site/app.js PALETTE.
PALETTE = ["#126b62", "#c0392b", "#3b6ea5", "#b07d2b", "#7d5ba6", "#1f7a47"]


def _env_value(key):
    """Read a credential from the environment, falling back to a local .env file."""
    if os.environ.get(key):
        return os.environ[key]
    env_file = config.ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return None


def kite_auth_status() -> dict:
    """Whether a Kite access token is present and valid for today (local login).

    Returns ``authed`` plus the ``api_key`` and ``login_url`` needed to log in.
    """
    from data.kite_source import TOKEN_PATH

    authed = False
    if TOKEN_PATH.exists():
        try:
            tok = json.loads(TOKEN_PATH.read_text())
            authed = tok.get("generated_on") == datetime.date.today().isoformat()
        except (ValueError, OSError):
            authed = False
    api_key = _env_value("KITE_API_KEY")
    login_url = (f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
                 if api_key else None)
    return {"authed": authed, "name": "Kamal", "api_key": api_key,
            "login_url": login_url}


# --- formatters -------------------------------------------------------------

def _fmt_pct(v):
    return "—" if v is None or pd.isna(v) else f"{float(v):.2f}%"


def _fmt_num(v):
    return "—" if v is None or pd.isna(v) else f"{float(v):.2f}"


def _fmt_int(v):
    return "—" if v is None or pd.isna(v) else f"{int(float(v))}"


def _fmt_money(v):
    return "—" if v is None or pd.isna(v) else f"{float(v):,.0f}"


def run_label(params_json, instrument=None) -> str:
    """Short label of the params that vary (skip the constant lot size).

    When ``instrument`` is given it's prefixed so labels stay unique across
    instruments that share params (e.g. nifty vs banknifty at n=9).
    """
    try:
        d = json.loads(params_json)
    except (TypeError, ValueError):
        return ""
    parts = [f"{k}={v}" for k, v in d.items() if k != "lot"]
    body = ", ".join(parts) if parts else "default"
    return f"{instrument} · {body}" if instrument else body


def _group_by_instrument(runs: pd.DataFrame) -> pd.DataFrame:
    """Order rows by instrument (config order) so a cluster groups by index,
    preserving each group's existing order (newest-first from list_runs)."""
    if "instrument" not in runs.columns:
        return runs
    order = {name: i for i, name in enumerate(config.INSTRUMENTS)}
    key = runs["instrument"].map(lambda x: order.get(x, len(order)))
    return runs.assign(_io=key).sort_values("_io", kind="stable").drop(columns="_io")


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
    runs = _group_by_instrument(runs)
    pkeys = _param_keys(runs)
    rows = []
    for _, r in runs.iterrows():
        p = json.loads(r["params_json"])
        stats = json.loads(r["stats_json"]) if isinstance(r["stats_json"], str) else {}
        final_eq = r["final_equity"]
        pnl = None if pd.isna(final_eq) else final_eq - config.DEFAULT_CASH
        row = {"Instrument": str(r.get("instrument", "—")).upper()}
        row.update({k: p.get(k, "—") for k in pkeys})
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
    cols = ["Instrument"] + pkeys + ["CAGR", "Return", "Total PnL", "Win%", "PF",
                                     "OOS PF", "Max DD", "Sharpe", "Trades", "Period"]
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
        base = run_label(r["params_json"], r.get("instrument")) or str(rid)[:8]
        used[base] = used.get(base, 0) + 1
        label = base if used[base] == 1 else f"{base} (#{used[base]})"
        data[label] = [_fmt_stat(k, stats.get(k)) for k in _FULL_STATS]
    return pd.DataFrame(data)


def comparison_html(df) -> str:
    """Comparison table as HTML so each metric name carries a hover tooltip.

    ``st.table``/``st.dataframe`` can't tooltip individual cells, so the Metric
    column is rendered with ``title=`` help from the shared glossary — matching
    the static site's hover behaviour.
    """
    import html as _html

    cols = list(df.columns)
    head = "".join(f"<th>{_html.escape(str(c))}</th>" for c in cols)
    body = []
    for _, row in df.iterrows():
        cells = []
        for i, c in enumerate(cols):
            val = _html.escape(str(row[c]))
            tip = glossary.help_for(str(row[c])) if i == 0 else None
            attr = f' class="tip" title="{_html.escape(tip)}"' if tip else ""
            cells.append(f"<td{attr}>{val}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return (f'<table class="cmp"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>')


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
        /* show full param labels in the run multiselect chips (no truncation) */
        [data-baseweb="tag"] { max-width: none !important; }
        [data-baseweb="tag"] span { max-width: none !important; text-overflow: clip !important; }
        /* HTML comparison table (Full metrics) with per-metric hover tooltips */
        table.cmp { border-collapse: collapse; width: 100%; font-size: 13px;
            font-variant-numeric: tabular-nums; }
        table.cmp th, table.cmp td { padding: 6px 13px; text-align: right;
            white-space: nowrap; border-bottom: 1px solid #e9e7e1;
            font-family: 'IBM Plex Mono', monospace; }
        table.cmp th { text-transform: uppercase; font-size: 11px; letter-spacing: .04em;
            color: #6c7178; background: #f4f2ec; font-family: 'IBM Plex Sans', sans-serif; }
        table.cmp th:first-child, table.cmp td:first-child { text-align: left;
            font-family: 'IBM Plex Sans', sans-serif; font-weight: 500; }
        table.cmp td.tip { cursor: help;
            text-decoration: underline dotted #d8d5cd; text-underline-offset: 3px; }
        table.cmp td.tip:hover { text-decoration-color: #126b62; color: #126b62; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # Header: title + Kite login status (local only). "Hi Kamal" when a token is
    # available, otherwise a login link + a box to paste the request_token.
    head_l, head_r = st.columns([5, 3])
    head_l.title("Backtests")
    with head_r:
        _auth = kite_auth_status()
        if _auth["authed"]:
            st.markdown(
                "<div style='text-align:right;padding-top:26px'>Hi "
                f"<b>{_auth['name']}</b> &nbsp;<span style='color:#1a7a47'>●</span> "
                "<span style='color:#6c7178'>Kite connected</span></div>",
                unsafe_allow_html=True,
            )
        elif _auth["login_url"]:
            st.markdown(
                "<div style='text-align:right;padding-top:8px'>"
                f"<a href='{_auth['login_url']}' target='_blank'>🔑 Log in to Kite</a>"
                "</div>", unsafe_allow_html=True,
            )
            _rt = st.text_input("request_token", label_visibility="collapsed",
                                placeholder="paste request_token after login")
            if st.button("Connect", use_container_width=True) and _rt:
                try:
                    from kiteconnect import KiteConnect
                    from data.kite_source import TOKEN_PATH

                    _kite = KiteConnect(api_key=_auth["api_key"])
                    _data = _kite.generate_session(
                        _rt.strip(), api_secret=_env_value("KITE_API_SECRET"))
                    TOKEN_PATH.write_text(json.dumps({
                        "access_token": _data["access_token"],
                        "user_id": _data.get("user_id"),
                        "generated_on": datetime.date.today().isoformat(),
                    }, indent=2))
                    st.rerun()
                except Exception as err:  # surface auth failures to the user
                    st.error(f"Login failed: {err}")
        else:
            st.caption("Set KITE_API_KEY (env or .env) to enable Kite login.")

    runs = persistence.list_runs()  # newest first

    if runs.empty:
        st.info(
            "No runs yet. Run e.g.\n\n"
            "`python run.py turnaround_tuesday --instrument nifty "
            "--start 2015-01-01`\n\n"
            "to record your first backtest."
        )
        st.stop()

    # Cluster by strategy.
    strategy = st.selectbox("Strategy", sorted(runs["strategy"].unique()))
    sub = runs[runs["strategy"] == strategy].reset_index(drop=True)

    st.subheader(f"{strategy} — {len(sub)} run(s)")
    try:
        _src = strategies.get(strategy).source
    except KeyError:
        _src = None
    if _src:
        st.markdown(f"Source: [{_src}]({_src})")
    _runs_tbl = build_runs_table(sub)
    st.dataframe(_runs_tbl, width="stretch", hide_index=True,
                 column_config=_column_config(_runs_tbl.columns))
    st.caption(
        "Hover any column header for what it means. CAGR is annualized return on the "
        "fixed cash base (10M); **Total PnL** is per **one futures lot** of that index "
        "(Nifty 65, BankNifty 30, Midcap 120 units/lot). Compare **Total PnL** and "
        "**PF / OOS PF** across rows. Each row is one instrument × parameter variation."
    )

    # Build unique labels -> run_id for selection.
    label_to_id = {}
    for _, r in sub.iterrows():
        base = run_label(r["params_json"], r.get("instrument")) or str(r["run_id"])[:8]
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
    st.markdown(comparison_html(build_comparison_table(sub, picked_ids)),
                unsafe_allow_html=True)
    st.caption("Hover a metric name for a plain-English description.")

    st.subheader("Equity curves (% return from start)")
    import altair as alt

    frames = []
    for p in picked:
        try:
            s = equity_return_curve(load_equity_series(label_to_id[p]))
        except (KeyError, FileNotFoundError):
            continue
        frames.append(pd.DataFrame({"Date": s.index, "Return %": s.to_numpy(), "Run": p}))
    if frames:
        cdf = pd.concat(frames, ignore_index=True)
        # Crosshair: as the cursor moves, snap to the nearest date and draw a
        # vertical rule + a horizontal rule at each run's value, with the values
        # labelled so the readout stays visible the whole time (not only on hover).
        nearest = alt.selection_point(nearest=True, on="pointermove",
                                      fields=["Date"], empty=False)
        base = alt.Chart(cdf).encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Return %:Q", title="% return from start"),
            # labelLimit large so long param labels never truncate.
            color=alt.Color("Run:N", title=None, scale=alt.Scale(range=PALETTE),
                            legend=alt.Legend(orient="top", labelLimit=1000,
                                              symbolType="stroke", columns=1)),
        )
        lines = base.mark_line(strokeWidth=1.5)
        selectors = base.mark_point(opacity=0).add_params(nearest)
        vrule = alt.Chart(cdf).mark_rule(color="#9aa0a6", strokeDash=[4, 3]).encode(
            x="Date:T").transform_filter(nearest)
        hrule = base.mark_rule(strokeDash=[2, 2], opacity=0.55).encode(
            y="Return %:Q").transform_filter(nearest)
        points = base.mark_point(size=55, filled=True).encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0)),
            tooltip=[alt.Tooltip("Run:N", title="Run"),
                     alt.Tooltip("Date:T", title="Date"),
                     alt.Tooltip("Return %:Q", format="+.2f")],
        )
        labels = base.mark_text(align="left", dx=7, dy=-7, font="IBM Plex Mono",
                                fontSize=11).encode(
            text=alt.condition(nearest, alt.Text("Return %:Q", format="+.2f"),
                               alt.value(" ")),
        )
        chart = alt.layer(lines, selectors, vrule, hrule, points, labels).properties(
            width="container", height=380)
        st.altair_chart(chart)

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
            _lot = json.loads(row["params_json"]).get("lot", "?")
            st.caption(
                f"{row['slippage'] * 100:.2f}% slippage applied per fill; commission "
                f"not modeled. PnL is per **1 {row['instrument']} futures lot** "
                f"({_lot} units)."
            )
            _trades_tbl = build_trades_table(artifacts["trades"])
            st.dataframe(_trades_tbl, width="stretch", hide_index=True,
                         column_config=_column_config(_trades_tbl.columns))
        except (KeyError, FileNotFoundError):
            st.warning("Trades for this run are unavailable.")
    else:
        st.caption("Select a single run to also see its trade list.")
