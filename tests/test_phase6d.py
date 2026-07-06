from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5n import filter_signals_by_side
from short_term_edge.phase6d import Phase6DConfig, rank_side_only_results, select_side_only_specs


class Phase6DTests(unittest.TestCase):
    def test_filter_signals_by_side_keeps_only_requested_direction(self) -> None:
        signals = [
            {"side": "long", "id": 1},
            {"side": "short", "id": 2},
            {"side": "long", "id": 3},
        ]

        self.assertEqual([signal["id"] for signal in filter_signals_by_side(signals, "long")], [1, 3])
        self.assertEqual([signal["id"] for signal in filter_signals_by_side(signals, "short")], [2])
        self.assertEqual(filter_signals_by_side(signals, "both"), signals)

    def test_select_side_only_specs_creates_long_and_short_variants(self) -> None:
        specs = select_side_only_specs(PROJECT_ROOT, Phase6DConfig(max_specs=12, min_specs=8))

        self.assertLessEqual(len(specs), 12)
        self.assertGreaterEqual(len(specs), 8)
        self.assertEqual({spec.instrument for spec in specs}, {"MNQ"})
        self.assertEqual({spec.risk.params["side_filter"] for spec in specs}, {"long", "short"})
        self.assertEqual([spec.canonical_id() for spec in specs], [spec.canonical_id() for spec in select_side_only_specs(PROJECT_ROOT, Phase6DConfig(max_specs=12, min_specs=8))])

    def test_rank_side_only_results_promotes_cleaner_directional_candidate(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "raw_high_net",
                    "side_filter": "both",
                    "net_pnl": 5000.0,
                    "slippage_4_ticks_net_pnl": 2500.0,
                    "trades": 800,
                    "active_session_pct": 0.90,
                    "max_drawdown": -4500.0,
                    "best_day_concentration": 0.45,
                    "best_trade_concentration": 0.30,
                    "validation_pnl": 1000.0,
                    "holdout_pnl": 1000.0,
                },
                {
                    "candidate_id": "directional_clean",
                    "side_filter": "short",
                    "net_pnl": 1400.0,
                    "slippage_4_ticks_net_pnl": 850.0,
                    "trades": 120,
                    "active_session_pct": 0.32,
                    "max_drawdown": -900.0,
                    "best_day_concentration": 0.22,
                    "best_trade_concentration": 0.14,
                    "validation_pnl": 250.0,
                    "holdout_pnl": 200.0,
                },
            ]
        )

        ranked = rank_side_only_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "directional_clean")
        self.assertEqual(ranked.iloc[0]["phase6d_label"], "side_only_prefilter_survivor")


if __name__ == "__main__":
    unittest.main()
