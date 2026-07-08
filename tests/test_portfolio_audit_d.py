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

from short_term_edge.portfolio_audit_d import (  # noqa: E402
    OFFICIAL_GATES,
    build_daily_pnl_matrix,
    concentration,
    construct_portfolio_trades,
    incremental_active_days,
    load_portfolio_audit_d_inputs,
    max_drawdown,
    phase13a_vs_phase14a_vs_phase15a_impact,
    render_portfolio_audit_d_report,
    run_portfolio_audit_d,
    select_portfolio_d_modules,
    signal_correlation,
)


class PortfolioAuditDTests(unittest.TestCase):
    def test_loads_registry_selects_phase13a_phase14a_phase15a_and_caps_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_portfolio_audit_d_inputs(out)
            selected = select_portfolio_d_modules(data)
            self.assertEqual(len(data["module_registry_csv"]), 10)
            self.assertLessEqual(len(selected), 28)
            self.assertEqual(set(selected[selected["phase"].eq("phase13a")]["candidate_id"]), {"p13a_a", "p13a_b"})
            self.assertEqual(set(selected[selected["phase"].eq("phase14a")]["candidate_id"]), {"p14a_a", "p14a_b"})
            self.assertEqual(set(selected[selected["phase"].eq("phase15a")]["candidate_id"]), {"p15a_a", "p15a_b", "p15a_c"})
            pd.testing.assert_frame_equal(selected, select_portfolio_d_modules(data))

    def test_daily_matrix_correlation_and_raw_sum_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_portfolio_audit_d_inputs(out)
            selected = select_portfolio_d_modules(data)
            matrix = build_daily_pnl_matrix(data, selected)
            self.assertEqual(list(matrix["trading_session"]), ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"])
            corr = signal_correlation(matrix)
            pd.testing.assert_frame_equal(corr, signal_correlation(matrix))
            result = run_portfolio_audit_d(out)
            raw = result["portfolio_daily_pnl"]
            raw = raw[(raw["portfolio_set"].eq("top_cross_family_plus_13a_14a_15a")) & (raw["portfolio_mode"].eq("raw_sum_diagnostic"))]
            keys = result["portfolio_results"][(result["portfolio_results"]["portfolio_set"].eq("top_cross_family_plus_13a_14a_15a")) & (result["portfolio_results"]["portfolio_mode"].eq("raw_sum_diagnostic"))].iloc[0]["signal_keys"].split(";")
            cols = [key for key in keys if key in matrix.columns]
            self.assertAlmostEqual(float(raw["net_pnl"].sum()), float(matrix[cols].sum(axis=1).sum()))

    def test_overlap_session_and_phase15a_priority(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b::a", "phase10b", "a", "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", 10),
            self._trade("phase13a::b", "phase13a", "b", "2026-01-01 09:30", "2026-01-01 09:45", "2026-01-01", 20),
            self._trade("phase14a::c", "phase14a", "c", "2026-01-01 09:30", "2026-01-01 09:40", "2026-01-01", 30),
            self._trade("phase15a::d", "phase15a", "d", "2026-01-01 09:30", "2026-01-01 09:35", "2026-01-01", 40),
            self._trade("phase12a::e", "phase12a", "e", "2026-01-02 09:30", "2026-01-02 10:00", "2026-01-02", 50),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col])
        accepted, skipped_overlap, _ = construct_portfolio_trades(trades, ["phase10b::a", "phase13a::b", "phase14a::c", "phase15a::d", "phase12a::e"], "one_trade_at_a_time_chronological")
        self.assertEqual(accepted.iloc[0]["phase"], "phase15a")
        self.assertEqual(skipped_overlap, 3)
        accepted_session, _, skipped_session = construct_portfolio_trades(trades, ["phase10b::a", "phase13a::b", "phase14a::c", "phase15a::d", "phase12a::e"], "max_one_trade_per_session")
        self.assertEqual(len(accepted_session), 2)
        self.assertEqual(skipped_session, 3)
        self.assertLessEqual(accepted_session.groupby("trading_session").size().max(), 1)

    def test_incremental_comparison_concentration_drawdown_gates_report_and_no_signals(self) -> None:
        before = dict(OFFICIAL_GATES)
        existing = pd.DataFrame([{"trading_session": "2026-01-01"}])
        phase15 = pd.DataFrame([{"trading_session": "2026-01-01"}, {"trading_session": "2026-01-03"}])
        self.assertEqual(incremental_active_days(existing, phase15), 1)
        self.assertEqual(concentration(pd.Series([80, 20, -10]))["best"], 0.888889)
        self.assertEqual(max_drawdown(pd.Series([10, -15, 5, -20])), -30.0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_portfolio_audit_d(out)
            self.assertFalse(bool(result["portfolio_results"]["paper_trading_approved"].any()))
            compare = result["phase13a_vs_phase14a_vs_phase15a_impact"]
            pd.testing.assert_frame_equal(compare, phase13a_vs_phase14a_vs_phase15a_impact(result["portfolio_results"]))
            report = render_portfolio_audit_d_report(result, Path("reports/portfolio_audit_d_report.md"))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("does not generate signals", report)
            self.assertNotIn("signal_time", " ".join(result["signal_selection"].columns))
        self.assertEqual(OFFICIAL_GATES, before)

    def _write_inputs(self, out: Path) -> None:
        modules = pd.DataFrame([
            self._module("phase10b", "p10", "parked_research_signal", "parked_module", 100),
            self._module("phase11a", "p11", "parked_research_signal", "parked_module", 90),
            self._module("phase12a", "p12", "rare_setup_research_signal", "rare_setup_module", 80),
            self._module("phase13a", "p13a_a", "parked_research_signal", "diversifier_module", 70),
            self._module("phase13a", "p13a_b", "parked_research_signal", "diversifier_module", 60),
            self._module("phase14a", "p14a_a", "parked_research_signal", "diversifier_module", 50),
            self._module("phase14a", "p14a_b", "parked_research_signal", "diversifier_module", 40),
            self._module("phase15a", "p15a_a", "parked_research_signal", "diversifier_module", 30),
            self._module("phase15a", "p15a_b", "parked_research_signal", "diversifier_module", 20),
            self._module("phase15a", "p15a_c", "parked_research_signal", "diversifier_module", 10),
        ])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        (out / "playbook_module_registry.json").write_text(modules.to_json(orient="records"), encoding="utf-8")
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        (out / "research_signal_registry.json").write_text(modules.to_json(orient="records"), encoding="utf-8")
        (out / "research_signal_registry_d_next_action_recommendation.json").write_text(json.dumps({"next_action": "portfolio_audit_d"}), encoding="utf-8")
        pd.DataFrame([{"portfolio_set": "audit_c_prior_best", "portfolio_mode": "raw_sum_diagnostic", "signal_keys": "phase10b::p10;phase11a::p11", "net_pnl": 10, "active_days": 3, "official_gates_passed": False}]).to_csv(out / "portfolio_audit_c_portfolio_results.csv", index=False)
        for name in ("portfolio_audit_c_signal_selection", "portfolio_audit_c_signal_correlation", "portfolio_audit_c_daily_pnl_matrix", "portfolio_audit_c_portfolio_daily_pnl", "portfolio_audit_c_portfolio_walk_forward_folds", "portfolio_audit_c_incremental", "portfolio_audit_c_phase14a_diversifier_impact", "portfolio_audit_c_phase13a_vs_phase14a_impact"):
            fname = "portfolio_audit_c_incremental_contribution" if name.endswith("incremental") else name
            pd.DataFrame([{"x": 1, "active_days_delta": 1, "fold_delta": 0, "best_day_concentration_delta": -0.1}]).to_csv(out / f"{fname}.csv", index=False)
        (out / "portfolio_audit_c_next_action_recommendation.json").write_text(json.dumps({"next_action": "c", "paper_trading_approved": False}), encoding="utf-8")
        for phase in ("phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a"):
            cids = modules[modules["phase"].eq(phase)]["candidate_id"].tolist()
            pd.DataFrame([{"candidate_id": cid, "net_pnl": 1} for cid in cids]).to_csv(out / f"{phase}_candidate_results.csv", index=False)
            trades = []
            for cid in cids:
                trades.extend([
                    {"candidate_id": cid, "entry_time": "2026-01-01 09:30", "exit_time": "2026-01-01 10:00", "trading_session": "2026-01-01", "net_pnl": 10, "gross_pnl": 10, "stress_pnl": 9, "split": "validation"},
                    {"candidate_id": cid, "entry_time": "2026-01-02 09:30", "exit_time": "2026-01-02 10:00", "trading_session": "2026-01-02", "net_pnl": -5, "gross_pnl": -5, "stress_pnl": -6, "split": "holdout"},
                    {"candidate_id": cid, "entry_time": "2026-01-04 09:30", "exit_time": "2026-01-04 10:00", "trading_session": "2026-01-04", "net_pnl": 15, "gross_pnl": 15, "stress_pnl": 14, "split": "discovery"},
                ])
            pd.DataFrame(trades).to_csv(out / f"{phase}_trade_logs.csv", index=False)
            daily = pd.DataFrame(trades).groupby(["candidate_id", "trading_session"], as_index=False)["net_pnl"].sum()
            if phase == "phase13a":
                daily = pd.concat([daily, pd.DataFrame([{"candidate_id": cids[0], "trading_session": "2026-01-03", "net_pnl": 6}])], ignore_index=True)
            if phase == "phase14a":
                daily = pd.concat([daily, pd.DataFrame([{"candidate_id": cids[0], "trading_session": "2026-01-05", "net_pnl": 7}])], ignore_index=True)
            if phase == "phase15a":
                daily = pd.concat([daily, pd.DataFrame([{"candidate_id": cids[0], "trading_session": "2026-01-06", "net_pnl": 8}])], ignore_index=True)
            daily.to_csv(out / f"{phase}_daily_pnl.csv", index=False)
            pd.DataFrame([{"candidate_id": cid, "fold": 1, "net_pnl": 10, "stress_pnl": 9} for cid in cids]).to_csv(out / f"{phase}_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"candidate_id": "p15a_a", "family": "trend", "average_correlation_to_registry": 0.1, "max_correlation_to_registry": 0.2}]).to_csv(out / "phase15a_correlation_to_registry.csv", index=False)
        pd.DataFrame([{"candidate_id": "p15a_a", "family": "trend", "average_correlation_to_playbook": 0.1, "max_correlation_to_playbook": 0.2}]).to_csv(out / "phase15a_correlation_to_playbook.csv", index=False)
        pd.DataFrame([{"family": "trend_power", "max_incremental_gap_days_covered": 1}]).to_csv(out / "phase15a_gap_coverage_summary.csv", index=False)

    def _module(self, phase: str, cid: str, track: str, role: str, net: float) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "market_condition": "trend_power", "module_family": "breakout", "portfolio_role": role, "plain_english_rule": "rule", "signal_evidence_status": "positive_research_signal", "tradability_status": "not_tradable_concentrated", "research_track": track, "portfolio_contribution_status": "not_evaluated", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": net, "stress_pnl": net - 1, "validation_pnl": 10, "holdout_pnl": 5, "walk_forward_stress_pnl": 4, "positive_wf_test_folds_pct": 0.5, "trades": 3, "active_days": 3, "best_day_concentration": 0.3, "best_trade_concentration": 0.2, "source_report": "report"}

    def _trade(self, key: str, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"signal_key": key, "phase": phase, "candidate_id": cid, "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "gross_pnl": pnl, "stress_pnl": pnl, "phase_priority": {"phase15a": 0, "phase14a": 1, "phase13a": 2, "phase10b": 3, "phase11a": 4, "phase12a": 5}[phase], "split": "validation"}


if __name__ == "__main__":
    unittest.main()
