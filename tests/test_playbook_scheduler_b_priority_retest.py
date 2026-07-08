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

from short_term_edge.playbook_scheduler_b_priority_retest import (  # noqa: E402
    DIAGNOSTIC_FILTERS,
    MAX_SELECTED_MODULES,
    MODES,
    OFFICIAL_GATES_UNCHANGED,
    PAPER_TRADING_APPROVED,
    PHASES,
    PRIORITY_POLICIES,
    build_priority_policy_orders,
    construct_scheduled_trades,
    load_playbook_scheduler_b_inputs,
    render_playbook_scheduler_b_report,
    run_playbook_scheduler_b_priority_retest,
    select_scheduler_b_modules,
)


class PlaybookSchedulerBPriorityRetestTests(unittest.TestCase):
    def test_loads_scheduler_a_portfolio_d_and_phase_trade_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_b_inputs(out)
            self.assertIn("scheduler_a_priority_results", data)
            self.assertIn("portfolio_d_signal_selection", data)
            for phase in PHASES:
                self.assertIn(f"{phase}_trades", data)
                self.assertFalse(data[f"{phase}_trades"].empty)

    def test_module_selection_is_deterministic_capped_and_includes_required_phases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_b_inputs(out)
            first = select_scheduler_b_modules(data)
            second = select_scheduler_b_modules(data)
            pd.testing.assert_frame_equal(first, second)
            self.assertLessEqual(len(first), MAX_SELECTED_MODULES)
            for phase in PHASES:
                self.assertIn(phase, set(first["phase"]))
            self.assertGreaterEqual(len(first[first["phase"].eq("phase15a")]), 3)

    def test_each_priority_policy_orders_modules_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_b_priority_retest(out)
            orders = result["priority_policy_orders"]
            self.assertEqual(set(orders), set(PRIORITY_POLICIES))
            self.assertEqual(orders, run_playbook_scheduler_b_priority_retest(out)["priority_policy_orders"])
            keys = result["selected_signal_keys"]
            self.assertEqual(set(orders["core_then_diversifier"]), set(keys))
            self.assertLess(orders["core_then_diversifier"]["phase10b::p10"], orders["core_then_diversifier"]["phase15a::p15a1"])
            self.assertLess(orders["diversifier_first"]["phase15a::p15a1"], orders["diversifier_first"]["phase10b::p10"])

    def test_one_trade_at_a_time_skips_overlaps_deterministically(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b", "p10", "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", -10),
            self._trade("phase15a", "p15a1", "2026-01-01 09:30", "2026-01-01 09:45", "2026-01-01", 20),
            self._trade("phase13a", "p13a1", "2026-01-01 09:50", "2026-01-01 10:10", "2026-01-01", 30),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], utc=True)
        order = {"phase15a::p15a1": 0, "phase10b::p10": 1, "phase13a::p13a1": 2}
        accepted, skipped_overlap, skipped_session, rejected, excluded = construct_scheduled_trades(trades, list(order), order, "one_trade_at_a_time_chronological")
        self.assertEqual(accepted.iloc[0]["signal_key"], "phase15a::p15a1")
        self.assertEqual(skipped_overlap, 1)
        self.assertEqual(skipped_session, 0)
        self.assertEqual(excluded, 0)
        self.assertEqual(len(rejected), 1)
        accepted2, skipped_overlap2, _, rejected2, _ = construct_scheduled_trades(trades, list(order), order, "one_trade_at_a_time_chronological")
        pd.testing.assert_frame_equal(accepted, accepted2)
        self.assertEqual(skipped_overlap, skipped_overlap2)
        pd.testing.assert_frame_equal(rejected, rejected2)

    def test_max_one_trade_per_session_enforces_session_cap(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase15a", "p15a1", "2026-01-01 09:30", "2026-01-01 09:45", "2026-01-01", 20),
            self._trade("phase10b", "p10", "2026-01-01 10:30", "2026-01-01 10:45", "2026-01-01", 10),
            self._trade("phase13a", "p13a1", "2026-01-02 09:30", "2026-01-02 09:45", "2026-01-02", 5),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], utc=True)
        order = {"phase15a::p15a1": 0, "phase10b::p10": 1, "phase13a::p13a1": 2}
        accepted, _, skipped_session, _, _ = construct_scheduled_trades(trades, list(order), order, "max_one_trade_per_session")
        self.assertEqual(skipped_session, 1)
        self.assertLessEqual(int(accepted.groupby("trading_session").size().max()), 1)

    def test_diagnostic_overlap_filter_marked_diagnostic_only_and_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_b_priority_retest(out)
            rows = result["priority_policy_results"]
            self.assertTrue(bool(rows[rows["diagnostic_filter"].eq("exclude_overlap_heavy_days")]["diagnostic_filter_only"].all()))
            self.assertFalse(bool(rows[rows["diagnostic_filter"].eq("no_filter_baseline")]["diagnostic_filter_only"].any()))
            self.assertTrue(OFFICIAL_GATES_UNCHANGED)
            self.assertFalse(PAPER_TRADING_APPROVED)
            self.assertFalse(bool(rows["paper_trading_approved"].any()))
            self.assertFalse(bool(rows["official_gates_changed"].any()))
            self.assertTrue(bool(rows["diagnostic_only_no_signals_generated"].all()))
            self.assertEqual(len(rows), len(PRIORITY_POLICIES) * len(MODES) * len(DIAGNOSTIC_FILTERS))
            self.assertFalse(result["next_action_recommendation"]["paper_trading_approved"])
            self.assertFalse(result["next_action_recommendation"]["official_gates_changed"])
            self.assertFalse(result["next_action_recommendation"]["raw_sum_diagnostic_used_as_candidate"])
            report = render_playbook_scheduler_b_report(result)
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("No new signals", report)
            self.assertIn("diagnostic-only", report)

    def _write_inputs(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        modules = pd.DataFrame([
            self._module("phase10b", "p10", "parked_research_signal", "parked_module", 100, 10, 0.5),
            self._module("phase11a", "p11", "parked_research_signal", "parked_module", 90, 9, 0.4),
            self._module("phase12a", "p12", "rare_setup_research_signal", "parked_module", 80, 8, 0.3),
            self._module("phase13a", "p13a1", "parked_research_signal", "diversifier_module", 70, 7, 0.2),
            self._module("phase13a", "p13a2", "parked_research_signal", "diversifier_module", 65, 6, 0.25),
            self._module("phase14a", "p14a1", "parked_research_signal", "diversifier_module", 60, 5, 0.22),
            self._module("phase14a", "p14a2", "parked_research_signal", "diversifier_module", 55, 4, 0.23),
            self._module("phase15a", "p15a1", "parked_research_signal", "diversifier_module", 50, 3, 0.18),
            self._module("phase15a", "p15a2", "parked_research_signal", "diversifier_module", 45, 2, 0.19),
            self._module("phase15a", "p15a3", "parked_research_signal", "diversifier_module", 40, 1, 0.20),
        ])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.drop(columns=["portfolio_role", "portfolio_contribution_status"], errors="ignore").to_csv(out / "research_signal_registry.csv", index=False)
        selection = modules.copy()
        selection.insert(0, "selection_rank", range(1, len(selection) + 1))
        selection["selection_reason"] = "test_selection"
        selection["outside_module_registry_for_baseline"] = False
        selection.to_csv(out / "portfolio_audit_d_signal_selection.csv", index=False)
        keys = [f"{r.phase}::{r.candidate_id}" for r in modules.itertuples()]
        pd.DataFrame([{"signal_a": a, "signal_b": b, "daily_pnl_correlation": 0.0 if a != b else 1.0} for a in keys for b in keys]).to_csv(out / "portfolio_audit_d_signal_correlation.csv", index=False)
        daily_matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"]})
        for key in keys:
            daily_matrix[key] = [1, 2, 3]
        daily_matrix.to_csv(out / "portfolio_audit_d_daily_pnl_matrix.csv", index=False)
        signal_keys = ";".join(keys)
        pd.DataFrame([
            {"portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "signal_keys": signal_keys, "net_pnl": 10, "active_days": 2, "positive_wf_test_folds_pct": 0.5, "best_day_concentration": 0.6, "best_trade_concentration": 0.7, "max_drawdown": -5, "paper_trading_approved": False, "official_gates_passed": False},
            {"portfolio_set": "audit_d_best", "portfolio_mode": "max_one_trade_per_session", "signal_keys": signal_keys, "net_pnl": 8, "active_days": 2, "positive_wf_test_folds_pct": 0.5, "best_day_concentration": 0.6, "best_trade_concentration": 0.7, "max_drawdown": -6, "paper_trading_approved": False, "official_gates_passed": False},
        ]).to_csv(out / "portfolio_audit_d_portfolio_results.csv", index=False)
        pd.DataFrame([{"portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "portfolio_audit_d_portfolio_daily_pnl.csv", index=False)
        pd.DataFrame([{"portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "portfolio_audit_d_portfolio_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"signal_key": "phase10b::p10", "same_timestamp_overlap": 1, "overlapping_holding_periods": 1, "same_session_overlap": 1}]).to_csv(out / "portfolio_audit_d_trade_overlap_summary.csv", index=False)
        (out / "portfolio_audit_d_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")
        self._write_scheduler_a_outputs(out, signal_keys)
        for phase in PHASES:
            phase_rows = modules[modules["phase"].eq(phase)]
            trades = []
            for idx, row in enumerate(phase_rows.itertuples(), start=1):
                for day, pnl in [("2026-01-01", idx), ("2026-01-02", idx + 1), ("2026-01-03", idx + 2)]:
                    trades.append(self._trade(phase, row.candidate_id, f"{day} 09:30", f"{day} 10:00", day, pnl))
            pd.DataFrame(trades).to_csv(out / f"{phase}_trade_logs.csv", index=False)

    def _write_scheduler_a_outputs(self, out: Path, signal_keys: str) -> None:
        a_rows = []
        for mode in MODES:
            a_rows.append({"scheduler_variant": "existing_priority_baseline", "portfolio_mode": mode, "regime_filter": "no_filter_baseline", "signals": 10, "signal_keys": signal_keys, "net_pnl": 5, "validation_pnl": 2, "holdout_pnl": 3, "walk_forward_stress_pnl": 4, "positive_wf_test_folds_pct": 0.5, "worst_wf_test_fold": -1, "trades": 5, "active_days": 3, "max_drawdown": -2, "best_day_concentration": 0.5, "best_trade_concentration": 0.5, "top_3_day_concentration": 1, "top_5_trade_concentration": 1, "skipped_overlap_count": 0, "skipped_session_count": 0, "rejected_trade_count": 0, "weak_fold_count": 1, "weak_fold_pnl": -1, "improvement_vs_portfolio_audit_d_best": 0, "official_gates_changed": False, "paper_trading_approved": False, "diagnostic_only_no_signals_generated": True})
        pd.DataFrame(a_rows).to_csv(out / "playbook_scheduler_audit_a_priority_results.csv", index=False)
        pd.DataFrame([{"regime_filter": "exclude_overlap_heavy_days", "scheduler_variant": "existing_priority_baseline", "portfolio_mode": MODES[0], "diagnostic_only_not_live_rule": True}]).to_csv(out / "playbook_scheduler_audit_a_regime_filter_results.csv", index=False)
        pd.DataFrame([{"scheduler_variant": "existing_priority_baseline", "portfolio_mode": MODES[0], "regime_filter": "no_filter_baseline", "accepted_trades": 1}]).to_csv(out / "playbook_scheduler_audit_a_overlap_diagnostics.csv", index=False)
        pd.DataFrame([{"scheduler_variant": "existing_priority_baseline", "portfolio_mode": MODES[0], "regime_filter": "no_filter_baseline", "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "playbook_scheduler_audit_a_daily_pnl.csv", index=False)
        pd.DataFrame([{"scheduler_variant": "existing_priority_baseline", "portfolio_mode": MODES[0], "regime_filter": "no_filter_baseline", "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "playbook_scheduler_audit_a_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"scheduler_variant": "existing_priority_baseline", "portfolio_mode": MODES[0], "regime_filter": "no_filter_baseline", "best_day_concentration": 0.5, "best_trade_concentration": 0.5}]).to_csv(out / "playbook_scheduler_audit_a_concentration.csv", index=False)
        (out / "playbook_scheduler_audit_a_next_action_recommendation.json").write_text(json.dumps({"next_action": "playbook_scheduler_b_priority_retest", "paper_trading_approved": False}), encoding="utf-8")

    def _module(self, phase: str, cid: str, track: str, role: str, net: float, validation: float, conc: float) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "market_condition": "diagnostic", "module_family": phase, "portfolio_role": role, "plain_english_rule": "existing rule", "signal_evidence_status": "existing_signal", "tradability_status": "not_tradable", "research_track": track, "portfolio_contribution_status": "not_evaluated", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": net, "stress_pnl": net, "validation_pnl": validation, "holdout_pnl": 1, "walk_forward_stress_pnl": 1, "positive_wf_test_folds_pct": 0.5, "trades": 3, "active_days": 3, "best_day_concentration": conc, "best_trade_concentration": conc, "source_report": "existing"}

    def _trade(self, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"candidate_id": cid, "phase": phase, "signal_key": f"{phase}::{cid}", "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "stress_pnl": pnl - 1, "gross_pnl": pnl, "split": "validation" if session <= "2026-01-02" else "holdout"}


if __name__ == "__main__":
    unittest.main()
