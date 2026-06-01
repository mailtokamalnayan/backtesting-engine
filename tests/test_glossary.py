"""Column/metric hover help: lookups and coverage of every displayed column."""

import dashboard
import export_site
import glossary

# The fixed headline-metric columns of the runs table (params vary per strategy).
RUNS_METRIC_COLUMNS = ["CAGR", "Return", "Total PnL", "Win%", "PF", "OOS PF",
                       "Max DD", "Sharpe", "Trades", "Period"]


def test_help_for_known_and_unknown():
    assert glossary.help_for("CAGR").startswith("Compound Annual Growth Rate")
    assert glossary.help_for("does-not-exist") is None


def test_every_comparison_metric_has_help():
    # STAT_LABELS are the (relabelled) full backtesting.py metrics shown as rows.
    missing = [s for s in export_site.STAT_LABELS if not glossary.help_for(s)]
    assert not missing, f"metrics without help: {missing}"


def test_every_runs_metric_column_has_help():
    missing = [c for c in RUNS_METRIC_COLUMNS if not glossary.help_for(c)]
    assert not missing, f"runs columns without help: {missing}"


def test_every_trade_column_has_help():
    missing = [c for c in dashboard.TRADE_COLUMNS if not glossary.help_for(c)]
    assert not missing, f"trade columns without help: {missing}"


def test_every_strategy_param_has_help():
    import strategies

    seen = set()
    for name in strategies.available():
        for param in strategies.get(name).spec.params:
            seen.add(param)
    missing = [p for p in sorted(seen) if not glossary.help_for(p)]
    assert not missing, f"strategy params without help: {missing}"
