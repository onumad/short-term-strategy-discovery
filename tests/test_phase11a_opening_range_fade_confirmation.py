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

from short_term_edge.phase11a_opening_range_fade_confirmation import (  # noqa: E402
    Phase11AConfig,
    Phase11ASpec,
    build_phase11a_feature_bars,
    build_phase11a_specs,
    compute_opening_range_levels,
    generate_phase11a_signals,
    render_phase11a_report,
    run_phase11a_retest,
    serialize_phase11a_specs,
    simulate_phase11a_trades,
)


class Phase11AOpeningRangeFadeTests(unittest.TestCase):
    def _bars(self, session: str = "2026-01-06", rows: list[dict[str, float]] | None = None) -> pd.DataFrame:
        if rows is None:
            rows = [
                {"time": "09:30", "open": 95.0, "high": 100.0, "low": 90.0, "close": 95.0},
                {"time": "09:35", "open": 95.0, "high": 102.0, "low": 94.0, "close": 99.0},
                {"time": "09:40", "open": 98.0, "high": 99.0, "low": 96.0, "close": 98.0},
                {"time": "09:45", "open": 97.0, "high": 99.0, "low": 95.0, "close": 96.0},
                {"time": "09:50", "open": 96.0, "high": 999.0, "low": 0.0, "close": 96.0},
                {"time": "10:30", "open": 96.0, "high": 101.0, "low": 95.0, "close": 99.0},
                {"time": "10:35", "open": 98.0, "high": 99.0, "low": 94.0, "close": 96.0},
                {"time": "13:25", "open": 96.0, "high": 103.0, "low": 95.0, "close": 99.0},
                {"time": "13:30", "open": 98.0, "high": 99.0, "low": 96.0, "close": 97.0},
                {"time": "15:45", "open": 97.0, "high": 98.0, "low": 96.0, "close": 97.0},
            ]
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

    def _spec(self, branch: str = "short_high_fade", or_window: str = "OR5", entry_window: str = "opening_response", confirmation: str = "close_back_inside_fill_next_open", exit_variant: str = "midpoint_target_time_exit") -> Phase11ASpec:
        return next(
            s
            for s in build_phase11a_specs()
            if s.branch == branch
            and s.or_window == or_window
            and s.entry_window == entry_window
            and s.confirmation_model == confirmation
            and s.exit_variant == exit_variant
        )

    def test_matrix_builds_exact_48_specs(self) -> None:
        specs = build_phase11a_specs(Phase11AConfig(max_specs=48))
        self.assertEqual(len(specs), 48)
        self.assertEqual({s.branch for s in specs}, {"short_high_fade", "long_low_fade"})
        self.assertEqual({s.or_window for s in specs}, {"OR5", "OR15", "OR30"})
        self.assertEqual({s.confirmation_model for s in specs}, {"close_back_inside_fill_next_open", "two_bar_inside_fill_next_open"})

    def test_opening_range_levels_use_only_rth_window_and_freeze(self) -> None:
        bars = self._bars()
        or5 = compute_opening_range_levels(bars, "OR5").iloc[0]
        self.assertEqual(float(or5["opening_range_high"]), 100.0)
        self.assertEqual(float(or5["opening_range_low"]), 90.0)
        self.assertEqual(float(or5["opening_range_midpoint"]), 95.0)
        self.assertEqual(float(or5["opening_range_width_points"]), 10.0)
        # Later post-OR extreme bars must not modify frozen OR5 levels.
        self.assertLess(float(or5["opening_range_high"]), float(bars["high"].max()))
        self.assertGreater(float(or5["opening_range_low"]), float(bars["low"].min()))
        or15 = compute_opening_range_levels(bars, "OR15").iloc[0]
        self.assertEqual(float(or15["opening_range_high"]), 102.0)
        self.assertEqual(float(or15["opening_range_low"]), 90.0)

    def test_short_high_fade_requires_breach_and_close_back_inside_next_open_entry(self) -> None:
        spec = self._spec("short_high_fade", confirmation="close_back_inside_fill_next_open")
        signals = generate_phase11a_signals(build_phase11a_feature_bars(self._bars(), spec), spec)
        first = signals[0]
        self.assertGreater(float(first["sweep_extreme"]), float(first["opening_range_high"]))
        self.assertLess(float(first["signal_close"]), float(first["opening_range_high"]))
        self.assertGreater(pd.Timestamp(first["entry_time"]), pd.Timestamp(first["signal_time"]))
        self.assertEqual(pd.Timestamp(first["entry_time"]).strftime("%H:%M"), "09:40")

    def test_long_low_fade_requires_breach_and_close_back_inside(self) -> None:
        rows = [
            {"time": "09:30", "open": 95.0, "high": 100.0, "low": 90.0, "close": 95.0},
            {"time": "09:35", "open": 95.0, "high": 96.0, "low": 88.0, "close": 91.0},
            {"time": "09:40", "open": 92.0, "high": 95.0, "low": 91.0, "close": 94.0},
            {"time": "09:45", "open": 94.0, "high": 96.0, "low": 93.0, "close": 95.0},
        ]
        spec = self._spec("long_low_fade")
        signals = generate_phase11a_signals(build_phase11a_feature_bars(self._bars(rows=rows), spec), spec)
        self.assertTrue(signals)
        self.assertLess(float(signals[0]["sweep_extreme"]), float(signals[0]["opening_range_low"]))
        self.assertGreater(float(signals[0]["signal_close"]), float(signals[0]["opening_range_low"]))

    def test_two_bar_inside_waits_for_second_inside_close_and_following_open(self) -> None:
        spec = self._spec("short_high_fade", confirmation="two_bar_inside_fill_next_open")
        signals = generate_phase11a_signals(build_phase11a_feature_bars(self._bars(), spec), spec)
        self.assertTrue(signals)
        self.assertEqual(pd.Timestamp(signals[0]["confirmation_time"]).strftime("%H:%M"), "09:40")
        self.assertEqual(pd.Timestamp(signals[0]["entry_time"]).strftime("%H:%M"), "09:45")

    def test_entries_respect_or_completion_minimum_and_midday_window_bounds(self) -> None:
        for or_window, min_time in [("OR5", "09:35"), ("OR15", "09:45"), ("OR30", "10:00")]:
            spec = self._spec("short_high_fade", or_window=or_window)
            signals = generate_phase11a_signals(build_phase11a_feature_bars(self._bars(), spec), spec)
            for sig in signals:
                self.assertGreaterEqual(pd.Timestamp(sig["entry_time"]).strftime("%H:%M"), min_time)
                self.assertGreaterEqual(pd.Timestamp(sig["entry_time"]).strftime("%H:%M"), "09:35")
                self.assertLess(pd.Timestamp(sig["entry_time"]).strftime("%H:%M"), "13:30")
        midday = self._spec("short_high_fade", entry_window="midday_response")
        midday_signals = generate_phase11a_signals(build_phase11a_feature_bars(self._bars(), midday), midday)
        self.assertTrue(midday_signals)
        self.assertTrue(all("10:30" <= pd.Timestamp(s["entry_time"]).strftime("%H:%M") < "13:30" for s in midday_signals))

    def test_stop_cap_logic_invalid_risk_and_same_bar_ambiguity(self) -> None:
        day = self._bars(
            rows=[
                {"time": "09:30", "open": 95.0, "high": 100.0, "low": 90.0, "close": 95.0},
                {"time": "09:35", "open": 99.0, "high": 102.0, "low": 94.0, "close": 99.0},
                {"time": "09:40", "open": 99.0, "high": 102.0, "low": 94.0, "close": 98.0},
                {"time": "09:45", "open": 98.0, "high": 99.0, "low": 96.0, "close": 97.0},
            ]
        )
        spec = self._spec("short_high_fade")
        features = build_phase11a_feature_bars(day, spec)
        signal = generate_phase11a_signals(features, spec)[0]
        signal["atr"] = 2.0
        trades, invalid = simulate_phase11a_trades(features, [signal], spec)
        self.assertEqual(invalid, 0)
        trade = trades.iloc[0]
        self.assertEqual(float(trade["structural_stop"]), 102.25)
        self.assertEqual(float(trade["atr_cap_stop"]), 101.5)
        self.assertEqual(float(trade["actual_stop"]), 101.5)
        self.assertEqual(str(trade["exit_reason"]), "stop_same_bar_conservative")
        self.assertEqual(int(trade["same_bar_ambiguity"]), 1)

        bad_signal = dict(signal)
        bad_signal["sweep_extreme"] = 98.0
        bad_trades, bad_invalid = simulate_phase11a_trades(features, [bad_signal], spec)
        self.assertTrue(bad_trades.empty)
        self.assertEqual(bad_invalid, 1)

        long_spec = self._spec("long_low_fade")
        long_features = build_phase11a_feature_bars(
            self._bars(
                rows=[
                    {"time": "09:30", "open": 95.0, "high": 100.0, "low": 90.0, "close": 95.0},
                    {"time": "09:35", "open": 91.0, "high": 96.0, "low": 88.0, "close": 91.0},
                    {"time": "09:40", "open": 91.0, "high": 96.0, "low": 88.0, "close": 92.0},
                    {"time": "09:45", "open": 92.0, "high": 94.0, "low": 91.0, "close": 93.0},
                ]
            ),
            long_spec,
        )
        long_signal = generate_phase11a_signals(long_features, long_spec)[0]
        long_signal["atr"] = 2.0
        long_trades, _ = simulate_phase11a_trades(long_features, [long_signal], long_spec)
        self.assertEqual(float(long_trades.iloc[0]["structural_stop"]), 87.75)
        self.assertEqual(float(long_trades.iloc[0]["atr_cap_stop"]), 88.5)
        self.assertEqual(float(long_trades.iloc[0]["actual_stop"]), 88.5)

    def test_partial_session_excluded_and_no_overnight_fields_required(self) -> None:
        partial = self._bars(session="2026-07-03")
        valid = self._bars(session="2026-01-06")
        bars = pd.concat([partial, valid], ignore_index=True)
        result = run_phase11a_retest(bars, Phase11AConfig(max_specs=2, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        if not result["trade_logs"].empty:
            self.assertNotIn("2026-07-03", set(result["trade_logs"]["trading_session"].astype(str)))
        spec = self._spec()
        features = build_phase11a_feature_bars(valid, spec)
        forbidden = [c for c in features.columns if c.startswith("overnight") or c in {"gap_bucket", "gap_filter"}]
        self.assertEqual(forbidden, [])

    def test_cost_waterfall_serialization_report_and_candidate_totals(self) -> None:
        result = run_phase11a_retest(self._bars(), Phase11AConfig(max_specs=4, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        candidates = result["candidate_results"]
        self.assertEqual(len(candidates), 4)
        for col in ["gross_pnl", "fees_only_pnl", "normal_slippage_pnl", "net_pnl", "stress_pnl", "invalid_risk_skipped_count"]:
            self.assertIn(col, candidates.columns)
        if not result["trade_logs"].empty:
            reconciled = round(float(result["trade_logs"].iloc[0]["normal_slippage_pnl"]), 2)
            self.assertEqual(reconciled, round(float(result["trade_logs"].iloc[0]["net_pnl"]), 2))
        payload = json.loads(serialize_phase11a_specs(build_phase11a_specs(Phase11AConfig(max_specs=2))))
        self.assertEqual(payload[0]["instrument"], "MNQ")
        report = render_phase11a_report(result, {"next_action": "unit", "rationale": "test"}, Path("reports/phase11a_opening_range_fade_confirmation_report.md"))
        self.assertIn(f"Specs evaluated: `{len(candidates)}`", report)
        self.assertIn("Research/simulation only. No live trading", report)


if __name__ == "__main__":
    unittest.main()
