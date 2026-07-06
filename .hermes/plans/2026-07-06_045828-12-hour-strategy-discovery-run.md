# 12-Hour Strategy Discovery Run Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task if delegating. For direct execution, follow TDD and commit each verified milestone.

**Goal:** Run a 12-hour autonomous research/development cycle that completes the remaining Phase 6A deterministic search expansion, analyzes why candidates fail, then implements a narrower Phase 6B focused on reducing slippage, concentration, and ambiguity instead of blindly expanding the search space.

**Architecture:** Continue the current deterministic, local-data-only futures research pipeline. Use resumable/checkpointed scripts for expensive candidate scoring, strict no-lookahead tests, bounded runtime batches, and milestone commits after verification. No live trading, broker integrations, webhooks, API-key storage, or automated execution.

**Tech Stack:** Python 3.11 via `./.venv/Scripts/python.exe`, pandas/numpy, unittest, local CSV data under `data/raw`, deterministic strategy specs under `src/short_term_edge`.

---

## Current Context

- Repo: `C:\Users\ulzii\Documents\Short Term Strategy Discovery`
- Branch: `master`
- Current status at plan creation: clean
- Latest relevant commits:
  - `104380f feat: advance phase 6a checkpoint`
  - `baff185 feat: add phase 6a checkpoint refresh`
  - `fd6f894 feat: add phase 6a search expansion`
  - `8d41c34 feat: complete phase 5n prefilter artifacts`
  - `175eb6c feat: add resumable phase 5n prefilter`
- Phase 5N complete: 40/40 candidates scored, all rejected.
- Phase 6A in progress: 17/48 candidates scored, all rejected.
- Current Phase 6A top candidate:
  - `MNQ_prior_session_levels_tf1_2fea04300c`
  - score `-321.2288`
  - label `rejected`
  - net `-$1,235.42`
  - 4-tick slip `-$4,634.42`
- Dominant observed failure modes:
  - 4-tick slippage stress
  - one-day concentration
  - one-trade concentration
  - drawdown beyond prefilter cap
  - negative validation/holdout splits

## Guardrails

- Research/simulation only.
- Do not add live trading, broker adapters, order routing, webhooks, credential storage, or automated execution.
- Use only local CSV data under `data/raw`.
- Preserve `America/New_York`, CME session handling, RTH, bar-start timestamp semantics, and no-lookahead constraints.
- Keep MNQ first. Do not expand to MGC unless Phase 6A/6B produces a clear MNQ result and there is time left.
- Use TDD for every code change.
- Commit only after targeted tests, relevant script run, and canonical tests pass.
- Canonical verification:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

---

# 12-Hour Timeline

## Hour 0-2: Complete Phase 6A Scoring

### Task 1: Verify clean starting state

**Objective:** Ensure no previous worker left partial changes.

**Files:** None expected.

**Commands:**

```bash
git status --short --branch
git log --oneline -8
```

**Expected:** clean `master`, latest commit around Phase 6A checkpoint.

### Task 2: Continue Phase 6A resumable batches

**Objective:** Score all remaining Phase 6A candidates.

**Files:**
- Modify/generated: `outputs/phase6a_expansion_results.csv`
- Modify/generated: `outputs/phase6a_candidate_specs.json`
- Modify/generated: `reports/phase6a_search_dimension_expansion_report.md`

**Run batches:**

```bash
PHASE6A_MAX_NEW_SPECS=6 ./.venv/Scripts/python.exe scripts/run_phase6a_search_dimension_expansion.py
```

Repeat until report says:

```text
selected 48 specs
48 scored candidates
```

If a batch exceeds practical runtime, reduce batch size:

```bash
PHASE6A_MAX_NEW_SPECS=3 ./.venv/Scripts/python.exe scripts/run_phase6a_search_dimension_expansion.py
```

