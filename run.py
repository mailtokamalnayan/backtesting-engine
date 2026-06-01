"""CLI entry point: run a backtest (or a sweep) and save it.

    # single run
    python run.py turnaround_tuesday --instrument nifty --start 2015-01-01

    # sweep: comma-separated params expand to the cartesian product of runs
    python run.py turnaround_tuesday --instrument nifty --start 2015-01-01 \
        --n 9,21,50 --exit_time 09:18

Every run saves to the index. A sweep builds one data source and shares it across
all runs, so the Kite range is fetched/refreshed once. End date defaults to today.
Cost is a fixed slippage per fill (config.DEFAULT_SLIPPAGE); commission is not modeled.
"""

import argparse
import datetime as dt
import itertools
import sys

import config
import strategies
from engine.runner import run_backtest


def _date(s):
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {s!r}; use YYYY-MM-DD")


def _build_base_parser():
    p = argparse.ArgumentParser(
        prog="run.py", description="Run and save an index backtest (or sweep)."
    )
    p.add_argument("strategy", help=f"one of: {', '.join(strategies.available())}")
    p.add_argument("--instrument", default="nifty",
                   choices=sorted(config.INSTRUMENTS),
                   help="index alias (default: nifty)")
    p.add_argument("--start", type=_date, required=True, help="YYYY-MM-DD")
    p.add_argument("--end", type=_date, default=dt.date.today(),
                   help="YYYY-MM-DD (default: today / latest available)")
    return p


def _parse_param_combos(strategy, extras):
    """Expand strategy params into a list of coerced param dicts.

    A comma-separated value (e.g. ``--n 9,21,50``) is a sweep axis; the cartesian
    product of all such axes is the run set. Raw tokens are coerced via the
    strategy's ``param_spec`` (a single value coerces identically to a one-run call).
    Raises ``ValueError`` on an uncoercible token.
    """
    spec = strategies.get(strategy).spec
    pp = argparse.ArgumentParser(prog=f"run.py {strategy}", add_help=False)
    for name in spec.params:
        pp.add_argument(f"--{name}", default=None)  # capture raw strings
    raw = vars(pp.parse_args(extras))

    axes = {}
    for name, meta in spec.params.items():
        if raw[name] is None:
            axes[name] = [meta["default"]]
        else:
            axes[name] = [spec.coerce(name, tok.strip())
                          for tok in str(raw[name]).split(",")]

    names = list(axes)
    return [dict(zip(names, values))
            for values in itertools.product(*(axes[n] for n in names))]


def _build_source(strategy):
    """One data source for the whole sweep, chosen by the strategy's interval."""
    if strategies.get(strategy).interval == "day":
        from data.source import JugaadDailySource
        return JugaadDailySource()
    from data.kite_source import KiteIntradaySource
    return KiteIntradaySource()


def main(argv=None):
    parser = _build_base_parser()
    args, extras = parser.parse_known_args(argv)

    if args.strategy not in strategies.available():
        parser.error(f"unknown strategy {args.strategy!r}. "
                     f"Available: {', '.join(strategies.available())}")

    try:
        combos = _parse_param_combos(args.strategy, extras)
    except ValueError as err:
        parser.error(f"bad parameter value: {err}")

    # One shared source: the range is fetched/refreshed once for the whole sweep.
    # A fetch failure raises on the first run before anything is saved.
    source = _build_source(args.strategy)
    results = []
    for params in combos:
        run_id = run_backtest(args.strategy, args.instrument, args.start, args.end,
                              params=params, source=source)
        results.append((run_id, params))

    _print_summary(results)
    print(f"note: {config.DEFAULT_SLIPPAGE * 100:.2f}% slippage applied per fill; "
          f"commission not modeled.")
    return 0


def _print_summary(results):
    print(f"saved {len(results)} run(s):")
    try:
        from engine import persistence

        runs = persistence.list_runs().set_index("run_id")
    except Exception:
        runs = None
    for run_id, params in results:
        label = ", ".join(f"{k}={v}" for k, v in params.items() if k != "lot")
        try:
            r = runs.loc[run_id]
            pnl = r.final_equity - config.DEFAULT_CASH
            print(f"  {label or 'default':28} trades {int(r.num_trades):>4}  "
                  f"PnL Rs {pnl:>12,.0f}  CAGR {r.cagr:6.2f}%  "
                  f"MaxDD {r.max_drawdown:6.2f}%")
        except Exception:
            print(f"  {label or 'default':28} -> {run_id}")


if __name__ == "__main__":
    sys.exit(main())
