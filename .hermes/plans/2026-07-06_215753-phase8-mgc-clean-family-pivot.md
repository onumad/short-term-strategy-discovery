# Phase 8 MGC Clean-Family Pivot Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Move beyond the failed legacy MGC combo transfer by running a bounded, deterministic MGC family search focused on lower same-bar ambiguity, lower drawdown, and cost-resilient behavior.

**Architecture:** Keep the existing inspectable research architecture: local bars → deterministic `StrategySpec` candidates → strict backtest/scoring → generated CSV/report artifacts. Phase 8 should not loosen Phase 7B/7D promotion gates; it should add new deterministic candidates and attribution that explain whether any non-legacy MGC family deserves later walk-forward validation.

**Tech Stack:** Python 3.11, pandas/numpy, existing `short_term_edge` modules, `unittest`, local CSV data under `data/raw` only.

---

## Current Context / Assumptions

- Project root: `C:\Users\ulzii\Documents\Short Term Strategy Discovery`.
- Current work is research/simulation only.
- No live trading approval, broker adapters, order routing, API-key storage, webhooks, or automated execution.
- Phase 7A/7B/7C/7D implemented MGC legacy transfer diagnostics.
- Phase 7B result: all tested MGC legacy combos rejected.
- Phase 7D result: `32` matched-window payout-path diagnostic rows, `0` successful payout-path rows.
- Phase 7C/7D conclusion: do not keep broadening the exact old MGC combo. Pivot to new deterministic MGC families or ambiguity-reducing variants.
- Existing uncommitted Phase 7C/7D files should remain intact. Do not commit unless the user explicitly asks.

## Proposed Next Phase

Implement **Phase 8A: MGC clean-family prefilter search**.

Phase 8A should test a small, bounded set of deterministic MGC candidates that are deliberately different from the failed Phase 7B combo shape and designed to reduce same-bar ambiguity:

1. `prior_day_breakout_retest` style candidates, if supported by current signal plumbing.
2. `opening_range_breakout` variants with wider stops/targets and conservative next-bar execution.
3. `vwap_reclaim_rejection` / VWAP continuation variants with stricter time windows and side filters.
4. Optional ambiguity-reducing exit modes using existing supported exits only; do not invent opaque model logic.

If an existing family is unsupported in `spec_to_phase4_candidate`, either:

- add the minimum deterministic mapping with tests, or
- skip it and document the skip in the Phase 8A report.

## Acceptance Criteria

Phase 8A is complete when:

- A deterministic Phase 8A spec selector exists.
- At least `6` and at most `12` bounded MGC specs are selected by default.
- Specs are serialized to JSON.
- A runner writes ranked CSV results and a markdown report.
- Ranking explicitly penalizes:
  - negative 4-tick slippage stress,
  - same-bar ambiguity,
  - high drawdown,
  - day/trade concentration,
  - negative validation/holdout splits,
  - too few trades / too little active-day coverage.
- Labels are conservative: `rejected`, `mgc_clean_family_watchlist`, or `mgc_clean_family_prefilter_survivor`.
- Canonical verification passes:
  - `./.venv/Scripts/python.exe -m unittest discover -s tests -v`
- If Hermes verification guard asks again, run a temp ad-hoc verifier under `C:\Users\ulzii\AppData\Local\Temp` with `hermes-verify-` prefix and label it ad-hoc.

---

## Files Likely To Change

Create:

- `src/short_term_edge/phase8a.py`
- `scripts/run_phase8a_mgc_clean_family_search.py`
- `tests/test_phase8a.py`
- `outputs/phase8a_mgc_clean_family_results.csv`
- `outputs/phase8a_candidate_specs.json`
- `reports/phase8a_mgc_clean_family_report.md`

Possibly modify only if needed:

- `src/short_term_edge/ai_search.py` — add minimal `StrategySpec` → phase4 candidate mapping for a supported deterministic family.
- `src/short_term_edge/phase4a.py` — only if a deterministic signal family already exists conceptually but lacks a small needed branch.
- `src/short_term_edge/strategy_spec.py` — avoid unless validation blocks an otherwise clean existing family.

Do not modify:

- broker/live-trading code: none should be added.
- legacy repo `C:\Users\ulzii\Documents\New project`.
- raw data under `data/raw`.

---

## Step-by-Step Plan

### Task 1: Re-check repo state and preserve Phase 7C/7D artifacts