**Verification after each successful batch:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase6a.py' -v
```

**Commit after meaningful checkpoint:**

```bash
git add outputs/phase6a_expansion_results.csv outputs/phase6a_candidate_specs.json reports/phase6a_search_dimension_expansion_report.md
git commit -m "feat: advance phase 6a scoring"
```

Do not commit if the script failed or outputs are inconsistent.

---

## Hour 2-3: Phase 6A Failure-Mode Summary

### Task 3: Write failing tests for Phase 6A failure analysis

**Objective:** Add deterministic analysis of rejection reasons before implementing reporting code.

**Files:**
- Create: `tests/test_phase6a_failure_analysis.py`
- Create/modify: `src/short_term_edge/phase6a_analysis.py`
- Create: `scripts/run_phase6a_failure_analysis.py`

**Test behavior:**

```python
def test_summarize_failure_modes_counts_semicolon_notes():
    rows = pd.DataFrame([
        {"phase6a_label": "rejected", "phase6a_notes": "fails aggregate 4-tick slippage stress; one-day concentration risk"},
        {"phase6a_label": "rejected", "phase6a_notes": "fails aggregate 4-tick slippage stress; drawdown exceeds prefilter cap"},
        {"phase6a_label": "watchlist_needs_walk_forward", "phase6a_notes": "negative holdout split"},
    ])
    summary = summarize_failure_modes(rows)
    assert summary.loc["fails aggregate 4-tick slippage stress", "count"] == 2
    assert summary.loc["one-day concentration risk", "count"] == 1
```

**Run RED:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase6a_failure_analysis.py' -v
```

Expected: fail because module/function is missing.

### Task 4: Implement Phase 6A failure analysis

**Objective:** Produce a concise report identifying which gates are killing candidates.

**Implementation outline:**

Create `src/short_term_edge/phase6a_analysis.py` with:

```python
from __future__ import annotations

from collections import Counter
import pandas as pd


def summarize_failure_modes(results: pd.DataFrame) -> pd.DataFrame:
    counter: Counter[str] = Counter()
    for notes in results.get("phase6a_notes", pd.Series(dtype=str)).fillna(""):
        for note in str(notes).split(";"):
            cleaned = note.strip()
            if cleaned:
                counter[cleaned] += 1
    rows = [{"failure_mode": key, "count": value} for key, value in counter.items()]
    if not rows:
        return pd.DataFrame(columns=["failure_mode", "count"])
    return pd.DataFrame(rows).sort_values(["count", "failure_mode"], ascending=[False, True]).set_index("failure_mode")
```

Create `scripts/run_phase6a_failure_analysis.py` to read:

```text
outputs/phase6a_expansion_results.csv
```

and write:

```text
outputs/phase6a_failure_modes.csv
reports/phase6a_failure_analysis_report.md
```

**Run GREEN:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase6a_failure_analysis.py' -v
./.venv/Scripts/python.exe scripts/run_phase6a_failure_analysis.py
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

**Commit:**

```bash
git add src/short_term_edge/phase6a_analysis.py tests/test_phase6a_failure_analysis.py scripts/run_phase6a_failure_analysis.py outputs/phase6a_failure_modes.csv reports/phase6a_failure_analysis_report.md
git commit -m "feat: add phase 6a failure analysis"
```

---

## Hour 3-6: Phase 6B Ambiguity/Concentration Reduction Search

### Task 5: Define Phase 6B scope from actual failure modes

**Objective:** Avoid random expansion; target the failure modes from Phase 6A.

Expected Phase 6B idea:

```text
Lower frequency / lower ambiguity deterministic variants:
- one trade per day
- no first 10-15 minutes after RTH open
- no final 15-30 minutes before close
- require trigger buffer beyond OR/prior levels
- require minimum opening range width
- require minimum prior/overnight range bucket
- wider target/stop ratios only where trade count remains adequate
```

### Task 6: Write failing Phase 6B tests

**Files:**
- Create: `tests/test_phase6b.py`
- Create: `src/short_term_edge/phase6b.py`
- Create: `scripts/run_phase6b_ambiguity_reduction.py`

**Test behaviors:**

1. `select_ambiguity_reduction_specs` is MNQ-only, deterministic, bounded.
2. Selected specs include explicit risk/entry parameters that reduce ambiguity/frequency, e.g. one trade per day or entry buffer.
3. Ranking promotes lower concentration and lower drawdown over raw net PnL.

Example test sketch:

