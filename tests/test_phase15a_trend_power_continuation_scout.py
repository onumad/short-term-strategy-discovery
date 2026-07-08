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

from short_term_edge.phase15a_trend_power_continuation_scout import (  # noqa: E402
    Phase15AConfig,
    Phase15ASpec,
    build_phase15a_feature_bars,
    build_phase15a_specs,
    compute_phase15a_frozen_levels,
    daily_correlation_to_matrix,
    generate_phase15a_signals,
    make_phase15a_recommendation,
    render_phase15a_report,
    resample_rth_5m,
    run_phase15a_scout,
    simulate_phase15a_trades,
)


class Phase15ATrendPowerContinuationScoutTests(unittest.TestCase):
    def test_matrix_builds_exact_48_and_excludes_banned_families(self) -> None:
        specs = build_phase15a_specs()
        self.assertEqual(len(specs), 48)
        text = json.dumps([s.to_dict() for s in specs]).lower()
        for required in ("trend_day_late_pullback_continuation", "power_hour_continuation", "low_volatility_late_expansion"):
            self.assertIn(required, text)
        for banned in ("mgc", "overnight", "prior_rth_high", "prior_rth_low", "prior_rth_close", "prior_rth_midpoint", "opening_range", "opening_drive", "vwap", "compression"):
            self.assertNotIn(banned, text)

    def test_build_windows_freeze_levels_and_prior_lunch_percentile(self) -> None:
        bars = self._window_bars()
        bars5 = resample_rth_5m(bars)
        levels = compute_phase15a_frozen_levels(bars5)
        row = levels[levels["trading_session"].eq("2026-01-03")].iloc[0]
        self.assertEqual(float(row["morning_high"]), 130.0)
        self.assertEqual(float(row["morning_low"]), 100.0)
        self.assertEqual(float(row["morning_close"]), 129.0)
        self.assertEqual(float(row["power_range_high"]), 142.0)
        self.assertEqual(float(row["power_range_low"]), 132.0)
        self.assertEqual(float(row["lunch_high"]), 134.0)
        self.assertEqual(float(row["lunch_low"]), 130.0)
        self.assertEqual(int(row["lunch_prior_sessions_used"]), 2)
        self.assertEqual(float(row["lunch_low_vol_threshold"]), 10.0)
        self.assertTrue(bool(row["lunch_low_vol_qualified"]))
        self.assertFalse(any("overnight" in c or "prior_rth" in c for c in levels.columns))

    def test_confirmation_entries_trade_windows_and_max_one_per_day(self) -> None:
        for family, trigger, side in [
            ("trend_day_late_pullback_continuation", "morning_midpoint_retest_resume", "long"),
            ("power_hour_continuation", "power_range_breakout_continuation", "long"),
            ("low_volatility_late_expansion", "lunch_expansion_breakout", "long"),
        ]:
            with self.subTest(family=family):
                spec = Phase15ASpec(family, side, trigger, "close_confirm_fill_next_open", "hard_stop_time_exit")
                features = build_phase15a_feature_bars(self._signal_bars(family), spec)
                signals = generate_phase15a_signals(features, spec)
                self.assertGreaterEqual(len(signals), 1)
                self.assertGreater(pd.Timestamp(signals[0]["entry_time"]), pd.Timestamp(signals[0]["signal_time"]))
                trades, invalid = simulate_phase15a_trades(features, signals, spec)
                self.assertEqual(invalid, 0)
                self.assertLessEqual(trades.groupby("trading_session").size().max(), 1)
        two = Phase15ASpec("power_hour_continuation", "long", "power_range_breakout_continuation", "two_bar_confirm_fill_next_open", "hard_stop_time_exit")
        two_signals = generate_phase15a_signals(build_phase15a_feature_bars(self._signal_bars("power_hour_continuation"), two), two)
        self.assertGreater(pd.Timestamp(two_signals[0]["entry_time"]), pd.Timestamp(two_signals[0]["confirmation_time"]))

    def test_stop_cap_invalid_risk_and_same_bar_ambiguity(self) -> None:
        spec = Phase15ASpec("power_hour_continuation", "long", "power_range_breakout_continuation", "close_confirm_fill_next_open", "structure_target_time_exit")
        features = build_phase15a_feature_bars(self._ambiguity_bars(), spec)
        signals = generate_phase15a_signals(features, spec)
        trades, invalid = simulate_phase15a_trades(features, signals, spec)
        self.assertEqual(invalid, 0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "stop_same_bar_conservative")
        self.assertEqual(int(trades.iloc[0]["same_bar_ambiguity"]), 1)
        self.assertLess(float(trades.iloc[0]["actual_stop"]), float(trades.iloc[0]["entry_price"]))
        bad_signal = dict(signals[0]); bad_signal["signal_low"] = 9999.0
        bad, invalid_bad = simulate_phase15a_trades(features, [bad_signal], spec)
        self.assertEqual(len(bad), 0)
        self.assertEqual(invalid_bad, 1)

    def test_correlation_gap_recommendation_official_gates_and_report_guardrail(self) -> None:
        cand = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "net_pnl": [1.0, -1.0, 1.0]})
        matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "reg": [1.0, -1.0, 1.0]})
        self.assertEqual(daily_correlation_to_matrix(cand, matrix)["max_abs_correlation"], 1.0)
        bars = self._signal_bars("trend_day_late_pullback_continuation", sessions=6)
        gaps = pd.DataFrame({"trading_session": sorted(bars["trading_session"].astype(str).unique()), "rth_trend_day_proxy": True, "power_hour_expansion": True, "lunch_range_expansion": True, "volatility_bucket": "low", "large_intraday_movement": True})
        result = run_phase15a_scout(bars, pd.DataFrame(), pd.DataFrame(columns=["trading_session", "net_pnl"]), gaps, Phase15AConfig(max_specs=8, recent_sessions=6, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        row = result["candidate_results"].iloc[0]
        self.assertFalse(bool(row["paper_trading_approved"]))
        self.assertFalse(bool(row["official_gates_passed"]))
        self.assertGreaterEqual(int(row["gap_days_covered"]), 1)
        rec = make_phase15a_recommendation(result)
        self.assertFalse(rec["paper_trading_approved"])
        self.assertFalse(rec["official_gates_changed"])
        report = render_phase15a_report(result, rec, Path("reports/phase15a_trend_power_continuation_scout_report.md"))
        self.assertIn("Research/simulation only. No live trading", report)

    def _window_bars(self) -> pd.DataFrame:
        rows = []
        specs = [
            ("2026-01-01", 10, 20),
            ("2026-01-02", 12, 22),
            ("2026-01-03", 130, 142),
        ]
        for day, base, phigh in specs:
            seq = [
                ("09:30", (100, 120 if day == "2026-01-03" else base + 5, 100 if day == "2026-01-03" else base, 110)),
                ("11:25", (128, 130 if day == "2026-01-03" else base + 10, 120 if day == "2026-01-03" else base, 129 if day == "2026-01-03" else base + 5)),
                ("11:30", (130, 134 if day == "2026-01-03" else base + 10, 130 if day == "2026-01-03" else base, 132)),
                ("13:25", (132, 133 if day == "2026-01-03" else base + 10, 131 if day == "2026-01-03" else base, 132)),
                ("13:30", (132, phigh, 132, 140)),
                ("14:25", (140, phigh, 136, 141)),
                ("14:30", (145, 180, 90, 160)),
            ]
            for hhmm, vals in seq:
                rows.append(self._row(f"{day} {hhmm}", *vals, session=day))
        return pd.DataFrame(rows)

    def _signal_bars(self, family: str, sessions: int = 3) -> pd.DataFrame:
        rows = []
        for n in range(sessions):
            day = f"2026-01-{1+n:02d}"
            if family == "trend_day_late_pullback_continuation":
                seq = [("09:30", (100, 105, 100, 104)), ("10:30", (104, 120, 103, 118)), ("11:25", (118, 130, 117, 128)), ("13:00", (128, 129, 114, 116)), ("13:05", (116, 125, 115, 124)), ("13:10", (124, 126, 123, 125)), ("13:15", (125, 127, 124, 126))]
            elif family == "power_hour_continuation":
                seq = [("09:30", (100, 105, 100, 104)), ("13:30", (120, 125, 119, 124)), ("14:25", (124, 126, 120, 125)), ("14:30", (126, 130, 125, 129)), ("14:35", (129, 132, 128, 131)), ("14:40", (131, 133, 130, 132)), ("14:45", (132, 134, 131, 133))]
            else:
                # first two sessions create high prior lunch ranges; later sessions qualify as low-vol.
                wide = n < 2
                seq = [("09:30", (100, 105, 100, 104)), ("11:30", (120, 140 if wide else 122, 110 if wide else 120, 121)), ("13:25", (121, 125 if wide else 122, 115 if wide else 120, 121)), ("13:30", (122, 126, 121, 125)), ("13:35", (125, 130, 124, 129)), ("13:40", (129, 131, 128, 130)), ("13:45", (130, 132, 129, 131))]
            for hhmm, vals in seq:
                rows.append(self._row(f"{day} {hhmm}", *vals, session=day))
        return pd.DataFrame(rows)

    def _ambiguity_bars(self) -> pd.DataFrame:
        rows = []
        for hhmm, vals in [("09:30", (100, 105, 100, 104)), ("13:30", (120, 125, 119, 124)), ("14:25", (124, 126, 120, 125)), ("14:30", (126, 130, 125, 129)), ("14:35", (129, 132, 128, 131)), ("14:40", (131, 150, 120, 132))]:
            rows.append(self._row(f"2026-01-03 {hhmm}", *vals, session="2026-01-03"))
        return pd.DataFrame(rows)

    def _row(self, ts: str, open_: float, high: float, low: float, close: float, session: str) -> dict[str, object]:
        return {"timestamp": pd.Timestamp(ts, tz="America/New_York"), "symbol": "MNQ", "open": open_, "high": high, "low": low, "close": close, "volume": 1, "trading_session": session, "session_segment": "RTH"}


if __name__ == "__main__":
    unittest.main()
