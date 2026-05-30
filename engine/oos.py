"""In-sample / out-of-sample split of a run's trades.

Every run is partitioned by trade entry date into an in-sample (older) segment and
an out-of-sample (most-recent) segment, so an edge can be checked on data the
parameters were not chosen on. Summary stats per segment are derived from the trade
list alone (no second backtest), which is enough to answer "does it hold out of
sample?": trade count, total/avg PnL, win rate, profit factor.
"""

import pandas as pd

_EMPTY_SEG = {"trades": 0, "total_pnl": 0.0, "avg_pnl": None,
              "win_rate": None, "profit_factor": None}


def _segment_stats(t: pd.DataFrame) -> dict:
    if t.empty:
        return dict(_EMPTY_SEG)
    pnl = t["PnL"]
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    return {
        "trades": int(len(t)),
        "total_pnl": float(pnl.sum()),
        "avg_pnl": float(pnl.mean()),
        "win_rate": float((pnl > 0).mean() * 100),
        "profit_factor": float(wins / losses) if losses else None,
    }


def split_summary(trades_df: pd.DataFrame, start, end, fraction) -> dict:
    """Split trades at ``start + fraction*(end-start)``; summarize each segment.

    ``start``/``end`` may be dates or ISO strings. Robust to a trades frame missing
    ``EntryTime`` or being empty (returns empty segments).
    """
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    split_ts = start_ts + (end_ts - start_ts) * fraction
    summary = {
        "split_date": split_ts.date().isoformat(),
        "fraction": fraction,
        "in_sample": dict(_EMPTY_SEG),
        "out_sample": dict(_EMPTY_SEG),
    }
    if trades_df is None or trades_df.empty or "EntryTime" not in trades_df.columns:
        return summary
    entry = pd.to_datetime(trades_df["EntryTime"])
    summary["in_sample"] = _segment_stats(trades_df[entry < split_ts])
    summary["out_sample"] = _segment_stats(trades_df[entry >= split_ts])
    return summary
