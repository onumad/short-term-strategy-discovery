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

from short_term_edge.framework_audit_c_null_bootstrap import (  # noqa: E402
    OFFICIAL_GATES,
    FrameworkAuditCConfig,
    daily_bootstrap,
    gate_probability,
    load_framework_audit_c_inputs,
    null_baseline_for_values,
    outlier_removal_for_values,
    render_framework_audit_c_report,
    run_framework_audit_c,
    select_audit_c_candidates,
    trade_bootstrap,
)


class FrameworkAuditCNullBootstrapTests(unittest.TestCase):
    def test_loads_phase_outputs_and_candidate_selection_is_capped_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_all_phases(out)
            loaded = load_framework_audit_c_inputs(out)
            self.assertEqual(set(loaded), {"phase10b", "phase11a", "phase12a"})
            first = select_audit_c_candidates(loaded, max_candidates=4)
            second = select_audit_c_candidates(loaded, max_candidates=4)
            pd.testing.assert_frame_equal(first, second)
            self.assertLessEqual(len(first), 4)
            self.assertIn("phase10b_top", set(first["candidate_id"]))

    def test_trade_and_daily_bootstrap_are_deterministic(self) -> None:
        values = [10.0, -5.0, 15.0, -2.0]
        self.assertEqual(trade_bootstrap(values, iterations=200, seed=7), trade_bootstrap(values, iterations=200, seed=7))
        self.assertEqual(daily_bootstrap(values, iterations=200, seed=8), daily_bootstrap(values, iterations=200, seed=8))

    def test_outlier_removal_computes_correct_totals(self) -> None:
        result = outlier_removal_for_values(pd.Series([100, 25, -10, 5]), pd.Series([90, 20, 10]))
        self.assertEqual(result["net_pnl"], 120.0)
        self.assertEqual(result["pnl_without_best_trade"], 20.0)
        self.assertEqual(result["pnl_without_top3_trades"], -10.0)
        self.assertEqual(result["pnl_without_best_day"], 30.0)
        self.assertEqual(result["pnl_without_top3_days"], 0.0)

    def test_gate_probability_and_null_baseline_are_deterministic(self) -> None:
        summary = trade_bootstrap([10, 20, -5], iterations=200, seed=11)
        self.assertEqual(gate_probability(summary, pnl_threshold=0.1), gate_probability(summary, pnl_threshold=0.1))
        first = null_baseline_for_values(10, [1, 2, 10, 20])
        second = null_baseline_for_values(10, [1, 2, 10, 20])
        self.assertEqual(first, second)
        self.assertEqual(first["null_percentile"], 0.75)

    def test_run_audit_preserves_official_gates_no_strategy_signals_and_report_guardrail(self) -> None:
        before = dict(OFFICIAL_GATES)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_all_phases(out)
            result = run_framework_audit_c(out, FrameworkAuditCConfig(iterations=200, top3_iterations=200, max_candidates=6, use_top3_iterations=False))
            self.assertIn("candidate_selection", result)
            self.assertLessEqual(len(result["candidate_selection"]), 6)
            self.assertNotIn("signal_time", " ".join(result["candidate_selection"].columns))
            report = render_framework_audit_c_report(result, Path("reports/framework_audit_c_null_bootstrap_report.md"))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn(result["next_action_recommendation"]["next_action"], {
                "pause_strategy_search_and_review_framework",
                "preserve_priority_family_for_more_data",
                "create_two_tier_research_signal_labeling",
                "revise_research_labels_not_promotion_gates",
                "pause_strategy_search_and_build_null_baseline_framework",
            })
        self.assertEqual(OFFICIAL_GATES, before)

    def _write_all_phases(self, out: Path) -> None:
        self._write_phase(out, "phase10b", positive_count=4, stress=90, validation=80, holdout=70, wf=60)
        self._write_phase(out, "phase11a", positive_count=3, stress=55, validation=30, holdout=25, wf=20)
        self._write_phase(out, "phase12a", positive_count=2, stress=40, validation=20, holdout=10, wf=15)

    def _write_phase(self, out: Path, phase: str, *, positive_count: int, stress: float, validation: float, holdout: float, wf: float) -> None:
        label = f"{phase}_label"
        rank = f"{phase}_rank"
        score = f"{phase}_score"
        rows = []
        for idx in range(positive_count + 1):
            cid = f"{phase}_{'top' if idx == 0 else 'pos_' + str(idx)}"
            rows.append(
                {
                    rank: idx + 1,
                    "candidate_id": cid,
                    "side": "long" if idx % 2 else "short",
                    "gross_pnl": 130 - idx,
                    "fees_only_pnl": 110 - idx,
                    "normal_slippage_pnl": 100 - idx,
                    "net_pnl": 100 - idx,
                    "stress_pnl": stress - idx,
                    "validation_pnl": validation - idx,
                    "holdout_pnl": holdout - idx,
                    "walk_forward_stress_pnl": wf - idx,
                    "walk_forward_test_pnl": wf + 5 - idx,
                    "positive_wf_test_folds_pct": 0.833333,
                    "worst_wf_test_fold": -20,
                    "trades": 12,
                    "active_days": 12,
                    "trades_per_active_day": 1.0,
                    "max_drawdown": -50,
                    "best_day_concentration": 0.25,
                    "best_trade_concentration": 0.15,
                    label: f"{phase}_rejected_fold_instability",
                    "research_axis_status": "axis_positive_but_concentrated",
                    score: 1000 - idx,
                    "reject_reasons": "fold instability; concentration",
                }
            )
        pd.DataFrame(rows).to_csv(out / f"{phase}_candidate_results.csv", index=False)
        trades = []
        daily = []
        folds = []
        for row in rows:
            cid = row["candidate_id"]
            for n, pnl in enumerate([20, -5, 15, 10], start=1):
                session = f"2026-01-0{n}"
                trades.append({"candidate_id": cid, "trading_session": session, "side": row["side"], "net_pnl": pnl, "stress_pnl": pnl - 1})
                daily.append({"candidate_id": cid, "trading_session": session, "trades": 1, "net_pnl": pnl, "stress_pnl": pnl - 1})
            folds.extend([
                {"candidate_id": cid, "fold": 1, "net_pnl": 30, "stress_pnl": 28, "trades": 3},
                {"candidate_id": cid, "fold": 2, "net_pnl": -5, "stress_pnl": -6, "trades": 1},
            ])
        pd.DataFrame(trades).to_csv(out / f"{phase}_trade_logs.csv", index=False)
        pd.DataFrame(daily).to_csv(out / f"{phase}_daily_pnl.csv", index=False)
        pd.DataFrame(folds).to_csv(out / f"{phase}_walk_forward_folds.csv", index=False)
        (out / f"{phase}_next_action_recommendation.json").write_text(json.dumps({"next_action": "park", "top_candidate": {"candidate_id": f"{phase}_top"}}), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
