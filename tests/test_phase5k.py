from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5k import Phase5KConfig, rank_vwap_focus_results, select_vwap_focus_specs


class Phase5KTests(unittest.TestCase):
    def test_select_vwap_focus_specs_is_mnq_only_deterministic_and_bounded(self) -> None:
        config = Phase5KConfig(max_specs=6)

        first = select_vwap_focus_specs(config)
        second = select_vwap_focus_specs(config)

        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertEqual({spec.instrument for spec in first}, {"MNQ"})
        self.assertEqual({spec.family for spec in first}, {"vwap_reclaim_rejection"})
        self.assertLessEqual(len(first), 6)
        self.assertGreaterEqual(len({spec.entry.params["mode"] for spec in first}), 2)
        self.assertGreaterEqual(len({(spec.exit.params["stop_ticks"], spec.exit.params["target_ticks"]) for spec in first}), 2)

    def test_rank_vwap_focus_results_promotes_clean_low_concentration_candidate(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "high_pnl_noisy",
                    "family": "vwap_reclaim_rejection",
                    "test_net_pnl": 3500.0,
                    "test_slippage_4_ticks_net_pnl": 3000.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.95,
                    "test_best_day_concentration": 0.55,
                    "test_best_trade_concentration": 0.30,
                },
                {
                    "candidate_id": "lower_pnl_clean",
                    "family": "vwap_reclaim_rejection",
                    "test_net_pnl": 900.0,
                    "test_slippage_4_ticks_net_pnl": 700.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.50,
                    "test_best_day_concentration": 0.30,
                    "test_best_trade_concentration": 0.18,
                },
            ]
        )

        ranked = rank_vwap_focus_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "lower_pnl_clean")
        self.assertEqual(ranked.iloc[0]["phase5k_label"], "vwap_research_candidate")
        self.assertGreater(ranked.iloc[0]["phase5k_score"], ranked.iloc[1]["phase5k_score"])


if __name__ == "__main__":
    unittest.main()
