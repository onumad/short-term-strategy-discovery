# Phase 8L Fixed No-Lookahead Filter Retest Implementation Plan

> **For Hermes:** Implement this plan directly with strict TDD. Do not commit unless explicitly asked.

**Goal:** Retest Phase 8K diagnostic filter candidates as fixed no-lookahead rules using chronological split and rolling walk-forward evidence.

**Architecture:** Add a Phase 8L module that consumes `outputs/phase8j_filtered_trade_log.csv` and `outputs/phase8k_candidate_actions.csv`, converts `fixed_filter_retest` actions into deterministic filter specs, applies those filters to the fixed Phase 8J trade log, and ranks candidates with split + walk-forward gates. Preserve legacy outputs and run-scoped artifact manifests.

**Tech Stack:** Python 3.11, pandas, unittest, existing `backtest.split_sessions`, Phase 8J fold helpers, run-scoped artifact helpers.

---

## Current Context

Phase 8K found diagnostic-only candidates from the Phase 8J weak fold. Top candidates include:

1. `exclude weekday=Wednesday`
2. `exclude minute_bucket=10:00-10:30`
3. `exclude weekday=Tuesday`
4. `exclude minute_bucket=12:30-13:00`
5. `exclude rth_bucket=10:00-11:00`

These are post-diagnostic observations. Phase 8L must treat them as fixed rules and retest them against the full Phase 8J filtered trade log. No rule may be promoted from Phase 8L alone.

## Files To Add

- `src/short_term_edge/phase8l_fixed_filter_retest.py`
- `tests/test_phase8l_fixed_filter_retest.py`
- `scripts/run_phase8l_fixed_filter_retest.py`

## Files To Modify

- `README.md`

## Outputs

Legacy outputs:

- `outputs/phase8l_filter_retest_results.csv`
- `outputs/phase8l_filter_retest_specs.json`
- `outputs/phase8l_filtered_trade_logs.csv`
- `reports/phase8l_fixed_filter_retest_report.md`

Run-scoped outputs:

```text
artifacts/phase8l_fixed_filter_retest/<run_id>/
  manifest.json
  results.csv
  specs.json
  filtered_trade_logs.csv
  report.md
```

## Implementation Steps

### Task 1: Write failing Phase 8L tests

Create `tests/test_phase8l_fixed_filter_retest.py` with tests for:

- building fixed filter specs only from Phase 8K `fixed_filter_retest` rows;
- applying `exclude weekday=Wednesday`, `exclude minute_bucket=10:00-10:30`, and `exclude rth_bucket=10:00-11:00` using entry/session metadata only;
- evaluating split metrics with discovery/validation/holdout and walk-forward metrics;
- labeling all outputs as research/watchlist/rejected, never paper/live promotion;
- rendering report guardrails and output paths.

Run:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8l_fixed_filter_retest.py' -v
```

Expected: fail because the module does not exist.

### Task 2: Implement Phase 8L core

Create `src/short_term_edge/phase8l_fixed_filter_retest.py` with:

- `Phase8LConfig`
- `Phase8LFilterSpec`
- `build_phase8l_filter_specs`
- `apply_phase8l_filter`
- `evaluate_phase8l_filters`
- `render_phase8l_report`

Scoring/labels:

- `phase8l_fixed_filter_candidate`: positive net/stress, discovery/validation/holdout, positive walk-forward test PnL/stress, all test folds positive, drawdown and concentration within limits.
- `phase8l_watchlist_needs_strategy_remap`: aggregate positive but at least one fold/concentration/drawdown gate weak.
- `rejected` / `insufficient_activity`: hard failures.

### Task 3: Implement runner

Create `scripts/run_phase8l_fixed_filter_retest.py` to:

1. Read Phase 8J filtered trades and Phase 8K candidate actions.
2. Build specs and evaluate them.
3. Write legacy outputs.
4. Write run-scoped outputs and manifest.
5. Print row counts and top candidate/label.

### Task 4: Update README

Append Phase 8L command, outputs, and current result. Make clear Phase 8L remains research-only and cannot promote a candidate.

### Task 5: Verify

Run:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8l_fixed_filter_retest.py' -v
EXPERIMENT_RUN_ID=phase8l-r1-smoke ./.venv/Scripts/python.exe scripts/run_phase8l_fixed_filter_retest.py
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/audit_data.py
```

If Hermes requests focused evidence, create a temporary verifier under `C:\Users\ulzii\AppData\Local\Temp` with a `hermes-verify-` prefix, run it, clean it up, and report it as ad-hoc verification.

## Guardrails

- Research/simulation only.
- No live trading approval.
- No broker adapters, order routing, API-key storage, webhooks, or automated execution.
- Phase 8L filters are fixed retests of Phase 8K diagnostics, not promotion.
- Do not tune on the same weak fold and call it validation.
