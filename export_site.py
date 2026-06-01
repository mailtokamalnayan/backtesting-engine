"""Export a static, interactive snapshot of all saved runs for hosting.

Reads results/index.sqlite + artifacts and writes site/data.json, which the static
frontend in site/ renders entirely in the browser (no server). Run locally after
backtesting, then deploy the site/ folder to Vercel:

    python export_site.py
    cd site && vercel --prod        # or connect the repo, root dir = site/

Only backtest results are exported — no API keys, no raw data. Equity curves are
downsampled (daily), so the whole snapshot stays light.
"""

import datetime as dt
import json
from pathlib import Path

import dashboard
import glossary
import strategies
from engine import persistence

SITE = Path(__file__).resolve().parent / "site"

# "# Trades" -> "Trades" so it isn't mistaken for a heading in the UI.
STAT_LABELS = ["Trades" if k == "# Trades" else k for k in dashboard._FULL_STATS]


def _equity_points(run_id):
    series = dashboard.equity_return_curve(dashboard.load_equity_series(run_id))
    return [[ts.strftime("%Y-%m-%d"), round(float(v), 3)] for ts, v in series.items()]


def _run_entry(r):
    stats = json.loads(r["stats_json"]) if isinstance(r["stats_json"], str) else {}
    split_raw = r.get("split_json")
    split = json.loads(split_raw) if isinstance(split_raw, str) and split_raw else {}
    try:
        trades_df = persistence.load_run_artifacts(r["run_id"])["trades"]
        trades = dashboard.build_trades_table(trades_df).to_dict("records")
        equity = _equity_points(r["run_id"])
    except Exception:
        trades, equity = [], []
    full_stats = dict(zip(
        STAT_LABELS,
        [dashboard._fmt_stat(k, stats.get(k)) for k in dashboard._FULL_STATS],
    ))
    return {
        "run_id": r["run_id"],
        "instrument": r.get("instrument"),
        "params": json.loads(r["params_json"]),
        "full_stats": full_stats,
        "oos": dashboard.build_oos_table(split).to_dict("records") if split else [],
        "equity": equity,
        "trades": trades,
    }


def build_data() -> dict:
    runs = persistence.list_runs()
    strategies_out = {}
    for strat in sorted(runs["strategy"].unique()):
        sub = runs[runs["strategy"] == strat].reset_index(drop=True)
        table = dashboard.build_runs_table(sub)
        entries, used = [], {}
        for _, r in sub.iterrows():
            base = (dashboard.run_label(r["params_json"], r.get("instrument"))
                    or str(r["run_id"])[:8])
            used[base] = used.get(base, 0) + 1
            label = base if used[base] == 1 else f"{base} (#{used[base]})"
            entry = _run_entry(r)
            entry["label"] = label
            entries.append(entry)
        try:
            source = strategies.get(strat).source
        except KeyError:
            source = None
        strategies_out[strat] = {
            "source": source,
            "columns": list(table.columns),
            "rows": table.to_dict("records"),
            "runs": entries,
        }
    return {
        "generated_at": dt.date.today().isoformat(),
        "stat_labels": STAT_LABELS,
        "glossary": glossary.COLUMN_HELP,  # column/metric hover help
        "strategies": strategies_out,
    }


def export():
    data = build_data()
    SITE.mkdir(exist_ok=True)
    (SITE / "data.json").write_text(json.dumps(data))
    n_runs = sum(len(s["runs"]) for s in data["strategies"].values())
    print(f"wrote {SITE / 'data.json'} — "
          f"{len(data['strategies'])} strategies, {n_runs} runs")


if __name__ == "__main__":
    export()
