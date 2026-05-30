"""The core run + save callable.

``run_backtest`` resolves data and strategy, runs a single backtest with fixed cash
and fill mode and a configurable per-side commission, then saves the run. ``cash``
and fill mode are constants (not user knobs), which keeps a run's identity to exactly
strategy + params + instrument + date range + commission.

Fills are next-bar open (``trade_on_close=False``): a signal on today's close fills at
tomorrow's open — the realistic assumption for an end-of-day daily strategy. Note the
spot index is not directly tradeable; see README's methodological caveats.
"""

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
    params=None, commission=config.DEFAULT_COMMISSION, source=None,
):
    """Execute and persist one backtest. Returns the new ``run_id``."""
    if not (0 <= commission < 0.1):
        raise ValueError(
            f"commission must be a per-side fraction in [0, 0.1); got {commission}. "
            f"Did you pass a percent? 0.05% == 0.0005."
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
    df = source.get_daily(symbol, start, end)

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
        commission=commission,
        trade_on_close=False,
        exclusive_orders=True,
        finalize_trades=True,
    )
    stats = bt.run(**effective)

    return persistence.save_run(
        strategy=strategy_name,
        instrument=instrument,
        params=effective,
        start=start,
        end=end,
        commission=commission,
        stats=stats,
        trades_df=stats["_trades"],
        equity_df=stats["_equity_curve"],
    )
