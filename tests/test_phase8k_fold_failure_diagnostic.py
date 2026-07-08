from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8k_fold_failure_diagnostic import (
    Phase8KConfig,
    build_phase8k_candidate_actions,
    build_phase8k_next_step_queue,
    render_phase8k_report,
    summarize_phase8k_buckets,
    summarize_phase8k_sessions,
    tag_phase8k_trades_with_folds,
)


class Phase8KFoldFailureDiagnosticTests(unittest.TestCase):
    def _trades(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"entry_time": "2026-01-05 09:45:00-05:00", "exit_time": "2026-01-05 10:00:00-05:00", "trading_session": "2026-01-05", "rth_bucket": "09:30-10:00", "weekday": "Monday", "net_pnl": 100.0, "stress_net_pnl": 95.0},
                {"entry_time": "2026-01-06 10:15:00-05:00", "exit_time": "2026-01-06 10:30:00-05:00", "trading_session": "2026-01-06", "rth_bucket": "10:00-11:00", "weekday": "Tuesday", "net_pnl": -20.0, "stress_net_pnl": -25.0},
                {"entry_time": "2026-01-07 11:15:00-05:00", "exit_time": "2026-01-07 11:30:00-05:00", "trading_session": "2026-01-07", "rth_bucket": "11:00-12:00", "weekday": "Wednesday", "net_pnl": 40.0, "stress_net_pnl": 35.0},
                {"entry_time": "2026-01-08 09:35:00-05:00", "exit_time": "2026-01-08 09:50:00-05:00", "trading_session": "2026-01-08", "rth_bucket": "09:30-10:00", "weekday": "Thursday", "net_pnl": -200.0, "stress_net_pnl": -205.0},
                {"entry_time": "2026-01-09 12:15:00-05:00", "exit_time": "2026-01-09 12:30:00-05:00", "trading_session": "2026-01-09", "rth_bucket": "12:00-13:00", "weekday": "Friday", "net_pnl": 80.0, "stress_net_pnl": 75.0},
            ]
        )

    def _folds(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"candidate_id": "candidate", "fold": 1, "segment": "train", "segment_start": "2026-01-05", "segment_end": "2026-01-06", "segment_session_count": 2, "net_pnl": 80.0, "stress_net_pnl": 70.0, "trades": 2, "best_day_concentration": 1.25, "best_trade_concentration": 1.25},
                {"candidate_id": "candidate", "fold": 1, "segment": "validation", "segment_start": "2026-01-07", "segment_end": "2026-01-07", "segment_session_count": 1, "net_pnl": 40.0, "stress_net_pnl": 35.0, "trades": 1, "best_day_concentration": 1.0, "best_trade_concentration": 1.0},
                {"candidate_id": "candidate", "fold": 1, "segment": "test", "segment_start": "2026-01-08", "segment_end": "2026-01-08", "segment_session_count": 1, "net_pnl": -200.0, "stress_net_pnl": -205.0, "trades": 1, "best_day_concentration": 1.0, "best_trade_concentration": 1.0},
                {"candidate_id": "candidate", "fold": 2, "segment": "train", "segment_start": "2026-01-06", "segment_end": "2026-01-07", "segment_session_count": 2, "net_pnl": 20.0, "stress_net_pnl": 10.0, "trades": 2, "best_day_concentration": 2.0, "best_trade_concentration": 2.0},
                {"candidate_id": "candidate", "fold": 2, "segment": "validation", "segment_start": "2026-01-08", "segment_end": "2026-01-08", "segment_session_count": 1, "net_pnl": -200.0, "stress_net_pnl": -205.0, "trades": 1, "best_day_concentration": 1.0, "best_trade_concentration": 1.0},
                {"candidate_id": "candidate", "fold": 2, "segment": "test", "segment_start": "2026-01-09", "segment_end": "2026-01-09", "segment_session_count": 1, "net_pnl": 80.0, "stress_net_pnl": 75.0, "trades": 1, "best_day_concentration": 1.0, "best_trade_concentration": 1.0},
            ]
        )

    def test_tag_phase8k_trades_maps_rolling_fold_membership_and_failure_labels(self) -> None:
        tagged = tag_phase8k_trades_with_folds(self._trades(), self._folds(), Phase8KConfig())

        self.assertEqual(len(tagged), 8)
        jan8 = tagged[tagged["trading_session"].eq("2026-01-08")].sort_values(["fold", "segment"])
        self.assertEqual(jan8["segment"].tolist(), ["test", "validation"])
        self.assertEqual(jan8["fold_segment_label"].tolist(), ["phase8k_losing_test_fold", "phase8k_losing_validation_fold"])
        self.assertEqual(tagged["phase8k_step"].nunique(), 1)

    def test_session_diagnostics_identifies_losing_fold_worst_session(self) -> None:
        tagged = tag_phase8k_trades_with_folds(self._trades(), self._folds(), Phase8KConfig())
        sessions = summarize_phase8k_sessions(tagged, self._folds(), Phase8KConfig())

        worst = sessions[(sessions["fold"].eq(1)) & (sessions["segment"].eq("test"))].iloc[0]
        self.assertEqual(worst["trading_session"], "2026-01-08")
        self.assertEqual(float(worst["net_pnl"]), -200.0)
        self.assertEqual(worst["session_label"], "phase8k_losing_fold_worst_session")
        self.assertGreater(float(worst["loss_share_of_segment"]), 0.99)

    def test_bucket_diagnostics_are_no_lookahead_and_rank_negative_buckets(self) -> None:
        tagged = tag_phase8k_trades_with_folds(self._trades(), self._folds(), Phase8KConfig())
        buckets = summarize_phase8k_buckets(tagged, Phase8KConfig())

        axes = set(buckets["diagnostic_axis"])
        self.assertTrue({"rth_bucket", "weekday", "minute_bucket"}.issubset(axes))
        bad = buckets[(buckets["diagnostic_axis"].eq("rth_bucket")) & (buckets["bucket"].eq("09:30-10:00"))].iloc[0]
        self.assertEqual(bad["bucket_label"], "phase8k_negative_test_bucket")
        self.assertLess(float(bad["test_net_pnl"]), 0.0)
        self.assertIn("entry", bad["lookahead_guardrail"])

    def test_candidate_actions_and_next_step_queue_stay_diagnostic_only(self) -> None:
        tagged = tag_phase8k_trades_with_folds(self._trades(), self._folds(), Phase8KConfig())
        sessions = summarize_phase8k_sessions(tagged, self._folds(), Phase8KConfig())
        buckets = summarize_phase8k_buckets(tagged, Phase8KConfig())
        actions = build_phase8k_candidate_actions(sessions, buckets, Phase8KConfig())
        queue = build_phase8k_next_step_queue(actions, sessions, buckets, Phase8KConfig())

        self.assertGreaterEqual(len(actions), 3)
        self.assertEqual(actions.iloc[0]["phase8k_action_label"], "diagnostic_only_retest_required")
        self.assertTrue(actions["candidate_action_id"].astype(str).str.startswith("phase8k_").all())
        self.assertEqual(queue["step_number"].tolist(), [1, 2, 3, 4, 5])
        self.assertFalse(queue["promotion_allowed"].any())
        self.assertIn("Phase 8L", queue.iloc[1]["next_phase"])

    def test_render_phase8k_report_includes_five_steps_outputs_and_guardrails(self) -> None:
        tagged = tag_phase8k_trades_with_folds(self._trades(), self._folds(), Phase8KConfig())
        sessions = summarize_phase8k_sessions(tagged, self._folds(), Phase8KConfig())
        buckets = summarize_phase8k_buckets(tagged, Phase8KConfig())
        actions = build_phase8k_candidate_actions(sessions, buckets, Phase8KConfig())
        queue = build_phase8k_next_step_queue(actions, sessions, buckets, Phase8KConfig())

        report = render_phase8k_report(
            sessions,
            buckets,
            actions,
            queue,
            Phase8KConfig(),
            tagged_trades_path=Path("outputs/phase8k_tagged_trades.csv"),
            session_diagnostics_path=Path("outputs/phase8k_session_diagnostics.csv"),
            bucket_diagnostics_path=Path("outputs/phase8k_bucket_diagnostics.csv"),
            candidate_actions_path=Path("outputs/phase8k_candidate_actions.csv"),
            next_step_queue_path=Path("outputs/phase8k_next_step_queue.csv"),
            report_path=Path("reports/phase8k_fold_failure_diagnostic_report.md"),
            run_artifact_dir=Path("artifacts/phase8k_fold_failure_diagnostic/test-run"),
        )

        self.assertIn("# Phase 8K Fold Failure Diagnostic", report)
        self.assertIn("Next Five Steps", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("No paper-trading promotion", report)
        self.assertIn("outputs/phase8k_next_step_queue.csv", report)


if __name__ == "__main__":
    unittest.main()
