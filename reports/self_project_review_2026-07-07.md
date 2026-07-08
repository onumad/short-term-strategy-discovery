# Self And Project Review Report — 2026-07-07

## Scope

Implemented the plan saved at `.hermes/plans/2026-07-07_074627-self-project-review.md`.

Reviewed:

- Recent Phase 8G implementation:
  - `src/short_term_edge/phase8g_event_execution_calibration.py`
  - `scripts/run_phase8g_event_execution_calibration.py`
  - `tests/test_phase8g_event_execution_calibration.py`
- Shared run-scoped artifact helper:
  - `src/short_term_edge/experiments/artifacts.py`
  - `tests/test_experiment_artifacts.py`
- Phase 8G generated artifacts:
  - `outputs/phase8g_event_execution_calibration.csv`
  - `reports/phase8g_event_execution_calibration_report.md`
  - `artifacts/phase8g_event_execution_calibration/phase8g-r1-smoke/manifest.json`
- Project safety/hygiene signals around live trading, broker adapters, webhooks, credentials, and promotion wording.

## Findings

### Fixed: Phase 8G manifest label counts were empty

The regenerated Phase 8G CSV/report had `calibration_label` counts, but the run-scoped manifest showed an empty `label_counts` object. Root cause: `write_experiment_manifest()` only detected phase-prefixed label columns such as `phase8a_label`; Phase 8G uses `calibration_label`.

Fix:

- Updated `src/short_term_edge/experiments/artifacts.py` so manifest label detection uses the last result column ending in `_label`, preserving DataFrame column order.
- Added regression coverage in `tests/test_experiment_artifacts.py` for a result frame with both `phase8e_label` and `calibration_label` to ensure the final diagnostic label is counted.
- Re-ran Phase 8G with `EXPERIMENT_RUN_ID=phase8g-r1-smoke` to refresh the manifest.

### Confirmed: Phase 8G artifacts are now consistent

Current artifact facts:

- CSV rows: `48`
- Manifest rows: `48`
- Required Phase 8G columns missing: `[]`
- CSV/manifest label counts:
  - `concentrated`: `8`
  - `cost_sensitive`: `2`
  - `rejected_timing_cost`: `38`
- Family counts:
  - `volatility_compression_breakout`: `16`
  - `vwap_pullback_continuation`: `16`
  - `vwap_reclaim_rejection`: `16`

### Confirmed: research-safety scope held

Safety scan hits were guardrail/report text and the existing Databento downloader reading `DATABENTO_API_KEY` from the environment. I did not find newly added broker adapters, order routing, credential storage, webhooks, or live execution behavior in the reviewed Phase 8G path.

### Project hygiene notes

- The working tree is intentionally broad/dirty with many untracked phase files and artifacts from Phase 7C through Phase 8G.
- `pygount` is not installed, so LOC/language composition was skipped rather than guessed.
- README has a large tracked diff relative to `HEAD`, but most Phase 8 content appears to predate this review and was treated as existing context except the Phase 8G section.

## Verification

Focused checks:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_experiment_artifacts.py' -v
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8g_event_execution_calibration.py' -v
```

Result: `7` focused tests passed.

Canonical suite:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Result: `116` tests passed.

Phase script rerun:

```bash
EXPERIMENT_RUN_ID=phase8g-r1-smoke ./.venv/Scripts/python.exe scripts/run_phase8g_event_execution_calibration.py
```

Result: completed successfully, regenerated `48` calibration rows, and refreshed run-scoped artifacts.

## Outcome

Review implemented. The main self-review issue was a provenance/reporting bug in manifest label counts, now fixed and covered by tests. Phase 8G remains diagnostic-only; no paper-trading or live-trading promotion was added.
