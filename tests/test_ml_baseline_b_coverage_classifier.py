from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_baseline_b_coverage_classifier import (  # noqa: E402
    PRIMARY_SPLIT,
    SPLIT_VARIANTS,
    TARGETS,
    build_feature_sets,
    build_recommendation,
    build_stability_summary,
    validate_inputs,
)


class MlBaselineBCoverageClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = pd.read_csv(PROJECT_ROOT / "outputs" / "ml_target_d_day_regime.csv")
        cls.features = json.loads((PROJECT_ROOT / "outputs" / "ml_dataset_b_feature_dictionary.json").read_text(encoding="utf-8"))
        cls.labels = json.loads((PROJECT_ROOT / "outputs" / "ml_target_d_label_dictionary.json").read_text(encoding="utf-8"))
        cls.readiness = pd.read_csv(PROJECT_ROOT / "outputs" / "ml_target_d_target_readiness_summary.csv")

    def test_only_readiness_approved_targets_and_splits_are_used(self) -> None:
        feature_sets = build_feature_sets(self.features, self.labels)
        validate_inputs(self.dataset, feature_sets, self.labels, self.readiness)
        for target in TARGETS:
            self.assertTrue(self.labels[target]["trainable_for_baseline_b"])
            for split in SPLIT_VARIANTS:
                ready = self.readiness[
                    self.readiness["target_name"].eq(target)
                    & self.readiness["split_variant"].eq(split)
                    & self.readiness["trainable_for_baseline_b"].astype(bool)
                ]
                self.assertEqual(len(ready), 1)

    def test_feature_windows_exclude_raw_price_targets_pnl_and_post_session(self) -> None:
        feature_sets = build_feature_sets(self.features, self.labels)
        for window, features in feature_sets.items():
            self.assertGreater(len(features), 0, window)
            for feature in features:
                meta = self.features[feature]
                self.assertTrue(meta["use_in_baseline_b"])
                self.assertFalse(meta["is_raw_price_level"])
                self.assertFalse(meta["is_post_session_diagnostic"])
                self.assertFalse(meta["is_target_or_outcome_derived"])
                self.assertFalse(feature.startswith("target_"))
                self.assertNotIn("pnl", feature.lower())

    def test_stability_requires_primary_and_two_rolling_holdouts(self) -> None:
        rows = []
        for variant in SPLIT_VARIANTS:
            rows.append(_metric(variant, "majority_class_baseline", 0.40, 0.50))
            rows.append(_metric(variant, "logistic_regression_numpy", 0.45, 0.55))
        stability = build_stability_summary(pd.DataFrame(rows))
        logistic = stability[stability["model_name"].eq("logistic_regression_numpy")].iloc[0]
        self.assertTrue(logistic["primary_holdout_beats_majority"])
        self.assertEqual(logistic["rolling_holdouts_beating_majority"], 3)
        self.assertTrue(logistic["stable_holdout_improvement"])
        recommendation = build_recommendation(pd.DataFrame(rows), stability)
        self.assertEqual(recommendation["next_action"], "ml_baseline_b_calibration_and_policy_impact_diagnostic")
        self.assertFalse(recommendation["generated_strategy_signals"])
        self.assertFalse(recommendation["paper_trading_approved"])

    def test_source_has_no_strategy_or_execution_mutation(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_baseline_b_coverage_classifier.py").read_text(encoding="utf-8").lower()
        for token in ("broker", "order routing", "to_csv(config.module_registry", "construct_scheduled_trades", "candidate_results_changed\": true"):
            self.assertNotIn(token, source)


def _metric(variant: str, model: str, f1: float, balanced_accuracy: float) -> dict[str, object]:
    return {
        "target_name": TARGETS[0],
        "split_variant": variant,
        "availability_window": "pre_rth_only",
        "model_name": model,
        "split": "holdout",
        "f1": f1,
        "balanced_accuracy": balanced_accuracy,
    }


if __name__ == "__main__":
    unittest.main()
