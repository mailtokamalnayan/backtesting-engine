"""Central configuration: paths, instrument map, and run defaults.

Importing this module sets ``J_CACHE_DIR`` so jugaad-data's built-in pickle
cache lands in a project-local directory. It MUST be imported before any
``jugaad_data`` import anywhere in the codebase, otherwise jugaad will pick its
default user-cache location. The data layer (``data/source.py``) imports config
first to honour this contract.
"""

import os
from pathlib import Path

# All paths resolve relative to the repo root (this file's directory).
ROOT = Path(__file__).resolve().parent

JDATA_CACHE_DIR = ROOT / ".jdata_cache"
RESULTS_DIR = ROOT / "results"
RUNS_DIR = RESULTS_DIR / "runs"
DB_PATH = RESULTS_DIR / "index.sqlite"

# Point jugaad-data's pickle cache at a project-local dir. setdefault so an
# explicit environment override (e.g. in tests) is never clobbered.
os.environ.setdefault("J_CACHE_DIR", str(JDATA_CACHE_DIR))

# Create the dirs jugaad and persistence need. Cheap and idempotent.
JDATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)

# Short CLI aliases -> exact niftyindices symbol strings. The only place these
# strings live.
INSTRUMENTS = {
    "nifty": "NIFTY 50",
    "banknifty": "NIFTY BANK",
}

# backtesting.py does not support fractional shares: if cash < price, buy()
# floors to zero units and silently opens no trade. Index levels are ~22k
# (Nifty) / ~50k (BankNifty), so cash must sit well above them.
DEFAULT_CASH = 10_000_000

# Per-side commission as a fraction (0.0005 == 0.05%). See run.py for the
# human-percent entry point and the percent-vs-fraction guard.
DEFAULT_COMMISSION = 0.0005
