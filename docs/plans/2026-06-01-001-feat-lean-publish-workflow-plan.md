---
title: "feat: Lean backtest → publish workflow (freshness-aware cache)"
type: feat
status: active
date: 2026-06-01
deepened: 2026-06-01
---

# feat: Lean backtest → publish workflow (freshness-aware cache)

## Summary

Tighten the "describe a strategy → backtest → live on the static site" loop: replace the Kite date-range Parquet cache with a **freshness-aware** one (cache immutable closed-day history in a single canonical file per symbol+interval, refetch only the open/trailing window so data is never stale and disk stays lean), let `run.py` run a whole param sweep in one invocation sharing the single load, and add a one-command `make publish` (backing `publish.py`) that exports the snapshot, deploys to Vercel, and re-points the alias.

---

## Problem Frame

The current loop works but is friction-heavy. Backtests run via ad-hoc `python -c` scripts; the Kite source keys its cache by exact `start`/`end`, so overlapping date ranges spawn a pile of redundant Parquet files (`.kite_cache/` already holds ~10) and a query whose end is "today" can serve a previous day's bars as if current; a param sweep means several manual invocations; and publishing is three remembered steps (`export_site.py`, `vercel --prod`, then a manual `vercel alias set` because the clean alias doesn't auto-follow a deploy). The user pays for the Kite historical API and wants current data without disk cruft — but unconditionally re-pulling ~11 years of immutable minute history on every command (≈68 chunked calls) would trade one problem (staleness/cruft) for another (slow, rate-limit-exposed iteration), since only the most recent day's bars can actually change.

---

## Requirements

- R1. The Kite data source serves immutable closed-day history from cache and **always refetches the open/trailing window** from the API, so returned data is never stale.
- R2. The cache is stored as **one canonical file per (symbol, interval)** — no per-date-range files — and stays lean; pre-existing date-range cache files are removed.
- R3. Within a single command, a given (symbol, interval) is loaded/refreshed once and reused in memory across a param sweep.
- R4. `run.py` can run a sweep — multiple param combinations — in one invocation, sharing the single load, and print a compact results summary.
- R5. A single `make publish` (backing `publish.py`) takes the current saved runs live: export snapshot → Vercel production deploy → re-point the clean alias.

---

## Scope Boundaries

- No new trading strategies and no changes to existing strategy logic — this is workflow/tooling only.
- The free `jugaad-data` `JugaadDailySource` and its pickle cache are not touched; the `DataSource` ABC is unchanged. The freshness-aware cache lives **only** on `KiteIntradaySource` (its `get_daily`, which delegates to `get_intraday(interval="day")`, inherits the new behavior — current strategies are all Kite-intraday anyway).
- No pruning of saved run artifacts or the SQLite results history — "lean" here means the data cache, not results.
- No CI / scheduled auto-publishing; `publish` is run on demand.
- Kite authentication is a prerequisite — the dashboard login header refreshes the token; the freshness-aware cache greatly shrinks (but does not remove) the per-command fetch, so a valid token is still needed for the trailing refetch.

### Deferred to Follow-Up Work

- None. (The earlier "make the alias auto-follow production" idea is **not** viable for a clean `.vercel.app` alias — Vercel does not allow a `*.vercel.app` subdomain to be set as a project production domain, which is precisely why the manual `vercel alias set` re-point exists. The bake-in in U3 is therefore the correct fix, not a stopgap.)

---

## Context & Research

### Relevant Code and Patterns

