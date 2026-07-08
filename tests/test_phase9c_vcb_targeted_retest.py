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

from short_term_edge.phase9c_vcb_targeted_retest import (  # noqa: E402
    Phase9CConfig,
    build_phase9c_specs,
    compute_phase9c_features,
    generate_phase9c_signals,
    run_phase9c_retest,
    serialize_phase9c_specs,
)


class Phase9CTargetedRetestTests(unittest.TestCase):
    def _bars(self) -> pd.DataFrame:
        rows = []
        for session in ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]:
            price = 100.0
            for idx, minute in enumerate(range(9 * 60 + 30, 14 * 60)):
                ts = pd.Timestamp(f"{session} {minute // 60:02d}:{minute % 60:02d}", tz="America/New_York")
                if 70 <= idx < 82:
                    high, low, close = price + 0.05, price - 0.05, price - 0.01
                elif idx == 82:
                    high, low, close = price + 0.05, price - 1.0, price - 0.8
                    price = close
                elif idx == 83:
                    price -= 0.4
                    high, low, close = price + 0.05, price - 0.4, price - 0.2
                elif idx == 100:
                    high, low, close = price + 0.6, price - 0.1, price + 0.2
                    price = close
                else:
                    price += 0.01
                    high, low, close = price + 0.20, price - 0.20, price
                rows.append({"timestamp": ts, "symbol": "MNQ", "open": price, "high": high, "low": low, "close": close, "volume": 100, "trading_session": session, "session_segment": "RTH"})
        return pd.DataFrame(rows)

    def test_specs_are_48_short_only_and_separate_primary_from_diagnostic_windows(self) -> None:
        specs = build_phase9c_specs(Phase9CConfig(max_specs=48))
        self.assertEqual(len(specs), 48)
        self.assertEqual({spec.direction_mode for spec in specs}, {"short_only"})
        self.assertEqual({spec.time_window for spec in specs}, {"core_midday", "extended_midday"})
        self.assertTrue(all(spec.is_primary_eligible == (spec.time_window == "core_midday") for spec in specs))
        self.assertEqual({spec.entry_model for spec in specs}, {"next_bar_open", "close_confirm_fill_next_open"})
        self.assertEqual({spec.exit_model for spec in specs}, {"capped_opposite_box_stop_time_exit", "close_back_inside_box_invalidation_with_hard_cap"})

    def test_compression_box_is_shifted_and_signals_are_short_only_without_future_bars(self) -> None:
        spec = build_phase9c_specs(Phase9CConfig(max_specs=1))[0]
        features = compute_phase9c_features(self._bars(), spec)
        formed = features.dropna(subset=["box_high", "box_low"])
        row = formed.iloc[0]
        prior = features[(features["trading_session"].eq(row["trading_session"])) & (features["timestamp"] < row["timestamp"])].tail(max(3, spec.compression_lookback // 2))
        self.assertEqual(float(row["box_high"]), float(prior["high"].max()))
        signals = generate_phase9c_signals(features, spec)
        self.assertTrue(signals)
        self.assertEqual({signal["side"] for signal in signals}, {"short"})
        self.assertTrue(all(pd.Timestamp(signal["entry_time"]) > pd.Timestamp(signal["signal_time"]) for signal in signals))

    def test_time_windows_exclude_bad_windows_and_flag_extended_as_diagnostic(self) -> None:
        specs = build_phase9c_specs(Phase9CConfig(max_specs=48))
        core = next(spec for spec in specs if spec.time_window == "core_midday")
        extended = next(spec for spec in specs if spec.time_window == "extended_midday")
        self.assertEqual(core.entry_start, "10:30")
        self.assertEqual(core.entry_end, "13:30")
        self.assertTrue(core.is_primary_eligible)
        self.assertEqual(extended.entry_start, "10:00")
        self.assertFalse(extended.is_primary_eligible)
        features = compute_phase9c_features(self._bars(), core)
        signals = generate_phase9c_signals(features, core)
        self.assertTrue(all(10 * 60 + 30 <= pd.Timestamp(s["signal_time"]).hour * 60 + pd.Timestamp(s["signal_time"]).minute < 13 * 60 + 30 for s in signals))

    def test_confirm_entry_fills_after_confirmation_bar_and_invalidation_exits_next_bar(self) -> None:
        specs = build_phase9c_specs(Phase9CConfig(max_specs=48))
        spec = next(s for s in specs if s.entry_model == "close_confirm_fill_next_open" and s.exit_model == "close_back_inside_box_invalidation_with_hard_cap")
        result = run_phase9c_retest(self._bars(), Phase9CConfig(max_specs=4, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        trades = result["trade_logs"]
        sample = trades[trades["entry_model"].eq(spec.entry_model)]
        self.assertFalse(sample.empty)
        self.assertTrue((pd.to_datetime(sample["entry_time"]) > pd.to_datetime(sample["confirmation_time"])).all())
        invalid = trades[trades["exit_reason"].eq("invalidation_exit")]
        if not invalid.empty:
            self.assertTrue((pd.to_datetime(invalid["exit_time"]) > pd.to_datetime(invalid["invalidation_time"])).all())

    def test_hard_cap_stop_active_and_same_bar_policy_is_conservative(self) -> None:
        result = run_phase9c_retest(self._bars(), Phase9CConfig(max_specs=8, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        trades = result["trade_logs"]
        self.assertFalse(trades.empty)
        self.assertTrue((trades["stop_price"] <= trades["opposite_box_stop"]).all())
        self.assertIn("same_bar_ambiguity", trades.columns)
        ambiguous = trades[trades["same_bar_ambiguity"].eq(1)]
        if not ambiguous.empty:
            self.assertTrue(ambiguous["exit_reason"].str.contains("stop").all())

    def test_outputs_include_required_diagnostics_labels_and_deterministic_specs(self) -> None:
        result = run_phase9c_retest(self._bars(), Phase9CConfig(max_specs=8, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        candidates = result["candidate_results"]
        self.assertFalse(candidates.empty)
        for column in ["quick_or_adverse_stop_count", "quick_or_adverse_stop_rate", "quick_or_adverse_stop_net", "time_stop_pnl", "target_pnl", "stop_pnl", "invalidation_exit_pnl", "phase9c_label"]:
            self.assertIn(column, candidates.columns)
        self.assertIn("stop_failure_bucket", result["trade_logs"].columns)
        payload = serialize_phase9c_specs(build_phase9c_specs(Phase9CConfig(max_specs=2)))
        self.assertEqual(json.loads(payload)[0]["direction_mode"], "short_only")


if __name__ == "__main__":
    unittest.main()
