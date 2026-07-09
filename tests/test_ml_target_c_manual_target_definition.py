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

from short_term_edge.ml_target_c_manual_target_definition import (  # noqa: E402
    MlTargetCConfig,
    build_dataset_c,
    build_label_dictionary_c,
    build_next_action_recommendation,
    build_pnl_source_coverage,
    build_target_balance_by_split,
    build_target_quality_summary,
    build_target_readiness_summary,
    run_ml_target_c_manual_target_definition,
)


class MlTargetCManualTargetDefinitionTests(unittest.TestCase):
    def test_loads_dataset_b_outputs(self) -> None:
        dataset = pd.read_csv(PROJECT_ROOT / "outputs" / "ml_dataset_b_day_regime.csv")
        labels = json.loads((PROJECT_ROOT / "outputs" / "ml_dataset_b_label_dictionary.json").read_text(encoding="utf-8"))
        self.assertFalse(dataset.empty)
        self.assertIn("scheduler_daily_pnl", dataset.columns)
        self.assertIn("target_bad_playbook_day", labels)

    def test_distinguishes_missing_pnl_from_no_trade_zero(self) -> None:
        frame = _sample_dataset()
        frame.loc[0, "scheduler_daily_pnl"] = float("nan")
        frame.loc[0, "playbook_daily_pnl"] = float("nan")
        out, _ = build_dataset_c(frame)
        self.assertTrue(out.loc[0, "missing_pnl_source_day_c"])
        self.assertFalse(out.loc[0, "no_trade_day_c"])
        self.assertTrue(out.loc[1, "no_trade_day_c"])
        self.assertEqual(out.loc[1, "selected_scheduler_or_playbook_pnl_c"], 0.0)

    def test_active_day_columns_are_deterministic(self) -> None:
        first, _ = build_dataset_c(_sample_dataset())
        second, _ = build_dataset_c(_sample_dataset())
        for column in ["playbook_active_day_c", "scheduler_active_day_c", "any_module_active_day_c", "default_scheduler_module_active_day_c", "rare_module_active_day_c", "no_trade_day_c", "missing_pnl_source_day_c"]:
            pd.testing.assert_series_equal(first[column], second[column])

    def test_revised_target_columns_are_deterministic(self) -> None:
        first, info1 = build_dataset_c(_sample_dataset())
        second, info2 = build_dataset_c(_sample_dataset())
        self.assertEqual(info1, info2)
        for column in ["target_active_day_loss_c", "target_active_day_large_loss_c", "target_any_module_active_day_c", "target_no_trade_but_module_positive_c", "target_bad_regime_c"]:
            pd.testing.assert_series_equal(first[column], second[column])

    def test_no_trade_days_do_not_force_active_day_loss_labels(self) -> None:
        out, _ = build_dataset_c(_sample_dataset())
        self.assertTrue(out.loc[1, "no_trade_day_c"])
        self.assertTrue(pd.isna(out.loc[1, "target_active_day_loss_c"]))

    def test_discovery_only_thresholds_are_used_for_large_loss_target(self) -> None:
        out, info = build_dataset_c(_large_loss_threshold_dataset())
        self.assertEqual(info["thresholds_fit_split"], "discovery")
        self.assertTrue(info["large_loss_threshold_available"])
        discovery_active = out[out["chronological_split"].eq("discovery")]["selected_scheduler_or_playbook_pnl_c"]
        self.assertAlmostEqual(info["large_loss_threshold"], float(discovery_active.quantile(0.25)))

    def test_target_readiness_rules_are_deterministic(self) -> None:
        out, info = build_dataset_c(_large_loss_threshold_dataset())
        balance = build_target_balance_by_split(out, ["target_active_day_loss_c", "target_any_module_active_day_c"])
        quality = build_target_quality_summary(out, balance, info)
        first = build_target_readiness_summary(quality)
        second = build_target_readiness_summary(quality)
        pd.testing.assert_frame_equal(first, second)

    def test_label_dictionary_documents_null_meaning(self) -> None:
        out, info = build_dataset_c(_sample_dataset())
        balance = build_target_balance_by_split(out, ["target_active_day_loss_c"])
        readiness = build_target_readiness_summary(build_target_quality_summary(out, balance, info))
        labels = build_label_dictionary_c({}, out, readiness, info)
        self.assertIn("null_meaning", labels["target_active_day_loss_c"])
        self.assertIn("No selected scheduler/playbook active trade", labels["target_active_day_loss_c"]["null_meaning"])

    def test_at_least_one_pnl_source_coverage_row_is_produced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily.csv"
            pd.DataFrame({"trading_session": ["2026-01-01"], "net_pnl": [0.0]}).to_csv(path, index=False)
            coverage = build_pnl_source_coverage(_sample_dataset(), {"unit_source": path})
            self.assertEqual(len(coverage), 1)
            self.assertEqual(coverage.loc[0, "zero_pnl_days"], 1)
            self.assertIn("missing_source_day", coverage.loc[0, "missing_pnl_handling"])

    def test_no_model_training_is_performed(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_target_c_manual_target_definition.py").read_text(encoding="utf-8").lower()
        for token in ["sklearn", ".fit(", "predict(", "train_test_split"]:
            self.assertNotIn(token, source)

    def test_no_strategy_signals_are_generated(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_target_c_manual_target_definition.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("entry_signal", source)
        self.assertNotIn("generated_strategy_signals\": true", source)

    def test_paper_trading_approved_remains_false(self) -> None:
        out, info = build_dataset_c(_sample_dataset())
        balance = build_target_balance_by_split(out, ["target_active_day_loss_c"])
        quality = build_target_quality_summary(out, balance, info)
        readiness = build_target_readiness_summary(quality)
        coverage = pd.DataFrame([{"present": True, "zero_meaning": "active_day_zero_result"}])
        recommendation = build_next_action_recommendation(out, readiness, coverage, quality, info)
        self.assertFalse(recommendation["paper_trading_approved"])
        self.assertFalse(recommendation["live_trading_approved"])

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = root / "outputs"
            reports = root / "reports"
            artifacts = root / "artifacts" / "ml_target_c_manual_target_definition" / "unit"
            outputs.mkdir(parents=True)
            _sample_dataset().to_csv(outputs / "ml_dataset_b_day_regime.csv", index=False)
            (outputs / "ml_dataset_b_label_dictionary.json").write_text(json.dumps({"target_bad_playbook_day": {"role": "target"}}), encoding="utf-8")
            source_path = outputs / "source.csv"
            pd.DataFrame({"trading_session": ["2026-01-01"], "net_pnl": [1.0]}).to_csv(source_path, index=False)
            config = MlTargetCConfig(
                dataset_b_path=outputs / "ml_dataset_b_day_regime.csv",
                label_dictionary_b_path=outputs / "ml_dataset_b_label_dictionary.json",
                output_dir=outputs,
                report_dir=reports,
                artifact_dir=artifacts,
                candidate_pnl_sources={"unit_source": source_path},
                run_id="unit",
            )
            run_ml_target_c_manual_target_definition(config)
            report = (reports / "ml_target_c_manual_target_definition_report.md").read_text(encoding="utf-8")
            self.assertIn("research-only", report.lower())
            self.assertIn("No model training", report)
            self.assertIn("live-trading approval", report)


def _sample_dataset() -> pd.DataFrame:
    rows = []
    for i in range(8):
        active = i in {0, 2, 3, 5}
        pnl = [-5.0, 0.0, 10.0, -2.0, 0.0, 4.0, 0.0, 0.0][i]
        rows.append({
            "trading_session": f"2026-01-{i+1:02d}",
            "chronological_split": "discovery" if i < 4 else ("validation" if i < 6 else "holdout"),
            "recent_oos_like": i >= 6,
            "scheduler_daily_pnl": pnl,
            "playbook_daily_pnl": pnl,
            "playbook_active_day": active,
            "scheduler_no_trade_day": not active,
            "playbook_weak_fold_day": i == 3,
            "strict_high_vol_mixed_flag": i == 0,
            "target_high_vol_mixed_weak_day": False,
            "target_prior_level_interaction_day": i % 2 == 0,
            "target_power_hour_expansion_day": i % 3 == 0,
            "phase10b_daily_pnl": 1.0 if i in {1, 4} else 0.0,
            "phase10b_active": i in {1, 4},
            "phase11a_daily_pnl": -1.0 if i == 6 else 0.0,
            "phase11a_active": i == 6,
            "phase12a_daily_pnl": 0.0,
            "phase12a_active": False,
            "phase13a_daily_pnl": 0.0,
            "phase13a_active": False,
            "phase14a_daily_pnl": 0.0,
            "phase14a_active": False,
            "phase15a_daily_pnl": 0.0,
            "phase15a_active": False,
            "phase16a_daily_pnl": 2.0 if i == 7 else 0.0,
            "phase16a_active": i == 7,
            "phase17a_daily_pnl": 0.0,
            "phase17a_active": False,
        })
    return pd.DataFrame(rows)


def _large_loss_threshold_dataset() -> pd.DataFrame:
    rows = []
    splits = ["discovery"] * 80 + ["validation"] * 30 + ["holdout"] * 30
    for i, split in enumerate(splits):
        pnl = float(i - 40) if split == "discovery" else (-1.0 if i % 2 == 0 else 1.0)
        rows.append({
            "trading_session": f"2026-03-{(i % 28) + 1:02d}-{i}",
            "chronological_split": split,
            "recent_oos_like": split == "holdout",
            "scheduler_daily_pnl": pnl,
            "playbook_daily_pnl": pnl,
            "playbook_active_day": True,
            "scheduler_no_trade_day": False,
            "playbook_weak_fold_day": False,
            "strict_high_vol_mixed_flag": False,
            "target_high_vol_mixed_weak_day": False,
            "target_prior_level_interaction_day": i % 2 == 0,
            "target_power_hour_expansion_day": i % 2 == 1,
            **{f"phase{phase}a_daily_pnl": 0.0 for phase in range(11, 18)},
            **{f"phase{phase}a_active": False for phase in range(11, 18)},
            "phase10b_daily_pnl": pnl,
            "phase10b_active": True,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
