"""Yahoo Finance daily index source — a DataSource implementation.

Added as a fallback because niftyindices.com (jugaad-data's index backend) blocks
some networks/IPs. It implements the exact same ``DataSource.get_daily`` contract as
``JugaadDailySource``, so the engine, persistence, CLI, and dashboard use it
unchanged — a demonstration of the R4 data-source seam.

No API key required. Maps the project's jugaad symbol strings to Yahoo tickers.
"""

import datetime as dt
import json
import urllib.request

import pandas as pd

import config  # noqa: F401 -- keep import-order parity with JugaadDailySource
from data.source import DataSource, DataUnavailableError

_YAHOO_TICKER = {
    "NIFTY 50": "^NSEI",
    "NIFTY BANK": "^NSEBANK",
}
_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


class YahooDailySource(DataSource):
    def __init__(self, timeout=30):
        self._timeout = timeout

    def get_daily(self, symbol, start, end) -> pd.DataFrame:
        if symbol not in _YAHOO_TICKER:
            raise DataUnavailableError(f"no Yahoo ticker mapping for {symbol!r}")
        ticker = _YAHOO_TICKER[symbol]
        p1 = int(dt.datetime.combine(start, dt.time()).timestamp())
        p2 = int(dt.datetime.combine(end, dt.time()).timestamp())
        url = (f"{_URL.format(ticker=urllib.parse.quote(ticker))}"
               f"?period1={p1}&period2={p2}&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            payload = json.loads(
                urllib.request.urlopen(req, timeout=self._timeout).read()
            )
            result = payload["chart"]["result"][0]
            ts = result["timestamp"]
            quote = result["indicators"]["quote"][0]
        except Exception as err:
            raise DataUnavailableError(
                f"Yahoo fetch failed for {symbol!r} {start}..{end}: {err}"
            )

        df = pd.DataFrame(
            {
                "Open": quote["open"],
                "High": quote["high"],
                "Low": quote["low"],
                "Close": quote["close"],
            },
            index=pd.to_datetime(ts, unit="s").normalize(),
        )
        df.index.name = "Date"
        df = df.dropna().sort_index()
        if df.empty:
            raise DataUnavailableError(f"no usable rows for {symbol!r} {start}..{end}")
        return df
