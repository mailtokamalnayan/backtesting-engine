"""CLI parsing, source selection, and param sweeps."""

import datetime as dt

import pytest

import run
from data.source import JugaadDailySource
from data.kite_source import KiteIntradaySource


@pytest.fixture
def captured_calls(monkeypatch):
    calls = []

    def fake_run_backtest(strategy, instrument, start, end, params=None, source=None):
        calls.append(dict(strategy=strategy, instrument=instrument, start=start,
                          end=end, params=params, source=source))
        return f"{strategy}_fake_id"

    monkeypatch.setattr(run, "run_backtest", fake_run_backtest)
    return calls


BASE = ["ema_cross", "--start", "2023-01-01", "--end", "2023-12-31"]


def test_happy_path_passes_typed_args(captured_calls, capsys):
    rc = run.main(BASE + ["--instrument", "nifty", "--n1", "10", "--n2", "20"])
    assert rc == 0
    call = captured_calls[0]
    assert call["strategy"] == "ema_cross"
    assert call["instrument"] == "nifty"
    assert call["start"] == dt.date(2023, 1, 1)
    assert call["params"] == {"n1": 10, "n2": 20}  # coerced to int
    assert "saved 1 run" in capsys.readouterr().out


def test_default_instrument_and_params(captured_calls):
    run.main(BASE)
    call = captured_calls[0]
    assert call["instrument"] == "nifty"
    assert call["params"] == {"n1": 10, "n2": 20}


def test_end_defaults_to_today(captured_calls):
    run.main(["ema_cross", "--start", "2023-01-01"])  # no --end
    assert captured_calls[0]["end"] == dt.date.today()


def test_unknown_strategy_exits_nonzero(captured_calls):
    with pytest.raises(SystemExit) as exc:
        run.main(["nope", "--start", "2023-01-01", "--end", "2023-12-31"])
    assert exc.value.code != 0


def test_malformed_date_exits_nonzero(captured_calls):
    with pytest.raises(SystemExit) as exc:
        run.main(["ema_cross", "--start", "2023/13/40", "--end", "2023-12-31"])
    assert exc.value.code != 0


def test_daily_strategy_uses_jugaad_source(captured_calls):
    run.main(BASE)
    assert isinstance(captured_calls[0]["source"], JugaadDailySource)


def test_intraday_strategy_uses_kite_source(captured_calls):
    run.main(["turnaround_tuesday", "--start", "2023-01-01", "--end", "2023-12-31"])
    assert isinstance(captured_calls[0]["source"], KiteIntradaySource)


def test_sweep_expands_cartesian_product(captured_calls, capsys):
    run.main(BASE + ["--n1", "10,20", "--n2", "30,50"])
    combos = [c["params"] for c in captured_calls]
    assert len(combos) == 4  # 2 x 2 cartesian product
    assert {"n1": 10, "n2": 30} in combos
    assert {"n1": 20, "n2": 50} in combos
    assert "saved 4 run" in capsys.readouterr().out


def test_sweep_shares_one_source(captured_calls):
    run.main(BASE + ["--n1", "10,20,50"])
    sources = {id(c["source"]) for c in captured_calls}
    assert len(captured_calls) == 3
    assert len(sources) == 1  # one source object reused across the sweep


def test_uncoercible_token_fails_before_any_run(captured_calls):
    with pytest.raises(SystemExit) as exc:
        run.main(BASE + ["--n1", "10,oops"])
    assert exc.value.code != 0
    assert captured_calls == []  # rejected at parse time, nothing ran


def test_two_runs_differing_in_params(captured_calls):
    run.main(BASE + ["--n2", "30"])
    run.main(BASE + ["--n2", "50"])
    assert len(captured_calls) == 2
    assert captured_calls[0]["params"]["n2"] == 30
    assert captured_calls[1]["params"]["n2"] == 50
