from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8d_hypothesis_queue import Phase8DConfig, build_phase8d_hypothesis_queue
from short_term_edge.phase8e_event_scout import Phase8EConfig, render_phase8e_report, run_phase8e_event_scout, score_hypothesis_events


class Phase8EEventScoutTests(unittest.TestCase):
    def _sample_bars(self) -> pd.DataFrame:
        timestamps = pd.date_range("2026-01-02 09:30", periods=90, freq="min", tz="America/New_York")
        close = [100.0 + index * 0.15 for index in range(90)]
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "symbol": "MGC",
                "open": close,
                "high": [value + 0.20 for value in close],
                "low": [value - 0.20 for value in close],
                "close": close,
                "volume": [1000] * 90,
                "trading_session": ["2026-01-02"] * 90,
                "session_segment": ["RTH"] * 90,
            }
        )

    def test_score_hypothesis_events_labels_directional_forward_behavior(self) -> None:
        hypothesis = {
            "hypothesis_id": "MGC_time_of_day_momentum_reversion_tf1_long_only_test",
            "instrument": "MGC",
            "timeframe": 1,
            "side": "long_only",
            "family": "time_of_day_momentum_reversion",
        }
        row = score_hypothesis_events(self._sample_bars(), hypothesis, Phase8EConfig(min_events=1))

        self.assertEqual(row["hypothesis_id"], hypothesis["hypothesis_id"])
        self.assertGreaterEqual(int(row["event_count"]), 1)
        self.assertGreater(float(row["avg_forward_15m"]), 0.0)
        self.assertIn(row["phase8e_label"], {"backtest_candidate", "needs_filter"})

    def test_sparse_events_are_labeled_too_sparse(self) -> None:
        hypothesis = {
            "hypothesis_id": "MGC_volatility_compression_breakout_tf15_long_only_test",
            "instrument": "MGC",
            "timeframe": 15,
            "side": "long_only",
            "family": "volatility_compression_breakout",
        }
        row = score_hypothesis_events(self._sample_bars().head(20), hypothesis, Phase8EConfig(min_events=50))

        self.assertEqual(row["phase8e_label"], "too_sparse")
        self.assertLess(int(row["event_count"]), 50)

    def test_run_phase8e_event_scout_selects_at_most_six_backtest_candidates(self) -> None:
        queue = build_phase8d_hypothesis_queue(Phase8DConfig(max_hypotheses=12))
        results = run_phase8e_event_scout(queue, {"MGC": self._sample_bars(), "MNQ": self._sample_bars().assign(symbol="MNQ")}, Phase8EConfig(max_hypotheses=12, min_events=1))

        self.assertLessEqual(int((results["phase8e_label"] == "backtest_candidate").sum()), 6)
        self.assertEqual(len(results), 12)
        self.assertIn("event_count", results.columns)
        self.assertIn("avg_forward_15m", results.columns)

    def test_render_phase8e_report_includes_guardrails_and_survivor_count(self) -> None:
        queue = build_phase8d_hypothesis_queue(Phase8DConfig(max_hypotheses=6))
        results = run_phase8e_event_scout(queue, {"MGC": self._sample_bars(), "MNQ": self._sample_bars().assign(symbol="MNQ")}, Phase8EConfig(max_hypotheses=6, min_events=1))
        report = render_phase8e_report(
            results,
            Phase8EConfig(max_hypotheses=6, min_events=1),
            results_path=Path("outputs/phase8e_event_scout_results.csv"),
            report_path=Path("reports/phase8e_event_scout_report.md"),
            run_artifact_dir=Path("artifacts/phase8e_event_scout/test-run"),
        )

        self.assertIn("# Phase 8E Cheap Event-Study Scout", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("Backtest candidates", report)
        self.assertIn("outputs/phase8e_event_scout_results.csv", report)


if __name__ == "__main__":
    unittest.main()