**Objective:** Confirm the current uncommitted state before adding Phase 8A.

**Files:**
- Read only: git status and existing Phase 7C/7D outputs.

**Commands:**

```bash
git status --short --branch
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

**Expected:**

- Working tree shows the existing Phase 7C/7D files plus later Phase 8A files once added.
- Tests pass before Phase 8A changes begin.

**Notes:**

- Do not commit unless explicitly asked.
- If tests fail before Phase 8A changes, stop and fix/stabilize the existing work first.

---

### Task 2: Add failing Phase 8A selector tests

**Objective:** Define deterministic spec-selection behavior before implementation.

**Files:**
- Create: `tests/test_phase8a.py`
- Later create: `src/short_term_edge/phase8a.py`

**Test skeleton:**

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8a import Phase8AConfig, select_mgc_clean_family_specs


class Phase8ATests(unittest.TestCase):
    def test_select_mgc_clean_family_specs_is_mgc_only_bounded_and_deterministic(self) -> None:
        config = Phase8AConfig(max_specs=12, min_specs=6, timeframes=(1, 3))

        first = select_mgc_clean_family_specs(config)
        second = select_mgc_clean_family_specs(config)

        self.assertGreaterEqual(len(first), 6)
        self.assertLessEqual(len(first), 12)
        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertEqual({spec.instrument for spec in first}, {"MGC"})
        self.assertGreaterEqual(len({spec.family for spec in first}), 2)
        self.assertNotIn("vwap_pullback_continuation", {spec.family for spec in first})


if __name__ == "__main__":
    unittest.main()
```

**Run:**

```bash
./.venv/Scripts/python.exe tests/test_phase8a.py -v
```

**Expected:** FAIL because `short_term_edge.phase8a` does not exist yet.

---

### Task 3: Implement `Phase8AConfig` and deterministic spec selector

**Objective:** Create a bounded, deterministic MGC-only spec selector.

**Files:**
- Create: `src/short_term_edge/phase8a.py`

**Implementation outline:**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


@dataclass(frozen=True)
class Phase8AConfig:
    symbol: str = "MGC"
    max_specs: int = 12
    min_specs: int = 6
    batch_size: int = 1
    max_new_specs_per_run: int | None = None
    timeframes: tuple[int, ...] = (1, 3)

    def validate(self) -> "Phase8AConfig":
        if self.symbol != "MGC":
            raise ValueError("Phase 8A is intentionally MGC-only")
        if self.min_specs < 1:
            raise ValueError("min_specs must be positive")
        if self.max_specs < self.min_specs:
            raise ValueError("max_specs must be greater than or equal to min_specs")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.max_new_specs_per_run is not None and self.max_new_specs_per_run < 0:
            raise ValueError("max_new_specs_per_run must be non-negative when provided")
        if any(int(tf) <= 0 for tf in self.timeframes):
            raise ValueError("timeframes must be positive")
        return self
```

**Selector rules:**

- Use only families already supported by `spec_to_phase4_candidate` where possible.
- Start with MGC-only candidates such as:
  - `opening_range_breakout`
  - `vwap_reclaim_rejection`
  - `prior_session_levels` if supported
- Exclude `vwap_pullback_continuation` and `opening_drive_continuation` from Phase 8A defaults because those were the Phase 7 legacy-transfer legs.
- Sort by family, timeframe, JSON params, and canonical ID.
- Round-robin by family to avoid one family dominating the default batch.

**Run:**

```bash
./.venv/Scripts/python.exe tests/test_phase8a.py -v
```

**Expected:** selector test passes.

---

### Task 4: Add ranking tests

**Objective:** Ensure Phase 8A ranking rewards cost-resilient, low-ambiguity candidates over raw fragile PnL.

**Files:**
- Modify: `tests/test_phase8a.py`
- Modify: `src/short_term_edge/phase8a.py`

**Test to add:**

```python
def test_rank_phase8a_results_prefers_clean_cost_resilient_candidate(self) -> None:
    rows = pd.DataFrame(
        [
            {
                "candidate_id": "raw_fragile",
                "net_pnl": 4000.0,
                "slippage_4_ticks_net_pnl": -100.0,
                "trades": 140,
                "active_session_pct": 0.35,
                "max_drawdown": -1800.0,
                "best_day_concentration": 0.40,
                "best_trade_concentration": 0.20,
                "validation_pnl": 900.0,
                "holdout_pnl": 800.0,
                "same_bar_stop_target_ambiguity_count": 12,
            },
            {
                "candidate_id": "clean_candidate",
                "net_pnl": 1500.0,
                "slippage_4_ticks_net_pnl": 800.0,
                "trades": 90,
                "active_session_pct": 0.22,
                "max_drawdown": -450.0,
                "best_day_concentration": 0.14,
                "best_trade_concentration": 0.09,
                "validation_pnl": 250.0,
                "holdout_pnl": 200.0,
                "same_bar_stop_target_ambiguity_count": 0,
            },
        ]
    )

    ranked = rank_phase8a_results(rows)

    self.assertEqual(ranked.iloc[0]["candidate_id"], "clean_candidate")
    self.assertEqual(ranked.iloc[0]["phase8a_label"], "mgc_clean_family_prefilter_survivor")
