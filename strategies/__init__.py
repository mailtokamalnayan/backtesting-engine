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

Registered = namedtuple("Registered", ["cls", "spec"])


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


def register(name, cls, spec: ParamSpec):
    STRATEGIES[name] = Registered(cls, spec)


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
