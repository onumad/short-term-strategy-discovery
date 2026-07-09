from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_baseline_a_regime_classifier import fit_logistic_regression_numpy, fit_preprocessor, transform_features  # noqa: E402
from short_term_edge.ml_baseline_a_regime_classifier import MlBaselineAConfig  # noqa: E402
from short_term_edge.ml_calibration_drift_policy_audit_a import (  # noqa: E402
    PlattCalibrator,
    apply_veto_overlay,
    apply_platt_calibrator,
    calibration_metrics,
    expanding_oof_scores,
    fit_platt_calibrator,
    population_stability_index,
    scheduler_replay_parity,
    score_with_abstention,
)


class MlCalibrationDriftPolicyAuditATests(unittest.TestCase):
    def test_expanding_oof_scores_are_strictly_chronological_and_deterministic(self) -> None:
        frame = _training_frame(140)
        first = expanding_oof_scores(frame, ("x",), "target", folds=4, iterations=40)
        second = expanding_oof_scores(frame, ("x",), "target", folds=4, iterations=40)

        pd.testing.assert_frame_equal(first, second)
        self.assertTrue((first["fit_end_session"] < first["trading_session"]).all())
        self.assertEqual(len(first), 70)
        self.assertEqual(first["oof_fold"].nunique(), 4)

    def test_platt_calibrator_serialization_primitives_are_bounded(self) -> None:
        oof = pd.DataFrame({"raw_score": [0.05, 0.15, 0.3, 0.7, 0.8, 0.95], "y_true": [0, 0, 0, 1, 1, 1]})
        calibrator = fit_platt_calibrator(oof)
        calibrated = apply_platt_calibrator(oof["raw_score"], calibrator)

        self.assertTrue(np.isfinite(calibrated).all())
        self.assertTrue(((calibrated >= 0.0) & (calibrated <= 1.0)).all())
        self.assertGreater(calibrated[-1], calibrated[0])
        self.assertEqual(calibrator.fit_partition, "cross_fitted_oof")

    def test_calibration_metrics_compare_with_prevalence_and_report_ece(self) -> None:
        metrics = calibration_metrics([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], bins=4)

        self.assertTrue(metrics["brier_beats_prevalence_baseline"])
        self.assertLess(metrics["expected_calibration_error"], 0.25)
        self.assertEqual(metrics["positive_rows"], 2)

    def test_population_stability_index_detects_shift(self) -> None:
        stable = population_stability_index(np.arange(100), np.arange(100))
        shifted = population_stability_index(np.arange(100), np.arange(100) + 1000)

        self.assertAlmostEqual(stable, 0.0)
        self.assertGreater(shifted, 0.2)

    def test_scoring_abstains_on_missing_null_and_invalid_time(self) -> None:
        frame = _training_frame(120)
        preprocessor = fit_preprocessor(frame.iloc[:100], ("x",))
        config = MlBaselineAConfig(Path("x"), Path("x"), Path("x"), Path("x"), Path("x"), Path("x"), iterations=20)
        model = fit_logistic_regression_numpy(
            transform_features(frame.iloc[:100], preprocessor), frame.iloc[:100]["target"].to_numpy(dtype=float), preprocessor, config
        )
        calibrator = PlattCalibrator(1.0, 0.0, 50, 25)
        now = pd.Timestamp("2026-07-09T15:30:00Z")

        self.assertEqual(score_with_abstention(pd.DataFrame({"other": [1]}), model, calibrator, feature_available_at=now, effective_at=now)["prediction_status"], "abstained")
        self.assertEqual(score_with_abstention(pd.DataFrame({"x": [np.nan]}), model, calibrator, feature_available_at=now, effective_at=now)["abstention_reason"], "null_required_feature")
        self.assertEqual(score_with_abstention(pd.DataFrame({"x": [1.0]}), model, calibrator, feature_available_at=now, effective_at=now - pd.Timedelta(minutes=1))["prediction_status"], "abstained")
        self.assertEqual(score_with_abstention(pd.DataFrame({"x": [1.0]}), model, calibrator, feature_available_at=now, effective_at=now)["prediction_status"], "predicted")

    def test_scheduler_parity_requires_exact_counts_and_pnl(self) -> None:
        dataset = pd.DataFrame(
            {
                "trading_session": ["2026-01-02", "2026-01-05"],
                "default_scheduler_accepted_trade_count_d": [1, 0],
                "default_scheduler_daily_pnl_d": [12.34, 0.0],
            }
        )
        ledger = pd.DataFrame({"trading_session": ["2026-01-02"], "net_pnl": [12.34]})

        parity = scheduler_replay_parity(dataset, ledger)
        self.assertTrue(parity["parity_pass"].all())
        ledger.loc[0, "net_pnl"] = 12.36
        self.assertFalse(scheduler_replay_parity(dataset, ledger)["parity_pass"].all())

    def test_veto_only_removes_baseline_trades_after_score_availability(self) -> None:
        ledger = pd.DataFrame(
            {
                "trading_session": ["2026-01-02"] * 3,
                "net_pnl": [-10.0, -20.0, 30.0],
                "score_available_before_entry": [False, True, True],
            }
        )
        scores = pd.DataFrame({"trading_session": ["2026-01-02"], "calibrated_score": [0.7]})

        retained, decisions = apply_veto_overlay(ledger, scores, 0.6)

        self.assertEqual(len(retained), 1)
        self.assertEqual(float(retained.iloc[0]["net_pnl"]), -10.0)
        self.assertFalse(bool(decisions.iloc[0]["vetoed"]))
        self.assertTrue(decisions.iloc[1:]["vetoed"].all())
        self.assertFalse(decisions["generates_new_entries"].any())


def _training_frame(rows: int) -> pd.DataFrame:
    x = np.linspace(-2.0, 2.0, rows)
    return pd.DataFrame(
        {
            "trading_session": pd.date_range("2023-01-01", periods=rows, freq="D").strftime("%Y-%m-%d"),
            "x": x,
            "target": (x + 0.2 * np.sin(np.arange(rows)) > 0.0).astype(int),
        }
    )


if __name__ == "__main__":
    unittest.main()
