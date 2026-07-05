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
from short_term_edge.phase3b import ExecutionMode
from short_term_edge.phase4a import (
    Phase4ACandidate,
    _entry_pos_after_signal,
    resample_signal_bars,
    simulate_one_minute_trade,
    simulate_phase4a_candidate,
)


def sample_day() -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-02 09:30", periods=10, freq="min", tz="America/New_York")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": "MNQ",
            "open": [100.0 + i for i in range(10)],
            "high": [101.0 + i for i in range(10)],
            "low": [99.0 + i for i in range(10)],
            "close": [100.5 + i for i in range(10)],
            "volume": [10 + i for i in range(10)],
            "trading_session": [pd.Timestamp("2026-01-02").date()] * 10,
            "session_segment": ["RTH"] * 10,
        }
    )


def candidate(mode: ExecutionMode) -> Phase4ACandidate:
    return Phase4ACandidate(
        candidate_id="MNQ_test",
        instrument="MNQ",
        family="test",
        variant="test",
        signal_timeframe=5,
        execution_timeframe="1m",
        entry_rule="test",
        stop_rule="test",
        target_rule="test",
        time_stop="15:55 ET",
        mode=mode,
        params={},
    )


class Phase4ATests(unittest.TestCase):
    def test_resample_anchors_to_0930_and_aggregates_ohlcv(self) -> None:
        bars = resample_signal_bars(sample_day(), 5)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars.iloc[0]["bar_start"].strftime("%H:%M"), "09:30")
        self.assertEqual(bars.iloc[0]["bar_end"].strftime("%H:%M"), "09:35")
        self.assertEqual(float(bars.iloc[0]["open"]), 100.0)
        self.assertEqual(float(bars.iloc[0]["high"]), 105.0)
        self.assertEqual(float(bars.iloc[0]["low"]), 99.0)
        self.assertEqual(float(bars.iloc[0]["close"]), 104.5)
        self.assertEqual(float(bars.iloc[0]["volume"]), sum(range(10, 15)))
        self.assertEqual(bars.iloc[1]["bar_start"].strftime("%H:%M"), "09:35")

    def test_resample_drops_incomplete_higher_timeframe_bar(self) -> None:
        bars = resample_signal_bars(sample_day().iloc[:9], 5)
        self.assertEqual(len(bars), 1)
        self.assertEqual(int(bars.iloc[0]["source_bar_count"]), 5)

    def test_bar_start_semantics_prevent_higher_timeframe_lookahead(self) -> None:
        day = sample_day()
        bars = resample_signal_bars(day, 5)
        first_signal_available = bars.iloc[0]["bar_end"]
        pos = _entry_pos_after_signal(day, first_signal_available)
        self.assertIsNotNone(pos)
        self.assertEqual(day.iloc[pos]["timestamp"].strftime("%H:%M"), "09:35")

    def test_one_minute_trade_counts_same_bar_ambiguity_and_uses_stop_first(self) -> None:
        day = sample_day().copy()
        day.loc[0, "open"] = 100.0
        day.loc[0, "high"] = 106.0
        day.loc[0, "low"] = 94.0
        trade = simulate_one_minute_trade(day, 0, "long", 95.0, 105.0, get_instrument("MNQ"))
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertEqual(trade["exit_price"], 95.0)
        self.assertEqual(trade["same_bar_stop_target_ambiguity"], 1)

    def test_no_overlap_blocks_second_signal_while_trade_open(self) -> None:
        day = sample_day()
        signals = [
            {
                "timestamp": day.iloc[0]["timestamp"],
                "available_time": day.iloc[1]["timestamp"],
                "trading_session": day.iloc[0]["trading_session"],
                "side": "long",
                "stop": 50.0,
                "target": 500.0,
                "reason": "test_long",
            },
            {
                "timestamp": day.iloc[1]["timestamp"],
                "available_time": day.iloc[2]["timestamp"],
                "trading_session": day.iloc[0]["trading_session"],
                "side": "long",
                "stop": 50.0,
                "target": 500.0,
                "reason": "test_long",
            },
        ]
        trades = simulate_phase4a_candidate(day, signals, candidate(ExecutionMode("max2", 2)), get_instrument("MNQ"), [day.iloc[0]["trading_session"]])
        self.assertEqual(len(trades), 1)

    def test_max_one_per_day_and_stop_after_first_loser_modes(self) -> None:
        day = sample_day()
        signals = [
            {
                "timestamp": day.iloc[0]["timestamp"],
                "available_time": day.iloc[1]["timestamp"],
                "trading_session": day.iloc[0]["trading_session"],
                "side": "long",
                "stop": 100.0,
                "target": 500.0,
                "reason": "test_long",
            },
            {
                "timestamp": day.iloc[2]["timestamp"],
                "available_time": day.iloc[3]["timestamp"],
                "trading_session": day.iloc[0]["trading_session"],
                "side": "short",
                "stop": 500.0,
                "target": 50.0,
                "reason": "test_short",
            },
        ]
        max_one = simulate_phase4a_candidate(day, signals, candidate(ExecutionMode("max1", 1)), get_instrument("MNQ"), [day.iloc[0]["trading_session"]])
        self.assertEqual(len(max_one), 1)
        stop_loser = simulate_phase4a_candidate(
            day,
            signals,
            candidate(ExecutionMode("stop_after_first_loser", 2, stop_after_first_loser=True)),
            get_instrument("MNQ"),
            [day.iloc[0]["trading_session"]],
        )
        self.assertEqual(len(stop_loser), 1)
        self.assertLess(float(stop_loser.iloc[0]["net_pnl"]), 0.0)


if __name__ == "__main__":
    unittest.main()
