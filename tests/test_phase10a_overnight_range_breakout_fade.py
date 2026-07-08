from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase10a_overnight_range_breakout_fade import (  # noqa: E402
    Phase10AConfig,
    build_phase10a_specs,
    compute_overnight_levels,
    generate_phase10a_signals,
    run_phase10a_retest,
    serialize_phase10a_specs,
)


class Phase10AOvernightRangeTests(unittest.TestCase):
    def _bars(self) -> pd.DataFrame:
        rows = []
        session = "2026-01-06"
        # ETH belongs to 2026-01-06 via CME 18:00 mapping.
        eth_times = ["2026-01-05 18:00", "2026-01-05 22:00", "2026-01-06 09:29"]
        for ts_s, high, low, close in zip(eth_times, [101.0, 102.0, 101.4], [99.5, 99.8, 100.1], [100.2, 101.5, 100.8]):
            rows.append({"timestamp": pd.Timestamp(ts_s, tz="America/New_York"), "symbol": "MNQ", "open": close, "high": high, "low": low, "close": close, "volume": 100, "trading_session": session, "session_segment": "ETH"})
        price = 100.8
        for minute in range(9 * 60 + 30, 11 * 60):
            ts = pd.Timestamp(f"2026-01-06 {minute//60:02d}:{minute%60:02d}", tz="America/New_York")
            high, low, close = price + 0.15, price - 0.15, price
            if minute == 9 * 60 + 40:  # long breakout close above ONH
                high, low, close = 102.8, 101.8, 102.5
            if minute == 9 * 60 + 45:  # short fade close back inside after sweep high
                high, low, close = 102.6, 101.2, 101.8
            if minute == 10 * 60 + 10:  # short breakout close below ONL
                high, low, close = 99.6, 98.9, 99.1
            if minute == 10 * 60 + 15:  # long fade close back inside after sweep low
                high, low, close = 100.4, 99.0, 99.9
            rows.append({"timestamp": ts, "symbol": "MNQ", "open": price, "high": high, "low": low, "close": close, "volume": 100, "trading_session": session, "session_segment": "RTH"})
            price = close
        return pd.DataFrame(rows)

    def test_specs_are_exact_48_and_deterministic(self) -> None:
        specs = build_phase10a_specs(Phase10AConfig(max_specs=48))
        self.assertEqual(len(specs), 48)
        self.assertEqual({s.branch for s in specs}, {"overnight_range_breakout", "overnight_range_fade"})
        self.assertEqual({s.side for s in specs}, {"long", "short"})
        self.assertEqual({s.timeframe for s in specs}, {5, 15})
        self.assertEqual({s.entry_window for s in specs}, {"opening_response", "midday_response"})
        self.assertEqual({s.execution_exit_variant for s in specs}, {"next_bar_open_hard_stop_time_exit", "next_bar_open_hard_stop_structure_target_time_exit", "close_confirm_fill_next_open_hard_stop_time_exit"})
        payload = json.loads(serialize_phase10a_specs(specs[:2]))
        self.assertEqual(payload[0]["instrument"], "MNQ")

    def test_overnight_levels_use_only_eth_pre_rth_and_are_frozen(self) -> None:
        bars = self._bars()
        levels = compute_overnight_levels(bars)
        row = levels.iloc[0]
        self.assertEqual(float(row["overnight_high"]), 102.0)
        self.assertEqual(float(row["overnight_low"]), 99.5)
        self.assertEqual(float(row["overnight_midpoint"]), 100.75)
        # RTH high above ONH must not alter frozen level.
        self.assertLess(float(row["overnight_high"]), float(bars[bars["session_segment"].eq("RTH")]["high"].max()))

    def test_breakout_and_fade_signals_require_level_behavior_and_rth_windows(self) -> None:
        bars = self._bars()
        specs = build_phase10a_specs(Phase10AConfig(max_specs=48))
        long_break = next(s for s in specs if s.branch == "overnight_range_breakout" and s.side == "long" and s.entry_window == "opening_response")
        short_break = next(s for s in specs if s.branch == "overnight_range_breakout" and s.side == "short" and s.entry_window == "opening_response")
        short_fade = next(s for s in specs if s.branch == "overnight_range_fade" and s.side == "short" and s.entry_window == "opening_response")
        long_fade = next(s for s in specs if s.branch == "overnight_range_fade" and s.side == "long" and s.entry_window == "opening_response")
        self.assertTrue(generate_phase10a_signals(bars, long_break))
        self.assertTrue(generate_phase10a_signals(bars, short_break))
        self.assertTrue(generate_phase10a_signals(bars, short_fade))
        self.assertTrue(generate_phase10a_signals(bars, long_fade))
        for sig in generate_phase10a_signals(bars, long_break):
            minute = pd.Timestamp(sig["signal_time"]).hour * 60 + pd.Timestamp(sig["signal_time"]).minute
            self.assertGreaterEqual(minute, 9 * 60 + 35)
            self.assertLess(minute, 10 * 60 + 30)
            self.assertGreater(float(sig["signal_close"]), float(sig["overnight_high"]))

    def test_confirm_fill_next_open_entries_are_after_confirmation_close(self) -> None:
        specs = build_phase10a_specs(Phase10AConfig(max_specs=48))
        spec = next(s for s in specs if s.execution_exit_variant.startswith("close_confirm") and s.branch == "overnight_range_fade" and s.side == "short")
        signals = generate_phase10a_signals(self._bars(), spec)
        self.assertTrue(signals)
        self.assertTrue(all(pd.Timestamp(s["entry_time"]) > pd.Timestamp(s["confirmation_time"]) for s in signals))

    def test_run_outputs_labels_stops_ambiguity_and_report_fields(self) -> None:
        result = run_phase10a_retest(self._bars(), Phase10AConfig(max_specs=6, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        self.assertFalse(result["candidate_results"].empty)
        self.assertIn("phase10a_label", result["candidate_results"].columns)
        self.assertIn("same_bar_ambiguity", result["trade_logs"].columns)
        self.assertIn("actual_stop", result["trade_logs"].columns)
        self.assertFalse(result["level_diagnostics"].empty)
        self.assertFalse(result["branch_summary"].empty)


if __name__ == "__main__":
    unittest.main()
