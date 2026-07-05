from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.concentration import build_period_pnl, summarize_concentration


class ConcentrationTests(unittest.TestCase):
    def test_build_period_pnl_groups_day_week_and_month(self) -> None:
        trades = pd.DataFrame(
            [
                {"candidate_id": "a", "trading_session": pd.Timestamp("2024-01-02"), "net_pnl": 100.0},
                {"candidate_id": "a", "trading_session": pd.Timestamp("2024-01-03"), "net_pnl": -25.0},
                {"candidate_id": "a", "trading_session": pd.Timestamp("2024-02-01"), "net_pnl": 50.0},
                {"candidate_id": "b", "trading_session": pd.Timestamp("2024-01-02"), "net_pnl": 10.0},
            ]
        )

        day = build_period_pnl(trades, "D")
        week = build_period_pnl(trades, "W")
        month = build_period_pnl(trades, "M")

        self.assertEqual(day.loc[(day["candidate_id"] == "a") & (day["period"] == "2024-01-02"), "net_pnl"].iloc[0], 100.0)
        self.assertEqual(int(day.loc[day["candidate_id"] == "a", "trades"].sum()), 3)
        self.assertEqual(float(week.loc[week["candidate_id"] == "a", "net_pnl"].iloc[0]), 75.0)
        self.assertIn("2024-02", set(month["period"]))

    def test_summarize_concentration_flags_one_period_dominance(self) -> None:
        day = pd.DataFrame(
            [
                {"candidate_id": "a", "period": "2024-01-02", "net_pnl": 900.0, "trades": 3},
                {"candidate_id": "a", "period": "2024-01-03", "net_pnl": 100.0, "trades": 2},
                {"candidate_id": "b", "period": "2024-01-02", "net_pnl": 50.0, "trades": 1},
            ]
        )
        week = pd.DataFrame(
            [
                {"candidate_id": "a", "period": "2024-W01", "net_pnl": 1000.0, "trades": 5},
                {"candidate_id": "b", "period": "2024-W01", "net_pnl": 50.0, "trades": 1},
            ]
        )
        month = pd.DataFrame(
            [
                {"candidate_id": "a", "period": "2024-01", "net_pnl": 1000.0, "trades": 5},
                {"candidate_id": "b", "period": "2024-01", "net_pnl": 50.0, "trades": 1},
            ]
        )

        summary = summarize_concentration(day, week, month)
        a = summary[summary["candidate_id"] == "a"].iloc[0]

        self.assertEqual(a["best_day_pnl"], 900.0)
        self.assertAlmostEqual(a["best_day_concentration"], 0.9)
        self.assertEqual(a["concentration_label"], "concentrated")
        self.assertIn("day concentration", a["concentration_notes"])


if __name__ == "__main__":
    unittest.main()
