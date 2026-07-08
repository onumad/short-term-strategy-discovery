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

from short_term_edge.playbook_evaluation import (
    OFFICIAL_PROMOTION_GATES_REFERENCE,
    build_labeling_rules,
    build_playbook_evaluation_config,
    build_reporting_guidelines,
    classify_existing_registry_rows,
    classify_module_activity,
    default_future_candidate_record,
    load_playbook_taxonomy,
    next_action_for_module,
    render_alignment_report,
)


class PlaybookEvaluationTests(unittest.TestCase):
    def test_loads_playbook_taxonomy_config(self) -> None:
        taxonomy = load_playbook_taxonomy(PROJECT_ROOT)
        config = build_playbook_evaluation_config(taxonomy)
        self.assertIn("market_condition", config["taxonomy"])
        self.assertIn("module_activity_gate", config)

    def test_module_and_playbook_activity_gates_are_distinct(self) -> None:
        config = build_playbook_evaluation_config(load_playbook_taxonomy(PROJECT_ROOT))
        self.assertIn("regular_practice_module", config["module_activity_gate"])
        self.assertIn("target_total_active_days", config["playbook_activity_gate"])
        self.assertNotEqual(config["module_activity_gate"], config["playbook_activity_gate"])

    def test_rare_setup_low_activity_does_not_force_no_signal(self) -> None:
        labels = classify_module_activity(
            signal_evidence_status="positive_research_signal",
            active_days=1,
            module_activity_type="rare_setup_module",
        )
        self.assertEqual(labels["signal_evidence_status"], "positive_research_signal")
        self.assertEqual(labels["research_track"], "rare_setup_research_signal")

    def test_low_activity_can_force_tradability_low_activity(self) -> None:
        labels = classify_module_activity(
            signal_evidence_status="positive_research_signal",
            active_days=3,
            module_activity_type="regular_practice_module",
        )
        self.assertEqual(labels["tradability_status"], "not_tradable_low_activity")

    def test_paper_trading_defaults_false(self) -> None:
        record = default_future_candidate_record("module_a")
        self.assertFalse(record["paper_trading_approved"])
        self.assertFalse(record["official_gates_passed"])

    def test_official_promotion_gates_are_not_changed(self) -> None:
        config = build_playbook_evaluation_config(load_playbook_taxonomy(PROJECT_ROOT))
        self.assertFalse(config["official_promotion_gates_reference"]["changed_by_playbook_framework_c"])
        self.assertEqual(config["official_promotion_gates_reference"], OFFICIAL_PROMOTION_GATES_REFERENCE)

    def test_score_components_are_separate(self) -> None:
        config = build_playbook_evaluation_config(load_playbook_taxonomy(PROJECT_ROOT))
        self.assertIn("stress_pnl", config["signal_score_components"])
        self.assertIn("active_days", config["tradability_score_components"])
        self.assertIn("incremental_active_days", config["portfolio_score_components"])
        self.assertFalse(set(config["signal_score_components"]) & {"official_gate_passes"})

    def test_next_action_positive_rare_adds_to_module_registry(self) -> None:
        action = next_action_for_module(
            signal_evidence_status="positive_research_signal",
            research_track="rare_setup_research_signal",
        )
        self.assertEqual(action, "add_to_module_registry")

    def test_next_action_positive_uncorrelated_runs_portfolio_audit(self) -> None:
        action = next_action_for_module(
            signal_evidence_status="positive_research_signal",
            research_track="parked_research_signal",
            average_correlation=0.12,
        )
        self.assertEqual(action, "run_portfolio_audit")

    def test_reporting_guidelines_include_preferred_language(self) -> None:
        guidelines = build_reporting_guidelines()
        self.assertIn("positive research signal but not tradable", guidelines["preferred_language"])

    def test_existing_registry_rows_classified_without_changing_old_labels(self) -> None:
        registry = pd.DataFrame(
            [
                {
                    "candidate_id": "a",
                    "signal_evidence_status": "real_but_nontradable_signal",
                    "tradability_status": "not_tradable_concentrated",
                    "research_track": "parked_research_signal",
                }
            ]
        )
        classified = classify_existing_registry_rows(registry)
        self.assertEqual(classified.loc[0, "signal_evidence_status"], "real_but_nontradable_signal")
        self.assertEqual(classified.loc[0, "original_signal_evidence_status"], "real_but_nontradable_signal")
        self.assertFalse(bool(classified.loc[0, "paper_trading_approved"]))

    def test_report_includes_research_guardrail(self) -> None:
        config = build_playbook_evaluation_config(load_playbook_taxonomy(PROJECT_ROOT))
        report = render_alignment_report(
            registry_rows=1,
            config=config,
            recommendation={
                "next_action": "phase13a_final_acceptance_then_module_registry_update",
                "rationale": "test",
                "official_gates_changed": False,
                "paper_trading_approved": False,
            },
        )
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)

    def test_labeling_rules_preserve_low_activity_split(self) -> None:
        rules = build_labeling_rules(load_playbook_taxonomy(PROJECT_ROOT))
        self.assertFalse(rules["low_activity_rule"]["signal_evidence_status_forced_to_no_signal"])
        self.assertEqual(rules["low_activity_rule"]["tradability_status_when_low_activity"], "not_tradable_low_activity")
        self.assertFalse(rules["official_gates_changed"])


if __name__ == "__main__":
    unittest.main()
