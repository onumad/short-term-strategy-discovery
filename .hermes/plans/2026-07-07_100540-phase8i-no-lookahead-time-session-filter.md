# Phase 8I No-Lookahead Time/Session Filter Plan

**Goal:** Convert the Phase 8H diagnostic hint into a strict no-lookahead pre-entry filter test for the de-duplicated MNQ VWAP signal.

**Context:** Phase 8H showed the two selected MNQ VWAP hypotheses are duplicate signals (`2597` overlapping events, Jaccard `1.000`) and that baseline `horizon_close_15m` remains a concentration artifact. The diagnostic `session_bucket_flatten` row looked positive, but it was derived from decomposition and must be retested as explicit pre-entry filters before any `StrategySpec` mapping.

**Approach:** Add Phase 8I as a bounded diagnostic that reads the Phase 8H trade log, de-duplicates to one canonical hypothesis, applies deterministic entry-time/session filters using only `entry_time`/weekday metadata, reports chronological discovery/validation/holdout metrics, and labels candidates conservatively.

## Steps

1. Create `src/short_term_edge/phase8i_no_lookahead_filter.py` with:
   - `Phase8IConfig`
   - `Phase8IFilterSpec`
   - `select_phase8i_source_trades()` to keep one canonical hypothesis from duplicate Phase 8H rows
   - `build_phase8i_filter_specs()` for fixed no-lookahead filters (`baseline_all`, morning windows, pre-14:00, exclude late, weekday variants)
   - `apply_phase8i_filter()` based only on pre-entry timestamp/weekday fields
   - `evaluate_phase8i_filters()` with discovery/validation/holdout, stress PnL, drawdown, concentration, and labels
   - `render_phase8i_report()` with guardrails and decision rule
2. Add `tests/test_phase8i_no_lookahead_filter.py` using TDD:
   - prove de-duplication keeps one canonical hypothesis
   - prove pre-14:00 filtering uses entry-time metadata and removes later rows
   - prove candidate labels require positive validation and holdout, stress survival, and concentration limits
   - prove report includes guardrails/output/decision text
3. Add `scripts/run_phase8i_no_lookahead_filter.py` to read `outputs/phase8h_mnq_vwap_trade_log.csv` and `outputs/phase8h_mnq_vwap_overlap_summary.csv`, write legacy outputs and run-scoped artifacts.
4. Run Phase 8I with `EXPERIMENT_RUN_ID=phase8i-r1-smoke` and inspect outputs.
5. Update `README.md` with Phase 8I results and next decision.
6. Verify with focused tests, full suite, data audit, Phase 8I runner, and an ad-hoc `hermes-verify-` temp script if requested by the guard.

## Expected Outputs

- `outputs/phase8i_deduped_mnq_vwap_trade_log.csv`
- `outputs/phase8i_no_lookahead_filter_results.csv`
- `reports/phase8i_no_lookahead_filter_report.md`
- `artifacts/phase8i_no_lookahead_filter/phase8i-r1-smoke/`

## Decision Rule

- If a filter is stress-positive with positive discovery/validation/holdout and concentration under limits, mark `phase8i_filter_candidate` for later walk-forward-aware StrategySpec mapping.
- If only in-sample/discovery succeeds or concentration remains high, keep it diagnostic/watchlist or reject.
- No paper-trading promotion from Phase 8I alone.
