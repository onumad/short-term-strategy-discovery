# Phase 10B Causality Quarantine and ML Baseline B

## Decision

Six default Phase 10B modules used full-sample overnight-range percentiles. Because future sessions could change historical percentile ranks and eligibility, the historical definitions are quarantined. They remain auditable under their original identifiers but are excluded from default scheduling and ML label backfill.

Separately versioned causal replacements used prior completed sessions only, with a 20-session unknown warm-up. None passed the unchanged module gates, so they were not registered or added to the scheduler. The remaining 16-module safe scheduler universe was replayed successfully for ML Target D, enabling a bounded coverage-aligned Baseline B diagnostic.

## Reproducible commands

```powershell
$env:EXPERIMENT_RUN_ID='ml-backfill-e-r1'
./.venv/Scripts/python.exe scripts/run_ml_backfill_e_phase10b_causality_audit.py

$env:EXPERIMENT_RUN_ID='module-registry-f-r1'
./.venv/Scripts/python.exe scripts/run_module_registry_f_quarantine.py

$env:EXPERIMENT_RUN_ID='phase10b-causal-v2-r1'
./.venv/Scripts/python.exe scripts/run_phase10b_causal_v2_validation.py

$env:EXPERIMENT_RUN_ID='ml-target-d-r2-quarantined'
./.venv/Scripts/python.exe scripts/build_ml_target_d_playbook_label_backfill.py

$env:EXPERIMENT_RUN_ID='ml-baseline-b-r1'
./.venv/Scripts/python.exe scripts/run_ml_baseline_b_coverage_classifier.py

./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/audit_data.py --no-write
```

## Evidence

- Causality audit: 6 unsafe default modules; eligibility drift was observed for every audited module.
- Registry F: all 6 historical identifiers preserved; scheduler and ML-backfill eligibility set false; default scheduler universe reduced from 22 to 16.
- Causal V2: 6 new candidate identifiers and 358 trades; 0 full gate passes. Two candidates failed fold stability and four failed minimum activity; concentration remained above unchanged limits.
- Target D: 869 sessions; 16 of 16 default modules backfilled; 0 unavailable modules; 12 target/split pairs passed readiness rules.
- Baseline B: two approved active-day loss targets, four point-in-time availability windows, one primary chronological split, and three rolling labeled folds. No threshold search used holdout data.
- The large-loss logistic classifier through 11:30 ET beat the majority baseline on the primary holdout and all three rolling holdouts. Mean holdout balanced accuracy was 0.621 and mean holdout F1 was 0.418.
- Canonical verification: 501 tests passed. The read-only data audit completed without changing `data_audit.md`.

Generated local evidence is under:

- `artifacts/ml_backfill_e_phase10b_causality_audit/ml-backfill-e-r1`
- `artifacts/module_registry_f_quarantine/module-registry-f-r1`
- `artifacts/phase10b_causal_v2_validation/phase10b-causal-v2-r1`
- `artifacts/ml_target_d_playbook_label_backfill/ml-target-d-r2-quarantined`
- `artifacts/ml_baseline_b_coverage_classifier/ml-baseline-b-r1`

## Stop condition and next question

Baseline B is diagnostic evidence only. It does not generate strategy signals and is not authorized to change module selection, scheduler policy, position sizing, risk limits, or orders.

Before any model output can become a versioned signal input, the next bounded milestone must test probability calibration, calibration drift across chronological folds, and counterfactual policy impact under deterministic risk constraints. The model must be parked if calibration is unstable or if apparent classification improvement does not improve the playbook after costs without worsening drawdown, concentration, or weak-fold behavior.

Official gates are unchanged. `paper_trading_approved=false` and `live_trading_approved=false`.
