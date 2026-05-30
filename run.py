"""CLI entry point: trigger a backtest and save it.

    python run.py ema_cross --instrument nifty --n1 10 --n2 20 \
        --start 2018-01-01 --end 2024-12-31 --commission-pct 0.05

Every invocation saves a new run. Strategy params (e.g. --n1) are discovered from
the chosen strategy's param spec. Commission is entered as human percent via
--commission-pct (recommended) or as a raw fraction via --commission, and is guarded
against the percent-vs-fraction mistake.
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


def _resolve_commission(parser, args):
    if args.commission is not None and args.commission_pct is not None:
        parser.error("pass only one of --commission or --commission-pct")
    if args.commission_pct is not None:
        fraction = args.commission_pct / 100.0
    elif args.commission is not None:
        fraction = args.commission
    else:
        fraction = config.DEFAULT_COMMISSION

    if not (0 <= fraction < 0.1):
        parser.error(
            f"commission {fraction} is out of range [0, 0.1) per side. "
            f"--commission takes a fraction (0.0005 = 0.05%); "
            f"for percent use --commission-pct."
        )
    return fraction


def _build_base_parser():
    p = argparse.ArgumentParser(
        prog="run.py", description="Run and save a daily index backtest."
    )
    p.add_argument("strategy", help=f"one of: {', '.join(strategies.available())}")
    p.add_argument("--instrument", default="nifty",
                   choices=sorted(config.INSTRUMENTS),
                   help="index alias (default: nifty)")
    p.add_argument("--start", type=_date, required=True, help="YYYY-MM-DD")
    p.add_argument("--end", type=_date, default=dt.date.today(),
                   help="YYYY-MM-DD (default: today / latest available)")
    p.add_argument("--commission", type=float, default=None,
                   help="per-side fraction (0.0005 = 0.05%%)")
    p.add_argument("--commission-pct", type=float, default=None,
                   help="per-side commission in human percent (0.05 = 0.05%%)")
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

    commission = _resolve_commission(parser, args)
    params = _parse_strategy_params(args.strategy, extras)

    run_id = run_backtest(
        args.strategy, args.instrument, args.start, args.end,
        params=params, commission=commission,
    )

    print(f"saved run {run_id}")
    _print_headline(run_id)
    print("note: fills are next-bar open on the (untradeable) spot index — "
          "see README caveats.")
    return 0


def _print_headline(run_id):
    try:
        from engine import persistence

        runs = persistence.list_runs()
        row = runs[runs.run_id == run_id].iloc[0]
        print(f"  CAGR {row.cagr:.2f}%   Max DD {row.max_drawdown:.2f}%   "
              f"# Trades {int(row.num_trades)}")
    except Exception:
        pass  # headline is best-effort; the run is already saved


if __name__ == "__main__":
    sys.exit(main())
