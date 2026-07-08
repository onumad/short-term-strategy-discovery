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

from short_term_edge.phase10b_overnight_range_targeted_retest import (  # noqa: E402
    Phase10BConfig,
    build_phase10b_specs,
    apply_phase10b_pre_entry_filters,
    run_phase10b_retest,
    serialize_phase10b_specs,
)


class Phase10BOvernightTargetedRetestTests(unittest.TestCase):
    def _trades(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"candidate_id": "a", "trading_session": "2026-01-06", "entry_time": pd.Timestamp("2026-01-06 10:45", tz="America/New_York"), "overnight_range_percentile": 0.10, "gap_from_prior_rth_close": -5.0, "first_touch": 1, "gross_pnl": 100.0, "net_pnl": 96.0, "stress_pnl": 94.0, "exit_reason": "time_stop", "branch": "overnight_range_breakout", "side": "short", "mfe": 100.0, "mae": 50.0},
            {"candidate_id": "a", "trading_session": "2026-01-06", "entry_time": pd.Timestamp("2026-01-06 11:15", tz="America/New_York"), "overnight_range_percentile": 0.50, "gap_from_prior_rth_close": 4.0, "first_touch": 0, "gross_pnl": -20.0, "net_pnl": -24.0, "stress_pnl": -26.0, "exit_reason": "stop", "branch": "overnight_range_breakout", "side": "short", "mfe": 10.0, "mae": 60.0},
            {"candidate_id": "b", "trading_session": "2026-01-07", "entry_time": pd.Timestamp("2026-01-07 09:45", tz="America/New_York"), "overnight_range_percentile": 0.90, "gap_from_prior_rth_close": -1.0, "first_touch": 1, "gross_pnl": 50.0, "net_pnl": 46.0, "stress_pnl": 44.0, "exit_reason": "target", "branch": "overnight_range_fade", "side": "long", "mfe": 80.0, "mae": 20.0},
        ])

    def test_matrix_builds_exact_48_with_primary_and_secondary_axes(self) -> None:
        specs = build_phase10b_specs(Phase10BConfig(max_specs=48))
        self.assertEqual(len(specs), 48)
        primary = [s for s in specs if s.axis == "primary_short_midday_breakout"]
        secondary = [s for s in specs if s.axis == "secondary_long_opening_fade"]
        self.assertEqual(len(primary), 32)
        self.assertEqual(len(secondary), 16)
        self.assertTrue(all(s.branch == "overnight_range_breakout" and s.side == "short" and s.timeframe == 15 and s.entry_window == "midday_response" for s in primary))
        self.assertTrue(all(s.branch == "overnight_range_fade" and s.side == "long" and s.entry_window == "opening_response" for s in secondary))

    def test_pre_entry_filters_use_range_gap_and_first_touch_without_dates(self) -> None:
        spec = next(s for s in build_phase10b_specs() if s.range_filter == "middle_60_only" and s.gap_filter == "gap_down_or_flat" and s.touch_filter == "first_touch_only")
        filtered = apply_phase10b_pre_entry_filters(self._trades(), spec)
        self.assertTrue(filtered.empty)
        spec2 = next(s for s in build_phase10b_specs() if s.range_filter == "exclude_widest_20" and s.gap_filter == "all_gaps" and s.touch_filter == "all_touches")
        filtered2 = apply_phase10b_pre_entry_filters(self._trades(), spec2)
        self.assertEqual(len(filtered2), 2)
        self.assertNotIn("excluded_session", filtered2.columns)

    def test_run_outputs_cost_waterfall_axis_status_and_summaries(self) -> None:
        result = run_phase10b_retest(self._trades(), Phase10BConfig(max_specs=4, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        candidates = result["candidate_results"]
        self.assertFalse(candidates.empty)
        for col in ["gross_pnl", "fees_only_pnl", "normal_slippage_pnl", "stress_pnl", "research_axis_status", "phase10b_label"]:
            self.assertIn(col, candidates.columns)
        for key in ["validation_failure_attribution", "range_regime_summary", "gap_regime_summary", "touch_sequence_summary", "branch_summary", "exit_reason_summary", "mfe_mae_summary"]:
            self.assertIn(key, result)

    def test_specs_serialize_deterministically(self) -> None:
        payload = serialize_phase10b_specs(build_phase10b_specs(Phase10BConfig(max_specs=2)))
        parsed = json.loads(payload)
        self.assertEqual(parsed[0]["instrument"], "MNQ")
        self.assertIn("range_filter", parsed[0])


if __name__ == "__main__":
    unittest.main()
