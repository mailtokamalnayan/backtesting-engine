"""Intraday strategy timing + runner interval routing (synthetic minute data)."""

import datetime as dt
from datetime import time

import pandas as pd
import pytest
from backtesting import Backtest

import strategies
from data.source import DataSource
from engine.runner import run_backtest
from strategies.turnaround_tuesday_intraday import TurnaroundTuesdayIntraday

pytestmark = pytest.mark.usefixtures("isolated_store")

_TIMES = [time(9, 15), time(9, 45), time(12, 0), time(15, 25), time(15, 29)]


def _intraday_declining(weeks=8):
    """Minute-ish bars (5/day) over business days, steadily declining so Mondays
    sit below their daily 9-EMA."""
    days = pd.bdate_range("2022-01-03", periods=weeks * 5)  # starts a Monday
    rows, idx = [], []
    for i, d in enumerate(days):
        day_price = 200.0 - i  # decline one point per day
        for j, tm in enumerate(_TIMES):
            px = day_price - j * 0.05
            rows.append((px, px + 0.5, px - 0.5, px))
            idx.append(pd.Timestamp.combine(d, tm))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"],
                        index=pd.DatetimeIndex(idx, name="Date"))


class _FixedIntraday(DataSource):
    def __init__(self, frame):
        self._frame = frame

    def get_daily(self, symbol, start, end):
        return self._frame

    def get_intraday(self, symbol, start, end, interval="minute"):
        return self._frame


def test_intraday_strategy_registered_interval_and_fill():
    entry = strategies.get("turnaround_tuesday_intraday")
    assert entry.interval == "minute"
    assert entry.trade_on_close is True


def test_enters_1525_monday_exits_0945_next_session():
    data = _intraday_declining()
    bt = Backtest(data, TurnaroundTuesdayIntraday, cash=100_000, commission=0.0,
                  exclusive_orders=True, finalize_trades=True, trade_on_close=True)
    stats = bt.run()
    trades = stats["_trades"]
    assert stats["# Trades"] >= 1
    assert (trades["EntryTime"].dt.time == time(15, 25)).all()
    assert (trades["EntryTime"].dt.weekday == 0).all()      # Monday
    assert (trades["ExitTime"].dt.time == time(9, 45)).all()
    assert (trades["ExitTime"].dt.weekday == 1).all()       # Tuesday
    assert (trades["ExitTime"].dt.date > trades["EntryTime"].dt.date).all()


def test_runner_routes_intraday_through_get_intraday():
    src = _FixedIntraday(_intraday_declining())
    run_id = run_backtest("turnaround_tuesday_intraday", "nifty",
                          dt.date(2022, 1, 1), dt.date(2022, 3, 31),
                          commission=0.0005, source=src)
    assert run_id is not None


def test_intraday_strategy_on_daily_only_source_raises():
    class _DailyOnly(DataSource):
        def get_daily(self, symbol, start, end):
            return _intraday_declining()

    with pytest.raises(ValueError, match="needs minute data"):
        run_backtest("turnaround_tuesday_intraday", "nifty",
                     dt.date(2022, 1, 1), dt.date(2022, 3, 31),
                     source=_DailyOnly())
