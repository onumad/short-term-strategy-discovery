from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase6_synthesis import render_phase6_failure_synthesis, summarize_failure_categories, summarize_note_counts


class Phase6FailureSynthesisTests(unittest.TestCase):
    def test_summarize_note_counts_handles_multiple_phase_note_columns(self) -> None:
        rows = pd.DataFrame(
            [
                {"phase6a_notes": "one-day concentration risk; drawdown exceeds prefilter cap"},
                {"phase6a_notes": "one-day concentration risk; fails aggregate 4-tick slippage stress"},
                {"phase6b_notes": "one-trade concentration risk; drawdown exceeds Phase 6B cap"},
                {"phase6b_notes": "one-trade concentration risk; same-bar stop/target ambiguity remains"},
            ]
        )

        summary = summarize_note_counts(rows, ("phase6a_notes", "phase6b_notes"))

        self.assertEqual(summary.loc["one-day concentration risk", "count"], 2)
        self.assertEqual(summary.loc["one-trade concentration risk", "count"], 2)
        self.assertEqual(summary.loc["drawdown exceeds prefilter cap", "count"], 1)
        self.assertEqual(summary.index.name, "failure_mode")

    def test_summarize_failure_categories_groups_phase6_notes_by_research_axis(self) -> None:
        failure_modes = pd.DataFrame(
            [
                {"failure_mode": "one-day concentration risk", "count": 70},
                {"failure_mode": "one-trade concentration risk", "count": 71},
                {"failure_mode": "fails aggregate 4-tick slippage stress", "count": 69},
                {"failure_mode": "drawdown exceeds prefilter cap", "count": 48},
                {"failure_mode": "same-bar stop/target ambiguity remains", "count": 17},
                {"failure_mode": "negative holdout split", "count": 55},
            ]
        ).set_index("failure_mode")

        categories = summarize_failure_categories(failure_modes)

        self.assertEqual(categories.loc["concentration", "count"], 141)
        self.assertEqual(categories.loc["cost_slippage", "count"], 69)
        self.assertEqual(categories.loc["drawdown", "count"], 48)
        self.assertEqual(categories.loc["ambiguity", "count"], 17)
        self.assertEqual(categories.loc["split_instability", "count"], 55)
        self.assertEqual(categories.index.name, "failure_category")

    def test_render_phase6_failure_synthesis_captures_counts_best_candidates_and_recommendation(self) -> None:
        phase6a = pd.DataFrame(
            [
                {
                    "candidate_id": "phase6a_best",
                    "family": "opening_range_breakout",
                    "phase6a_rank": 1,
                    "phase6a_label": "rejected",
                    "phase6a_score": 3.44,
                    "net_pnl": 2421.28,
                    "slippage_4_ticks_net_pnl": 1362.28,
                    "phase6a_notes": "one-day concentration risk; drawdown exceeds prefilter cap",
                }
            ]
        )
        phase6b = pd.DataFrame(
            [
                {
                    "candidate_id": "phase6b_best",
                    "family": "prior_session_levels",
                    "phase6b_rank": 1,
                    "phase6b_label": "rejected",
                    "phase6b_score": 12.03,
                    "net_pnl": 4895.83,
                    "slippage_4_ticks_net_pnl": 2246.83,
                    "phase6b_notes": "one-trade concentration risk; drawdown exceeds Phase 6B cap",
                }
            ]
        )

        report = render_phase6_failure_synthesis(phase6a, phase6b)

        self.assertIn("1 scored Phase 6A candidates", report)
        self.assertIn("1 scored Phase 6B candidates", report)
        self.assertIn("phase6a_best", report)
        self.assertIn("phase6b_best", report)
        self.assertIn("No Phase 6B prefilter survivors or watchlist candidates were found", report)
        self.assertIn("Failure Category Totals", report)
        self.assertIn("concentration", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("lower-frequency session-selection strategies", report)
        self.assertNotIn("broker", report.lower().replace("no live trading, broker adapters", ""))


if __name__ == "__main__":
    unittest.main()
