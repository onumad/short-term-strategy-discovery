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

from short_term_edge.phase12a_opening_drive_first_pullback import (  # noqa: E402
    Phase12AConfig,
    Phase12ASpec,
    build_phase12a_feature_bars,
    build_phase12a_specs,
    compute_opening_drive_levels,
    generate_phase12a_signals,
    render_phase12a_report,
    run_phase12a_retest,
    serialize_phase12a_specs,
    simulate_phase12a_trades,
)


class Phase12AOpeningDrivePullbackTests(unittest.TestCase):
    def _bars(self, session: str = "2026-01-06", rows: list[dict[str, float]] | None = None) -> pd.DataFrame:
        if rows is None:
            rows = self._long_rows()
        out = []
        for row in rows:
            out.append(
                {
                    "timestamp": pd.Timestamp(f"{session} {row['time']}", tz="America/New_York"),
                    "symbol": "MNQ",
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": 100,
                    "trading_session": session,
                    "session_segment": "RTH",
                }
            )
        return pd.DataFrame(out)

    def _long_rows(self) -> list[dict[str, float]]:
        return [
            {"time": "09:30", "open": 100.0, "high": 104.0, "low": 100.0, "close": 103.0},
            {"time": "09:35", "open": 103.0, "high": 107.0, "low": 102.0, "close": 106.0},
            {"time": "09:40", "open": 106.0, "high": 110.0, "low": 104.0, "close": 108.0},
            {"time": "09:45", "open": 108.0, "high": 114.0, "low": 107.0, "close": 112.0},
            {"time": "09:50", "open": 110.0, "high": 113.0, "low": 109.5, "close": 111.0},
            {"time": "09:55", "open": 112.0, "high": 116.0, "low": 109.0, "close": 113.0},
            {"time": "10:00", "open": 113.0, "high": 115.0, "low": 109.5, "close": 112.0},
            {"time": "10:05", "open": 112.0, "high": 115.0, "low": 111.0, "close": 114.0},
            {"time": "13:30", "open": 114.0, "high": 116.0, "low": 113.0, "close": 115.0},
            {"time": "15:45", "open": 115.0, "high": 116.0, "low": 114.0, "close": 115.0},
        ]

    def _short_rows(self) -> list[dict[str, float]]:
        return [
            {"time": "09:30", "open": 110.0, "high": 110.0, "low": 106.0, "close": 107.0},
            {"time": "09:35", "open": 107.0, "high": 108.0, "low": 103.0, "close": 104.0},
            {"time": "09:40", "open": 104.0, "high": 106.0, "low": 100.0, "close": 102.0},
            {"time": "09:45", "open": 102.0, "high": 103.0, "low": 96.0, "close": 98.0},
            {"time": "09:50", "open": 100.0, "high": 100.5, "low": 97.0, "close": 99.0},
            {"time": "09:55", "open": 98.0, "high": 101.0, "low": 94.0, "close": 97.0},
            {"time": "10:00", "open": 97.0, "high": 100.5, "low": 95.0, "close": 98.0},
            {"time": "10:05", "open": 98.0, "high": 99.0, "low": 94.0, "close": 96.0},
        ]

    def _spec(self, branch: str = "long_first_pullback", od_window: str = "OD15", anchor: str = "drive_boundary_retest", confirmation: str = "resume_close_fill_next_open", exit_variant: str = "structure_target_time_exit") -> Phase12ASpec:
        return next(
            s
            for s in build_phase12a_specs()
            if s.branch == branch
            and s.od_window == od_window
            and s.pullback_anchor == anchor
            and s.confirmation_model == confirmation
            and s.exit_variant == exit_variant
        )

    def test_matrix_builds_exact_48_specs(self) -> None:
        specs = build_phase12a_specs(Phase12AConfig(max_specs=48))
        self.assertEqual(len(specs), 48)
        self.assertEqual({s.branch for s in specs}, {"long_first_pullback", "short_first_pullback"})
        self.assertEqual({s.od_window for s in specs}, {"OD15", "OD30", "OD60"})
        self.assertEqual({s.pullback_anchor for s in specs}, {"drive_boundary_retest", "ema20_retest"})
        self.assertEqual({s.confirmation_model for s in specs}, {"resume_close_fill_next_open", "two_bar_resume_fill_next_open"})
        self.assertEqual({s.exit_variant for s in specs}, {"hard_stop_time_exit", "structure_target_time_exit"})

    def test_opening_drive_levels_use_window_bars_and_freeze(self) -> None:
        bars = self._bars()
        od15 = compute_opening_drive_levels(bars, "OD15").iloc[0]
        self.assertEqual(float(od15["opening_drive_open"]), 100.0)
        self.assertEqual(float(od15["opening_drive_high"]), 110.0)
        self.assertEqual(float(od15["opening_drive_low"]), 100.0)
        self.assertEqual(float(od15["opening_drive_midpoint"]), 105.0)
        self.assertEqual(float(od15["opening_drive_width_points"]), 10.0)
        self.assertEqual(float(od15["opening_drive_close"]), 108.0)
        self.assertAlmostEqual(float(od15["opening_drive_close_position"]), 0.8)
        self.assertLess(float(od15["opening_drive_high"]), float(bars["high"].max()))
        od30 = compute_opening_drive_levels(bars, "OD30").iloc[0]
        self.assertEqual(float(od30["opening_drive_high"]), 116.0)
        od60 = compute_opening_drive_levels(bars, "OD60").iloc[0]
        self.assertEqual(float(od60["opening_drive_high"]), 116.0)

    def test_trend_qualification_top_and_bottom_30_pct(self) -> None:
        long_spec = self._spec()
        self.assertTrue(generate_phase12a_signals(build_phase12a_feature_bars(self._bars(), long_spec), long_spec))
        weak_long = self._long_rows()
        weak_long[2] = {"time": "09:40", "open": 106.0, "high": 110.0, "low": 104.0, "close": 106.0}
        self.assertFalse(generate_phase12a_signals(build_phase12a_feature_bars(self._bars(rows=weak_long), long_spec), long_spec))
        short_spec = self._spec("short_first_pullback")
        self.assertTrue(generate_phase12a_signals(build_phase12a_feature_bars(self._bars(rows=self._short_rows()), short_spec), short_spec))
        weak_short = self._short_rows()
        weak_short[2] = {"time": "09:40", "open": 104.0, "high": 106.0, "low": 100.0, "close": 104.0}
        self.assertFalse(generate_phase12a_signals(build_phase12a_feature_bars(self._bars(rows=weak_short), short_spec), short_spec))

    def test_continuation_extension_required_before_pullback_long_and_short(self) -> None:
        long_spec = self._spec()
        no_long_extension = self._long_rows()
        no_long_extension[3] = {"time": "09:45", "open": 108.0, "high": 110.0, "low": 107.0, "close": 109.5}
        no_long_extension[4] = {"time": "09:50", "open": 109.0, "high": 110.0, "low": 109.0, "close": 109.5}
        no_long_extension[5] = {"time": "09:55", "open": 109.5, "high": 110.0, "low": 109.0, "close": 109.5}
        self.assertFalse(generate_phase12a_signals(build_phase12a_feature_bars(self._bars(rows=no_long_extension), long_spec), long_spec))
        short_spec = self._spec("short_first_pullback")
        no_short_extension = self._short_rows()
        no_short_extension[3] = {"time": "09:45", "open": 102.0, "high": 103.0, "low": 100.0, "close": 100.5}
        no_short_extension[4] = {"time": "09:50", "open": 100.5, "high": 101.0, "low": 100.0, "close": 100.5}
        no_short_extension[5] = {"time": "09:55", "open": 100.5, "high": 101.0, "low": 100.0, "close": 100.5}
        self.assertFalse(generate_phase12a_signals(build_phase12a_feature_bars(self._bars(rows=no_short_extension), short_spec), short_spec))

    def test_drive_boundary_retest_logic_long_and_short(self) -> None:
        long_spec = self._spec(anchor="drive_boundary_retest")
        long_signal = generate_phase12a_signals(build_phase12a_feature_bars(self._bars(), long_spec), long_spec)[0]
        self.assertLessEqual(float(long_signal["pullback_low"]), float(long_signal["opening_drive_high"]) + 0.25)
        self.assertGreater(float(long_signal["signal_close"]), float(long_signal["opening_drive_high"]))
        short_spec = self._spec("short_first_pullback", anchor="drive_boundary_retest")
        short_signal = generate_phase12a_signals(build_phase12a_feature_bars(self._bars(rows=self._short_rows()), short_spec), short_spec)[0]
        self.assertGreaterEqual(float(short_signal["pullback_high"]), float(short_signal["opening_drive_low"]) - 0.25)
        self.assertLess(float(short_signal["signal_close"]), float(short_signal["opening_drive_low"]))

    def test_ema20_retest_logic_long_and_short_without_overnight_fields(self) -> None:
        long_spec = self._spec(anchor="ema20_retest")
        long_features = build_phase12a_feature_bars(self._bars(), long_spec)
        long_features.loc[long_features["timestamp"].dt.strftime("%H:%M").eq("09:50"), "ema20"] = 110.5
        long_signal = generate_phase12a_signals(long_features, long_spec)[0]
        self.assertLessEqual(float(long_signal["pullback_low"]), float(long_signal["ema20"]))
        self.assertGreater(float(long_signal["signal_close"]), float(long_signal["ema20"]))
        self.assertGreater(float(long_signal["signal_close"]), float(long_signal["opening_drive_midpoint"]))
        short_spec = self._spec("short_first_pullback", anchor="ema20_retest")
        short_features = build_phase12a_feature_bars(self._bars(rows=self._short_rows()), short_spec)
        short_features.loc[short_features["timestamp"].dt.strftime("%H:%M").eq("09:50"), "ema20"] = 99.5
        short_signal = generate_phase12a_signals(short_features, short_spec)[0]
        self.assertGreaterEqual(float(short_signal["pullback_high"]), float(short_signal["ema20"]))
        self.assertLess(float(short_signal["signal_close"]), float(short_signal["ema20"]))
        self.assertLess(float(short_signal["signal_close"]), float(short_signal["opening_drive_midpoint"]))
        forbidden = [c for c in long_features.columns if c.startswith("overnight") or c in {"gap_bucket", "gap_filter"}]
        self.assertEqual(forbidden, [])

    def test_next_open_semantics_and_two_bar_confirmation(self) -> None:
        resume = self._spec(confirmation="resume_close_fill_next_open")
        resume_signal = generate_phase12a_signals(build_phase12a_feature_bars(self._bars(), resume), resume)[0]
        self.assertEqual(pd.Timestamp(resume_signal["signal_time"]).strftime("%H:%M"), "09:50")
        self.assertEqual(pd.Timestamp(resume_signal["entry_time"]).strftime("%H:%M"), "09:55")
        self.assertGreater(pd.Timestamp(resume_signal["entry_time"]), pd.Timestamp(resume_signal["signal_time"]))
        two_bar = self._spec(confirmation="two_bar_resume_fill_next_open")
        two_bar_signal = generate_phase12a_signals(build_phase12a_feature_bars(self._bars(), two_bar), two_bar)[0]
        self.assertEqual(pd.Timestamp(two_bar_signal["confirmation_time"]).strftime("%H:%M"), "09:55")
        self.assertEqual(pd.Timestamp(two_bar_signal["entry_time"]).strftime("%H:%M"), "10:00")

    def test_first_pullback_only_and_entry_bounds(self) -> None:
        spec = self._spec()
        signals = generate_phase12a_signals(build_phase12a_feature_bars(self._bars(), spec), spec)
        self.assertEqual(len(signals), 1)
        self.assertEqual(int(signals[0]["first_pullback_only"]), 1)
        self.assertGreaterEqual(int(signals[0]["skipped_non_first_pullbacks"]), 1)
        for od_window, minimum in [("OD15", "09:45"), ("OD30", "10:00"), ("OD60", "10:30")]:
            s = self._spec(od_window=od_window)
            for sig in generate_phase12a_signals(build_phase12a_feature_bars(self._bars(), s), s):
                hhmm = pd.Timestamp(sig["entry_time"]).strftime("%H:%M")
                self.assertGreaterEqual(hhmm, minimum)
                self.assertGreaterEqual(hhmm, "09:45")
                self.assertLess(hhmm, "13:30")

    def test_stop_cap_invalid_risk_and_same_bar_ambiguity_long_and_short(self) -> None:
        long_spec = self._spec(exit_variant="structure_target_time_exit")
        long_features = build_phase12a_feature_bars(self._bars(), long_spec)
        long_signal = generate_phase12a_signals(long_features, long_spec)[0]
        long_signal["atr"] = 2.0
        long_trades, long_invalid = simulate_phase12a_trades(long_features, [long_signal], long_spec)
        self.assertEqual(long_invalid, 0)
        lt = long_trades.iloc[0]
        self.assertEqual(float(lt["structural_stop"]), 109.25)
        self.assertEqual(float(lt["atr_cap_stop"]), 109.5)
        self.assertEqual(float(lt["actual_stop"]), 109.5)
        self.assertEqual(str(lt["exit_reason"]), "stop_same_bar_conservative")
        self.assertEqual(int(lt["same_bar_ambiguity"]), 1)
        bad = dict(long_signal)
        bad["pullback_low"] = 114.0
        bad_trades, bad_invalid = simulate_phase12a_trades(long_features, [bad], long_spec)
        self.assertTrue(bad_trades.empty)
        self.assertEqual(bad_invalid, 1)

        short_spec = self._spec("short_first_pullback", exit_variant="structure_target_time_exit")
        short_features = build_phase12a_feature_bars(self._bars(rows=self._short_rows()), short_spec)
        short_signal = generate_phase12a_signals(short_features, short_spec)[0]
        short_signal["atr"] = 2.0
        short_trades, _ = simulate_phase12a_trades(short_features, [short_signal], short_spec)
        st = short_trades.iloc[0]
        self.assertEqual(float(st["structural_stop"]), 100.75)
        self.assertEqual(float(st["atr_cap_stop"]), 100.5)
        self.assertEqual(float(st["actual_stop"]), 100.5)

    def test_partial_session_excluded_and_candidate_diagnostics_present(self) -> None:
        bars = pd.concat([self._bars(session="2026-07-03"), self._bars(session="2026-01-06")], ignore_index=True)
        result = run_phase12a_retest(bars, Phase12AConfig(max_specs=4, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        if not result["trade_logs"].empty:
            self.assertNotIn("2026-07-03", set(result["trade_logs"]["trading_session"].astype(str)))
        candidates = result["candidate_results"]
        self.assertEqual(len(candidates), 4)
        for col in [
            "gross_pnl",
            "fees_only_pnl",
            "normal_slippage_pnl",
            "net_pnl",
            "stress_pnl",
            "validation_pnl",
            "holdout_pnl",
            "walk_forward_test_pnl",
            "walk_forward_stress_pnl",
            "positive_wf_test_folds_pct",
            "worst_wf_test_fold",
            "invalid_risk_skipped_count",
            "first_pullback_only_count",
            "skipped_non_first_pullbacks",
        ]:
            self.assertIn(col, candidates.columns)

    def test_cost_waterfall_specs_report_and_totals(self) -> None:
        result = run_phase12a_retest(self._bars(), Phase12AConfig(max_specs=4, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        if not result["trade_logs"].empty:
            self.assertEqual(round(float(result["trade_logs"].iloc[0]["normal_slippage_pnl"]), 2), round(float(result["trade_logs"].iloc[0]["net_pnl"]), 2))
        payload = json.loads(serialize_phase12a_specs(build_phase12a_specs(Phase12AConfig(max_specs=2))))
        self.assertEqual(payload[0]["instrument"], "MNQ")
        self.assertEqual(payload[0]["candidate_id"], build_phase12a_specs(Phase12AConfig(max_specs=1))[0].candidate_id)
        report = render_phase12a_report(result, {"next_action": "unit", "rationale": "test"}, Path("reports/phase12a_opening_drive_first_pullback_report.md"))
        self.assertIn(f"Specs evaluated: `{len(result['candidate_results'])}`", report)
        self.assertIn("Research/simulation only. No live trading", report)
        self.assertIn("phase12a_candidate_results.csv", report)


if __name__ == "__main__":
    unittest.main()
