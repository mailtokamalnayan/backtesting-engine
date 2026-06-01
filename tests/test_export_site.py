"""Static-site exporter produces a valid data bundle."""

import datetime as dt
import json

import pytest

import export_site
from data.source import DataSource
from engine.runner import run_backtest

pytestmark = pytest.mark.usefixtures("isolated_store")


class _Fixed(DataSource):
    def __init__(self, frame):
        self._frame = frame

    def get_daily(self, symbol, start, end):
        return self._frame


def test_export_builds_valid_bundle(synthetic_ohlc, monkeypatch, tmp_path):
    run_backtest("ema_cross", "nifty", dt.date(2020, 1, 1), dt.date(2020, 12, 31),
                 source=_Fixed(synthetic_ohlc))
    monkeypatch.setattr(export_site, "SITE", tmp_path / "site")

    export_site.export()

    data = json.loads((tmp_path / "site" / "data.json").read_text())
    assert "generated_at" in data
    assert "stat_labels" in data and "Trades" in data["stat_labels"]
    assert "# Trades" not in data["stat_labels"]  # relabelled for the UI

    assert "ema_cross" in data["strategies"]
    strat = data["strategies"]["ema_cross"]
    assert strat["columns"] and strat["rows"]
    run = strat["runs"][0]
    for key in ("label", "params", "full_stats", "oos", "equity", "trades"):
        assert key in run
    # full_stats is keyed by the relabelled metric names
    assert "CAGR [%]" in run["full_stats"]
    # equity points are [date, value] pairs
    if run["equity"]:
        assert len(run["equity"][0]) == 2
