from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5l import rank_vwap_regime_results, vwap_regime_filters


class Phase5LTests(unittest.TestCase):
    def test_vwap_regime_filters_are_bounded_and_include_baseline(self) -> None:
        filters = vwap_regime_filters()

        self.assertEqual(filters[0], {})
        self.assertEqual(filters, vwap_regime_filters())
        self.assertLessEqual(len(filters), 6)
        self.assertIn({"prior_range_bucket": "high"}, filters)
        self.assertIn({"gap_abs_bucket": "low"}, filters)
        self.assertEqual(len({tuple(sorted(item.items())) for item in filters}), len(filters))

    def test_rank_vwap_regime_results_prefers_cleaner_filter(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "vwap",
                    "regime_filter": "all",
                    "test_net_pnl": 150.0,
                    "test_slippage_4_ticks_net_pnl": 40.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.95,
                    "test_best_day_concentration": 0.37,
                    "test_best_trade_concentration": 0.18,
                },
                {
                    "candidate_id": "vwap",
                    "regime_filter": "gap_abs_bucket=low",
                    "test_net_pnl": 90.0,
                    "test_slippage_4_ticks_net_pnl": 35.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.50,
                    "test_best_day_concentration": 0.25,
                    "test_best_trade_concentration": 0.16,
                },
            ]
        )

        ranked = rank_vwap_regime_results(rows)

        self.assertEqual(ranked.iloc[0]["regime_filter"], "gap_abs_bucket=low")
        self.assertEqual(ranked.iloc[0]["phase5l_label"], "vwap_regime_candidate")
        self.assertGreater(ranked.iloc[0]["phase5l_score"], ranked.iloc[1]["phase5l_score"])


if __name__ == "__main__":
    unittest.main()
