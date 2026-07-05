from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5j import Phase5JConfig, rank_family_search_results, select_family_search_specs


class Phase5JTests(unittest.TestCase):
    def test_select_family_search_specs_is_mnq_only_deterministic_and_multi_family(self) -> None:
        config = Phase5JConfig(max_specs=6)

        first = select_family_search_specs(config)
        second = select_family_search_specs(config)

        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertEqual({spec.instrument for spec in first}, {"MNQ"})
        self.assertLessEqual(len(first), 6)
        self.assertIn("opening_range_breakout", {spec.family for spec in first})
        self.assertIn("vwap_reclaim_rejection", {spec.family for spec in first})
        self.assertIn("prior_session_levels", {spec.family for spec in first})

    def test_rank_family_search_results_prefers_distributed_family_candidate(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "high_pnl_concentrated",
                    "family": "opening_range_failure",
                    "test_net_pnl": 6000.0,
                    "test_slippage_4_ticks_net_pnl": 5500.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.85,
                    "test_best_day_concentration": 0.65,
                    "test_best_trade_concentration": 0.45,
                },
                {
                    "candidate_id": "family_candidate",
                    "family": "vwap_reclaim_rejection",
                    "test_net_pnl": 1600.0,
                    "test_slippage_4_ticks_net_pnl": 1300.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.45,
                    "test_best_day_concentration": 0.25,
                    "test_best_trade_concentration": 0.18,
                },
            ]
        )

        ranked = rank_family_search_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "family_candidate")
        self.assertEqual(ranked.iloc[0]["phase5j_label"], "family_research_candidate")
        self.assertGreater(ranked.iloc[0]["phase5j_score"], ranked.iloc[1]["phase5j_score"])


if __name__ == "__main__":
    unittest.main()
