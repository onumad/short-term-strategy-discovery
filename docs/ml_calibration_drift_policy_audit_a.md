# ML Calibration, Drift, and Policy-Impact Audit A

## Decision

The frozen Baseline B large-loss overlay is parked. It is not eligible for
signal-input review, and it remains unapproved for paper, shadow, or live
execution.

The audit did not tune around failed holdout results. Existing Baseline B
holdouts were already consumed during model/window selection and remain
exploratory evidence.

## Frozen question

The audit evaluated exactly one historical candidate:

- release: `ml-baseline-b:ml-baseline-b-r2-frozen`;
- target: `target_default_scheduler_active_day_large_loss_d`;
- model: frozen NumPy logistic regression;
- feature availability: through 11:30 ET;
- action: veto an already accepted candidate at a fixed risk threshold;
- scope: accepted candidates entering at or after 11:30 ET only.

The overlay cannot create entries, reschedule a rejected candidate, alter size,
change stops or targets, override risk, or mutate scheduler policy.

## Causal calibration design

Five expanding chronological folds generated out-of-fold scores from the latter
half of the primary training partition. Each fold refit preprocessing and the
baseline model using only earlier rows. A Platt mapping was fit on those OOF
scores. No validation or holdout labels entered calibration fitting.

The threshold grid was declared in source before the run. Threshold `0.40` was
selected using validation PnL with an 80% active-day retention floor. Holdout
data was evaluated only after the threshold was frozen.

## Replay integrity

The phase reconstructed the scheduler directly from the local MNQ bars,
registered non-rare module universe, and existing deterministic simulators.

- scheduler sessions matched: 869/869;
- accepted trades: 2,859;
- daily trade counts matched Target D exactly;
- daily net PnL matched Target D exactly;
- source revision: `544acedd9700a5fed368a46cadf59882f16c17a1`;
- manifest dirty-worktree state: `false`.

This parity is a hard prerequisite. The phase raises an error instead of
running a policy overlay when any daily count or PnL differs.

## Evidence

Calibration remained imperfect despite beating the prevalence Brier baseline:

- holdout Brier: 0.178047 versus prevalence 0.204082;
- holdout ECE: 0.102775, above the 0.10 framework limit;
- worst chronological holdout-fold ECE: 0.162692, above 0.15;
- calibration slope: 1.027133, within range;
- calibration intercept: -0.251002, outside the ±0.10 limit.

Drift was material:

- maximum feature/score PSI: 4.253930;
- largest shift: `first_30m_range` in holdout;
- validation OOD rows: 14/170;
- holdout OOD rows: 27/168;
- prediction coverage: 100%;
- invalid or stale input abstention: 100%.

The validation-selected overlay improved aggregate and validation results but
failed the locked holdout non-degradation rule:

| Metric | No model | Veto overlay |
| --- | ---: | ---: |
| Net PnL | -$16,222.02 | -$14,638.09 |
| Stress PnL | -$19,081.01 | -$17,165.08 |
| Validation PnL | -$6,853.01 | -$6,339.97 |
| Holdout PnL | $2,818.83 | $2,148.82 |
| Max drawdown | -$22,755.26 | -$21,311.56 |
| Active days | 851 | 849 |
| Accepted trades | 2,859 | 2,527 |

The Framework G counterfactual decision failed `holdout_pnl_worsened`. The full
model review also failed calibration intercept, ECE, worst-fold ECE, PSI, and
counterfactual policy-impact checks.

## Reproduction

```powershell
$env:EXPERIMENT_RUN_ID='ml-calibration-drift-policy-audit-a-r1'
./.venv/Scripts/python.exe scripts/run_ml_calibration_drift_policy_audit_a.py
```

Key generated artifacts:

- `reports/ml_calibration_drift_policy_audit_a_report.md`;
- `outputs/ml_calibration_a_calibrator.json`;
- `outputs/ml_calibration_a_calibration.csv`;
- `outputs/ml_calibration_a_drift.csv`;
- `outputs/ml_calibration_a_scheduler_parity.csv`;
- `outputs/ml_calibration_a_threshold_search.csv`;
- `outputs/ml_calibration_a_policy_comparison.csv`;
- `outputs/ml_calibration_a_recommendation.json`;
- `artifacts/ml_calibration_drift_policy_audit_a/ml-calibration-drift-policy-audit-a-r1/manifest.json`.

Generated research artifacts remain ignored and reproducible from committed
source plus local licensed data.

## Stop rule and next eligibility condition

Do not alter the calibrator, feature set, threshold, or veto rule in response to
these validation/holdout results. That would reuse consumed evidence.

Reconsideration requires either:

1. genuinely future unseen sessions evaluated under a precommitted frozen
   release, or
2. a structurally new, causally justified model hypothesis that restarts model
   selection with an explicitly separated confirmation plan.

No result in this audit changes official gates or authorizes a later execution
stage.
