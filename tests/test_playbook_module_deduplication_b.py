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

from short_term_edge.playbook_module_deduplication_b import (  # noqa: E402
    DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED,
    OFFICIAL_GATES_CHANGED,
    PAPER_TRADING_APPROVED,
    SEED_SUSPECT_MODULE,
    build_redundancy_clusters,
    identify_seed_suspect_cluster,
    load_playbook_module_deduplication_b_inputs,
    render_playbook_module_deduplication_b_report,
    run_playbook_module_deduplication_b,
    select_representative_modules,
    write_playbook_module_deduplication_b_outputs,
)
from short_term_edge.playbook_scheduler_b_priority_retest import PHASES  # noqa: E402


class PlaybookModuleDeduplicationBTests(unittest.TestCase):
    def test_loads_module_registry_redundancy_pairs_and_scheduler_c_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            keys = self._write_inputs(out)
            data = load_playbook_module_deduplication_b_inputs(out)
            self.assertIn("playbook_module_registry", data)
            self.assertIn("module_pruning_redundancy_pairs", data)
            self.assertIn("scheduler_c_results", data)
            self.assertEqual(len(keys), 9)

    def test_identifies_seed_suspect_cluster_deterministically(self) -> None:
        keys = self._keys()
        first = identify_seed_suspect_cluster(keys)
        second = identify_seed_suspect_cluster(keys)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)
        self.assertIn(SEED_SUSPECT_MODULE, first)

    def test_builds_redundancy_clusters_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            first = run_playbook_module_deduplication_b(out)["redundancy_clusters"]
            second = run_playbook_module_deduplication_b(out)["redundancy_clusters"]
            pd.testing.assert_frame_equal(first, second)
            self.assertGreaterEqual(len(first), 1)
            self.assertTrue(bool(first["is_phase10b_seed_cluster"].any()))

    def test_selects_representatives_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = run_playbook_module_deduplication_b(self._write_inputs(out) and out)
            reps = result["representative_modules"]
            self.assertFalse(reps.empty)
            self.assertEqual(len(reps), reps["cluster_id"].nunique())
            seed_rows = reps[reps["cluster_members"].str.contains("first_touch_only_mt1", regex=False)]
            self.assertFalse(seed_rows.empty)

    def test_produces_overlay_without_mutating_registries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            before_module = (out / "playbook_module_registry.csv").read_bytes()
            before_signal = (out / "research_signal_registry.csv").read_bytes()
            result = run_playbook_module_deduplication_b(out)
            write_playbook_module_deduplication_b_outputs(result, out, out / "report.md")
            self.assertEqual(before_module, (out / "playbook_module_registry.csv").read_bytes())
            self.assertEqual(before_signal, (out / "research_signal_registry.csv").read_bytes())
            overlay = result["scheduler_overlay"]
            self.assertFalse(overlay["registry_mutation"])
            self.assertFalse(overlay["official_gates_changed"])
            self.assertFalse(overlay["paper_trading_approved"])
            self.assertTrue(overlay["diagnostic_only_no_signals_generated"])
            self.assertIn("modules_to_deprioritize", overlay)

    def test_no_new_signals_and_report_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_module_deduplication_b(out)
            self.assertFalse(OFFICIAL_GATES_CHANGED)
            self.assertFalse(PAPER_TRADING_APPROVED)
            self.assertTrue(DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED)
            overlay = result["scheduler_overlay"]
            self.assertTrue(overlay["diagnostic_only_no_signals_generated"])
            report = render_playbook_module_deduplication_b_report(result)
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertIn("No new signals", report)
            self.assertIn("Official gates changed: `false`", report)
            self.assertIn("Paper trading approved: `false`", report)

    def _keys(self) -> list[str]:
        seed_base = SEED_SUSPECT_MODULE.rsplit("_", 1)[0]
        return [
            SEED_SUSPECT_MODULE,
            f"{seed_base}_mt2",
            SEED_SUSPECT_MODULE.replace("first_touch_only_mt1", "all_touches_mt1"),
            SEED_SUSPECT_MODULE.replace("first_touch_only_mt1", "all_touches_mt2"),
            "phase11a::core11_long_rule_mt1",
            "phase11a::core11_long_rule_mt2",
            "phase12a::core12",
            "phase13a::div13",
            "phase15a::div15",
        ]

    def _write_inputs(self, out: Path) -> list[str]:
        out.mkdir(parents=True, exist_ok=True)
        keys = self._keys()
        modules = pd.DataFrame([self._module(k, i) for i, k in enumerate(keys, start=1)])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        research = modules[["phase", "candidate_id", "plain_english_rule", "net_pnl", "stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl", "positive_wf_test_folds_pct", "trades", "active_days", "best_day_concentration", "best_trade_concentration", "signal_evidence_status", "tradability_status", "research_track", "source_report"]].copy()
        research["family"] = modules["source_family"]
        research["bootstrap_or_null_classification"] = "existing_signal"
        research["revisit_condition"] = "review"
        research.to_csv(out / "research_signal_registry.csv", index=False)
        diag = modules[["signal_key", "phase", "candidate_id"]].copy()
        diag["scheduler_b_net_contribution"] = [10, -2, 8, -1, 5, -3, 4, 6, 7]
        diag["accepted_trade_count"] = [3] * len(keys)
        diag["accepted_net_pnl"] = [10, -2, 8, -1, 5, -3, 4, 6, 7]
        diag["contribution_in_weak_folds"] = [1, -2, 1, -1, 0, -3, 0, 1, 1]
        diag["average_daily_correlation_to_other_modules"] = [0.9, 0.9, 0.9, 0.9, 0.4, 0.4, 0.1, 0.1, 0.1]
        diag["max_daily_correlation_to_other_modules"] = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.2, 0.2, 0.2]
        diag["overlap_rate_with_other_modules"] = [0.8, 0.8, 0.8, 0.8, 0.2, 0.2, 0.1, 0.1, 0.1]
        diag["harmful_when_accepted"] = [False, True, False, True, False, True, False, False, False]
        diag["seed_suspect"] = [k == SEED_SUSPECT_MODULE for k in keys]
        diag.to_csv(out / "module_pruning_audit_a_module_diagnostics.csv", index=False)
        pd.DataFrame([{"pruning_variant": "remove_high_redundancy_pairs", "kept_module_count": 6, "removed_module_count": 3, "removed_modules": ";".join([keys[1], keys[3], keys[5]])}]).to_csv(out / "module_pruning_audit_a_pruning_variants.csv", index=False)
        pd.DataFrame([{"pruning_variant": "remove_high_redundancy_pairs", "priority_policy": "hybrid", "portfolio_mode": "max_one_trade_per_session", "net_pnl": 10, "positive_wf_test_folds_pct": 0.833, "best_day_concentration": 0.3, "best_trade_concentration": 0.3}]).to_csv(out / "module_pruning_audit_a_portfolio_results.csv", index=False)
        pd.DataFrame([
            {"signal_a": keys[0], "signal_b": keys[1], "daily_pnl_correlation": 1.0, "paired_duplicate_variant": True, "high_redundancy_pair": True, "lower_ranked_module": keys[1], "dedupe_reason": "paired_duplicate_variant"},
            {"signal_a": keys[2], "signal_b": keys[3], "daily_pnl_correlation": 1.0, "paired_duplicate_variant": True, "high_redundancy_pair": True, "lower_ranked_module": keys[3], "dedupe_reason": "paired_duplicate_variant"},
            {"signal_a": keys[4], "signal_b": keys[5], "daily_pnl_correlation": 1.0, "paired_duplicate_variant": True, "high_redundancy_pair": True, "lower_ranked_module": keys[5], "dedupe_reason": "paired_duplicate_variant"},
        ]).to_csv(out / "module_pruning_audit_a_redundancy_pairs.csv", index=False)
        (out / "module_pruning_audit_a_next_action_recommendation.json").write_text(json.dumps({"next_action": "playbook_scheduler_c_pruning_retest", "paper_trading_approved": False}), encoding="utf-8")
        pd.DataFrame([{"pruning_variant": "remove_high_redundancy_pairs", "priority_policy": "hybrid", "portfolio_mode": "max_one_trade_per_session", "signals": 6, "net_pnl": 20, "positive_wf_test_folds_pct": 0.833, "best_day_concentration": 0.25, "best_trade_concentration": 0.25, "scheduler_c_label": "scheduler_c_improves_folds_and_concentration"}]).to_csv(out / "playbook_scheduler_c_pruning_policy_results.csv", index=False)
        pd.DataFrame([{"pruning_variant": "remove_high_redundancy_pairs", "priority_policy": "hybrid", "portfolio_mode": "max_one_trade_per_session", "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "playbook_scheduler_c_daily_pnl.csv", index=False)
        pd.DataFrame([{"pruning_variant": "remove_high_redundancy_pairs", "priority_policy": "hybrid", "portfolio_mode": "max_one_trade_per_session", "fold": 1, "net_pnl": 1, "stress_pnl": 1, "active_days": 1}]).to_csv(out / "playbook_scheduler_c_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"pruning_variant": "remove_high_redundancy_pairs", "priority_policy": "hybrid", "portfolio_mode": "max_one_trade_per_session", "best_day_concentration": 0.25, "best_trade_concentration": 0.25}]).to_csv(out / "playbook_scheduler_c_concentration.csv", index=False)
        pd.DataFrame([{"pruning_variant": "remove_high_redundancy_pairs", "priority_policy": "hybrid", "portfolio_mode": "max_one_trade_per_session", "accepted_trades": 1, "skipped_overlap_count": 0, "skipped_session_count": 0}]).to_csv(out / "playbook_scheduler_c_overlap_summary.csv", index=False)
        acceptance = pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": "hybrid", "portfolio_mode": "max_one_trade_per_session", "priority_rank": i, "phase": k.split("::", 1)[0], "candidate_id": k.split("::", 1)[1], "signal_key": k, "module_kept": True, "module_removed": False, "module_deprioritized": False, "accepted_trade_count": 1, "accepted_net_pnl": pnl, "skipped_trade_count": 0, "skipped_net_pnl": 0} for i, (k, pnl) in enumerate(zip(keys, [10, -2, 8, -1, 5, -3, 4, 6, 7]))])
        acceptance.to_csv(out / "playbook_scheduler_c_module_acceptance_summary.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "kept_module_count": len(keys), "removed_module_count": 0, "deprioritized_module_count": 0, "removed_modules": "", "deprioritized_modules": "", "registry_files_mutated": False}]).to_csv(out / "playbook_scheduler_c_pruned_module_summary.csv", index=False)
        (out / "playbook_scheduler_c_next_action_recommendation.json").write_text(json.dumps({"next_action": "playbook_module_deduplication_b_review", "paper_trading_approved": False}), encoding="utf-8")
        b_acceptance = acceptance.rename(columns={"pruning_variant": "diagnostic_filter"}).copy()
        b_acceptance["diagnostic_filter"] = "no_filter_baseline"
        b_acceptance.to_csv(out / "playbook_scheduler_b_module_acceptance_summary.csv", index=False)
        (out / "playbook_scheduler_b_next_action_recommendation.json").write_text(json.dumps({"next_action": "module_pruning_audit_a", "paper_trading_approved": False}), encoding="utf-8")
        trade_columns = ["candidate_id", "phase", "signal_key", "entry_time", "exit_time", "trading_session", "net_pnl", "stress_pnl", "gross_pnl", "split"]
        for phase in PHASES:
            pd.DataFrame([self._trade(k) for k in keys if k.startswith(f"{phase}::")], columns=trade_columns).to_csv(out / f"{phase}_trade_logs.csv", index=False)
        return keys

    def _module(self, key: str, rank: int) -> dict[str, object]:
        phase, cid = key.split("::", 1)
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "signal_key": key, "source_family": "family", "market_condition": "condition", "module_family": "module_family", "portfolio_role": "diversifier_module" if phase in {"phase13a", "phase15a"} else "parked_module", "plain_english_rule": f"plain rule {rank}", "signal_evidence_status": "positive_research_signal", "tradability_status": "not_tradable_concentrated", "research_track": "parked_research_signal", "portfolio_contribution_status": "review", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": 100 - rank, "stress_pnl": 90 - rank, "validation_pnl": 10 if rank != 4 else -1, "holdout_pnl": 5, "walk_forward_stress_pnl": 5, "positive_wf_test_folds_pct": 0.5, "trades": 6, "active_days": 6, "best_day_concentration": 0.2 + rank / 100, "best_trade_concentration": 0.2 + rank / 100, "source_report": "existing"}

    def _trade(self, key: str) -> dict[str, object]:
        phase, cid = key.split("::", 1)
        return {"candidate_id": cid, "phase": phase, "signal_key": key, "entry_time": "2026-01-01 09:30", "exit_time": "2026-01-01 10:00", "trading_session": "2026-01-01", "net_pnl": 1, "stress_pnl": 1, "gross_pnl": 1, "split": "validation"}


if __name__ == "__main__":
    unittest.main()
