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

from short_term_edge.ml_baseline_a_regime_classifier import (
    FEATURE_WINDOWS,
    MIN_CLASS_EXAMPLES,
    PRIMARY_TARGET,
    build_feature_sets,
    compute_metrics,
    fit_logistic_regression_numpy,
    fit_preprocessor,
    run_ml_baseline_a,
    select_trainable_targets,
    transform_features,
)
from short_term_edge.ml_baseline_a_regime_classifier import MlBaselineAConfig


class MlBaselineARegimeClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset_path = PROJECT_ROOT / "outputs" / "ml_dataset_a_day_regime.csv"
        cls.feature_dictionary_path = PROJECT_ROOT / "outputs" / "ml_dataset_a_feature_dictionary.json"
        cls.label_dictionary_path = PROJECT_ROOT / "outputs" / "ml_dataset_a_label_dictionary.json"
        cls.dataset = pd.read_csv(cls.dataset_path)
        cls.feature_dictionary = json.loads(cls.feature_dictionary_path.read_text(encoding="utf-8"))
        cls.label_dictionary = json.loads(cls.label_dictionary_path.read_text(encoding="utf-8"))

    def test_loads_ml_dataset_a_outputs(self) -> None:
        self.assertFalse(self.dataset.empty)
        self.assertTrue(self.feature_dictionary)
        self.assertTrue(self.label_dictionary)
        self.assertIn("chronological_split", self.dataset.columns)
        self.assertIn(PRIMARY_TARGET, self.dataset.columns)

    def test_feature_sets_do_not_include_target_columns_as_features(self) -> None:
        feature_sets = build_feature_sets(self.feature_dictionary, self.label_dictionary)
        all_features = {feature for features in feature_sets.values() for feature in features}
        target_columns = {name for name, meta in self.label_dictionary.items() if bool(meta.get("is_target"))}
        self.assertFalse(all_features & target_columns)
        self.assertTrue(all(not feature.startswith("target_") for feature in all_features))

    def test_feature_sets_exclude_post_session_diagnostic_features(self) -> None:
        feature_sets = build_feature_sets(self.feature_dictionary, self.label_dictionary)
        for features in feature_sets.values():
            for feature in features:
                self.assertNotEqual(self.feature_dictionary[feature]["availability_time"], "post_session_diagnostic")

    def test_availability_windows_use_expected_feature_times(self) -> None:
        feature_sets = build_feature_sets(self.feature_dictionary, self.label_dictionary)
        for window, features in feature_sets.items():
            allowed = set(FEATURE_WINDOWS[window])
            self.assertTrue({self.feature_dictionary[f]["availability_time"] for f in features} <= allowed)

    def test_uses_discovery_split_for_fitting_imputation_and_scaling_only(self) -> None:
        feature_sets = build_feature_sets(self.feature_dictionary, self.label_dictionary)
        features = feature_sets["pre_rth_only"]
        discovery = self.dataset[self.dataset["chronological_split"].eq("discovery")]
        preprocessor = fit_preprocessor(discovery, features)
        encoded_discovery = pd.DataFrame(transform_features(discovery, preprocessor, standardize=False), columns=preprocessor.encoded_features)
        expected_medians = encoded_discovery.median(axis=0, numeric_only=True).fillna(0.0)
        pd.testing.assert_series_equal(preprocessor.medians, expected_medians, check_names=False)

    def test_holdout_not_used_for_fitting_or_threshold_selection_artifacts(self) -> None:
        threshold_path = PROJECT_ROOT / "outputs" / "ml_baseline_a_threshold_sweep.csv"
        if not threshold_path.exists():
            self.skipTest("ML Baseline A threshold artifact not generated yet")
        threshold = pd.read_csv(threshold_path)
        selection = threshold[threshold["selected_for_holdout_diagnostic"].astype(str).str.lower().eq("true")]
        self.assertTrue(set(selection["split"].astype(str)) <= {"validation", "holdout_diagnostic_best_validation_threshold"})
        self.assertTrue((selection[selection["split"].eq("validation")]["threshold"].isin([0.30, 0.40, 0.50, 0.60, 0.70])).all())

    def test_constant_single_class_targets_are_skipped(self) -> None:
        frame = self.dataset[["trading_session", "chronological_split", PRIMARY_TARGET]].copy()
        frame["target_no_trade_or_reduce_risk_day"] = True
        frame["target_high_vol_mixed_weak_day"] = False
        frame["target_prior_level_interaction_day"] = self.dataset["target_prior_level_interaction_day"]
        frame["target_power_hour_expansion_day"] = self.dataset["target_power_hour_expansion_day"]
        plan = select_trainable_targets(frame)
        self.assertIn("target_no_trade_or_reduce_risk_day", plan["skipped_targets"])
        self.assertIn("target_high_vol_mixed_weak_day", plan["skipped_targets"])
        self.assertTrue(all(min(v.values()) >= MIN_CLASS_EXAMPLES for k, v in plan["target_balances"].items() if k in plan["trained_targets"]))

    def test_metrics_are_deterministic(self) -> None:
        y_true = pd.Series([0, 0, 1, 1]).to_numpy()
        y_pred = pd.Series([0, 1, 1, 1]).to_numpy()
        y_score = pd.Series([0.1, 0.8, 0.7, 0.9]).to_numpy()
        self.assertEqual(compute_metrics(y_true, y_pred, y_score), compute_metrics(y_true, y_pred, y_score))

    def test_logistic_regression_training_is_deterministic_with_fixed_seed(self) -> None:
        feature_sets = build_feature_sets(self.feature_dictionary, self.label_dictionary)
        features = feature_sets["pre_rth_only"]
        discovery = self.dataset[self.dataset["chronological_split"].eq("discovery")]
        preprocessor = fit_preprocessor(discovery, features)
        x_train = transform_features(discovery, preprocessor)
        y_train = discovery[PRIMARY_TARGET].astype(bool).astype(float).to_numpy()
        cfg = MlBaselineAConfig(self.dataset_path, self.feature_dictionary_path, self.label_dictionary_path, PROJECT_ROOT / "outputs", PROJECT_ROOT / "reports", PROJECT_ROOT / "artifacts" / "unit")
        first = fit_logistic_regression_numpy(x_train, y_train, preprocessor, cfg)
        second = fit_logistic_regression_numpy(x_train, y_train, preprocessor, cfg)
        self.assertEqual(first.intercept, second.intercept)
        self.assertTrue((first.coefficients == second.coefficients).all())

    def test_predictions_file_has_required_columns(self) -> None:
        path = PROJECT_ROOT / "outputs" / "ml_baseline_a_predictions.csv"
        if not path.exists():
            self.skipTest("ML Baseline A predictions artifact not generated yet")
        predictions = pd.read_csv(path, nrows=5)
        required = {"session_date", "chronological_split", "target_name", "availability_window", "model_name", "y_true", "y_pred", "y_score", "threshold", "is_holdout"}
        self.assertTrue(required <= set(predictions.columns))

    def test_model_cards_include_research_only_and_no_live_guardrails(self) -> None:
        path = PROJECT_ROOT / "outputs" / "ml_baseline_a_model_cards.json"
        if not path.exists():
            self.skipTest("ML Baseline A model cards artifact not generated yet")
        cards = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(cards["research_only"])
        self.assertFalse(cards["live_trading_approved"])
        self.assertEqual(cards["allowed_use"], "diagnostic regime classification only")

    def test_paper_trading_approved_remains_false(self) -> None:
        path = PROJECT_ROOT / "outputs" / "ml_baseline_a_model_cards.json"
        if not path.exists():
            self.skipTest("ML Baseline A model cards artifact not generated yet")
        cards = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(cards["paper_trading_approved"])

    def test_no_strategy_signals_are_generated(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_baseline_a_regime_classifier.py").read_text(encoding="utf-8").lower()
        banned = ["generate_trade_signal", "entry_signal", "exit_signal", "order_id", "api_key", "paper_trading_approved\": true", "live_trading_approved\": true"]
        for token in banned:
            self.assertNotIn(token, source)
        path = PROJECT_ROOT / "outputs" / "ml_baseline_a_next_action_recommendation.json"
        if path.exists():
            recommendation = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(recommendation["generated_strategy_signals"])

    def test_run_function_writes_artifacts_to_temp_outputs(self) -> None:
        # Smoke-test the writer on the real dataset but isolated output/report/artifact directories.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = MlBaselineAConfig(
                dataset_path=self.dataset_path,
                feature_dictionary_path=self.feature_dictionary_path,
                label_dictionary_path=self.label_dictionary_path,
                output_dir=root / "outputs",
                report_dir=root / "reports",
                artifact_dir=root / "artifacts" / "ml_baseline_a_regime_classifier" / "unit",
                iterations=20,
            )
            result = run_ml_baseline_a(cfg)
            self.assertTrue((root / "outputs" / "ml_baseline_a_predictions.csv").exists())
            self.assertTrue(result["next_action_recommendation"]["research_only"])


if __name__ == "__main__":
    unittest.main()
