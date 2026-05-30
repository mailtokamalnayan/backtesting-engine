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
# Run a backtest (saves a new run every time). End date defaults to today.
.venv/bin/python run.py ema_cross --instrument nifty --n1 10 --n2 20 \
    --start 2018-01-01

# Tweak params and run again -> a second saved run
.venv/bin/python run.py ema_cross --instrument nifty --n1 20 --n2 50 \
    --start 2018-01-01

# Browse and compare every run
.venv/bin/python -m streamlit run dashboard.py
```

Cost model: a fixed **slippage** is applied to every fill (`config.DEFAULT_SLIPPAGE`,
default 0.5% per fill ≈ 1% round trip). Commission is not modeled separately. Change
that one constant to tune (e.g. `0.0005` for a futures-like 0.05%).

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
                dt.date(2022,1,1), source=KiteIntradaySource())  # end defaults to today
   ```

`turnaround_tuesday_intraday` trades **one Nifty futures lot** (`lot` units, default
65): on a weak Monday (price at 15:25 below the daily 9-EMA) it buys 1 lot at 15:25
and sells at 09:45 the next session unconditionally. Trade PnL is the rupee P&L of one
futures contract (points × lot), net of slippage.

## Methodological caveats — read before trusting a number

This harness is a fast idea-explorer, not a promise of real-world returns. It does
**not** protect you from the following, and you should discount results accordingly:

- **Index price as a futures proxy.** Backtests run on the index *level* series, used
  as a stand-in for the **futures** price. Strategies that trade futures (e.g.
  `turnaround_tuesday_intraday`) size in lots so PnL is per-contract rupees, and a
  fixed slippage is applied per fill. But the index level is **not** the futures price:
  futures **roll cost, basis, and expiry** are not modeled. Treat PnL as an
  approximation, not an executable statement.
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
