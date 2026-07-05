from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5i import expanded_regime_filters, rank_expanded_regime_results


class Phase5ITests(unittest.TestCase):
    def test_expanded_regime_filters_are_deterministic_and_include_combos(self) -> None:
        first = expanded_regime_filters()
        second = expanded_regime_filters()

        self.assertEqual(first, second)
        self.assertEqual(first[0], {})
        self.assertIn({"prior_range_bucket": "high"}, first)
        self.assertIn({"gap_abs_bucket": "low"}, first)
        self.assertIn({"prior_range_bucket": "high", "gap_abs_bucket": "low"}, first)
        self.assertIn({"prior_range_bucket": "high", "or_width_bucket": "mid"}, first)
        self.assertEqual(len({tuple(sorted(item.items())) for item in first}), len(first))

    def test_rank_expanded_regime_results_promotes_cleaner_filter(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "dirty",
                    "regime_filter": "all",
                    "test_net_pnl": 5000.0,
                    "test_slippage_4_ticks_net_pnl": 4500.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.80,
                    "test_best_day_concentration": 0.60,
                    "test_best_trade_concentration": 0.45,
                },
                {
                    "candidate_id": "clean",
                    "regime_filter": "prior_range_bucket=high;gap_abs_bucket=low",
                    "test_net_pnl": 1500.0,
                    "test_slippage_4_ticks_net_pnl": 1300.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.45,
                    "test_best_day_concentration": 0.28,
                    "test_best_trade_concentration": 0.18,
                },
            ]
        )

        ranked = rank_expanded_regime_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "clean")
        self.assertEqual(ranked.iloc[0]["phase5i_label"], "regime_filtered_candidate")
        self.assertGreater(ranked.iloc[0]["phase5i_score"], ranked.iloc[1]["phase5i_score"])


if __name__ == "__main__":
    unittest.main()
