# Project Plan

## Objective

Develop a production-grade hybrid ML/LLM automated intraday futures trading bot built from a diversified playbook of specialized deterministic modules. No individual setup must trade daily; the combined playbook must provide enough regular opportunities while preserving strict validation, deterministic risk control, and auditable execution.

The current stage is exploratory research and simulation. It does not attempt to prove a permanent multi-year edge, and passing a research gate does not automatically authorize paper or live trading.

## Delivery Stages

1. **Research and simulation (current):** discover and validate deterministic modules and playbook behavior using chronological out-of-sample testing, realistic costs, and no-lookahead controls.
2. **Paper trading:** operate frozen strategy and risk configurations on live data using simulated orders and fills.
3. **Shadow execution:** exercise the production order lifecycle, position reconciliation, monitoring, and failure handling with order transmission disabled and no market exposure.
4. **Controlled live execution:** add broker routing, credential isolation, deterministic pre-trade risk checks, duplicate-order prevention, reconciliation, kill switches, and limited-size rollout controls.

Advancing stages requires an explicit project policy change and stage-specific acceptance criteria. ML scores and LLM proposals may inform intended actions, but deterministic policy and independent risk controls retain final authority.

## System Architecture

- **Point-in-time data and features:** provide validated, timestamped inputs with explicit freshness and missing-data states.
- **Deterministic playbook:** defines versioned strategy modules and point-in-time activation contracts for their eligible market conditions. Condition eligibility, research eligibility, and default-scheduler admission are separate states; no-trade is valid when no admitted specialist is active.
- **ML layer:** produces versioned, calibrated predictions, rankings, and signal inputs; training and promotion remain offline and reproducible.
- **LLM layer:** produces schema-constrained analysis and proposals with versioned prompts, models, context, and outputs.
- **Policy engine:** deterministically combines playbook state, ML outputs, and permitted LLM proposals into an intended action.
- **Independent risk engine:** applies position, loss, exposure, freshness, market-hours, and kill-switch constraints; rejection is final.
- **Execution and reconciliation:** owns broker credentials, validates approved intents, prevents duplicates, reconciles orders and positions, and fails closed.
- **Monitoring and audit:** records inputs, versions, decisions, overrides, orders, fills, errors, and operator actions for replay.

Model processes must not hold broker credentials or call broker APIs directly. See `docs/hybrid_ml_llm_trading_architecture.md` for the component contracts and staged promotion requirements.

## Data Loading And Normalization

- Use only CSV files discovered under `data/raw`.
- Require the schema `timestamp,symbol,open,high,low,close,volume`.
- Parse source timestamps as UTC and convert them to `America/New_York`.
- Keep continuous futures prices unadjusted.
- Add derived columns for CME-style `trading_session` and `session_segment`.
- Exclude partial sessions from first-pass strategy windows.

## Session Handling

- Under the current implementation, assign bars at or after `18:00 ET` to the next local calendar date; this is not an exchange-calendar calculation.
- Treat `[09:30,16:00) ET` as RTH; a bar starting at `16:00 ET` is ETH.
- Treat all other included bars as ETH.
- Track known closures from the recent data handoff in audit metadata: Good Friday 2026 and the Juneteenth 2026 early close. The session-date helper does not adjust weekends, holidays, or early closes.
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
- Keep live trading, broker connectivity, and credential handling out of the current research stage. Introduce them only after explicit promotion to the appropriate delivery stage.

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

- Use the longest causally valid local history available for the research question. Record exact input files, date coverage, exclusions, and content hashes for every run.
- Use the shared `2026-04-06` through `2026-07-02` window only for cross-instrument comparisons that require identical MNQ/MGC coverage; do not treat it as the universal project history.
- Split discovery, validation, and final holdout chronologically. Use rolling or walk-forward companion folds when the sample supports them.
- Do not optimize on the final holdout.
- Rank by recent expectancy after costs, trade frequency, drawdown, weekly distribution, simplicity, parameter stability, and worse-slippage sensitivity.
- Keep signal evidence separate from tradability. Rare modules may remain research signals, but the combined playbook is responsible for regular opportunity and low activity still blocks standalone tradability.

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
- Report `signal_evidence_status`, `tradability_status`, and `research_track` separately. Use `review_packet_candidate` only as research-review language; it never implies paper-trading approval.

## ML Research Validation

- Train only targets that pass causal coverage, class-balance, chronological-split, and leakage readiness checks.
- Fit imputers, scalers, encoders, calibration mappings, thresholds, and models on permitted training data only.
- Evaluate discrimination, probability calibration, calibration drift, chronological stability, coverage, abstention, feature drift, and out-of-distribution behavior.
- Require counterfactual playbook impact after costs before approving any model release as a non-authoritative signal input.
- Default every model release to `approved_as_signal_input=false`; a model metric or recommendation cannot change this field automatically.
- Model outputs may never authorize orders, sizing, risk overrides, or broker actions.

## Bounded LLM Research

- Start only with a versioned task registry and strict task-specific schemas.
- Keep LLM work outside the order-authority path and treat free-form text as commentary only.
- Record provider/model identifier, prompt version, tool policy, allowlisted inputs, validated output, and abstention or rejection reason.
- LLM proposals may reference allowlisted research entities but may not set quantity, risk limits, credentials, or broker instructions.
