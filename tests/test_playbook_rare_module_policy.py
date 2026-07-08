from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.playbook_rare_module_policy import (  # noqa: E402
    build_playbook_framework_e_artifacts,
    build_playbook_rare_module_policy,
    load_playbook_rare_module_policy_inputs,
    phase16a_rare_modules_in_registry,
    rare_low_activity_mapping,
    passes_rare_registry_rules,
    watchlist_hygiene_review_status,
)


class PlaybookRareModulePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_playbook_rare_module_policy_inputs(PROJECT_ROOT)
        cls.artifacts = build_playbook_framework_e_artifacts(PROJECT_ROOT)
        cls.policy = cls.artifacts["policy"]

    def test_loads_rare_module_validation_track_policy(self) -> None:
        policy = self.data["rare_module_validation_track_policy"]
        self.assertTrue(policy["rare_module_track_enabled"])
        self.assertFalse(policy["official_gates_changed"])
        self.assertFalse(policy["paper_trading_approved"])

    def test_loads_research_signal_and_playbook_module_registries(self) -> None:
        self.assertGreater(len(self.data["research_signal_registry_csv"]), 0)
        self.assertGreater(len(self.data["playbook_module_registry_csv"]), 0)
        self.assertIn("research_signal_registry_json", self.data)
        self.assertIn("playbook_module_registry_json", self.data)

    def test_phase16a_rare_modules_are_present_in_registry(self) -> None:
        rare_modules = phase16a_rare_modules_in_registry(self.data["playbook_module_registry_csv"])
        self.assertEqual(len(rare_modules), 3)
        self.assertTrue((rare_modules["research_track"] == "rare_setup_research_signal").all())
        self.assertTrue((rare_modules["tradability_status"] == "not_tradable_low_activity").all())

    def test_builds_playbook_rare_module_policy_deterministically(self) -> None:
        first = build_playbook_rare_module_policy(self.data)
        second = build_playbook_rare_module_policy(self.data)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(first["policy_name"], "playbook_framework_e_rare_module_policy_integration")

    def test_rare_module_low_activity_does_not_convert_signal_evidence_to_no_signal(self) -> None:
        mapping = rare_low_activity_mapping("positive_research_signal")
        self.assertEqual(mapping["signal_evidence_status"], "positive_research_signal")
        self.assertFalse(mapping["signal_evidence_status_forced_to_no_signal"])
        self.assertNotEqual(mapping["signal_evidence_status"], "no_signal")

    def test_rare_module_low_activity_maps_tradability_to_not_tradable_low_activity(self) -> None:
        mapping = rare_low_activity_mapping("positive_research_signal")
        self.assertEqual(mapping["tradability_status"], "not_tradable_low_activity")

    def test_rare_module_registry_rules_preserve_paper_trading_false(self) -> None:
        rare_modules = phase16a_rare_modules_in_registry(self.data["playbook_module_registry_csv"])
        self.assertTrue((rare_modules["paper_trading_approved"].astype(str).str.lower() == "false").all())
        passing = [passes_rare_registry_rules(row.to_dict()) for _, row in rare_modules.iterrows()]
        self.assertTrue(all(passing))

    def test_rare_module_registry_rules_preserve_official_gates_false(self) -> None:
        rare_modules = phase16a_rare_modules_in_registry(self.data["playbook_module_registry_csv"])
        self.assertTrue((rare_modules["official_gates_passed"].astype(str).str.lower() == "false").all())
        self.assertFalse(self.policy["official_gates_changed"])

    def test_watchlist_hygiene_blocks_weak_invalid_watchlist_rows_from_review_status(self) -> None:
        rows = self.data["rare_module_validation_track_registration_decisions"]
        watchlist_rows = rows[rows["label"].eq("phase16a_watchlist_needs_more_history")]
        self.assertGreater(len(watchlist_rows), 0)
        statuses = [watchlist_hygiene_review_status(row.to_dict()) for _, row in watchlist_rows.iterrows()]
        self.assertTrue(all(status == "blocked_from_review" for status in statuses))

    def test_portfolio_audit_rules_include_rare_module_contribution_fields(self) -> None:
        rules = self.artifacts["portfolio_audit_rules"]
        fields = rules["required_rare_module_contribution_fields"]
        self.assertIn("rare_module_active_days_added", fields)
        self.assertIn("rare_module_weak_fold_improvement_status", fields)
        self.assertIn("rare_module_drawdown_delta", fields)
        self.assertTrue(rules["report_rare_module_contribution_separately"])

    def test_official_gates_are_not_changed(self) -> None:
        self.assertFalse(self.policy["official_gates_changed"])
        self.assertTrue(self.policy["no_official_paper_review_threshold_is_loosened"])
        self.assertFalse(self.artifacts["recommendation"]["official_gates_changed"])

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        report = self.artifacts["report"]
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("Rare module track is research-only", report)
        self.assertIn("paper_trading_approved: `false`", report)


if __name__ == "__main__":
    unittest.main()
