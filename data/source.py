"""Daily OHLC data sources.

``DataSource`` is the seam the rest of the harness depends on — nothing outside
this module imports ``jugaad_data``. Only a daily source exists today; an intraday
source can be added later as a sibling implementation without touching the engine
or strategies.

``config`` is imported first (top of module) so ``J_CACHE_DIR`` is set before any
``jugaad_data`` import, keeping jugaad's pickle cache project-local.
"""

import time
from abc import ABC, abstractmethod

import pandas as pd

import config  # noqa: F401 -- side effect: sets J_CACHE_DIR before jugaad import

_OHLC = ["Open", "High", "Low", "Close"]
_RENAME = {"OPEN": "Open", "HIGH": "High", "LOW": "Low", "CLOSE": "Close"}


class DataUnavailableError(Exception):
    """Raised when a source cannot return usable data for a symbol+range."""


class DataSource(ABC):
    """A source of daily OHLC bars for an instrument."""

    @abstractmethod
    def get_daily(self, symbol, start, end) -> pd.DataFrame:
        """Return a backtesting.py-ready daily OHLC frame.

        The frame has exactly ``Open/High/Low/Close`` columns, a sorted
        ``DatetimeIndex``, and no NaN rows. ``start``/``end`` are ``datetime.date``.
        """


def _default_fetch(symbol, start, end):
    # Lazy import: config (above) has already set J_CACHE_DIR by the time this runs.
    from jugaad_data.nse import index_df

    return index_df(symbol=symbol, from_date=start, to_date=end)


def _transform(raw: pd.DataFrame) -> pd.DataFrame:
    """jugaad index_df output -> clean, sorted, NaN-free OHLC on a DatetimeIndex."""
    df = raw.rename(columns=_RENAME)
    df["HistoricalDate"] = pd.to_datetime(df["HistoricalDate"], errors="coerce")
    # Drop unparseable dates (NaT) and any NaN OHLC -- backtesting.py hard-raises
    # on either.
    df = df.dropna(subset=["HistoricalDate", *_OHLC])
    df = df.set_index("HistoricalDate").sort_index()
    df.index.name = "Date"
    return df[_OHLC]


class JugaadDailySource(DataSource):
    """Daily index OHLC via jugaad-data, with retry/backoff.

    jugaad-data has no retry logic and hits niftyindices.com directly; a single
    failed month-chunk aborts the whole call. We wrap it in bounded retries.
    jugaad's own per-month pickle cache (relocated via J_CACHE_DIR) means a
    successful range is served from disk with no network call on the next run,
    satisfying the "fetched at most once" requirement.
    """

    def __init__(self, max_retries=3, backoff_base=0.5, fetch_fn=_default_fetch):
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._fetch_fn = fetch_fn

    def get_daily(self, symbol, start, end) -> pd.DataFrame:
        last_err = None
        for attempt in range(self._max_retries):
            try:
                raw = self._fetch_fn(symbol, start, end)
            except Exception as err:  # jugaad raises bare exceptions on failure
                last_err = err
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2 ** attempt))
                continue

            if raw is None or len(raw) == 0:
                last_err = DataUnavailableError(
                    f"empty payload for {symbol!r} {start}..{end}"
                )
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2 ** attempt))
                continue

            df = _transform(raw)
            if df.empty:
                raise DataUnavailableError(
                    f"no usable rows for {symbol!r} {start}..{end} after cleaning"
                )
            return df

        raise DataUnavailableError(
            f"failed to fetch {symbol!r} {start}..{end}: {last_err}"
        )
