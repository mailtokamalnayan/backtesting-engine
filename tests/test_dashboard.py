"""Dashboard pure helpers (Streamlit shell verified manually)."""

import datetime as dt

import pandas as pd
import pytest

import config
import dashboard
from data.source import DataSource
from engine.runner import run_backtest

pytestmark = pytest.mark.usefixtures("isolated_store")


def _runs_frame():
    return pd.DataFrame([
        {"run_id": "b", "strategy": "turnaround_tuesday",
         "instrument": "nifty", "params_json": '{"n": 9, "lot": 65, "hold_days": 2}',
         "start_date": "2015-01-01", "end_date": "2026-05-30",
         "cagr": 0.31, "return_pct": 2.4, "max_drawdown": -1.2, "win_rate": 56.5,
         "sharpe": 0.15, "num_trades": 232, "final_equity": 10_428_474.0,
         "stats_json": '{"Profit Factor": 1.76, "CAGR [%]": 0.31, "# Trades": 232}',
         "split_json": '{"out_sample": {"profit_factor": 1.05}}',
         "created_at": "2026-05-30T10:01:00"},
        {"run_id": "a", "strategy": "turnaround_tuesday",
         "instrument": "nifty", "params_json": '{"n": 50, "lot": 65, "hold_days": 2}',
         "start_date": "2015-01-01", "end_date": "2026-05-30",
         "cagr": 0.30, "return_pct": 2.0, "max_drawdown": -0.6, "win_rate": 56.8,
         "sharpe": 0.20, "num_trades": 190, "final_equity": 10_420_171.0,
         "stats_json": '{"Profit Factor": 1.58, "CAGR [%]": 0.30, "# Trades": 190}',
         "split_json": '{"out_sample": {"profit_factor": 1.79}}',
         "created_at": "2026-05-30T10:00:00"},
    ])


def test_run_label_skips_lot():
    assert dashboard.run_label('{"n": 9, "lot": 65, "hold_days": 2}') == "n=9, hold_days=2"
    assert dashboard.run_label('{}') == "default"


def test_build_runs_table_breaks_params_into_columns():
    table = dashboard.build_runs_table(_runs_frame())
    # Param keys become their own columns.
    for col in ("n", "lot", "hold_days", "CAGR", "Total PnL", "PF", "OOS PF"):
        assert col in table.columns
    first = table.iloc[0]
    assert first["n"] == 9
    assert first["CAGR"] == "0.31%"
    assert first["PF"] == "1.76"          # from stats_json
    assert first["OOS PF"] == "1.05"      # from split_json
    assert first["Total PnL"] == "428,474"  # final_equity - 10M cash base
    assert first["Trades"] == "232"


def test_build_runs_table_empty():
    assert dashboard.build_runs_table(pd.DataFrame()).empty


def test_build_comparison_table_side_by_side():
    runs = _runs_frame()
    table = dashboard.build_comparison_table(runs, ["b", "a"])
    assert table.columns[0] == "Metric"
    # Each run is a column, labelled by its varying params.
    assert "n=9, hold_days=2" in table.columns
    assert "n=50, hold_days=2" in table.columns
    # Full stat set surfaced, including CAGR and Profit Factor.
    metrics = list(table["Metric"])
    assert "CAGR [%]" in metrics and "Profit Factor" in metrics
    # "# Trades" relabelled to "Trades" so st.table doesn't render it as an H1.
    assert "Trades" in metrics and "# Trades" not in metrics
    pf_row = table[table["Metric"] == "Profit Factor"].iloc[0]
    assert pf_row["n=9, hold_days=2"] == "1.76"


def test_build_comparison_table_dedupes_labels():
    runs = pd.DataFrame([
        {"run_id": "x", "params_json": '{"n": 9, "lot": 65}',
         "stats_json": '{"Profit Factor": 1.5}'},
        {"run_id": "y", "params_json": '{"n": 9, "lot": 65}',
         "stats_json": '{"Profit Factor": 1.6}'},
    ])
    table = dashboard.build_comparison_table(runs, ["x", "y"])
    assert "n=9" in table.columns
    assert "n=9 (#2)" in table.columns  # second identical label disambiguated


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


