from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8i_no_lookahead_filter import (
    Phase8IConfig,
    Phase8IFilterSpec,
    apply_phase8i_filter,
    build_phase8i_filter_specs,
    evaluate_phase8i_filters,
    render_phase8i_report,
    select_phase8i_source_trades,
)


class Phase8INoLookaheadFilterTests(unittest.TestCase):
    def _duplicate_trades(self) -> pd.DataFrame:
        rows = []
        for hypothesis_id in ["left_dup", "right_dup"]:
            for session_index, session in enumerate(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]):
                entry = pd.Timestamp(f"{session} 09:45", tz="America/New_York")
                rows.append(
                    {
                        "hypothesis_id": hypothesis_id,
                        "instrument": "MNQ",
                        "family": "vwap_pullback_continuation",
                        "event_time": entry - pd.Timedelta(minutes=5),
                        "entry_time": entry,
                        "exit_time": entry + pd.Timedelta(minutes=15),
                        "trading_session": session,
                        "side": "long",
                        "net_pnl": 100.0 + session_index * 10.0,
                        "stress_net_pnl": 90.0 + session_index * 10.0,
                        "rth_bucket": "09:30-10:00",
                        "weekday": entry.day_name(),
                    }
                )
        return pd.DataFrame(rows)

    def test_select_phase8i_source_trades_deduplicates_overlap_pair(self) -> None:
        overlap = pd.DataFrame(
            [
                {
                    "left_hypothesis_id": "left_dup",
                    "right_hypothesis_id": "right_dup",
                    "overlap_event_count": 5,
                    "event_jaccard_ratio": 1.0,
                    "shared_pnl_correlation": 1.0,
                    "phase8h_overlap_label": "phase8h_duplicate_signal",
                }
            ]
        )

        selected = select_phase8i_source_trades(self._duplicate_trades(), overlap, Phase8IConfig())

        self.assertEqual(set(selected["hypothesis_id"]), {"left_dup"})
        self.assertEqual(len(selected), 5)
        self.assertTrue(selected["phase8i_source_note"].str.contains("de-duplicated").all())

    def test_apply_phase8i_filter_uses_only_pre_entry_time_metadata(self) -> None:
        trades = pd.DataFrame(
            [
                {"entry_time": pd.Timestamp("2026-01-02 09:45", tz="America/New_York"), "weekday": "Friday", "net_pnl": -999.0},
                {"entry_time": pd.Timestamp("2026-01-02 13:59", tz="America/New_York"), "weekday": "Friday", "net_pnl": 1.0},
                {"entry_time": pd.Timestamp("2026-01-02 14:00", tz="America/New_York"), "weekday": "Friday", "net_pnl": 9999.0},
            ]
        )
        spec = Phase8IFilterSpec("time_window:pre_14_00", "time_window", {"start": "09:30", "end": "14:00"}, "Before 14:00 ET")

        filtered = apply_phase8i_filter(trades, spec)

        self.assertEqual(len(filtered), 2)
        self.assertLess(filtered["entry_time"].max().hour * 60 + filtered["entry_time"].max().minute, 14 * 60)
        self.assertIn(-999.0, set(filtered["net_pnl"]))

    def test_apply_phase8i_filter_handles_mixed_dst_offsets_as_new_york_time(self) -> None:
        trades = pd.DataFrame(
            [
                {"entry_time": "2025-10-31 13:59:00-04:00", "weekday": "Friday", "net_pnl": 1.0},
                {"entry_time": "2025-11-03 14:00:00-05:00", "weekday": "Monday", "net_pnl": 2.0},
            ]
        )
        spec = Phase8IFilterSpec("time_window:pre_14_00", "time_window", {"start": "09:30", "end": "14:00"}, "Before 14:00 ET")

        filtered = apply_phase8i_filter(trades, spec)

        self.assertEqual(filtered["net_pnl"].tolist(), [1.0])

    def test_evaluate_phase8i_filters_requires_positive_validation_and_holdout(self) -> None:
        trades = self._duplicate_trades()[lambda frame: frame["hypothesis_id"].eq("left_dup")].copy()
        specs = [Phase8IFilterSpec("baseline_all", "all", {}, "Keep every de-duplicated trade")]

        results = evaluate_phase8i_filters(trades, specs, Phase8IConfig(min_trades=3, concentration_limit=0.75, drawdown_limit=-1000.0))
        row = results.iloc[0]

        self.assertEqual(row["phase8i_label"], "phase8i_filter_candidate")
        self.assertGreater(float(row["discovery_pnl"]), 0.0)
        self.assertGreater(float(row["validation_pnl"]), 0.0)
        self.assertGreater(float(row["holdout_pnl"]), 0.0)
        self.assertEqual(int(row["kept_trade_count"]), 5)

    def test_build_phase8i_filter_specs_includes_static_pre_14_filter(self) -> None:
        specs = build_phase8i_filter_specs()

        self.assertIn("time_window:pre_14_00", {spec.filter_id for spec in specs})
        self.assertTrue(all(spec.filter_family != "pnl_derived" for spec in specs))

    def test_render_phase8i_report_includes_guardrails_outputs_and_decision(self) -> None:
        results = pd.DataFrame(
            [
                {
                    "phase8i_rank": 1,
                    "filter_id": "time_window:pre_14_00",
                    "phase8i_label": "phase8i_filter_candidate",
                    "phase8i_score": 10.0,
                    "kept_trade_count": 5,
                    "active_session_pct": 1.0,
                    "net_pnl": 500.0,
                    "stress_net_pnl": 450.0,
                    "discovery_pnl": 300.0,
                    "validation_pnl": 100.0,
                    "holdout_pnl": 100.0,
                    "max_drawdown": 0.0,
                    "best_day_concentration": 0.3,
                    "best_trade_concentration": 0.24,
                    "phase8i_notes": "survives split-aware no-lookahead filter diagnostic",
                }
            ]
        )

        report = render_phase8i_report(
            results,
            Phase8IConfig(),
            source_trade_count=5,
            deduped_trade_count=5,
            results_path=Path("outputs/phase8i_no_lookahead_filter_results.csv"),
            report_path=Path("reports/phase8i_no_lookahead_filter_report.md"),
            run_artifact_dir=Path("artifacts/phase8i_no_lookahead_filter/test-run"),
        )

        self.assertIn("# Phase 8I No-Lookahead Time/Session Filter", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("outputs/phase8i_no_lookahead_filter_results.csv", report)
        self.assertIn("phase8i_filter_candidate", report)


if __name__ == "__main__":
    unittest.main()
