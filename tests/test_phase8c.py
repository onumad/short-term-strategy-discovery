from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8c import (
    Phase8CConfig,
    apply_phase8c_filter,
    build_phase8c_filter_specs,
    evaluate_phase8c_filters,
    render_phase8c_report,
)


class Phase8CNoTradeFilterTests(unittest.TestCase):
    def _sample_trades(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "source_candidate_id": "candidate_a",
                    "entry_time": "2026-01-02T09:35:00-05:00",
                    "exit_time": "2026-01-02T09:45:00-05:00",
                    "trading_session": "2026-01-02",
                    "side": "long",
                    "net_pnl": 40.0,
                    "stress_net_pnl": 30.0,
                    "split": "discovery",
                    "same_bar_stop_target_ambiguity": 0,
                },
                {
                    "source_candidate_id": "candidate_a",
                    "entry_time": "2026-01-03T12:15:00-05:00",
                    "exit_time": "2026-01-03T12:20:00-05:00",
                    "trading_session": "2026-01-03",
                    "side": "short",
                    "net_pnl": -20.0,
                    "stress_net_pnl": -30.0,
                    "split": "validation",
                    "same_bar_stop_target_ambiguity": 1,
                },
                {
                    "source_candidate_id": "candidate_b",
                    "entry_time": "2026-01-04T15:10:00-05:00",
                    "exit_time": "2026-01-04T15:20:00-05:00",
                    "trading_session": "2026-01-04",
                    "side": "short",
                    "net_pnl": 15.0,
                    "stress_net_pnl": 5.0,
                    "split": "holdout",
                    "same_bar_stop_target_ambiguity": 0,
                },
            ]
        )

    def test_filter_specs_are_deterministic_serializable_and_diverse(self) -> None:
        specs = build_phase8c_filter_specs()
        payloads = [spec.to_dict() for spec in specs]
        json.dumps(payloads)

        self.assertEqual([spec.filter_id for spec in specs], [spec.filter_id for spec in build_phase8c_filter_specs()])
        self.assertGreaterEqual(len(specs), 8)
        self.assertIn("time_window:first_60", {spec.filter_id for spec in specs})
        self.assertIn("side:long_only", {spec.filter_id for spec in specs})
        self.assertIn("side:short_only", {spec.filter_id for spec in specs})

    def test_apply_phase8c_filter_uses_pre_entry_trade_metadata(self) -> None:
        trades = self._sample_trades()
        specs = {spec.filter_id: spec for spec in build_phase8c_filter_specs()}

        first_60 = apply_phase8c_filter(trades, specs["time_window:first_60"])
        long_only = apply_phase8c_filter(trades, specs["side:long_only"])
        no_lunch = apply_phase8c_filter(trades, specs["time_window:exclude_lunch"])

        self.assertEqual(first_60["entry_time"].dt.strftime("%H:%M").tolist(), ["09:35"])
        self.assertEqual(long_only["side"].tolist(), ["long"])
        self.assertEqual(no_lunch["entry_time"].dt.strftime("%H:%M").tolist(), ["09:35", "15:10"])

    def test_evaluate_phase8c_filters_ranks_reduction_without_mutating_trades(self) -> None:
        trades = self._sample_trades()
        original_columns = list(trades.columns)
        specs = [spec for spec in build_phase8c_filter_specs() if spec.filter_id in {"time_window:first_60", "side:short_only", "time_window:exclude_lunch"}]

        results = evaluate_phase8c_filters(
            trades,
            specs,
            complete_sessions=["2026-01-02", "2026-01-03", "2026-01-04"],
            config=Phase8CConfig(min_trades=1, concentration_limit=1.0),
        )

        self.assertEqual(list(trades.columns), original_columns)
        self.assertEqual(set(results["filter_id"]), {"time_window:first_60", "side:short_only", "time_window:exclude_lunch"})
        first_60 = results.set_index("filter_id").loc["time_window:first_60"]
        self.assertEqual(int(first_60["source_candidate_count"]), 2)
        self.assertEqual(int(first_60["kept_trade_count"]), 1)
        self.assertEqual(float(first_60["net_pnl"]), 40.0)
        self.assertEqual(int(first_60["same_bar_stop_target_ambiguity_count"]), 0)
        self.assertNotEqual(first_60["phase8c_label"], "rejected")

    def test_render_phase8c_report_includes_guardrails_outputs_and_decision(self) -> None:
        trades = self._sample_trades()
        results = evaluate_phase8c_filters(
            trades,
            [spec for spec in build_phase8c_filter_specs() if spec.filter_id in {"time_window:first_60", "side:short_only"}],
            complete_sessions=["2026-01-02", "2026-01-03", "2026-01-04"],
            config=Phase8CConfig(min_trades=1),
        )
        report = render_phase8c_report(
            results,
            Phase8CConfig(min_trades=1),
            source_trade_count=len(trades),
            source_candidate_count=2,
            results_path=Path("outputs/phase8c_no_trade_filter_results.csv"),
            report_path=Path("reports/phase8c_no_trade_filter_report.md"),
            run_artifact_dir=Path("artifacts/phase8c_no_trade_filter/test-run"),
        )

        self.assertIn("# Phase 8C No-Trade / Session-Selection Diagnostic", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("phase8c_no_trade_filter_candidate", report)
        self.assertIn("outputs/phase8c_no_trade_filter_results.csv", report)
        self.assertIn("artifacts/phase8c_no_trade_filter/test-run", report)


if __name__ == "__main__":
    unittest.main()
