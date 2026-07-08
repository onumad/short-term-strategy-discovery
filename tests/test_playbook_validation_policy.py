from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.playbook_validation_policy import (  # noqa: E402
    FUTURE_VALIDATION_FIELDS,
    NEXT_ACTION_RECOMMENDATION,
    build_validation_framework_d_artifacts,
    build_playbook_validation_policy,
    classify_fold_adequacy,
    load_validation_framework_d_inputs,
)


class PlaybookValidationPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_validation_framework_d_inputs(PROJECT_ROOT)
        cls.artifacts = build_validation_framework_d_artifacts(PROJECT_ROOT)
        cls.policy = cls.artifacts["policy"]

    def test_loads_validation_framework_audit_c_outputs(self) -> None:
        self.assertIn("fold_boundary_summary", self.data)
        self.assertIn("alternative_fold_results", self.data)
        self.assertIn("gate_sensitivity_by_fold_design", self.data)
        self.assertGreater(len(self.data["alternative_fold_results"]), 0)

    def test_loads_playbook_evaluation_config_and_taxonomy(self) -> None:
        self.assertIn("playbook_evaluation_config", self.data)
        self.assertIn("playbook_module_taxonomy", self.data)
        self.assertIn("taxonomy", self.data["playbook_evaluation_config"])
        self.assertIn("module_family", self.data["playbook_module_taxonomy"])

    def test_builds_policy_deterministically(self) -> None:
        first = build_playbook_validation_policy(self.data)
        second = build_playbook_validation_policy(self.data)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_policy_keeps_official_gates_false(self) -> None:
        self.assertFalse(self.policy["official_gates_changed"])
        self.assertTrue(self.policy["official_gate_policy"]["official_promotion_gates_remain_unchanged"])
        self.assertTrue(self.policy["official_gate_policy"]["no_official_paper_review_threshold_is_loosened"])

    def test_policy_keeps_paper_trading_false(self) -> None:
        self.assertFalse(self.policy["paper_trading_approved"])
        self.assertFalse(self.policy["validation_levels"]["paper_review_validation"]["paper_trading_approved_by_this_policy"])

    def test_defines_required_validation_levels(self) -> None:
        self.assertIn("module_level_validation", self.policy["validation_levels"])
        self.assertIn("playbook_level_validation", self.policy["validation_levels"])
        self.assertIn("paper_review_validation", self.policy["validation_levels"])

    def test_defines_required_fold_views(self) -> None:
        views = self.policy["standard_fold_views"]
        self.assertIn("existing_project_folds", views)
        self.assertIn("half_year_folds", views)
        self.assertIn("rolling_6_month_test_folds", views)
        self.assertIn("quarterly_folds", views)
        self.assertTrue(views["quarterly_folds"]["adequacy_warning_required"])
        self.assertFalse(views["quarterly_folds"]["official_promotion_gate"])

    def test_rare_module_low_activity_does_not_convert_to_no_signal(self) -> None:
        adequacy = classify_fold_adequacy(
            validation_level="module_level_validation",
            active_days=1,
            trades=1,
            policy=self.policy,
        )
        self.assertEqual(adequacy["fold_adequacy_status"], "low_activity_not_fully_interpretable")
        self.assertFalse(adequacy["signal_evidence_status_forced_to_no_signal"])
        self.assertTrue(adequacy["tradability_blocked_by_low_activity"])

    def test_future_output_schema_includes_validation_level_and_fold_adequacy(self) -> None:
        schema = self.artifacts["schema"]
        fields = self.policy["future_candidate_output_fields"]
        self.assertIn("validation_level", fields)
        self.assertIn("fold_adequacy_status", fields)
        self.assertIn("validation_level", FUTURE_VALIDATION_FIELDS)
        self.assertIn("future_candidate_output_fields", schema["required"])

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        report = self.artifacts["report"]
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("official_gates_changed: `false`", report)

    def test_no_new_strategy_signals_are_generated(self) -> None:
        self.assertFalse(self.policy["new_strategy_signals_generated"])
        self.assertFalse(self.policy["strategy_searches_run"])
        self.assertFalse(self.policy["candidate_results_changed"])
        self.assertFalse(self.policy["candidates_promoted"])

    def test_next_action_recommendation_matches_contract(self) -> None:
        self.assertEqual(self.artifacts["recommendation"], NEXT_ACTION_RECOMMENDATION)


if __name__ == "__main__":
    unittest.main()
