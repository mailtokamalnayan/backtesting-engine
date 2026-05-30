"""Zerodha Kite Connect data source — daily and intraday index candles.

Implements the ``DataSource`` seam (R4), adding intraday support via
``get_intraday``. Auth is two-step and the access token expires daily, so the
intended pattern is: authenticate once (``python -m data.kite_auth``), then
download history and cache it to Parquet — backtests run offline from the cache
forever, so the daily-token expiry never bites.

Credentials come from the environment (never hardcoded):
    KITE_API_KEY, KITE_API_SECRET
The access token is written by the auth helper to ``.kite_token.json`` (gitignored).

Requires the ``kiteconnect`` package and an active Kite Connect historical-data
subscription. ``kiteconnect`` is imported lazily so this module loads without it.
"""

import datetime as dt
import json
import os

import pandas as pd

import config  # noqa: F401 -- import-order parity with other sources
from data.source import DataSource, DataUnavailableError

TOKEN_PATH = config.ROOT / ".kite_token.json"
CACHE_DIR = config.ROOT / ".kite_cache"

# niftyindices symbol string -> Kite instrument_token (NSE indices).
INSTRUMENT_TOKENS = {
    "NIFTY 50": 256265,
    "NIFTY BANK": 260105,
}

# Max days Kite serves per request, by interval (chunk longer ranges).
_MAX_DAYS = {
    "minute": 60, "3minute": 100, "5minute": 100, "10minute": 100,
    "15minute": 200, "30minute": 200, "60minute": 400, "day": 2000,
}

_OHLC = ["Open", "High", "Low", "Close"]


def load_access_token() -> dict:
    """Read the token written by data.kite_auth, or raise a clear instruction."""
    if not TOKEN_PATH.exists():
        raise DataUnavailableError(
            "no Kite access token found. Run `python -m data.kite_auth` to log in."
        )
    with open(TOKEN_PATH) as fh:
        return json.load(fh)


class KiteIntradaySource(DataSource):
    """Daily + intraday NSE index candles via Kite Connect.

    Pass ``kite`` to inject a pre-authenticated client (used in tests); otherwise
    a client is built lazily from ``KITE_API_KEY`` + the saved access token.
    """

    def __init__(self, api_key=None, access_token=None, kite=None):
        self._api_key = api_key or os.environ.get("KITE_API_KEY")
        self._access_token = access_token
        self._kite = kite

    def _client(self):
        if self._kite is not None:
            return self._kite
        if not self._api_key:
            raise DataUnavailableError("KITE_API_KEY is not set in the environment.")
        token = self._access_token or load_access_token().get("access_token")
        try:
            from kiteconnect import KiteConnect
        except ImportError as err:
            raise DataUnavailableError(
                "kiteconnect is not installed. `pip install kiteconnect`."
            ) from err
        kite = KiteConnect(api_key=self._api_key)
        kite.set_access_token(token)
        self._kite = kite
        return kite

    def get_daily(self, symbol, start, end) -> pd.DataFrame:
        return self.get_intraday(symbol, start, end, interval="day")

    def get_intraday(self, symbol, start, end, interval="minute") -> pd.DataFrame:
        if symbol not in INSTRUMENT_TOKENS:
            raise DataUnavailableError(f"no Kite instrument token for {symbol!r}")
        if interval not in _MAX_DAYS:
            raise DataUnavailableError(f"unsupported interval {interval!r}")

        cache_path = self._cache_path(symbol, interval, start, end)
        if cache_path.exists():
            return pd.read_parquet(cache_path)

        token = INSTRUMENT_TOKENS[symbol]
        records = self._fetch_chunked(token, start, end, interval)
        df = self._to_df(records)
        if df.empty:
            raise DataUnavailableError(
                f"no candles for {symbol!r} {start}..{end} @ {interval}"
            )
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path)
        return df

    def _fetch_chunked(self, token, start, end, interval):
        step = dt.timedelta(days=_MAX_DAYS[interval])
        client = self._client()
        out = []
        window_start = start
        while window_start <= end:
            window_end = min(window_start + step - dt.timedelta(days=1), end)
            try:
                out.extend(
                    client.historical_data(token, window_start, window_end, interval)
                )
            except Exception as err:  # KiteException, network, token expiry, ...
                raise DataUnavailableError(
                    f"Kite historical_data failed for {window_start}..{window_end} "
                    f"@ {interval}: {err}. (Token may have expired -- re-run "
                    f"`python -m data.kite_auth`.)"
                ) from err
            window_start = window_end + dt.timedelta(days=1)
        return out

    @staticmethod
    def _to_df(records) -> pd.DataFrame:
        if not records:
            return pd.DataFrame(columns=_OHLC)
        df = pd.DataFrame(records).rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"}
        )
        idx = pd.to_datetime(df["date"])
        # Kite returns tz-aware IST timestamps; drop tz to get naive IST wall-clock
        # so time-of-day checks (15:25, 09:45) read in market local time.
        if getattr(idx.dt, "tz", None) is not None:
            idx = idx.dt.tz_localize(None)
        df.index = pd.DatetimeIndex(idx, name="Date")
        df = df[_OHLC].dropna().sort_index()
        return df[~df.index.duplicated(keep="first")]

    @staticmethod
    def _cache_path(symbol, interval, start, end):
        slug = symbol.replace(" ", "_")
        return CACHE_DIR / f"{slug}_{interval}_{start}_{end}.parquet"