```

**Run:**

```bash
./.venv/Scripts/python.exe tests/test_phase8a.py -v
```

**Expected:** FAIL until `rank_phase8a_results` is implemented.

---

### Task 5: Implement Phase 8A ranking and labels

**Objective:** Add conservative labels and scoring consistent with previous phases.

**Files:**
- Modify: `src/short_term_edge/phase8a.py`

**Implementation approach:**

- Reuse `_finite_float` from `phase5n`.
- Follow the scoring style from `phase7a.py` / `phase7b.py`, but tune labels for Phase 8A:
  - reject if 4-tick stress <= 0,
  - reject if trades < 30,
  - reject if active_session_pct < 0.10,
  - reject if best_day_concentration > 0.25,
  - reject if best_trade_concentration > 0.16,
  - reject if max_drawdown < -1500,
  - reject if same-bar ambiguity > 0,
  - watchlist if validation or holdout is negative,
  - otherwise survivor.

**Labels:**

```python
"rejected"
"mgc_clean_family_watchlist"
"mgc_clean_family_prefilter_survivor"
```

**Run:**

```bash
./.venv/Scripts/python.exe tests/test_phase8a.py -v
```

**Expected:** selector and ranking tests pass.

---

### Task 6: Implement Phase 8A runner function and JSON writer

**Objective:** Wire Phase 8A specs into the existing scoring pipeline.

**Files:**
- Modify: `src/short_term_edge/phase8a.py`

**Implementation approach:**

- Reuse `_prepare_phase7a_data` for MGC data prep if practical.
- Reuse `score_prefilter_specs` from `phase5n`.
- Reuse `_limit_specs_for_run` style from `phase7a`, but keep a local Phase 8A helper if cleaner.
- Provide:
  - `run_phase8a_mgc_clean_family_search(project_root, config, checkpoint_path=None)`
  - `write_phase8a_specs(specs, path)`

**Pseudo-flow:**

```python
def run_phase8a_mgc_clean_family_search(project_root: Path, config: Phase8AConfig = Phase8AConfig(), checkpoint_path: Path | None = None) -> Phase5NResult:
    config.validate()
    specs = select_mgc_clean_family_specs(config)
    if config.max_new_specs_per_run == 0:
        existing = pd.read_csv(checkpoint_path) if checkpoint_path and checkpoint_path.exists() else pd.DataFrame()
        return Phase5NResult(search_results=rank_phase8a_results(existing), specs=specs, complete_sessions=[])
    specs_for_run = _limit_specs_for_run(specs, checkpoint_path, config.max_new_specs_per_run)
    prepared, complete_sessions = _prepare_phase7a_data(project_root, Phase7AConfig(symbol=config.symbol, max_specs=len(specs), min_specs=1, timeframes=config.timeframes))
    scored = score_prefilter_specs(specs_for_run, prepared, complete_sessions, checkpoint_path=checkpoint_path, batch_size=config.batch_size)
    return Phase5NResult(search_results=rank_phase8a_results(scored), specs=specs, complete_sessions=complete_sessions)
