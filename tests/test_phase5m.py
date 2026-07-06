from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5m import Phase5MConfig, rank_deep_vwap_results, select_deep_vwap_spec


class Phase5MTests(unittest.TestCase):
    def test_select_deep_vwap_spec_uses_top_phase5k_candidate(self) -> None:
        spec = select_deep_vwap_spec(PROJECT_ROOT, Phase5MConfig())

        self.assertEqual(spec.instrument, "MNQ")
        self.assertEqual(spec.family, "vwap_reclaim_rejection")
        self.assertEqual(spec.canonical_id(), "MNQ_vwap_reclaim_rejection_tf1_a52d373916")

    def test_rank_deep_vwap_results_requires_multifold_survival(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "one_fold_close_call",
                    "folds": 1,
                    "test_net_pnl": 150.0,
                    "test_slippage_4_ticks_net_pnl": 40.0,
                    "test_positive_fold_pct": 1.0,
                    "test_active_session_pct": 0.95,
                    "test_best_day_concentration": 0.36,
                    "test_best_trade_concentration": 0.18,
                },
                {
                    "candidate_id": "multi_fold_clean",
                    "folds": 3,
                    "test_net_pnl": 700.0,
                    "test_slippage_4_ticks_net_pnl": 400.0,
                    "test_positive_fold_pct": 0.67,
                    "test_active_session_pct": 0.55,
                    "test_best_day_concentration": 0.30,
                    "test_best_trade_concentration": 0.18,
                },
            ]
        )

        ranked = rank_deep_vwap_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "multi_fold_clean")
        self.assertEqual(ranked.iloc[0]["phase5m_label"], "deep_vwap_candidate")
        self.assertEqual(ranked.loc[ranked["candidate_id"].eq("one_fold_close_call"), "phase5m_label"].iloc[0], "needs_deeper_validation")


if __name__ == "__main__":
    unittest.main()
