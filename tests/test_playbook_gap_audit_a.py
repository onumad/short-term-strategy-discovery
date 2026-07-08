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

from short_term_edge.playbook_gap_audit_a import (  # noqa: E402
    build_candidate_module_briefs,
    build_market_day_features,
    build_module_coverage,
    load_playbook_gap_audit_inputs,
    make_recommendation,
    render_gap_audit_report,
    run_playbook_gap_audit_a,
    weak_fold_analysis,
)


class PlaybookGapAuditATests(unittest.TestCase):
    def test_loads_portfolio_audit_b_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            data = load_playbook_gap_audit_inputs(root)
            self.assertEqual(len(data["portfolio_results"]), 2)
            self.assertIn("module_registry", data)

    def test_identifies_weak_folds_deterministically(self) -> None:
        daily = pd.DataFrame([
            {"portfolio_set": "s", "portfolio_mode": "m", "trading_session": f"2026-01-0{i}", "net_pnl": i} for i in range(1, 7)
        ])
        folds = pd.DataFrame([
            {"portfolio_set": "s", "portfolio_mode": "m", "fold": 1, "net_pnl": -5, "stress_pnl": -6, "active_days": 1},
            {"portfolio_set": "s", "portfolio_mode": "m", "fold": 2, "net_pnl": 5, "stress_pnl": 4, "active_days": 1},
        ])
        matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02"], "phase13a::a": [1, 0]})
        results = pd.DataFrame([{"portfolio_set": "s", "portfolio_mode": "m", "signal_keys": "phase13a::a"}])
        first = weak_fold_analysis(daily, folds, results, matrix, config=type("C", (), {"weak_fold_threshold": 0.0})())
        second = weak_fold_analysis(daily, folds, results, matrix, config=type("C", (), {"weak_fold_threshold": 0.0})())
        pd.testing.assert_frame_equal(first, second)
        self.assertTrue(bool(first.iloc[0]["is_weak_fold"]))

    def test_no_trade_and_coverage_and_report_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_inputs(root)
            result = run_playbook_gap_audit_a(root)
            self.assertFalse(result["no_trade_days"].empty)
            coverage = result["module_coverage"]
            for col in ["overnight_prior_level_module_coverage", "opening_range_fade_coverage", "opening_drive_pullback_coverage", "prior_rth_breakout_coverage"]:
                self.assertIn(col, coverage.columns)
            report = render_gap_audit_report(result)
            self.assertIn("Research/simulation only. No live trading", report)
            self.assertFalse(result["next_action_recommendation"]["paper_trading_approved"])

    def test_market_features_without_lookahead_and_briefs_diagnostic_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_raw(root)
            features = build_market_day_features(root / "data" / "raw")
            self.assertIn("gap_from_prior_rth_close", features.columns)
            self.assertTrue(pd.isna(features.iloc[0]["gap_from_prior_rth_close"]))
            gaps = pd.DataFrame([
                {"gap_type": "power_hour_expansion_days_with_no_module", "day_count": 3, "evidence": "x"},
                {"gap_type": "trend_days_with_no_module", "day_count": 0, "evidence": "x"},
            ])
            briefs = build_candidate_module_briefs(gaps)
            self.assertEqual(briefs[0]["proposed_module_name"], "power_hour_continuation")
            self.assertTrue(briefs[0]["diagnostic_only_no_signals_generated"])
            rec = make_recommendation(gaps, briefs)
            self.assertFalse(rec["official_gates_changed"])
            self.assertFalse(rec["paper_trading_approved"])

    def _write_inputs(self, root: Path) -> None:
        out = root / "outputs"
        out.mkdir(parents=True)
        self._write_raw(root)
        modules = pd.DataFrame([
            self._module("phase10b", "p10"),
            self._module("phase11a", "p11"),
            self._module("phase12a", "p12"),
            self._module("phase13a", "p13"),
        ])
        modules.to_csv(out / "playbook_module_registry.csv", index=False)
        modules.to_csv(out / "research_signal_registry.csv", index=False)
        results = pd.DataFrame([
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "one_trade_at_a_time_chronological", "signal_keys": "phase10b::p10;phase13a::p13", "net_pnl": 1},
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "max_one_trade_per_session", "signal_keys": "phase10b::p10;phase13a::p13", "net_pnl": 1},
        ])
        results.to_csv(out / "portfolio_audit_b_portfolio_results.csv", index=False)
        daily = pd.DataFrame([
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-01", "net_pnl": -5},
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "one_trade_at_a_time_chronological", "trading_session": "2026-01-02", "net_pnl": 0},
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "max_one_trade_per_session", "trading_session": "2026-01-01", "net_pnl": -5},
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "max_one_trade_per_session", "trading_session": "2026-01-02", "net_pnl": 0},
        ])
        daily.to_csv(out / "portfolio_audit_b_portfolio_daily_pnl.csv", index=False)
        folds = pd.DataFrame([
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "one_trade_at_a_time_chronological", "fold": 1, "net_pnl": -5, "stress_pnl": -6, "active_days": 1},
            {"portfolio_set": "audit_a_best_plus_phase13a", "portfolio_mode": "max_one_trade_per_session", "fold": 1, "net_pnl": -5, "stress_pnl": -6, "active_days": 1},
        ])
        folds.to_csv(out / "portfolio_audit_b_portfolio_walk_forward_folds.csv", index=False)
        pd.DataFrame([{"x": 1}]).to_csv(out / "portfolio_audit_b_incremental_contribution.csv", index=False)
        pd.DataFrame([{"x": 1}]).to_csv(out / "portfolio_audit_b_phase13a_diversifier_impact.csv", index=False)
        (out / "portfolio_audit_b_next_action_recommendation.json").write_text(json.dumps({"next_action": "x", "paper_trading_approved": False}), encoding="utf-8")
        for phase, cid in [("phase10b", "p10"), ("phase11a", "p11"), ("phase12a", "p12"), ("phase13a", "p13")]:
            pd.DataFrame([
                {"candidate_id": cid, "trading_session": "2026-01-01", "net_pnl": -2 if phase != "phase13a" else 3},
                {"candidate_id": cid, "trading_session": "2026-01-03", "net_pnl": 1},
            ]).to_csv(out / f"{phase}_daily_pnl.csv", index=False)
            pd.DataFrame([
                {"candidate_id": cid, "trading_session": "2026-01-01", "entry_time": "2026-01-01 10:00", "exit_time": "2026-01-01 10:30", "net_pnl": 1},
            ]).to_csv(out / f"{phase}_trade_logs.csv", index=False)

    def _module(self, phase: str, cid: str) -> dict[str, object]:
        return {"module_id": cid, "phase": phase, "candidate_id": cid, "source_family": phase, "portfolio_role": "diversifier_module" if phase == "phase13a" else "parked_module"}

    def _write_raw(self, root: Path) -> None:
        raw = root / "data" / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        rows = []
        for day, base in [("2026-01-01", 100), ("2026-01-02", 110), ("2026-01-03", 120)]:
            for minute in range(390):
                hour = 9 + (30 + minute) // 60
                mn = (30 + minute) % 60
                price = base + minute * 0.1
                rows.append({"timestamp": f"{day} {hour:02d}:{mn:02d}:00", "symbol": "MNQ", "open": price, "high": price + 1, "low": price - 1, "close": price + 0.5, "volume": 1})
        pd.DataFrame(rows).to_csv(raw / "mnq_test.csv", index=False)


if __name__ == "__main__":
    unittest.main()
