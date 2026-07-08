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

from short_term_edge.portfolio_audit_a import (  # noqa: E402
    OFFICIAL_GATES,
    build_daily_pnl_matrix,
    concentration,
    construct_portfolio_trades,
    load_portfolio_audit_inputs,
    max_drawdown,
    render_portfolio_audit_report,
    run_portfolio_audit_a,
    select_portfolio_signals,
    signal_correlation,
)


class PortfolioAuditATests(unittest.TestCase):
    def test_loads_registry_and_phase_trade_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_portfolio_audit_inputs(out)
            self.assertEqual(len(data["registry_csv"]), 4)
            self.assertEqual(len(data["phase10b_trades"]), 6)

    def test_candidate_selection_is_deterministic_and_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_portfolio_audit_inputs(out)
            first = select_portfolio_signals(data)
            second = select_portfolio_signals(data)
            pd.testing.assert_frame_equal(first, second)
            self.assertLessEqual(len(first), 20)
            self.assertTrue({"phase10b_top", "phase11a_top", "phase12a_top"}.issubset(set(first["candidate_id"])))

    def test_daily_matrix_correlation_and_raw_sum_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_portfolio_audit_inputs(out)
            selected = select_portfolio_signals(data)
            matrix = build_daily_pnl_matrix(data, selected)
            self.assertEqual(list(matrix["trading_session"]), ["2026-01-01", "2026-01-02", "2026-01-03"])
            corr = signal_correlation(matrix)
            pd.testing.assert_frame_equal(corr, signal_correlation(matrix))
            cols = [c for c in matrix.columns if c != "trading_session"]
            self.assertAlmostEqual(float(matrix[cols].sum(axis=1).sum()), 80.0)

    def test_overlap_and_one_trade_per_session_rules(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b::a", "phase10b", "a", "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", 10),
            self._trade("phase11a::b", "phase11a", "b", "2026-01-01 09:45", "2026-01-01 10:15", "2026-01-01", 20),
            self._trade("phase12a::c", "phase12a", "c", "2026-01-02 09:30", "2026-01-02 10:00", "2026-01-02", 30),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col])
        accepted, skipped_overlap, _ = construct_portfolio_trades(trades, ["phase10b::a", "phase11a::b", "phase12a::c"], "one_trade_at_a_time_chronological")
        self.assertEqual(len(accepted), 2)
        self.assertEqual(skipped_overlap, 1)
        accepted_session, _, skipped_session = construct_portfolio_trades(trades, ["phase10b::a", "phase11a::b", "phase12a::c"], "max_one_trade_per_session")
        self.assertEqual(len(accepted_session), 2)
        self.assertEqual(skipped_session, 1)

    def test_concentration_drawdown_gates_and_report_guardrail(self) -> None:
        before = dict(OFFICIAL_GATES)
        self.assertEqual(concentration(pd.Series([80, 20, -10]))["best"], 0.888889)
        self.assertEqual(max_drawdown(pd.Series([10, -15, 5, -20])), -30.0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_portfolio_audit_a(out)
            report = render_portfolio_audit_report(result, Path("reports/portfolio_audit_a_report.md"))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertNotIn("signal_time", " ".join(result["signal_selection"].columns))
        self.assertEqual(OFFICIAL_GATES, before)

    def _write_inputs(self, out: Path) -> None:
        registry = pd.DataFrame([
            self._registry("phase10b", "phase10b_top", "real_but_nontradable_signal", "parked_research_signal", 100, 90, 80, 70, 60, 100, 100, 0.2, 0.1),
            self._registry("phase11a", "phase11a_top", "real_but_nontradable_signal", "parked_research_signal", 60, 50, 40, 30, 20, 80, 80, 0.25, 0.15),
            self._registry("phase12a", "phase12a_top", "positive_research_signal", "rare_setup_research_signal", 40, 30, 20, 10, 5, 40, 40, 0.3, 0.2),
            self._registry("phase10b", "phase10b_extra", "real_but_nontradable_signal", "parked_research_signal", 30, 20, 10, 5, 2, 30, 30, 0.4, 0.3),
        ])
        registry.to_csv(out / "research_signal_registry.csv", index=False)
        (out / "research_signal_registry.json").write_text(registry.to_json(orient="records"), encoding="utf-8")
        (out / "research_signal_registry_next_action_recommendation.json").write_text(json.dumps({"next_action": "maintain"}), encoding="utf-8")
        audit_c = registry[["phase", "candidate_id", "net_pnl"]].copy()
        audit_c["phase_rank"] = [1, 1, 1, 2]
        audit_c["phase_score"] = audit_c["net_pnl"]
        audit_c["audit_c_rank"] = [1, 2, 3, 4]
        audit_c.to_csv(out / "framework_audit_c_candidate_selection.csv", index=False)
        pd.DataFrame([{"phase": "phase10b", "candidates": 2}]).to_csv(out / "framework_audit_c_family_comparison.csv", index=False)
        (out / "framework_audit_c_next_action_recommendation.json").write_text(json.dumps({"next_action": "two_tier"}), encoding="utf-8")
        for phase in ("phase10b", "phase11a", "phase12a"):
            cids = registry[registry["phase"].eq(phase)]["candidate_id"].tolist()
            pd.DataFrame([{"candidate_id": cid, "net_pnl": 1} for cid in cids]).to_csv(out / f"{phase}_candidate_results.csv", index=False)
            trades = []
            for cid in cids:
                trades.extend([
                    {"candidate_id": cid, "entry_time": "2026-01-01 09:30", "exit_time": "2026-01-01 10:00", "trading_session": "2026-01-01", "net_pnl": 10, "gross_pnl": 12, "stress_pnl": 9, "split": "validation"},
                    {"candidate_id": cid, "entry_time": "2026-01-02 09:30", "exit_time": "2026-01-02 10:00", "trading_session": "2026-01-02", "net_pnl": -5, "gross_pnl": -3, "stress_pnl": -6, "split": "holdout"},
                    {"candidate_id": cid, "entry_time": "2026-01-03 09:30", "exit_time": "2026-01-03 10:00", "trading_session": "2026-01-03", "net_pnl": 15, "gross_pnl": 17, "stress_pnl": 14, "split": "discovery"},
                ])
            pd.DataFrame(trades).to_csv(out / f"{phase}_trade_logs.csv", index=False)
            pd.DataFrame(trades).groupby(["candidate_id", "trading_session"], as_index=False)["net_pnl"].sum().to_csv(out / f"{phase}_daily_pnl.csv", index=False)
            pd.DataFrame([{"candidate_id": cid, "fold": 1, "net_pnl": 10, "stress_pnl": 9, "trades": 1} for cid in cids]).to_csv(out / f"{phase}_walk_forward_folds.csv", index=False)

    def _registry(self, phase: str, cid: str, evidence: str, track: str, net: float, stress: float, val: float, hold: float, wf: float, trades: int, active: int, day: float, trade: float) -> dict[str, object]:
        return {"phase": phase, "candidate_id": cid, "family": phase, "plain_english_rule": "rule", "net_pnl": net, "stress_pnl": stress, "validation_pnl": val, "holdout_pnl": hold, "walk_forward_stress_pnl": wf, "positive_wf_test_folds_pct": 0.8, "trades": trades, "active_days": active, "best_day_concentration": day, "best_trade_concentration": trade, "bootstrap_or_null_classification": evidence, "signal_evidence_status": evidence, "tradability_status": "not_tradable_concentrated", "research_track": track, "revisit_condition": "more data", "source_report": "report"}

    def _trade(self, key: str, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"signal_key": key, "phase": phase, "candidate_id": cid, "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "gross_pnl": pnl, "stress_pnl": pnl, "phase_priority": {"phase10b": 0, "phase11a": 1, "phase12a": 2}[phase], "split": "validation"}


if __name__ == "__main__":
    unittest.main()
