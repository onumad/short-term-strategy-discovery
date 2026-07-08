from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8g_event_execution_calibration import Phase8GConfig, render_phase8g_report, run_phase8g_calibration, select_phase8g_candidates


class Phase8GEventExecutionCalibrationTests(unittest.TestCase):
    def _event_results(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_a25f2113",
                    "instrument": "MNQ",
                    "timeframe": 5,
                    "side": "long_only",
                    "family": "vwap_pullback_continuation",
                    "event_count": 80,
                    "phase8e_score": 61.0,
                    "phase8e_label": "backtest_candidate",
                },
                {
                    "hypothesis_id": "MNQ_vwap_reclaim_rejection_tf1_long_only_bdbad7c5",
                    "instrument": "MNQ",
                    "timeframe": 1,
                    "side": "long_only",
                    "family": "vwap_reclaim_rejection",
                    "event_count": 80,
                    "phase8e_score": 60.0,
                    "phase8e_label": "backtest_candidate",
                },
                {
                    "hypothesis_id": "MNQ_vwap_reclaim_rejection_tf3_long_only_duplicate",
                    "instrument": "MNQ",
                    "timeframe": 3,
                    "side": "long_only",
                    "family": "vwap_reclaim_rejection",
                    "event_count": 80,
                    "phase8e_score": 59.0,
                    "phase8e_label": "backtest_candidate",
                },
                {
                    "hypothesis_id": "MGC_opening_range_breakout_tf15_short_only_parked",
                    "instrument": "MGC",
                    "timeframe": 15,
                    "side": "short_only",
                    "family": "opening_range_breakout",
                    "event_count": 80,
                    "phase8e_score": 90.0,
                    "phase8e_label": "needs_filter",
                },
            ]
        )

    def _sample_bars(self) -> pd.DataFrame:
        frames = []
        for day_index, session in enumerate(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"]):
            timestamps = pd.date_range(f"{session} 09:30", periods=90, freq="min", tz="America/New_York")
            close = []
            for index in range(90):
                cycle = index % 20
                value = 100.0 + day_index * 0.2 + cycle * 0.2
                if cycle >= 10:
                    value -= (cycle - 9) * 0.05
                close.append(value)
            frames.append(
                pd.DataFrame(
                    {
                        "timestamp": timestamps,
                        "symbol": "MNQ",
                        "open": close,
                        "high": [value + 0.25 for value in close],
                        "low": [value - 0.25 for value in close],
                        "close": close,
                        "volume": [1000] * 90,
                        "trading_session": [session] * 90,
                        "session_segment": ["RTH"] * 90,
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)

    def test_select_phase8g_candidates_caps_and_diversifies_backtest_candidates(self) -> None:
        selected = select_phase8g_candidates(self._event_results(), Phase8GConfig(max_candidates=2))

        self.assertEqual(len(selected), 2)
        self.assertEqual(set(selected["phase8e_label"]), {"backtest_candidate"})
        self.assertEqual(len({(row.instrument, row.family) for row in selected.itertuples()}), 2)
        self.assertNotIn("needs_filter", set(selected["phase8e_label"]))

    def test_run_phase8g_calibration_outputs_required_diagnostic_columns(self) -> None:
        config = Phase8GConfig(max_candidates=1, entry_delays=("next_bar_open",), variants=Phase8GConfig().variants[:2])
        results = run_phase8g_calibration(self._event_results(), {"MNQ": self._sample_bars()}, config)

        self.assertEqual(len(results), 2)
        self.assertIn("calibration_id", results.columns)
        self.assertIn("slippage_4_ticks_net_pnl", results.columns)
        self.assertIn("same_bar_stop_target_ambiguity_count", results.columns)
        self.assertTrue((results["event_count"] > 0).all())
        self.assertTrue((results["executable_trade_count"] > 0).all())
        self.assertTrue(set(results["calibration_label"]).issubset({"calibration_survivor", "split_unstable", "concentrated", "cost_sensitive", "rejected_timing_cost", "ambiguous_execution", "too_sparse"}))

    def test_render_phase8g_report_includes_guardrails_outputs_and_decision_rule(self) -> None:
        results = pd.DataFrame(
            [
                {
                    "phase8g_rank": 1,
                    "calibration_id": "cal1",
                    "hypothesis_id": "hyp1",
                    "instrument": "MNQ",
                    "family": "vwap_reclaim_rejection",
                    "entry_delay": "next_bar_open",
                    "stop_model": "none",
                    "target_model": "horizon_close",
                    "time_stop": 15,
                    "calibration_label": "rejected_timing_cost",
                    "net_pnl": -10.0,
                    "slippage_4_ticks_net_pnl": -20.0,
                    "executable_trade_count": 10,
                    "max_drawdown": -50.0,
                    "calibration_notes": "negative net",
                }
            ]
        )
        report = render_phase8g_report(
            results,
            Phase8GConfig(max_candidates=1),
            results_path=Path("outputs/phase8g_event_execution_calibration.csv"),
            report_path=Path("reports/phase8g_event_execution_calibration_report.md"),
            run_artifact_dir=Path("artifacts/phase8g_event_execution_calibration/test-run"),
        )

        self.assertIn("# Phase 8G Event-To-Execution Calibration", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("horizon-close", report)
        self.assertIn("outputs/phase8g_event_execution_calibration.csv", report)


if __name__ == "__main__":
    unittest.main()
