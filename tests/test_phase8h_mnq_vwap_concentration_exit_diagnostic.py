from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8h_mnq_vwap_concentration_exit_diagnostic import (
    Phase8HConfig,
    render_phase8h_report,
    replay_phase8h_trades,
    run_phase8h_exit_shape_grid,
    select_phase8h_inputs,
    summarize_phase8h_concentration,
    summarize_phase8h_overlap,
)


class Phase8HMNQVwapConcentrationExitDiagnosticTests(unittest.TestCase):
    def _sample_bars(self) -> pd.DataFrame:
        frames = []
        for day_index, session in enumerate(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"]):
            timestamps = pd.date_range(f"{session} 09:30", periods=90, freq="min", tz="America/New_York")
            close = []
            for index in range(90):
                cycle = index % 20
                value = 100.0 + day_index * 0.2 + cycle * 0.2
                if cycle >= 10:
                    value -= (cycle - 9) * 0.05
                close.append(value)
            frames.append(
                pd.DataFrame(
                    {
                        "timestamp": timestamps,
                        "symbol": "MNQ",
                        "open": close,
                        "high": [value + 0.25 for value in close],
                        "low": [value - 0.25 for value in close],
                        "close": close,
                        "volume": [1000] * 90,
                        "trading_session": [session] * 90,
                        "session_segment": ["RTH"] * 90,
                    }
                )
            )
        return pd.concat(frames, ignore_index=True)

    def _selected_inputs(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_keep",
                    "instrument": "MNQ",
                    "timeframe": 5,
                    "side": "long_only",
                    "family": "vwap_pullback_continuation",
                    "phase8e_label": "backtest_candidate",
                    "entry_delay": "next_5m_close",
                    "stop_model": "none",
                    "target_model": "horizon_close",
                    "time_stop": 15,
                }
            ]
        )

    def test_select_phase8h_inputs_keeps_only_positive_mnq_vwap_horizon_rows(self) -> None:
        event_results = pd.DataFrame(
            [
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_keep",
                    "instrument": "MNQ",
                    "timeframe": 5,
                    "side": "long_only",
                    "family": "vwap_pullback_continuation",
                    "phase8e_label": "backtest_candidate",
                    "phase8e_score": 61.0,
                },
                {
                    "hypothesis_id": "MGC_vwap_pullback_continuation_tf5_long_only_wrong_instrument",
                    "instrument": "MGC",
                    "timeframe": 5,
                    "side": "long_only",
                    "family": "vwap_pullback_continuation",
                    "phase8e_label": "backtest_candidate",
                    "phase8e_score": 90.0,
                },
                {
                    "hypothesis_id": "MNQ_opening_range_breakout_tf15_long_only_wrong_family",
                    "instrument": "MNQ",
                    "timeframe": 15,
                    "side": "long_only",
                    "family": "opening_range_breakout",
                    "phase8e_label": "backtest_candidate",
                    "phase8e_score": 80.0,
                },
                {
                    "hypothesis_id": "MNQ_vwap_reclaim_rejection_tf1_long_only_not_candidate",
                    "instrument": "MNQ",
                    "timeframe": 1,
                    "side": "long_only",
                    "family": "vwap_reclaim_rejection",
                    "phase8e_label": "needs_filter",
                    "phase8e_score": 70.0,
                },
            ]
        )
        phase8g_results = pd.DataFrame(
            [
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_keep",
                    "instrument": "MNQ",
                    "family": "vwap_pullback_continuation",
                    "entry_delay": "next_5m_close",
                    "stop_model": "none",
                    "target_model": "horizon_close",
                    "time_stop": 15,
                    "net_pnl": 500.0,
                    "slippage_4_ticks_net_pnl": 100.0,
                    "calibration_label": "concentrated",
                    "calibration_score": 12.0,
                },
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_keep",
                    "instrument": "MNQ",
                    "family": "vwap_pullback_continuation",
                    "entry_delay": "next_5m_close",
                    "stop_model": "fixed_ticks",
                    "target_model": "1R",
                    "time_stop": 30,
                    "net_pnl": 600.0,
                    "slippage_4_ticks_net_pnl": 200.0,
                    "calibration_label": "calibration_survivor",
                    "calibration_score": 99.0,
                },
                {
                    "hypothesis_id": "MGC_vwap_pullback_continuation_tf5_long_only_wrong_instrument",
                    "instrument": "MGC",
                    "family": "vwap_pullback_continuation",
                    "entry_delay": "next_5m_close",
                    "stop_model": "none",
                    "target_model": "horizon_close",
                    "time_stop": 15,
                    "net_pnl": 700.0,
                    "slippage_4_ticks_net_pnl": 300.0,
                    "calibration_label": "calibration_survivor",
                    "calibration_score": 90.0,
                },
                {
                    "hypothesis_id": "MNQ_opening_range_breakout_tf15_long_only_wrong_family",
                    "instrument": "MNQ",
                    "family": "opening_range_breakout",
                    "entry_delay": "next_5m_close",
                    "stop_model": "none",
                    "target_model": "horizon_close",
                    "time_stop": 15,
                    "net_pnl": 800.0,
                    "slippage_4_ticks_net_pnl": 400.0,
                    "calibration_label": "calibration_survivor",
                    "calibration_score": 80.0,
                },
                {
                    "hypothesis_id": "MNQ_vwap_reclaim_rejection_tf1_long_only_not_candidate",
                    "instrument": "MNQ",
                    "family": "vwap_reclaim_rejection",
                    "entry_delay": "next_5m_close",
                    "stop_model": "none",
                    "target_model": "horizon_close",
                    "time_stop": 15,
                    "net_pnl": -1.0,
                    "slippage_4_ticks_net_pnl": 10.0,
                    "calibration_label": "rejected_timing_cost",
                    "calibration_score": 70.0,
                },
            ]
        )

        selected = select_phase8h_inputs(event_results, phase8g_results, Phase8HConfig())

        self.assertEqual(selected["hypothesis_id"].tolist(), ["MNQ_vwap_pullback_continuation_tf5_long_only_keep"])
        self.assertEqual(selected.iloc[0]["entry_delay"], "next_5m_close")
        self.assertEqual(selected.iloc[0]["target_model"], "horizon_close")
        self.assertGreater(float(selected.iloc[0]["slippage_4_ticks_net_pnl"]), 0.0)

    def test_replay_phase8h_trades_returns_trade_level_cost_columns(self) -> None:
        trades = replay_phase8h_trades(self._selected_inputs(), {"MNQ": self._sample_bars()}, Phase8HConfig())

        self.assertFalse(trades.empty)
        for column in ["net_pnl", "stress_net_pnl", "trading_session", "minute_of_day", "rth_bucket", "weekday"]:
            self.assertIn(column, trades.columns)
        self.assertEqual(set(trades["hypothesis_id"]), {"MNQ_vwap_pullback_continuation_tf5_long_only_keep"})
        self.assertTrue((trades["exit_shape"] == "horizon_close_15m").all())

    def test_phase8h_labels_concentrated_when_best_day_exceeds_limit(self) -> None:
        trades = pd.DataFrame(
            [
                {
                    "hypothesis_id": "hyp1",
                    "instrument": "MNQ",
                    "family": "vwap_pullback_continuation",
                    "trading_session": "2026-01-02",
                    "entry_time": pd.Timestamp("2026-01-02 09:35", tz="America/New_York"),
                    "net_pnl": 80.0,
                    "stress_net_pnl": 70.0,
                    "rth_bucket": "09:30-10:00",
                    "weekday": "Friday",
                },
                {
                    "hypothesis_id": "hyp1",
                    "instrument": "MNQ",
                    "family": "vwap_pullback_continuation",
                    "trading_session": "2026-01-03",
                    "entry_time": pd.Timestamp("2026-01-03 10:35", tz="America/New_York"),
                    "net_pnl": 20.0,
                    "stress_net_pnl": 10.0,
                    "rth_bucket": "10:00-11:00",
                    "weekday": "Saturday",
                },
            ]
        )

        summary = summarize_phase8h_concentration(trades, Phase8HConfig(min_trades=1))
        row = summary[(summary["summary_scope"] == "hypothesis") & (summary["summary_key"] == "hyp1")].iloc[0]

        self.assertEqual(row["phase8h_label"], "rejected_concentration_artifact")
        self.assertGreater(float(row["best_day_concentration"]), 0.35)
        self.assertIn("one-day concentration", row["phase8h_notes"])

    def test_exit_shape_grid_compares_non_intrabar_exit_shapes(self) -> None:
        config = Phase8HConfig(min_trades=1)
        results = run_phase8h_exit_shape_grid(self._selected_inputs(), {"MNQ": self._sample_bars()}, config)

        self.assertEqual(
            set(results["exit_shape"]),
            {"horizon_close_10m", "horizon_close_15m", "horizon_close_20m", "trailing_time_stop", "session_bucket_flatten"},
        )
        self.assertIn("stress_net_pnl", results.columns)
        self.assertIn("phase8h_label", results.columns)

    def test_overlap_summary_detects_duplicate_event_timestamps(self) -> None:
        trades = pd.DataFrame(
            [
                {"hypothesis_id": "hyp1", "event_time": pd.Timestamp("2026-01-02 09:35", tz="America/New_York"), "net_pnl": 1.0},
                {"hypothesis_id": "hyp1", "event_time": pd.Timestamp("2026-01-02 09:36", tz="America/New_York"), "net_pnl": 2.0},
                {"hypothesis_id": "hyp2", "event_time": pd.Timestamp("2026-01-02 09:35", tz="America/New_York"), "net_pnl": 1.5},
                {"hypothesis_id": "hyp2", "event_time": pd.Timestamp("2026-01-02 09:37", tz="America/New_York"), "net_pnl": 3.0},
            ]
        )

        overlap = summarize_phase8h_overlap(trades)

        self.assertEqual(int(overlap.iloc[0]["overlap_event_count"]), 1)
        self.assertAlmostEqual(float(overlap.iloc[0]["event_jaccard_ratio"]), 1 / 3)
        self.assertEqual(overlap.iloc[0]["phase8h_overlap_label"], "distinct_signals")

    def test_render_phase8h_report_includes_guardrails_outputs_and_decision_rule(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "summary_scope": "overall",
                    "summary_key": "all",
                    "trade_count": 10,
                    "session_count": 4,
                    "active_session_pct": 1.0,
                    "net_pnl": 100.0,
                    "stress_net_pnl": 80.0,
                    "max_drawdown": -20.0,
                    "best_day": "2026-01-02",
                    "best_day_net_pnl": 80.0,
                    "best_day_concentration": 0.8,
                    "best_trade_concentration": 0.2,
                    "net_excluding_best_day": 20.0,
                    "stress_excluding_best_day": 10.0,
                    "phase8h_label": "rejected_concentration_artifact",
                    "phase8h_notes": "one-day concentration risk",
                }
            ]
        )
        exit_results = pd.DataFrame(
            [
                {
                    "hypothesis_id": "hyp1",
                    "exit_shape": "horizon_close_15m",
                    "trade_count": 10,
                    "net_pnl": 100.0,
                    "stress_net_pnl": 80.0,
                    "max_drawdown": -20.0,
                    "best_day_concentration": 0.8,
                    "phase8h_label": "rejected_concentration_artifact",
                    "phase8h_notes": "one-day concentration risk",
                }
            ]
        )
        report = render_phase8h_report(
            self._selected_inputs(),
            summary,
            exit_results,
            pd.DataFrame(),
            Phase8HConfig(),
            trade_log_path=Path("outputs/phase8h_mnq_vwap_trade_log.csv"),
            summary_path=Path("outputs/phase8h_mnq_vwap_concentration_summary.csv"),
            exit_shape_path=Path("outputs/phase8h_mnq_vwap_exit_shape_results.csv"),
            report_path=Path("reports/phase8h_mnq_vwap_concentration_exit_diagnostic_report.md"),
            run_artifact_dir=Path("artifacts/phase8h_mnq_vwap_concentration_exit_diagnostic/test-run"),
        )

        self.assertIn("# Phase 8H MNQ VWAP Concentration And Exit Diagnostic", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("outputs/phase8h_mnq_vwap_trade_log.csv", report)
        self.assertIn("Decision Rule", report)
        self.assertIn("rejected_concentration_artifact", report)


if __name__ == "__main__":
    unittest.main()
