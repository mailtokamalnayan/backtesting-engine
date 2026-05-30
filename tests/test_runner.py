"""U5: run engine — guards, commission effect, persistence wiring."""

import datetime as dt

import pandas as pd
import pytest

import config
from data.source import DataSource
from engine import persistence
from engine.runner import InsufficientDataError, run_backtest

pytestmark = pytest.mark.usefixtures("isolated_store")


class _FixedSource(DataSource):
    def __init__(self, frame):
        self._frame = frame

    def get_daily(self, symbol, start, end):
        return self._frame


def _run(frame, params=None, commission=0.0005):
    return run_backtest(
        "ema_cross", "nifty",
        dt.date(2020, 1, 1), dt.date(2020, 12, 31),
        params=params, commission=commission, source=_FixedSource(frame),
    )


def test_run_persists_a_complete_row(synthetic_ohlc):
    run_id = _run(synthetic_ohlc)
    runs = persistence.list_runs()
    assert run_id in set(runs.run_id)
    assert runs.iloc[0].num_trades >= 0


def test_commission_reduces_final_equity_ae3(synthetic_ohlc):
    id_free = _run(synthetic_ohlc, commission=0.0)
    id_costly = _run(synthetic_ohlc, commission=0.02)
    runs = persistence.list_runs().set_index("run_id")
    assert runs.loc[id_costly, "final_equity"] < runs.loc[id_free, "final_equity"]


def test_params_none_uses_defaults(synthetic_ohlc):
    run_id = _run(synthetic_ohlc, params=None)
    params = persistence.load_run_artifacts(run_id)
    # default n1/n2 land in the saved params
    import json

    with open(config.RUNS_DIR / run_id / "params.json") as fh:
        saved = json.load(fh)
    assert saved == {"n1": 10, "n2": 20}


def test_too_short_range_raises_insufficient_data():
    short = pd.DataFrame(
        {"Open": [1, 2, 3], "High": [1, 2, 3], "Low": [1, 2, 3], "Close": [1, 2, 3]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
    )
    with pytest.raises(InsufficientDataError):
        _run(short, params={"n1": 10, "n2": 50})


def test_cash_guard_rejects_prices_above_cash(monkeypatch, synthetic_ohlc):
    monkeypatch.setattr(config, "DEFAULT_CASH", 50)  # below synthetic prices (~100+)
    with pytest.raises(ValueError, match="must exceed the max price"):
        _run(synthetic_ohlc)


def test_bad_commission_raises_before_fetch(synthetic_ohlc):
    with pytest.raises(ValueError, match="per-side fraction"):
        _run(synthetic_ohlc, commission=0.1)


def test_unknown_instrument_and_strategy_raise(synthetic_ohlc):
    with pytest.raises(ValueError, match="unknown instrument"):
        run_backtest("ema_cross", "dowjones", dt.date(2020, 1, 1),
                     dt.date(2020, 12, 31), source=_FixedSource(synthetic_ohlc))
    with pytest.raises(KeyError):
        run_backtest("no_such", "nifty", dt.date(2020, 1, 1),
                     dt.date(2020, 12, 31), source=_FixedSource(synthetic_ohlc))
