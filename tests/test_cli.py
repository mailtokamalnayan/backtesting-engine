"""U6: CLI parsing, commission guard, validation."""

import datetime as dt

import pytest

import run


@pytest.fixture
def captured_calls(monkeypatch):
    calls = []

    def fake_run_backtest(strategy, instrument, start, end, params=None,
                          commission=None):
        calls.append(dict(strategy=strategy, instrument=instrument, start=start,
                          end=end, params=params, commission=commission))
        return "ema_cross_fake_id"

    monkeypatch.setattr(run, "run_backtest", fake_run_backtest)
    return calls


BASE = ["ema_cross", "--start", "2023-01-01", "--end", "2023-12-31"]


def test_happy_path_passes_typed_args(captured_calls, capsys):
    rc = run.main(BASE + ["--instrument", "nifty", "--n1", "10", "--n2", "20",
                          "--commission-pct", "0.05"])
    assert rc == 0
    call = captured_calls[0]
    assert call["strategy"] == "ema_cross"
    assert call["instrument"] == "nifty"
    assert call["start"] == dt.date(2023, 1, 1)
    assert call["params"] == {"n1": 10, "n2": 20}  # coerced to int
    assert call["commission"] == pytest.approx(0.0005)  # 0.05% -> fraction
    assert "ema_cross_fake_id" in capsys.readouterr().out


def test_default_instrument_and_params(captured_calls):
    run.main(BASE)
    call = captured_calls[0]
    assert call["instrument"] == "nifty"
    assert call["params"] == {"n1": 10, "n2": 20}
    assert call["commission"] == pytest.approx(0.0005)  # default


def test_commission_fraction_footgun_rejected(captured_calls):
    # 0.1 as a fraction = 10% per side; the classic percent-vs-fraction mistake.
    with pytest.raises(SystemExit) as exc:
        run.main(BASE + ["--commission", "0.1"])
    assert exc.value.code != 0
    assert captured_calls == []  # never reached run_backtest


def test_unknown_strategy_exits_nonzero(captured_calls):
    with pytest.raises(SystemExit) as exc:
        run.main(["nope", "--start", "2023-01-01", "--end", "2023-12-31"])
    assert exc.value.code != 0


def test_malformed_date_exits_nonzero(captured_calls):
    with pytest.raises(SystemExit) as exc:
        run.main(["ema_cross", "--start", "2023/13/40", "--end", "2023-12-31"])
    assert exc.value.code != 0


def test_two_runs_differing_in_params(captured_calls):
    run.main(BASE + ["--n2", "30"])
    run.main(BASE + ["--n2", "50"])
    assert len(captured_calls) == 2
    assert captured_calls[0]["params"]["n2"] == 30
    assert captured_calls[1]["params"]["n2"] == 50
