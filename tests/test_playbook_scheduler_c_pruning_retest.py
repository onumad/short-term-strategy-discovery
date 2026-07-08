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

from short_term_edge.playbook_scheduler_c_pruning_retest import (  # noqa: E402
    DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED,
    MODES,
    OFFICIAL_GATES_CHANGED,
    PAPER_TRADING_APPROVED,
    PRIORITY_POLICIES,
    PRUNING_VARIANTS,
    SEED_SUSPECT_MODULE,
    build_priority_policy_orders,
    construct_scheduled_trades,
    deprioritize_modules,
    identify_seed_suspect_cluster,
    load_playbook_scheduler_c_inputs,
    reconstruct_high_redundancy_pairs,
    render_playbook_scheduler_c_report,
    run_playbook_scheduler_c_pruning_retest,
    write_playbook_scheduler_c_outputs,
)
from short_term_edge.playbook_scheduler_b_priority_retest import PHASES  # noqa: E402


class PlaybookSchedulerCPruningRetestTests(unittest.TestCase):
    def test_loads_module_pruning_a_and_scheduler_b_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            keys = self._write_inputs(out)
            data = load_playbook_scheduler_c_inputs(out)
            self.assertIn("module_pruning_results", data)
            self.assertIn("module_pruning_redundancy_pairs", data)
            self.assertIn("scheduler_b_results", data)
            self.assertEqual(len(keys), 9)

    def test_identifies_seed_suspect_cluster_deterministically(self) -> None:
        keys = self._keys()
        cluster1 = identify_seed_suspect_cluster(keys)
        cluster2 = identify_seed_suspect_cluster(keys)
        self.assertEqual(cluster1, cluster2)
        self.assertEqual(len(cluster1), 4)
        self.assertIn(SEED_SUSPECT_MODULE, cluster1)

    def test_reconstructs_remove_high_redundancy_pairs_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            keys = self._write_inputs(out)
            data = load_playbook_scheduler_c_inputs(out)
            selected = data["module_pruning_diagnostics"].copy()
            selected["scheduler_b_best_rank"] = range(len(selected))
            matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02"]})
            for key in keys:
                matrix[key] = [1, 2]
            first = reconstruct_high_redundancy_pairs(selected, matrix, data["module_pruning_redundancy_pairs"])
            second = reconstruct_high_redundancy_pairs(selected, matrix, data["module_pruning_redundancy_pairs"])
            pd.testing.assert_frame_equal(first, second)
            self.assertIn("lower_ranked_module", first.columns)
            self.assertFalse(first.empty)

    def test_pruning_variants_do_not_mutate_registry_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            before_module = (out / "playbook_module_registry.csv").read_bytes()
            before_signal = (out / "research_signal_registry.csv").read_bytes()
            result = run_playbook_scheduler_c_pruning_retest(out)
            write_playbook_scheduler_c_outputs(result, out, out / "report.md")
            self.assertEqual(before_module, (out / "playbook_module_registry.csv").read_bytes())
            self.assertEqual(before_signal, (out / "research_signal_registry.csv").read_bytes())

    def test_deprioritize_variant_keeps_modules_but_changes_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_c_pruning_retest(out)
            summary = result["pruned_module_summary"]
            row = summary[summary["pruning_variant"].eq("deprioritize_seed_cluster")].iloc[0]
            self.assertEqual(int(row["removed_module_count"]), 0)
            self.assertGreater(int(row["deprioritized_module_count"]), 0)
            acc = result["module_acceptance_summary"]
            seg = acc[(acc["pruning_variant"].eq("deprioritize_seed_cluster")) & (acc["priority_policy"].eq(PRIORITY_POLICIES[0])) & (acc["portfolio_mode"].eq(MODES[0]))]
            self.assertTrue(bool(seg[seg["module_deprioritized"]]["priority_rank"].min() > seg[~seg["module_deprioritized"]]["priority_rank"].max()))
            base_order = {key: i for i, key in enumerate(self._keys())}
            moved = deprioritize_modules(base_order, identify_seed_suspect_cluster(self._keys()))
            self.assertGreater(moved[SEED_SUSPECT_MODULE], base_order[SEED_SUSPECT_MODULE])

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

    def test_guardrails_official_gates_no_paper_no_signals_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_c_pruning_retest(out)
            rows = result["policy_results"]
            self.assertFalse(OFFICIAL_GATES_CHANGED)
            self.assertFalse(PAPER_TRADING_APPROVED)
            self.assertTrue(DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED)
            self.assertFalse(bool(rows["official_gates_changed"].any()))
            self.assertFalse(bool(rows["paper_trading_approved"].any()))
            self.assertTrue(bool(rows["diagnostic_only_no_signals_generated"].all()))
            self.assertFalse(bool(rows["raw_sum_diagnostic_used_as_candidate"].any()))
            self.assertFalse(result["next_action_recommendation"]["paper_trading_approved"])
            self.assertFalse(result["next_action_recommendation"]["official_gates_changed"])
            self.assertEqual(len(rows), len(PRUNING_VARIANTS) * len(PRIORITY_POLICIES) * len(MODES))
            report = render_playbook_scheduler_c_report(result)
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("No new signals", report)
            self.assertIn("Registry files mutated: `false`", report)
            self.assertIn("Weak-fold-derived regime filters used: `false`", report)

    def _keys(self) -> list[str]:
        seed_base = SEED_SUSPECT_MODULE.rsplit("_", 1)[0]
        return [
            SEED_SUSPECT_MODULE,
            f"{seed_base}_mt2",
            SEED_SUSPECT_MODULE.replace("first_touch_only_mt1", "all_touches_mt1"),
            SEED_SUSPECT_MODULE.replace("first_touch_only_mt1", "all_touches_mt2"),
            "phase11a::core11",
            "phase12a::core12",
            "phase13a::div13",
            "phase14a::div14",
            "phase15a::div15",
        ]

    def _write_inputs(self, out: Path) -> list[str]:
        out.mkdir(parents=True, exist_ok=True)
        keys = self._keys()
        modules = pd.DataFrame([self._module(k, i) for i, k in enumerate(keys, start=1)])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        diag = modules.copy()
        diag.insert(0, "selection_rank", range(1, len(diag) + 1))
        diag["scheduler_b_best_rank"] = range(len(diag))
        diag["average_daily_correlation_to_other_modules"] = [0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1]
        diag.to_csv(out / "module_pruning_audit_a_module_diagnostics.csv", index=False)
        signal_keys = ";".join(keys)
        pd.DataFrame([
            {"pruning_variant": "remove_high_redundancy_pairs", "kept_module_count": 7, "removed_module_count": 2, "removed_modules": ";".join(keys[1:3])},
            {"pruning_variant": "no_pruning_baseline", "kept_module_count": len(keys), "removed_module_count": 0, "removed_modules": ""},
        ]).to_csv(out / "module_pruning_audit_a_pruning_variants.csv", index=False)
        a_rows = []
        for policy in PRIORITY_POLICIES:
            for mode in MODES:
                a_rows.append(self._result_row("no_pruning_baseline", policy, mode, signal_keys, 10, 0.5, 0.5, 0.5, "pruning_a_no_improvement"))
        pd.DataFrame(a_rows).to_csv(out / "module_pruning_audit_a_portfolio_results.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "module_pruning_audit_a_daily_pnl.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "module_pruning_audit_a_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "best_day_concentration": 0.5, "best_trade_concentration": 0.5}]).to_csv(out / "module_pruning_audit_a_concentration.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "accepted_trades": 1, "skipped_overlap_count": 0, "skipped_session_count": 0}]).to_csv(out / "module_pruning_audit_a_overlap_summary.csv", index=False)
        pd.DataFrame([
            {"signal_a": keys[0], "signal_b": keys[1], "daily_pnl_correlation": 1.0, "paired_duplicate_variant": True, "high_redundancy_pair": True, "lower_ranked_module": keys[1], "dedupe_reason": "paired_duplicate_variant"},
            {"signal_a": keys[2], "signal_b": keys[3], "daily_pnl_correlation": 1.0, "paired_duplicate_variant": True, "high_redundancy_pair": True, "lower_ranked_module": keys[3], "dedupe_reason": "paired_duplicate_variant"},
        ]).to_csv(out / "module_pruning_audit_a_redundancy_pairs.csv", index=False)
        (out / "module_pruning_audit_a_next_action_recommendation.json").write_text(json.dumps({"next_action": "playbook_scheduler_c_pruning_retest", "paper_trading_approved": False}), encoding="utf-8")
        b_rows = []
        for policy in PRIORITY_POLICIES:
            for mode in MODES:
                b_rows.append(self._scheduler_b_row(policy, mode, signal_keys))
        pd.DataFrame(b_rows).to_csv(out / "playbook_scheduler_b_priority_policy_results.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "playbook_scheduler_b_daily_pnl.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "fold": 1, "net_pnl": 1, "stress_pnl": -1, "active_days": 1}]).to_csv(out / "playbook_scheduler_b_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "best_day_concentration": 0.5, "best_trade_concentration": 0.5}]).to_csv(out / "playbook_scheduler_b_concentration.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "accepted_trades": 1, "skipped_overlap_count": 0, "skipped_session_count": 0}]).to_csv(out / "playbook_scheduler_b_overlap_summary.csv", index=False)
        pd.DataFrame([{"priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "diagnostic_filter": "no_filter_baseline", "signal_key": k, "accepted_trade_count": 1, "accepted_net_pnl": 1, "skipped_trade_count": 0, "skipped_net_pnl": 0} for k in keys]).to_csv(out / "playbook_scheduler_b_module_acceptance_summary.csv", index=False)
        (out / "playbook_scheduler_b_next_action_recommendation.json").write_text(json.dumps({"next_action": "module_pruning_audit_a", "paper_trading_approved": False}), encoding="utf-8")
        for phase in PHASES:
            rows = []
            for key in keys:
                ph, cid = key.split("::", 1)
                if ph != phase:
                    continue
                for i, day in enumerate(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"], start=1):
                    pnl = -5 if key == SEED_SUSPECT_MODULE else i
                    rows.append(self._trade(ph, cid, f"{day} 09:{30+i:02d}", f"{day} 10:{30+i:02d}", day, pnl))
            pd.DataFrame(rows).to_csv(out / f"{phase}_trade_logs.csv", index=False)
        return keys

    def _module(self, key: str, rank: int) -> dict[str, object]:
        phase, cid = key.split("::", 1)
        role = "diversifier_module" if phase in {"phase13a", "phase14a", "phase15a"} else "parked_module"
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "signal_key": key, "portfolio_role": role, "research_track": "parked_research_signal", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": 100-rank, "stress_pnl": 90-rank, "validation_pnl": 10, "holdout_pnl": 5, "walk_forward_stress_pnl": 5, "positive_wf_test_folds_pct": 0.5, "trades": 6, "active_days": 6, "best_day_concentration": 0.2 + rank / 100, "best_trade_concentration": 0.2 + rank / 100, "prior_score": 100-rank, "source_report": "existing"}

    def _scheduler_b_row(self, policy: str, mode: str, signal_keys: str) -> dict[str, object]:
        row = self._result_row("", policy, mode, signal_keys, 5, 0.5, 0.7, 0.7, "scheduler_b_no_improvement")
        row.pop("pruning_variant")
        row.pop("scheduler_c_label", None)
        row["diagnostic_filter"] = "no_filter_baseline"
        return row

    def _result_row(self, variant: str, policy: str, mode: str, signal_keys: str, net: float, folds: float, day_conc: float, trade_conc: float, label: str) -> dict[str, object]:
        return {"pruning_variant": variant, "priority_policy": policy, "portfolio_mode": mode, "signals": len(signal_keys.split(';')), "signal_keys": signal_keys, "net_pnl": net, "validation_pnl": 1, "holdout_pnl": 1, "walk_forward_test_pnl": net, "walk_forward_stress_pnl": net, "positive_wf_test_folds_pct": folds, "worst_wf_test_fold": -1, "trades": 6, "active_days": 6, "trades_per_active_day": 1, "max_drawdown": -1, "best_day_concentration": day_conc, "best_trade_concentration": trade_conc, "top_3_day_concentration": 1, "top_5_trade_concentration": 1, "skipped_overlap_count": 0, "skipped_session_count": 0, "weak_fold_count": 1, "weak_fold_pnl": -1, "removed_module_count": 0, "removed_modules": "", "scheduler_c_label": label, "official_gates_changed": False, "paper_trading_approved": False, "diagnostic_only_no_signals_generated": True, "raw_sum_diagnostic_used_as_candidate": False}

    def _trade(self, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"candidate_id": cid, "phase": phase, "signal_key": f"{phase}::{cid}", "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "stress_pnl": pnl - 1, "gross_pnl": pnl, "split": "validation" if session <= "2026-01-03" else "holdout"}


if __name__ == "__main__":
    unittest.main()