def test_downsample_equity_shrinks_large_minute_curve():
    idx = pd.date_range("2024-01-01 09:15", periods=7200, freq="min")  # ~5 days
    series = pd.Series(range(7200), index=idx, dtype=float)
    out = dashboard.downsample_equity(series, max_points=2000)
    assert len(out) <= 2000
    assert isinstance(out, pd.Series)


def test_downsample_equity_passes_small_curve_through():
    series = pd.Series(range(500), dtype=float)
    out = dashboard.downsample_equity(series, max_points=2000)
    assert len(out) == 500


def test_equity_return_curve_starts_at_zero():
    series = pd.Series([1_000_000.0, 1_100_000.0, 1_050_000.0])
    out = dashboard.equity_return_curve(series)
    assert out.iloc[0] == 0.0                 # begins at 0%
    assert out.iloc[1] == pytest.approx(10.0)  # +10%
    assert out.iloc[2] == pytest.approx(5.0)   # +5%


def test_build_trades_table_formats_sorts_latest_first():
    # Shape mimics trades.csv after round-trip: string times/duration.
    trades = pd.DataFrame({
        "EntryTime": ["2024-02-05 15:25:00", "2024-02-12 15:25:00"],
        "ExitTime": ["2024-02-06 09:45:00", "2024-02-13 09:45:00"],
        "Duration": ["0 days 18:20:00", "0 days 18:20:00"],
        "EntryPrice": [21900.5, 22100.0],
        "ExitPrice": [21950.0, 22050.0],
        "PnL": [3217.5, -3250.0],
        "ReturnPct": [0.00226, -0.00226],
    })
    table = dashboard.build_trades_table(trades)
    assert list(table.columns) == dashboard.TRADE_COLUMNS
    assert "Feb 12" in table.iloc[0]["Entry"]   # latest entry first
    assert table.iloc[0]["Entry"].endswith("03:25pm")
    assert table.iloc[0]["Exit"].endswith("09:45am")
    assert table.iloc[0]["Duration"] == "18h 20m"
    assert table.iloc[0]["PnL"] == "-3,250"
    assert table.iloc[0]["Return %"] == "-0.23%"


def test_build_trades_table_empty_returns_columns():
    out = dashboard.build_trades_table(pd.DataFrame())
    assert list(out.columns) == dashboard.TRADE_COLUMNS
    assert len(out) == 0


def test_build_oos_table_formats_both_segments():
    split = {
        "split_date": "2022-01-01", "fraction": 0.7,
        "in_sample": {"trades": 162, "total_pnl": 300000.0, "avg_pnl": 1851.0,
                      "win_rate": 56.5, "profit_factor": 1.8},
        "out_sample": {"trades": 70, "total_pnl": 128000.0, "avg_pnl": 1828.0,
                       "win_rate": 55.0, "profit_factor": 1.7},
    }
    table = dashboard.build_oos_table(split)
    assert list(table.columns) == ["Metric", "In-Sample", "Out-of-Sample"]
    vals = dict(zip(table["Metric"], table["Out-of-Sample"]))
    assert vals["Trades"] == "70"
    assert vals["Total PnL"] == "128,000"
    assert vals["Win Rate"] == "55.00%"
    assert vals["Profit Factor"] == "1.70"


def test_build_oos_table_handles_empty_segment():
    split = {"in_sample": {"trades": 0, "total_pnl": 0.0, "avg_pnl": None,
                           "win_rate": None, "profit_factor": None},
             "out_sample": {}}
    table = dashboard.build_oos_table(split)
    assert table.iloc[0]["In-Sample"] == "0"
    assert table.iloc[2]["In-Sample"] == "—"  # avg_pnl None
