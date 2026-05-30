"""Kite source: chunking, transform, caching, and clear failure modes (no live API)."""

import datetime as dt

import pandas as pd
import pytest

import data.kite_source as ksrc
from data.kite_source import KiteIntradaySource
from data.source import DataUnavailableError


class _FakeKite:
    """Records the (from, to) windows requested; returns one daily 09:15 bar each."""

    def __init__(self):
        self.windows = []

    def historical_data(self, token, frm, to, interval):
        self.windows.append((frm, to))
        out = []
        day = frm
        price = 100.0
        while day <= to:
            ts = pd.Timestamp(day).tz_localize("Asia/Kolkata") + pd.Timedelta(
                hours=9, minutes=15
            )
            out.append({"date": ts, "open": price, "high": price + 1,
                        "low": price - 1, "close": price, "volume": 0})
            day += dt.timedelta(days=1)
            price += 0.1
        return out


@pytest.fixture(autouse=True)
def cache_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(ksrc, "CACHE_DIR", tmp_path / "kc")


def test_chunking_splits_long_minute_range():
    fake = _FakeKite()
    src = KiteIntradaySource(kite=fake)
    df = src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 5, 10),
                          interval="minute")
    # 130 days / 60-day chunks -> 3 windows, contiguous and non-overlapping.
    assert len(fake.windows) == 3
    assert fake.windows[0][0] == dt.date(2023, 1, 1)
    assert fake.windows[1][0] == fake.windows[0][1] + dt.timedelta(days=1)
    assert not df.empty


def test_transform_normalizes_tz_and_sorts():
    df = KiteIntradaySource._to_df([
        {"date": pd.Timestamp("2023-01-02 15:25", tz="Asia/Kolkata"),
         "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 0},
        {"date": pd.Timestamp("2023-01-02 09:15", tz="Asia/Kolkata"),
         "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 0},
    ])
    assert list(df.columns) == ["Open", "High", "Low", "Close"]
    assert df.index.tz is None                      # tz dropped to IST wall-clock
    assert df.index.is_monotonic_increasing         # sorted
    assert df.index[0].time() == dt.time(9, 15)


def test_cache_reused_on_second_call():
    fake = _FakeKite()
    src = KiteIntradaySource(kite=fake)
    args = ("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 20), "minute")
    src.get_intraday(*args)
    calls_after_first = len(fake.windows)
    src.get_intraday(*args)  # identical -> served from Parquet cache
    assert len(fake.windows) == calls_after_first  # no new fetch


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    src = KiteIntradaySource()  # no injected client, no key
    with pytest.raises(DataUnavailableError, match="KITE_API_KEY"):
        src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 5))


def test_unknown_symbol_and_interval_raise():
    src = KiteIntradaySource(kite=_FakeKite())
    with pytest.raises(DataUnavailableError, match="instrument token"):
        src.get_intraday("DOW", dt.date(2023, 1, 1), dt.date(2023, 1, 2))
    with pytest.raises(DataUnavailableError, match="interval"):
        src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 2),
                         interval="tick")
