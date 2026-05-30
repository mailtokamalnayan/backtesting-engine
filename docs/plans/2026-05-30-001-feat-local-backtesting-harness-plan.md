---
title: "feat: Local Backtesting Harness for Nifty/BankNifty"
type: feat
status: completed
date: 2026-05-30
deepened: 2026-05-30
origin: docs/brainstorms/local-backtesting-harness-requirements.md
---

# feat: Local Backtesting Harness for Nifty/BankNifty

## Summary

Build a greenfield, local, single-user Python harness that runs daily-bar backtests of Nifty/BankNifty index strategies on `backtesting.py`, fed by a `jugaad-data` source (cached via jugaad's own per-month pickle cache), and persists every run to a SQLite index plus per-run artifact files. Runs are triggered from code/CLI; a read-only Streamlit dashboard browses and compares all saved runs and their variations. Seven dependency-ordered units: scaffold → data layer → strategy registry → persistence → run engine → CLI → dashboard.

---

## Problem Frame

The user wants a fast, repeatable loop for testing trading ideas on Indian indices and a durable, browsable record of every variation tried, in a minimal local form (see origin: `docs/brainstorms/local-backtesting-harness-requirements.md`). This plan is the HOW: how the run/save/browse loop is assembled from the settled stack.

---

## Requirements

**Strategy definition**
- R1. Strategies are small Python `backtesting.py` `Strategy` subclasses with tunable params, registered by name.
- R2. Ship at least one worked example strategy so the loop is usable on day one.

**Data**
- R3. Daily OHLC for Nifty/BankNifty sourced via `jugaad-data`, cached locally so a given symbol+range is fetched at most once.
- R4. Data access sits behind a thin source interface so an intraday provider can be added later without touching strategy/engine code.

**Execution**
- R6. A run applies a single configurable commission, over a chosen instrument/date-range/param-set.
- R7. Each run produces CAGR, max drawdown, win-rate, Sharpe, # trades, the trade list, and an equity curve (persisted as `equity.parquet`).

**Persistence**
- R5. Re-running with different params creates a new saved run; runs are never overwritten.
- R8. Every run persists as a row in a single local index plus per-run artifact files.
- R9. A run is identified by strategy + params + instrument + date range + **commission** (the full set of result-affecting inputs; `cash` and fill mode are fixed constants — see Key Technical Decisions).

**Dashboard**
- R10. A local web dashboard shows a sortable/filterable table of all runs with key metrics.
- R11. Selecting a run opens a detail view: equity curve + trade list.

**Origin actors:** single user — writes strategies, triggers runs via CLI, browses the dashboard.
**Origin flows:** F1 (Run a new backtest), F2 (Tweak and compare variations).
**Origin acceptance examples:** AE1 (covers R3 — cache hit avoids network re-fetch), AE2 (covers R5, R8 — new params = new row, original unchanged), AE3 (covers R6, R7 — returns are net of commission).

---

## Scope Boundaries

- Options strategies / options-chain data — out.
- Intraday/minute data sourcing — `DataSource` seam is built (R4, U2) but no intraday source is implemented.
- Detailed Indian cost modeling (STT/GST/stamp itemized) — out; single commission fraction stands in.
- Hosting, multi-user, auth, cloud — out; local-only.
- Live/paper trading, broker/order integration — out.
- Multi-instrument/portfolio backtests in one run — out; one instrument per run.
- Running or tweaking backtests *from the dashboard UI* — out for v0; dashboard is read-only. The run engine is a plain callable, so a dashboard run-form is a clean future addition.
- **Equity-curve comparison across runs** — out for v0; the detail view shows one run at a time. The table compares scalar metrics across variations; visual curve-overlay is deferred (see below).

### Deferred to Follow-Up Work

- **Inspectable/portable Parquet cache layer** — v0 relies on jugaad's built-in pickle cache only; a project-local Parquet mirror (for inspection/portability) is a future addition.
- **Param-sweep / `bt.optimize` integration** for bulk variation generation — core loop is manual re-runs.
- **Equity-curve comparison view** — minimal future form: a multiselect on the runs table that overlays selected runs' equity series on one `st.line_chart`.
- **`config_hash` grouping/flagging in the dashboard** — the `config_hash` column is stored (for manual dedup via `SELECT`), but no dashboard grouping UI in v0.
- **Per-run standalone Bokeh `report.html`** — the dashboard renders the equity curve from `equity.parquet`; a standalone HTML report is a future nicety.
- **Second example strategy** (e.g. RSI mean-reversion) — v0 ships one (EMA crossover); more can follow.

---

## Context & Research

### Relevant Code and Patterns

Greenfield — no existing code. Library facts below are verified against live source (backtesting.py 0.6.5, jugaad-data 0.33.1) and are authoritative.

**`backtesting.py` 0.6.5** (PyPI `backtesting`, Python 3.9+; transitively pulls `pandas`, `numpy`, `bokeh`):
- Strategy = subclass `backtesting.Strategy`, implement `init()` (register indicators via `self.I(func, ...)`) and `next()` (trade via `self.buy()/self.sell()/self.position.close()`). `backtesting.lib.crossover(a, b)` for crossovers.
- `Backtest(data, strategy, cash=, commission=, trade_on_close=, exclusive_orders=, finalize_trades=)`. Input DataFrame must have **exact title-case** columns `Open/High/Low/Close` (+ optional `Volume`) and a `DatetimeIndex`. Lowercase columns raise `ValueError`; **any NaN OHLC raises `ValueError`** (`backtesting.py:1227`).
- **`cash` must exceed the price** — backtesting.py does not support fractional shares, so `np.any(Close > cash)` warns and `self.buy()` floors to **zero units → no trade** (`backtesting.py:1231`). Index levels are ~22,000 (Nifty) / ~50,000 (BankNifty), so `cash` must be set well above these.
- **Indicator warmup:** the run loop starts at `1 + _indicator_warmup_nbars(strategy)` (`backtesting.py:1318`). If the date range has fewer bars than the slowest indicator lookback, `next()` **never fires → zero trades, no exception**.
- `commission` is a **fraction** (`0.0005` = 0.05%), charged **per-side** (round-trip ≈ 2×), and the library **asserts `-0.1 <= commission < 0.1`** (`backtesting.py:759`) — a value ≥ 0.1 raises `AssertionError`.
- `bt.run(**params)` overrides strategy class attributes and returns a `pd.Series` of stats. **Exact native stat keys:** `'CAGR [%]'`, `'Return [%]'`, `'Max. Drawdown [%]'` (reported as a **negative** number), `'Win Rate [%]'`, `'Sharpe Ratio'`, `'Sortino Ratio'`, `'Profit Factor'`, `'# Trades'`, `'Equity Final [$]'`. CAGR is native — no derivation needed.
- `stats['_trades']` (DataFrame) and `stats['_equity_curve']` (DataFrame indexed by timestamp: `Equity, DrawdownPct, DrawdownDuration`) are the artifact sources.
- Always set `finalize_trades=True` and `exclusive_orders=True`; default fill is **next-bar Open** (`trade_on_close=False`) — realistic for EOD daily signals.

**`jugaad-data` 0.33.1** (PyPI `jugaad-data`, Python 3.9+; **pandas is NOT a declared dep — add explicitly**):
- `from jugaad_data.nse import index_df` → `index_df(symbol, from_date, to_date)`. Symbols: `"NIFTY 50"`, `"NIFTY BANK"` (exact, case-sensitive). `from_date`/`to_date` are `datetime.date` objects.
- Returns columns `INDEX_NAME, HistoricalDate, OPEN, HIGH, LOW, CLOSE` (**UPPERCASE, no Volume**), a **RangeIndex (not Datetime)**, rows **NOT sorted ascending**, and `HistoricalDate` can be `NaT` for an unparseable row (`util.py:36`).
- Hits niftyindices.com directly with **no retry logic**; chunks the range per-month via a 2-thread pool, and a single failed month aborts the whole call. Has a **built-in per-month pickle disk cache** keyed by `symbol-from-to`, relocatable via the `J_CACHE_DIR` env var (no `--force`; delete files to invalidate). Successful month-chunks are cached even if a later chunk fails, so a retry only re-hits the failed month.
- Required transform before feeding `backtesting.py`: rename `OPEN/HIGH/LOW/CLOSE` → `Open/High/Low/Close`, `set_index('HistoricalDate')` as `DatetimeIndex`, `sort_index()`, **`dropna()`**, validate non-empty.

### Institutional Learnings

None — no `docs/solutions/` in this greenfield repo.

### External References

- backtesting.py docs: https://kernc.github.io/backtesting.py/ · repo: https://github.com/kernc/backtesting.py
- jugaad-data repo: https://github.com/jugaad-py/jugaad-data · docs: https://marketsetup.in/documentation/jugaad-data/

---

## Key Technical Decisions

- **Single cache layer — jugaad's built-in pickle cache (R3):** `get_daily` calls `index_df` + transform each time; jugaad's per-month pickle cache (relocated to project-local `.jdata_cache/` via `J_CACHE_DIR`) serves already-fetched months from disk with no network call, satisfying R3 and AE1. **No bespoke Parquet/coverage/merge layer** — it was the plan's biggest complexity hotspot and could silently feed the engine a date-gapped series; dropped for v0 (a portable Parquet mirror is deferred). Hard requirement: `config` must be imported before any `jugaad_data` import so `J_CACHE_DIR` is set first.
- **`DataSource` abstract seam (R4):** A single `get_daily(symbol, start, end) -> DataFrame` interface, implemented now only by `JugaadDailySource`. Intraday slots in later as a sibling implementation; engine/strategies depend on the interface, never on `jugaad_data` directly.
- **Fixed `cash` and fill mode (correctness + identity):** `cash` is a constant (`DEFAULT_CASH`, set well above index price to avoid the zero-trade trap) and fill mode is hard-coded (`trade_on_close=False`, `exclusive_orders=True`, `finalize_trades=True`). These are correctness settings, not user knobs — which keeps run identity clean: the only result-affecting inputs are strategy, params, instrument, date range, and commission.
- **Append-always run identity (R5, R9):** Every run gets a unique `run_id`; `config_hash = stable_hash(strategy, params, instrument, start, end, commission)` is stored (not unique-constrained) for manual dedup. Identical re-runs append a new row — never overwrite, never silently skip.
- **Denormalized hot metrics + full-stats JSON (R8, R10):** The `runs` table stores key metrics inline (cagr, return_pct, max_drawdown, win_rate, sharpe, num_trades, final_equity) **and** the complete stats series as a `stats_json` column. The dashboard table is one fast query over the hot columns, but any other native metric (Sortino, Profit Factor, …) is still sortable/filterable via `json_extract` — no schema migration ever needed. Full trades + equity live in per-run files for the detail view.
- **Atomic artifact write (consistency):** `save_run` writes artifacts to a temp dir, `os.rename`s it into place, then inserts the index row — so a crash leaves no partial dir and no index row pointing at missing files.
- **Commission ergonomics (footgun guard):** Internally commission is a fraction (per-side). The CLI accepts `--commission-pct` (human percent, divided by 100) as the primary path and validates `0 <= fraction < 0.1`, rejecting likely percent-vs-fraction errors with a clear message. This prevents the 100× cost mistake that would make a good strategy look catastrophic.
- **Methodological honesty (avoid silent mislead):** The spot index is **not directly tradeable** (you'd trade futures/ETF/options, each with different cost/price behavior). README + `run_backtest` docstring + a dashboard note state that results approximate a frictionless index-tracking instrument and ignore futures roll/basis and ETF tracking error, and flag survivorship (baked into the index level) and overfitting-by-search (which saving many variations encourages). Cheap caveat; converts a silent lie into a stated approximation.
- **Streamlit reads `_equity_curve` data, not Bokeh:** Persist the equity curve as `equity.parquet` and render via `st.line_chart`; no `bt.plot()` Bokeh artifact in v0.

---

## Open Questions

### Resolved During Planning

- jugaad-data daily index support (origin deferred): **Resolved** — `index_df("NIFTY 50"/"NIFTY BANK", from_date, to_date)` confirmed against source, deep history available.
- Cache layout (origin deferred): **Resolved** — jugaad's built-in pickle cache only, relocated via `J_CACHE_DIR`; bespoke Parquet layer dropped for v0 (deferred).
- Run index schema + dedup behavior (origin deferred): **Resolved** — single `runs` table, denormalized hot metrics + `stats_json`, append-always with `config_hash`. See U4.
- Metric subset (origin deferred): **Resolved** — hot columns drive the table; `stats_json` keeps every other metric sortable. See Key Technical Decisions.
- Run identity / `cash` / fill mode (review): **Resolved** — `cash` and fill mode fixed; identity = strategy+params+instrument+range+commission.

### Deferred to Implementation

- Exact `run_id` format (timestamp string vs short hash) — must be filesystem-safe (names the artifact dir) and sortable. Decide in U4.
- Exact `DEFAULT_CASH` value — any value safely above BankNifty levels (e.g. 10,000,000). Decide in U1.
- Exact Streamlit row-selection widget (`st.dataframe` selection vs `st.data_editor`) — settle against the installed version in U7.
- Exact warmup-buffer math in the min-bars guard — derive required bars from the strategy's declared lookback params plus a small buffer. Decide in U3/U5.

---

## Output Structure

    backtesting-engine-v0/
      pyproject.toml            # deps: backtesting==0.6.5, jugaad-data>=0.33.1, pandas, pyarrow, streamlit
      README.md                 # run + tweak loop; methodological caveats; cache-clear instructions
      config.py                 # paths, INSTRUMENTS map, DEFAULT_CASH, DEFAULT_COMMISSION; sets J_CACHE_DIR
      data/
        __init__.py
        source.py               # DataSource ABC + JugaadDailySource (transform + retry, jugaad cache)
      strategies/
        __init__.py             # registry: name -> Strategy class + param_spec (incl. lookback params)
        ema_cross.py            # example strategy (U3)
      engine/
        __init__.py
        runner.py               # run_backtest(): data + strategy + backtesting.py -> stats; min-bars guard
        persistence.py          # SQLite index (hot cols + stats_json) + atomic artifact writer
      run.py                    # CLI entry point
      dashboard.py              # Streamlit read-only browser
      tests/
        conftest.py             # shared fixtures: synthetic OHLC frame + raw jugaad-shaped frame
        test_source.py
        test_strategies.py
        test_persistence.py
        test_runner.py
        test_cli.py
      .jdata_cache/             # jugaad pickle cache via J_CACHE_DIR (gitignored)
      results/
        index.sqlite            # the runs index
        runs/<run_id>/          # params.json, metrics.json, trades.csv, equity.parquet

*Scope declaration, not a constraint — the implementer may adjust layout. Per-unit `Files:` lists are authoritative.*

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
            run.py (CLI)                         dashboard.py (Streamlit, read-only)
                |                                          |
       parse + commission guard                  reads results/index.sqlite --> table (R10)
       (--commission-pct -> fraction)             (hot cols; json_extract for others)
                v                                          |
        engine/runner.run_backtest                 select run row
                |                                          v
   +------------+--------------+----------+      reads results/runs/<id>/ --> equity + trades (R11)
   |            |              |          |
   v            v              v          v
data.source  strategies   min-bars     backtesting.py
get_daily()  registry[name] guard       Backtest(cash=DEFAULT_CASH, commission,
   |          (+param_spec   (raise       trade_on_close=False, exclusive_orders=True,
   v           lookback)     Insufficient  finalize_trades=True).run(**params)
jugaad index_df            DataError)         |
+ transform (rename/sort/                      v
 dropna/validate); jugaad             stats (pd.Series) --> engine/persistence
 pickle cache via J_CACHE_DIR         _trades, _equity_curve        |
 (no network on cache hit)                                          v
                                       write artifacts to tmp -> rename ->
                                       INSERT runs row (hot metrics + stats_json)  (R5, R8)
```

F1 (run): CLI parses + guards commission → `run_backtest` pulls a daily DataFrame, checks min-bars, instantiates the registered `Strategy`, runs `Backtest`, extracts stats → persistence atomically writes artifacts + appends a SQLite row. F2 (compare): re-run with new params appends another row; dashboard reads SQLite → table → row selection → artifact detail view.

---

## Implementation Units

- U1. **Project scaffold, dependencies, and config**

**Goal:** Establish the package layout, dependency manifest, shared paths/constants, instrument map, and the `J_CACHE_DIR` wiring so all later units have a stable foundation.

**Requirements:** Supports R1–R11 (foundational).

**Dependencies:** None.

**Files:**
- Create: `pyproject.toml` (deps: `backtesting==0.6.5`, `jugaad-data>=0.33.1`, `pandas`, `pyarrow`, `streamlit`)
- Create: `config.py` (repo-root paths for `.jdata_cache/`, `results/`; `INSTRUMENTS = {"nifty": "NIFTY 50", "banknifty": "NIFTY BANK"}`; `DEFAULT_CASH` set well above BankNifty levels (e.g. 10,000,000); `DEFAULT_COMMISSION = 0.0005`)
- Create: `.gitignore` (`.jdata_cache/`, `results/`, `__pycache__/`)
- Create: `README.md` (run + tweak-loop usage; **methodological caveats** — spot not directly tradeable, survivorship, overfitting; cache-clear instructions)
- Create: `__init__.py` for `data/`, `strategies/`, `engine/`

**Approach:**
- `config.py` resolves all paths relative to the repo root and sets `os.environ.setdefault("J_CACHE_DIR", <.jdata_cache abs path>)` **at import**, before any `jugaad_data` import anywhere, so jugaad's cache lands project-local. Creates `.jdata_cache/` and `results/` on import if missing.
- `INSTRUMENTS` is the only place symbol strings live.
- README's caveats section is load-bearing (methodological honesty decision), not boilerplate.

**Patterns to follow:** Constants centralized in one module; import-ordering contract documented.

**Test scenarios:**
- Happy path: importing `config` creates `.jdata_cache/` and `results/` if absent and sets `J_CACHE_DIR`.
- Happy path: `INSTRUMENTS["nifty"] == "NIFTY 50"`, `INSTRUMENTS["banknifty"] == "NIFTY BANK"`; `DEFAULT_CASH > 60000` (above BankNifty).
- Edge case: importing `config` twice does not error and does not clobber a pre-existing `J_CACHE_DIR` from the environment.

**Verification:** `python -c "import config"` runs clean; dirs exist; `J_CACHE_DIR` is set to a project-local absolute path.

---

- U2. **Data layer: `DataSource` interface and jugaad daily source**

**Goal:** Provide a clean, `backtesting.py`-ready daily OHLC DataFrame for a symbol+range, behind an interface future intraday sources can implement, with no network call on a cache hit.

**Requirements:** R3, R4. Covers AE1.

**Dependencies:** U1.

**Files:**
- Create: `data/source.py` (`DataSource` ABC with `get_daily(symbol, start, end) -> pd.DataFrame`; `JugaadDailySource` with transform + retry; `DataUnavailableError`)
- Test: `tests/test_source.py`

**Approach:**
- `DataSource` ABC defines `get_daily(symbol, start, end)`. `JugaadDailySource` implements it; nothing else imports `jugaad_data`.
- `get_daily`: import `config` first (ensures `J_CACHE_DIR`), call `index_df(symbol, from_date, to_date)`, then the **transform pipeline**: rename `OPEN/HIGH/LOW/CLOSE` → `Open/High/Low/Close`, `set_index('HistoricalDate')` as `DatetimeIndex`, `sort_index()`, **`dropna()`** (drops `NaT`/NaN rows that would hard-raise in backtesting.py), keep `Open/High/Low/Close`, validate non-empty.
- **No bespoke cache** — jugaad's per-month pickle cache (in `.jdata_cache/`) serves fetched months with no network call. R3/AE1 hold at the month-chunk level.
- **Resilience:** wrap `index_df` in retry-with-backoff (jugaad has none); on empty/malformed payload after retries, raise `DataUnavailableError` naming symbol + range.
- Accept `datetime.date`; CLI converts strings upstream (U6).

**Patterns to follow:** ABC seam (engine never imports jugaad). Transform recipe from Context & Research.

**Test scenarios:**
- Covers AE1. Integration: with a populated `.jdata_cache/` (jugaad cache) for the requested range, `get_daily` returns data and makes **no network call** (spy on the underlying fetch).
- Happy path: a fetch (jugaad call mocked to a raw UPPERCASE, unsorted, RangeIndex frame from the shared fixture) yields exactly `Open/High/Low/Close`, a sorted `DatetimeIndex`, ascending dates.
- Edge case: a raw frame containing a `NaT`/NaN row has that row dropped by `dropna()`; the returned frame has no NaN OHLC.
- Error path: jugaad raises on first attempt then succeeds → retry recovers.
- Error path: jugaad returns empty/malformed on all attempts → `DataUnavailableError` naming symbol + range.
- Edge case: empty result after transform raises rather than returning an empty frame to the engine.

**Verification:** `get_daily("NIFTY 50", date(2023,1,1), date(2023,6,30))` returns a sorted, NaN-free OHLC `DatetimeIndex` frame; a second identical call makes no network call.

---

- U3. **Strategy registry and example strategy**

**Goal:** Let users define strategies as small `backtesting.py` `Strategy` subclasses with declared tunable params (including which are bar-lookbacks), discoverable by name; ship one worked example.

**Requirements:** R1, R2.

**Dependencies:** U1.

**Files:**
- Create: `strategies/__init__.py` (registry: `register(name, cls, param_spec)` / `get(name)` / `available()`; `STRATEGIES` mapping)
- Create: `strategies/ema_cross.py` (`EmaCross(Strategy)` with `n1`, `n2`; `init()` registers two EMAs via `self.I`; `next()` uses `crossover`)
- Test: `tests/test_strategies.py`

**Approach:**
- Each strategy module defines a `Strategy` subclass with tunable params as class attributes (so `bt.run(**params)` overrides work) and registers a `param_spec`: per-param type/default **and** a `lookback_params` list naming the params that are bar-lookbacks (so U5 can compute the minimum bars required). For `EmaCross`, `lookback_params = ["n1", "n2"]`.
- `EmaCross`: `init()` builds `self.I(EMA, self.data.Close, n)` for `n1`/`n2`; `next()` buys on `crossover(fast, slow)`, sells on the inverse. Engine sets `exclusive_orders=True` so opposite signals flip.
- Registry `available()` feeds CLI help / dashboard labels.

**Patterns to follow:** backtesting.py idiom from Context & Research (`self.I`, `backtesting.lib.crossover`, title-case `self.data.Close`).

**Test scenarios:**
- Happy path: `get("ema_cross")` returns `EmaCross`; `available()` lists `"ema_cross"`.
- Happy path: `EmaCross` exposes `n1`/`n2` as overridable class attributes; its `param_spec` declares types/defaults and `lookback_params == ["n1","n2"]`.
- Edge case: `get("nope")` raises a clear error listing available names.
- Integration: running `EmaCross` over the shared synthetic uptrend→downtrend OHLC fixture (prices below a test `cash`) through `Backtest(...).run()` produces ≥1 trade (proves indicators register and `next()` fires past warmup).

**Verification:** `ema_cross` is registered, instantiable, declares its lookbacks, and trades on the trending fixture.

---

- U4. **Persistence: SQLite run index and atomic artifact writer**

**Goal:** Append each run to a single SQLite index (hot metrics + full-stats JSON), write per-run artifacts atomically, never overwriting prior runs.

**Requirements:** R5, R8, R9. Covers AE2.

**Dependencies:** U1.

**Files:**
- Create: `engine/persistence.py` (`init_db()`, `save_run(...) -> run_id`, `list_runs() -> DataFrame`, `load_run_artifacts(run_id)`)
- Test: `tests/test_persistence.py`

**Approach:**
- `runs` columns: `run_id` (PK, filesystem-safe sortable id), `strategy`, `instrument`, `params_json`, `start_date`, `end_date`, `commission`, `config_hash`, `created_at`, `artifact_dir`, denormalized hot metrics (`cagr`, `return_pct`, `max_drawdown`, `win_rate`, `sharpe`, `num_trades`, `final_equity`), and `stats_json` (full stats series, minus the `_trades`/`_equity_curve`/`_strategy` objects).
- `config_hash = stable_hash(strategy, params, instrument, start, end, commission)` — stored, **not** unique-constrained (append-always per R5).
- Hot metrics pulled by exact stat keys (`'CAGR [%]'`→`cagr`, `'Max. Drawdown [%]'`→`max_drawdown` (stored as backtesting.py reports it — negative), `'Win Rate [%]'`→`win_rate`, `'Sharpe Ratio'`→`sharpe`, `'# Trades'`→`num_trades`, `'Return [%]'`→`return_pct`, `'Equity Final [$]'`→`final_equity`). Missing keys store null, not crash.
- **Atomic write:** write `params.json`, `metrics.json`, `trades.csv` (from `_trades`), `equity.parquet` (from `_equity_curve`) into `results/runs/.<run_id>.tmp/`, then `os.rename` to `results/runs/<run_id>/`, **then** INSERT the row.
- `init_db()` is idempotent and is called defensively at the top of `save_run` and `list_runs` (no separate bootstrap step needed).

**Patterns to follow:** stdlib `sqlite3`; JSON for params/stats; pyarrow Parquet for equity. No ORM.

**Test scenarios:**
- Covers AE2. Integration: save run A (`n1=20,n2=50`), then run B (`n1=10,n2=30`) → `list_runs()` returns two distinct rows; A's metrics and artifact files are unchanged after B.
- Happy path: `save_run` creates `results/runs/<run_id>/` with all four files and a row whose hot metrics equal the stats values and whose `stats_json` round-trips the full series.
- Happy path: a non-hot metric (e.g. `'Sortino Ratio'`) is recoverable from `stats_json` via `json_extract` (proves the no-migration claim).
- Edge case: identical config saved twice → two rows, **same `config_hash`, different `run_id`** (append-always).
- Edge case: `save_run` called on a fresh DB (no prior `init_db`) creates the table and succeeds (defensive init).
- Error path: a stats series missing an expected hot key stores null and does not crash.
- Error path (atomicity): a simulated failure mid-artifact-write leaves no `results/runs/<run_id>/` dir and no index row (only a `.tmp` dir, if anything).

**Verification:** Two runs persist as separate rows + dirs; fresh-DB save works; hot metrics match artifacts; any stat is queryable via `stats_json`.

---

- U5. **Run engine: `run_backtest`**

**Goal:** Tie data + strategy + `backtesting.py` into one callable that executes a backtest with fixed cash/fill mode and a configurable commission, guards against insufficient data, and saves the run.

**Requirements:** R6, R7, R9. Covers AE3.

**Dependencies:** U2, U3, U4.

**Files:**
- Create: `engine/runner.py` (`run_backtest(strategy_name, instrument, start, end, params=None, commission=DEFAULT_COMMISSION) -> run_id`; `InsufficientDataError`)
- Test: `tests/test_runner.py`

**Approach:**
- Resolve `instrument` alias → jugaad symbol via `config.INSTRUMENTS`; pull data via `DataSource` (U2); resolve strategy class + `param_spec` via the registry (U3).
- **Min-bars guard:** compute required bars from the strategy's `lookback_params` against the effective params (e.g. `max(n1, n2)`) plus a small buffer; if `len(df) <= required`, raise `InsufficientDataError` naming bars-available vs bars-required — **before** `bt.run()`.
- **Cash guard:** assert `cash > df['Close'].max()` (using `config.DEFAULT_CASH`); on failure raise a clear error (defends the zero-trade trap).
- Build `Backtest(df, StrategyCls, cash=DEFAULT_CASH, commission=commission, trade_on_close=False, exclusive_orders=True, finalize_trades=True)`; execute `bt.run(**params)`.
- Extract `stats`, `_trades`, `_equity_curve`; hand to `persistence.save_run` (U4); return `run_id`. `cash` and fill mode are fixed constants here (not params), keeping run identity = strategy+params+instrument+range+commission.
- Commission is a fraction; bounds validation lives at the CLI boundary (U6), but `run_backtest` re-asserts `0 <= commission < 0.1` defensively (library asserts too).

**Patterns to follow:** backtesting.py run/stats extraction from Context & Research. Docstring states commission is a per-side fraction and that fills are next-bar-open on the spot index (methodological caveat).

**Test scenarios:**
- Covers AE3. Integration: a run with `commission=0.01` vs the same with `commission=0` yields a strictly lower `Equity Final [$]`; saved `metrics.json` reflects the net figures.
- Happy path: `run_backtest("ema_cross", "nifty", start, end, {"n1":10,"n2":20})` (data source mocked to the deterministic fixture) returns a `run_id` and a populated row.
- Edge case: `params=None` runs with the strategy's default class-attribute params.
- Error path: a date range shorter than `max(n1,n2)` raises `InsufficientDataError` naming available vs required bars (not a silent zero-trade).
- Error path: `cash` below `max(Close)` raises the cash guard (proves the zero-trade trap is closed).
- Error path: unknown `instrument` or `strategy_name` raises a clear error before any fetch/run.

**Verification:** A full `run_backtest` over a cached Nifty range saves a complete run; commission reduces final equity; too-short ranges and bad cash fail loudly.

---

- U6. **CLI entry point (`run.py`)**

**Goal:** Trigger and re-run backtests from the terminal, tweaking params, each invocation saving a new run, with a commission-ergonomics guard.

**Requirements:** R5, R6, R9. Covers F1, F2.

**Dependencies:** U5.

**Files:**
- Create: `run.py` (argument parsing → `run_backtest`)
- Test: `tests/test_cli.py`

**Approach:**
- Args: positional `strategy`; `--instrument` (alias, default `nifty`); `--start`/`--end` (ISO dates → `datetime.date`); strategy params as `--key value` (coerced via `param_spec`) or `key=value`.
- **Commission:** primary `--commission-pct` (human percent; divided by 100) and/or `--commission` (raw fraction). Validate the resulting fraction is `0 <= f < 0.1`; reject likely percent-vs-fraction errors with a message (e.g. "`--commission 0.1` = 10% per side; did you mean `--commission-pct 0.1`?"). Default = `DEFAULT_COMMISSION`.
- No `--cash` or `--trade-on-close` flags (fixed constants — keeps the loop simple and identity clean).
- Validate strategy + instrument against the registry / `INSTRUMENTS` before running; on success print the `run_id` and headline metrics (CAGR, Max DD) plus a one-line reminder that fills are next-bar-open on the (untradeable) spot index.
- Thin layer — all logic in `run_backtest`.

**Patterns to follow:** stdlib `argparse`. Date parsing to `datetime.date`.

**Test scenarios:**
- Happy path: `run.py ema_cross --instrument nifty --n1 10 --n2 20 --start 2023-01-01 --end 2023-12-31` (with `run_backtest` mocked) calls it once with correctly-typed args and prints the `run_id`.
- Happy path: `--commission-pct 0.1` passes `commission=0.001` to `run_backtest`; param coercion turns `--n1 10` into `int 10`.
- Error path: `--commission 0.1` (fraction ≥ 0.1) exits non-zero with the percent-vs-fraction message (closes the 100× footgun).
- Edge case: omitting params runs with strategy defaults; omitting `--instrument` defaults to `nifty`.
- Error path: invalid strategy name exits non-zero listing available strategies; malformed date exits non-zero with a clear parse error.
- Edge case (F2): two invocations differing only in `--n2` each call `run_backtest` → two saved runs.

**Verification:** Running the CLI twice with different params produces two saved runs; the commission footgun and bad input fail fast with helpful messages.

---

- U7. **Streamlit dashboard (read-only browse + detail)**

**Goal:** Browse, sort, and compare all saved runs in a table, and drill into any run's equity curve and trades.

**Requirements:** R10, R11. Covers F2.

**Dependencies:** U4 (schema/artifacts); meaningful once U5/U6 have produced runs.

**Files:**
- Create: `dashboard.py` (Streamlit app reading `results/index.sqlite` + artifacts)
- Test: `tests/test_dashboard.py` (pure-helper logic; e2e is manual)

**Approach:**
- Load `persistence.list_runs()` into a sortable table. **Default sort: `created_at DESC`** (most recent first; secondary `cagr DESC`). Columns: strategy, instrument, compact params (e.g. `n1=10,n2=20`), CAGR, Return, Max Drawdown, Win Rate, Sharpe, # Trades, created_at.
- **Number formatting:** CAGR/Return/Max Drawdown/Win Rate to 2 decimals with `%` (Max Drawdown displays the stored **negative** value, e.g. `-23.45%`); Sharpe to 2 decimals; # Trades as integer.
- **Filters:** `st.selectbox` for strategy and instrument, populated from the distinct `list_runs()` values, default "All", placed above the table. (Any non-hot metric remains available via `stats_json`/`json_extract` if a sort beyond the hot columns is wanted.)
- **Empty state:** when there are no runs, show an instructional message — e.g. "No runs yet. Run `python run.py ema_cross --instrument nifty --start 2023-01-01 --end 2023-12-31` to record your first backtest."
- Row selection → detail (R11): read `results/runs/<run_id>/` → equity curve from `equity.parquet` via `st.line_chart`, metrics panel from `metrics.json`, trades table from `trades.csv`. **Single run at a time in v0** (curve-overlay comparison deferred — see Scope Boundaries).
- Keep table assembly, params formatting, metric formatting, and equity loading in small pure helpers so they're unit-testable without a Streamlit runtime. No `config_hash` grouping UI (deferred).

**Patterns to follow:** Streamlit `st.dataframe`/`st.selectbox`/`st.line_chart`. Equity from `equity.parquet`, not Bokeh.

**Test scenarios:**
- Happy path (helpers): the table-assembly helper produces the display columns in the defined order, with formatted params and metrics (CAGR `12.34%`, Max Drawdown `-23.45%`, Sharpe `1.23`, # Trades integer), default-sorted `created_at DESC`.
- Happy path (helpers): the equity-loader helper reads a run's `equity.parquet` and returns a timestamp-indexed `Equity` series for `st.line_chart`.
- Edge case: empty `runs` table → table helper returns an empty display frame and the app shows the instructional empty state (no crash).
- Edge case: the strategy/instrument filter helper narrows rows to the selected value and returns all rows for "All".
- Error path: a run row whose artifact dir is missing/corrupt yields an unavailable-detail state, not a crash.
- Integration: `Test expectation: full end-to-end Streamlit rendering is verified manually` — automated coverage targets the pure helpers; noted in the test file.

**Verification:** `streamlit run dashboard.py` lists runs newest-first, filters by strategy/instrument, formats metrics readably, shows an instructional empty state, and on selection shows a run's equity curve + trades; missing-artifact rows degrade gracefully.

---

## System-Wide Impact

- **Interaction graph:** `run.py` and `dashboard.py` are the two entry points; both funnel through `engine/persistence` for the SQLite index. The `DataSource` ABC is the only seam to external data — nothing else imports `jugaad_data`. `config` must be imported before `jugaad_data` everywhere (J_CACHE_DIR contract).
- **Error propagation:** `DataUnavailableError` (U2), `InsufficientDataError` and the cash guard (U5), and the commission guard (U6) propagate to the CLI, which exits non-zero with clear messages. The dashboard triggers no fetches/runs, so it can't hit these.
- **State lifecycle:** Atomic artifact write (tmp-dir + rename, then row insert) means no partial dirs and no index rows pointing at missing files — the orphan/partial-dir window is closed.
- **API surface parity:** Adding an intraday source later means implementing `DataSource` only; engine, persistence, CLI, dashboard unchanged (R4 seam).
- **Integration coverage:** AE1 (cache no-network), AE2 (append-not-overwrite), AE3 (commission nets equity) are each pinned by an integration-level test in U2/U4/U5.
- **Unchanged invariants:** N/A — greenfield.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| **Results silently mislead: spot index isn't directly tradeable** (you'd trade futures/ETF/options) | Methodological caveats in README + `run_backtest` docstring + dashboard note: results approximate a frictionless index-tracking instrument; ignore futures roll/basis, ETF tracking error; survivorship + overfitting flagged. Stated approximation, not a hidden claim. |
| **Commission percent-vs-fraction → 100× cost error** makes a good strategy look terrible | CLI `--commission-pct` (human percent) as primary path + `0 <= fraction < 0.1` validation rejecting likely mistakes; runner + library re-assert bounds. |
| **Zero trades on real index prices** (cash < price; no fractional shares) | `DEFAULT_CASH` set well above BankNifty; U5 asserts `cash > max(Close)`. |
| **Zero trades on too-short ranges** (indicator warmup never completes) | U5 min-bars guard derives required bars from the strategy's declared `lookback_params` and raises `InsufficientDataError`. |
| **NaN OHLC hard-raises in backtesting.py** | U2 transform includes `dropna()`. |
| `jugaad-data`/niftyindices blocks or returns malformed payloads (no built-in retry) | U2 retry+backoff + non-empty validation + `DataUnavailableError`; jugaad pickle cache reuses successful months on retry and serves cached pulls offline. |
| Stale jugaad pickle cache masks fresh data | Contained in project-local `.jdata_cache/`; README documents deleting it to invalidate. |
| Wanting a metric not in the hot columns (Sortino, Profit Factor) | Full stats stored in `stats_json`; queryable via `json_extract` with no schema migration. |
| Streamlit row-selection API drift | U7 keeps logic in pure helpers (unit-tested); widget choice deferred to the installed version. |

---

## Documentation / Operational Notes

- `README.md` (U1) documents the loop (write/register a strategy → `python run.py <strategy> --commission-pct ... --start ... --end ...` → `streamlit run dashboard.py`), the **methodological caveats**, and cache-clearing (`.jdata_cache/`).
- Note pandas/pyarrow must be explicit deps (jugaad doesn't declare pandas; backtesting pulls pandas/numpy/bokeh transitively).
- Local-only; no rollout/monitoring concerns.

---

## Sources & References

- **Origin document:** [docs/brainstorms/local-backtesting-harness-requirements.md](docs/brainstorms/local-backtesting-harness-requirements.md)
- backtesting.py: https://kernc.github.io/backtesting.py/ · https://github.com/kernc/backtesting.py
- jugaad-data: https://github.com/jugaad-py/jugaad-data · https://marketsetup.in/documentation/jugaad-data/
