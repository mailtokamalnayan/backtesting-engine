"""Turnaround Tuesday.

If Monday closes below its 9-period EMA (a weak Monday), buy at Monday's close and
sell at the next session's close (normally Tuesday). A one-day, close-to-close hold
that bets weak Mondays bounce.

Declares ``trade_on_close=True`` so the buy fills at the Monday close that triggered
it and the exit fills at the next close — matching the rule literally.
"""

import pandas as pd
from backtesting import Strategy

from strategies import ParamSpec, register

MONDAY = 0


def _ema(values, n):
    return pd.Series(values).ewm(span=n, adjust=False).mean().values


class TurnaroundTuesday(Strategy):
    n = 9  # EMA period for the "weak Monday" test

    def init(self):
        self.ema = self.I(_ema, self.data.Close, self.n)

    def next(self):
        # Exit first: any open position was opened on the prior bar (Monday), so
        # close it on this bar's close (Tuesday). One-day hold.
        if self.position:
            self.position.close()
            return
        # Enter only on a Monday that closed below its 9 EMA.
        if self.data.index[-1].weekday() == MONDAY and \
                self.data.Close[-1] < self.ema[-1]:
            self.buy()


register(
    "turnaround_tuesday",
    TurnaroundTuesday,
    ParamSpec(
        params={"n": {"type": int, "default": 9}},
        lookback_params=["n"],
    ),
    trade_on_close=True,
)
