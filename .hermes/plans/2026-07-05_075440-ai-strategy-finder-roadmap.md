# AI Strategy Finder Roadmap

> **For Hermes:** Use this as the project roadmap. Implement phase-by-phase with tests, reports, deterministic outputs, and commits after each passing milestone.

**Goal:** Evolve this futures research workspace into an AI-assisted, deterministic strategy finder that proposes auditable strategy specs, validates them rigorously, and produces manual paper-trading candidates only.

**Architecture:** Keep the AI/search layer separate from execution. Strategy candidates are serializable deterministic specs; feature generation is no-lookahead; scoring and walk-forward validation decide whether a candidate is rejected, watchlisted, or promoted to paper-test candidate. No live trading, broker adapters, webhooks, order routing, or automated execution.

**Tech Stack:** Python 3.11, pandas, numpy, matplotlib, databento, pyarrow/parquet, unittest. Add new dependencies only when justified; Optuna is optional after deterministic search baselines are stable.

---

## Current State

Completed baseline:

- Initial project snapshot committed.
- Hermes-specific `.hermes.md` project rules committed.
- Databento API key saved outside the repo in Hermes env.
- Historical Databento continuous 1-minute OHLCV downloaded for MNQ and MGC from 2023-01-01 through 2026-07-03.
- Data audit regenerated.
- Phase 5A deterministic AI-search foundation implemented.
- Phase 5B deterministic feature/regime dataset implemented.
- Phase 5C robust deterministic search implemented.
- Canonical test suite currently has 30 tests passing.

Key current outputs:

- `outputs/phase5_ai_candidates.csv`
- `outputs/phase5_feature_summary.csv`
- `outputs/phase5b_features.parquet`
- `outputs/phase5b_feature_summary.csv`
- `outputs/phase5c_search_results.csv`
- `outputs/phase5c_candidate_specs.json`
- `reports/phase5_ai_search_report.md`
- `reports/phase5b_feature_report.md`
- `reports/phase5c_search_report.md`

Current leading candidates:

- `MNQ_opening_range_failure_tf1_982fe6172f`
- `MNQ_opening_range_failure_tf3_1dce415f36`
- `MGC_opening_range_failure_tf1_9454d5e6d4`

---

## Phase 5D: Walk-Forward Validation And Promotion Gates

**Objective:** Determine whether Phase 5C candidates survive repeated chronological train/validation/test folds across the 2023-2026 data.

**Likely files:**

- Create: `src/short_term_edge/walk_forward.py`
- Create: `scripts/run_phase5d_walk_forward.py`
- Create: `tests/test_walk_forward.py`
- Write outputs:
  - `outputs/phase5d_walk_forward_results.csv`
  - `outputs/phase5d_candidate_summary.csv`
  - `reports/phase5d_walk_forward_report.md`

**Implementation steps:**

1. Add a chronological fold generator.
   - No shuffling.
   - No leakage.
   - Support rolling windows such as 9-month train, 3-month validation, 3-month test.
   - Support candidate evaluation on each split.

2. Write tests for split correctness.
   - Folds are ordered.
   - Train ends before validation.
   - Validation ends before test.
   - No session appears in multiple segments within one fold.

3. Load `outputs/phase5c_candidate_specs.json` and evaluate top candidates.
   - Focus MNQ first.
   - Include MGC after MNQ path is stable.

4. Add promotion labels.
   - `rejected`
   - `watchlist`
   - `robust_research_candidate`
   - `paper_test_candidate`

5. Generate a report that emphasizes stability over maximum PnL.

