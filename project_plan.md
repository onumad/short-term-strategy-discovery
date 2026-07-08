# Project Plan

## Objective

Build a diversified playbook of specialized deterministic MNQ intraday setups. No individual setup must trade daily; the combined playbook must provide enough regular opportunities while preserving strict research-only validation.

This project is exploratory. It does not attempt to prove a permanent multi-year edge, does not change official promotion gates, and does not approve live or paper trading unless unchanged gates pass.

## Data Loading And Normalization

- Use only CSV files discovered under `data/raw`.
- Require the schema `timestamp,symbol,open,high,low,close,volume`.
- Parse timestamps into `America/New_York`.
- Keep continuous futures prices unadjusted.
- Add derived columns for CME-style `trading_session` and `session_segment`.
- Exclude partial sessions from first-pass strategy windows.

## Session Handling

- Assign bars at or after `18:00 ET` to the next trading session.
- Treat `09:30-16:00 ET` as RTH.
- Treat all other included bars as ETH.
- Model known closures from the recent data handoff: Good Friday 2026 and Juneteenth 2026 early close.
- Later strategy tests should define explicit no-trade windows, flatten times, and whether signals may use ETH, RTH, or both.

## Costs And Slippage

Later backtests must include:

- Tick size and tick value per contract.
- Commissions, exchange fees, and routing assumptions when known.
- Baseline slippage and a worse-slippage sensitivity run.
- Conservative next-bar execution unless intrabar ordering is explicitly available.

## Backtest Design

- Process bars chronologically.
- Compute indicators only from data available at the decision timestamp.
- Use deterministic rules and serializable parameters.
- Flatten positions by configured time.
- Track daily stop conditions and risk breaches as measurements, not immediate discovery blockers.
- Keep live trading, broker connectivity, and credential handling out of scope.

## Trade Frequency Measurement

Every candidate should report:

- Trades per complete trading day.
- Percent of days with at least one qualified setup.
- Distribution of trades by session segment and time of day.
- Whether the candidate depends on one or two outlier days.

## Candidate Strategy Families

Start with simple, manually tradable intraday ideas:

- Opening range breakout continuation.
- Opening range breakout failure or reversal.
- VWAP reclaim continuation.
- VWAP rejection.
- VWAP pullback in trend.
- Prior day high/low break and hold.
- Prior day high/low sweep and reversal.
- Overnight high/low sweep and reversal.
- Gap continuation.
- Gap fade.
- First-hour trend continuation.
- Midday mean reversion.
- Power hour continuation.
- Momentum after compression.
- Volatility regime filters.

## Discovery And Validation

- Use the complete shared window `2026-04-06` through `2026-07-02`.
- Split discovery and final holdout chronologically inside that window.
- Do not optimize on the final holdout.
- Rank by recent expectancy after costs, trade frequency, drawdown, weekly distribution, simplicity, parameter stability, and worse-slippage sensitivity.
- Prefer useful daily activity over rare clean-looking setups.

## Anti-Lookahead Controls

- No future bars in indicators.
- No repainting signals.
- No same-bar fills unless order of events can be proven.
- No close-only execution assumptions that would be unknowable intrabar.
- Preserve exact configs, commands, data file names, and generated report paths.

## Report Format

Later strategy reports should include:

- Strategy rules and parameters.
- Instrument, timeframe, sessions, and sample period.
- Fees, slippage, fill assumptions, and contract metadata.
- Equity curve, drawdowns, expectancy, profit factor, win rate, average win/loss, and trade distribution.
- Trade frequency and days-active statistics.
- Rule breaches, near-breaches, unstable parameters, and data-quality concerns.
- One of these labels only: `rejected`, `interesting_but_needs_validation`, `watchlist`, `paper_trade_candidate`.
