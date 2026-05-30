"""Turn of the Month — Nifty futures seasonality.

Buy one Nifty futures lot at 15:25 on the **5th-last trading day** of the month and
sell at 15:25 on the **1st trading day of the next month** — capturing the
well-documented turn-of-the-month drift around month-end.

The "Nth-last trading day of the month" and "1st of next month" are calendar facts
known in advance (exchange holidays are published ahead), so they're computed once
in ``init`` from the data's trading days — this is not price look-ahead. Runs on
minute bars and fills on the signal bar's close (``trade_on_close=True``).
"""

from collections import defaultdict
from datetime import time

import pandas as pd
from backtesting import Strategy

from strategies import ParamSpec, register

ACT_AT = time(15, 25)  # enter/exit at 15:25


class TurnOfMonth(Strategy):
    lot = 65            # Nifty futures lot size
    entry_offset = 5    # buy on the Nth-last trading day of the month

    def init(self):
        idx = pd.DatetimeIndex(self.data.index)
        by_month = defaultdict(list)
        for d in sorted(set(idx.date)):
            by_month[(d.year, d.month)].append(d)

        self._entries, self._exits = set(), set()
        months = sorted(by_month)
        for i, ym in enumerate(months):
            mdays = by_month[ym]  # already ascending
            if len(mdays) >= self.entry_offset:
                self._entries.add(mdays[-self.entry_offset])
            if i + 1 < len(months):
                self._exits.add(by_month[months[i + 1]][0])  # 1st of next month

    def next(self):
        ts = self.data.index[-1]
        if ts.time() < ACT_AT:  # only act at/after 15:25
            return
        d = ts.date()
        if self.position and d in self._exits:
            self.position.close()
        elif not self.position and d in self._entries:
            self.buy(size=self.lot)


register(
    "turn_of_month",
    TurnOfMonth,
    ParamSpec(
        params={
            "lot": {"type": int, "default": 65},
            "entry_offset": {"type": int, "default": 5},
        },
        lookback_params=[],
    ),
    trade_on_close=True,
    interval="minute",
)
