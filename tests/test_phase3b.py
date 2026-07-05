from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.instruments import get_instrument
from short_term_edge.phase3b import (
    _max_simultaneous_by_session,
    audit_overlaps,
    execution_mode_metrics,
)


def sample_trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate_id": "x",
                "trading_session": "2026-01-02",
                "entry_time": "2026-01-02 10:00",
                "exit_time": "2026-01-02 10:30",
                "side": "long",
                "reason": "or_failure_long",
                "gross_pnl": -100.0,
                "net_pnl": -102.74,
                "split": "discovery",
            },
            {
                "candidate_id": "x",
                "trading_session": "2026-01-02",
                "entry_time": "2026-01-02 10:05",
                "exit_time": "2026-01-02 10:30",
                "side": "long",
                "reason": "or_failure_long",
                "gross_pnl": -90.0,
                "net_pnl": -92.74,
                "split": "discovery",
            },
            {
                "candidate_id": "x",
                "trading_session": "2026-01-03",
                "entry_time": "2026-01-03 10:00",
                "exit_time": "2026-01-03 10:10",
                "side": "short",
                "reason": "or_failure_short",
                "gross_pnl": 200.0,
                "net_pnl": 197.26,
                "split": "holdout",
            },
        ]
    )


class Phase3BTests(unittest.TestCase):
    def test_overlap_audit_detects_same_side_same_exit_pair(self) -> None:
        pairs, summary = audit_overlaps(sample_trades())
        self.assertEqual(summary["overlapping_trade_pairs"], 1)
        self.assertEqual(summary["same_side_overlap_pairs"], 1)
        self.assertEqual(summary["same_exit_overlap_pairs"], 1)
        self.assertTrue(summary["has_more_than_1_mnq_exposure"])
        self.assertEqual(len(pairs), 1)

    def test_max_simultaneous_uses_half_open_intervals(self) -> None:
        trades = pd.DataFrame(
            [
                {"trading_session": "d", "entry_time": "2026-01-02 10:00", "exit_time": "2026-01-02 10:05", "net_pnl": 1, "reason": "or_failure_long"},
                {"trading_session": "d", "entry_time": "2026-01-02 10:05", "exit_time": "2026-01-02 10:10", "net_pnl": 1, "reason": "or_failure_short"},
            ]
        )
        self.assertEqual(_max_simultaneous_by_session(trades), 1)

    def test_execution_mode_metrics_include_strict_slippage_and_label(self) -> None:
        trades = sample_trades().iloc[[2]].copy()
        metrics = execution_mode_metrics("B_one_open_position", trades, get_instrument("MNQ"), ["2026-01-02", "2026-01-03"])
        self.assertEqual(metrics["trades"], 1)
        self.assertAlmostEqual(metrics["slippage_4_ticks_net_pnl"], 200.0 - (1.74 + 2 * 4 * 0.50))
        self.assertEqual(metrics["max_simultaneous_exposure"], 1)


if __name__ == "__main__":
    unittest.main()
