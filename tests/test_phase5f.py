from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5f import Phase5FConfig, rank_walk_forward_search, select_walk_forward_search_specs


class Phase5FTests(unittest.TestCase):
    def test_spec_selection_is_deterministic_mnq_first_and_checks_timeframes(self) -> None:
        config = Phase5FConfig(symbols=("MNQ", "MGC"), candidates_per_symbol=6, seed=77, timeframes=(1, 3, 5), opening_range_minutes=(15, 30))

        first = select_walk_forward_search_specs(config)
        second = select_walk_forward_search_specs(config)

        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertEqual([spec.instrument for spec in first[:6]], ["MNQ"] * 6)
        self.assertEqual([spec.instrument for spec in first[6:]], ["MGC"] * 6)
        self.assertTrue({1, 3, 5}.issubset({spec.timeframe for spec in first}))
        self.assertTrue(all(spec.family == "opening_range_failure" for spec in first[:6]))

    def test_rank_walk_forward_search_prefers_stable_test_performance(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "candidate_id": "fragile",
                    "instrument": "MNQ",
                    "family": "opening_range_failure",
                    "timeframe": 1,
                    "phase5d_label": "rejected",
                    "phase5d_score": -20.0,
                    "test_net_pnl": 2000.0,
                    "test_slippage_4_ticks_net_pnl": -100.0,
                    "test_positive_fold_pct": 0.33,
                    "test_trades": 90,
                    "test_active_session_pct": 0.8,
                    "test_best_day_concentration": 0.5,
                    "test_best_trade_concentration": 0.3,
                },
                {
                    "candidate_id": "stable",
                    "instrument": "MNQ",
                    "family": "opening_range_failure",
                    "timeframe": 3,
                    "phase5d_label": "paper_test_candidate",
                    "phase5d_score": 45.0,
                    "test_net_pnl": 900.0,
                    "test_slippage_4_ticks_net_pnl": 600.0,
                    "test_positive_fold_pct": 0.75,
                    "test_trades": 70,
                    "test_active_session_pct": 0.55,
                    "test_best_day_concentration": 0.2,
                    "test_best_trade_concentration": 0.12,
                },
            ]
        )

        ranked = rank_walk_forward_search(summary)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "stable")
        self.assertEqual(ranked.iloc[0]["phase5f_label"], "paper_test_candidate")
        self.assertLess(ranked.iloc[1]["phase5f_score"], ranked.iloc[0]["phase5f_score"])


if __name__ == "__main__":
    unittest.main()
