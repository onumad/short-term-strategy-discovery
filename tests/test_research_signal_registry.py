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

from short_term_edge.research_signal_registry import (  # noqa: E402
    REGISTRY_COLUMNS,
    build_research_signal_registry,
    load_registry_inputs,
    render_registry_report,
    signal_evidence_status,
    tradability_status,
    write_registry_outputs,
)


class ResearchSignalRegistryTests(unittest.TestCase):
    def test_load_registry_inputs_requires_audit_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with self.assertRaisesRegex(FileNotFoundError, "Research Signal Registry"):
                load_registry_inputs(out)

    def test_status_logic_is_two_tier_and_strict_for_tradability(self) -> None:
        row = {
            "net_pnl": 100,
            "stress_pnl": 90,
            "validation_pnl": 80,
            "holdout_pnl": 70,
            "walk_forward_stress_pnl": 60,
            "positive_wf_test_folds_pct": 0.95,
            "trades": 100,
            "active_days": 100,
            "best_day_concentration": 0.30,
            "best_trade_concentration": 0.20,
            "bootstrap_or_null_classification": "real_but_nontradable_signal",
        }
        self.assertEqual(signal_evidence_status(row), "real_but_nontradable_signal")
        self.assertEqual(tradability_status(row), "not_tradable_concentrated")
        row["best_day_concentration"] = 0.10
        row["best_trade_concentration"] = 0.05
        self.assertEqual(tradability_status(row), "review_packet_candidate")
        row["stress_pnl"] = -1
        self.assertEqual(signal_evidence_status(row), "no_signal")
        self.assertEqual(tradability_status(row), "not_tradable_negative")

    def test_build_registry_includes_audit_c_and_top_phase_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = build_research_signal_registry(out)
            registry = result["registry"]
            self.assertEqual(list(registry.columns), REGISTRY_COLUMNS)
            ids = set(registry["candidate_id"])
            self.assertTrue({"phase10b_top", "phase11a_top", "phase12a_top"}.issubset(ids))
            self.assertIn("phase10b_extra", ids)
            self.assertEqual(bool(result["recommendation"]["paper_trading_approved"]), False)
            self.assertEqual(bool(result["recommendation"]["official_gates_changed"]), False)

    def test_write_outputs_json_report_and_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "outputs"
            reports = root / "reports"
            out.mkdir()
            reports.mkdir()
            self._write_inputs(out)
            result = build_research_signal_registry(out)
            paths = write_registry_outputs(result, out, reports)
            self.assertTrue(paths["registry_csv"].exists())
            self.assertTrue(paths["registry_json"].exists())
            data = json.loads(paths["registry_json"].read_text(encoding="utf-8"))
            self.assertEqual(len(data), len(result["registry"]))
            report = render_registry_report(result["registry"], result["recommendation"])
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("No candidate is approved for paper trading", report)

    def _write_inputs(self, out: Path) -> None:
        audit_c = pd.DataFrame([
            self._candidate("phase10b", "phase10b_top", 1, "real_but_nontradable_signal", 100, 90, 80, 70, 60, 0.30, 0.20, 100, 100),
            self._candidate("phase11a", "phase11a_top", 2, "real_but_nontradable_signal", 70, 60, 50, 40, 30, 0.25, 0.18, 90, 90),
            self._candidate("phase12a", "phase12a_top", 3, "real_but_nontradable_signal", 60, 50, 40, 30, 20, 0.22, 0.15, 50, 50),
            self._candidate("phase10b", "phase10b_extra", 4, "weak_research_signal", 30, 20, -1, 10, 10, 0.12, 0.07, 80, 80),
        ])
        audit_c.to_csv(out / "framework_audit_c_candidate_selection.csv", index=False)
        audit_c[["phase", "candidate_id"]].assign(positive_without_best_trade=True, positive_without_top3_trades=True).to_csv(out / "framework_audit_c_outlier_removal_summary.csv", index=False)
        audit_c[["phase", "candidate_id"]].assign(all_bootstrap_positive_prob_min=0.8).to_csv(out / "framework_audit_c_gate_probability_summary.csv", index=False)
        audit_c[["phase", "candidate_id"]].assign(beats_phase_stress_75th=True).to_csv(out / "framework_audit_c_null_baseline_summary.csv", index=False)
        pd.DataFrame([{"phase": "phase10b", "candidates": 2}]).to_csv(out / "framework_audit_c_family_comparison.csv", index=False)
        (out / "framework_audit_c_next_action_recommendation.json").write_text(json.dumps({"next_action": "create_two_tier_research_signal_labeling"}), encoding="utf-8")
        audit_b = audit_c.rename(columns={"phase_label": "label", "audit_c_classification": "interpretation"})
        audit_b.to_csv(out / "framework_audit_b_research_signal_summary.csv", index=False)
        (out / "framework_audit_b_next_action_recommendation.json").write_text(json.dumps({"next_action": "separate_rare_setup_research_track"}), encoding="utf-8")
        for phase in ("phase10b", "phase11a", "phase12a"):
            audit_c[audit_c["phase"].eq(phase)].to_csv(out / f"{phase}_candidate_results.csv", index=False)

    def _candidate(self, phase: str, candidate_id: str, rank: int, classification: str, net: float, stress: float, validation: float, holdout: float, wf: float, day: float, trade: float, trades: int, active: int) -> dict[str, object]:
        return {
            "audit_c_rank": rank,
            "phase": phase,
            "candidate_id": candidate_id,
            "selected_reason": "recommendation_top_candidate" if candidate_id.endswith("top") else "positive_stress_validation_holdout_wf",
            "phase_rank": rank,
            "phase_score": net,
            "phase_label": f"{phase}_rejected_fold_instability",
            "research_axis_status": "axis_positive_but_concentrated",
            "net_pnl": net,
            "stress_pnl": stress,
            "validation_pnl": validation,
            "holdout_pnl": holdout,
            "walk_forward_stress_pnl": wf,
            "positive_wf_test_folds_pct": 0.95,
            "trades": trades,
            "active_days": active,
            "best_day_concentration": day,
            "best_trade_concentration": trade,
            "reject_reasons": "fold instability; concentration",
            "audit_c_classification": classification,
        }


if __name__ == "__main__":
    unittest.main()
