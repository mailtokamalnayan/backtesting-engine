"""The core run + save callable.

``run_backtest`` resolves data and strategy, runs a single backtest with fixed cash
and fill mode and a fixed slippage cost, then saves the run. ``cash`` and fill mode
are constants (not user knobs), which keeps a run's identity to exactly strategy +
params + instrument + date range + slippage. Slippage (default 0.5% per fill,
``config.DEFAULT_SLIPPAGE``) stands in for all trading cost; commission is not
modeled separately.

Fill mode is declared per strategy (``Registered.trade_on_close``): most strategies
fill at the next bar's open (realistic for an EOD signal), while signal-on-close
strategies fill on the signal bar's close. Note the spot index is not directly
tradeable; see README's methodological caveats.
"""

import warnings

import config
import strategies
from backtesting import Backtest
from data.source import JugaadDailySource
from engine import persistence

# Bars beyond the slowest lookback to be confident indicators have warmed up.
_WARMUP_BUFFER = 2


class InsufficientDataError(Exception):
    """Raised when the date range has too few bars for the strategy's lookbacks."""


def _min_bars_required(spec, params) -> int:
    if not spec.lookback_params:
        return 0
    # int() guards a programmatic caller passing stringy lookback values; the CLI
    # already coerces via param_spec.
    return max(int(params[name]) for name in spec.lookback_params) + _WARMUP_BUFFER


def run_backtest(
    strategy_name, instrument, start, end,
    params=None, slippage=config.DEFAULT_SLIPPAGE, source=None,
):
    """Execute and persist one backtest. Returns the new ``run_id``."""
    if not (0 <= slippage < 0.1):
        raise ValueError(
            f"slippage must be a per-fill fraction in [0, 0.1); got {slippage}. "
            f"Did you pass a percent? 0.5% == 0.005."
        )

    if instrument not in config.INSTRUMENTS:
        raise ValueError(
            f"unknown instrument {instrument!r}. "
            f"Available: {', '.join(config.INSTRUMENTS)}"
        )
    symbol = config.INSTRUMENTS[instrument]

    entry = strategies.get(strategy_name)  # raises KeyError if unknown
    effective = entry.spec.defaults()
    effective.update(params or {})

    source = source or JugaadDailySource()
    if entry.interval == "day":
        df = source.get_daily(symbol, start, end)
    elif hasattr(source, "get_intraday"):
        df = source.get_intraday(symbol, start, end, interval=entry.interval)
    else:
        raise ValueError(
            f"strategy {strategy_name!r} needs {entry.interval} data, but "
            f"{type(source).__name__} only provides daily bars."
        )

    if config.DEFAULT_CASH <= df["Close"].max():
        raise ValueError(
            f"DEFAULT_CASH ({config.DEFAULT_CASH}) must exceed the max price "
            f"({df['Close'].max():.2f}); backtesting.py cannot trade fractional units."
        )

    required = _min_bars_required(entry.spec, effective)
    if len(df) <= required:
        raise InsufficientDataError(
            f"{strategy_name} needs > {required} bars (lookbacks "
            f"{entry.spec.lookback_params}) but the range has only {len(df)}."
        )

    bt = Backtest(
        df,
        entry.cls,
        cash=config.DEFAULT_CASH,
        commission=slippage,  # backtesting.py's per-fill cost models our slippage
        trade_on_close=entry.trade_on_close,  # strategy declares its fill mode
        exclusive_orders=True,
        # Do NOT force-close a still-open position at the last bar: that fabricates
        # an exit that violates the strategy's rule. Only completed, rule-exited
        # trades are reported; a currently-open position is simply excluded.
        finalize_trades=False,
    )
    with warnings.catch_warnings():
        # Expected: we intentionally leave a still-open final position out of stats.
        warnings.filterwarnings("ignore", message="Some trades remain open")
        stats = bt.run(**effective)

    return persistence.save_run(
        strategy=strategy_name,
        instrument=instrument,
        params=effective,
        start=start,
        end=end,
        slippage=slippage,
        stats=stats,
        trades_df=stats["_trades"],
        equity_df=stats["_equity_curve"],
    )
