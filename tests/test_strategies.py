"""U3: strategy registry and the EmaCross example."""

import numpy as np
import pandas as pd
import pytest
from backtesting import Backtest

import strategies
from strategies.ema_cross import EmaCross
from strategies.turnaround_tuesday import TurnaroundTuesday


def test_registry_lookup_and_available():
    entry = strategies.get("ema_cross")
    assert entry.cls is EmaCross
    assert "ema_cross" in strategies.available()


def test_param_spec_declares_lookbacks_and_defaults():
    spec = strategies.get("ema_cross").spec
    assert spec.lookback_params == ["n1", "n2"]
    assert spec.defaults() == {"n1": 10, "n2": 20}
    assert spec.coerce("n1", "15") == 15  # string -> int


def test_unknown_strategy_raises_with_available_names():
    with pytest.raises(KeyError) as exc:
        strategies.get("nope")
    assert "ema_cross" in str(exc.value)


def test_emacross_trades_on_trending_data(synthetic_ohlc):
    bt = Backtest(
        synthetic_ohlc,
        EmaCross,
        cash=100_000,
        commission=0.0,
        exclusive_orders=True,
        finalize_trades=True,
    )
    stats = bt.run()
    assert stats["# Trades"] >= 1


def test_fill_mode_is_per_strategy():
    assert strategies.get("ema_cross").trade_on_close is False
    assert strategies.get("turnaround_tuesday").trade_on_close is True


def _declining_daily(weeks=10):
    """Business-day series declining steadily, so Close sits below its lagging EMA."""
    n = weeks * 5
    dates = pd.date_range("2022-01-03", periods=n, freq="B")  # starts a Monday
    close = np.linspace(200, 150, n)
    return pd.DataFrame(
        {"Open": close, "High": close + 1, "Low": close - 1, "Close": close},
        index=pd.DatetimeIndex(dates, name="Date"),
    )


def test_turnaround_tuesday_enters_mondays_exits_next_close():
    data = _declining_daily()
    bt = Backtest(
        data, TurnaroundTuesday, cash=100_000, commission=0.0,
        exclusive_orders=True, finalize_trades=True, trade_on_close=True,
    )
    stats = bt.run()
    trades = stats["_trades"]
    assert stats["# Trades"] >= 1
    # Every entry is a Monday; every exit is the next session (Tuesday) -> one-day hold.
    assert (trades["EntryTime"].dt.weekday == 0).all()
    assert (trades["ExitTime"].dt.weekday == 1).all()
    assert (trades["ExitBar"] - trades["EntryBar"] == 1).all()
