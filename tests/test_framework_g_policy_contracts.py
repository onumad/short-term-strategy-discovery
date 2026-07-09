from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.framework_g_policy_contracts import (  # noqa: E402
    LLM_OUTPUT_ENVELOPE_VERSION,
    bounded_llm_task_registry,
    counterfactual_policy_contract,
    evaluate_counterfactual_policy_impact,
    validate_llm_output_envelope,
)


class FrameworkGPolicyContractsTests(unittest.TestCase):
    def test_counterfactual_contract_cannot_generate_entries_change_size_or_risk(self) -> None:
        contract = counterfactual_policy_contract()
        self.assertIn("generate_new_entry", contract["prohibited_changes"])
        self.assertIn("increase_position_size", contract["prohibited_changes"])
        self.assertIn("change_risk_limit", contract["prohibited_changes"])
        self.assertFalse(contract["automatic_scheduler_mutation"])
        self.assertFalse(contract["automatic_signal_input_approval"])

    def test_counterfactual_impact_requires_economic_and_risk_non_degradation(self) -> None:
        result = evaluate_counterfactual_policy_impact(_metrics(110), _metrics(120), _metadata())
        self.assertTrue(result["eligible_for_signal_input_review"])
        self.assertFalse(result["approved_as_signal_input"])
        worse = _metrics(120)
        worse["max_drawdown"] = -20
        result = evaluate_counterfactual_policy_impact(_metrics(110), worse, _metadata())
        self.assertFalse(result["eligible_for_signal_input_review"])
        self.assertIn("max_drawdown_worsened", result["failed_checks"])

    def test_counterfactual_rejects_new_entry_or_size_changes(self) -> None:
        metadata = _metadata()
        metadata["generates_new_entries"] = True
        with self.assertRaisesRegex(ValueError, "cannot generate"):
            evaluate_counterfactual_policy_impact(_metrics(110), _metrics(120), metadata)

    def test_llm_candidate_proposal_is_disabled_and_all_tasks_are_non_authoritative(self) -> None:
        registry = bounded_llm_task_registry()
        self.assertFalse(registry["tasks"]["candidate_proposal"]["enabled"])
        self.assertTrue(all(not task["may_affect_policy"] for task in registry["tasks"].values()))
        self.assertFalse(registry["llm_may_authorize_orders"])
        self.assertFalse(registry["approved_as_signal_input_default"])

    def test_llm_output_rejects_prohibited_fields_and_disabled_tasks(self) -> None:
        payload = _llm_output()
        payload["output"]["quantity"] = 1
        with self.assertRaisesRegex(ValueError, "unknown or prohibited"):
            validate_llm_output_envelope(payload)
        disabled = _llm_output()
        disabled["task_id"] = "candidate_proposal"
        disabled["output"] = {
            "module_ids": ["x"], "direction": "long", "evidence_codes": ["e"],
            "expires_at": "2026-07-09T15:00:00Z", "uncertainties": [],
        }
        with self.assertRaisesRegex(ValueError, "disabled"):
            validate_llm_output_envelope(disabled)

    def test_llm_research_summary_validates_exact_schema(self) -> None:
        result = validate_llm_output_envelope(_llm_output())
        self.assertEqual(result["authorization_stage"], "research")
        self.assertFalse(result["approved_as_signal_input"])


def _metrics(net_pnl: float) -> dict[str, object]:
    return {
        "net_pnl": net_pnl,
        "stress_pnl": 100,
        "validation_pnl": 20,
        "holdout_pnl": 30,
        "walk_forward_stress_pnl": 80,
        "max_drawdown": -10,
        "best_day_concentration": 0.10,
        "best_trade_concentration": 0.05,
        "positive_wf_test_folds_pct": 1.0,
        "worst_wf_test_fold": 5,
        "active_days": 100,
        "accepted_trades": 100,
        "model_abstention_count": 0,
        "risk_reject_count": 0,
    }


def _metadata() -> dict[str, object]:
    return {
        "model_release_id": "baseline-b:r1",
        "calibration_version": "cal-v1",
        "feature_contract_version": "features-v1",
        "overlay_action": "veto_existing_candidate_at_fixed_threshold",
        "threshold": 0.7,
        "scheduler_policy_version": "scheduler-f",
        "risk_policy_version": "risk-research-v1",
        "cost_and_slippage_config": "mnq-default-v1",
        "generates_new_entries": False,
        "changes_size_or_risk": False,
    }


def _llm_output() -> dict[str, object]:
    return {
        "schema_version": LLM_OUTPUT_ENVELOPE_VERSION,
        "task_id": "research_evidence_summary",
        "model_identifier": "model-x",
        "prompt_template_version": "prompt-v1",
        "tool_policy_version": "tools-v1",
        "input_refs": ["report:1"],
        "output": {"evidence_codes": ["e1"], "summary": "bounded", "uncertainties": ["u1"]},
        "validation_status": "schema_valid",
        "authorization_stage": "research",
        "approved_as_signal_input": False,
    }


if __name__ == "__main__":
    unittest.main()
