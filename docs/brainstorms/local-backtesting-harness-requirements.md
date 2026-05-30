---
date: 2026-05-30
topic: local-backtesting-harness
---

# Local Backtesting Harness for Nifty/BankNifty

## Summary

A local, single-user backtesting harness for daily Nifty and BankNifty spot-index strategies. Each idea is expressed as a tiny Python strategy function; running it with a commission setting produces standard performance metrics and auto-saves the run. A local web dashboard lists every run and its variations so the user can tweak params, re-run, and compare results at a glance.

---

## Problem Frame

The user wants to test trading ideas on Indian indices (Nifty, BankNifty) but has no lightweight way to go from "idea" to "measured result" and keep a record of what was tried. General-purpose backtesting tools are either too heavy to start fast or don't retain a browsable history of variations. The repeated pain is the loop itself: define an idea, run it, look at the numbers, change a parameter, run again — and then lose track of which variation produced which result. Without saved history, comparison across variations is manual and error-prone, and the exploration doesn't compound.

The work is local-only and for one person; hosting, collaboration, and production concerns are explicitly not in play.

---

## Key Flows

- F1. Run a new backtest
  - **Trigger:** User has a strategy function (existing or newly written) and wants to test it.
  - **Actors:** User
  - **Steps:** Select/write the strategy function → choose instrument (Nifty/BankNifty), date range, params, and commission → run → engine fetches (or reads cached) daily data and executes the backtest → metrics, trades, and equity-curve plot are produced and the run is saved.
  - **Outcome:** A new persisted run exists with its params, metrics, trades, and plot; it appears in the dashboard.
  - **Covered by:** R1, R2, R3, R4, R6, R7, R8

- F2. Tweak and compare variations
  - **Trigger:** User wants to vary one or more params of a strategy already run.
  - **Actors:** User
  - **Steps:** Change param values → re-run → a new run is saved (the prior run is preserved, not overwritten) → open the dashboard → sort/filter the run table → click a run to inspect its equity curve and trades.
  - **Outcome:** Both the original and the variation are visible side by side in the run table for comparison.
  - **Covered by:** R5, R8, R9, R10, R11

---

## Requirements

**Strategy definition**
- R1. A strategy is defined as a small Python function/class (the engine's native strategy form), expressing entry/exit logic over daily OHLC data with parameters the user can vary.
- R2. The harness ships with at least one worked example strategy (e.g. an EMA crossover) so the run/tweak/compare loop is usable on day one.

**Data**
- R3. Daily OHLC history for Nifty and BankNifty is sourced via `jugaad-data` and cached locally so a given symbol+range is fetched at most once, then re-read from cache on subsequent runs.
- R4. Data access sits behind a thin source interface so an intraday provider can be added later without changing strategy or engine code. Only the daily source is implemented now.

**Execution**
- R6. A run executes a chosen strategy over a chosen instrument, date range, and parameter set, applying a single configurable commission percentage that approximates combined brokerage + slippage.
- R7. Each run produces, at minimum: CAGR, max drawdown, win-rate, Sharpe, number of trades, the trade list, and an equity-curve plot.

**Persistence**
- R5. Re-running a strategy with different parameters creates a new saved run; existing runs are never overwritten.
- R8. Every run is persisted as: a row in a single local index (strategy name, params, key metrics, instrument, date range, timestamp) plus per-run artifacts (full params, full metrics, trades, and the equity-curve plot).
- R9. A run is identified by strategy name + parameter set + instrument + date range.

**Dashboard**
- R10. A local web dashboard presents a sortable, filterable table of all runs showing strategy, params, and key metrics (e.g. CAGR, max drawdown, win-rate).
- R11. Selecting a run in the dashboard opens its detail view: the equity-curve plot and the trade list.

---

## Acceptance Examples

- AE1. **Covers R3.** Given Nifty daily data for 2020–2025 has already been fetched once, when the user runs another backtest over an overlapping range, the data is read from the local cache rather than re-fetched from the network.
- AE2. **Covers R5, R8.** Given a strategy was run with `ema=20/50`, when the user re-runs it with `ema=10/30`, both runs appear as separate rows in the dashboard and the original run's metrics are unchanged.
- AE3. **Covers R6, R7.** Given a strategy and a 0.05% commission, when the backtest runs, the reported returns are net of that commission and the equity curve reflects post-cost performance.

---

## Success Criteria

- The user can go from "new idea" to a saved, measured backtest result in minutes, writing only a small strategy function.
- After several sessions of tweaking, the user can open the dashboard and see every strategy and its variations with their results, without having tracked anything manually.
- A downstream implementer can build this from the requirements without having to decide product behavior — the engine library, data source, persistence shape, and dashboard surface are already settled (see Key Decisions).

---

## Scope Boundaries

- Options strategies and options-chain data (strikes, IV, expiries) — out.
- Intraday / minute-bar data sourcing — interface is prepared (R4) but no intraday source is built now.
- Detailed Indian cost modeling (STT, GST, stamp duty, exchange charges itemized) — out; a single commission % stands in.
- Hosting, multi-user, authentication, cloud deployment — out; local-only.
- Live trading, paper trading, broker/order integration — out.
- Multi-instrument / portfolio backtests in a single run — out; one instrument per run.

---

## Key Decisions

This brainstorm is inherently technical (the user chose to build on existing libraries), so the stack is part of the product definition:

- Engine = `backtesting.py`: Strategies are tiny `init`/`next` classes — a direct match for "describe an idea as a small Python function." Provides metrics, trade list, and equity-curve plot out of the box, and natively supports a single commission parameter. Single-instrument focus is acceptable because runs are one instrument at a time.
- Data = `jugaad-data`, cached to local files (e.g. Parquet): Free, covers daily Nifty/BankNifty history, no hosting needed.
- Persistence index = a single local store (e.g. SQLite) holding one row per run, alongside per-run artifact files: Simple, queryable, no server.
- Dashboard = a local web app (e.g. Streamlit): One-command local launch, sortable table + click-through detail, reads from the persistence index.
- New params = new run, never overwrite: The saved variation history is the core value; overwriting would destroy the comparison the product exists to enable.

---

## Dependencies / Assumptions

- `jugaad-data` reliably provides daily Nifty/BankNifty OHLC for the desired history — to be confirmed at implementation; if a range is unavailable, the data interface (R4) allows substituting another daily source without engine changes.
- `backtesting.py` is suitable for daily single-instrument index strategies (assumed; confirm current maintenance/version at planning time).
- Runs locally with Python 3 (Homebrew `python3` present in the environment).

---

## Outstanding Questions

### Deferred to Planning

- [Affects R3, R4][Technical] Exact cache format and on-disk layout for cached daily data (Parquet vs CSV; directory structure).
- [Affects R8, R9][Technical] Precise schema of the run index and the run-identity/dedup behavior when an identical strategy+params+range is run twice (new row vs idempotent).
- [Affects R7][Technical] Whether to surface `backtesting.py`'s full metric set or a curated subset in the dashboard table vs the detail view.
- [Affects R3][Needs research] Confirm `jugaad-data`'s current support and historical depth for Nifty/BankNifty daily index data.
- [Affects R10, R11][Technical] Dashboard interaction details (filtering controls, grouping a strategy's variations) — settle during planning/build.
