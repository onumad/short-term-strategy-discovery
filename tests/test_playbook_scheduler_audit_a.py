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

from short_term_edge.playbook_scheduler_audit_a import (  # noqa: E402
    MODES,
    OFFICIAL_GATES_UNCHANGED,
    PAPER_TRADING_APPROVED,
    PHASES,
    REGIME_FILTERS,
    SCHEDULER_VARIANTS,
    build_regime_filter_sessions,
    build_scheduler_variant_orders,
    construct_scheduled_trades,
    load_playbook_scheduler_audit_a_inputs,
    render_playbook_scheduler_audit_a_report,
    run_playbook_scheduler_audit_a,
)


class PlaybookSchedulerAuditATests(unittest.TestCase):
    def test_loads_weak_fold_regime_b_outputs_and_phase_trade_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_audit_a_inputs(out)
            self.assertIn("weak_fold_b_market_features", data)
            self.assertIn("weak_fold_b_overlap_diag", data)
            for phase in PHASES:
                self.assertIn(f"{phase}_trades", data)
                self.assertFalse(data[f"{phase}_trades"].empty)

    def test_scheduler_priority_ordering_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_audit_a(out)
            first = result["scheduler_variant_orders"]
            second = run_playbook_scheduler_audit_a(out)["scheduler_variant_orders"]
            self.assertEqual(first, second)
            self.assertEqual(set(first), set(SCHEDULER_VARIANTS))
            phase10_key = "phase10b::p10"
            phase15_key = "phase15a::p15"
            self.assertLess(first["phase10b_first"][phase10_key], first["phase10b_first"][phase15_key])
            self.assertLess(first["phase15a_first"][phase15_key], first["phase15a_first"][phase10_key])

    def test_overlapping_trades_are_skipped_deterministically(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b", "p10", "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", -10),
            self._trade("phase15a", "p15", "2026-01-01 09:30", "2026-01-01 09:45", "2026-01-01", 20),
            self._trade("phase13a", "p13", "2026-01-01 09:50", "2026-01-01 10:10", "2026-01-01", 30),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], utc=True)
        order = {"phase15a::p15": 0, "phase10b::p10": 1, "phase13a::p13": 2}
        accepted, skipped_overlap, skipped_session, rejected = construct_scheduled_trades(trades, list(order), order, "one_trade_at_a_time_chronological")
        self.assertEqual(accepted.iloc[0]["signal_key"], "phase15a::p15")
        self.assertEqual(skipped_overlap, 1)
        self.assertEqual(skipped_session, 0)
        self.assertEqual(len(rejected), 1)
        accepted2, skipped_overlap2, _, rejected2 = construct_scheduled_trades(trades, list(order), order, "one_trade_at_a_time_chronological")
        pd.testing.assert_frame_equal(accepted, accepted2)
        self.assertEqual(skipped_overlap, skipped_overlap2)
        pd.testing.assert_frame_equal(rejected, rejected2)

    def test_max_one_trade_per_session_is_enforced(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase15a", "p15", "2026-01-01 09:30", "2026-01-01 09:45", "2026-01-01", 20),
            self._trade("phase10b", "p10", "2026-01-01 10:30", "2026-01-01 10:45", "2026-01-01", 10),
            self._trade("phase13a", "p13", "2026-01-02 09:30", "2026-01-02 09:45", "2026-01-02", 5),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], utc=True)
        order = {"phase15a::p15": 0, "phase10b::p10": 1, "phase13a::p13": 2}
        accepted, _, skipped_session, _ = construct_scheduled_trades(trades, list(order), order, "max_one_trade_per_session")
        self.assertEqual(skipped_session, 1)
        self.assertLessEqual(int(accepted.groupby("trading_session").size().max()), 1)

    def test_diagnostic_regime_filters_use_existing_day_features_only(self) -> None:
        features = pd.DataFrame([
            {"trading_session": "2026-01-01", "high_volatility_bucket": True, "full_day_trend_proxy": False, "range_day_proxy": False, "power_hour_expansion": True},
            {"trading_session": "2026-01-02", "high_volatility_bucket": True, "full_day_trend_proxy": False, "range_day_proxy": False, "power_hour_expansion": False},
            {"trading_session": "2026-01-03", "high_volatility_bucket": False, "full_day_trend_proxy": True, "range_day_proxy": False, "power_hour_expansion": False},
        ])
        filters = build_regime_filter_sessions(features, {"2026-01-03"})
        self.assertEqual(filters["exclude_high_vol_mixed_days"], {"2026-01-01", "2026-01-02"})
        self.assertEqual(filters["exclude_high_vol_mixed_power_expand_days"], {"2026-01-01"})
        self.assertEqual(filters["exclude_high_vol_mixed_no_power_expand_days"], {"2026-01-02"})
        self.assertEqual(filters["exclude_overlap_heavy_days"], {"2026-01-03"})
        self.assertEqual(set(filters), set(REGIME_FILTERS))

    def test_guardrails_no_gates_paper_signals_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_audit_a(out)
            self.assertTrue(OFFICIAL_GATES_UNCHANGED)
            self.assertFalse(PAPER_TRADING_APPROVED)
            self.assertFalse(bool(result["priority_results"]["paper_trading_approved"].any()))
            self.assertFalse(bool(result["priority_results"]["official_gates_changed"].any()))
            self.assertTrue(bool(result["priority_results"]["diagnostic_only_no_signals_generated"].all()))
            self.assertFalse(result["next_action_recommendation"]["paper_trading_approved"])
            self.assertFalse(result["next_action_recommendation"]["official_gates_changed"])
            self.assertTrue(result["next_action_recommendation"]["diagnostic_only_no_signals_generated"])
            report = render_playbook_scheduler_audit_a_report(result)
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("does not generate new signals", report)
            self.assertIn("Diagnostic filters are not promotion filters or live rules", report)
            self.assertEqual(len(result["priority_results"]), len(SCHEDULER_VARIANTS) * len(MODES) * len(REGIME_FILTERS))

    def _write_inputs(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        modules = pd.DataFrame([
            self._module("phase10b", "p10", "parked_research_signal", 100, 10),
            self._module("phase11a", "p11", "parked_research_signal", 90, 9),
            self._module("phase12a", "p12", "rare_setup_research_signal", 80, 8),
            self._module("phase13a", "p13", "parked_research_signal", 70, 7),
            self._module("phase14a", "p14", "parked_research_signal", 60, 6),
            self._module("phase15a", "p15", "parked_research_signal", 50, 5),
        ])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        signal_keys = ";".join(["phase15a::p15", "phase14a::p14", "phase13a::p13", "phase10b::p10", "phase11a::p11", "phase12a::p12"])
        pd.DataFrame([
            {"portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "signal_keys": signal_keys, "net_pnl": 10, "active_days": 2, "positive_wf_test_folds_pct": 0.5, "best_day_concentration": 0.6, "best_trade_concentration": 0.7, "paper_trading_approved": False, "official_gates_passed": False},
            {"portfolio_set": "audit_d_best", "portfolio_mode": "max_one_trade_per_session", "signal_keys": signal_keys, "net_pnl": 8, "active_days": 2, "positive_wf_test_folds_pct": 0.5, "best_day_concentration": 0.6, "best_trade_concentration": 0.7, "paper_trading_approved": False, "official_gates_passed": False},
        ]).to_csv(out / "portfolio_audit_d_portfolio_results.csv", index=False)
        pd.DataFrame([{"portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "portfolio_audit_d_portfolio_daily_pnl.csv", index=False)
        pd.DataFrame([{"portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "portfolio_audit_d_portfolio_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"signal_key": "phase10b::p10", "same_timestamp_overlap": 1, "overlapping_holding_periods": 1, "same_session_overlap": 1}]).to_csv(out / "portfolio_audit_d_trade_overlap_summary.csv", index=False)
        (out / "portfolio_audit_d_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")
        self._write_weak_fold_outputs(out)
        for phase, cid, pnl in [("phase10b", "p10", -10), ("phase11a", "p11", 2), ("phase12a", "p12", 3), ("phase13a", "p13", 4), ("phase14a", "p14", 5), ("phase15a", "p15", 6)]:
            pd.DataFrame([
                self._trade(phase, cid, "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", pnl),
                self._trade(phase, cid, "2026-01-02 09:30", "2026-01-02 10:00", "2026-01-02", pnl + 1),
                self._trade(phase, cid, "2026-01-03 09:30", "2026-01-03 10:00", "2026-01-03", pnl + 2),
            ]).to_csv(out / f"{phase}_trade_logs.csv", index=False)

    def _write_weak_fold_outputs(self, out: Path) -> None:
        pd.DataFrame([{"audit": "D", "portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "is_weak_fold": True, "fold_pnl": -1, "fold_stress_pnl": -2}]).to_csv(out / "weak_fold_regime_audit_b_fold_summary.csv", index=False)
        pd.DataFrame([{"audit": "D", "portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "trading_session": "2026-01-01", "daily_playbook_pnl": -1}]).to_csv(out / "weak_fold_regime_audit_b_weak_fold_days.csv", index=False)
        pd.DataFrame([
            {"trading_session": "2026-01-01", "high_volatility_bucket": True, "full_day_trend_proxy": False, "range_day_proxy": False, "power_hour_expansion": True},
            {"trading_session": "2026-01-02", "high_volatility_bucket": True, "full_day_trend_proxy": False, "range_day_proxy": False, "power_hour_expansion": False},
            {"trading_session": "2026-01-03", "high_volatility_bucket": False, "full_day_trend_proxy": True, "range_day_proxy": False, "power_hour_expansion": False},
        ]).to_csv(out / "weak_fold_regime_audit_b_market_regime_features.csv", index=False)
        pd.DataFrame([{"cohort": "weak_fold_days", "day_count": 1}]).to_csv(out / "weak_fold_regime_audit_b_regime_comparison.csv", index=False)
        pd.DataFrame([{"audit": "D", "portfolio_set": "audit_d_best", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "is_weak_fold": True, "overlap_days": 1}]).to_csv(out / "weak_fold_regime_audit_b_overlap_and_scheduler_diagnostics.csv", index=False)
        pd.DataFrame([{"cluster_key": "high_vol|mixed|power_expand", "day_count": 1, "total_pnl": -1}]).to_csv(out / "weak_fold_regime_audit_b_bad_day_clusters.csv", index=False)

    def _module(self, phase: str, cid: str, track: str, net: float, validation: float) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "market_condition": "diagnostic", "module_family": phase, "portfolio_role": "parked_module", "plain_english_rule": "existing rule", "signal_evidence_status": "existing_signal", "tradability_status": "not_tradable", "research_track": track, "portfolio_contribution_status": "not_evaluated", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": net, "stress_pnl": net, "validation_pnl": validation, "holdout_pnl": 1, "walk_forward_stress_pnl": 1, "positive_wf_test_folds_pct": 0.5, "trades": 3, "active_days": 3, "best_day_concentration": 0.5, "best_trade_concentration": 0.5, "source_report": "existing"}

    def _trade(self, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"candidate_id": cid, "phase": phase, "signal_key": f"{phase}::{cid}", "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "stress_pnl": pnl - 1, "gross_pnl": pnl, "split": "validation" if session <= "2026-01-02" else "holdout"}


if __name__ == "__main__":
    unittest.main()
