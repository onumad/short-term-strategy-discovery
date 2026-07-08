# Phase 8H MNQ VWAP Concentration And Exit Diagnostic Plan

> **For Hermes:** Execute directly in this repo unless the user asks for a separate worktree. Do not commit unless explicitly asked.

**Goal:** Decide whether the Phase 8G MNQ VWAP event edge is a real repeatable structure or mostly a one-day / one-trade artifact, and identify the next deterministic exit/filter shape before any broader parameter sweep.

**Architecture:** Add a bounded diagnostic phase that reuses Phase 8G selected event candidates and local OHLCV data, exports trade-level rows for the only positive/stress-positive horizon-close variants, decomposes PnL by day/time/regime, and tests a small set of pre-entry/no-trade filters plus non-same-bar exit alternatives. The output is diagnostic-only and must not promote paper or live trading.

**Tech Stack:** Python 3.11 via `./.venv/Scripts/python.exe`, pandas, existing `short_term_edge` modules, `unittest`, local CSVs under `data/raw`.

---

## Current Context

Phase 8G is complete and verified. It produced `48` calibration rows in `outputs/phase8g_event_execution_calibration.csv`.

Observed Phase 8G facts from the current CSV/report:

- Labels: `{'rejected_timing_cost': 38, 'concentrated': 8, 'cost_sensitive': 2}`.
- The only positive/stress-positive rows are MNQ VWAP horizon-close variants with `time_stop=15m`.
- The two top hypotheses are effectively duplicate-shaped:
  - `MNQ_vwap_pullback_continuation_tf5_long_only_a25f2113`
  - `MNQ_vwap_reclaim_rejection_tf1_long_only_bdbad7c5`
- Best row: `next_5m_close`, no stop, horizon close `15m`, net `$8578.72`, 4-tick stress `$5981.72`, `2597` trades, max DD `$-6801.92`, but one-day concentration risk.
- Fixed stop/target variants all failed with `rejected_timing_cost`.
- Phase 8G decision rules say:
  - if horizon-close rows are positive but fixed stop/target rows fail, design better deterministic exits before parameter sweeps;
  - if concentration dominates, require pre-entry filters before deeper backtests.

Therefore, the next step should **not** be a wider strategy search. It should be a diagnostic bridge between Phase 8G and a future executable `StrategySpec` family.

## Proposed Next Milestone

Implement **Phase 8H: MNQ VWAP concentration and exit-shape diagnostic**.

Primary question:

> After removing or controlling the dominant outlier day/trade/time bucket, does the MNQ VWAP horizon-close edge remain positive under realistic costs and 4-tick stress?

Secondary question:

> Can we express the surviving behavior as deterministic pre-entry filters and exits that avoid same-bar stop/target ambiguity?

## Non-Goals

- Do not add broker adapters, order routing, API-key storage, webhooks, or live execution.
- Do not approve paper-trading or live-trading promotion.
- Do not run a broad parameter sweep.
- Do not add LLM-driven trading decisions.
- Do not widen back to MGC unless the diagnostic explicitly invalidates the MNQ path and a later plan chooses a new branch.

---

## Task 1: Add Phase 8H Trade-Level Diagnostic Module

**Objective:** Create a reusable module that replays Phase 8G’s selected candidates and keeps trade-level rows for specific calibration variants.

**Files:**

- Create: `src/short_term_edge/phase8h_mnq_vwap_concentration_exit_diagnostic.py`
- Read/reuse: `src/short_term_edge/phase8g_event_execution_calibration.py`
- Test: `tests/test_phase8h_mnq_vwap_concentration_exit_diagnostic.py`

**Implementation shape:**

- Define `Phase8HConfig` with narrow defaults:
  - `target_instrument="MNQ"`
  - `target_families=("vwap_pullback_continuation", "vwap_reclaim_rejection")`
  - `target_entry_delay="next_5m_close"`
  - `baseline_time_stop=15`
  - `concentration_limit=0.35`
  - `min_trades=250`
- Add `select_phase8h_inputs(event_results, phase8g_results, config)`:
  - require `phase8e_label == "backtest_candidate"`
  - require Phase 8G calibration row with `stop_model == "none"`, `target_model == "horizon_close"`, `time_stop == 15`, `entry_delay == "next_5m_close"`
  - require `net_pnl > 0` and `slippage_4_ticks_net_pnl > 0`
  - keep only MNQ VWAP families by default
