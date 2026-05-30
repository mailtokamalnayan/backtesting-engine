"""Turnaround Tuesday — intraday Nifty futures.

Trade one Nifty futures lot (``lot`` units, default 65): on a Monday, if price at
15:25 is below the daily 9-EMA (a weak Monday), buy 1 lot at 15:25 and sell it at
09:45 the next session — unconditionally. Captures the overnight-and-open move.

Because each trade is a fixed lot, the trade PnL is the real rupee P&L of one Nifty
futures contract (points moved x lot size), net of slippage. Runs on minute bars
(``interval="minute"``) and fills on the signal bar's close (``trade_on_close=True``),
so the 15:25 entry and 09:45 exit fill at those bars. The 9-EMA is computed on
*daily* closes via ``resample_apply`` and aligned back to the minute series — no
look-ahead.

NOTE: Nifty's contract lot size has changed over time; ``lot`` defaults to 65 (per
the user) and is tunable — set it to the current NSE contract size if different.
"""

from datetime import time

import pandas as pd
from backtesting import Strategy
from backtesting.lib import resample_apply

from strategies import ParamSpec, register

MONDAY = 0
ENTRY_AFTER = time(15, 25)   # buy at/after 15:25 on a weak Monday
EXIT_AFTER = time(9, 45)     # sell at/after 09:45 the next session


def _ema(values, n):
    return pd.Series(values).ewm(span=n, adjust=False).mean().values


class TurnaroundTuesdayIntraday(Strategy):
    n = 9      # daily EMA period
    lot = 65   # Nifty futures lot size (units traded per signal)

    def init(self):
        # Daily 9-EMA aligned onto the minute index (look-ahead safe).
        self.daily_ema = resample_apply("D", _ema, self.data.Close, self.n)
        self._entry_day = None

    def next(self):
        ts = self.data.index[-1]
        t = ts.time()

        # Exit on the next session at/after 09:45 (never same day as entry).
        if self.position and self._entry_day is not None \
                and ts.date() > self._entry_day and t >= EXIT_AFTER:
            self.position.close()
            self._entry_day = None
            return

        # Enter once, on a Monday at/after 15:25, if below the daily 9-EMA.
        if self._entry_day is None and not self.position \
                and ts.weekday() == MONDAY and t >= ENTRY_AFTER \
                and self.data.Close[-1] < self.daily_ema[-1]:
            self.buy(size=self.lot)  # one futures lot
            self._entry_day = ts.date()


register(
    "turnaround_tuesday_intraday",
    TurnaroundTuesdayIntraday,
    ParamSpec(
        params={
            "n": {"type": int, "default": 9},
            "lot": {"type": int, "default": 65},
        },
        # No bar-lookback guard: warmup is in *daily* terms (resample_apply yields
        # NaN until 9 days exist, which is NaN-safe), not minute bars.
        lookback_params=[],
    ),
    trade_on_close=True,
    interval="minute",
)
