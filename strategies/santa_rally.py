"""Santa Rally — the year-end Nifty seasonality.

Buy one Nifty futures lot at 15:25 on the **Nth-last trading day of December**
(``entry_offset``, default 5) and sell at 15:25 on the **Mth trading day of the
following January** (``exit_offset``, default 2) — capturing the well-known
"Santa Claus rally" drift across the New Year boundary.

Like ``turn_of_month``, the entry/exit dates are calendar facts known in advance
(exchange holidays are published ahead), so they're computed once in ``init`` from
the data's trading days — not price look-ahead. Each December is paired with the
January that immediately follows it. Runs on minute bars and fills on the signal
bar's close (``trade_on_close=True``).
"""

from collections import defaultdict
from datetime import time

import pandas as pd
from backtesting import Strategy

from strategies import ParamSpec, register

ACT_AT = time(15, 25)  # enter/exit at 15:25


class SantaRally(Strategy):
    lot = 65            # Nifty futures lot size
    entry_offset = 5    # buy on the Nth-last trading day of December
    exit_offset = 2     # sell on the Nth trading day of the next January (2 = 2nd)

    def init(self):
        idx = pd.DatetimeIndex(self.data.index)
        by_month = defaultdict(list)
        for d in sorted(set(idx.date)):
            by_month[(d.year, d.month)].append(d)

        self._entries, self._exits = set(), set()
        for (year, month), days in by_month.items():  # days ascending
            if month == 12 and len(days) >= self.entry_offset:
                self._entries.add(days[-self.entry_offset])
            if month == 1 and len(days) >= self.exit_offset:
                self._exits.add(days[self.exit_offset - 1])

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
    "santa_rally",
    SantaRally,
    ParamSpec(
        params={
            "lot": {"type": int, "default": 65},
            "entry_offset": {"type": int, "default": 5},
            "exit_offset": {"type": int, "default": 2},
        },
        lookback_params=[],
    ),
    trade_on_close=True,
    interval="minute",
)
