from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase6a_analysis import render_failure_analysis_report, summarize_failure_modes


class Phase6AFailureAnalysisTests(unittest.TestCase):
    def test_summarize_failure_modes_counts_semicolon_notes(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "phase6a_label": "rejected",
                    "phase6a_notes": "fails aggregate 4-tick slippage stress; one-day concentration risk",
                },
                {
                    "phase6a_label": "rejected",
                    "phase6a_notes": "fails aggregate 4-tick slippage stress; drawdown exceeds prefilter cap",
                },
                {
                    "phase6a_label": "watchlist_needs_walk_forward",
                    "phase6a_notes": "negative holdout split",
                },
                {"phase6a_label": "rejected", "phase6a_notes": "  "},
            ]
        )

        summary = summarize_failure_modes(rows)

        self.assertEqual(summary.loc["fails aggregate 4-tick slippage stress", "count"], 2)
        self.assertEqual(summary.loc["one-day concentration risk", "count"], 1)
        self.assertEqual(summary.loc["drawdown exceeds prefilter cap", "count"], 1)
        self.assertNotIn("", summary.index)

    def test_summarize_failure_modes_returns_empty_shape_without_notes(self) -> None:
        rows = pd.DataFrame([{"phase6a_label": "rejected"}])

        summary = summarize_failure_modes(rows)

        self.assertEqual(list(summary.columns), ["count"])
        self.assertEqual(summary.index.name, "failure_mode")
        self.assertTrue(summary.empty)

    def test_render_failure_analysis_report_includes_counts_and_recommendation(self) -> None:
        results = pd.DataFrame(
            [
                {
                    "candidate_id": "candidate_a",
                    "phase6a_rank": 1,
                    "phase6a_label": "rejected",
                    "phase6a_score": 3.44,
                    "net_pnl": 2421.28,
                    "slippage_4_ticks_net_pnl": 1362.28,
                    "phase6a_notes": "one-day concentration risk; one-trade concentration risk",
                },
                {
                    "candidate_id": "candidate_b",
                    "phase6a_rank": 2,
                    "phase6a_label": "rejected",
                    "phase6a_score": -45.80,
                    "net_pnl": 1778.57,
                    "slippage_4_ticks_net_pnl": 632.57,
                    "phase6a_notes": "one-day concentration risk; drawdown exceeds prefilter cap",
                },
            ]
        )
        modes = summarize_failure_modes(results)

        report = render_failure_analysis_report(results, modes)

        self.assertIn("2 scored Phase 6A candidates", report)
        self.assertIn("`{'rejected': 2}`", report)
        self.assertIn("one-day concentration risk", report)
        self.assertIn("Phase 6B should prioritize ambiguity/concentration reduction", report)


if __name__ == "__main__":
    unittest.main()
