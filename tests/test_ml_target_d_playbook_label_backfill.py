from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_target_d_playbook_label_backfill import (  # noqa: E402
    TARGETS_D,
    audit_default_scheduler_universe,
    build_coverage_aligned_splits,
    build_dataset_d,
    build_module_daily_outcome,
    build_next_action_recommendation,
    build_playbook_daily_outcome,
    build_target_balance_by_split,
    build_target_readiness_summary,
    outcome_status,
)


class MlTargetDPlaybookLabelBackfillTests(unittest.TestCase):
    def test_loads_dataset_c_outputs(self) -> None:
        frame = pd.read_csv(PROJECT_ROOT / "outputs" / "ml_target_c_day_regime.csv")
        labels = json.loads((PROJECT_ROOT / "outputs" / "ml_target_c_label_dictionary.json").read_text(encoding="utf-8"))
        self.assertEqual(len(frame), 869)
        self.assertIn("target_active_day_loss_c", labels)

    def test_scheduler_policy_excludes_rare_modules_by_default(self) -> None:
        policy, registry = _real_policy_registry()
        universe = audit_default_scheduler_universe(policy, registry)
        self.assertFalse(policy["default_include_rare_modules_in_scheduler"])
        self.assertFalse(universe["rare_modules_default_scheduler_included"])
        self.assertTrue(set(universe["default_signal_keys"]).isdisjoint(universe["rare_signal_keys"]))

    def test_missing_coverage_is_not_no_trade_zero(self) -> None:
        self.assertEqual(outcome_status(False, 0, 0.0), "missing_source_day")
        universe = _universe()
        replay = {"trades": pd.DataFrame(), "module_status": {"phase11a::module": {"backfill_status": "unavailable_for_backfill", "reason": "unit"}}}
        daily = build_module_daily_outcome(["2023-01-03"], universe, replay)
        self.assertEqual(daily.loc[0, "outcome_status"], "missing_source_day")
        self.assertTrue(pd.isna(daily.loc[0, "daily_net_pnl"]))

    def test_coverage_and_split_generation_are_deterministic(self) -> None:
        dataset, playbook, modules = _sample_inputs(500)
        first_splits, first_summary = build_coverage_aligned_splits(dataset, playbook, modules)
        second_splits, second_summary = build_coverage_aligned_splits(dataset, playbook, modules)
        self.assertEqual(first_splits.keys(), second_splits.keys())
        for key in first_splits:
            pd.testing.assert_series_equal(first_splits[key], second_splits[key])
        pd.testing.assert_frame_equal(first_summary, second_summary)

    def test_revised_targets_are_deterministic(self) -> None:
        dataset, playbook, modules = _sample_inputs(500)
        splits, _ = build_coverage_aligned_splits(dataset, playbook, modules)
        first, info1 = build_dataset_d(dataset, playbook, modules, splits)
        second, info2 = build_dataset_d(dataset, playbook, modules, splits)
        self.assertEqual(info1, info2)
        for target in TARGETS_D:
            pd.testing.assert_series_equal(first[target], second[target])

    def test_active_day_loss_is_null_on_no_trade_and_missing_days(self) -> None:
        dataset, playbook, modules = _sample_inputs(10)
        playbook.loc[0, ["reliable_scheduler_coverage", "accepted_trade_count", "daily_net_pnl", "outcome_status"]] = [False, np.nan, np.nan, "missing_source_day"]
        playbook.loc[1, ["accepted_trade_count", "daily_net_pnl", "outcome_status"]] = [0, 0.0, "no_trade_day"]
        splits, _ = build_coverage_aligned_splits(dataset, playbook, modules)
        out, _ = build_dataset_d(dataset, playbook, modules, splits)
        self.assertTrue(pd.isna(out.loc[0, "target_default_scheduler_active_day_loss_d"]))
        self.assertTrue(pd.isna(out.loc[1, "target_default_scheduler_active_day_loss_d"]))

    def test_large_loss_threshold_uses_labeled_training_only(self) -> None:
        dataset, playbook, modules = _sample_inputs(500)
        splits, _ = build_coverage_aligned_splits(dataset, playbook, modules)
        out, info = build_dataset_d(dataset, playbook, modules, splits)
        training = splits["labeled_coverage_chronological_split"].eq("train") & out["default_scheduler_accepted_trade_count_d"].gt(0)
        expected = float(out.loc[training, "default_scheduler_daily_pnl_d"].quantile(0.25))
        self.assertEqual(info["thresholds_fit_split"], "train")
        self.assertAlmostEqual(info["large_loss_threshold"], expected)

    def test_readiness_rules_are_deterministic(self) -> None:
        dataset, playbook, modules = _sample_inputs(500)
        splits, _ = build_coverage_aligned_splits(dataset, playbook, modules)
        out, _ = build_dataset_d(dataset, playbook, modules, splits)
        balance = build_target_balance_by_split(out, splits)
        first = build_target_readiness_summary(balance, dataset)
        second = build_target_readiness_summary(balance, dataset)
        pd.testing.assert_frame_equal(first, second)

    def test_rare_modules_are_not_in_default_scheduler_labels(self) -> None:
        policy, registry = _real_policy_registry()
        universe = audit_default_scheduler_universe(policy, registry)
        self.assertEqual(universe["default_module_count"], 16)
        self.assertEqual(universe["rare_module_count_excluded"], 25)
        self.assertEqual(universe["quarantined_module_count_excluded"], 6)
        self.assertFalse(universe["quarantined_modules_default_scheduler_included"])

    def test_no_model_training_or_strategy_search_or_promotion(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_target_d_playbook_label_backfill.py").read_text(encoding="utf-8").lower()
        for token in ("sklearn", ".fit(", "predict(", "train_test_split", "optuna"):
            self.assertNotIn(token, source)
        self.assertNotIn("candidate_results_changed\": true", source)
        self.assertNotIn("strategy_candidates_promoted\": true", source)

    def test_recommendation_guardrails_keep_paper_false(self) -> None:
        readiness = pd.DataFrame([{"target_name": "x", "split_variant": "v", "trainable_for_baseline_b": False, "total_non_null_rows": 0, "true_count": 0}])
        coverage = pd.DataFrame([
            {"audit_item": "unavailable_module_count", "value": 1},
            {"audit_item": "backfilled_module_count", "value": 0},
            {"audit_item": "default_module_count", "value": 1},
        ])
        dataset = pd.DataFrame({"default_scheduler_outcome_status_d": ["missing_source_day"]})
        rec = build_next_action_recommendation(readiness, coverage, dataset)
        self.assertEqual(rec["next_action"], "manual_module_backfill_required")
        self.assertFalse(rec["paper_trading_approved"])
        self.assertFalse(rec["live_trading_approved"])
        self.assertFalse(rec["official_gates_changed"])

    def test_report_includes_research_only_no_live_guardrail(self) -> None:
        report = PROJECT_ROOT / "reports" / "ml_target_d_playbook_label_backfill_report.md"
        if not report.exists():
            self.skipTest("Build output not generated yet")
        text = report.read_text(encoding="utf-8").lower()
        self.assertIn("research-only", text)
        self.assertIn("no model training", text)
        self.assertIn("live-trading approval", text)


def _real_policy_registry() -> tuple[dict, pd.DataFrame]:
    policy = json.loads((PROJECT_ROOT / "outputs" / "playbook_scheduler_policy.json").read_text(encoding="utf-8"))
    registry = pd.read_csv(PROJECT_ROOT / "outputs" / "playbook_module_registry.csv")
    return policy, registry


def _universe() -> dict:
    return {"default_signal_keys": ["phase11a::module"], "rare_signal_keys": [], "default_module_count": 1, "rare_module_count_excluded": 0, "rare_modules_default_scheduler_included": False, "quarantined_signal_keys": [], "quarantined_module_count_excluded": 0, "quarantined_modules_default_scheduler_included": False}


def _sample_inputs(n: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2023-01-03", periods=n).strftime("%Y-%m-%d").tolist()
    original = ["discovery" if i < int(n * .6) else ("validation" if i < int(n * .8) else "holdout") for i in range(n)]
    dataset = pd.DataFrame({
        "trading_session": dates,
        "chronological_split": original,
        "recent_oos_like": [i >= n - min(100, n) for i in range(n)],
        "playbook_weak_fold_day": [False] * n,
        "target_high_vol_mixed_weak_day": [False] * n,
        "target_prior_level_interaction_day": [i % 2 == 0 for i in range(n)],
        "target_power_hour_expansion_day": [i % 3 == 0 for i in range(n)],
    })
    active = np.array([i % 3 != 0 for i in range(n)])
    pnl = np.array([float((i % 11) - 5) if active[i] else 0.0 for i in range(n)])
    pnl[active & (pnl == 0)] = 1.0
    playbook = pd.DataFrame({
        "trading_session": dates,
        "reliable_scheduler_coverage": True,
        "accepted_trade_count": active.astype(int),
        "daily_net_pnl": pnl,
        "active_day": active,
        "outcome_status": [outcome_status(True, int(a), float(p)) for a, p in zip(active, pnl)],
    })
    modules = pd.DataFrame({
        "trading_session": dates,
        "signal_key": "phase11a::module",
        "default_scheduler_eligible": True,
        "rare_module": False,
        "reliable_outcome_coverage": True,
        "accepted_trade_count": active.astype(int),
        "daily_net_pnl": pnl,
        "active_day": active,
    })
    return dataset, playbook, modules


if __name__ == "__main__":
    unittest.main()
