"""Turnaround Tuesday — Nifty futures.

Trade one Nifty futures lot (``lot`` units, default 65): on a Monday, if price at
15:25 is below the daily 9-EMA (a weak Monday), buy 1 lot at 15:25 and sell it
unconditionally on a later session. The exit is parametrized: ``hold_days`` calendar
days after entry, at/after ``exit_time``. Defaults (1, "09:45") exit Tuesday 09:45;
``hold_days=2, exit_time="09:18"`` exits Wednesday 09:18.

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


def _ema(values, n):
    return pd.Series(values).ewm(span=n, adjust=False).mean().values


class TurnaroundTuesday(Strategy):
    n = 9               # daily EMA period
    lot = 65            # Nifty futures lot size (units traded per signal)
    hold_days = 1       # calendar days held before the exit window opens
                        #   1 -> exit next session (Tuesday); 2 -> Wednesday
    exit_time = "09:45"  # sell at/after this time on the exit session ("HH:MM")

    def init(self):
        # Daily 9-EMA aligned onto the minute index (look-ahead safe).
        self.daily_ema = resample_apply("D", _ema, self.data.Close, self.n)
        self._entry_day = None
        hh, mm = self.exit_time.split(":")
        self._exit_after = time(int(hh), int(mm))

    def next(self):
        ts = self.data.index[-1]
        t = ts.time()

        # Exit once held >= hold_days calendar days, at/after exit_time.
        if self.position and self._entry_day is not None \
                and (ts.date() - self._entry_day).days >= self.hold_days \
                and t >= self._exit_after:
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
    "turnaround_tuesday",
    TurnaroundTuesday,
    ParamSpec(
        params={
            "n": {"type": int, "default": 9},
            "lot": {"type": int, "default": 65},
            "hold_days": {"type": int, "default": 1},
            "exit_time": {"type": str, "default": "09:45"},
        },
        # No bar-lookback guard: warmup is in *daily* terms (resample_apply yields
        # NaN until 9 days exist, which is NaN-safe), not minute bars.
        lookback_params=[],
    ),
    trade_on_close=True,
    interval="minute",
)
