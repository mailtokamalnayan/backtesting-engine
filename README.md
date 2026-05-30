# Backtesting Engine

A local, single-user harness for backtesting **daily** trading strategies on Indian
indices (Nifty 50, Nifty Bank). You write a small Python strategy, run it from the
CLI, and every run is saved. A read-only Streamlit dashboard browses and compares all
your runs and their variations.

Built on [`backtesting.py`](https://kernc.github.io/backtesting.py/) (engine) and
[`jugaad-data`](https://github.com/jugaad-py/jugaad-data) (NSE daily index data).

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .          # installs deps from pyproject.toml
.venv/bin/python -m pip install -e ".[dev]"   # + pytest
```

## The loop

```bash
# Run a backtest (saves a new run every time)
.venv/bin/python run.py ema_cross --instrument nifty --n1 10 --n2 20 \
    --start 2018-01-01 --end 2024-12-31 --commission-pct 0.05

# Tweak params and run again -> a second saved run
.venv/bin/python run.py ema_cross --instrument nifty --n1 20 --n2 50 \
    --start 2018-01-01 --end 2024-12-31 --commission-pct 0.05

# Browse and compare every run
.venv/bin/python -m streamlit run dashboard.py
```

Commission: pass `--commission-pct` in **human percent** (`0.05` = 0.05% per side).
A raw `--commission` fraction is also accepted but guarded — values ≥ 0.1 are
rejected as a likely percent-vs-fraction mistake.

## Writing a strategy

Strategies are tiny `backtesting.py` `Strategy` subclasses registered by name. See
`strategies/ema_cross.py` for the worked example. Declare which params are bar
lookbacks via `lookback_params` so the engine can guard against too-short date ranges.

A strategy also declares two execution properties at registration (fixed per
strategy, so they don't change a run's identity):

- `trade_on_close` — `True` for signal-on-close strategies that fill on the signal
  bar's close (e.g. `turnaround_tuesday`); default `False` fills next-bar open.
- `interval` — the bar timeframe it needs (`"day"` default, or `"minute"` etc.). The
  runner fetches data at this interval; an intraday strategy run against a daily-only
  source fails clearly.

## Intraday via Zerodha Kite Connect

Daily data comes from `jugaad-data` (free, no auth). Intraday (minute) data comes
from **Kite Connect**, which requires a Zerodha account, an app, and a paid
historical-data subscription. Setup:

1. Create a Kite Connect app at https://developers.kite.trade/ with redirect URL
   `http://127.0.0.1`. Enable the historical-data add-on.
2. Export credentials (never commit them):
   ```bash
   export KITE_API_KEY=xxxx
   export KITE_API_SECRET=yyyy
   .venv/bin/python -m pip install -e ".[kite]"
   ```
3. Authenticate once (token saved to `.kite_token.json`, valid until ~7:30 AM next
   day):
   ```bash
   .venv/bin/python -m data.kite_auth
   ```
4. Run an intraday strategy — the runner fetches minute bars via `KiteIntradaySource`,
   chunking long ranges into 60-day windows and caching to `.kite_cache/`:
   ```python
   from data.kite_source import KiteIntradaySource
   from engine.runner import run_backtest
   import datetime as dt
   run_backtest("turnaround_tuesday_intraday", "nifty",
                dt.date(2022,1,1), dt.date(2024,12,31),
                commission=0.0005, source=KiteIntradaySource())
   ```

`turnaround_tuesday_intraday` enters at 15:25 on a weak Monday (price below the daily
9-EMA) and exits at 09:45 the next session — the overnight version of the daily rule.

## Methodological caveats — read before trusting a number

This harness is a fast idea-explorer, not a promise of real-world returns. It does
**not** protect you from the following, and you should discount results accordingly:

- **The spot index is not directly tradeable.** You cannot buy "NIFTY 50" at its
  close. Real exposure comes from **futures** (roll cost, basis, expiry), **index
  ETFs** like NIFTYBEES (tracking error, liquidity), or **options**. Results here run
  on the spot index *level* and approximate a frictionless index-tracking instrument.
  The commission models brokerage/slippage only — it does **not** model futures roll
  or ETF tracking error. Treat the headline number as an upper-bound approximation,
  not an executable P&L.
- **Fills are next-bar open.** A signal computed on today's close fills at tomorrow's
  open. Indian indices gap overnight, so realised fills can diverge meaningfully from
  the signal close — in either direction.
- **Survivorship is baked into the index.** Nifty/BankNifty are periodically
  reconstituted (losers dropped, winners added), so the index *level* already carries
  a survivorship tailwind. Long-horizon CAGR is flattered by this.
- **Saving many variations encourages overfitting.** The whole point of this tool is
  to try lots of param sets — which is also exactly how you fit to noise. A great
  backtest across 50 tweaks is weak evidence. Validate out-of-sample before believing.

## Clearing the data cache

jugaad-data caches fetched months as pickles under `.jdata_cache/`; Kite candles
cache to `.kite_cache/`. There is no force-refresh flag — delete the directory to
invalidate:

```bash
rm -rf .jdata_cache/ .kite_cache/
```

## Project layout

```
config.py          # paths, instrument map, defaults; sets J_CACHE_DIR
data/source.py     # DataSource interface + jugaad daily source
data/kite_source.py / kite_auth.py  # Kite Connect intraday/daily source + login
strategies/        # strategy registry + example strategies
engine/runner.py   # run_backtest(): the core run + save callable
engine/persistence.py  # SQLite run index + per-run artifact files
run.py             # CLI entry point
dashboard.py       # Streamlit read-only browser
results/           # index.sqlite + per-run artifacts (gitignored)
```