- `data/kite_source.py` — `KiteIntradaySource.get_intraday` currently reads/writes `_cache_path` (Parquet keyed by `symbol_interval_start_end`), wrapping `_fetch_chunked` (60-day windows, `_MAX_DAYS`) + `_to_df` + non-empty validation. The module docstring ("download history and cache it... run offline from the cache forever") describes the *intent* the freshness-aware cache restores correctly. This is where R1/R2/R3 land.
- `data/source.py` — `DataSource` ABC + `JugaadDailySource` (its own pickle cache); the `get_daily`/`get_intraday` seam the runner routes through by `entry.interval`. **Unchanged.**
- `engine/runner.py` — `run_backtest(...)` takes an optional `source`; when omitted it builds `JugaadDailySource()`, then routes `get_daily` vs `get_intraday` by `entry.interval` (lines ~62-71). For a shared sweep load, the CLI must build one source and pass it to every run. Note: today the CLI passes **no** source, so an intraday strategy run via `run.py` would default to `JugaadDailySource` and fail at the `get_intraday` branch — U2 also closes that gap.
- `run.py` — single-backtest CLI; `_parse_strategy_params` builds a *second* argparse with `type=meta["type"]` per param. `strategies.ParamSpec.coerce` exists (`strategies/__init__.py`) but the CLI does **not** call it today — relevant to the sweep coercion design.
- `export_site.py` — `export()`/`build_data()` write `site/data.json`; verified it imports cleanly without Streamlit (dashboard imports `streamlit` only under `__main__`). `export_site.SITE` is the canonical `site/` path. `publish` reuses both.
- `site/README.md` — documents the manual publish steps (scope `kamals-projects-ce7b0100`, alias `backtest-in-nf.vercel.app`); `publish` automates exactly this sequence.

### Institutional Learnings

- No `docs/solutions/` entries; direct repo knowledge from building the harness this session.

### External References

- Vercel CLI: `vercel deploy --prod --yes --scope <scope> <dir>` is non-interactive and prints the production **deployment URL as its sole stdout line** on success (status/inspect lines go to stderr); that immutable `*-<hash>-…vercel.app` URL is what `vercel alias set <url> <alias> --scope <scope>` needs. A `*.vercel.app` alias must be re-pointed after each prod deploy (it does not auto-follow).

---

## Key Technical Decisions

- **Freshness-aware cache, not deletion (reverses the initial "no cache" lean toward full deletion after review):** historical minute bars for a closed trading day are immutable; only the current/most-recent day can change. So cache the immutable history and refetch only the trailing window. This satisfies "never stale + lean + fast across commands" — the property unconditional re-fetch would lose, since the user's real loop is many separate commands (run → inspect → tweak → run), where an in-memory-only memo helps nothing.
- **One canonical Parquet per (symbol, interval)** keyed `<symbol>_<interval>.parquet` (no `start`/`end` in the name). This eliminates the overlapping-date-range cruft that motivated the original "no cache" instinct, and makes coverage trivial: the file holds a single contiguous, growing history; requests slice from it.
- **Refetch policy:** on a request, load the canonical frame; refetch from the last cached date through `end` (captures new closed days **and** re-pulls the possibly-incomplete most-recent day, deduped on merge); if the request needs data older than the cache's earliest date, refetch the full requested range and merge. Merge → dedupe by timestamp → sort → persist → slice `[start, end]`. In normal use (`start` constant, `end` = today) this means a tiny trailing fetch after the first full pull.
- **In-memory hold per instance (R3):** after loading/refreshing, keep the canonical frame in memory on the `KiteIntradaySource` instance so a sweep within one command does not re-read disk or re-refetch. The sweep builds one source and passes it to every `run_backtest`.
- **Source selection moves into `run.py`:** the CLI picks the source from the strategy's declared `interval` (minute → `KiteIntradaySource`, day → `JugaadDailySource`), builds it once, and passes it to all runs — which also makes intraday strategies runnable from `run.py` (today's CLI can't run them, see Context).
- **Sweep via list-valued params (cartesian product), coerced per-token:** any strategy param given comma-separated (`--n 9,21,50`) expands; the cartesian product of all list params defines the runs. Because the current second-phase parser would choke on `int("9,21,50")`, the parser captures raw strings and applies `strategies.get(name).spec.coerce(param, token)` per comma-split token (using the existing-but-unused `ParamSpec.coerce`); a single value coerces identically. Comma is the sweep separator; params whose literal value contains a comma are unsupported (none exist today).
- **`make publish` is the primary interface, `publish.py` backs it:** `publish.py` calls `export_site.export()` in-process, then shells out to `vercel deploy --prod` and `vercel alias set`; the Makefile `publish` target is the documented entry point. Keeping the Vercel calls in one place makes the alias re-point un-forgettable.

---

## Open Questions

### Resolved During Planning

