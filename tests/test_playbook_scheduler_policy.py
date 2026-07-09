from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.playbook_scheduler_policy import (  # noqa: E402
    build_playbook_scheduler_f_artifacts,
    build_playbook_scheduler_policy,
    default_admission_universe,
    default_scheduler_universe,
    load_playbook_scheduler_policy_inputs,
    rare_low_activity_scheduler_mapping,
    rare_modules_from_registry,
)


class PlaybookSchedulerPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_playbook_scheduler_policy_inputs(PROJECT_ROOT)
        cls.artifacts = build_playbook_scheduler_f_artifacts(PROJECT_ROOT)
        cls.policy = cls.artifacts["policy"]

    def test_loads_scheduler_e_recommendation(self) -> None:
        recommendation = self.data["scheduler_e_recommendation"]
        self.assertEqual(recommendation["next_action"], "park_rare_modules_in_registry_but_exclude_from_scheduler")
        self.assertFalse(recommendation["official_gates_changed"])
        self.assertFalse(recommendation["paper_trading_approved"])

    def test_loads_rare_module_policy(self) -> None:
        policy = self.data["rare_module_policy"]
        self.assertTrue(policy["rare_module_track_enabled"])
        self.assertFalse(policy["official_gates_changed"])
        self.assertFalse(policy["paper_trading_approved"])

    def test_builds_scheduler_policy_deterministically(self) -> None:
        first = build_playbook_scheduler_policy(self.data)
        second = build_playbook_scheduler_policy(self.data)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(first["policy_name"], "playbook_scheduler_f_rare_module_exclusion_policy")

    def test_rare_modules_are_registry_only_by_default(self) -> None:
        registry = self.data["playbook_module_registry"]
        rare = rare_modules_from_registry(registry)
        default_universe = default_scheduler_universe(registry)
        rare_ids = set(rare["module_id"].astype(str))
        default_ids = set(default_universe["module_id"].astype(str))
        self.assertGreater(len(rare_ids), 0)
        self.assertTrue(rare_ids.isdisjoint(default_ids))
        self.assertFalse(self.policy["default_include_rare_modules_in_scheduler"])
        self.assertEqual(
            self.policy["rare_module_default_scheduler_status"],
            "registry_only_excluded_from_default_scheduler",
        )

    def test_historical_replay_is_separate_from_current_default_admission(self) -> None:
        registry = self.data["playbook_module_registry"]
        historical = default_scheduler_universe(registry)
        admitted = default_admission_universe(registry)
        self.assertEqual(len(historical), 16)
        self.assertTrue(admitted.empty)
        self.assertEqual(
            self.policy["recommended_default_scheduler_universe"]["semantic_status"],
            "historical_research_replay_universe_not_current_default_admission",
        )
        self.assertEqual(self.policy["current_default_admission_universe"]["module_count"], 0)

    def test_conditional_scheduler_allows_no_trade_without_daily_target(self) -> None:
        self.assertTrue(self.policy["no_trade_is_valid"])
        self.assertIsNone(self.policy["minimum_trades_per_day"])
        self.assertFalse(self.policy["forced_daily_activity"])
        self.assertEqual(
            set(self.policy["eligibility_layers"]),
            {"condition_eligible", "research_eligible", "default_scheduler_admitted"},
        )

    def test_rare_modules_allowed_in_explicit_rare_or_diversifier_audits(self) -> None:
        exception_rules = self.policy["rare_module_exception_rules"]
        self.assertTrue(self.policy["rare_modules_allowed_in_explicit_audits"])
        self.assertIn("explicit_rare_module_audit", exception_rules["allowed_contexts"])
        self.assertIn("explicit_diversifier_audit", exception_rules["allowed_contexts"])
        self.assertEqual(exception_rules["required_explicit_flag"], "include_rare_modules_in_scheduler=true")

    def test_low_activity_does_not_map_to_no_signal(self) -> None:
        mapping = rare_low_activity_scheduler_mapping("positive_research_signal")
        self.assertEqual(mapping["signal_evidence_status"], "positive_research_signal")
        self.assertFalse(mapping["signal_evidence_status_forced_to_no_signal"])
        self.assertNotEqual(mapping["signal_evidence_status"], "no_signal")
        self.assertTrue(mapping["low_activity_blocks_tradability"])

    def test_paper_trading_approved_remains_false(self) -> None:
        self.assertFalse(self.policy["paper_trading_approved"])
        self.assertFalse(self.artifacts["recommendation"]["paper_trading_approved"])
        self.assertTrue(self.policy["rare_module_exception_rules"]["must_keep_paper_trading_approved_false"])

    def test_official_gates_changed_remains_false(self) -> None:
        self.assertFalse(self.policy["official_gates_changed"])
        self.assertFalse(self.artifacts["recommendation"]["official_gates_changed"])
        self.assertTrue(self.policy["rare_module_exception_rules"]["must_keep_official_gates_changed_false"])

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        report = self.artifacts["report"]
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("approved no paper or live trading", report)
        self.assertIn("default_include_rare_modules_in_scheduler: `false`", report)


if __name__ == "__main__":
    unittest.main()
