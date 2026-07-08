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

from short_term_edge.framework_audit_b import (  # noqa: E402
    OFFICIAL_GATES,
    FrameworkAuditBConfig,
    load_phase_outputs,
    render_framework_audit_b_report,
    run_framework_audit_b,
)


class FrameworkAuditBTests(unittest.TestCase):
    def test_audit_loads_phase_outputs_and_handles_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_phase(out, "phase10b", net=100, stress=90, validation=80, holdout=70, wf=60)
            loaded = load_phase_outputs(out, ("phase10b",))
            self.assertIn("phase10b", loaded)
            self.assertEqual(len(loaded["phase10b"]["candidate_results"]), 2)
            (out / "phase10b_trade_logs.csv").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "phase10b"):
                load_phase_outputs(out, ("phase10b",))

    def test_cost_waterfall_reconciles_and_top_candidate_matches_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_all_phases(out)
            result = run_framework_audit_b(out)
            cost = result["cost_waterfall_summary"]
            row = cost[cost["candidate_id"].eq("phase10b_top")].iloc[0]
            self.assertEqual(float(row["gross_to_net_drag"]), 20.0)
            self.assertEqual(float(row["net_to_stress_drag"]), 10.0)
            summary = result["research_signal_summary"]
            self.assertIn("phase10b_top", set(summary["candidate_id"]))
            self.assertIn("phase11a_top", set(summary["candidate_id"]))
            self.assertIn("phase12a_top", set(summary["candidate_id"]))

    def test_gate_sensitivity_is_deterministic_and_official_gates_unchanged(self) -> None:
        before = dict(OFFICIAL_GATES)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_all_phases(out)
            first = run_framework_audit_b(out, FrameworkAuditBConfig())["gate_sensitivity"]
            second = run_framework_audit_b(out, FrameworkAuditBConfig())["gate_sensitivity"]
            pd.testing.assert_frame_equal(first, second)
            relaxed = first[first["gate_type"].eq("best_day_concentration") & first["threshold"].eq(0.25)].iloc[0]
            strict = first[first["gate_type"].eq("best_day_concentration") & first["threshold"].eq(0.15)].iloc[0]
            self.assertGreaterEqual(int(relaxed["pass_count"]), int(strict["pass_count"]))
        self.assertEqual(OFFICIAL_GATES, before)

    def test_removing_best_day_and_trade_recomputes_pnl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_all_phases(out)
            dep = run_framework_audit_b(out)["top_trade_day_dependency"]
            row = dep[dep["candidate_id"].eq("phase10b_top")].iloc[0]
            self.assertEqual(float(row["pnl_without_best_day"]), 40.0)
            self.assertEqual(float(row["pnl_without_best_trade"]), 40.0)
            self.assertEqual(float(row["pnl_without_top3_trades"]), -10.0)

    def test_no_new_strategy_signals_and_report_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_all_phases(out)
            result = run_framework_audit_b(out)
            report = render_framework_audit_b_report(result, Path("reports/framework_audit_b_report.md"))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertNotIn("signal_time", " ".join(result["research_signal_summary"].columns))
            self.assertIn(result["next_action_recommendation"]["next_action"], {
                "pause_strategy_search_and_review_framework",
                "preserve_as_priority_research_signal_for_more_data",
                "create_two_tier_labeling_system",
                "revisit_cost_slippage_assumptions",
                "separate_rare_setup_research_track",
            })

    def _write_all_phases(self, out: Path) -> None:
        self._write_phase(out, "phase10b", net=100, stress=90, validation=80, holdout=70, wf=60, best_day=0.6, best_trade=0.3, active_days=80)
        self._write_phase(out, "phase11a", net=50, stress=40, validation=30, holdout=20, wf=10, best_day=0.4, best_trade=0.2, active_days=55)
        self._write_phase(out, "phase12a", net=-10, stress=-20, validation=10, holdout=5, wf=-5, best_day=1.0, best_trade=1.0, active_days=20)

    def _write_phase(self, out: Path, phase: str, *, net: float, stress: float, validation: float, holdout: float, wf: float, best_day: float = 0.2, best_trade: float = 0.1, active_days: int = 80) -> None:
        label = f"{phase}_label"
        rank = f"{phase}_rank"
        candidates = pd.DataFrame([
            {
                rank: 1,
                "candidate_id": f"{phase}_top",
                "gross_pnl": net + 20,
                "fees_only_pnl": net,
                "normal_slippage_pnl": net,
                "net_pnl": net,
                "stress_pnl": stress,
                "validation_pnl": validation,
                "holdout_pnl": holdout,
                "walk_forward_stress_pnl": wf,
                "walk_forward_test_pnl": wf + 5,
                "positive_wf_test_folds_pct": 0.833333,
                "worst_wf_test_fold": -25,
                "trades": active_days,
                "active_days": active_days,
                "trades_per_active_day": 1.0,
                "max_drawdown": -100,
                "best_day_concentration": best_day,
                "best_trade_concentration": best_trade,
                "avg_mfe": 10,
                "avg_mae": 5,
                label: f"{phase}_rejected_fold_instability",
                "research_axis_status": "axis_positive_but_concentrated" if stress > 0 else "axis_failed",
                "reject_reasons": "fold instability; concentration",
            },
            {
                rank: 2,
                "candidate_id": f"{phase}_other",
                "gross_pnl": -5,
                "fees_only_pnl": -10,
                "normal_slippage_pnl": -10,
                "net_pnl": -10,
                "stress_pnl": -12,
                "validation_pnl": -1,
                "holdout_pnl": -1,
                "walk_forward_stress_pnl": -2,
                "walk_forward_test_pnl": -1,
                "positive_wf_test_folds_pct": 0.0,
                "worst_wf_test_fold": -50,
                "trades": 5,
                "active_days": 5,
                "trades_per_active_day": 1.0,
                "max_drawdown": -50,
                "best_day_concentration": 1.0,
                "best_trade_concentration": 1.0,
                "avg_mfe": 1,
                "avg_mae": 2,
                label: f"{phase}_rejected_negative_stress",
                "research_axis_status": "axis_failed",
                "reject_reasons": "negative stress",
            },
        ])
        candidates.to_csv(out / f"{phase}_candidate_results.csv", index=False)
        trades = pd.DataFrame([
            {"candidate_id": f"{phase}_top", "trading_session": "2026-01-01", "net_pnl": 60, "stress_pnl": 55},
            {"candidate_id": f"{phase}_top", "trading_session": "2026-01-02", "net_pnl": 30, "stress_pnl": 25},
            {"candidate_id": f"{phase}_top", "trading_session": "2026-01-03", "net_pnl": 20, "stress_pnl": 15},
            {"candidate_id": f"{phase}_top", "trading_session": "2026-01-03", "net_pnl": -10, "stress_pnl": -12},
        ])
        trades.to_csv(out / f"{phase}_trade_logs.csv", index=False)
        pd.DataFrame([
            {"candidate_id": f"{phase}_top", "fold": 1, "net_pnl": 70, "stress_pnl": 65, "trades": 10},
            {"candidate_id": f"{phase}_top", "fold": 2, "net_pnl": -10, "stress_pnl": -5, "trades": 5},
        ]).to_csv(out / f"{phase}_walk_forward_folds.csv", index=False)
        trades.groupby(["candidate_id", "trading_session"]).agg(trades=("net_pnl", "size"), net_pnl=("net_pnl", "sum"), stress_pnl=("stress_pnl", "sum")).reset_index().to_csv(out / f"{phase}_daily_pnl.csv", index=False)
        trades.groupby(["candidate_id", "trading_session"]).agg(pnl=("net_pnl", "sum"), trades=("net_pnl", "size")).reset_index().to_csv(out / f"{phase}_concentration_diagnostics.csv", index=False)
        (out / f"{phase}_next_action_recommendation.json").write_text(json.dumps({"next_action": "park", "top_candidate": {"candidate_id": f"{phase}_top"}}), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
