from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


class StrategySpecTests(unittest.TestCase):
    def test_canonical_id_is_deterministic_for_param_order(self) -> None:
        left = StrategySpec(
            instrument="MNQ",
            family="opening_range_failure",
            timeframe=5,
            entry=EntryRule("close_back_inside", {"target": "mid", "or_minutes": 30}),
            exit=ExitRule("range_target", {"target": "mid"}),
            risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
        )
        right = StrategySpec(
            instrument="MNQ",
            family="opening_range_failure",
            timeframe=5,
            entry=EntryRule("close_back_inside", {"or_minutes": 30, "target": "mid"}),
            exit=ExitRule("range_target", {"target": "mid"}),
            risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
        )
        self.assertEqual(left.canonical_id(), right.canonical_id())
        self.assertIn("MNQ_opening_range_failure_tf5", left.canonical_id())

    def test_json_round_trip_preserves_spec(self) -> None:
        spec = StrategySpec(
            instrument="MGC",
            family="vwap_reclaim_rejection",
            timeframe=1,
            entry=EntryRule("vwap_cross", {"mode": "both"}),
            exit=ExitRule("fixed_ticks", {"stop_ticks": 18, "target_ticks": 27}),
            risk=RiskRule("one_open_position", {"max_trades_per_day": 2, "stop_after_first_loser": True}),
        )
        self.assertEqual(StrategySpec.from_json(spec.to_json()), spec)

    def test_unknown_family_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            StrategySpec(
                instrument="MNQ",
                family="neural_net_black_box",
                timeframe=1,
                entry=EntryRule("opaque", {}),
                exit=ExitRule("opaque", {}),
                risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
            ).validate()


if __name__ == "__main__":
    unittest.main()
