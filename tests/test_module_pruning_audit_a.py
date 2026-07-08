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

from short_term_edge.module_pruning_audit_a import (  # noqa: E402
    MODES,
    OFFICIAL_GATES_CHANGED,
    PAPER_TRADING_APPROVED,
    PRIORITY_POLICIES,
    PRUNING_VARIANTS,
    SEED_SUSPECT_MODULE,
    calculate_redundancy_pairs,
    construct_scheduled_trades,
    identify_seed_suspect,
    identify_sibling_duplicate_variants,
    load_module_pruning_audit_a_inputs,
    render_module_pruning_audit_a_report,
    run_module_pruning_audit_a,
    write_module_pruning_audit_a_outputs,
)
from short_term_edge.playbook_scheduler_b_priority_retest import PHASES  # noqa: E402


class ModulePruningAuditATests(unittest.TestCase):
    def test_loads_scheduler_b_outputs_and_module_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_module_pruning_audit_a_inputs(out)
            self.assertIn("scheduler_b_results", data)
            self.assertIn("playbook_module_registry", data)
            self.assertFalse(data["scheduler_b_results"].empty)
            self.assertFalse(data["playbook_module_registry"].empty)

    def test_identifies_seed_suspect_deterministically(self) -> None:
        keys = [SEED_SUSPECT_MODULE, "phase10b::other"]
        self.assertEqual(identify_seed_suspect(keys), SEED_SUSPECT_MODULE)
        with self.assertRaises(ValueError):
            identify_seed_suspect(["phase10b::other"])

    def test_identifies_sibling_duplicate_variants_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_module_pruning_audit_a_inputs(out)
            selected = data["portfolio_d_selection"]
            matrix = data["portfolio_d_daily_matrix"]
            corr = data["portfolio_d_correlation"]
            first = identify_sibling_duplicate_variants(SEED_SUSPECT_MODULE, selected, matrix, corr)
            second = identify_sibling_duplicate_variants(SEED_SUSPECT_MODULE, selected, matrix, corr)
            self.assertEqual(first, second)
            self.assertIn(SEED_SUSPECT_MODULE, first)
            self.assertIn("phase10b::seed_mt2", first)

    def test_pruning_variants_do_not_mutate_registry_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            before_module = (out / "playbook_module_registry.csv").read_bytes()
            before_signal = (out / "research_signal_registry.csv").read_bytes()
            result = run_module_pruning_audit_a(out)
            write_module_pruning_audit_a_outputs(result, out, out / "report.md")
            self.assertEqual(before_module, (out / "playbook_module_registry.csv").read_bytes())
            self.assertEqual(before_signal, (out / "research_signal_registry.csv").read_bytes())

    def test_scheduler_retest_after_pruning_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            first = run_module_pruning_audit_a(out)
            second = run_module_pruning_audit_a(out)
            pd.testing.assert_frame_equal(first["portfolio_results"], second["portfolio_results"])
            self.assertEqual(len(first["portfolio_results"]), len(PRUNING_VARIANTS) * len(PRIORITY_POLICIES) * len(MODES))

    def test_one_trade_at_a_time_chronological_skips_overlaps_deterministically(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b", "seed", "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", 10),
            self._trade("phase11a", "core11", "2026-01-01 09:45", "2026-01-01 10:10", "2026-01-01", 20),
            self._trade("phase13a", "div13", "2026-01-01 10:15", "2026-01-01 10:30", "2026-01-01", 30),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], utc=True)
        order = {"phase10b::seed": 0, "phase11a::core11": 1, "phase13a::div13": 2}
        accepted, skipped_overlap, skipped_session, rejected, _ = construct_scheduled_trades(trades, list(order), order, "one_trade_at_a_time_chronological")
        self.assertEqual(skipped_overlap, 1)
        self.assertEqual(skipped_session, 0)
        self.assertEqual(list(accepted["signal_key"]), ["phase10b::seed", "phase13a::div13"])
        self.assertEqual(rejected.iloc[0]["skip_reason"], "overlapping_holding_period")

    def test_max_one_trade_per_session_enforces_cme_session_cap(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b", "seed", "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", 10),
            self._trade("phase11a", "core11", "2026-01-01 11:00", "2026-01-01 11:15", "2026-01-01", 20),
            self._trade("phase13a", "div13", "2026-01-02 09:30", "2026-01-02 09:45", "2026-01-02", 30),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], utc=True)
        order = {"phase10b::seed": 0, "phase11a::core11": 1, "phase13a::div13": 2}
        accepted, _, skipped_session, rejected, _ = construct_scheduled_trades(trades, list(order), order, "max_one_trade_per_session")
        self.assertEqual(skipped_session, 1)
        self.assertLessEqual(int(accepted.groupby("trading_session").size().max()), 1)
        self.assertEqual(rejected.iloc[0]["skip_reason"], "session_already_used")

    def test_redundancy_pair_calculation_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_module_pruning_audit_a_inputs(out)
            first = calculate_redundancy_pairs(data["portfolio_d_selection"], data["portfolio_d_daily_matrix"], data["portfolio_d_correlation"])
            second = calculate_redundancy_pairs(data["portfolio_d_selection"], data["portfolio_d_daily_matrix"], data["portfolio_d_correlation"])
            pd.testing.assert_frame_equal(first, second)
            self.assertFalse(first.empty)
            self.assertIn("lower_ranked_module", first.columns)

    def test_guardrails_official_gates_no_paper_and_no_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_module_pruning_audit_a(out)
            rows = result["portfolio_results"]
            self.assertFalse(OFFICIAL_GATES_CHANGED)
            self.assertFalse(PAPER_TRADING_APPROVED)
            self.assertFalse(bool(rows["official_gates_changed"].any()))
            self.assertFalse(bool(rows["paper_trading_approved"].any()))
            self.assertTrue(bool(rows["diagnostic_only_no_signals_generated"].all()))
            self.assertFalse(bool(rows["raw_sum_diagnostic_used_as_candidate"].any()))
            self.assertFalse(result["next_action_recommendation"]["paper_trading_approved"])
            self.assertFalse(result["next_action_recommendation"]["official_gates_changed"])

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            report = render_module_pruning_audit_a_report(run_module_pruning_audit_a(out))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("No new signals", report)
            self.assertIn("Registry modules removed: `false`", report)

    def _write_inputs(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        modules = pd.DataFrame([
            self._module("phase10b", SEED_SUSPECT_MODULE.split("::", 1)[1], "parked_research_signal", "core", 100, 10, 0.4),
            self._module("phase10b", "seed_mt2", "parked_research_signal", "core", 90, 9, 0.4),
            self._module("phase11a", "core11", "parked_research_signal", "core", 80, 8, 0.3),
            self._module("phase12a", "core12", "rare_setup_research_signal", "core", 70, 7, 0.2),
            self._module("phase13a", "div13", "parked_research_signal", "diversifier_module", 60, 6, 0.2),
            self._module("phase14a", "div14", "parked_research_signal", "diversifier_module", 50, 5, 0.2),
            self._module("phase15a", "div15", "parked_research_signal", "diversifier_module", 40, 4, 0.2),
        ])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        selection = modules.copy()
        selection.insert(0, "selection_rank", range(1, len(selection) + 1))
        selection["signal_key"] = selection.apply(lambda r: f"{r.phase}::{r.candidate_id}", axis=1)
        selection["prior_score"] = selection["net_pnl"]
        selection.to_csv(out / "portfolio_audit_d_signal_selection.csv", index=False)
        keys = selection["signal_key"].tolist()
        signal_keys = ";".join(keys)
        corr_rows = []
        for a in keys:
            for b in keys:
                val = 1.0 if a == b or {a, b} == {SEED_SUSPECT_MODULE, "phase10b::seed_mt2"} else 0.0
                corr_rows.append({"signal_a": a, "signal_b": b, "daily_pnl_correlation": val})
        pd.DataFrame(corr_rows).to_csv(out / "portfolio_audit_d_signal_correlation.csv", index=False)
        daily_matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"]})
        for key in keys:
            daily_matrix[key] = [1, 2, 3, 4, 5, 6]
        daily_matrix.to_csv(out / "portfolio_audit_d_daily_pnl_matrix.csv", index=False)
        self._write_scheduler_b_outputs(out, signal_keys, keys)
        self._write_portfolio_d_outputs(out, signal_keys)
        self._write_weak_fold_outputs(out)
        for phase in PHASES:
            rows = []
            for key in keys:
                ph, cid = key.split("::", 1)
                if ph != phase:
                    continue
                for i, day in enumerate(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"], start=1):
                    pnl = -10 if key == SEED_SUSPECT_MODULE else i
                    rows.append(self._trade(phase, cid, f"{day} 09:{30+i:02d}", f"{day} 10:{30+i:02d}", day, pnl))
            pd.DataFrame(rows).to_csv(out / f"{phase}_trade_logs.csv", index=False)

    def _write_scheduler_b_outputs(self, out: Path, signal_keys: str, keys: list[str]) -> None:
        rows = []
        for policy in PRIORITY_POLICIES:
            for mode in MODES:
                rows.append({"priority_policy": policy, "portfolio_mode": mode, "diagnostic_filter": "no_filter_baseline", "signals": len(keys), "signal_keys": signal_keys, "net_pnl": 10, "validation_pnl": 5, "holdout_pnl": 5, "walk_forward_test_pnl": 10, "walk_forward_stress_pnl": 8, "positive_wf_test_folds_pct": 0.5, "worst_wf_test_fold": -1, "trades": 6, "active_days": 6, "trades_per_active_day": 1, "max_drawdown": -5, "best_day_concentration": 0.5, "best_trade_concentration": 0.5, "top_3_day_concentration": 1, "top_5_trade_concentration": 1, "skipped_overlap_count": 0, "skipped_session_count": 0, "weak_fold_count": 1, "weak_fold_pnl": -1, "official_gates_changed": False, "paper_trading_approved": False, "diagnostic_only_no_signals_generated": True})
        pd.DataFrame(rows).to_csv(out / "playbook_scheduler_b_priority_policy_results.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "playbook_scheduler_b_daily_pnl.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "fold": 1, "net_pnl": 1, "stress_pnl": -1, "active_days": 1}]).to_csv(out / "playbook_scheduler_b_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "best_day_concentration": 0.5, "best_trade_concentration": 0.5}]).to_csv(out / "playbook_scheduler_b_concentration.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "accepted_trades": 1, "skipped_overlap_count": 0, "skipped_session_count": 0}]).to_csv(out / "playbook_scheduler_b_overlap_summary.csv", index=False)
        acc = []
        for key in keys:
            ph, cid = key.split("::", 1)
            acc.append({"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "phase": ph, "candidate_id": cid, "signal_key": key, "accepted_trade_count": 0 if key == SEED_SUSPECT_MODULE else 2, "accepted_net_pnl": -10 if key == SEED_SUSPECT_MODULE else 10, "skipped_trade_count": 8 if key == SEED_SUSPECT_MODULE else 0, "skipped_net_pnl": 0})
        pd.DataFrame(acc).to_csv(out / "playbook_scheduler_b_module_acceptance_summary.csv", index=False)
        (out / "playbook_scheduler_b_next_action_recommendation.json").write_text(json.dumps({"next_action": "module_pruning_audit_a", "paper_trading_approved": False}), encoding="utf-8")

    def _write_portfolio_d_outputs(self, out: Path, signal_keys: str) -> None:
        pd.DataFrame([{"portfolio_set": "d", "portfolio_mode": MODES[0], "signal_keys": signal_keys, "net_pnl": 1, "paper_trading_approved": False}]).to_csv(out / "portfolio_audit_d_portfolio_results.csv", index=False)
        pd.DataFrame([{"portfolio_set": "d", "portfolio_mode": MODES[0], "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "portfolio_audit_d_portfolio_daily_pnl.csv", index=False)
        pd.DataFrame([{"portfolio_set": "d", "portfolio_mode": MODES[0], "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "portfolio_audit_d_portfolio_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"signal_key": SEED_SUSPECT_MODULE, "same_session_overlap": 1}]).to_csv(out / "portfolio_audit_d_trade_overlap_summary.csv", index=False)
        (out / "portfolio_audit_d_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")

    def _write_weak_fold_outputs(self, out: Path) -> None:
        pd.DataFrame([{"audit": "D", "portfolio_set": "d", "portfolio_mode": MODES[0], "fold": 1, "is_weak_fold": True, "module_group": "phase10b", "phase": "phase10b", "net_pnl_contribution": -10}]).to_csv(out / "weak_fold_regime_audit_b_module_contribution_by_fold.csv", index=False)
        pd.DataFrame([{"regime": "high_vol|mixed", "phase": "phase10b", "module_group": "phase10b", "net_pnl_contribution": -10, "active_days": 1, "consistently_hurts_weak_folds": True}]).to_csv(out / "weak_fold_regime_audit_b_module_contribution_by_regime.csv", index=False)
        pd.DataFrame([{"audit": "D", "portfolio_set": "d", "portfolio_mode": MODES[0], "fold": 1, "is_weak_fold": True, "overlap_days": 1}]).to_csv(out / "weak_fold_regime_audit_b_overlap_and_scheduler_diagnostics.csv", index=False)
        pd.DataFrame([{"cluster_key": "high_vol|mixed", "day_count": 1, "total_pnl": -10, "avg_pnl": -10, "large_negative_days": 1}]).to_csv(out / "weak_fold_regime_audit_b_bad_day_clusters.csv", index=False)

    def _module(self, phase: str, cid: str, track: str, role: str, net: float, validation: float, conc: float) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "market_condition": "diagnostic", "module_family": phase, "portfolio_role": role, "plain_english_rule": "existing rule", "signal_evidence_status": "existing_signal", "tradability_status": "not_tradable", "research_track": track, "portfolio_contribution_status": "not_evaluated", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": net, "stress_pnl": net, "validation_pnl": validation, "holdout_pnl": 1, "walk_forward_stress_pnl": 1, "positive_wf_test_folds_pct": 0.5, "trades": 6, "active_days": 6, "best_day_concentration": conc, "best_trade_concentration": conc, "source_report": "existing"}

    def _trade(self, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"candidate_id": cid, "phase": phase, "signal_key": f"{phase}::{cid}", "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "stress_pnl": pnl - 1, "gross_pnl": pnl, "split": "validation" if session <= "2026-01-03" else "holdout"}


if __name__ == "__main__":
    unittest.main()
