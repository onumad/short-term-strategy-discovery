from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase9b_vcb_failure_attribution import (  # noqa: E402
    Phase9BConfig,
    assign_phase9b_time_bucket,
    build_phase9b_specs,
    compute_phase9b_trade_attribution,
    group_phase9b_summary,
    make_phase9b_recommendation,
    render_phase9b_report,
    run_phase9b_diagnostic,
)


class Phase9BFailureAttributionTests(unittest.TestCase):
    def _bars(self) -> pd.DataFrame:
        rows = []
        sessions = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]
        for day_i, session in enumerate(sessions):
            price = 100.0 + day_i
            for idx, minute in enumerate(range(9 * 60 + 30, 11 * 60 + 45)):
                ts = pd.Timestamp(f"{session} {minute // 60:02d}:{minute % 60:02d}", tz="America/New_York")
                if 20 <= idx < 32:
                    high, low, close = price + 0.05, price - 0.05, price + 0.01
                elif idx == 32:
                    high, low, close = price + 1.2, price - 0.05, price + 1.0
                    price = close
                elif idx == 54:
                    high, low, close = price + 0.05, price - 1.2, price - 1.0
                    price = close
                else:
                    price += 0.04
                    high, low, close = price + 0.25, price - 0.25, price
                rows.append({"timestamp": ts, "symbol": "MNQ", "open": price, "high": high, "low": low, "close": close, "volume": 100, "trading_session": session, "session_segment": "RTH"})
        return pd.DataFrame(rows)

    def test_build_phase9b_specs_is_bounded_representative_and_includes_entry_diagnostics(self) -> None:
        specs = build_phase9b_specs(Phase9BConfig(max_specs=48))

        self.assertEqual(len(specs), 48)
        self.assertEqual({spec.timeframe for spec in specs}, {5, 15})
        self.assertEqual({spec.compression_method for spec in specs}, {"range_percentile", "atr_percentile", "realized_vol_percentile"})
        self.assertEqual({spec.entry_model for spec in specs}, {"next_bar_open", "next_bar_close"})
        self.assertEqual({spec.direction_mode for spec in specs}, {"long_only", "short_only"})

    def test_time_bucket_assignment_uses_new_york_bar_start_windows(self) -> None:
        self.assertEqual(assign_phase9b_time_bucket(pd.Timestamp("2026-01-05 09:45", tz="America/New_York")), "09:30-10:00")
        self.assertEqual(assign_phase9b_time_bucket(pd.Timestamp("2026-01-05 10:15", tz="America/New_York")), "10:00-10:30")
        self.assertEqual(assign_phase9b_time_bucket(pd.Timestamp("2026-01-05 11:00", tz="America/New_York")), "10:30-11:30")
        self.assertEqual(assign_phase9b_time_bucket(pd.Timestamp("2026-01-05 12:00", tz="America/New_York")), "11:30-13:30")
        self.assertEqual(assign_phase9b_time_bucket(pd.Timestamp("2026-01-05 14:00", tz="America/New_York")), "13:30-15:45")

    def test_trade_attribution_adds_mfe_mae_entry_timing_and_geometry_fields(self) -> None:
        config = Phase9BConfig(max_specs=4, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3)
        trades, *_ = compute_phase9b_trade_attribution(self._bars(), build_phase9b_specs(config), config)

        self.assertFalse(trades.empty)
        for column in ["mfe", "mae", "mfe_to_mae_ratio", "entry_slippage_from_signal_close", "r_multiple", "target_hit", "stop_hit", "time_bucket"]:
            self.assertIn(column, trades.columns)
        self.assertTrue((trades["entry_time"] > trades["signal_time"]).all())

    def test_group_summary_reports_required_failure_metrics(self) -> None:
        config = Phase9BConfig(max_specs=4, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3)
        trades, _, folds, _ = compute_phase9b_trade_attribution(self._bars(), build_phase9b_specs(config), config)
        summary = group_phase9b_summary(trades, folds, "side")

        self.assertFalse(summary.empty)
        for column in ["trades", "net_pnl", "stress_pnl", "profit_factor", "avg_mfe", "avg_mae", "target_hit_rate", "stop_hit_rate", "same_bar_ambiguity_rate", "walk_forward_stress_pnl"]:
            self.assertIn(column, summary.columns)

    def test_run_phase9b_diagnostic_outputs_recommendation_and_report(self) -> None:
        config = Phase9BConfig(max_specs=4, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3)
        result = run_phase9b_diagnostic(self._bars(), config)
        recommendation = make_phase9b_recommendation(result)
        report = render_phase9b_report(result, recommendation, Path("reports/phase9b_vcb_failure_attribution_report.md"))

        self.assertIn("next_action", recommendation)
        self.assertIn("# Phase 9B MNQ VCB Failure Attribution", report)
        self.assertIn("Diagnostic only", report)
        self.assertIn("No live trading", report)


if __name__ == "__main__":
    unittest.main()
