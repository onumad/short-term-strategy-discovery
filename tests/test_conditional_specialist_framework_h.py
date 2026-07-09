from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.conditional_specialist_framework_h import (  # noqa: E402
    ACTIVATION_CONTRACT_VERSION,
    SESSION_WINDOWS,
    activation_contract_schema,
    build_activation_contracts,
    build_condition_coverage_matrix,
    build_hypothesis_ledger,
    build_redundancy_audit,
    conditional_specialist_policy,
)


class ConditionalSpecialistFrameworkHTests(unittest.TestCase):
    def test_policy_makes_no_trade_valid_without_daily_target(self) -> None:
        policy = conditional_specialist_policy()
        self.assertTrue(policy["no_trade_is_valid"])
        self.assertIsNone(policy["minimum_trades_per_day"])
        self.assertFalse(policy["forced_daily_activity"])
        self.assertFalse(policy["paper_trading_approved"])
        self.assertFalse(policy["live_trading_approved"])

    def test_activation_schema_separates_three_eligibility_layers(self) -> None:
        schema = activation_contract_schema()
        self.assertEqual(schema["schema_version"], ACTIVATION_CONTRACT_VERSION)
        self.assertEqual(set(schema["eligibility_layers"]), {"condition_eligible", "research_eligible", "default_scheduler_admitted"})
        self.assertTrue(schema["runtime_binding_required_before_active_use"])

    def test_current_style_parked_module_is_not_default_admitted(self) -> None:
        contracts = build_activation_contracts(_registry())
        parked = contracts[contracts["candidate_id"].eq("parked")].iloc[0]
        self.assertTrue(parked["research_eligible"])
        self.assertFalse(parked["default_scheduler_admitted"])
        self.assertIn("not_regular_practice_candidate", parked["default_admission_failures"])
        self.assertIn("runtime_activation_contract_not_bound", parked["default_admission_failures"])
        self.assertTrue(parked["no_trade_is_valid"])

    def test_even_passing_metadata_requires_runtime_binding(self) -> None:
        contracts = build_activation_contracts(_registry())
        candidate = contracts[contracts["candidate_id"].eq("candidate")].iloc[0]
        self.assertFalse(candidate["default_scheduler_admitted"])
        self.assertEqual(candidate["default_admission_failures"], "runtime_activation_contract_not_bound")

    def test_coverage_matrix_contains_every_condition_window_and_no_forced_trade(self) -> None:
        contracts = build_activation_contracts(_registry())
        taxonomy = {"market_condition": ["range_day", "trend_day"]}
        coverage = build_condition_coverage_matrix(contracts, taxonomy)
        self.assertEqual(len(coverage), 2 * len(SESSION_WINDOWS))
        self.assertTrue(coverage["no_trade_is_valid"].all())
        self.assertIn("uncovered", set(coverage["coverage_status"]))

    def test_redundancy_and_hypothesis_ledgers_are_deterministic(self) -> None:
        registry = _registry()
        contracts = build_activation_contracts(registry)
        redundancy = build_redundancy_audit(contracts)
        ledger = build_hypothesis_ledger(registry)
        self.assertEqual(len(redundancy), 1)
        self.assertEqual(int(redundancy.iloc[0]["module_count"]), 2)
        self.assertTrue((ledger["parameter_variation_alone_may_reopen"] == False).all())  # noqa: E712
        self.assertTrue((ledger["paper_trading_approved"] == False).all())  # noqa: E712


def _registry() -> pd.DataFrame:
    base = {
        "phase": "phase11a",
        "market_condition": "range_day",
        "module_family": "fade",
        "signal_evidence_status": "positive_research_signal",
        "causality_review_status": "causal_definition_reviewed",
        "official_gates_passed": False,
        "portfolio_contribution_status": "not_evaluated",
        "stress_pnl": 10.0,
        "holdout_pnl": 5.0,
    }
    return pd.DataFrame(
        [
            {**base, "module_id": "m1", "candidate_id": "parked", "tradability_status": "not_tradable_concentrated", "research_track": "parked_research_signal"},
            {**base, "module_id": "m2", "candidate_id": "candidate", "tradability_status": "review_packet_candidate", "research_track": "regular_practice_candidate", "official_gates_passed": True, "portfolio_contribution_status": "positive_incremental_contribution"},
        ]
    )


if __name__ == "__main__":
    unittest.main()