**Verification:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/run_phase5d_walk_forward.py
```

**Commit:**

```bash
git add src/short_term_edge/walk_forward.py scripts/run_phase5d_walk_forward.py tests/test_walk_forward.py outputs/phase5d_* reports/phase5d_walk_forward_report.md
git commit -m "feat: add phase 5d walk-forward validation"
```

---

## Phase 5E: Paper-Test Candidate Protocol Generator

**Objective:** Convert any Phase 5D survivor into a manual paper-trading protocol with exact setup rules, daily checklist, risk gates, and invalidation criteria.

**Likely files:**

- Create: `src/short_term_edge/paper_protocol.py`
- Create: `scripts/run_phase5e_paper_protocol.py`
- Create: `tests/test_paper_protocol.py`
- Write outputs:
  - `reports/phase5e_manual_paper_trading_plan.md`
  - `outputs/phase5e_daily_checklist.csv`
  - `outputs/phase5e_trade_log_template.csv`

**Implementation steps:**

1. Define a `PaperProtocol` object from a strategy spec and validation summary.
2. Render exact manual rules:
   - instrument
   - timeframe
   - opening range definition
   - valid long/short setup
   - entry timing
   - stop/target
   - max trades per day
   - stop-after-first-loser behavior
   - flatten time
3. Add invalidation rules:
   - 20-session negative PnL
   - max drawdown threshold
   - worst rolling 5-session threshold
   - consecutive losing days
   - rule violation
4. Produce a daily checklist and trade log template.

**Verification:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/run_phase5e_paper_protocol.py
```

**Commit:**

```bash
git commit -m "feat: generate phase 5e paper-test protocol"
```

---

## Phase 5F: Full-History Search Scaling

**Objective:** Scale deterministic search beyond the bounded 63-session window while keeping runtime controlled and outputs deterministic.

**Likely files:**

- Modify: `src/short_term_edge/phase5c.py`
- Modify/Create: `src/short_term_edge/search_space.py`
- Create: `scripts/run_phase5f_full_history_search.py`
- Create: `tests/test_search_space.py`
- Write outputs:
  - `outputs/phase5f_full_history_search_results.csv`
  - `outputs/phase5f_candidate_specs.json`
  - `reports/phase5f_full_history_search_report.md`

**Implementation steps:**

1. Extract the current candidate generation grid into a dedicated search-space module.
2. Add deterministic runtime controls:
   - seed
   - max candidates
   - per-family caps
   - symbol ordering
   - optional session window selection
3. Add cache/reuse logic where safe.
4. Run MNQ first across longer history.
5. Add MGC after MNQ runtime is acceptable.

**Verification:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/run_phase5f_full_history_search.py --symbol MNQ --max-candidates 64
```

**Commit:**

```bash
git commit -m "feat: scale deterministic full-history search"
```

---

## Phase 5G: Optuna Or Bayesian Search Experiment

**Objective:** Test whether a smarter parameter search improves candidate discovery beyond deterministic seeded search, without making the system opaque.

**Dependency decision:** Add `optuna` only if Phase 5F shows deterministic grids are too inefficient or too narrow.

**Likely files:**

- Modify: `requirements.txt` if adding Optuna.
- Create: `src/short_term_edge/optuna_search.py`
- Create: `scripts/run_phase5g_optuna_search.py`
- Create: `tests/test_optuna_search.py`
- Write outputs:
  - `outputs/phase5g_optuna_trials.csv`
  - `outputs/phase5g_candidate_specs.json`
  - `reports/phase5g_optuna_search_report.md`

**Implementation steps:**

1. Define deterministic objective with fixed sampler seed.
2. Limit search to serializable deterministic strategy specs.
3. Penalize:
   - drawdown
   - low active-day percentage
   - concentration
   - complexity
   - weak holdout
   - slippage stress failure
4. Compare Optuna results against Phase 5F deterministic search results.

**Verification:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/run_phase5g_optuna_search.py --trials 50
```

**Commit:**

```bash
git commit -m "feat: add bounded optuna strategy search experiment"
```

---

## Phase 5H: Candidate Ranking Model

**Objective:** Train a simple model that ranks candidate specs or candidate/fold summaries by likelihood of surviving validation. The model does not generate trades.

**Likely files:**

- Modify: `requirements.txt` to add `scikit-learn` if not already present.
- Create: `src/short_term_edge/candidate_model.py`
- Create: `scripts/run_phase5h_candidate_model.py`
- Create: `tests/test_candidate_model.py`
- Write outputs:
  - `outputs/phase5h_candidate_training_set.csv`
  - `outputs/phase5h_model_scores.csv`
  - `reports/phase5h_candidate_model_report.md`

