"""Turnaround Tuesday — Quantified version (Mon close >=1% below Fri close)."""

from datetime import time

import pandas as pd
import pytest
from backtesting import Backtest

import strategies
from strategies.turnaround_tuesday_quantified import (
    SOURCE_URL, TurnaroundTuesdayQuantified,
)


def _gap_down_mondays(n=30):
    """Business days with a 15:25 bar; every Monday is 2% below the prior session."""
    days = pd.bdate_range("2022-01-03", periods=n)  # starts a Monday
    rows, idx, prev = [], [], 100.0
    for d in days:
        p = prev * 0.98 if d.weekday() == 0 else prev  # Monday gaps down 2%
        for t in (time(9, 15), time(15, 25)):
            rows.append((p, p + 0.2, p - 0.2, p))
            idx.append(pd.Timestamp.combine(d, t))
        prev = p
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"],
                        index=pd.DatetimeIndex(idx, name="Date"))


def _run(data, **params):
    bt = Backtest(data, TurnaroundTuesdayQuantified, cash=1_000_000, commission=0.0,
                  exclusive_orders=True, finalize_trades=True, trade_on_close=True)
    return bt.run(**params)


def test_registered_with_source_and_intraday():
    entry = strategies.get("turnaround_tuesday_quantified_version")
    assert entry.interval == "minute"
    assert entry.trade_on_close is True
    assert entry.source == SOURCE_URL


def test_enters_weak_monday_close_exits_tuesday_close():
    stats = _run(_gap_down_mondays())
    trades = stats["_trades"]
    assert stats["# Trades"] >= 2
    assert (trades["EntryTime"].dt.weekday == 0).all()          # Monday
    assert (trades["EntryTime"].dt.time == time(15, 25)).all()  # at the close
    assert (trades["ExitTime"].dt.weekday == 1).all()           # Tuesday
    assert (trades["ExitTime"].dt.time == time(15, 25)).all()


def test_drop_pct_threshold_filters_entries():
    # 2% gaps don't clear a 5% threshold -> no trades.
    stats = _run(_gap_down_mondays(), drop_pct=5.0)
    assert stats["# Trades"] == 0