- Add a trade replay function that returns one row per executable event with:
  - `hypothesis_id`, `instrument`, `family`, `side`, `timeframe`
  - `event_time`, `entry_time`, `exit_time`, `trading_session`
  - `entry_price`, `exit_price`, `exit_reason`
  - `gross_pnl`, `net_pnl`, `stress_net_pnl`
  - `minute_of_day`, `rth_bucket`, `weekday`

**Notes:**

- Reuse Phase 8G internals where practical, but avoid making a large refactor unless tests force it.
- If a tiny helper extraction is needed, make it in `phase8g_event_execution_calibration.py` and cover it.

## Task 2: Write Unit Tests For Selection And Trade Rows

**Objective:** Lock down the diagnostic’s scope and prevent accidental broadening.

**Files:**

- Create: `tests/test_phase8h_mnq_vwap_concentration_exit_diagnostic.py`

**Tests:**

1. `test_select_phase8h_inputs_keeps_only_positive_mnq_vwap_horizon_rows`
   - Build small fake Phase 8E and Phase 8G frames.
   - Include one positive MNQ VWAP row, one MGC row, one fixed-stop row, and one negative row.
   - Assert only the positive MNQ VWAP horizon row is selected.

2. `test_replay_phase8h_trades_returns_trade_level_cost_columns`
   - Use synthetic MNQ bars similar to `tests/test_phase8g_event_execution_calibration.py`.
   - Assert output contains `net_pnl`, `stress_net_pnl`, `trading_session`, `minute_of_day`, and `rth_bucket`.

3. `test_phase8h_labels_concentrated_when_best_day_exceeds_limit`
   - Create a small trade frame where one day contributes more than `35%` of positive net.
   - Assert label is `concentrated` and notes mention one-day concentration.

**Focused verification command:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8h_mnq_vwap_concentration_exit_diagnostic.py' -v
```

Expected: all new tests pass.

## Task 3: Add Concentration Decomposition

**Objective:** Measure exactly where the apparent edge comes from before trying to rescue it.

**Files:**

- Modify/Create in `src/short_term_edge/phase8h_mnq_vwap_concentration_exit_diagnostic.py`

**Add summaries:**

- By `hypothesis_id`.
- By `trading_session`.
- By `weekday`.
- By `rth_bucket`, using simple fixed buckets such as:
  - `09:30-10:00`
  - `10:00-11:00`
  - `11:00-12:00`
  - `12:00-14:00`
  - `14:00-15:30`
  - `15:30-16:00`
- Leave-one-day-out metrics:
  - total net excluding the best day
  - stress net excluding the best day
  - max drawdown excluding the best day
  - active session percentage excluding the best day
- Duplicate-overlap metrics between the two top VWAP hypotheses:
  - event timestamp overlap count
  - event timestamp Jaccard ratio
  - trade PnL correlation on shared event timestamps, if enough shared rows exist

**Decision labels:**

- `phase8h_candidate_filter_design`: positive and stress-positive after excluding best day, concentration within limits, adequate activity.
- `phase8h_needs_time_filter`: total edge survives only in specific time buckets.
- `phase8h_duplicate_signal`: two hypotheses overlap enough that they should be treated as one signal.
- `rejected_concentration_artifact`: edge fails after excluding best day or best-trade concentration remains too high.
- `rejected_cost_or_drawdown`: stress PnL or drawdown fails after decomposition.

## Task 4: Add Small Exit-Shape Grid Without Same-Bar Stop/Target Dependence

**Objective:** Test deterministic exits suggested by Phase 8G without immediately returning to same-bar fixed stop/target ambiguity.

**Files:**

- Modify/Create: `src/short_term_edge/phase8h_mnq_vwap_concentration_exit_diagnostic.py`
- Test: `tests/test_phase8h_mnq_vwap_concentration_exit_diagnostic.py`

**Exit shapes to compare:**

- `horizon_close_10m`
- `horizon_close_15m` baseline
- `horizon_close_20m`
- `trailing_time_stop`: if PnL is positive after 10 minutes, hold to 20 minutes; otherwise exit at 10 minutes
- `session_bucket_flatten`: force no entries after the last profitable bucket identified in the decomposition

**Rules:**

- Keep these as diagnostics, not final strategy definitions.
- Avoid intrabar stop/target ordering assumptions in this step.
- Include base cost and 4-tick stress for every row.

## Task 5: Add Runner And Artifacts

**Objective:** Produce reproducible Phase 8H outputs with the same artifact conventions as Phase 8G.

**Files:**

- Create: `scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py`
- Output: `outputs/phase8h_mnq_vwap_trade_log.csv`
- Output: `outputs/phase8h_mnq_vwap_concentration_summary.csv`
- Output: `outputs/phase8h_mnq_vwap_exit_shape_results.csv`
- Report: `reports/phase8h_mnq_vwap_concentration_exit_diagnostic_report.md`
- Run artifacts: `artifacts/phase8h_mnq_vwap_concentration_exit_diagnostic/<run_id>/`

**Runner inputs:**

- `outputs/phase8e_event_scout_results.csv`
- `outputs/phase8g_event_execution_calibration.csv`
- local OHLCV CSVs discovered from `data/raw`

**Runner command:**

```bash
./.venv/Scripts/python.exe scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py
```

**Manifest guardrails:**

- Include the existing research/simulation guardrails.
- Include data files used.
- Include selected hypothesis IDs.
- Include output paths and label counts.

## Task 6: Render Report With A Hard Decision Gate

**Objective:** Make the report end with a clear next action instead of more open-ended sweeping.

**Report sections:**

1. Scope and guardrails.
2. Why Phase 8H exists: Phase 8G positives were profitable but concentrated.
3. Selected hypotheses and overlap.
4. Baseline trade-level concentration decomposition.
5. Leave-one-day-out results.
6. Time bucket / weekday results.
7. Exit-shape comparison.
8. Decision rule and recommended next step.

**Decision rule:**

- If leave-one-best-day-out stress PnL is still positive and concentration falls under `0.35`, then the next milestone is a narrow executable `StrategySpec` mapping for the surviving MNQ VWAP family with the selected time filter/exit.
- If only a time bucket survives, implement a narrow pre-entry time/session filter diagnostic before StrategySpec mapping.
- If excluding the best day makes stress PnL negative, park the MNQ VWAP event path as a concentration artifact and return to Phase 8D/8E queue expansion, prioritizing families not yet executable.
- If the two VWAP hypotheses have high timestamp overlap, de-duplicate them and treat the better-scoring variant as a single signal family.

## Task 7: Update README Current Scope

**Objective:** Keep the repo’s handoff documentation current after Phase 8H runs.

**Files:**

- Modify: `README.md`

**Update:**

- Add a short `Phase 8H` section with command and outputs.
- Replace the Phase 8G-only next-step language with the Phase 8H decision.
- Preserve all research and live-trading guardrails.

## Task 8: Verification

**Objective:** Verify the new phase with focused tests, full suite, audit, and a real script run.

**Commands:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8h_mnq_vwap_concentration_exit_diagnostic.py' -v
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/audit_data.py
EXPERIMENT_RUN_ID=phase8h-r1-smoke ./.venv/Scripts/python.exe scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py
```

