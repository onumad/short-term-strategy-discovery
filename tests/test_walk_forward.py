from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from short_term_edge.walk_forward import WalkForwardConfig, apply_walk_forward_promotion, generate_walk_forward_folds, shared_complete_sessions


class WalkForwardTests(unittest.TestCase):
    def test_generate_walk_forward_folds_are_chronological_and_non_overlapping(self) -> None:
        sessions = list(range(20))
        config = WalkForwardConfig(train_sessions=8, validation_sessions=4, test_sessions=3, step_sessions=3, min_folds=1)

        folds = generate_walk_forward_folds(sessions, config)

        self.assertEqual(len(folds), 2)
        first = folds[0]
        self.assertEqual(first.fold, 1)
        self.assertEqual(first.train_sessions, tuple(range(0, 8)))
        self.assertEqual(first.validation_sessions, tuple(range(8, 12)))
        self.assertEqual(first.test_sessions, tuple(range(12, 15)))
        self.assertLess(max(first.train_sessions), min(first.validation_sessions))
        self.assertLess(max(first.validation_sessions), min(first.test_sessions))
        self.assertEqual(len(set(first.train_sessions) & set(first.validation_sessions)), 0)
        self.assertEqual(len(set(first.validation_sessions) & set(first.test_sessions)), 0)
        self.assertEqual(folds[1].train_sessions, tuple(range(3, 11)))

    def test_generate_walk_forward_folds_fails_closed_when_history_too_short(self) -> None:
        config = WalkForwardConfig(train_sessions=8, validation_sessions=4, test_sessions=3, step_sessions=3, min_folds=1)

        with self.assertRaises(ValueError):
            generate_walk_forward_folds(list(range(10)), config)

    def test_shared_complete_sessions_uses_full_history_intersection(self) -> None:
        rows = []
        for symbol in ("MNQ", "MGC"):
            for session, count in [("2023-01-03", 3), ("2023-01-04", 2), ("2026-07-02", 3)]:
                for i in range(count):
                    rows.append({"symbol": symbol, "trading_session": pd.Timestamp(session), "bar": i})
        rows.append({"symbol": "MGC", "trading_session": pd.Timestamp("2023-01-05"), "bar": 0})

        sessions = shared_complete_sessions(pd.DataFrame(rows), symbols=("MNQ", "MGC"), min_bars=3)

        self.assertEqual(sessions, [pd.Timestamp("2023-01-03"), pd.Timestamp("2026-07-02")])

    def test_promotion_requires_positive_test_folds_and_slippage_survival(self) -> None:
        strong = {
            "candidate_id": "demo",
            "folds": 5,
            "test_positive_folds": 4,
            "test_positive_fold_pct": 0.8,
            "test_net_pnl": 1500.0,
            "test_slippage_4_ticks_net_pnl": 900.0,
            "test_active_session_pct": 0.55,
            "test_trades": 80,
            "worst_test_fold_pnl": -150.0,
            "max_test_drawdown": -450.0,
            "test_best_day_concentration": 0.22,
            "test_best_trade_concentration": 0.16,
        }
        fragile = {
            **strong,
            "test_positive_folds": 2,
            "test_positive_fold_pct": 0.4,
            "test_slippage_4_ticks_net_pnl": -25.0,
            "test_active_session_pct": 0.2,
        }

        self.assertEqual(apply_walk_forward_promotion(strong)["phase5d_label"], "paper_test_candidate")
        rejected = apply_walk_forward_promotion(fragile)
        self.assertEqual(rejected["phase5d_label"], "rejected")
        self.assertIn("insufficient positive test folds", rejected["phase5d_notes"])


if __name__ == "__main__":
    unittest.main()
