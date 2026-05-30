"""Shared test fixtures.

Two deterministic frames so unit tests never touch the network:

- ``synthetic_ohlc``: a clean, title-cased OHLC frame on a DatetimeIndex with a
  pronounced up-then-down trend and prices well below a small test ``cash`` value,
  so an EMA-crossover strategy actually trades.
- ``raw_jugaad_frame``: a frame shaped exactly like ``jugaad_data.index_df`` output
  (UPPERCASE columns, RangeIndex, unsorted rows, a NaT row) for transform tests.
"""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_ohlc():
    """~240 daily bars: ramp up 100->200, then down to 120. Crossovers guaranteed."""
    n = 240
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    up = np.linspace(100, 200, n // 2)
    down = np.linspace(200, 120, n - n // 2)
    close = np.concatenate([up, down])
    # Build OHLC around the close with a small, deterministic intrabar range.
    open_ = close - 0.5
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close},
        index=pd.DatetimeIndex(dates, name="Date"),
    )


@pytest.fixture
def raw_jugaad_frame():
    """Mimics jugaad_data.index_df: UPPERCASE cols, RangeIndex, unsorted, one NaT."""
    rows = [
        {"INDEX_NAME": "Nifty 50", "HistoricalDate": "10-Jan-2023",
         "OPEN": 102.0, "HIGH": 104.0, "LOW": 101.0, "CLOSE": 103.0},
        {"INDEX_NAME": "Nifty 50", "HistoricalDate": "09-Jan-2023",
         "OPEN": 100.0, "HIGH": 103.0, "LOW": 99.0, "CLOSE": 102.0},
        {"INDEX_NAME": "Nifty 50", "HistoricalDate": "11-Jan-2023",
         "OPEN": 103.0, "HIGH": 106.0, "LOW": 102.5, "CLOSE": 105.0},
        # Unparseable date -> becomes NaT after coercion; must be dropped.
        {"INDEX_NAME": "Nifty 50", "HistoricalDate": "not-a-date",
         "OPEN": 0.0, "HIGH": 0.0, "LOW": 0.0, "CLOSE": 0.0},
    ]
    df = pd.DataFrame(rows)  # default RangeIndex, rows out of date order
    df["HistoricalDate"] = pd.to_datetime(
        df["HistoricalDate"], format="%d-%b-%Y", errors="coerce"
    )
    return df
