from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.framework_g_research_release import (  # noqa: E402
    PREDICTION_SCHEMA_VERSION,
    authorization_policy,
    calibration_fit_policy,
    evaluate_model_review_eligibility,
    ml_evaluation_policy,
    prediction_schema,
    validate_calibration_plan,
    validate_prediction_envelope,
)


class FrameworkGResearchReleaseTests(unittest.TestCase):
    def test_authorization_is_research_only_and_models_cannot_self_approve(self) -> None:
        policy = authorization_policy()
        self.assertEqual(policy["authorization_stage"], "research")
        self.assertFalse(policy["approved_as_signal_input_default"])
        self.assertFalse(policy["paper_trading_approved"])
        self.assertFalse(policy["live_trading_approved"])
        self.assertFalse(policy["model_may_authorize_orders"])

    def test_prediction_schema_rejects_unknown_fields(self) -> None:
        schema = prediction_schema()
        self.assertFalse(schema["additionalProperties"])
        payload = _prediction()
        payload["quantity"] = 1
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_prediction_envelope(payload)

    def test_prediction_envelope_is_versioned_and_non_authoritative(self) -> None:
        payload = validate_prediction_envelope(_prediction())
        self.assertEqual(payload["schema_version"], PREDICTION_SCHEMA_VERSION)
        self.assertFalse(payload["approved_as_signal_input"])
        self.assertEqual(payload["authorization_stage"], "research")

    def test_prediction_abstains_fail_closed(self) -> None:
        payload = _prediction()
        payload.update({"prediction_status": "abstained", "score": None, "uncertainty": None, "abstention_reason": "stale_features"})
        self.assertEqual(validate_prediction_envelope(payload)["prediction_status"], "abstained")
        payload["abstention_reason"] = ""
        with self.assertRaisesRegex(ValueError, "requires null"):
            validate_prediction_envelope(payload)

    def test_prediction_rejects_future_feature_availability(self) -> None:
        payload = _prediction()
        payload["feature_available_at"] = "2026-07-09T14:01:00+00:00"
        with self.assertRaisesRegex(ValueError, "availability"):
            validate_prediction_envelope(payload)

    def test_passing_metrics_only_create_review_eligibility(self) -> None:
        result = evaluate_model_review_eligibility(_passing_metrics())
        self.assertTrue(result["eligible_for_signal_input_review"])
        self.assertFalse(result["approved_as_signal_input"])
        self.assertFalse(result["automatic_approval"])
        failed = _passing_metrics()
        failed["expected_calibration_error"] = 0.11
        result = evaluate_model_review_eligibility(failed)
        self.assertFalse(result["eligible_for_signal_input_review"])
        self.assertIn("expected_calibration_error", result["failed_checks"])

    def test_evaluation_requires_calibration_drift_abstention_and_policy_impact(self) -> None:
        policy = ml_evaluation_policy()
        self.assertTrue(policy["calibration"]["brier_score_must_beat_prevalence_baseline"])
        self.assertTrue(policy["drift_and_coverage"]["ood_evaluation_required"])
        self.assertEqual(policy["drift_and_coverage"]["missing_feature_behavior"], "abstain")
        self.assertTrue(policy["counterfactual_policy_impact"]["required_before_signal_input_review"])
        self.assertFalse(policy["approval_behavior"]["automatic_signal_input_approval"])

    def test_calibration_plan_cannot_fit_or_select_on_consumed_holdouts(self) -> None:
        policy = calibration_fit_policy()
        self.assertIn("holdout", policy["prohibited_fit_partitions"])
        plan = {
            "model_release_id": "ml-baseline-b:r2",
            "calibration_method": "platt_logistic",
            "fit_partitions": ["cross_fitted_oof"],
            "threshold_selection_partitions": ["validation"],
            "existing_holdout_status": "consumed_exploratory_selection_evidence",
            "future_confirmation_status": "not_available",
        }
        validated = validate_calibration_plan(plan)
        self.assertTrue(validated["exploratory_calibration_authorized"])
        self.assertFalse(validated["confirmatory_evidence"])
        self.assertFalse(validated["approved_as_signal_input"])
        plan["fit_partitions"] = ["holdout"]
        with self.assertRaisesRegex(ValueError, "prohibited fit"):
            validate_calibration_plan(plan)


def _prediction() -> dict[str, object]:
    return {
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "event_id": "event-1",
        "correlation_id": "corr-1",
        "created_at": "2026-07-09T13:59:00+00:00",
        "effective_at": "2026-07-09T14:00:00+00:00",
        "expires_at": "2026-07-09T14:05:00+00:00",
        "environment": "research",
        "release_id": "baseline-b:r1",
        "source_versions": {"features": "v1"},
        "authorization_stage": "research",
        "model_version": "baseline-b-v1",
        "calibration_version": None,
        "feature_contract_version": "ml-dataset-b/v1",
        "label_contract_version": "ml-target-d/v1",
        "feature_available_at": "2026-07-09T13:59:00+00:00",
        "score": 0.7,
        "uncertainty": 0.2,
        "prediction_status": "predicted",
        "abstention_reason": None,
        "approved_as_signal_input": False,
    }


def _passing_metrics() -> dict[str, object]:
    return {
        "causal_features": True,
        "coverage_aligned_targets": True,
        "chronological_splits": True,
        "leakage_checks_pass": True,
        "training_only_preprocessing": True,
        "primary_holdout_beats_baseline": True,
        "rolling_holdouts_beating_baseline": 3,
        "brier_beats_prevalence_baseline": True,
        "expected_calibration_error": 0.05,
        "worst_fold_expected_calibration_error": 0.10,
        "calibration_slope": 1.0,
        "calibration_intercept": 0.0,
        "calibration_mapping_fit_without_holdout": True,
        "maximum_feature_or_score_psi": 0.1,
        "prediction_coverage": 0.99,
        "invalid_input_abstention_rate": 1.0,
        "ood_evaluation_completed": True,
        "counterfactual_policy_impact_passed": True,
    }


if __name__ == "__main__":
    unittest.main()
