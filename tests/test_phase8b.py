from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8b import Phase8BConfig, render_phase8b_report, synthesize_phase8b_failures


class Phase8BFailureSynthesisTests(unittest.TestCase):
    def test_synthesize_phase8b_failures_prioritizes_structural_no_trade_axis(self) -> None:
        phase7c = pd.DataFrame(
            [
                {"axis": "optimization objective", "severity": "high"},
                {"axis": "phase and lockout policy", "severity": "high"},
                {"axis": "same-bar ambiguity", "severity": "high"},
                {"axis": "cost and slippage stress", "severity": "medium"},
            ]
        )
        phase7d = pd.DataFrame(
            [
                {
                    "success": False,
                    "phase7d_notes": "max-loss breach before payout objective; same-bar ambiguity remains; still not promotable",
                },
                {
                    "success": False,
                    "phase7d_notes": "passes evaluation but does not reach payout threshold; same-bar ambiguity remains; still not promotable",
                },
            ]
        )
        phase8a = pd.DataFrame(
            [
                {
                    "candidate_id": "candidate_a",
                    "family": "opening_range_breakout",
                    "phase8a_label": "rejected",
                    "phase8a_notes": "fails aggregate 4-tick slippage stress; one-day concentration risk; drawdown exceeds Phase 8A cap; negative holdout split",
                    "net_pnl": -100.0,
                    "validation_pnl": 25.0,
                    "holdout_pnl": -50.0,
                    "slippage_4_ticks_net_pnl": -300.0,
                    "trades": 900,
                    "active_session_pct": 0.96,
                    "max_drawdown": -1500.0,
                    "best_day_concentration": 1.0,
                    "best_trade_concentration": 1.0,
                    "same_bar_stop_target_ambiguity_count": 0,
                },
                {
                    "candidate_id": "candidate_b",
                    "family": "vwap_reclaim_rejection",
                    "phase8a_label": "rejected",
                    "phase8a_notes": "fails aggregate 4-tick slippage stress; same-bar stop/target ambiguity remains; negative validation split; negative holdout split",
                    "net_pnl": -200.0,
                    "validation_pnl": -10.0,
                    "holdout_pnl": -20.0,
                    "slippage_4_ticks_net_pnl": -500.0,
                    "trades": 1700,
                    "active_session_pct": 0.98,
                    "max_drawdown": -2500.0,
                    "best_day_concentration": 1.0,
                    "best_trade_concentration": 1.0,
                    "same_bar_stop_target_ambiguity_count": 11,
                },
            ]
        )
        manifest = {"selected_specs_count": 12, "result_row_count": 2, "label_counts": {"rejected": 2}}

        result = synthesize_phase8b_failures(phase7c, phase7d, phase8a, phase8a_manifest=manifest)
        summary = result.failure_summary.set_index("failure_category")

        self.assertEqual(result.phase7c_high_severity_count, 3)
        self.assertEqual(result.phase7d_success_count, 0)
        self.assertEqual(result.phase8a_scored_count, 2)
        self.assertEqual(result.phase8a_selected_specs_count, 12)
        self.assertEqual(result.phase8a_label_counts, {"rejected": 2})
        self.assertGreaterEqual(int(summary.loc["concentration", "total_count"]), 4)
        self.assertGreaterEqual(int(summary.loc["cost_slippage", "total_count"]), 3)
        self.assertGreaterEqual(int(summary.loc["drawdown", "total_count"]), 3)
        self.assertGreaterEqual(int(summary.loc["ambiguity", "total_count"]), 4)
        self.assertGreaterEqual(int(summary.loc["overtrading", "total_count"]), 2)
        self.assertGreaterEqual(int(summary.loc["split_instability", "total_count"]), 3)
        self.assertNotIn("other", summary.index)
        self.assertIn("phase8c_no_trade_session_filters", result.recommended_next_step)
        self.assertIn("Stop entry-variant grinding", result.decision)

    def test_render_phase8b_report_records_sources_guardrails_and_decision(self) -> None:
        result = synthesize_phase8b_failures(
            pd.DataFrame([{"axis": "same-bar ambiguity", "severity": "high"}]),
            pd.DataFrame([{"success": False, "phase7d_notes": "max-loss breach before payout objective"}]),
            pd.DataFrame(
                [
                    {
                        "candidate_id": "candidate_a",
                        "family": "opening_range_breakout",
                        "phase8a_label": "rejected",
                        "phase8a_notes": "fails aggregate 4-tick slippage stress; one-day concentration risk; negative holdout split",
                        "net_pnl": -100.0,
                        "validation_pnl": 5.0,
                        "holdout_pnl": -50.0,
                        "slippage_4_ticks_net_pnl": -300.0,
                        "trades": 900,
                        "active_session_pct": 0.96,
                        "max_drawdown": -1500.0,
                        "best_day_concentration": 1.0,
                        "best_trade_concentration": 1.0,
                        "same_bar_stop_target_ambiguity_count": 0,
                    }
                ]
            ),
            phase8a_manifest={"selected_specs_count": 12, "label_counts": {"rejected": 1}},
        )
        config = Phase8BConfig()
        report = render_phase8b_report(
            result,
            config,
            summary_path=Path("outputs/phase8b_failure_summary.csv"),
            report_path=Path("reports/phase8b_failure_synthesis_report.md"),
            run_artifact_dir=Path("artifacts/phase8b_failure_synthesis/test-run"),
        )

        self.assertIn("# Phase 8B MGC Failure Synthesis Report", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("Phase 7C high-severity drift axes: `1`", report)
        self.assertIn("Phase 7D successful payout-path rows: `0 / 1`", report)
        self.assertIn("Phase 8A scored clean-family specs: `1 / 12`", report)
        self.assertIn("phase8c_no_trade_session_filters", report)
        self.assertIn("Stop entry-variant grinding", report)
        self.assertIn("outputs/phase7c_assumption_drift.csv", report)
        self.assertIn("outputs/phase7d_payout_diagnostic_results.csv", report)
        self.assertIn("outputs/phase8a_mgc_clean_family_results.csv", report)
        self.assertIn("./.venv/Scripts/python.exe scripts/run_phase8b_failure_synthesis.py", report)
        self.assertIn("artifacts/phase8b_failure_synthesis/test-run", report)

    def test_phase8b_result_serializes_manifest_payload(self) -> None:
        result = synthesize_phase8b_failures(
            pd.DataFrame([{"axis": "data window", "severity": "high"}]),
            pd.DataFrame([{"success": False, "phase7d_notes": "does not pass evaluation target"}]),
            pd.DataFrame([{"candidate_id": "candidate_a", "family": "prior_session_levels", "phase8a_label": "rejected", "phase8a_notes": "negative holdout split"}]),
            phase8a_manifest={"selected_specs_count": 12, "label_counts": {"rejected": 1}},
        )

        payload = result.to_manifest_payload()
        json.dumps(payload)

        self.assertEqual(payload["phase7c_high_severity_count"], 1)
        self.assertEqual(payload["phase7d_success_count"], 0)
        self.assertEqual(payload["phase8a_scored_count"], 1)
        self.assertEqual(payload["phase8a_selected_specs_count"], 12)
        self.assertIn("recommended_next_step", payload)


if __name__ == "__main__":
    unittest.main()
