"""Run index (SQLite) and per-run artifact storage.

Every run appends one row to a single ``runs`` table — never overwriting prior runs
(R5). Hot metrics are denormalized into columns so the dashboard table is one fast
query; the full stats series is also stored as ``stats_json`` so any other native
metric (Sortino, Profit Factor, ...) stays queryable via ``json_extract`` with no
schema migration.

Artifacts are written atomically: into a temp dir, then ``os.rename``d into place,
then the row is inserted. A crash leaves no partial dir and no row pointing at
missing files.
"""

import datetime as _dt
import hashlib
import json
import os
import shutil
import sqlite3
import uuid

import pandas as pd

import config
from engine import oos

# stats keys we denormalize into columns -> (column name, python type)
_HOT_METRICS = {
    "CAGR [%]": ("cagr", float),
    "Return [%]": ("return_pct", float),
    "Max. Drawdown [%]": ("max_drawdown", float),  # stored as reported (negative)
    "Win Rate [%]": ("win_rate", float),
    "Sharpe Ratio": ("sharpe", float),
    "# Trades": ("num_trades", int),
    "Equity Final [$]": ("final_equity", float),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    strategy     TEXT NOT NULL,
    instrument   TEXT NOT NULL,
    params_json  TEXT NOT NULL,
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    slippage     REAL NOT NULL,
    config_hash  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    artifact_dir TEXT NOT NULL,
    cagr         REAL,
    return_pct   REAL,
    max_drawdown REAL,
    win_rate     REAL,
    sharpe       REAL,
    num_trades   INTEGER,
    final_equity REAL,
    stats_json   TEXT NOT NULL,
    split_json   TEXT
)
"""


def _connect():
    return sqlite3.connect(config.DB_PATH)


def init_db():
    """Create the runs table if absent and apply column migrations. Idempotent."""
    with _connect() as conn:
        conn.execute(_SCHEMA)
        # Lightweight forward-migration for DBs created before a column existed.
        existing = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
        if "split_json" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN split_json TEXT")


def config_hash(strategy, params, instrument, start, end, slippage) -> str:
    """Stable hash of the full set of result-affecting inputs (R9)."""
    payload = json.dumps(
        {
            "strategy": strategy,
            "params": params,
            "instrument": instrument,
            "start": str(start),
            "end": str(end),
            "slippage": slippage,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _stats_to_dict(stats) -> dict:
    """JSON-safe dict of the stats series, minus the internal object fields."""
    out = {}
    for key, value in stats.items():
        if key.startswith("_"):
            continue
        if isinstance(value, (int, float, str, bool)) or value is None:
            out[key] = value
        else:  # Timestamp, Timedelta, numpy scalars -> str
            out[key] = str(value)
    return out


def _hot_values(stats) -> dict:
    values = {}
    for key, (col, cast) in _HOT_METRICS.items():
        raw = stats.get(key) if hasattr(stats, "get") else None
        try:
            values[col] = None if raw is None or pd.isna(raw) else cast(raw)
        except (TypeError, ValueError):
            values[col] = None
    return values


def _write_artifacts(tmp_dir, params, stats_dict, trades_df, equity_df):
    os.makedirs(tmp_dir, exist_ok=True)
    with open(os.path.join(tmp_dir, "params.json"), "w") as fh:
        json.dump(params, fh, indent=2, default=str)
    with open(os.path.join(tmp_dir, "metrics.json"), "w") as fh:
        json.dump(stats_dict, fh, indent=2, default=str)
    trades_df.to_csv(os.path.join(tmp_dir, "trades.csv"), index=False)
    equity_df.to_parquet(os.path.join(tmp_dir, "equity.parquet"))


def save_run(
    strategy, instrument, params, start, end, slippage,
    stats, trades_df, equity_df,
):
    """Persist one run: write artifacts atomically, then insert the index row.

    Returns the generated ``run_id``. Appends a new row even for an identical
    config (never overwrites).
    """
    init_db()

    now = _dt.datetime.now()
    run_id = f"{strategy}_{now:%Y%m%d%H%M%S}_{uuid.uuid4().hex[:6]}"
    chash = config_hash(strategy, params, instrument, start, end, slippage)
    stats_dict = _stats_to_dict(stats)

    final_dir = config.RUNS_DIR / run_id
    tmp_dir = config.RUNS_DIR / f".{run_id}.tmp"
    artifact_rel = os.path.relpath(final_dir, config.ROOT)

    try:
        _write_artifacts(tmp_dir, params, stats_dict, trades_df, equity_df)
        os.rename(tmp_dir, final_dir)
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise  # no row inserted, no partial dir left behind

    row = {
        "run_id": run_id,
        "strategy": strategy,
        "instrument": instrument,
        "params_json": json.dumps(params, default=str),
        "start_date": str(start),
        "end_date": str(end),
        "slippage": float(slippage),
        "config_hash": chash,
        "created_at": now.isoformat(),
        "artifact_dir": artifact_rel,
        "stats_json": json.dumps(stats_dict, default=str),
        "split_json": json.dumps(
            oos.split_summary(trades_df, start, end, config.DEFAULT_OOS_SPLIT)
        ),
        **_hot_values(stats),
    }
    cols = ", ".join(row)
    placeholders = ", ".join(f":{c}" for c in row)
    with _connect() as conn:
        conn.execute(f"INSERT INTO runs ({cols}) VALUES ({placeholders})", row)

    return run_id


def list_runs() -> pd.DataFrame:
    """All runs as a DataFrame, newest first."""
    init_db()
    with _connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM runs ORDER BY created_at DESC", conn
        )


def delete_run(run_id):
    """Remove a run's index row and its artifact directory. Raises if unknown."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "SELECT artifact_dir FROM runs WHERE run_id = ?", (run_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"unknown run_id {run_id!r}")
        conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
    shutil.rmtree(config.ROOT / row[0], ignore_errors=True)


def load_run_artifacts(run_id) -> dict:
    """Load a run's full metrics, trades, and equity curve for the detail view."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "SELECT artifact_dir FROM runs WHERE run_id = ?", (run_id,)
        )
        result = cur.fetchone()
    if result is None:
        raise KeyError(f"unknown run_id {run_id!r}")
    run_dir = config.ROOT / result[0]
    with open(run_dir / "metrics.json") as fh:
        metrics = json.load(fh)
    trades = pd.read_csv(run_dir / "trades.csv")
    equity = pd.read_parquet(run_dir / "equity.parquet")
    return {"metrics": metrics, "trades": trades, "equity": equity}
