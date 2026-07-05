from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5c import Phase5CConfig, apply_phase5c_robust_scoring, select_seeded_strategy_specs


class Phase5CTests(unittest.TestCase):
    def test_seeded_spec_selection_is_reproducible_and_mnq_first(self) -> None:
        config = Phase5CConfig(symbols=("MNQ", "MGC"), candidates_per_symbol=8, seed=123)
        first = select_seeded_strategy_specs(config)
        second = select_seeded_strategy_specs(config)
        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertEqual([spec.instrument for spec in first[:8]], ["MNQ"] * 8)
        self.assertEqual([spec.instrument for spec in first[8:]], ["MGC"] * 8)
        self.assertTrue(all(spec.to_json() for spec in first))

    def test_different_seed_changes_tail_selection(self) -> None:
        a = select_seeded_strategy_specs(Phase5CConfig(symbols=("MNQ",), candidates_per_symbol=20, seed=1))
        b = select_seeded_strategy_specs(Phase5CConfig(symbols=("MNQ",), candidates_per_symbol=20, seed=2))
        self.assertNotEqual([spec.canonical_id() for spec in a], [spec.canonical_id() for spec in b])

    def test_robust_scoring_penalizes_fragile_candidate(self) -> None:
        base = {
            "candidate_id": "demo",
            "instrument": "MNQ",
            "family": "opening_range_failure",
            "timeframe": 1,
            "ranking_score": 60.0,
            "net_pnl": 1000.0,
            "validation_pnl": 800.0,
            "holdout_pnl": 500.0,
            "slippage_4_ticks_net_pnl": 900.0,
            "trades": 80,
            "active_session_pct": 0.8,
            "max_drawdown": -250.0,
            "best_day_concentration": 0.20,
            "best_trade_concentration": 0.10,
        }
        robust = apply_phase5c_robust_scoring(base)
        fragile = apply_phase5c_robust_scoring(
            {
                **base,
                "holdout_pnl": -200.0,
                "slippage_4_ticks_net_pnl": -100.0,
                "trades": 5,
                "active_session_pct": 0.05,
                "max_drawdown": -5000.0,
                "best_day_concentration": 0.80,
                "best_trade_concentration": 0.70,
            }
        )
        self.assertGreater(robust["phase5c_score"], fragile["phase5c_score"])
        self.assertEqual(fragile["phase5c_label"], "rejected")
        self.assertGreater(fragile["phase5c_total_penalty"], robust["phase5c_total_penalty"])


if __name__ == "__main__":
    unittest.main()
