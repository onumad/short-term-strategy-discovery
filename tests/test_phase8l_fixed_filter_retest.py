from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8l_fixed_filter_retest import (
    Phase8LConfig,
    apply_phase8l_filter,
    build_phase8l_filter_specs,
    evaluate_phase8l_filters,
    render_phase8l_report,
)


class Phase8LFixedFilterRetestTests(unittest.TestCase):
    def _actions(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "phase8k_action_rank": 1,
                    "candidate_action_id": "phase8k_retest_exclude_weekday_wednesday",
                    "action_type": "fixed_filter_retest",
                    "action_rule": "exclude weekday=Wednesday",
                    "source_axis": "weekday",
                    "source_bucket": "Wednesday",
                    "evidence": "test_pnl=-100.00; validation_pnl=-50.00; test_trades=2",
                },
                {
                    "phase8k_action_rank": 2,
                    "candidate_action_id": "phase8k_retest_exclude_minute_bucket_10_00_10_30",
                    "action_type": "fixed_filter_retest",
                    "action_rule": "exclude minute_bucket=10:00-10:30",
                    "source_axis": "minute_bucket",
                    "source_bucket": "10:00-10:30",
                    "evidence": "test_pnl=-80.00; validation_pnl=-20.00; test_trades=1",
                },
                {
                    "phase8k_action_rank": 3,
                    "candidate_action_id": "phase8k_review_session_2026_05_18_fold_2_test",
                    "action_type": "failure_attribution",
                    "action_rule": "review session 2026-05-18 in fold 2 test",
                    "source_axis": "trading_session",
                    "source_bucket": "2026-05-18",
                    "evidence": "session_pnl=-1754.14",
                },
            ]
        )

    def _trades(self) -> pd.DataFrame:
        rows = []
        sessions = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"])
        pnls = [100.0, 80.0, -200.0, 70.0, 90.0, 60.0]
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Monday"]
        minutes = ["09:45", "10:15", "10:15", "11:15", "12:45", "13:15"]
        buckets = ["09:30-10:00", "10:00-11:00", "10:00-11:00", "11:00-12:00", "12:00-14:00", "12:00-14:00"]
        for session, pnl, weekday, minute, bucket in zip(sessions, pnls, weekdays, minutes, buckets):
            entry = pd.Timestamp(f"{session.date()} {minute}", tz="America/New_York")
            rows.append(
                {
                    "phase8j_candidate_id": "MNQ_vwap_pullback_continuation_tf5_test",
                    "instrument": "MNQ",
                    "family": "vwap_pullback_continuation",
                    "timeframe": 5,
                    "entry_time": entry,
                    "exit_time": entry + pd.Timedelta(minutes=15),
                    "trading_session": str(session.date()),
                    "weekday": weekday,
                    "rth_bucket": bucket,
                    "net_pnl": pnl,
                    "stress_net_pnl": pnl - 1.0,
                }
            )
        return pd.DataFrame(rows)

    def test_build_phase8l_filter_specs_keeps_fixed_filter_actions_and_baseline_only(self) -> None:
        specs = build_phase8l_filter_specs(self._actions(), Phase8LConfig(max_action_specs=4))

        self.assertEqual([spec.filter_id for spec in specs], ["baseline_phase8j", "exclude:weekday:Wednesday", "exclude:minute_bucket:10:00-10:30"])
        self.assertEqual(specs[1].source_action_id, "phase8k_retest_exclude_weekday_wednesday")
        self.assertEqual(specs[1].axis, "weekday")
        self.assertFalse(specs[1].promotion_allowed)

    def test_apply_phase8l_filter_excludes_weekday_and_minute_bucket_without_future_data(self) -> None:
        specs = build_phase8l_filter_specs(self._actions(), Phase8LConfig(max_action_specs=4))
        weekday_spec = specs[1]
        minute_spec = specs[2]

        weekday_filtered = apply_phase8l_filter(self._trades(), weekday_spec)
        minute_filtered = apply_phase8l_filter(self._trades(), minute_spec)

        self.assertNotIn("Wednesday", set(weekday_filtered["weekday"]))
        self.assertEqual(len(weekday_filtered), 5)
        self.assertEqual(weekday_filtered["phase8l_filter_id"].nunique(), 1)
        self.assertNotIn("10:00-10:30", set(minute_filtered["minute_bucket"]))
        self.assertEqual(len(minute_filtered), 4)

    def test_evaluate_phase8l_filters_requires_fixed_splits_walk_forward_and_no_promotion(self) -> None:
        config = Phase8LConfig(train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3, min_trades=3, concentration_limit=1.0, trade_concentration_limit=1.0, drawdown_limit=-500.0)
        specs = build_phase8l_filter_specs(self._actions(), config)

        results, filtered_logs = evaluate_phase8l_filters(self._trades(), specs, config)

        self.assertEqual(len(results), 3)
        top = results.iloc[0]
        self.assertEqual(top["filter_id"], "exclude:weekday:Wednesday")
        self.assertEqual(top["phase8l_label"], "phase8l_fixed_filter_candidate")
        self.assertFalse(bool(top["promotion_allowed"]))
        self.assertEqual(int(top["walk_forward_test_positive_folds"]), 3)
        self.assertGreater(float(top["validation_pnl"]), 0.0)
        self.assertGreater(float(top["holdout_pnl"]), 0.0)
        self.assertEqual(filtered_logs["filter_id"].nunique(), 3)
        self.assertIn("phase8l_filter_rank", results.columns)

    def test_render_phase8l_report_includes_guardrails_outputs_and_decision(self) -> None:
        config = Phase8LConfig(train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3, min_trades=3, concentration_limit=1.0, trade_concentration_limit=1.0)
        specs = build_phase8l_filter_specs(self._actions(), config)
        results, _ = evaluate_phase8l_filters(self._trades(), specs, config)

        report = render_phase8l_report(
            results,
            config,
            results_path=Path("outputs/phase8l_filter_retest_results.csv"),
            specs_path=Path("outputs/phase8l_filter_retest_specs.json"),
            filtered_trade_logs_path=Path("outputs/phase8l_filtered_trade_logs.csv"),
            report_path=Path("reports/phase8l_fixed_filter_retest_report.md"),
            run_artifact_dir=Path("artifacts/phase8l_fixed_filter_retest/test-run"),
        )

        self.assertIn("# Phase 8L Fixed No-Lookahead Filter Retest", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("No paper-trading promotion", report)
        self.assertIn("phase8l_fixed_filter_candidate", report)
        self.assertIn("outputs/phase8l_filter_retest_results.csv", report)


if __name__ == "__main__":
    unittest.main()
