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

from short_term_edge.portfolio_audit_e import (  # noqa: E402
    OFFICIAL_GATES,
    PHASE_PRIORITY,
    build_daily_pnl_matrix,
    construct_portfolio_trades,
    incremental_active_days,
    load_portfolio_audit_e_inputs,
    rare_module_contribution_summary,
    render_portfolio_audit_e_report,
    run_portfolio_audit_e,
    select_portfolio_e_modules,
    signal_correlation,
    weak_regime_coverage_summary,
)


class PortfolioAuditETests(unittest.TestCase):
    def test_loads_policy_registry_phase16a_and_selects_all_three_with_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_portfolio_audit_e_inputs(out)
            selected = select_portfolio_e_modules(data)
            phase16 = selected[selected["phase"].eq("phase16a")]
            self.assertTrue(data["rare_policy"]["rare_module_track_enabled"])
            self.assertEqual(len(data["module_registry_csv"][data["module_registry_csv"]["phase"].eq("phase16a")]), 3)
            self.assertEqual(set(phase16["candidate_id"]), {"p16a_a", "p16a_b", "p16a_c"})
            self.assertLessEqual(len(selected), 32)
            pd.testing.assert_frame_equal(selected, select_portfolio_e_modules(data))

    def test_daily_matrix_correlation_and_raw_sum_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_portfolio_audit_e_inputs(out)
            selected = select_portfolio_e_modules(data)
            matrix = build_daily_pnl_matrix(data, selected)
            self.assertEqual(list(matrix["trading_session"]), ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06", "2026-01-07"])
            corr = signal_correlation(matrix)
            pd.testing.assert_frame_equal(corr, signal_correlation(matrix))
            result = run_portfolio_audit_e(out)
            raw = result["portfolio_daily_pnl"]
            raw = raw[(raw["portfolio_set"].eq("phase16a_only")) & (raw["portfolio_mode"].eq("raw_sum_diagnostic"))]
            keys = result["portfolio_results"][(result["portfolio_results"]["portfolio_set"].eq("phase16a_only")) & (result["portfolio_results"]["portfolio_mode"].eq("raw_sum_diagnostic"))].iloc[0]["signal_keys"].split(";")
            cols = [key for key in keys if key in matrix.columns]
            self.assertAlmostEqual(float(raw["net_pnl"].sum()), float(matrix[cols].sum(axis=1).sum()))

    def test_overlap_and_session_rules_use_phase16a_priority(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b::a", "phase10b", "a", "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", 10),
            self._trade("phase15a::b", "phase15a", "b", "2026-01-01 09:30", "2026-01-01 09:45", "2026-01-01", 20),
            self._trade("phase16a::c", "phase16a", "c", "2026-01-01 09:30", "2026-01-01 09:35", "2026-01-01", 30),
            self._trade("phase12a::d", "phase12a", "d", "2026-01-02 09:30", "2026-01-02 10:00", "2026-01-02", 40),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col])
        keys = trades["signal_key"].tolist()
        accepted, skipped_overlap, _ = construct_portfolio_trades(trades, keys, "one_trade_at_a_time_chronological")
        self.assertEqual(accepted.iloc[0]["phase"], "phase16a")
        self.assertEqual(skipped_overlap, 2)
        accepted_session, _, skipped_session = construct_portfolio_trades(trades, keys, "max_one_trade_per_session")
        self.assertEqual(len(accepted_session), 2)
        self.assertEqual(skipped_session, 2)
        self.assertLessEqual(accepted_session.groupby("trading_session").size().max(), 1)

    def test_incremental_rare_weak_gates_paper_guardrail_and_no_new_signals(self) -> None:
        before = dict(OFFICIAL_GATES)
        existing = pd.DataFrame([{"trading_session": "2026-01-01"}])
        phase16 = pd.DataFrame([{"trading_session": "2026-01-01"}, {"trading_session": "2026-01-03"}])
        self.assertEqual(incremental_active_days(existing, phase16), 1)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_portfolio_audit_e(out)
            self.assertFalse(bool(result["portfolio_results"]["paper_trading_approved"].any()))
            self.assertFalse(bool(result["next_action_recommendation"]["paper_trading_approved"]))
            rare_again = rare_module_contribution_summary(result["signal_selection"], result["portfolio_results"], self._selected_trades_for_result(out, result))
            self.assertEqual(list(result["rare_module_contribution_summary"]["signal_key"]), list(rare_again["signal_key"]))
            weak_again = weak_regime_coverage_summary(result["portfolio_results"], result["daily_pnl_matrix"], load_portfolio_audit_e_inputs(out))
            pd.testing.assert_frame_equal(result["weak_regime_coverage_summary"], weak_again)
            report = render_portfolio_audit_e_report(result, Path("reports/portfolio_audit_e_report.md"))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("does not generate signals", report)
            self.assertNotIn("signal_time", " ".join(result["signal_selection"].columns))
        self.assertEqual(OFFICIAL_GATES, before)

    def _selected_trades_for_result(self, out: Path, result: dict) -> pd.DataFrame:
        from short_term_edge.portfolio_audit_e import load_portfolio_audit_e_inputs, selected_trade_logs

        return selected_trade_logs(load_portfolio_audit_e_inputs(out), result["signal_selection"])

    def _write_inputs(self, out: Path) -> None:
        modules = pd.DataFrame([
            self._module("phase10b", "p10", "parked_research_signal", "parked_module", 100),
            self._module("phase11a", "p11", "parked_research_signal", "parked_module", 90),
            self._module("phase12a", "p12", "rare_setup_research_signal", "rare_setup_module", 80),
            self._module("phase13a", "p13a_a", "parked_research_signal", "diversifier_module", 70),
            self._module("phase13a", "p13a_b", "parked_research_signal", "diversifier_module", 60),
            self._module("phase14a", "p14a_a", "parked_research_signal", "diversifier_module", 50),
            self._module("phase14a", "p14a_b", "parked_research_signal", "diversifier_module", 40),
            self._module("phase15a", "p15a_a", "rare_setup_research_signal", "diversifier_module", 30),
            self._module("phase15a", "p15a_b", "rare_setup_research_signal", "diversifier_module", 20),
            self._module("phase15a", "p15a_c", "rare_setup_research_signal", "diversifier_module", 10),
            self._module("phase16a", "p16a_a", "rare_setup_research_signal", "diversifier_module", 35),
            self._module("phase16a", "p16a_b", "rare_setup_research_signal", "diversifier_module", 25),
            self._module("phase16a", "p16a_c", "rare_setup_research_signal", "diversifier_module", 15),
        ])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        (out / "playbook_module_registry.json").write_text(modules.to_json(orient="records"), encoding="utf-8")
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        (out / "research_signal_registry.json").write_text(modules.to_json(orient="records"), encoding="utf-8")
        for name, content in {
            "playbook_rare_module_policy.json": {"rare_module_track_enabled": True, "paper_trading_approved": False, "official_gates_changed": False},
            "playbook_rare_module_portfolio_audit_rules.json": {"include_rare_modules_as_diversifier_candidates": True},
            "playbook_framework_e_next_action_recommendation.json": {"next_action": "portfolio_audit_e_with_phase16a_rare_modules", "paper_trading_approved": False},
            "portfolio_audit_d_next_action_recommendation.json": {"next_action": "d", "paper_trading_approved": False},
            "playbook_scheduler_d_next_action_recommendation.json": {"next_action": "d", "paper_trading_approved": False},
            "playbook_scheduler_c_next_action_recommendation.json": {"next_action": "c", "paper_trading_approved": False},
        }.items():
            (out / name).write_text(json.dumps(content), encoding="utf-8")
        keys = ";".join(["phase10b::p10", "phase11a::p11", "phase12a::p12", "phase13a::p13a_a", "phase14a::p14a_a", "phase15a::p15a_a"])
        result_row = {"portfolio_set": "prior_best", "portfolio_mode": "max_one_trade_per_session", "signal_keys": keys, "net_pnl": 100, "active_days": 6, "official_gates_passed": False}
        for fname in ("portfolio_audit_d_portfolio_results.csv", "playbook_scheduler_d_overlay_policy_results.csv", "playbook_scheduler_c_pruning_policy_results.csv"):
            pd.DataFrame([result_row]).to_csv(out / fname, index=False)
        for fname in ("portfolio_audit_d_signal_selection.csv", "portfolio_audit_d_portfolio_daily_pnl.csv", "portfolio_audit_d_portfolio_walk_forward_folds.csv", "playbook_scheduler_d_daily_pnl.csv", "playbook_scheduler_d_walk_forward_folds.csv", "playbook_scheduler_d_concentration.csv", "playbook_scheduler_c_daily_pnl.csv", "playbook_scheduler_c_walk_forward_folds.csv", "playbook_scheduler_c_concentration.csv", "weak_fold_regime_audit_b_bad_day_clusters.csv", "weak_fold_regime_audit_b_regime_comparison.csv", "phase16a_gap_coverage_summary.csv"):
            pd.DataFrame([{"x": 1}]).to_csv(out / fname, index=False)
        pd.DataFrame([{"trading_session": "2026-01-03", "regime": "high_vol_mixed"}, {"trading_session": "2026-01-07", "regime": "high_vol_mixed"}]).to_csv(out / "weak_fold_regime_audit_b_market_regime_features.csv", index=False)
        pd.DataFrame([{"trading_session": "2026-01-03"}, {"trading_session": "2026-01-06"}]).to_csv(out / "weak_fold_regime_audit_b_weak_fold_days.csv", index=False)
        for phase in ("phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a", "phase16a"):
            cids = modules[modules["phase"].eq(phase)]["candidate_id"].tolist()
            pd.DataFrame([{"candidate_id": cid, "net_pnl": 1} for cid in cids]).to_csv(out / f"{phase}_candidate_results.csv", index=False)
            trades = []
            for cid in cids:
                trades.extend([
                    {"candidate_id": cid, "entry_time": "2026-01-01 09:30", "exit_time": "2026-01-01 10:00", "trading_session": "2026-01-01", "net_pnl": 10, "gross_pnl": 10, "stress_pnl": 9, "split": "validation"},
                    {"candidate_id": cid, "entry_time": "2026-01-02 09:30", "exit_time": "2026-01-02 10:00", "trading_session": "2026-01-02", "net_pnl": -5, "gross_pnl": -5, "stress_pnl": -6, "split": "holdout"},
                    {"candidate_id": cid, "entry_time": "2026-01-03 09:30", "exit_time": "2026-01-03 10:00", "trading_session": "2026-01-03", "net_pnl": 15, "gross_pnl": 15, "stress_pnl": 14, "split": "discovery"},
                ])
            pd.DataFrame(trades).to_csv(out / f"{phase}_trade_logs.csv", index=False)
            daily = pd.DataFrame(trades).groupby(["candidate_id", "trading_session"], as_index=False)["net_pnl"].sum()
            if phase == "phase13a":
                daily = pd.concat([daily, pd.DataFrame([{"candidate_id": cids[0], "trading_session": "2026-01-04", "net_pnl": 6}])], ignore_index=True)
            if phase == "phase14a":
                daily = pd.concat([daily, pd.DataFrame([{"candidate_id": cids[0], "trading_session": "2026-01-05", "net_pnl": 7}])], ignore_index=True)
            if phase == "phase15a":
                daily = pd.concat([daily, pd.DataFrame([{"candidate_id": cids[0], "trading_session": "2026-01-06", "net_pnl": 8}])], ignore_index=True)
            if phase == "phase16a":
                daily = pd.concat([daily, pd.DataFrame([{"candidate_id": cids[0], "trading_session": "2026-01-07", "net_pnl": 9}])], ignore_index=True)
            daily.to_csv(out / f"{phase}_daily_pnl.csv", index=False)
            pd.DataFrame([{"candidate_id": cid, "fold": 1, "net_pnl": 10, "stress_pnl": 9} for cid in cids]).to_csv(out / f"{phase}_walk_forward_folds.csv", index=False)

    def _module(self, phase: str, cid: str, track: str, role: str, net: float) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "market_condition": "mixed", "module_family": "breakout", "portfolio_role": role, "plain_english_rule": "rule", "signal_evidence_status": "positive_research_signal", "tradability_status": "not_tradable_low_activity", "research_track": track, "portfolio_contribution_status": "not_evaluated", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": net, "stress_pnl": net - 1, "validation_pnl": 10, "holdout_pnl": 5, "walk_forward_stress_pnl": 4, "positive_wf_test_folds_pct": 0.5, "trades": 3, "active_days": 3, "best_day_concentration": 0.3, "best_trade_concentration": 0.2, "fold_adequacy_status": "low_activity_not_fully_interpretable" if phase == "phase16a" else "not_available", "source_report": "report"}

    def _trade(self, key: str, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"signal_key": key, "phase": phase, "candidate_id": cid, "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "gross_pnl": pnl, "stress_pnl": pnl, "phase_priority": PHASE_PRIORITY[phase], "split": "validation"}


if __name__ == "__main__":
    unittest.main()
