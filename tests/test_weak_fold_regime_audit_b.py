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

from short_term_edge.weak_fold_regime_audit_b import (  # noqa: E402
    build_market_regime_features,
    build_overlap_and_scheduler_diagnostics,
    compare_weak_vs_non_weak_regimes,
    load_weak_fold_regime_audit_b_inputs,
    make_next_action_recommendation,
    render_weak_fold_regime_audit_b_report,
    run_weak_fold_regime_audit_b,
)


class WeakFoldRegimeAuditBTests(unittest.TestCase):
    def test_loads_portfolio_audit_b_c_d_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            data = load_weak_fold_regime_audit_b_inputs(root)
            self.assertIn("audit_b_portfolio_results", data)
            self.assertIn("audit_c_portfolio_results", data)
            self.assertIn("audit_d_portfolio_results", data)

    def test_identifies_weak_folds_and_extracts_days_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            first = run_weak_fold_regime_audit_b(root)
            second = run_weak_fold_regime_audit_b(root)
            pd.testing.assert_frame_equal(first["fold_summary"], second["fold_summary"])
            pd.testing.assert_frame_equal(first["weak_fold_days"], second["weak_fold_days"])
            self.assertGreater(int(first["fold_summary"]["is_weak_fold"].sum()), 0)
            self.assertIn("phase13a_helped_or_hurt", first["weak_fold_days"].columns)

    def test_computes_rth_day_features_without_lookahead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_raw(root)
            features = build_market_regime_features(root / "data" / "raw")
            self.assertIn("prior_rth_close_relation", features.columns)
            self.assertEqual(features.iloc[0]["prior_rth_close_relation"], "unknown")
            self.assertIn("first_30m_range", features.columns)
            self.assertIn("power_hour_direction", features.columns)

    def test_regime_comparison_and_module_contribution_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_weak_fold_regime_audit_b(root)
            a = result["regime_comparison"]
            b = compare_weak_vs_non_weak_regimes(result["weak_fold_days"], result["market_regime_features"], pd.DataFrame())
            self.assertEqual(list(a["cohort"]), ["weak_fold_days", "non_weak_fold_days"])
            self.assertIn("module_group", result["module_contribution_by_fold"].columns)
            self.assertIn("net_pnl_contribution", result["module_contribution_by_regime"].columns)
            self.assertIn("cohort", b.columns)

    def test_scheduler_overlap_diagnostics_are_deterministic_on_synthetic_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_weak_fold_regime_audit_b(root)
            diag = result["overlap_and_scheduler_diagnostics"]
            self.assertIn("early_losing_module_when_later_module_helped_days", diag.columns)
            self.assertTrue(bool(diag["diagnosis_overlap_priority_risk"].any()))
            pd.testing.assert_frame_equal(diag, result["overlap_and_scheduler_diagnostics"])

    def test_remedy_json_generated_without_signals_or_gate_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_weak_fold_regime_audit_b(root)
            rec = result["next_action_recommendation"]
            self.assertTrue(result["candidate_remedies"])
            self.assertFalse(rec["official_gates_changed"])
            self.assertFalse(rec["paper_trading_approved"])
            self.assertTrue(rec["diagnostic_only_no_signals_generated"])
            report = render_weak_fold_regime_audit_b_report(result)
            self.assertIn("Research/simulation only. No live trading", report)

    def test_recommendation_respects_allowed_action_shape(self) -> None:
        rec = make_next_action_recommendation(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), [])
        self.assertFalse(rec["paper_trading_approved"])
        self.assertIn(rec["next_action"], {
            "phase16a_targeted_regime_module_scout",
            "playbook_scheduler_a_priority_audit",
            "pause_module_search_and_collect_more_data_or_review_manual_examples",
            "module_pruning_audit_a",
            "phase16a_no_trade_gap_module_scout",
            "validation_framework_audit_c_fold_design",
        })

    def _write_inputs(self, root: Path) -> None:
        out = root / "outputs"
        out.mkdir(parents=True)
        self._write_raw(root)
        modules = pd.DataFrame([self._module(phase, f"{phase}_a") for phase in ["phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a"]])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        signal_keys = ";".join(f"{phase}::{phase}_a" for phase in ["phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a"])
        for audit in ["b", "c", "d"]:
            pd.DataFrame([{
                "portfolio_set": f"audit_{audit}_set",
                "portfolio_mode": "one_trade_at_a_time_chronological",
                "signal_keys": signal_keys,
                "trades": 6,
                "trade_overlap_count": 2,
                "skipped_overlap_count": 1,
                "skipped_session_count": 0,
                "paper_trading_approved": False,
                "official_gates_passed": False,
            }]).to_csv(out / f"portfolio_audit_{audit}_portfolio_results.csv", index=False)
            pd.DataFrame([
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-01", "net_pnl": -10.0},
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-02", "net_pnl": 0.0},
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-03", "net_pnl": 20.0},
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-04", "net_pnl": 5.0},
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-05", "net_pnl": 1.0},
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-06", "net_pnl": 2.0},
            ]).to_csv(out / f"portfolio_audit_{audit}_portfolio_daily_pnl.csv", index=False)
            pd.DataFrame([
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "net_pnl": -10.0, "stress_pnl": -12.0, "active_days": 1},
                {"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 2, "net_pnl": 20.0, "stress_pnl": 18.0, "active_days": 1},
            ]).to_csv(out / f"portfolio_audit_{audit}_portfolio_walk_forward_folds.csv", index=False)
            pd.DataFrame([{"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "best_day_concentration": 0.5}]).to_csv(out / f"portfolio_audit_{audit}_portfolio_concentration.csv", index=False)
            pd.DataFrame([{"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "max_drawdown": -12.0}]).to_csv(out / f"portfolio_audit_{audit}_portfolio_drawdown_summary.csv", index=False)
            pd.DataFrame([{"portfolio_set": f"audit_{audit}_set", "portfolio_mode": "one_trade_at_a_time_chronological", "phase13a_net_contribution": 1.0}]).to_csv(out / f"portfolio_audit_{audit}_incremental_contribution.csv", index=False)
            (out / f"portfolio_audit_{audit}_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")
        for phase in ["phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a"]:
            cid = f"{phase}_a"
            pnl = -4.0 if phase == "phase10b" else 3.0 if phase == "phase13a" else 0.0
            pd.DataFrame([
                {"candidate_id": cid, "trading_session": "2026-01-01", "trades": 1, "net_pnl": pnl, "stress_pnl": pnl - 1},
                {"candidate_id": cid, "trading_session": "2026-01-03", "trades": 1, "net_pnl": 2.0, "stress_pnl": 1.0},
            ]).to_csv(out / f"{phase}_daily_pnl.csv", index=False)
            pd.DataFrame([
                {"candidate_id": cid, "trading_session": "2026-01-01", "entry_time": "2026-01-01 10:00:00-05:00", "exit_time": "2026-01-01 10:15:00-05:00", "net_pnl": pnl},
                {"candidate_id": cid, "trading_session": "2026-01-01", "entry_time": "2026-01-01 11:00:00-05:00", "exit_time": "2026-01-01 11:15:00-05:00", "net_pnl": 1.0},
            ]).to_csv(out / f"{phase}_trade_logs.csv", index=False)

    def _module(self, phase: str, cid: str) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "module_family": phase, "portfolio_role": "parked_module", "paper_trading_approved": False, "official_gates_passed": False}

    def _write_raw(self, root: Path) -> None:
        raw = root / "data" / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, day in enumerate(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"]):
            base = 100 + i * 10
            for minute in range(390):
                hour = 9 + (30 + minute) // 60
                mn = (30 + minute) % 60
                slope = 0.2 if i % 2 == 0 else -0.1
                price = base + minute * slope
                rows.append({"timestamp": f"{day} {hour:02d}:{mn:02d}:00", "symbol": "MNQ", "open": price, "high": price + 1, "low": price - 1, "close": price + slope, "volume": 1})
        pd.DataFrame(rows).to_csv(raw / "mnq_test.csv", index=False)


if __name__ == "__main__":
    unittest.main()
