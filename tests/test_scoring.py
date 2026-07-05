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
from short_term_edge.scoring import score_candidate_trades
from short_term_edge.strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


def spec() -> StrategySpec:
    return StrategySpec(
        instrument="MNQ",
        family="opening_range_failure",
        timeframe=1,
        entry=EntryRule("close_back_inside", {"or_minutes": 30, "target": "opposite"}),
        exit=ExitRule("range_target", {"target": "opposite"}),
        risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
    )


def trades(pnls: list[float]) -> pd.DataFrame:
    sessions = [pd.Timestamp("2026-01-02").date(), pd.Timestamp("2026-01-03").date(), pd.Timestamp("2026-01-04").date(), pd.Timestamp("2026-01-05").date()]
    return pd.DataFrame(
        {
            "candidate_id": [spec().canonical_id()] * len(pnls),
            "trading_session": sessions[: len(pnls)],
            "entry_time": pd.date_range("2026-01-02 09:35", periods=len(pnls), freq="D", tz="America/New_York"),
            "exit_time": pd.date_range("2026-01-02 10:00", periods=len(pnls), freq="D", tz="America/New_York"),
            "net_pnl": pnls,
            "gross_pnl": [p + get_instrument("MNQ").base_cost for p in pnls],
            "side": ["long"] * len(pnls),
            "same_bar_stop_target_ambiguity": [0] * len(pnls),
            "split": ["discovery", "discovery", "validation", "holdout"][: len(pnls)],
        }
    )


class ScoringTests(unittest.TestCase):
    def test_empty_trades_are_rejected(self) -> None:
        score = score_candidate_trades(spec(), pd.DataFrame(), get_instrument("MNQ"), [pd.Timestamp("2026-01-02").date()])
        self.assertEqual(score.label, "rejected")
        self.assertIn("No trades", score.risk_notes)

    def test_profitable_concentrated_candidate_is_not_promoted(self) -> None:
        score = score_candidate_trades(spec(), trades([1000.0, -10.0, -10.0, 25.0]), get_instrument("MNQ"), list(trades([1, 2, 3, 4])["trading_session"]))
        self.assertGreater(score.net_pnl, 0)
        self.assertNotEqual(score.label, "paper_trade_candidate")
        self.assertIn("one-trade concentration risk", score.risk_notes)

    def test_split_aware_score_is_deterministic(self) -> None:
        frame = trades([100.0, 120.0, 80.0, 60.0])
        first = score_candidate_trades(spec(), frame.sample(frac=1.0, random_state=7), get_instrument("MNQ"), list(frame["trading_session"]))
        second = score_candidate_trades(spec(), frame, get_instrument("MNQ"), list(frame["trading_session"]))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.holdout_pnl, 60.0)


if __name__ == "__main__":
    unittest.main()