**Expected:**

- All tests pass.
- Data audit passes.
- Phase 8H runner writes CSV/report/run-scoped artifacts.
- Report ends with one of the explicit decision labels, not a promotion.

## Files Likely To Change

- `src/short_term_edge/phase8h_mnq_vwap_concentration_exit_diagnostic.py` — new diagnostic module.
- `scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py` — new reproducible runner.
- `tests/test_phase8h_mnq_vwap_concentration_exit_diagnostic.py` — new tests.
- `README.md` — update current state after the run.
- Generated artifacts under:
  - `outputs/phase8h_mnq_vwap_trade_log.csv`
  - `outputs/phase8h_mnq_vwap_concentration_summary.csv`
  - `outputs/phase8h_mnq_vwap_exit_shape_results.csv`
  - `reports/phase8h_mnq_vwap_concentration_exit_diagnostic_report.md`
  - `artifacts/phase8h_mnq_vwap_concentration_exit_diagnostic/phase8h-r1-smoke/`

## Risks And Tradeoffs

- Phase 8G internals currently expose mostly summarized calibration behavior; trade-level reuse may require a small helper extraction. Keep this minimal and tested.
- The two top MNQ VWAP hypotheses may be near-duplicates. Treating them as independent would overstate evidence.
- Positive horizon-close behavior without stops may be hard to translate into executable risk management. Phase 8H should identify whether a non-ambiguous exit shape exists before any StrategySpec mapping.
- If the edge disappears after excluding one day, stop this branch quickly rather than tuning around noise.

## Recommended Immediate Action

Start Phase 8H with Task 1 and Task 2 only: create the diagnostic module and tests for selection/trade-level replay. Once those pass, add decomposition and runner artifacts.
