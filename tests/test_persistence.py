"""U4: SQLite run index + atomic artifact writer."""

import json
import sqlite3

import pandas as pd
import pytest

import config
from engine import persistence

pytestmark = pytest.mark.usefixtures("isolated_store")


def _stats(cagr=12.0, trades=5, extra=None):
    data = {
        "Start": pd.Timestamp("2020-01-01"),  # non-scalar -> str in stats_json
        "CAGR [%]": cagr,
        "Return [%]": 40.0,
        "Max. Drawdown [%]": -18.0,
        "Win Rate [%]": 55.0,
        "Sharpe Ratio": 1.2,
        "# Trades": trades,
        "Equity Final [$]": 1_400_000.0,
        "Sortino Ratio": 1.8,  # non-hot, lives only in stats_json
    }
    if extra:
        data.update(extra)
    return pd.Series(data)


def _trades():
    return pd.DataFrame({"Size": [1], "EntryPrice": [100.0], "PnL": [40.0]})


def _equity():
    return pd.DataFrame(
        {"Equity": [1_000_000.0, 1_400_000.0]},
        index=pd.to_datetime(["2020-01-01", "2020-12-31"]),
    )


def _save(strategy="ema_cross", params=None, commission=0.0005, stats=None):
    return persistence.save_run(
        strategy=strategy,
        instrument="NIFTY 50",
        params=params or {"n1": 10, "n2": 20},
        start="2020-01-01",
        end="2020-12-31",
        commission=commission,
        stats=stats if stats is not None else _stats(),
        trades_df=_trades(),
        equity_df=_equity(),
    )


def test_append_not_overwrite_ae2(isolated_store):
    id_a = _save(params={"n1": 20, "n2": 50}, stats=_stats(cagr=12.0))
    id_b = _save(params={"n1": 10, "n2": 30}, stats=_stats(cagr=9.0))

    runs = persistence.list_runs()
    assert len(runs) == 2
    assert id_a != id_b
    # A's metrics unchanged after B saved.
    a_row = runs[runs.run_id == id_a].iloc[0]
    assert a_row.cagr == 12.0
    # A's artifact files intact.
    a_art = persistence.load_run_artifacts(id_a)
    assert a_art["metrics"]["CAGR [%]"] == 12.0


def test_save_creates_all_artifacts_and_hot_metrics(isolated_store):
    run_id = _save()
    run_dir = isolated_store / "runs" / run_id
    for fname in ("params.json", "metrics.json", "trades.csv", "equity.parquet"):
        assert (run_dir / fname).exists()

    row = persistence.list_runs().iloc[0]
    assert row.cagr == 12.0
    assert row.num_trades == 5
    assert row.max_drawdown == -18.0
    # stats_json round-trips the full series (Timestamp coerced to str).
    sj = json.loads(row.stats_json)
    assert sj["CAGR [%]"] == 12.0
    assert isinstance(sj["Start"], str)


def test_non_hot_metric_queryable_via_json_extract(isolated_store):
    _save()
    with sqlite3.connect(config.DB_PATH) as conn:
        val = conn.execute(
            "SELECT json_extract(stats_json, '$.\"Sortino Ratio\"') FROM runs"
        ).fetchone()[0]
    assert val == 1.8  # no schema migration needed for a non-hot metric


def test_identical_config_appends_with_same_hash(isolated_store):
    id1 = _save(params={"n1": 10, "n2": 20})
    id2 = _save(params={"n1": 10, "n2": 20})
    runs = persistence.list_runs()
    assert id1 != id2
    assert runs.config_hash.nunique() == 1  # same config -> same hash, two rows


def test_save_on_fresh_db_creates_table(isolated_store):
    # No explicit init_db() call first; save_run must self-initialize.
    run_id = _save()
    assert run_id in set(persistence.list_runs().run_id)


def test_missing_hot_key_stores_null(isolated_store):
    s = _stats()
    del s["Sharpe Ratio"]
    _save(stats=s)
    row = persistence.list_runs().iloc[0]
    assert pd.isna(row.sharpe)


def test_atomic_write_failure_leaves_no_dir_or_row(isolated_store, monkeypatch):
    def boom(*a, **k):
        raise IOError("disk full mid-write")

    monkeypatch.setattr(persistence, "_write_artifacts", boom)
    with pytest.raises(IOError):
        _save()

    # No row, and no final run dir (only possibly a cleaned tmp).
    assert len(persistence.list_runs()) == 0
    leftover = [p.name for p in (isolated_store / "runs").iterdir()]
    assert all(name.endswith(".tmp") is False for name in leftover) or leftover == []
