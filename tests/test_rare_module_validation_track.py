from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.rare_module_validation_track import (  # noqa: E402
    build_candidate_review,
    build_next_action_recommendation,
    build_policy,
    build_rare_module_validation_track_artifacts,
    load_rare_module_validation_inputs,
    passes_rare_module_registration_rules,
    phase16a_watchlist_rows,
    identify_phase16a_positive_uncorrelated_candidates,
    watchlist_hygiene_status,
)


class RareModuleValidationTrackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_rare_module_validation_inputs(PROJECT_ROOT)
        cls.artifacts = build_rare_module_validation_track_artifacts(PROJECT_ROOT)
        cls.policy = cls.artifacts["policy"]
        cls.candidate_review = cls.artifacts["candidate_review"]

    def test_loads_playbook_validation_policy(self) -> None:
        self.assertIn("playbook_validation_policy", self.data)
        self.assertFalse(self.data["playbook_validation_policy"]["official_gates_changed"])
        self.assertFalse(self.data["playbook_validation_policy"]["paper_trading_approved"])

    def test_loads_phase16a_candidate_and_fold_adequacy_outputs(self) -> None:
        self.assertIn("phase16a_candidate_results", self.data)
        self.assertIn("phase16a_module_fold_adequacy", self.data)
        self.assertGreater(len(self.data["phase16a_candidate_results"]), 0)
        self.assertGreater(len(self.data["phase16a_module_fold_adequacy"]), 0)

    def test_identifies_phase16a_positive_uncorrelated_candidates(self) -> None:
        positives = identify_phase16a_positive_uncorrelated_candidates(self.data["phase16a_candidate_results"])
        self.assertEqual(len(positives), 3)
        self.assertTrue((positives["phase16a_label"] == "phase16a_positive_uncorrelated_research_signal").all())

    def test_identifies_phase16a_watchlist_rows(self) -> None:
        watchlist = phase16a_watchlist_rows(self.data["phase16a_candidate_results"])
        self.assertEqual(len(watchlist), 5)
        self.assertTrue((watchlist["phase16a_label"] == "phase16a_watchlist_needs_more_history").all())

    def test_rare_module_registration_rules_are_deterministic(self) -> None:
        review_a = build_candidate_review(self.data)
        review_b = build_candidate_review(self.data)
        self.assertEqual(review_a.to_json(orient="records"), review_b.to_json(orient="records"))
        first_positive = self.data["phase16a_candidate_results"].query(
            "phase16a_label == 'phase16a_positive_uncorrelated_research_signal'"
        ).iloc[0].to_dict()
        self.assertTrue(passes_rare_module_registration_rules(first_positive))

    def test_watchlist_label_hygiene_blocks_weak_invalid_watchlist_rows(self) -> None:
        watchlist = phase16a_watchlist_rows(self.data["phase16a_candidate_results"])
        statuses = [watchlist_hygiene_status(row.to_dict()) for _, row in watchlist.iterrows()]
        self.assertTrue(all(status.startswith("blocked_from_registry_watchlist") for status in statuses))
        blocked = self.candidate_review[self.candidate_review["label"].eq("phase16a_watchlist_needs_more_history")]
        self.assertTrue((blocked["registration_decision"] == "reject_from_registry").all())

    def test_policy_keeps_official_gates_changed_false(self) -> None:
        self.assertFalse(self.policy["official_gates_changed"])
        self.assertFalse(self.artifacts["recommendation"]["official_gates_changed"])

    def test_policy_keeps_paper_trading_approved_false(self) -> None:
        self.assertFalse(self.policy["paper_trading_approved"])
        self.assertFalse(self.artifacts["recommendation"]["paper_trading_approved"])

    def test_no_registry_files_are_mutated_by_artifact_build(self) -> None:
        registry_paths = [
            PROJECT_ROOT / "outputs" / "research_signal_registry.csv",
            PROJECT_ROOT / "outputs" / "research_signal_registry.json",
            PROJECT_ROOT / "outputs" / "playbook_module_registry.csv",
            PROJECT_ROOT / "outputs" / "playbook_module_registry.json",
        ]
        before = {path: _sha256(path) for path in registry_paths}
        build_rare_module_validation_track_artifacts(PROJECT_ROOT)
        after = {path: _sha256(path) for path in registry_paths}
        self.assertEqual(before, after)

    def test_no_new_strategy_signals_are_generated(self) -> None:
        self.assertFalse(self.policy["new_strategy_signals_generated"])
        self.assertFalse(self.policy["strategy_searches_run"])
        self.assertFalse(self.policy["candidate_results_changed"])
        self.assertEqual(self.artifacts["recommendation"]["strategy_searches_run"], False)

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        report = self.artifacts["report"]
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("approved no paper or live trading", report)

    def test_recommendation_for_phase16a_rare_modules_and_label_hygiene(self) -> None:
        recommendation = build_next_action_recommendation(self.candidate_review, build_policy())
        self.assertEqual(recommendation["next_action"], "research_signal_registry_e_add_phase16a_rare_modules")
        self.assertIn("phase16a_label_hygiene_patch", recommendation["recommended_actions"])
        self.assertIn("playbook_framework_e_rare_module_policy_integration", recommendation["recommended_actions"])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