```python
def test_phase6b_specs_are_mnq_only_deterministic_and_bounded():
    config = Phase6BConfig(max_specs=24)
    first = select_ambiguity_reduction_specs(config)
    second = select_ambiguity_reduction_specs(config)
    assert [s.canonical_id() for s in first] == [s.canonical_id() for s in second]
    assert len(first) <= 24
    assert {s.instrument for s in first} == {"MNQ"}
    assert any(s.risk.params.get("max_trades_per_day") == 1 for s in first)
```

**Run RED:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase6b.py' -v
```

Expected: fail because `short_term_edge.phase6b` is missing.

### Task 7: Implement Phase 6B module

**Objective:** Create a bounded deterministic candidate selector and scorer focused on fewer, cleaner trades.

**Files:**
- Create: `src/short_term_edge/phase6b.py`

**Implementation requirements:**

- Use existing `StrategySpec` model.
- Reuse existing proposal/spec functions where possible.
- Do not invent live execution hooks.
- Add only serializable deterministic parameters.
- If current signal engine does not support new entry buffers/time avoids, first inspect `src/short_term_edge/phase4a.py` and neighboring tests. Add behavior with tests there before using it in Phase 6B.

**Likely config:**

```python
@dataclass(frozen=True)
class Phase6BConfig:
    symbol: str = "MNQ"
    max_specs: int = 24
    timeframes: tuple[int, ...] = (1, 2, 3, 5)
    opening_range_minutes: tuple[int, ...] = (15, 30, 60)
```

### Task 8: Implement Phase 6B runner

**Files:**
- Create: `scripts/run_phase6b_ambiguity_reduction.py`
- Generated: `outputs/phase6b_candidate_specs.json`
- Generated: `outputs/phase6b_ambiguity_reduction_results.csv`
- Generated: `reports/phase6b_ambiguity_reduction_report.md`

**Run:**

```bash
PHASE6B_MAX_NEW_SPECS=6 ./.venv/Scripts/python.exe scripts/run_phase6b_ambiguity_reduction.py
```

Make it resumable/checkpointed from the start, modeled on Phase 5N/6A.

**Verification:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase6b.py' -v
./.venv/Scripts/python.exe scripts/run_phase6b_ambiguity_reduction.py
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

**Commit:**

```bash
git add src/short_term_edge/phase6b.py scripts/run_phase6b_ambiguity_reduction.py tests/test_phase6b.py outputs/phase6b_candidate_specs.json outputs/phase6b_ambiguity_reduction_results.csv reports/phase6b_ambiguity_reduction_report.md
git commit -m "feat: add phase 6b ambiguity reduction search"
```

---

## Hour 6-8: Continue Phase 6B Batches And Analyze Results

### Task 9: Complete Phase 6B scoring in bounded batches

**Objective:** Score all selected Phase 6B candidates.

**Run repeatedly:**

```bash
PHASE6B_MAX_NEW_SPECS=6 ./.venv/Scripts/python.exe scripts/run_phase6b_ambiguity_reduction.py
```

If runtime is high:

```bash
PHASE6B_MAX_NEW_SPECS=3 ./.venv/Scripts/python.exe scripts/run_phase6b_ambiguity_reduction.py
```

**After each batch:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase6b.py' -v
```

**Commit checkpoint if outputs advanced materially:**

```bash
git add outputs/phase6b_ambiguity_reduction_results.csv outputs/phase6b_candidate_specs.json reports/phase6b_ambiguity_reduction_report.md
git commit -m "feat: advance phase 6b scoring"
```

### Task 10: Decision gate after Phase 6B

If Phase 6B produces any:

```text
phase6b_label == prefilter_survivor
```

then proceed to Phase 6C deep validation.

If all rejected, proceed to Phase 6B failure analysis and stop expanding until failure modes are understood.

---

## Hour 8-10: Phase 6C Deep Validation Of Any Survivors

Only do this if Phase 6B has survivors/watchlist candidates.

### Task 11: Write failing Phase 6C tests

**Files:**
- Create: `tests/test_phase6c.py`
- Create: `src/short_term_edge/phase6c.py`
- Create: `scripts/run_phase6c_deep_validation.py`

**Test behaviors:**

1. Select top N Phase 6B survivors deterministically.
2. Reject if no survivors unless `include_watchlist=True`.
3. Rank deep results by multi-fold slippage survival and concentration.

