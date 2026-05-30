"""In-sample / out-of-sample split summary."""

import pandas as pd

from engine.oos import split_summary


def _trades():
    return pd.DataFrame({
        "EntryTime": ["2016-06-06", "2018-06-04", "2020-06-01",  # in-sample
                      "2023-06-05", "2024-06-03"],                # out-of-sample
        "PnL": [100.0, -50.0, 200.0, 300.0, -100.0],
    })


def test_split_partitions_by_entry_date():
    s = split_summary(_trades(), "2015-01-01", "2025-01-01", 0.7)
    assert s["split_date"].startswith("2022-01")  # 70% of 10 years
    assert s["in_sample"]["trades"] == 3
    assert s["in_sample"]["total_pnl"] == 250.0     # 100-50+200
    assert s["out_sample"]["trades"] == 2
    assert s["out_sample"]["total_pnl"] == 200.0    # 300-100


def test_split_segment_stats():
    s = split_summary(_trades(), "2015-01-01", "2025-01-01", 0.7)
    assert round(s["in_sample"]["win_rate"], 1) == 66.7      # 2 of 3
    assert s["in_sample"]["profit_factor"] == 6.0           # 300 / 50
    assert s["out_sample"]["win_rate"] == 50.0
    assert s["out_sample"]["profit_factor"] == 3.0          # 300 / 100


def test_split_handles_empty_and_missing_entrytime():
    empty = split_summary(pd.DataFrame(), "2015-01-01", "2025-01-01", 0.7)
    assert empty["in_sample"]["trades"] == 0
    assert empty["out_sample"]["trades"] == 0

    no_entry = split_summary(pd.DataFrame({"PnL": [1.0]}),
                             "2015-01-01", "2025-01-01", 0.7)
    assert no_entry["in_sample"]["trades"] == 0
