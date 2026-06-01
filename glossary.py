"""Plain-English help for table columns and metrics.

Single source of truth shared by the Streamlit dashboard (column header tooltips
via ``st.column_config``) and the exported static site (header + metric-row hover
tooltips). Keys are the exact display labels used in the tables; both the short
runs-table names (``CAGR``) and the full backtesting.py names (``CAGR [%]``) are
covered so the same map serves every table. Lookups fall back to None.

Tone: written for someone new to trading/backtesting. Each line ends with a short
parenthetical cue (e.g. "(higher is better)") so the reader knows how to read it.
"""

COLUMN_HELP = {
    "Instrument": "Which index this run traded — Nifty 50, Bank Nifty, or Nifty "
                  "Midcap Select. Lot size differs per index (Nifty 65, BankNifty 30, "
                  "Midcap 120 units).",

    # --- headline performance metrics (runs table + OOS + full stats) ---
    "CAGR": "Compound Annual Growth Rate — your average return per year, with gains "
            "compounding. (higher is better)",
    "CAGR [%]": "Compound Annual Growth Rate — average return per year, compounded. "
                "(higher is better)",
    "Return": "Total return over the whole test period, start to finish. "
              "(higher is better)",
    "Return [%]": "Total return over the whole test period. (higher is better)",
    "Return (Ann.) [%]": "The total return expressed as a per-year rate. "
                         "(higher is better)",
    "Buy & Hold Return [%]": "What you'd have made by simply buying on day one and "
                             "holding — the benchmark your strategy should beat. "
                             "(strategy ideally beats this)",
    "Total PnL": "Total profit or loss in rupees, for one Nifty futures lot. "
                 "(higher is better)",
    "Avg PnL/trade": "Average rupee profit or loss per trade. (higher is better)",
    "Win%": "Share of trades that ended in profit. (higher is better — but a high "
            "win rate with big losers can still lose money)",
    "Win Rate": "Share of trades that ended in profit. (higher is better)",
    "Win Rate [%]": "Share of trades that ended in profit. (higher is better)",
    "PF": "Profit Factor — total winnings divided by total losses. (higher is "
          "better; above 1 makes money, above 1.5 is strong)",
    "Profit Factor": "Total money won divided by total money lost. (higher is "
                     "better; above 1 is profitable)",
    "OOS PF": "Profit Factor on out-of-sample data — the recent slice the strategy "
              "was NOT tuned on. Sanity-checks that the edge is real, not overfit. "
              "(higher is better; close to PF is reassuring)",
    "Max DD": "Maximum Drawdown — the worst peak-to-bottom drop in account value "
              "along the way. (closer to 0 is better)",
    "Max. Drawdown [%]": "The worst peak-to-bottom fall in account value. "
                         "(closer to 0 is better)",
    "Avg. Drawdown [%]": "The average size of the dips along the way. "
                         "(closer to 0 is better)",
    "Max. Drawdown Duration": "The longest stretch spent below a previous high "
                              "(underwater). (shorter is better)",
    "Sharpe": "Sharpe Ratio — return earned for each unit of risk (how much the "
              "value bounces around). (higher is better; above 1 is good)",
    "Sharpe Ratio": "Return earned per unit of risk. (higher is better; above 1 "
                    "is good)",
    "Sortino Ratio": "Like Sharpe, but only counts downside moves as risk. "
                     "(higher is better)",
    "Calmar Ratio": "Annual return divided by the worst drawdown. (higher is better)",
    "Volatility (Ann.) [%]": "How much the yearly return swings up and down. "
                             "(lower is steadier)",
    "Trades": "Number of trades taken. (more trades make the statistics more "
              "trustworthy)",
    "# Trades": "Number of trades taken. (more trades = more reliable statistics)",
    "Period": "The date range this backtest covers (start → end).",
    "Exposure Time [%]": "Share of the period with a position actually open and "
                         "money at work. (context, not good or bad on its own)",
    "Equity Final [$]": "Account value at the end of the test. (higher is better)",
    "Equity Peak [$]": "The highest account value reached during the test. "
                       "(higher is better)",
    "Best Trade [%]": "The return of the single best trade.",
    "Worst Trade [%]": "The return of the single worst trade. (closer to 0 is better)",
    "Avg. Trade [%]": "Average return per trade. (higher is better)",
    "Expectancy [%]": "The average return you can expect from each trade. "
                      "(higher is better)",
    "Max. Trade Duration": "The longest a single trade stayed open.",
    "Avg. Trade Duration": "How long a trade typically stays open.",
    "SQN": "System Quality Number — an overall score combining edge size and "
           "consistency. (higher is better)",
    "Kelly Criterion": "A textbook 'ideal' bet size for long-run growth. (a guide "
                       "only — most traders risk a fraction of it)",
    "Start": "The first day of the backtest.",
    "End": "The last day of the backtest.",
    "Duration": "The total length of the test period.",

    # --- trade-list columns ---
    "Entry": "When the trade was opened.",
    "Exit": "When the trade was closed.",
    "Entry Price": "The index level when the trade opened.",
    "Exit Price": "The index level when the trade closed.",
    "PnL": "Profit or loss on this trade in rupees, for one lot. (higher is better)",
    "Return %": "This trade's gain or loss as a percentage. (higher is better)",

    # --- strategy settings (params, not results) ---
    "n1": "Fast moving-average length in days — reacts quickly to price. "
          "(a strategy setting you choose, not a result)",
    "n2": "Slow moving-average length in days — the steadier trend line. "
          "(a strategy setting)",
    "n": "Look-back length in days for the signal, e.g. the moving-average period. "
         "(a strategy setting)",
    "lot": "Futures lot size — contracts traded per position (Nifty = 65 units). "
           "(a fixed strategy setting)",
    "hold_days": "How many days a position is held before it's closed. "
                 "(a strategy setting)",
    "exit_time": "The time of day the position is closed. (a strategy setting)",
    "entry_offset": "Which trading day to enter on — e.g. 5 = the 5th-from-last "
                    "trading day of the month. (a strategy setting)",
    "exit_offset": "Which trading day to exit on — e.g. 2 = the 2nd trading day of "
                   "the month. (a strategy setting)",
    "drop_pct": "How far price must fall first to trigger a buy, in percent. "
                "(a strategy setting)",
}


def help_for(label):
    """Plain-English help for a column/metric label, or None if not documented."""
    return COLUMN_HELP.get(label)
