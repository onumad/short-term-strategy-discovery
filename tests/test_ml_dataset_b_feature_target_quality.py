from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_dataset_b_feature_target_quality import (  # noqa: E402
    REVISED_TARGETS,
    add_revised_targets,
    build_dataset_b,
    build_feature_dictionary_b,
    build_label_dictionary_b,
    build_leakage_audit,
    build_model_readiness_summary,
    build_next_action_recommendation,
    build_target_balance_by_split,
    run_ml_dataset_b_feature_target_quality,
    MlDatasetBConfig,
)


class MlDatasetBFeatureTargetQualityTests(unittest.TestCase):
    def test_loads_dataset_a_outputs(self) -> None:
        dataset = pd.read_csv(PROJECT_ROOT / "outputs" / "ml_dataset_a_day_regime.csv")
        features = json.loads((PROJECT_ROOT / "outputs" / "ml_dataset_a_feature_dictionary.json").read_text(encoding="utf-8"))
        labels = json.loads((PROJECT_ROOT / "outputs" / "ml_dataset_a_label_dictionary.json").read_text(encoding="utf-8"))
        self.assertFalse(dataset.empty)
        self.assertIn("target_bad_playbook_day", dataset.columns)
        self.assertIn("prior_rth_high", features)
        self.assertIn("target_bad_playbook_day", labels)

    def test_loads_ml_baseline_a_outputs(self) -> None:
        for name in [
            "ml_baseline_a_model_metrics.csv",
            "ml_baseline_a_predictions.csv",
            "ml_baseline_a_feature_importance.csv",
            "ml_baseline_a_confusion_matrices.csv",
            "ml_baseline_a_threshold_sweep.csv",
        ]:
            self.assertFalse(pd.read_csv(PROJECT_ROOT / "outputs" / name).empty, name)

    def test_target_balance_by_split_is_deterministic(self) -> None:
        frame = _sample_dataset()
        first = build_target_balance_by_split(frame, ["target_bad_playbook_day"])
        second = build_target_balance_by_split(frame, ["target_bad_playbook_day"])
        pd.testing.assert_frame_equal(first, second)

    def test_revised_target_thresholds_are_discovery_only(self) -> None:
        frame = _sample_dataset()
        out, info = add_revised_targets(frame)
        self.assertEqual(info["thresholds_fit_split"], "discovery")
        self.assertEqual(info["pnl_source_column"], "scheduler_daily_pnl")
        self.assertAlmostEqual(float(info["bad_day_threshold"]), -2.8)
        self.assertAlmostEqual(float(info["good_day_threshold"]), 4.6)
        self.assertFalse(out.loc[out["trading_session"].eq("2026-01-07"), "target_bad_playbook_day_v2"].iloc[0])

    def test_revised_target_columns_are_deterministic(self) -> None:
        frame = _sample_dataset()
        first, info1 = build_dataset_b(frame)
        second, info2 = build_dataset_b(frame)
        self.assertEqual(info1, info2)
        pd.testing.assert_series_equal(first["target_reduce_risk_day_v2"], second["target_reduce_risk_day_v2"])
        for target in REVISED_TARGETS:
            self.assertIn(target, first.columns)

    def test_feature_dictionary_marks_availability_for_every_feature_and_excludes_targets(self) -> None:
        frame = _sample_dataset()
        dataset_b, _ = build_dataset_b(frame)
        features = build_feature_dictionary_b(_sample_feature_dictionary(), dataset_b)
        self.assertTrue(all(meta.get("availability_time") for meta in features.values()))
        for target in ["target_bad_playbook_day", *REVISED_TARGETS]:
            self.assertNotIn(target, features)

    def test_post_session_diagnostic_features_are_not_trainable(self) -> None:
        frame = _sample_dataset()
        dataset_b, _ = build_dataset_b(frame)
        features = build_feature_dictionary_b(_sample_feature_dictionary(), dataset_b)
        self.assertFalse(features["power_hour_range"]["use_in_baseline_b"])
        self.assertEqual(features["power_hour_range"]["availability_time"], "post_session_diagnostic")

    def test_raw_price_level_features_flagged_or_disabled_for_baseline_b(self) -> None:
        frame = _sample_dataset()
        dataset_b, _ = build_dataset_b(frame)
        features = build_feature_dictionary_b(_sample_feature_dictionary(), dataset_b)
        self.assertTrue(features["prior_rth_high"]["is_raw_price_level"])
        self.assertFalse(features["prior_rth_high"]["use_in_baseline_b"])
        self.assertIn("raw_price_level", features["prior_rth_high"]["risky_feature_reason"])

    def test_leakage_audit_reports_no_target_as_feature_leakage(self) -> None:
        frame = _sample_dataset()
        dataset_b, info = build_dataset_b(frame)
        features = build_feature_dictionary_b(_sample_feature_dictionary(), dataset_b)
        labels = build_label_dictionary_b(_sample_label_dictionary(), dataset_b)
        audit = build_leakage_audit(dataset_b, features, labels, info)
        row = audit[audit["check"].eq("no_target_column_in_feature_dictionary")].iloc[0]
        self.assertEqual(row["status"], "pass")

    def test_recommendation_logic_is_deterministic(self) -> None:
        frame = _sample_dataset()
        dataset_b, info = build_dataset_b(frame)
        target_balance = build_target_balance_by_split(dataset_b, ["target_bad_playbook_day", *REVISED_TARGETS])
        features = build_feature_dictionary_b(_sample_feature_dictionary(), dataset_b)
        labels = build_label_dictionary_b(_sample_label_dictionary(), dataset_b)
        leakage = build_leakage_audit(dataset_b, features, labels, info)
        readiness = build_model_readiness_summary(dataset_b, target_balance, pd.DataFrame(), leakage)
        feature_quality = pd.DataFrame([{"severe_missingness_flag": False}])
        feature_stability = pd.DataFrame()
        first = build_next_action_recommendation(dataset_b, readiness, leakage, feature_quality, feature_stability, info)
        second = build_next_action_recommendation(dataset_b, readiness, leakage, feature_quality, feature_stability, info)
        self.assertEqual(first, second)
        self.assertFalse(first["paper_trading_approved"])

    def test_no_model_training_or_strategy_signals_source_guard(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_dataset_b_feature_target_quality.py").read_text(encoding="utf-8").lower()
        banned = ["sklearn", ".fit(", "train_test_split"]
        for token in banned:
            self.assertNotIn(token, source)
        self.assertNotIn("generated_strategy_signals\": true", source)

    def test_paper_trading_approved_remains_false_in_policies(self) -> None:
        for name in ["playbook_validation_policy.json", "playbook_scheduler_policy.json"]:
            policy = json.loads((PROJECT_ROOT / "outputs" / name).read_text(encoding="utf-8"))
            self.assertFalse(bool(policy.get("paper_trading_approved", False)))

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "outputs"
            reports = root / "reports"
            artifacts = root / "artifacts" / "ml_dataset_b_feature_target_quality" / "unit"
            outputs.mkdir(parents=True)
            _write_minimal_inputs(outputs)
            config = MlDatasetBConfig(
                dataset_a_path=outputs / "ml_dataset_a_day_regime.csv",
                feature_dictionary_a_path=outputs / "ml_dataset_a_feature_dictionary.json",
                label_dictionary_a_path=outputs / "ml_dataset_a_label_dictionary.json",
                baseline_metrics_path=outputs / "ml_baseline_a_model_metrics.csv",
                baseline_predictions_path=outputs / "ml_baseline_a_predictions.csv",
                baseline_feature_importance_path=outputs / "ml_baseline_a_feature_importance.csv",
                baseline_confusion_path=outputs / "ml_baseline_a_confusion_matrices.csv",
                baseline_threshold_sweep_path=outputs / "ml_baseline_a_threshold_sweep.csv",
                validation_policy_path=outputs / "playbook_validation_policy.json",
                scheduler_policy_path=outputs / "playbook_scheduler_policy.json",
                research_signal_registry_path=outputs / "research_signal_registry.csv",
                playbook_module_registry_path=outputs / "playbook_module_registry.csv",
                output_dir=outputs,
                report_dir=reports,
                artifact_dir=artifacts,
                run_id="unit",
            )
            run_ml_dataset_b_feature_target_quality(config)
            report = (reports / "ml_dataset_b_feature_target_quality_report.md").read_text(encoding="utf-8")
            self.assertIn("Research/simulation only", report)
            self.assertIn("No model training", report)
            self.assertIn("No live trading", report)


def _sample_dataset() -> pd.DataFrame:
    rows = []
    splits = ["discovery"] * 4 + ["validation"] * 3 + ["holdout"] * 3
    pnls = [-10.0, -2.0, 4.0, 10.0, -5.0, 0.0, 20.0, -1.0, 8.0, 12.0]
    for i, (split, pnl) in enumerate(zip(splits, pnls, strict=True)):
        rows.append({
            "trading_session": f"2026-01-{i+1:02d}",
            "chronological_split": split,
            "recent_oos_like": i >= 7,
            "prior_rth_high": 100.0 + i,
            "prior_rth_range": 10.0,
            "gap_from_prior_rth_close": float(i - 3),
            "first_30m_range": 2.0 + i,
            "morning_0930_1130_range": 4.0 + i,
            "lunch_1130_1330_range": 1.0 + i,
            "prior_day_close_position": 0.1 + 0.08 * i,
            "first_30m_close_position": 0.2 + 0.05 * i,
            "morning_close_position": 0.3 + 0.04 * i,
            "lunch_range_percentile": min(0.9, 0.1 * i),
            "morning_range_percentile": min(0.9, 0.1 * i),
            "morning_direction_flip_flag": i % 2 == 0,
            "broad_high_vol_mixed_flag": i % 3 == 0,
            "power_hour_range": 5.0,
            "scheduler_daily_pnl": pnl,
            "scheduler_large_loss_day": pnl <= -10.0,
            "playbook_large_loss_day": False,
            "target_bad_playbook_day": i % 2 == 0,
            "target_good_playbook_day": i % 2 == 1,
            "target_no_trade_or_reduce_risk_day": i % 4 == 0,
            "target_best_phase_group": "phase10b",
            "target_worst_phase_group": "phase11a",
            "target_high_vol_mixed_weak_day": False,
            "target_prior_level_interaction_day": i % 3 == 0,
            "target_power_hour_expansion_day": i % 2 == 0,
        })
    return pd.DataFrame(rows)


def _sample_feature_dictionary() -> dict[str, dict[str, object]]:
    return {
        "prior_rth_high": {"role": "feature", "feature_group": "pre_rth", "availability_time": "pre_rth"},
        "prior_rth_range": {"role": "feature", "feature_group": "pre_rth", "availability_time": "pre_rth"},
        "power_hour_range": {"role": "feature", "feature_group": "late_session_diagnostic", "availability_time": "post_session_diagnostic"},
    }


def _sample_label_dictionary() -> dict[str, dict[str, object]]:
    return {
        "target_bad_playbook_day": {"role": "target", "is_target": True, "is_feature": False},
        "chronological_split": {"role": "split_metadata", "is_target": False, "is_feature": False},
    }


def _write_minimal_inputs(outputs: Path) -> None:
    frame = _sample_dataset()
    frame.to_csv(outputs / "ml_dataset_a_day_regime.csv", index=False)
    (outputs / "ml_dataset_a_feature_dictionary.json").write_text(json.dumps(_sample_feature_dictionary()), encoding="utf-8")
    (outputs / "ml_dataset_a_label_dictionary.json").write_text(json.dumps(_sample_label_dictionary()), encoding="utf-8")
    metrics = pd.DataFrame([{
        "target_name": "target_bad_playbook_day",
        "availability_window": "pre_rth_only",
        "model_name": "univariate_threshold_stump",
        "split": "validation",
        "balanced_accuracy": 0.8,
        "f1": 0.7,
        "accuracy": 0.7,
    }, {
        "target_name": "target_bad_playbook_day",
        "availability_window": "pre_rth_only",
        "model_name": "univariate_threshold_stump",
        "split": "holdout",
        "balanced_accuracy": 0.5,
        "f1": 0.0,
        "accuracy": 0.5,
    }])
    metrics.to_csv(outputs / "ml_baseline_a_model_metrics.csv", index=False)
    pd.DataFrame([{"chronological_split": "holdout", "target_name": "target_bad_playbook_day", "availability_window": "pre_rth_only", "model_name": "univariate_threshold_stump", "y_pred": 0}]).to_csv(outputs / "ml_baseline_a_predictions.csv", index=False)
    pd.DataFrame([{"raw_feature": "prior_rth_high", "absolute_coefficient": 1.0}]).to_csv(outputs / "ml_baseline_a_feature_importance.csv", index=False)
    pd.DataFrame([{"target_name": "target_bad_playbook_day", "split": "holdout", "true_positive": 0, "false_positive": 0, "true_negative": 1, "false_negative": 1}]).to_csv(outputs / "ml_baseline_a_confusion_matrices.csv", index=False)
    pd.DataFrame([{"target_name": "target_bad_playbook_day", "split": "validation", "threshold": 0.5}]).to_csv(outputs / "ml_baseline_a_threshold_sweep.csv", index=False)
    pd.DataFrame([{"x": 1}]).to_csv(outputs / "research_signal_registry.csv", index=False)
    pd.DataFrame([{"x": 1}]).to_csv(outputs / "playbook_module_registry.csv", index=False)
    policy = {"paper_trading_approved": False, "official_gates_changed": False}
    (outputs / "playbook_validation_policy.json").write_text(json.dumps(policy), encoding="utf-8")
    (outputs / "playbook_scheduler_policy.json").write_text(json.dumps(policy), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
