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

from short_term_edge.validation_framework_audit_c_fold_design import (  # noqa: E402
    all_fold_windows,
    alternative_fold_results,
    current_fold_boundary_summary,
    gate_sensitivity_by_fold_design,
    load_validation_framework_audit_c_inputs,
    recommended_validation_policy,
    render_validation_framework_audit_c_report,
    run_validation_framework_audit_c_fold_design,
)


class ValidationFrameworkAuditCFoldDesignTests(unittest.TestCase):
    def test_loads_scheduler_portfolio_fold_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            data = load_validation_framework_audit_c_inputs(root)
            self.assertIn("scheduler_d_folds", data)
            self.assertIn("portfolio_b_folds", data)
            self.assertIn("weak_fold_summary", data)

    def test_loads_module_daily_pnl_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            data = load_validation_framework_audit_c_inputs(root)
            self.assertIn("phase10b_daily", data)
            self.assertIn("phase15a_daily", data)

    def test_computes_current_fold_summaries_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            a = run_validation_framework_audit_c_fold_design(root)["fold_boundary_summary"]
            b = run_validation_framework_audit_c_fold_design(root)["fold_boundary_summary"]
            pd.testing.assert_frame_equal(a, b)
            self.assertIn("same_calendar_region_weak_across_b_c_d_scheduler_b_c_d", a.columns)

    def test_builds_calendar_half_year_quarterly_and_rolling_folds(self) -> None:
        daily = pd.DataFrame({"trading_session": pd.date_range("2025-01-01", periods=370, freq="D").strftime("%Y-%m-%d"), "net_pnl": 1.0})
        self.assertGreaterEqual(len(all_fold_windows(daily, pd.DataFrame(), "calendar_year_folds")), 2)
        self.assertGreaterEqual(len(all_fold_windows(daily, pd.DataFrame(), "half_year_folds")), 3)
        self.assertGreaterEqual(len(all_fold_windows(daily, pd.DataFrame(), "quarterly_folds")), 5)
        self.assertGreater(len(all_fold_windows(daily, pd.DataFrame(), "rolling_3_month_test_folds")), 0)
        self.assertGreater(len(all_fold_windows(daily, pd.DataFrame(), "rolling_6_month_test_folds")), 0)
        first = all_fold_windows(daily, pd.DataFrame(), "calendar_year_folds")
        second = all_fold_windows(daily, pd.DataFrame(), "calendar_year_folds")
        self.assertEqual(first, second)

    def test_builds_expanding_recent_test_style_when_safely_computable(self) -> None:
        daily = pd.DataFrame({"trading_session": pd.date_range("2025-01-01", periods=370, freq="D").strftime("%Y-%m-%d"), "net_pnl": 1.0})
        windows = all_fold_windows(daily, pd.DataFrame(), "expanding_train_recent_test_style")
        self.assertGreater(len(windows), 0)
        self.assertEqual(windows[0]["fold_design"], "expanding_train_recent_test_style")

    def test_detects_low_activity_folds_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_validation_framework_audit_c_fold_design(root)
            module_activity = result["module_activity_by_fold"]
            self.assertTrue(bool(module_activity["low_activity_makes_pass_fail_noisy"].any()))
            self.assertFalse(bool(module_activity[module_activity["module_group"].eq("phase10b")].iloc[0]["enough_observations"]))

    def test_fold_regime_composition_uses_existing_day_features_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_validation_framework_audit_c_fold_design(root)
            regime = result["fold_regime_composition"]
            self.assertIn("high_vol_frequency", regime.columns)
            self.assertIn("prior_level_interaction_frequency", regime.columns)
            self.assertNotIn("entry_signal", regime.columns)

    def test_gate_sensitivity_does_not_modify_official_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_validation_framework_audit_c_fold_design(root)
            gate = gate_sensitivity_by_fold_design(result["alternative_fold_results"])
            self.assertTrue((gate["official_gates_changed"] == False).all())  # noqa: E712
            self.assertIn("positive_wf_test_folds_pct_ge_0_9", gate.columns)

    def test_worst_fold_and_active_day_threshold_variants_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            gate = run_validation_framework_audit_c_fold_design(root)["gate_sensitivity_by_fold_design"]
            self.assertIn("worst_fold_pnl_ge_0_0", gate.columns)
            self.assertIn("worst_fold_pnl_ge_neg_500_0", gate.columns)
            self.assertIn("all_folds_active_days_ge_5", gate.columns)

    def test_policy_and_recommendation_guardrails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_validation_framework_audit_c_fold_design(root)
            policy = result["recommended_validation_policy"]
            rec = result["next_action_recommendation"]
            self.assertFalse(policy["official_gates_changed"])
            self.assertFalse(policy["paper_trading_approved"])
            self.assertFalse(rec["paper_trading_approved"])
            self.assertFalse(rec["new_strategy_signals_generated"])
            self.assertFalse(rec["strategy_searches_run"])

    def test_no_new_strategy_signals_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_validation_framework_audit_c_fold_design(root)
            self.assertTrue(result["next_action_recommendation"]["diagnostic_only_no_signals_generated"])
            for frame_name in ["alternative_fold_results", "module_activity_by_fold", "playbook_activity_by_fold"]:
                self.assertNotIn("signal_time", result[frame_name].columns)

    def test_recommended_validation_policy_has_official_gates_changed_false(self) -> None:
        policy = recommended_validation_policy(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        self.assertFalse(policy["official_gates_changed"])
        self.assertTrue(policy["keep_official_gates_unchanged"])

    def test_report_includes_research_only_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            report = render_validation_framework_audit_c_report(run_validation_framework_audit_c_fold_design(root))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("Official gates changed: `false`", report)

    def _write_inputs(self, root: Path) -> None:
        out = root / "outputs"
        out.mkdir(parents=True)
        modules = pd.DataFrame([self._module(phase, f"{phase}_a") for phase in ["phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a"]])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        self._write_weak_fold_inputs(out)
        dates = pd.date_range("2025-01-01", periods=12, freq="D").strftime("%Y-%m-%d").tolist()
        for scheduler in ["b", "c", "d"]:
            self._write_scheduler(out, scheduler, dates)
        for portfolio in ["b", "c", "d"]:
            self._write_portfolio(out, portfolio, dates)
        for phase in ["phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a"]:
            cid = f"{phase}_a"
            # Sparse by design: only two active days per project fold for several phases.
            pd.DataFrame([
                {"candidate_id": cid, "trading_session": dates[0], "trades": 1, "net_pnl": -10.0, "stress_pnl": -11.0},
                {"candidate_id": cid, "trading_session": dates[6], "trades": 1, "net_pnl": 15.0, "stress_pnl": 14.0},
            ]).to_csv(out / f"{phase}_daily_pnl.csv", index=False)

    def _write_scheduler(self, out: Path, scheduler: str, dates: list[str]) -> None:
        if scheduler == "b":
            dims = {"priority_policy": "p", "portfolio_mode": "one_trade_at_a_time_chronological", "diagnostic_filter": "no_filter_baseline"}
            result_name = "playbook_scheduler_b_priority_policy_results.csv"
        elif scheduler == "c":
            dims = {"pruning_variant": "v", "priority_policy": "p", "portfolio_mode": "one_trade_at_a_time_chronological"}
            result_name = "playbook_scheduler_c_pruning_policy_results.csv"
        else:
            dims = {"pruning_variant": "v", "priority_policy": "p", "portfolio_mode": "one_trade_at_a_time_chronological"}
            result_name = "playbook_scheduler_d_overlay_policy_results.csv"
        daily = pd.DataFrame([{**dims, "trading_session": d, "net_pnl": (-5.0 if i < 6 else 8.0)} for i, d in enumerate(dates)])
        daily.to_csv(out / f"playbook_scheduler_{scheduler}_daily_pnl.csv", index=False)
        folds = pd.DataFrame([{**dims, "fold": 1, "net_pnl": -30.0, "stress_pnl": -32.0, "active_days": 6}, {**dims, "fold": 2, "net_pnl": 48.0, "stress_pnl": 46.0, "active_days": 6}])
        folds.to_csv(out / f"playbook_scheduler_{scheduler}_walk_forward_folds.csv", index=False)
        pd.DataFrame([{**dims, "best_day_concentration": 0.5, "best_trade_concentration": 0.5, "top_3_day_concentration": 0.8, "top_5_trade_concentration": 1.0}]).to_csv(out / f"playbook_scheduler_{scheduler}_concentration.csv", index=False)
        pd.DataFrame([{**dims, "trades": 12, "active_days": 12, "net_pnl": 18.0, "positive_wf_test_folds_pct": 0.5, "official_gates_changed": False, "paper_trading_approved": False}]).to_csv(out / result_name, index=False)
        (out / f"playbook_scheduler_{scheduler}_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")

    def _write_portfolio(self, out: Path, portfolio: str, dates: list[str]) -> None:
        dims = {"portfolio_set": f"set_{portfolio}", "portfolio_mode": "one_trade_at_a_time_chronological"}
        pd.DataFrame([{**dims, "trading_session": d, "net_pnl": (-2.0 if i < 6 else 3.0)} for i, d in enumerate(dates)]).to_csv(out / f"portfolio_audit_{portfolio}_portfolio_daily_pnl.csv", index=False)
        pd.DataFrame([{**dims, "fold": 1, "net_pnl": -12.0, "stress_pnl": -14.0, "active_days": 6}, {**dims, "fold": 2, "net_pnl": 18.0, "stress_pnl": 16.0, "active_days": 6}]).to_csv(out / f"portfolio_audit_{portfolio}_portfolio_walk_forward_folds.csv", index=False)

    def _write_weak_fold_inputs(self, out: Path) -> None:
        pd.DataFrame([{"audit": "B", "portfolio_set": "set_b", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "fold_start": "2025-01-01", "fold_end": "2025-01-06", "is_weak_fold": True}]).to_csv(out / "weak_fold_regime_audit_b_fold_summary.csv", index=False)
        pd.DataFrame([{"trading_session": "2025-01-01", "daily_playbook_pnl": -5.0}]).to_csv(out / "weak_fold_regime_audit_b_weak_fold_days.csv", index=False)
        pd.DataFrame([
            {"trading_session": d, "high_volatility_bucket": i % 2 == 0, "full_day_trend_proxy": i % 3 == 0, "range_day_proxy": i % 3 == 1, "power_hour_expansion": i % 4 == 0, "prior_rth_high_low_interaction_flag": i % 2 == 1}
            for i, d in enumerate(pd.date_range("2025-01-01", periods=12, freq="D").strftime("%Y-%m-%d"))
        ]).to_csv(out / "weak_fold_regime_audit_b_market_regime_features.csv", index=False)
        pd.DataFrame([{"cohort": "weak_fold_days", "day_count": 1}, {"cohort": "non_weak_fold_days", "day_count": 11}]).to_csv(out / "weak_fold_regime_audit_b_regime_comparison.csv", index=False)
        (out / "weak_fold_regime_audit_b_next_action_recommendation.json").write_text(json.dumps({"next_action": "validation_framework_audit_c_fold_design", "paper_trading_approved": False}), encoding="utf-8")

    def _module(self, phase: str, cid: str) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "module_family": phase, "portfolio_role": "parked_module", "paper_trading_approved": False, "official_gates_passed": False}


if __name__ == "__main__":
    unittest.main()
