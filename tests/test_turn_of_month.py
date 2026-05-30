"""Turn-of-month strategy: enters 5th-last trading day, exits 1st of next month."""

from collections import defaultdict
from datetime import time

import pandas as pd
from backtesting import Backtest

import strategies
from strategies.turn_of_month import TurnOfMonth


def _monthly_intraday(n_bdays=85):
    """Business days across ~4 months, each with a 09:15 and a 15:25 bar."""
    days = pd.bdate_range("2022-01-03", periods=n_bdays)
    rows, idx = [], []
    price = 100.0
    for d in days:
        for t in (time(9, 15), time(15, 25)):
            rows.append((price, price + 1, price - 1, price))
            idx.append(pd.Timestamp.combine(d, t))
        price += 0.5
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"],
                        index=pd.DatetimeIndex(idx, name="Date"))


def _expected_dates(data, entry_offset=5, exit_offset=1):
    by_month = defaultdict(list)
    for d in sorted(set(data.index.date)):
        by_month[(d.year, d.month)].append(d)
    months = sorted(by_month)
    entries, exits = set(), set()
    for i, ym in enumerate(months):
        if len(by_month[ym]) >= entry_offset:
            entries.add(by_month[ym][-entry_offset])
        if i + 1 < len(months):
            ndays = by_month[months[i + 1]]
            if len(ndays) >= exit_offset:
                exits.add(ndays[exit_offset - 1])
    return entries, exits


def test_registered_as_intraday_close_fill():
    entry = strategies.get("turn_of_month")
    assert entry.interval == "minute"
    assert entry.trade_on_close is True


def test_enters_5th_last_exits_first_of_next_month():
    data = _monthly_intraday()
    bt = Backtest(data, TurnOfMonth, cash=1_000_000, commission=0.0,
                  exclusive_orders=True, finalize_trades=True, trade_on_close=True)
    stats = bt.run()
    trades = stats["_trades"]
    entries, exits = _expected_dates(data)

    assert stats["# Trades"] >= 2
    assert (trades["EntryTime"].dt.time == time(15, 25)).all()
    assert set(trades["EntryTime"].dt.date) <= entries
    # Properly-closed trades exit at 15:25 on the 1st of the next month. The final
    # trade may still be open at the last bar (force-closed by finalize_trades).
    closed = trades[trades["ExitTime"].dt.date.isin(exits)]
    assert len(closed) >= 2
    assert (closed["ExitTime"].dt.time == time(15, 25)).all()
    assert (trades["ExitTime"] > trades["EntryTime"]).all()


def test_entry_offset_param_shifts_entry():
    data = _monthly_intraday()
    bt = Backtest(data, TurnOfMonth, cash=1_000_000, commission=0.0,
                  exclusive_orders=True, finalize_trades=True, trade_on_close=True)
    stats = bt.run(entry_offset=3)
    entries, _ = _expected_dates(data, entry_offset=3)
    assert set(stats["_trades"]["EntryTime"].dt.date) <= entries


def test_exit_offset_param_shifts_exit():
    data = _monthly_intraday()
    bt = Backtest(data, TurnOfMonth, cash=1_000_000, commission=0.0,
                  exclusive_orders=True, finalize_trades=True, trade_on_close=True)
    stats = bt.run(exit_offset=3)  # exit on 3rd trading day of next month
    _, exits = _expected_dates(data, exit_offset=3)
    closed = stats["_trades"][stats["_trades"]["ExitTime"].dt.date.isin(exits)]
    assert len(closed) >= 1
    assert (closed["ExitTime"].dt.time == time(15, 25)).all()
