"""U7: dashboard pure helpers (Streamlit shell verified manually)."""

import datetime as dt

import pandas as pd
import pytest

import dashboard
from data.source import DataSource
from engine.runner import run_backtest

pytestmark = pytest.mark.usefixtures("isolated_store")


def _runs_frame():
    return pd.DataFrame([
        {"run_id": "b", "strategy": "ema_cross", "instrument": "nifty",
         "params_json": '{"n1": 10, "n2": 30}', "cagr": 11.8, "return_pct": 30.0,
         "max_drawdown": -22.0, "win_rate": 50.0, "sharpe": 1.05, "num_trades": 8,
         "created_at": "2026-05-30T10:01:00"},
        {"run_id": "a", "strategy": "ema_cross", "instrument": "banknifty",
         "params_json": '{"n1": 20, "n2": 50}', "cagr": 14.2, "return_pct": 42.0,
         "max_drawdown": -18.0, "win_rate": 55.0, "sharpe": 1.23, "num_trades": 5,
         "created_at": "2026-05-30T10:00:00"},
    ])


def test_build_table_formats_and_preserves_order():
    table = dashboard.build_table(_runs_frame())
    assert list(table.columns) == dashboard.TABLE_COLUMNS
    assert table.iloc[0]["Run ID"] == "b"  # input order preserved
    assert table.iloc[0]["CAGR"] == "11.80%"
    assert table.iloc[1]["Max DD"] == "-18.00%"   # negative drawdown shown as-is
    assert table.iloc[1]["Sharpe"] == "1.23"
    assert table.iloc[0]["Params"] == "n1=10,n2=30"
    assert table.iloc[1]["# Trades"] == 5


def test_build_table_empty_returns_columns_no_crash():
    table = dashboard.build_table(pd.DataFrame())
    assert list(table.columns) == dashboard.TABLE_COLUMNS
    assert len(table) == 0


def test_filter_runs_by_strategy_and_instrument():
    runs = _runs_frame()
    assert len(dashboard.filter_runs(runs, instrument="nifty")) == 1
    assert len(dashboard.filter_runs(runs, strategy="All", instrument="All")) == 2
    assert len(dashboard.filter_runs(runs, strategy="ema_cross")) == 2


def test_nan_metric_renders_dash():
    runs = _runs_frame()
    runs.loc[0, "sharpe"] = float("nan")
    table = dashboard.build_table(runs)
    assert table.iloc[0]["Sharpe"] == "—"


def test_load_equity_series_roundtrip(synthetic_ohlc):
    class _Fixed(DataSource):
        def get_daily(self, symbol, start, end):
            return synthetic_ohlc

    run_id = run_backtest("ema_cross", "nifty", dt.date(2020, 1, 1),
                          dt.date(2020, 12, 31), source=_Fixed())
    series = dashboard.load_equity_series(run_id)
    assert isinstance(series, pd.Series)
    assert len(series) > 0


def test_load_equity_series_unknown_run_raises():
    with pytest.raises(KeyError):
        dashboard.load_equity_series("does_not_exist")
