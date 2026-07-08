# Phase 8J Walk-Forward Strategy Mapping Plan

**Goal:** Convert the Phase 8I `time_window:pre_14_00` MNQ VWAP filter candidate into a deterministic StrategySpec-style research artifact and run a bounded walk-forward diagnostic over the de-duplicated Phase 8H/8I trade path.

**Context:** Phase 8H proved the two MNQ VWAP hypotheses are duplicate signals. Phase 8I de-duplicated to one canonical hypothesis and found a fixed no-lookahead pre-14:00 entry filter candidate: net `$13587.90`, stress `$11422.90`, validation `$1699.98`, holdout `$6733.60`, best-day concentration `27.6%`. This is not paper/live promotion. The next step is to map it into a serializable spec and check fold stability before any deeper StrategySpec/backtester integration.

**Architecture:** Add a small Phase 8J module that uses the existing `StrategySpec` shape for serialization, extends allowed exits with `horizon_close`, applies the Phase 8I filter to the de-duplicated trade log, builds rolling chronological folds, scores train/validation/test segments, and writes CSV/JSON/Markdown plus run-scoped artifacts. Keep it diagnostic: no broker/live/paper approval and no LLM trade decisions.

## Steps

1. Extend `src/short_term_edge/strategy_spec.py` to allow `ExitRule("horizon_close", {"time_stop_minutes": 15})` for research specs.
2. Add `tests/test_phase8j_walk_forward_strategy_mapping.py` with failing tests for:
   - `horizon_close` StrategySpec validation and JSON round-trip.
   - building one deterministic Phase 8J StrategySpec from a Phase 8I trade row and top filter row.
   - applying the selected pre-14 filter returns only entry times before `14:00 ET`.
   - rolling folds are chronological and score train/validation/test segments.
   - labels reject/watchlist/candidate based on positive test folds, stress survival, drawdown, and concentration.
   - report includes guardrails, outputs, and no-promotion language.
3. Implement `src/short_term_edge/phase8j_walk_forward_strategy_mapping.py` with:
   - `Phase8JConfig`
   - `build_phase8j_strategy_spec()`
   - `apply_phase8j_strategy_spec()`
   - `generate_phase8j_folds()`
   - `run_phase8j_walk_forward()`
   - `summarize_phase8j_walk_forward()`
   - `render_phase8j_report()`
4. Add `scripts/run_phase8j_walk_forward_strategy_mapping.py` to read:
   - `outputs/phase8i_deduped_mnq_vwap_trade_log.csv`
   - `outputs/phase8i_no_lookahead_filter_results.csv`
   and write:
   - `outputs/phase8j_strategy_spec.json`
   - `outputs/phase8j_filtered_trade_log.csv`
   - `outputs/phase8j_walk_forward_folds.csv`
   - `outputs/phase8j_walk_forward_summary.csv`
   - `reports/phase8j_walk_forward_strategy_mapping_report.md`
   - `artifacts/phase8j_walk_forward_strategy_mapping/<run_id>/`
5. Update `README.md` with Phase 8J outputs and findings.
6. Verify with focused Phase 8J tests, the Phase 8J runner, full unittest discovery, data audit, and a temporary `hermes-verify-` ad-hoc artifact verifier if requested.

## Decision Rule

- `phase8j_strategy_mapping_candidate`: all test folds positive, aggregate test stress positive, fold count sufficient, concentration below limits, and drawdown within limit.
- `phase8j_watchlist_needs_more_history`: positive aggregate behavior but at least one fold/gate is weak.
- `rejected`: fails aggregate test PnL/stress or activity gates.

Even `phase8j_strategy_mapping_candidate` is only a research milestone. No paper/live promotion until a later independent validation/paper-test plan passes.
