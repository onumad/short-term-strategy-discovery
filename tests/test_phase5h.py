from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5h import build_session_regimes, filter_trades_by_regime, rank_regime_filtered_results


class Phase5HTests(unittest.TestCase):
    def test_session_regimes_use_prior_and_opening_features_only(self) -> None:
        features = pd.DataFrame(
            [
                {"symbol": "MNQ", "trading_session": "2024-01-02", "timestamp": pd.Timestamp("2024-01-02 10:00"), "prior_session_range": 40.0, "gap_from_prior_close": 5.0, "or_width_30m": 20.0, "day_of_week": 1},
                {"symbol": "MNQ", "trading_session": "2024-01-03", "timestamp": pd.Timestamp("2024-01-03 10:00"), "prior_session_range": 80.0, "gap_from_prior_close": -20.0, "or_width_30m": 35.0, "day_of_week": 2},
                {"symbol": "MNQ", "trading_session": "2024-01-04", "timestamp": pd.Timestamp("2024-01-04 10:00"), "prior_session_range": 120.0, "gap_from_prior_close": 2.0, "or_width_30m": 50.0, "day_of_week": 3},
            ]
        )

        regimes = build_session_regimes(features, symbol="MNQ")

        self.assertEqual(list(regimes["trading_session"]), ["2024-01-02", "2024-01-03", "2024-01-04"])
        self.assertEqual(list(regimes["prior_range_bucket"]), ["low", "mid", "high"])
        self.assertEqual(list(regimes["gap_abs_bucket"]), ["mid", "high", "low"])
        self.assertEqual(list(regimes["or_width_bucket"]), ["low", "mid", "high"])

    def test_filter_trades_by_regime_keeps_matching_sessions(self) -> None:
        regimes = pd.DataFrame(
            [
                {"trading_session": "2024-01-02", "prior_range_bucket": "low", "gap_abs_bucket": "mid", "or_width_bucket": "low"},
                {"trading_session": "2024-01-03", "prior_range_bucket": "high", "gap_abs_bucket": "high", "or_width_bucket": "high"},
            ]
        )
        trades = pd.DataFrame(
            [
                {"trading_session": "2024-01-02", "net_pnl": -10.0},
                {"trading_session": "2024-01-03", "net_pnl": 50.0},
            ]
        )

        kept = filter_trades_by_regime(trades, regimes, {"prior_range_bucket": "high"})

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept.iloc[0]["trading_session"], "2024-01-03")
        self.assertEqual(kept.iloc[0]["regime_filter"], "prior_range_bucket=high")

    def test_rank_regime_filtered_results_prefers_less_concentrated_candidate(self) -> None:
        rows = pd.DataFrame(
            [
                {"candidate_id": "high_pnl_concentrated", "regime_filter": "all", "test_net_pnl": 2000.0, "test_slippage_4_ticks_net_pnl": 1700.0, "test_positive_fold_pct": 1.0, "test_active_session_pct": 0.8, "test_best_day_concentration": 0.7, "test_best_trade_concentration": 0.5},
                {"candidate_id": "distributed", "regime_filter": "prior_range_bucket=mid", "test_net_pnl": 1200.0, "test_slippage_4_ticks_net_pnl": 950.0, "test_positive_fold_pct": 1.0, "test_active_session_pct": 0.5, "test_best_day_concentration": 0.25, "test_best_trade_concentration": 0.15},
            ]
        )

        ranked = rank_regime_filtered_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "distributed")
        self.assertEqual(ranked.iloc[0]["phase5h_label"], "regime_filtered_candidate")
        self.assertGreater(ranked.iloc[0]["phase5h_score"], ranked.iloc[1]["phase5h_score"])


if __name__ == "__main__":
    unittest.main()
