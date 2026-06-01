"""CLI entry point: trigger a backtest and save it.

    python run.py turnaround_tuesday --instrument nifty \
        --start 2022-01-01

Every invocation saves a new run. Strategy params (e.g. --n1, --lot) are discovered
from the chosen strategy's param spec. End date defaults to today. Cost is a fixed
slippage applied to every fill (config.DEFAULT_SLIPPAGE); commission is not modeled.
"""

import argparse
import datetime as dt
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
        prog="run.py", description="Run and save an index backtest."
    )
    p.add_argument("strategy", help=f"one of: {', '.join(strategies.available())}")
    p.add_argument("--instrument", default="nifty",
                   choices=sorted(config.INSTRUMENTS),
                   help="index alias (default: nifty)")
    p.add_argument("--start", type=_date, required=True, help="YYYY-MM-DD")
    p.add_argument("--end", type=_date, default=dt.date.today(),
                   help="YYYY-MM-DD (default: today / latest available)")
    return p


def _parse_strategy_params(strategy, extras):
    """Coerce leftover --key value flags against the strategy's param spec."""
    spec = strategies.get(strategy).spec
    pp = argparse.ArgumentParser(prog=f"run.py {strategy}", add_help=False)
    for name, meta in spec.params.items():
        pp.add_argument(f"--{name}", type=meta["type"], default=meta["default"])
    ns = pp.parse_args(extras)
    return vars(ns)


def main(argv=None):
    parser = _build_base_parser()
    args, extras = parser.parse_known_args(argv)

    if args.strategy not in strategies.available():
        parser.error(
            f"unknown strategy {args.strategy!r}. "
            f"Available: {', '.join(strategies.available())}"
        )

    params = _parse_strategy_params(args.strategy, extras)

    run_id = run_backtest(
        args.strategy, args.instrument, args.start, args.end, params=params,
    )

    print(f"saved run {run_id}")
    _print_headline(run_id)
    print(f"note: {config.DEFAULT_SLIPPAGE * 100:.2f}% slippage applied per fill; "
          f"commission not modeled.")
    return 0


def _print_headline(run_id):
    try:
        from engine import persistence

        runs = persistence.list_runs()
        row = runs[runs.run_id == run_id].iloc[0]
        print(f"  CAGR {row.cagr:.2f}%   Max DD {row.max_drawdown:.2f}%   "
              f"Trades {int(row.num_trades)}")
    except Exception:
        pass  # headline is best-effort; the run is already saved


if __name__ == "__main__":
    sys.exit(main())
