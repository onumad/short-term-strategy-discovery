from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.module_registry_f_quarantine import (  # noqa: E402
    QUARANTINE_STATUS,
    apply_quarantine,
    build_module_registry_f_quarantine,
    update_registry_schema,
)
from short_term_edge.ml_target_d_playbook_label_backfill import audit_default_scheduler_universe  # noqa: E402
from short_term_edge.playbook_scheduler_policy import default_scheduler_universe  # noqa: E402


class ModuleRegistryFQuarantineTests(unittest.TestCase):
    def test_real_inputs_quarantine_exactly_six_and_preserve_ids(self) -> None:
        registry = pd.read_csv(PROJECT_ROOT / "outputs" / "playbook_module_registry.csv")
        audit = pd.read_csv(PROJECT_ROOT / "outputs" / "ml_backfill_e_phase10b_module_audit.csv")
        original_ids = registry["module_id"].astype(str).tolist()
        updated, quarantine = apply_quarantine(registry, audit)
        self.assertEqual(len(quarantine), 6)
        self.assertEqual(original_ids, updated["module_id"].astype(str).tolist())
        self.assertTrue(quarantine["causality_review_status"].eq(QUARANTINE_STATUS).all())
        self.assertFalse(quarantine["scheduler_eligible"].any())
        self.assertFalse(quarantine["ml_backfill_eligible"].any())

    def test_scheduler_excludes_quarantine_even_when_not_rare(self) -> None:
        registry = pd.DataFrame(
            [
                _row("safe", "not_flagged_by_phase10b_causality_audit", True),
                _row("unsafe", QUARANTINE_STATUS, False),
            ]
        )
        universe = default_scheduler_universe(registry)
        self.assertEqual(universe["candidate_id"].tolist(), ["safe"])

    def test_ml_backfill_fails_closed_if_policy_reintroduces_quarantine(self) -> None:
        registry = pd.DataFrame([_row("unsafe", QUARANTINE_STATUS, False)])
        policy = {
            "recommended_default_scheduler_universe": {"signal_keys": ["phase10b::unsafe"]},
            "default_include_rare_modules_in_scheduler": False,
        }
        with self.assertRaisesRegex(ValueError, "Quarantined modules"):
            audit_default_scheduler_universe(policy, registry)

    def test_schema_requires_quarantine_fields(self) -> None:
        schema = update_registry_schema({"columns": ["module_id"], "required_columns": ["module_id"]})
        for field in ("causality_review_status", "scheduler_eligible", "ml_backfill_eligible", "quarantine_reason", "replacement_module_id"):
            self.assertIn(field, schema["columns"])
            self.assertIn(field, schema["required_columns"])
        self.assertFalse(schema["causality_quarantine"]["silent_definition_replacement_allowed"])

    def test_real_build_has_six_quarantined_and_sixteen_default_modules(self) -> None:
        result = build_module_registry_f_quarantine(PROJECT_ROOT, "module-registry-f-test")
        self.assertEqual(len(result["quarantine"]), 6)
        self.assertEqual(result["scheduler_policy"]["recommended_default_scheduler_universe"]["module_count"], 16)
        rec = result["next_action_recommendation"]
        self.assertFalse(rec["paper_trading_approved"])
        self.assertFalse(rec["live_trading_approved"])
        self.assertFalse(rec["official_gates_changed"])


def _row(candidate: str, status: str, eligible: bool) -> dict[str, object]:
    return {
        "module_id": candidate,
        "phase": "phase10b",
        "candidate_id": candidate,
        "research_track": "parked_research_signal",
        "portfolio_role": "parked_module",
        "portfolio_contribution_status": "previously_parked_research_signal",
        "causality_review_status": status,
        "scheduler_eligible": eligible,
        "ml_backfill_eligible": eligible,
    }


if __name__ == "__main__":
    unittest.main()
