"""Turnaround Tuesday — Quantified Strategies version.

A stricter, gap-driven variant of Turnaround Tuesday, per the rules described at
https://www.quantifiedstrategies.com/turnaround-tuesday-strategy/ :

    1. Today is Monday.
    2. Monday's close is at least ``drop_pct`` (default 1%) below Friday's close.
    3. If both hold, buy at Monday's close.
    4. Sell at Tuesday's close.

"Close" is taken as 15:25 on Nifty (the user's convention). "Friday's close" is the
previous trading session's 15:25 (robust to holiday weeks). Trades one Nifty futures
lot, so PnL is the per-contract rupee P&L net of slippage.

Entry/exit dates are precomputed in ``init`` from the data's 15:25 prices — this only
uses Monday's and the prior session's closes (both known at the Monday-15:25 decision
bar), so there is no look-ahead.
"""

from datetime import time

import numpy as np
import pandas as pd
from backtesting import Strategy

from strategies import ParamSpec, register

MONDAY = 0
ACT = time(15, 25)  # "close" = 15:25
SOURCE_URL = "https://www.quantifiedstrategies.com/turnaround-tuesday-strategy/"


class TurnaroundTuesdayQuantified(Strategy):
    lot = 65            # Nifty futures lot size
    drop_pct = 1.0      # Monday close must be >= this % below Friday's close

    def init(self):
        idx = pd.DatetimeIndex(self.data.index)
        close = pd.Series(np.asarray(self.data.Close), index=idx)
        # Price at 15:25 per trading date (fall back to the day's last bar).
        at_close = close[idx.time == ACT]
        price = {ts.date(): float(v) for ts, v in at_close.items()}
        if len(price) < len(set(idx.date)):
            for d, v in close.groupby(idx.date).last().items():
                price.setdefault(d, float(v))

        dates = sorted(price)
        thresh = 1.0 - self.drop_pct / 100.0
        self._entries, self._exits = set(), set()
        for i, d in enumerate(dates):
            if i == 0:
                continue
            if d.weekday() == MONDAY and price[d] <= price[dates[i - 1]] * thresh:
                self._entries.add(d)
                if i + 1 < len(dates):
                    self._exits.add(dates[i + 1])  # next session = Tuesday

    def next(self):
        ts = self.data.index[-1]
        if ts.time() < ACT:  # only act at/after the 15:25 close
            return
        d = ts.date()
        if self.position and d in self._exits:
            self.position.close()
        elif not self.position and d in self._entries:
            self.buy(size=self.lot)


register(
    "turnaround_tuesday_quantified_version",
    TurnaroundTuesdayQuantified,
    ParamSpec(
        params={
            "lot": {"type": int, "default": 65},
            "drop_pct": {"type": float, "default": 1.0},
        },
        lookback_params=[],
    ),
    trade_on_close=True,
    interval="minute",
    source=SOURCE_URL,
)
