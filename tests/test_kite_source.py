"""Kite source: freshness-aware cache, chunking, transform, failure modes (no live API)."""

import datetime as dt

import pandas as pd
import pytest

import data.kite_source as ksrc
from data.kite_source import KiteIntradaySource
from data.source import DataUnavailableError

TODAY = dt.date(2023, 6, 1)  # pinned "today" for the freshness boundary


class _FakeKite:
    """Records the (from, to) windows requested; returns one 09:15 bar per day."""

    def __init__(self, fail=False):
        self.windows = []
        self.fail = fail

    def historical_data(self, token, frm, to, interval):
        self.windows.append((frm, to))
        if self.fail:
            raise RuntimeError("kite blew up")
        out, day, price = [], frm, 100.0
        while day <= to:
            ts = pd.Timestamp(day).tz_localize("Asia/Kolkata") + pd.Timedelta(
                hours=9, minutes=15)
            out.append({"date": ts, "open": price, "high": price + 1,
                        "low": price - 1, "close": price, "volume": 0})
            day += dt.timedelta(days=1)
            price += 0.1
        return out


@pytest.fixture(autouse=True)
def cache_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(ksrc, "CACHE_DIR", tmp_path / "kc")
    monkeypatch.setattr(ksrc, "_today", lambda: TODAY)
    return tmp_path / "kc"


def _files(cache_dir):
    return sorted(p.name for p in cache_dir.iterdir()) if cache_dir.exists() else []


def test_first_call_fetches_and_writes_one_canonical_file(cache_in_tmp):
    fake = _FakeKite()
    src = KiteIntradaySource(kite=fake)
    df = src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 20),
                          interval="day")
    assert not df.empty
    assert len(fake.windows) == 1
    # canonical name has NO date range — one file per (symbol, interval)
    assert _files(cache_in_tmp) == ["NIFTY_50_day.parquet"]


def test_chunking_splits_long_minute_range():
    fake = _FakeKite()
    src = KiteIntradaySource(kite=fake)
    df = src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 5, 10),
                          interval="minute")
    # 130 days / 60-day chunks -> 3 windows, contiguous.
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
    assert df.index.tz is None
    assert df.index.is_monotonic_increasing
    assert df.index[0].time() == dt.time(9, 15)


def test_in_memory_hold_reuses_within_instance():
    fake = _FakeKite()
    src = KiteIntradaySource(kite=fake)
    args = ("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 20), "day")
    src.get_intraday(*args)
    after_first = len(fake.windows)
    src.get_intraday(*args)  # identical -> served from in-memory hold, no fetch
    assert len(fake.windows) == after_first


def test_closed_range_served_from_disk_no_fetch(cache_in_tmp):
    # Instance A populates the canonical file.
    a = _FakeKite()
    KiteIntradaySource(kite=a).get_intraday(
        "NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 3, 1), interval="day")
    # Instance B (fresh, no hold) requests a fully-closed covered range.
    b = _FakeKite()
    df = KiteIntradaySource(kite=b).get_intraday(
        "NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 3, 1), interval="day")
    assert len(b.windows) == 0          # immutable closed days -> no API call
    assert not df.empty


def test_trailing_window_refetched_when_end_is_today():
    # Cache already covers through today.
    a = _FakeKite()
    KiteIntradaySource(kite=a).get_intraday(
        "NIFTY 50", dt.date(2023, 1, 1), TODAY, interval="day")
    # New instance, same range ending today -> refetch ONLY the trailing window.
    b = _FakeKite()
    KiteIntradaySource(kite=b).get_intraday(
        "NIFTY 50", dt.date(2023, 1, 1), TODAY, interval="day")
    assert len(b.windows) == 1
    assert b.windows[0][0] == TODAY      # fetch_from == cached_max, not the start


def test_extend_forward_fetches_only_gap_one_file(cache_in_tmp):
    fake = _FakeKite()
    src = KiteIntradaySource(kite=fake)
    src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 20), "day")
    src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 2, 10), "day")
    # second fetch starts at the cached max (re-pulls last day + forward), not start
    assert fake.windows[1][0] == dt.date(2023, 1, 20)
    assert _files(cache_in_tmp) == ["NIFTY_50_day.parquet"]  # still one file


def test_older_gap_refetches_full_range():
    fake = _FakeKite()
    src = KiteIntradaySource(kite=fake)
    src.get_intraday("NIFTY 50", dt.date(2023, 2, 1), dt.date(2023, 3, 1), "day")
    src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 3, 1), "day")
    assert fake.windows[1][0] == dt.date(2023, 1, 1)  # start < cache min -> full


def test_fetch_failure_not_persisted_or_held(cache_in_tmp):
    fake = _FakeKite(fail=True)
    src = KiteIntradaySource(kite=fake)
    with pytest.raises(DataUnavailableError):
        src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 5), "day")
    assert _files(cache_in_tmp) == []            # nothing written
    assert ("NIFTY 50", "day") not in src._hold  # nothing held -> retry can succeed


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    src = KiteIntradaySource()
    with pytest.raises(DataUnavailableError, match="KITE_API_KEY"):
        src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 5))


def test_unknown_symbol_and_interval_raise():
    src = KiteIntradaySource(kite=_FakeKite())
    with pytest.raises(DataUnavailableError, match="instrument token"):
        src.get_intraday("DOW", dt.date(2023, 1, 1), dt.date(2023, 1, 2))
    with pytest.raises(DataUnavailableError, match="interval"):
        src.get_intraday("NIFTY 50", dt.date(2023, 1, 1), dt.date(2023, 1, 2),
                         interval="tick")
