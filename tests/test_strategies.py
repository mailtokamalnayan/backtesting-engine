"""U3: strategy registry and the EmaCross example."""

import pytest
from backtesting import Backtest

import strategies
from strategies.ema_cross import EmaCross


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