**Run RED:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase6c.py' -v
```

### Task 12: Implement Phase 6C deep validation

**Objective:** Run expensive walk-forward only on candidates that pass cheap prefilter gates.

**Config:**

```text
MNQ only
max_candidates: 3
walk-forward: 120/30/30 sessions
step: 360
min_folds: 2 or 3
```

**Files:**
- Create: `src/short_term_edge/phase6c.py`
- Create: `scripts/run_phase6c_deep_validation.py`
- Generated: `outputs/phase6c_deep_validation_results.csv`
- Generated: `outputs/phase6c_deep_validation_fold_results.csv`
- Generated: `reports/phase6c_deep_validation_report.md`

**Run:**

```bash
./.venv/Scripts/python.exe scripts/run_phase6c_deep_validation.py
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

**Commit:**

```bash
git add src/short_term_edge/phase6c.py scripts/run_phase6c_deep_validation.py tests/test_phase6c.py outputs/phase6c_deep_validation_results.csv outputs/phase6c_deep_validation_fold_results.csv reports/phase6c_deep_validation_report.md
git commit -m "feat: add phase 6c deep validation"
```

---

## Hour 10-11: If No Survivors, Write Strategic Failure Report

Do this if Phase 6B/6C produces no viable candidates.

### Task 13: Create failure-mode synthesis report

**Objective:** Turn the negative research into a useful decision point.

**Files:**
- Create: `reports/phase6_failure_synthesis_report.md`

Include:

```text
- completed phases and candidate counts
- best candidate from each phase
- which gates killed candidates most often
- whether failures are cost, concentration, drawdown, or split-instability dominated
- recommendation for next research axis
```

Potential next axes:

```text
- lower-frequency session-selection strategies
- different instrument (MGC) only after MNQ lesson captured
- event/time-of-day segmentation
- volatility-adaptive exits
- explicit no-trade filters around high-ambiguity periods
```

**Verification:** report is deterministic, references actual output CSVs, and does not claim candidates are tradable.

**Commit:**

```bash
git add reports/phase6_failure_synthesis_report.md
git commit -m "docs: add phase 6 failure synthesis"
```

---

## Hour 11-12: Final Verification And Handoff

### Task 14: Run canonical verification

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Expected: all tests pass.

### Task 15: Check repo cleanliness

```bash
git status --short --branch
git log --oneline -12
```

Expected: clean or only intentional uncommitted report/work-in-progress files with clear explanation.

### Task 16: Produce final handoff summary

Final message/report should include:

```text
- commits created
- phases completed
- candidate counts scored
- survivor/watchlist/rejected counts
- best candidate and why it did/did not pass
- exact verification commands and results
- next recommended phase
```

Optionally send Telegram final update if requested:

```bash
hermes send --to telegram "12-hour strategy run complete: <summary>"
```

---

# Autonomous Run Prompt Template

Use this if launching a background 12-hour Hermes process:

```text
You are continuing autonomous 12-hour work in `C:\Users\ulzii\Documents\Short Term Strategy Discovery`.
Follow `.hermes.md` and the plan at `.hermes/plans/2026-07-06_045828-12-hour-strategy-discovery-run.md`.
Work directly in the repo. Use TDD. Commit each verified milestone. Do not push.
Research/simulation only: no live trading, broker adapters, webhooks, API-key storage, order routing, or automated execution.
First complete Phase 6A scoring. Then add Phase 6A failure analysis. Then implement Phase 6B ambiguity/concentration reduction. If Phase 6B finds survivors, add Phase 6C deep validation. If no survivors, write a failure synthesis report.
Run targeted tests, relevant scripts, and canonical tests before every commit.
Keep final response concise with commits, verification, key results, and next recommendation.
```

# Success Criteria

A successful 12-hour run should end with at least one of:

1. Phase 6A fully scored and failure modes summarized.
2. Phase 6B implemented and partially or fully scored.
3. Phase 6C deep validation completed for real survivors.
4. If no candidates survive, a clear failure synthesis report explaining why and what to try next.

Do not paper-trade any candidate unless it passes cheap prefilter, concentration gates, and multi-fold walk-forward validation.
