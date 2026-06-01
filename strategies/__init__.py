"""Strategy registry.

Strategies are small ``backtesting.py`` ``Strategy`` subclasses registered by name
with a ``ParamSpec`` describing their tunable params (type + default) and which of
those params are bar-lookbacks. The engine uses ``lookback_params`` to guard against
date ranges too short for the strategy's indicators to warm up.

Example strategy modules are imported at the bottom so importing this package
populates the registry.
"""

from collections import namedtuple
from dataclasses import dataclass, field

Registered = namedtuple(
    "Registered", ["cls", "spec", "trade_on_close", "interval", "source"]
)


@dataclass
class ParamSpec:
    # name -> {"type": <callable>, "default": <value>}
    params: dict = field(default_factory=dict)
    # subset of params.keys() that are bar-lookbacks (e.g. EMA periods)
    lookback_params: list = field(default_factory=list)

    def defaults(self) -> dict:
        return {name: meta["default"] for name, meta in self.params.items()}

    def coerce(self, name, raw):
        return self.params[name]["type"](raw)


STRATEGIES = {}


def register(name, cls, spec: ParamSpec, trade_on_close=False, interval="day",
             source=None):
    """Register a strategy.

    ``trade_on_close`` is a property of the strategy's logic, not a free runner
    knob: signal-on-close strategies (e.g. "buy at this close") set it True so
    fills happen on the signal bar's close rather than the next bar's open.

    ``interval`` is the bar timeframe the strategy needs ("day", "minute", ...).
    The runner fetches data at this interval; an intraday strategy run against a
    daily-only source fails clearly. Both fields are fixed per strategy, so they
    don't widen a run's identity.

    ``source`` is an optional URL crediting where the strategy idea came from;
    the dashboards surface it as a link under the strategy.
    """
    STRATEGIES[name] = Registered(cls, spec, trade_on_close, interval, source)


def get(name) -> Registered:
    if name not in STRATEGIES:
        raise KeyError(
            f"unknown strategy {name!r}. Available: {', '.join(available())}"
        )
    return STRATEGIES[name]


def available():
    return sorted(STRATEGIES)


# Importing example modules triggers their self-registration. Kept at the bottom
# so `register`/`ParamSpec` are defined before the modules import them.
from . import ema_cross  # noqa: E402,F401
from . import turnaround_tuesday  # noqa: E402,F401
from . import turnaround_tuesday_quantified  # noqa: E402,F401
from . import turn_of_month  # noqa: E402,F401
