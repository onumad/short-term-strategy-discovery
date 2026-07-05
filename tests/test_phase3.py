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
from short_term_edge.phase3 import (
    apply_daily_loss_stop,
    longest_losing_streak,
    slippage_net_pnl,
)


class Phase3MetricTests(unittest.TestCase):
    def test_longest_losing_streak(self) -> None:
        values = pd.Series([10.0, -1.0, -2.0, 3.0, -4.0, -5.0, -6.0, 7.0])
        self.assertEqual(longest_losing_streak(values), 3)

    def test_slippage_net_pnl_uses_round_turn_cost(self) -> None:
        trades = pd.DataFrame({"gross_pnl": [100.0, -50.0]})
        spec = get_instrument("MNQ")
        expected = (100.0 - (1.74 + 2 * 3 * 0.50)) + (-50.0 - (1.74 + 2 * 3 * 0.50))
        self.assertAlmostEqual(slippage_net_pnl(trades, spec, 3), expected)

    def test_daily_loss_stop_drops_later_trades_after_breach(self) -> None:
        trades = pd.DataFrame(
            [
                {"trading_session": "2026-01-02", "entry_time": "2026-01-02 10:00", "net_pnl": -300.0},
                {"trading_session": "2026-01-02", "entry_time": "2026-01-02 10:30", "net_pnl": -250.0},
                {"trading_session": "2026-01-02", "entry_time": "2026-01-02 11:00", "net_pnl": 500.0},
                {"trading_session": "2026-01-03", "entry_time": "2026-01-03 10:00", "net_pnl": 100.0},
            ]
        )
        stopped = apply_daily_loss_stop(trades, 500.0)
        self.assertEqual(len(stopped), 3)
        self.assertNotIn("2026-01-02 11:00", stopped["entry_time"].tolist())


if __name__ == "__main__":
    unittest.main()