**Implementation steps:**

1. Build a training table from candidate specs, Phase 5C scores, and Phase 5D fold results.
2. Define labels such as `survived_walk_forward` or `paper_test_candidate`.
3. Train simple baseline models only:
   - logistic regression
   - random forest
   - histogram gradient boosting
4. Report feature importance and calibration.
5. Do not use the model to emit trade signals.

**Verification:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/run_phase5h_candidate_model.py
```

**Commit:**

```bash
git commit -m "feat: add candidate survival ranking model"
```

---

## Phase 5I: Regime Filter Research

**Objective:** Research whether prior-session and pre-open features can filter candidate strategies by day without changing deterministic entry/exit rules.

**Likely files:**

- Create: `src/short_term_edge/regime_filter.py`
- Create: `scripts/run_phase5i_regime_filter.py`
- Create: `tests/test_regime_filter.py`
- Write outputs:
  - `outputs/phase5i_regime_filter_results.csv`
  - `reports/phase5i_regime_filter_report.md`

**Implementation steps:**

1. Use Phase 5B features available before or at RTH open.
2. Build simple filters:
   - volatility regime
   - overnight range regime
   - gap regime
   - prior-session return regime
   - day-of-week/month regime
3. Compare unfiltered vs filtered performance across walk-forward folds.
4. Reject filters that reduce trade count too much or only improve one fold.

**Verification:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/run_phase5i_regime_filter.py
```

**Commit:**

```bash
git commit -m "feat: research deterministic regime filters"
```

---

## Phase 6A: Data Expansion And Normalization

**Objective:** Add more instruments and/or more history only after MNQ/MGC validation infrastructure is stable.

Potential instruments:

- `ES`
- `MES`
- `NQ`
- `MNQ`
- `GC`
- `MGC`

**Important:** Estimate Databento cost before download and ask the user before any billable download.

**Likely files:**

- Modify: `scripts/download_databento_ohlcv.py`
- Modify: `src/short_term_edge/instruments.py`
- Modify tests and audit report logic.

**Verification:**

```bash
./.venv/Scripts/python.exe scripts/audit_data.py
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

---

## Phase 6B: Cross-Instrument Robustness

**Objective:** Check whether strategy families generalize across related instruments instead of only fitting one market.

Examples:

- MNQ vs NQ
- MGC vs GC
- MES vs ES

Deliverables:

- `reports/phase6b_cross_instrument_report.md`
- `outputs/phase6b_cross_instrument_results.csv`

---

## Phase 6C: Research Dashboard Or Review Notebook

**Objective:** Make review easier with deterministic static outputs, not live trading.

Options:

- Markdown report only.
- Static HTML report.
- Jupyter notebook for inspection.

Avoid building a live dashboard until research workflow is stable.

---

## Ongoing Quality Gates

Every phase must preserve:

- deterministic outputs
- no live trading or broker integration
- no API keys in repo
- no webhooks/order routing
- no LLM-driven discretionary trade decisions
- no-lookahead tests
- canonical test pass before completion

Canonical verification:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Data audit after data changes:

```bash
./.venv/Scripts/python.exe scripts/audit_data.py
```

Git discipline:

```bash
git status --short --branch
```

Do not push unless the user explicitly asks.

---

## Recommended Immediate Next Step

Implement **Phase 5D: Walk-Forward Validation And Promotion Gates**, focused on the two leading MNQ candidates:

- `MNQ_opening_range_failure_tf1_982fe6172f`
- `MNQ_opening_range_failure_tf3_1dce415f36`

Then include the leading MGC candidate after the MNQ path is stable:

- `MGC_opening_range_failure_tf1_9454d5e6d4`

The key question for Phase 5D:

> Are the Phase 5C robust candidates stable across multiple chronological out-of-sample folds, or are they just strong on the recent 63-session window?
