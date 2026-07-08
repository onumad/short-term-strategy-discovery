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

from short_term_edge.playbook_scheduler_b_priority_retest import PHASES, construct_scheduled_trades  # noqa: E402
from short_term_edge.playbook_scheduler_d_overlay_retest import (  # noqa: E402
    DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED,
    LIVE_TRADING_APPROVED,
    MODES,
    OFFICIAL_GATES_CHANGED,
    OVERLAY_VARIANTS,
    PAPER_TRADING_APPROVED,
    PRIORITY_POLICIES,
    REGISTRY_MUTATION,
    SEED_SUSPECT_MODULE,
    apply_overlay_priority,
    build_scheduler_d_overlay_variants,
    identify_seed_suspect_cluster,
    load_playbook_scheduler_d_inputs,
    render_playbook_scheduler_d_report,
    run_playbook_scheduler_d_overlay_retest,
    validate_overlay_guardrails,
    write_playbook_scheduler_d_outputs,
)


class PlaybookSchedulerDOverlayRetestTests(unittest.TestCase):
    def test_loads_dedup_overlay_json_and_scheduler_c_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            data = load_playbook_scheduler_d_inputs(out)
            self.assertIn("dedup_overlay", data)
            self.assertIn("scheduler_c_results", data)
            self.assertFalse(data["dedup_overlay"]["registry_mutation"])

    def test_overlay_variants_are_deterministic(self) -> None:
        keys = self._keys()
        overlay = self._overlay(keys)
        selected = pd.DataFrame({"signal_key": keys, "phase": [k.split("::", 1)[0] for k in keys]})
        seed = identify_seed_suspect_cluster(keys)
        first = build_scheduler_d_overlay_variants(selected, keys, overlay, seed)
        second = build_scheduler_d_overlay_variants(selected, keys, overlay, seed)
        self.assertEqual(first, second)
        self.assertEqual(tuple(first), OVERLAY_VARIANTS)

    def test_overlay_priority_only_keeps_all_modules(self) -> None:
        keys = self._keys()
        variants = build_scheduler_d_overlay_variants(pd.DataFrame({"signal_key": keys}), keys, self._overlay(keys), identify_seed_suspect_cluster(keys))
        self.assertEqual(variants["overlay_priority_only"], keys)

    def test_overlay_exclude_parked_removes_only_parked_modules(self) -> None:
        keys = self._keys()
        overlay = self._overlay(keys)
        variants = build_scheduler_d_overlay_variants(pd.DataFrame({"signal_key": keys}), keys, overlay, identify_seed_suspect_cluster(keys))
        removed = set(keys) - set(variants["overlay_exclude_parked"])
        self.assertEqual(removed, set(overlay["modules_to_park"]))

    def test_overlay_keep_representatives_plus_diversifiers_keeps_reps_and_diversifiers(self) -> None:
        keys = self._keys()
        overlay = self._overlay(keys)
        variants = build_scheduler_d_overlay_variants(pd.DataFrame({"signal_key": keys}), keys, overlay, identify_seed_suspect_cluster(keys))
        kept = set(variants["overlay_keep_representatives_plus_diversifiers"])
        self.assertTrue(set(overlay["modules_to_keep"]).issubset(kept))
        self.assertIn("phase13a::div13", kept)
        self.assertIn("phase14a::div14", kept)
        self.assertIn("phase15a::div15", kept)
        self.assertFalse(set(overlay["modules_to_park"]).intersection(kept))

    def test_seed_cluster_deprioritized_keeps_seed_modules_but_moves_last(self) -> None:
        keys = self._keys()
        overlay = self._overlay(keys)
        seed = identify_seed_suspect_cluster(keys)
        variants = build_scheduler_d_overlay_variants(pd.DataFrame({"signal_key": keys}), keys, overlay, seed)
        self.assertTrue(set(seed).issubset(set(variants["overlay_seed_cluster_deprioritized"])))
        order = apply_overlay_priority({k: i for i, k in enumerate(keys)}, "overlay_seed_cluster_deprioritized", overlay, seed, pd.DataFrame())
        self.assertGreater(min(order[k] for k in seed), max(order[k] for k in keys if k not in seed))

    def test_seed_cluster_excluded_removes_only_seed_cluster_modules(self) -> None:
        keys = self._keys()
        seed = identify_seed_suspect_cluster(keys)
        variants = build_scheduler_d_overlay_variants(pd.DataFrame({"signal_key": keys}), keys, self._overlay(keys), seed)
        self.assertEqual(set(keys) - set(variants["overlay_seed_cluster_excluded"]), set(seed))

    def test_registries_are_not_mutated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            before_module = (out / "playbook_module_registry.csv").read_bytes()
            before_signal = (out / "research_signal_registry.csv").read_bytes()
            result = run_playbook_scheduler_d_overlay_retest(out)
            write_playbook_scheduler_d_outputs(result, out, out / "report.md")
            self.assertEqual(before_module, (out / "playbook_module_registry.csv").read_bytes())
            self.assertEqual(before_signal, (out / "research_signal_registry.csv").read_bytes())
            self.assertFalse(bool(result["policy_results"]["registry_mutation"].any()))

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

    def test_guardrails_official_gates_no_paper_no_live_and_no_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            result = run_playbook_scheduler_d_overlay_retest(out)
            rows = result["policy_results"]
            self.assertFalse(OFFICIAL_GATES_CHANGED)
            self.assertFalse(PAPER_TRADING_APPROVED)
            self.assertFalse(LIVE_TRADING_APPROVED)
            self.assertFalse(REGISTRY_MUTATION)
            self.assertTrue(DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED)
            self.assertFalse(bool(rows["official_gates_changed"].any()))
            self.assertFalse(bool(rows["paper_trading_approved"].any()))
            self.assertFalse(bool(rows["live_trading_approved"].any()))
            self.assertTrue(bool(rows["diagnostic_only_no_signals_generated"].all()))
            self.assertFalse(bool(rows["raw_sum_diagnostic_used_as_candidate"].any()))
            self.assertFalse(result["next_action_recommendation"]["paper_trading_approved"])
            self.assertEqual(len(rows), len(OVERLAY_VARIANTS) * len(PRIORITY_POLICIES) * len(MODES))

    def test_overlay_guardrails_fail_closed(self) -> None:
        overlay = self._overlay(self._keys())
        overlay["paper_trading_approved"] = True
        with self.assertRaises(ValueError):
            validate_overlay_guardrails(overlay)

    def test_report_includes_research_only_no_live_trading_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self._write_inputs(out)
            report = render_playbook_scheduler_d_report(run_playbook_scheduler_d_overlay_retest(out))
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

    def _overlay(self, keys: list[str]) -> dict[str, object]:
        return {
            "overlay_version": "test",
            "registry_mutation": False,
            "official_gates_changed": False,
            "paper_trading_approved": False,
            "live_trading_approved": False,
            "diagnostic_only_no_signals_generated": True,
            "modules_to_keep": [keys[0], keys[6]],
            "modules_to_deprioritize": [keys[1], keys[2]],
            "modules_to_park": [keys[4], keys[5]],
            "cluster_representatives": {"c1": keys[0]},
        }

    def _write_inputs(self, out: Path) -> list[str]:
        out.mkdir(parents=True, exist_ok=True)
        keys = self._keys()
        modules = pd.DataFrame([self._module(k, i) for i, k in enumerate(keys, start=1)])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.assign(signal_key=modules["phase"] + "::" + modules["candidate_id"]).to_csv(out / "research_signal_registry.csv", index=False)
        overlay = self._overlay(keys)
        (out / "playbook_module_deduplication_b_scheduler_overlay.json").write_text(json.dumps(overlay), encoding="utf-8")
        pd.DataFrame([{"cluster_id": "c1", "members": ";".join(keys[:4]), "is_phase10b_seed_cluster": True}]).to_csv(out / "playbook_module_deduplication_b_redundancy_clusters.csv", index=False)
        pd.DataFrame([{"signal_key": k, "average_correlation": 0.1, "scheduler_b_accepted_net_pnl": 1, "scheduler_c_accepted_net_pnl": 1, "weak_fold_harm": False} for k in keys]).to_csv(out / "playbook_module_deduplication_b_module_review.csv", index=False)
        pd.DataFrame([{"signal_key": k} for k in overlay["modules_to_keep"]]).to_csv(out / "playbook_module_deduplication_b_representative_modules.csv", index=False)
        pd.DataFrame([{"signal_key": k} for k in overlay["modules_to_deprioritize"]]).to_csv(out / "playbook_module_deduplication_b_deprioritization_candidates.csv", index=False)
        (out / "playbook_module_deduplication_b_next_action_recommendation.json").write_text(json.dumps({"next_action": "playbook_scheduler_d_overlay_retest", "paper_trading_approved": False}), encoding="utf-8")
        signal_keys = ";".join(keys)
        c_rows = []
        for policy in PRIORITY_POLICIES:
            for mode in MODES:
                c_rows.append(self._result_row("no_pruning_baseline", policy, mode, signal_keys, 5, 0.5, 0.7, 0.7, "scheduler_c_no_improvement"))
        pd.DataFrame(c_rows).to_csv(out / "playbook_scheduler_c_pruning_policy_results.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "trading_session": "2026-01-01", "net_pnl": 1}]).to_csv(out / "playbook_scheduler_c_daily_pnl.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "fold": 1, "net_pnl": 1, "stress_pnl": -1, "active_days": 1}]).to_csv(out / "playbook_scheduler_c_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "best_day_concentration": 0.7, "best_trade_concentration": 0.7}]).to_csv(out / "playbook_scheduler_c_concentration.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "accepted_trades": 1, "skipped_overlap_count": 0, "skipped_session_count": 0}]).to_csv(out / "playbook_scheduler_c_overlap_summary.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "priority_policy": PRIORITY_POLICIES[0], "portfolio_mode": MODES[0], "signal_key": k, "priority_rank": i} for i, k in enumerate(keys)]).to_csv(out / "playbook_scheduler_c_module_acceptance_summary.csv", index=False)
        pd.DataFrame([{"pruning_variant": "no_pruning_baseline", "kept_module_count": len(keys), "removed_module_count": 0}]).to_csv(out / "playbook_scheduler_c_pruned_module_summary.csv", index=False)
        (out / "playbook_scheduler_c_next_action_recommendation.json").write_text(json.dumps({"next_action": "playbook_module_deduplication_b_review", "paper_trading_approved": False}), encoding="utf-8")
        b_rows = []
        for policy in PRIORITY_POLICIES:
            for mode in MODES:
                row = self._result_row("", policy, mode, signal_keys, 4, 0.5, 0.8, 0.8, "scheduler_b_no_improvement")
                row.pop("pruning_variant")
                row["diagnostic_filter"] = "no_filter_baseline"
                b_rows.append(row)
        pd.DataFrame(b_rows).to_csv(out / "playbook_scheduler_b_priority_policy_results.csv", index=False)
        pd.DataFrame(columns=["priority_policy", "portfolio_mode", "diagnostic_filter", "trading_session", "net_pnl"]).to_csv(out / "playbook_scheduler_b_daily_pnl.csv", index=False)
        pd.DataFrame(columns=["priority_policy", "portfolio_mode", "diagnostic_filter", "fold", "net_pnl", "stress_pnl", "active_days"]).to_csv(out / "playbook_scheduler_b_walk_forward_folds.csv", index=False)
        pd.DataFrame(columns=["priority_policy", "portfolio_mode", "diagnostic_filter", "best_day_concentration", "best_trade_concentration"]).to_csv(out / "playbook_scheduler_b_concentration.csv", index=False)
        pd.DataFrame([{"signal_key": k} for k in keys]).to_csv(out / "playbook_scheduler_b_module_acceptance_summary.csv", index=False)
        a_rows = [self._result_row("no_pruning_baseline", PRIORITY_POLICIES[0], MODES[0], signal_keys, 3, 0.5, 0.8, 0.8, "pruning_a_no_improvement")]
        pd.DataFrame(a_rows).to_csv(out / "module_pruning_audit_a_portfolio_results.csv", index=False)
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
        role = "diversifier_module" if phase in {"phase13a", "phase14a", "phase15a"} else "core_module"
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "portfolio_role": role, "research_track": "rare_setup_research_signal", "official_gates_passed": False, "paper_trading_approved": False, "net_pnl": 100-rank, "stress_pnl": 90-rank, "validation_pnl": 10, "holdout_pnl": 5, "walk_forward_stress_pnl": 5, "positive_wf_test_folds_pct": 0.5, "trades": 6, "active_days": 6, "best_day_concentration": 0.2 + rank / 100, "best_trade_concentration": 0.2 + rank / 100, "average_correlation_to_registry": 0.1, "source_report": "existing"}

    def _result_row(self, variant: str, policy: str, mode: str, signal_keys: str, net: float, folds: float, day_conc: float, trade_conc: float, label: str) -> dict[str, object]:
        return {"pruning_variant": variant, "priority_policy": policy, "portfolio_mode": mode, "signals": len(signal_keys.split(';')), "signal_keys": signal_keys, "net_pnl": net, "validation_pnl": 1, "holdout_pnl": 1, "walk_forward_test_pnl": net, "walk_forward_stress_pnl": net, "positive_wf_test_folds_pct": folds, "worst_wf_test_fold": -1, "trades": 6, "active_days": 6, "trades_per_active_day": 1, "max_drawdown": -1, "best_day_concentration": day_conc, "best_trade_concentration": trade_conc, "top_3_day_concentration": 1, "top_5_trade_concentration": 1, "skipped_overlap_count": 0, "skipped_session_count": 0, "weak_fold_count": 1, "weak_fold_pnl": -1, "removed_module_count": 0, "removed_modules": "", "scheduler_c_label": label, "official_gates_changed": False, "paper_trading_approved": False, "diagnostic_only_no_signals_generated": True, "raw_sum_diagnostic_used_as_candidate": False}

    def _trade(self, phase: str, cid: str, entry: str, exit_: str, session: str, pnl: float) -> dict[str, object]:
        return {"candidate_id": cid, "phase": phase, "signal_key": f"{phase}::{cid}", "entry_time": entry, "exit_time": exit_, "trading_session": session, "net_pnl": pnl, "stress_pnl": pnl - 1, "gross_pnl": pnl, "split": "validation" if session <= "2026-01-03" else "holdout"}


if __name__ == "__main__":
    unittest.main()
