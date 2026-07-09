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

from short_term_edge.playbook_scheduler_e_rare_module_priority_audit import (  # noqa: E402
    DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED,
    LIVE_TRADING_APPROVED,
    MODES,
    OFFICIAL_GATES_CHANGED,
    PAPER_TRADING_APPROVED,
    POLICIES,
    build_scheduler_e_policy_orders,
    construct_scheduler_e_trades,
    load_playbook_scheduler_e_inputs,
    phase16a_rare_module_keys,
    rare_module_keys,
    render_playbook_scheduler_e_report,
    run_playbook_scheduler_e_rare_module_priority_audit,
    select_scheduler_e_modules,
    validate_rare_policy_guardrails,
)


class PlaybookSchedulerERareModulePriorityAuditTests(unittest.TestCase):
    def test_loads_playbook_rare_module_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_e_inputs(out)
            self.assertIn("rare_policy", data)
            self.assertTrue(data["rare_policy"]["rare_module_track_enabled"])

    def test_loads_playbook_module_registry_with_phase16a_rare_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_e_inputs(out)
            selected = select_scheduler_e_modules(data)
            self.assertGreaterEqual(len(phase16a_rare_module_keys(selected)), 2)

    def test_selects_rare_modules_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_e_inputs(out)
            self.assertEqual(rare_module_keys(select_scheduler_e_modules(data)), rare_module_keys(select_scheduler_e_modules(data)))

    def test_selects_phase16a_rare_modules_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_e_inputs(out)
            self.assertEqual(phase16a_rare_module_keys(select_scheduler_e_modules(data)), phase16a_rare_module_keys(select_scheduler_e_modules(data)))

    def test_scheduler_policies_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_e_inputs(out)
            selected = select_scheduler_e_modules(data)
            keys = selected["signal_key"].astype(str).tolist()
            rare = rare_module_keys(selected)
            p16 = phase16a_rare_module_keys(selected)
            corr = {k: 0.1 for k in keys}
            self.assertEqual(build_scheduler_e_policy_orders(selected, keys, rare, p16, corr, data), build_scheduler_e_policy_orders(selected, keys, rare, p16, corr, data))
            self.assertEqual(set(build_scheduler_e_policy_orders(selected, keys, rare, p16, corr, data)), set(POLICIES))

    def test_rare_session_cap_allows_at_most_one_rare_trade_per_session(self) -> None:
        trades = pd.DataFrame([
            self._trade("phase10b", "core", "2026-01-01 09:30", "2026-01-01 09:45", "2026-01-01", 10),
            self._trade("phase16a", "rare1", "2026-01-01 10:00", "2026-01-01 10:15", "2026-01-01", 20),
            self._trade("phase16a", "rare2", "2026-01-01 10:30", "2026-01-01 10:45", "2026-01-01", 30),
        ])
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], utc=True)
        keys = list(trades["signal_key"].unique())
        rare = ["phase16a::rare1", "phase16a::rare2"]
        selected = pd.DataFrame({"signal_key": keys, "phase": [k.split("::", 1)[0] for k in keys]})
        accepted, rejected, _ = construct_scheduler_e_trades(trades, keys, {"phase16a::rare1": 0, "phase16a::rare2": 1, "phase10b::core": 2}, "one_trade_at_a_time_chronological", "rare_session_cap", rare, rare, selected)
        rare_accepted = accepted[accepted["signal_key"].isin(rare)]
        max_rare_per_session = 0 if rare_accepted.empty else int(rare_accepted.groupby("trading_session").size().max())
        self.assertLessEqual(max_rare_per_session, 1)
        self.assertIn("rare_session_cap_used", set(rejected.get("skip_reason", pd.Series(dtype=str))))

    def test_rare_only_if_no_prior_trade_in_session_is_chronological_no_future(self) -> None:
        trades = self._toy_trades()
        keys = list(trades["signal_key"].unique())
        rare = ["phase16a::rare1", "phase16a::rare2"]
        selected = pd.DataFrame({"signal_key": keys, "phase": [k.split("::", 1)[0] for k in keys]})
        accepted, rejected, _ = construct_scheduler_e_trades(trades, keys, {"phase10b::core": 0, "phase16a::rare1": 1, "phase16a::rare2": 2}, "one_trade_at_a_time_chronological", "rare_only_if_no_prior_trade_in_session", rare, rare, selected)
        self.assertEqual(list(accepted["signal_key"]), ["phase10b::core"])
        self.assertTrue(set(rejected["skip_reason"]).issuperset({"rare_prior_trade_in_session"}))

    def test_rare_only_if_no_overlap_skips_overlapping_rare_deterministically(self) -> None:
        trades = self._toy_trades()
        keys = list(trades["signal_key"].unique())
        rare = ["phase16a::rare1", "phase16a::rare2"]
        selected = pd.DataFrame({"signal_key": keys, "phase": [k.split("::", 1)[0] for k in keys]})
        accepted, rejected, _ = construct_scheduler_e_trades(trades, keys, {"phase10b::core": 0, "phase16a::rare1": 1, "phase16a::rare2": 2}, "one_trade_at_a_time_chronological", "rare_only_if_no_overlap", rare, rare, selected)
        self.assertEqual(list(accepted["signal_key"]), ["phase10b::core"])
        self.assertIn("rare_overlaps_already_accepted_trade", set(rejected["skip_reason"]))

    def test_one_trade_at_a_time_chronological_skips_overlaps_deterministically(self) -> None:
        trades = self._toy_trades()
        keys = list(trades["signal_key"].unique())
        selected = pd.DataFrame({"signal_key": keys, "phase": [k.split("::", 1)[0] for k in keys]})
        accepted, rejected, counts = construct_scheduler_e_trades(trades, keys, {"phase10b::core": 0, "phase16a::rare1": 1, "phase16a::rare2": 2}, "one_trade_at_a_time_chronological", "baseline_existing_priority", ["phase16a::rare1", "phase16a::rare2"], ["phase16a::rare1", "phase16a::rare2"], selected)
        self.assertEqual(list(accepted["signal_key"]), ["phase10b::core"])
        self.assertEqual(counts["skipped_overlap_count"], 2)
        self.assertEqual(set(rejected["skip_reason"]), {"overlapping_holding_period"})

    def test_max_one_trade_per_session_enforces_one_trade_per_cme_session(self) -> None:
        trades = self._toy_trades()
        keys = list(trades["signal_key"].unique())
        selected = pd.DataFrame({"signal_key": keys, "phase": [k.split("::", 1)[0] for k in keys]})
        accepted, rejected, counts = construct_scheduler_e_trades(trades, keys, {k: i for i, k in enumerate(keys)}, "max_one_trade_per_session", "baseline_existing_priority", ["phase16a::rare1", "phase16a::rare2"], ["phase16a::rare1", "phase16a::rare2"], selected)
        self.assertLessEqual(int(accepted.groupby("trading_session").size().max()), 1)
        self.assertEqual(counts["skipped_session_count"], 2)
        self.assertEqual(set(rejected["skip_reason"]), {"session_already_used"})

    def test_official_gates_are_not_modified(self) -> None:
        self.assertFalse(OFFICIAL_GATES_CHANGED)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_e_rare_module_priority_audit(out)
            self.assertFalse(bool(result["policy_results"]["official_gates_changed"].any()))

    def test_paper_trading_approved_remains_false(self) -> None:
        self.assertFalse(PAPER_TRADING_APPROVED)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_e_rare_module_priority_audit(out)
            self.assertFalse(bool(result["policy_results"]["paper_trading_approved"].any()))
            self.assertFalse(result["next_action_recommendation"]["paper_trading_approved"])

    def test_no_new_strategy_signals_are_generated(self) -> None:
        self.assertTrue(DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED)
        self.assertFalse(LIVE_TRADING_APPROVED)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            before = pd.read_csv(out / "playbook_module_registry.csv").shape[0]
            result = run_playbook_scheduler_e_rare_module_priority_audit(out)
            after = pd.read_csv(out / "playbook_module_registry.csv").shape[0]
            self.assertEqual(before, after)
            self.assertTrue(bool(result["policy_results"]["diagnostic_only_no_signals_generated"].all()))
            self.assertFalse(bool(result["policy_results"]["raw_sum_diagnostic_used_as_candidate"].any()))

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            report = render_playbook_scheduler_e_report(run_playbook_scheduler_e_rare_module_priority_audit(out))
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("No new signals", report)
            self.assertIn("Live trading approved: `false`", report)

    def test_rare_policy_guardrails_fail_closed(self) -> None:
        policy = {"official_gates_changed": False, "paper_trading_approved": True}
        rules = {"official_gates_changed": False, "paper_trading_approved": False}
        with self.assertRaises(ValueError):
            validate_rare_policy_guardrails(policy, rules)

    def _toy_trades(self) -> pd.DataFrame:
        rows = [
            self._trade("phase10b", "core", "2026-01-01 09:30", "2026-01-01 10:30", "2026-01-01", 10),
            self._trade("phase16a", "rare1", "2026-01-01 09:45", "2026-01-01 10:00", "2026-01-01", 20),
            self._trade("phase16a", "rare2", "2026-01-01 10:00", "2026-01-01 10:15", "2026-01-01", 30),
        ]
        df = pd.DataFrame(rows)
        for col in ("entry_time", "exit_time"):
            df[col] = pd.to_datetime(df[col], utc=True)
        return df

    def _write_inputs(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        keys = [
            "phase10b::core10",
            "phase11a::core11",
            "phase12a::core12",
            "phase13a::div13",
            "phase14a::div14",
            "phase15a::div15",
            "phase16a::rare16a",
            "phase16a::rare16b",
        ]
        modules = pd.DataFrame([self._module(k, i) for i, k in enumerate(keys, start=1)])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        (out / "playbook_module_registry.json").write_text(modules.to_json(orient="records"), encoding="utf-8")
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        (out / "research_signal_registry.json").write_text(modules.to_json(orient="records"), encoding="utf-8")
        rare_policy = {"rare_module_track_enabled": True, "official_gates_changed": False, "paper_trading_approved": False, "live_trading_approved": False}
        (out / "playbook_rare_module_policy.json").write_text(json.dumps(rare_policy), encoding="utf-8")
        (out / "playbook_rare_module_portfolio_audit_rules.json").write_text(json.dumps({"official_gates_changed": False, "paper_trading_approved": False}), encoding="utf-8")
        signal_keys = ";".join(keys)
        result_rows = []
        for mode in ("raw_sum_diagnostic", *MODES):
            result_rows.append(self._result_row("baseline", mode, signal_keys, 100 if mode != "raw_sum_diagnostic" else 90))
        pd.DataFrame([{"selection_rank": i, **self._module(k, i)} for i, k in enumerate(keys, start=1)]).to_csv(out / "portfolio_audit_e_signal_selection.csv", index=False)
        pd.DataFrame([{"signal_a": a, "signal_b": b, "daily_pnl_correlation": 0.1 if a != b else 1.0} for a in keys for b in keys]).to_csv(out / "portfolio_audit_e_signal_correlation.csv", index=False)
        pd.DataFrame([{"trading_session": "2026-01-01", **{k: 1 for k in keys}}]).to_csv(out / "portfolio_audit_e_daily_pnl_matrix.csv", index=False)
        pd.DataFrame([{"signal_key": k, "same_timestamp_overlap": 0, "overlapping_holding_periods": 0, "same_session_overlap": 0} for k in keys]).to_csv(out / "portfolio_audit_e_trade_overlap_summary.csv", index=False)
        pd.DataFrame(result_rows).to_csv(out / "portfolio_audit_e_portfolio_results.csv", index=False)
        pd.DataFrame([{"portfolio_set": "baseline", "portfolio_mode": MODES[0], "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "portfolio_audit_e_portfolio_daily_pnl.csv", index=False)
        pd.DataFrame([{"portfolio_set": "baseline", "portfolio_mode": MODES[0], "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "portfolio_audit_e_portfolio_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"portfolio_set": "baseline", "portfolio_mode": MODES[0], "best_day_concentration": 0.2, "best_trade_concentration": 0.15}]).to_csv(out / "portfolio_audit_e_portfolio_concentration.csv", index=False)
        pd.DataFrame([{"portfolio_set": "baseline", "portfolio_mode": MODES[0], "max_drawdown": -5}]).to_csv(out / "portfolio_audit_e_portfolio_drawdown_summary.csv", index=False)
        for name in ["incremental_contribution", "phase16a_rare_module_impact", "rare_module_contribution_summary", "weak_regime_coverage_summary"]:
            pd.DataFrame([{"portfolio_mode": MODES[0], "value": 1}]).to_csv(out / f"portfolio_audit_e_{name}.csv", index=False)
        (out / "portfolio_audit_e_next_action_recommendation.json").write_text(json.dumps({"next_action": "playbook_scheduler_e_rare_module_priority_audit", "paper_trading_approved": False}), encoding="utf-8")
        pd.DataFrame([self._result_row("scheduler_d", m, signal_keys, 80) for m in MODES]).to_csv(out / "playbook_scheduler_d_overlay_policy_results.csv", index=False)
        pd.DataFrame([{"overlay_variant": "baseline", "priority_policy": "baseline", "portfolio_mode": MODES[0], "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "playbook_scheduler_d_daily_pnl.csv", index=False)
        pd.DataFrame([{"overlay_variant": "baseline", "priority_policy": "baseline", "portfolio_mode": MODES[0], "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "playbook_scheduler_d_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"overlay_variant": "baseline", "priority_policy": "baseline", "portfolio_mode": MODES[0], "best_day_concentration": 0.2, "best_trade_concentration": 0.15}]).to_csv(out / "playbook_scheduler_d_concentration.csv", index=False)
        (out / "playbook_scheduler_d_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")
        pd.DataFrame([self._result_row("scheduler_c", m, signal_keys, 70) for m in MODES]).to_csv(out / "playbook_scheduler_c_pruning_policy_results.csv", index=False)
        pd.DataFrame([{"pruning_variant": "baseline", "priority_policy": "baseline", "portfolio_mode": MODES[0], "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "playbook_scheduler_c_daily_pnl.csv", index=False)
        pd.DataFrame([{"pruning_variant": "baseline", "priority_policy": "baseline", "portfolio_mode": MODES[0], "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "playbook_scheduler_c_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"pruning_variant": "baseline", "priority_policy": "baseline", "portfolio_mode": MODES[0], "best_day_concentration": 0.2, "best_trade_concentration": 0.15}]).to_csv(out / "playbook_scheduler_c_concentration.csv", index=False)
        (out / "playbook_scheduler_c_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")
        pd.DataFrame([{"trading_session": "2026-01-01"}]).to_csv(out / "weak_fold_regime_audit_b_market_regime_features.csv", index=False)
        pd.DataFrame([{"trading_session": "2026-01-01"}]).to_csv(out / "weak_fold_regime_audit_b_weak_fold_days.csv", index=False)
        pd.DataFrame([{"trading_session": "2026-01-01"}]).to_csv(out / "weak_fold_regime_audit_b_bad_day_clusters.csv", index=False)
        pd.DataFrame([{"regime": "test"}]).to_csv(out / "weak_fold_regime_audit_b_regime_comparison.csv", index=False)
        for phase in ["phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a", "phase16a"]:
            rows = []
            for key in keys:
                ph, cid = key.split("::", 1)
                if ph == phase:
                    rows.append(self._trade(ph, cid, "2026-01-01 09:30", "2026-01-01 10:00", "2026-01-01", 10))
                    rows.append(self._trade(ph, cid, "2026-01-02 09:30", "2026-01-02 10:00", "2026-01-02", 5))
            pd.DataFrame(rows).to_csv(out / f"{phase}_trade_logs.csv", index=False)

    def _module(self, key: str, rank: int) -> dict[str, object]:
        phase, cid = key.split("::", 1)
        rare = phase == "phase16a"
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "portfolio_role": "diversifier_module" if phase in {"phase13a", "phase14a", "phase15a", "phase16a"} else "parked_module", "research_track": "rare_setup_research_signal" if rare else "parked_research_signal", "rare_module_track_enabled": rare, "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": 100-rank, "stress_pnl": 90-rank, "validation_pnl": 10, "holdout_pnl": 5, "walk_forward_stress_pnl": 5, "positive_wf_test_folds_pct": 0.833333, "trades": 2, "active_days": 2, "best_day_concentration": 0.2, "best_trade_concentration": 0.1, "average_correlation_to_registry": 0.1}

    def _result_row(self, name: str, mode: str, signal_keys: str, net: float) -> dict[str, object]:
        return {"portfolio_set": name, "portfolio_mode": mode, "priority_policy": name, "pruning_variant": name, "signals": len(signal_keys.split(';')), "signal_keys": signal_keys, "net_pnl": net, "validation_pnl": 1, "holdout_pnl": 1, "walk_forward_test_pnl": net, "walk_forward_stress_pnl": net, "positive_wf_test_folds_pct": 0.833333, "worst_wf_test_fold": 1, "trades": 2, "active_days": 2, "trades_per_active_day": 1, "max_drawdown": -1, "best_day_concentration": 0.2, "best_trade_concentration": 0.1, "top_3_day_concentration": 0.5, "top_5_trade_concentration": 0.5, "skipped_overlap_count": 0, "skipped_session_count": 0, "paper_trading_approved": False}

    def _trade(self, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"candidate_id": cid, "phase": phase, "signal_key": f"{phase}::{cid}", "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "stress_pnl": pnl - 1, "gross_pnl": pnl, "split": "validation" if session <= "2026-01-01" else "holdout"}


if __name__ == "__main__":
    unittest.main()
