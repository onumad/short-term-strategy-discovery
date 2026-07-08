# Self And Project Review Implementation Plan

> **For Hermes:** Execute directly in this session; do not commit unless explicitly asked.

**Goal:** Review the recent Phase 8G implementation, my own prior work, and the current research project state; apply only minimal fixes that improve correctness, reproducibility, or hygiene.

**Architecture:** Treat this as a bounded pre-commit-style audit, not a new strategy search. Inspect the actual changed/untracked files, verify generated Phase 8G artifacts against code/report expectations, scan for research-safety violations, then fix only concrete issues found.

**Tech Stack:** Python 3.11 via `./.venv/Scripts/python.exe`, `unittest`, pandas CSV/JSON artifact checks, git diff/status.

---

## Scope

Review:

- Recent Phase 8G code:
  - `src/short_term_edge/phase8g_event_execution_calibration.py`
  - `scripts/run_phase8g_event_execution_calibration.py`
  - `tests/test_phase8g_event_execution_calibration.py`
- Generated Phase 8G artifacts:
  - `outputs/phase8g_event_execution_calibration.csv`
  - `reports/phase8g_event_execution_calibration_report.md`
  - `artifacts/phase8g_event_execution_calibration/phase8g-r1-smoke/manifest.json`
- Project-level hygiene/safety signals:
  - `README.md`
  - `AGENTS.md`
  - `requirements.txt`
  - obvious live-trading/prohibited-scope strings under `src/`, `scripts/`, and `tests/`

Do not review every old strategy family line-by-line unless a targeted check points to a specific defect.

## Task 1: Establish Review Baseline

**Objective:** Capture the exact workspace state and changed/untracked files before making any fixes.

**Commands:**

```bash
git status --short --branch
git diff --stat
git ls-files --others --exclude-standard | sed -n '1,160p'
```

**Expected:** Dirty tree with many untracked phase artifacts/files; no commits or pushes.

## Task 2: Inspect Phase 8G Code For Logic Issues

**Objective:** Check that Phase 8G obeys the intended event-to-execution calibration semantics.

**Files:**

- Read: `src/short_term_edge/phase8g_event_execution_calibration.py`
- Read: `scripts/run_phase8g_event_execution_calibration.py`
- Read: `tests/test_phase8g_event_execution_calibration.py`

**Checklist:**

- Candidate selection only uses `phase8e_label == "backtest_candidate"` and caps/diversifies by instrument/family.
- Entry delay handling does not use future labels as signal inputs.
- Stop/target ambiguity is reported, not hidden.
- Costs use existing `InstrumentSpec.base_cost` and `InstrumentSpec.stress_cost`.
- Split metrics are chronological enough for diagnostics and are not promoted as validation approval.
- Labels remain diagnostic and never say paper-trading/live promotion.

## Task 3: Inspect Phase 8G Artifacts For Consistency

**Objective:** Verify code, CSV, report, and manifest agree.

**Files:**

- Read/parse: `outputs/phase8g_event_execution_calibration.csv`
- Read: `reports/phase8g_event_execution_calibration_report.md`
- Read/parse: `artifacts/phase8g_event_execution_calibration/phase8g-r1-smoke/manifest.json`

**Checks:**

- CSV row count equals report and manifest row count.
- CSV has required columns from the event-to-execution calibration spec.
- Label counts agree across CSV/report/manifest.
- Report includes guardrails and decision rules.
- Manifest records command, data files, git state, and guardrails.

## Task 4: Project Safety/Hygiene Scan

**Objective:** Detect scope drift and avoid adding live-trading or credential behavior.

**Commands:**

```bash
grep -RInE "broker|order routing|webhook|api[_-]?key|secret|password|token|live trading|paper_trade_candidate" src scripts tests README.md AGENTS.md
```

**Expected:** Guardrail text only; no broker adapters, credential storage, webhooks, or live execution code.

## Task 5: Apply Minimal Fixes If Defects Are Found

**Objective:** Fix only concrete issues found in Tasks 2-4.

**Rules:**

- Prefer small patches over refactors.
- Preserve existing project style.
- Do not rewrite old phases unless directly implicated.
- Do not commit.

## Task 6: Verification

**Objective:** Produce real verification evidence after any fixes.

**Commands:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8g_event_execution_calibration.py' -v
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

If the guard requires it, also create a temporary `hermes-verify-*.py` script under the OS temp directory to assert changed Phase 8G behavior and artifact consistency, then clean it up.

## Task 7: Report Review Outcome

**Objective:** Summarize findings and verification without overstating promotion status.

Include:

- Plan path.
- Defects found and fixes applied, if any.
- Phase 8G artifact facts: rows, label counts, top diagnosis.
- Verification commands and actual pass/fail output.
- Remaining non-blocking project risks or next recommended step.