```

**Run:**

```bash
./.venv/Scripts/python.exe tests/test_phase8a.py -v
```

**Expected:** tests pass.

---

### Task 7: Add Phase 8A script

**Objective:** Provide a reproducible CLI-style runner for Phase 8A.

**Files:**
- Create: `scripts/run_phase8a_mgc_clean_family_search.py`

**Script behavior:**

- Create `outputs/` and `reports/`.
- Read env var `PHASE8A_MAX_NEW_SPECS`, default `3` for bounded interactive runs.
- Use `Phase8AConfig(symbol="MGC", max_specs=12, min_specs=6, max_new_specs_per_run=max_new, timeframes=(1, 3))`.
- Write:
  - `outputs/phase8a_mgc_clean_family_results.csv`
  - `outputs/phase8a_candidate_specs.json`
  - `reports/phase8a_mgc_clean_family_report.md`

**Report sections:**

- Scope and guardrails.
- Why Phase 8A pivots from Phase 7D.
- Configuration.
- Outputs.
- Top ranked results table.
- Interpretation of labels.
- Repro command.

**Run:**

```bash
PHASE8A_MAX_NEW_SPECS=2 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py
```

**Expected:** script exits 0 and reports `Rows scored: 2 / N selected specs` on first bounded run.

---

### Task 8: Run bounded Phase 8A batch and inspect results

**Objective:** Generate initial Phase 8A evidence without over-searching.

**Files:**
- Generate/modify:
  - `outputs/phase8a_mgc_clean_family_results.csv`
  - `outputs/phase8a_candidate_specs.json`
  - `reports/phase8a_mgc_clean_family_report.md`

**Commands:**

```bash
PHASE8A_MAX_NEW_SPECS=2 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py
```

Optionally continue bounded batches:

```bash
PHASE8A_MAX_NEW_SPECS=3 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py
```

**Expected:**

- Results checkpoint grows deterministically.
- Report clearly labels candidates as rejected/watchlist/survivor.
- If all candidates are rejected, report why; do not keep broadening indefinitely.

---

### Task 9: Add focused artifact tests if script reveals edge cases

**Objective:** Cover any discovered implementation details from the real Phase 8A run.

**Files:**
- Modify: `tests/test_phase8a.py`

**Potential tests:**

- checkpoint refresh with `max_new_specs_per_run=0` preserves ranked rows;
- unsupported families fail closed with a useful error;
- selected specs exclude Phase 7 legacy combo legs by default;
- report renderer includes guardrails and label descriptions.

**Run:**

```bash
./.venv/Scripts/python.exe tests/test_phase8a.py -v
```

**Expected:** PASS.

---

### Task 10: Canonical verification

**Objective:** Prove the repo is stable after Phase 8A implementation.

**Files:**
- No planned edits.

**Command:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

**Expected:** all tests pass.

If Hermes coding guard says canonical verification was not detected, run a focused temp verifier:

- create via Python `tempfile.mkstemp(prefix="hermes-verify-", suffix="-phase8a.py")`;
- place under `C:\Users\ulzii\AppData\Local\Temp` automatically;
- assert Phase 8A module imports, generated artifacts exist, result schemas/labels are correct, and at least one synthetic ranking case passes;
- delete the temp file;
- explicitly call it **ad-hoc verification**, not suite green.

---

## Risks / Tradeoffs

- **Unsupported family mappings:** Some promising legacy/new families may not be supported by current `spec_to_phase4_candidate`. Prefer skipping unsupported ideas with report notes unless a tiny deterministic mapping is clearly justified.
- **Over-search risk:** Phase 8A should stay bounded. Do not iterate endlessly on the same data/holdout.
- **Same-bar ambiguity:** If most candidates still have ambiguity, pause to design ambiguity-free exits or coarser-bar validation rather than ranking ambiguous candidates higher.
- **Full-history harshness:** Current data covers `2023-01-03` through `2026-07-02`, much broader than the legacy six-month window. Keep full-history strictness for promotion, but report matched-window diagnostics separately if useful.
- **Generated artifacts:** CSV/report outputs are research artifacts and can be regenerated. Keep them deterministic and concise.

## Open Questions

1. Should Phase 8A remain MGC-only, or should a later Phase 8B compare MNQ/MGC clean families side by side?
2. Should the next candidate family come from the old project's later `liquidity_sweep` / `prior_day_breakout_retest` finalists, or should we stay only with families already implemented in the current repo?
3. Should generated outputs be committed with code, or should only code/tests/scripts be committed? Do not commit either way unless explicitly asked.

## Recommended Immediate Action

Implement Task 1 through Task 8 as one focused Phase 8A milestone. If all Phase 8A candidates are rejected, stop and write a short synthesis report rather than expanding the search space immediately.