- Cache policy: **freshness-aware** (confirmed after review) — cache immutable closed-day history, refetch only the trailing/today window; one canonical file per symbol+interval.
- Publish shape: **run many, publish once** (confirmed) — running and publishing are separate commands; a sweep deploys the site only once.
- Sweep coercion path: resolved — capture raw strings, split on comma, coerce per token via the existing `ParamSpec.coerce` (the CLI's current `type=`-based path cannot expand lists).
- Vercel URL capture: resolved — `vercel deploy --prod` stdout sole-URL-line, not deferred.

### Deferred to Implementation

- Exact "trailing window" boundary (refetch from `cached_max` vs `cached_max - 1 day` to be safe about an incomplete last bar) — settle against real Kite minute output during implementation.
- Whether the in-memory hold caches the full frame or per-(symbol,interval) slices — implementer's call; both satisfy R3.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
KiteIntradaySource.get_intraday(symbol, interval, start, end):
  cached = load canonical .kite_cache/<symbol>_<interval>.parquet   (or in-memory hold)
  if cached covers [start, end] and end < today:        # all closed, immutable
        return cached.slice(start, end)
  fetch_from = start if (cached is empty or start < cached.min_date) else cached.max_date
  fresh = _fetch_chunked(symbol, interval, fetch_from, end) -> _to_df   # only the gap/trailing
  merged = concat(cached, fresh) -> dedupe by timestamp -> sort
  persist merged to canonical file ; hold in memory
  return merged.slice(start, end)
  # a failed fetch raises DataUnavailableError and is NOT merged/held (retry can succeed)
```

---

## Implementation Units

- U1. **Freshness-aware Kite cache + in-memory hold**

**Goal:** `KiteIntradaySource` serves immutable history from one canonical file per (symbol, interval), refetches only the trailing/open window, and holds the frame in memory for the command's lifetime.

**Requirements:** R1, R2, R3.

**Dependencies:** None.

**Files:**
- Modify: `data/kite_source.py` (cache logic + docstring)
- Modify: `data/kite_auth.py` (docstring only — "reused until expiry" still holds; remove the "offline forever" overclaim)
- Test: `tests/test_kite_source.py`

**Approach:**
- Replace `_cache_path`'s date-range key with a canonical `<symbol>_<interval>.parquet`. Load it (or an empty frame) at the top of `get_intraday`.
- Apply the refetch policy in the High-Level Technical Design: serve from cache when the range is fully covered and `end` is a closed day; otherwise fetch only `[fetch_from, end]` (trailing/gap), merge + dedupe + sort + persist, and slice.
- Add an instance-level in-memory hold of the canonical frame so repeat calls in one command (a sweep) skip disk + refetch.
- Keep `_fetch_chunked` / `_to_df` / non-empty validation and the `fetch_fn`/`kite` injection seam intact. A failed fetch must raise `DataUnavailableError` and leave neither the file nor the in-memory hold updated.
- Update the `kite_source.py` module docstring to describe the freshness-aware behavior (closed history cached, trailing window refetched).

**Execution note:** Add a characterization test of the current transform/validation behavior before reworking the cache block, so the refactor preserves it.

**Patterns to follow:** existing `get_intraday` structure; the injected `fetch_fn`/`kite` seam the current tests use.

**Test scenarios:**
- Happy path: first call (empty cache) fetches `[start, end]`, writes one canonical file, returns the slice.
- Happy path: a second call for a range fully inside the cache with `end` in the past (closed days) returns from cache with **no** fetch (spy on fetch fn).
- Edge case (freshness): a call whose `end` is today refetches only the trailing window (fetch invoked with `fetch_from == cached_max`, not the full range), and a changed most-recent-day bar is reflected after merge+dedupe.
- Edge case (extend forward): cache covers 2015→May; request 2015→June fetches only May→June and the canonical file now covers 2015→June (single contiguous frame, deduped — no second file).
- Edge case (older gap): a request starting before the cache's earliest date refetches the full requested range and merges.
- Edge case (lean): only **one** Parquet per (symbol, interval) ever exists; no date-range-named files are written.
- Edge case (in-memory hold): two identical `get_intraday` calls on the same instance read disk / refetch **once** (sweep reuse).
- Error path: a fetch failure raises `DataUnavailableError`, and neither the canonical file nor the in-memory hold is updated (a later retry can succeed).

**Verification:** the first backtest over a range does the full pull; subsequent commands on the same range refetch only today's window; `.kite_cache/` holds exactly one file per symbol+interval.

---

- U2. **Sweep + source selection in `run.py`**

**Goal:** one CLI invocation runs a strategy across multiple param combinations, sharing a single source/load, and prints a compact results table.

**Requirements:** R4.

**Dependencies:** U1 (shared source's in-memory hold makes the sweep's repeated reads free).

**Files:**
- Modify: `run.py`
- Modify: `README.md` (the "loop" section — show the sweep form)
- Test: `tests/test_cli.py`

**Approach:**
- Build the source once from `strategies.get(name).interval` (minute → `KiteIntradaySource`, day → `JugaadDailySource`) and pass it explicitly to every `run_backtest` (also fixes intraday-via-CLI).
- Change the second-phase param parser to capture **raw string** values, then for each param split on `,` into tokens and coerce each via `strategies.get(name).spec.coerce(param, token)`. The cartesian product of all list-valued params is the run set; a no-comma invocation runs exactly one backtest (identical coercion to today).
- Run each combination through `run_backtest` with the shared source; collect `run_id`s + headline metrics; print one row per run at the end.
- Preserve the existing single-run behavior and the slippage-fixed CLI surface.

**Patterns to follow:** the existing two-phase argparse in `run.py`; `ParamSpec.coerce` (now actually used); the runner's `entry.interval` routing.

**Test scenarios:**
- Happy path: `--n 9,21,50` (others scalar) → 3 runs with correctly typed params (`run_backtest` mocked).
- Happy path: a single-valued invocation runs exactly once (back-compat) and coerces identically.
- Edge case: two list params expand to the cartesian product (`--n 9,21` × `--exit_time 09:18,09:45` → 4 runs).
- Edge case: all runs in a sweep receive the **same** source instance (assert identity) so the load/fetch is shared once.
- Edge case: an intraday strategy selects `KiteIntradaySource`; a daily strategy selects `JugaadDailySource` (assert type per `interval`).
- Error path: an uncoercible token (e.g. `--n 9,foo`) fails fast before any run.
- Error path: a fetch failure on the shared source aborts the sweep with a clear error and saves **zero** runs (no partial state); pairs with U1's "failed fetch not held".

**Verification:** `python run.py turnaround_tuesday --instrument nifty --start 2015-01-01 --n 9,21,50` runs three backtests, refreshes Kite data once, saves three runs, and prints a 3-row summary.

---

- U3. **`make publish` + `publish.py` (export → deploy → re-alias)**

**Goal:** one command takes the saved runs live: export `site/data.json`, deploy to Vercel production, re-point the clean alias.

**Requirements:** R5.

**Dependencies:** None (consumes whatever runs are saved).

**Files:**
- Create: `publish.py`
- Create: `Makefile`
- Modify: `site/README.md` (point at `make publish`; note the freshness-aware no-cruft behavior)
- Test: `tests/test_publish.py`

**Approach:**
- `publish.py` calls `export_site.export()` in-process, then runs `vercel deploy --prod --yes --scope <SCOPE> <site_dir>` capturing the deployment URL from **stdout** (the sole URL line), then `vercel alias set <url> <ALIAS> --scope <SCOPE>`.
- Reuse `export_site.SITE` for the deploy directory (single source of truth — no duplicated path). `SCOPE`/`ALIAS` are module constants.
- Structure as small functions (command construction + a run wrapper) so command strings are unit-testable with a mocked subprocess; the real deploy is run manually. On a non-zero deploy exit, echo the captured stderr verbatim (so an expired token / PATH issue is diagnosable) and **do not** run the alias step.
- `Makefile` `publish` target runs `python publish.py` and is the documented entry point.

**Approach note:** `publish.py` orchestrates external CLIs and is not pure; keep export + command-construction separable from subprocess execution so the tested surface is the command strings, not the network.

**Patterns to follow:** `export_site.export()` / `export_site.SITE`; the exact deploy + alias commands in `site/README.md`.

**Test scenarios:**
- Happy path: `publish` calls `export_site.export()` first, then constructs the correct `vercel deploy --prod --yes --scope <SCOPE> <SITE>` command, then `vercel alias set <parsed-url> <ALIAS> --scope <SCOPE>` (subprocess mocked; assert commands + order).
- Happy path: the deployment URL parsed from the (mocked) stdout is the one passed to `alias set`.
- Error path: a non-zero deploy exit surfaces the captured stderr and the alias step is **not** run.
- Edge case: `export()` runs before any deploy command (ordering); the deploy dir equals `export_site.SITE`.

**Verification:** `make publish` refreshes `site/data.json`, deploys, and `https://backtest-in-nf.vercel.app` serves the latest runs after one command.

---

## System-Wide Impact

- **Interaction graph:** `run.py` → `run_backtest` → `KiteIntradaySource` (one shared instance per command). `publish.py` → `export_site.export()` → `site/data.json`, then the Vercel CLI. No change to the Streamlit dashboard, the strategy registry, `JugaadDailySource`, or the `DataSource` ABC.
- **State lifecycle:** the canonical-file cache must merge+dedupe+sort atomically enough that a crash mid-write doesn't corrupt history (write-then-rename, or accept a re-fetch on next run). Failed fetches must not be merged/held (U1 error path). The in-memory hold is process-scoped and self-cleaning.
- **API surface parity:** `run_backtest`'s programmatic signature is unchanged; the CLI gains sweep + source-selection. `get_daily`/`get_intraday` return shapes are unchanged — only their caching behavior changes, and only on `KiteIntradaySource`.
- **Integration coverage:** U1's freshness behaviors (closed-day cache hit, trailing refetch, single canonical file) and U2's shared-source identity + sweep-abort-on-fetch-failure are the cross-cutting behaviors the mocks must prove; the real Kite refresh and real Vercel deploy are verified manually.
- **Unchanged invariants:** strategy logic, the SQLite run-index schema, both dashboards, and the OOS-split feature are untouched.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Canonical-file merge/coverage logic introduces a silent data gap or duplicate bars | One contiguous growing frame keyed only by (symbol, interval); merge dedupes by timestamp and sorts; tests cover extend-forward, older-gap, and trailing-refetch cases; older-than-cache requests refetch the full range rather than risk a hole. |
| Mid-write crash corrupts the canonical cache | Write to a temp file and rename (atomic), or treat a corrupt/missing file as empty and re-fetch. |
| Trailing token expiry (~7:30 AM) still needed for the (now small) refresh | Freshness-aware cache shrinks the per-command fetch to today's window, so an expired-token retry is cheap; the dashboard login header refreshes it; a missing token raises a clear `DataUnavailableError`. |
| `vercel` CLI output/format drift breaks URL capture | Use `vercel deploy --prod` (deployment URL is the sole stdout line); fail loudly if stdout isn't a single `https://…vercel.app`, and echo stderr; isolate extraction in one function. |
| `vercel` not installed / unauthenticated / wrong scope | `publish.py` echoes the deploy stderr on non-zero exit and skips the alias step; README notes the `vercel` + auth prerequisite. |
| Stale pre-existing `.kite_cache/` date-range files linger after the switch | One-time `rm -rf .kite_cache/` in U1 verification so the canonical-file scheme starts clean. |

---

## Documentation / Operational Notes

- `README.md` (sweep form) and `site/README.md` (`make publish`, freshness-aware caching) updated within U2/U3.
- Operationally: publishing is on-demand via `make publish`; deploys target the existing `backtest-in-nf` Vercel project (scope `kamals-projects-ce7b0100`).

---

## Sources & References

- Related code: `data/kite_source.py`, `data/kite_auth.py`, `run.py`, `engine/runner.py`, `strategies/__init__.py` (`ParamSpec.coerce`), `export_site.py`, `site/README.md`
- External: Vercel CLI `vercel deploy --prod --yes --scope` (stdout deployment URL) + `vercel alias set` (documented in `site/README.md`); `*.vercel.app` aliases cannot be project production domains (hence the re-point).
