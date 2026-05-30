"""EMA crossover — the worked example strategy.

Go long when the fast EMA crosses above the slow EMA; flip short on the inverse
cross. ``exclusive_orders=True`` (set by the engine) makes each new order close the
opposite position, so a single ``buy()``/``sell()`` per signal is enough.
"""

import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

from strategies import ParamSpec, register


def _ema(values, n):
    return pd.Series(values).ewm(span=n, adjust=False).mean().values


class EmaCross(Strategy):
    n1 = 10  # fast EMA period
    n2 = 20  # slow EMA period

    def init(self):
        self.ema_fast = self.I(_ema, self.data.Close, self.n1)
        self.ema_slow = self.I(_ema, self.data.Close, self.n2)

    def next(self):
        if crossover(self.ema_fast, self.ema_slow):
            self.buy()
        elif crossover(self.ema_slow, self.ema_fast):
            self.sell()


register(
    "ema_cross",
    EmaCross,
    ParamSpec(
        params={
            "n1": {"type": int, "default": 10},
            "n2": {"type": int, "default": 20},
        },
        lookback_params=["n1", "n2"],
    ),
)
