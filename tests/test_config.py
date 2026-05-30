"""U1: config scaffolding."""

import importlib
import os


def test_instruments_map():
    import config

    assert config.INSTRUMENTS["nifty"] == "NIFTY 50"
    assert config.INSTRUMENTS["banknifty"] == "NIFTY BANK"


def test_default_cash_above_banknifty():
    import config

    # Must sit well above BankNifty levels (~50k) to avoid the zero-trade trap.
    assert config.DEFAULT_CASH > 60_000


def test_import_creates_dirs_and_sets_cache_env():
    import config

    assert config.JDATA_CACHE_DIR.is_dir()
    assert config.RUNS_DIR.is_dir()
    assert os.environ["J_CACHE_DIR"]


def test_reimport_does_not_clobber_existing_cache_env(monkeypatch):
    monkeypatch.setenv("J_CACHE_DIR", "/tmp/preset-cache")
    import config

    importlib.reload(config)
    # setdefault must not overwrite an explicit env value.
    assert os.environ["J_CACHE_DIR"] == "/tmp/preset-cache"
