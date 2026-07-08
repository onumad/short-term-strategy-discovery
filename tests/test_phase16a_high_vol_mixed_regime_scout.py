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

from short_term_edge.phase16a_high_vol_mixed_regime_scout import (  # noqa: E402
    Phase16AConfig,
    Phase16ASpec,
    build_phase16a_feature_bars,
    build_phase16a_specs,
    compute_phase16a_frozen_levels,
    daily_correlation_to_matrix,
    generate_phase16a_signals,
    make_phase16a_recommendation,
    render_phase16a_report,
    resample_rth_5m,
    run_phase16a_scout,
    simulate_phase16a_trades,
)


class Phase16AHighVolMixedRegimeScoutTests(unittest.TestCase):
    def test_matrix_builds_exact_48_and_excludes_banned_logic(self) -> None:
        specs = build_phase16a_specs()
        self.assertEqual(len(specs), 48)
        text = json.dumps([s.to_dict() for s in specs]).lower()
        for required in ("high_vol_mixed_extreme_fade", "high_vol_mixed_midpoint_reclaim", "high_vol_mixed_late_resolution_breakout"):
            self.assertIn(required, text)
        for banned in ("mgc", "overnight", "prior_rth", "opening_range", "opening_drive", "vwap", "compression", "trend_day_late", "power_hour_continuation"):
            self.assertNotIn(banned, text)

    def test_regime_window_prior_percentile_and_lunch_freeze_are_deterministic(self) -> None:
        bars = self._window_bars()
        config = Phase16AConfig(min_prior_sessions_for_percentile=2)
        levels = compute_phase16a_frozen_levels(resample_rth_5m(bars), config)
        row = levels[levels["trading_session"].eq("2026-01-03")].iloc[0]
        self.assertEqual(float(row["morning_high"]), 135.0)
        self.assertEqual(float(row["morning_low"]), 95.0)
        self.assertEqual(float(row["morning_range"]), 40.0)
        self.assertEqual(float(row["morning_range_p70"]), 10.0)
        self.assertEqual(float(row["morning_range_p80"]), 10.0)
        self.assertTrue(bool(row["broad_high_vol_mixed"]))
        self.assertTrue(bool(row["strict_high_vol_mixed"]))
        self.assertEqual(row["first_30m_direction"], "up")
        self.assertEqual(row["post_30m_to_1130_direction"], "down")
        self.assertTrue(bool(row["direction_flip_flag"]))
        self.assertEqual(float(row["lunch_high"]), 130.0)
        self.assertEqual(float(row["lunch_low"]), 120.0)
        self.assertFalse(any("overnight" in c or "prior_rth" in c or "vwap" in c for c in levels.columns))

    def test_confirmations_entries_windows_and_max_one_trade_per_day(self) -> None:
        config = Phase16AConfig(min_prior_sessions_for_percentile=2)
        cases = [
            ("high_vol_mixed_extreme_fade", "long", "12:00"),
            ("high_vol_mixed_midpoint_reclaim", "short", "12:00"),
            ("high_vol_mixed_late_resolution_breakout", "long", "13:00"),
        ]
        for family, side, _ in cases:
            with self.subTest(family=family):
                spec = Phase16ASpec(family, side, "broad_high_vol_mixed", "close_confirm_fill_next_open", "hard_stop_time_exit")
                features = build_phase16a_feature_bars(self._signal_bars(family, side), config)
                signals = generate_phase16a_signals(features, spec)
                self.assertGreaterEqual(len(signals), 1)
                self.assertGreater(pd.Timestamp(signals[0]["entry_time"]), pd.Timestamp(signals[0]["signal_time"]))
                trades, invalid = simulate_phase16a_trades(features, signals, spec)
                self.assertEqual(invalid, 0)
                self.assertLessEqual(trades.groupby("trading_session").size().max(), 1)
        two = Phase16ASpec("high_vol_mixed_late_resolution_breakout", "long", "broad_high_vol_mixed", "two_bar_confirm_fill_next_open", "hard_stop_time_exit")
        two_features = build_phase16a_feature_bars(self._signal_bars("high_vol_mixed_late_resolution_breakout", "long"), config)
        two_signals = generate_phase16a_signals(two_features, two)
        self.assertGreater(pd.Timestamp(two_signals[0]["entry_time"]), pd.Timestamp(two_signals[0]["confirmation_time"]))

    def test_stop_cap_invalid_risk_and_same_bar_ambiguity(self) -> None:
        config = Phase16AConfig(min_prior_sessions_for_percentile=2)
        spec = Phase16ASpec("high_vol_mixed_late_resolution_breakout", "long", "broad_high_vol_mixed", "close_confirm_fill_next_open", "structure_target_time_exit")
        features = build_phase16a_feature_bars(self._ambiguity_bars(), config)
        signals = generate_phase16a_signals(features, spec)
        trades, invalid = simulate_phase16a_trades(features, signals, spec)
        self.assertEqual(invalid, 0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "stop_same_bar_conservative")
        self.assertEqual(int(trades.iloc[0]["same_bar_ambiguity"]), 1)
        self.assertLess(float(trades.iloc[0]["actual_stop"]), float(trades.iloc[0]["entry_price"]))
        short = Phase16ASpec("high_vol_mixed_late_resolution_breakout", "short", "broad_high_vol_mixed", "close_confirm_fill_next_open", "hard_stop_time_exit")
        short_features = build_phase16a_feature_bars(self._signal_bars("high_vol_mixed_late_resolution_breakout", "short"), config)
        short_signals = generate_phase16a_signals(short_features, short)
        short_trades, _ = simulate_phase16a_trades(short_features, short_signals, short)
        self.assertGreater(float(short_trades.iloc[0]["actual_stop"]), float(short_trades.iloc[0]["entry_price"]))
        bad_signal = dict(signals[0]); bad_signal["pullback_low"] = 9999.0
        bad, invalid_bad = simulate_phase16a_trades(features, [bad_signal], spec)
        self.assertEqual(len(bad), 0)
        self.assertEqual(invalid_bad, 1)

    def test_correlation_gap_policy_folds_official_gates_and_guardrail(self) -> None:
        cand = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "net_pnl": [1.0, -1.0, 1.0]})
        matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "reg": [1.0, -1.0, 1.0]})
        self.assertEqual(daily_correlation_to_matrix(cand, matrix)["max_abs_correlation"], 1.0)
        bars = self._signal_bars("high_vol_mixed_extreme_fade", "long", sessions=8)
        gaps = pd.DataFrame({"trading_session": sorted(bars["trading_session"].astype(str).unique()), "high_volatility_bucket": True, "full_day_trend_proxy": False, "power_hour_expansion": [True, False] * 4, "large_intraday_movement": True, "prior_rth_high_low_interaction_flag": True, "weak_fold_day": True})
        policy = {"fold_adequacy_defaults": {"module_fold_min_active_days": 1, "module_fold_min_trades": 1}}
        result = run_phase16a_scout(bars, pd.DataFrame(), pd.DataFrame(columns=["trading_session", "net_pnl"]), pd.DataFrame(columns=["trading_session", "net_pnl"]), gaps, policy, Phase16AConfig(max_specs=8, recent_sessions=8, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_prior_sessions_for_percentile=2, min_trades=1, min_active_days=1))
        row = result["candidate_results"].iloc[0]
        self.assertFalse(bool(row["paper_trading_approved"]))
        self.assertFalse(bool(row["official_gates_passed"]))
        self.assertIn(row["primary_fold_view"], "existing_project_folds")
        self.assertIn("fold_adequacy_status", row)
        self.assertGreaterEqual(int(row["gap_days_covered"]), 1)
        self.assertEqual(set(result["walk_forward_folds"]["fold_view"].unique()), {"existing_project_folds", "half_year_folds", "rolling_6_month_test_folds", "quarterly_folds"})
        rec = make_phase16a_recommendation(result)
        self.assertFalse(rec["paper_trading_approved"])
        self.assertFalse(rec["official_gates_changed"])
        report = render_phase16a_report(result, rec, Path("reports/phase16a_high_vol_mixed_regime_scout_report.md"))
        self.assertIn("Research/simulation only. No live trading", report)
        self.assertIn("official gates unchanged", report.lower())

    def _window_bars(self) -> pd.DataFrame:
        rows = []
        for day, rng in [("2026-01-01", 10), ("2026-01-02", 10), ("2026-01-03", 40)]:
            if day == "2026-01-03":
                seq = [("09:30", (100, 120, 100, 115)), ("09:55", (115, 135, 110, 130)), ("10:00", (130, 132, 105, 110)), ("11:25", (110, 115, 95, 115)), ("11:30", (122, 130, 120, 126)), ("12:55", (126, 129, 121, 125)), ("13:00", (126, 128, 124, 127))]
            else:
                seq = [("09:30", (100, 105, 100, 104)), ("10:00", (104, 108, 102, 106)), ("11:25", (106, 110, 100, 105)), ("11:30", (105, 110, 103, 106)), ("12:55", (106, 109, 104, 107))]
            for hhmm, vals in seq:
                rows.append(self._row(f"{day} {hhmm}", *vals, session=day))
        return pd.DataFrame(rows)

    def _signal_bars(self, family: str, side: str, sessions: int = 3) -> pd.DataFrame:
        rows = []
        for n in range(sessions):
            day = f"2026-01-{1+n:02d}"
            seq = [("09:30", (100, 120, 100, 115)), ("09:55", (115, 135, 110, 130)), ("10:00", (130, 132, 105, 110)), ("11:25", (110, 115, 95, 115)), ("11:30", (116, 124, 112, 120)), ("12:55", (120, 126, 116, 121))]
            if n < 2:
                seq = [("09:30", (100, 105, 100, 104)), ("10:00", (104, 108, 102, 106)), ("11:25", (106, 110, 100, 105)), ("11:30", (105, 110, 103, 106)), ("12:55", (106, 109, 104, 107))]
            elif family == "high_vol_mixed_extreme_fade":
                seq += [("12:00", (100, 101, 94, 96)), ("12:05", (96, 110, 95, 105)), ("12:10", (105, 111, 104, 110))] if side == "long" else [("12:00", (130, 136, 129, 134)), ("12:05", (134, 135, 120, 125)), ("12:10", (125, 126, 118, 120))]
            elif family == "high_vol_mixed_midpoint_reclaim":
                seq += [("12:00", (114, 116, 106, 112)), ("12:05", (112, 114, 108, 109)), ("12:10", (109, 110, 104, 105))] if side == "short" else [("12:00", (106, 114, 105, 112)), ("12:05", (112, 120, 111, 118)), ("12:10", (118, 124, 117, 122))]
            else:
                seq += [("13:00", (124, 128, 123, 127)), ("13:05", (127, 130, 126, 129)), ("13:10", (129, 132, 120, 130))] if side == "long" else [("13:00", (114, 116, 110, 111)), ("13:05", (111, 112, 108, 109)), ("13:10", (109, 120, 100, 108))]
            for hhmm, vals in seq:
                rows.append(self._row(f"{day} {hhmm}", *vals, session=day))
        return pd.DataFrame(rows)

    def _ambiguity_bars(self) -> pd.DataFrame:
        rows = []
        seq = [("09:30", (100, 120, 100, 115)), ("09:55", (115, 135, 110, 130)), ("10:00", (130, 132, 105, 110)), ("11:25", (110, 115, 95, 115)), ("11:30", (116, 124, 112, 120)), ("12:55", (120, 126, 116, 121)), ("13:00", (124, 128, 123, 127)), ("13:05", (127, 130, 126, 129)), ("13:10", (129, 150, 120, 130))]
        for n in range(2):
            day = f"2026-01-{1+n:02d}"
            for hhmm, vals in [("09:30", (100, 105, 100, 104)), ("10:00", (104, 108, 102, 106)), ("11:25", (106, 110, 100, 105)), ("11:30", (105, 110, 103, 106)), ("12:55", (106, 109, 104, 107))]:
                rows.append(self._row(f"{day} {hhmm}", *vals, session=day))
        for hhmm, vals in seq:
            rows.append(self._row(f"2026-01-03 {hhmm}", *vals, session="2026-01-03"))
        return pd.DataFrame(rows)

    def _row(self, ts: str, open_: float, high: float, low: float, close: float, session: str) -> dict[str, object]:
        return {"timestamp": pd.Timestamp(ts, tz="America/New_York"), "symbol": "MNQ", "open": open_, "high": high, "low": low, "close": close, "volume": 1, "trading_session": session, "session_segment": "RTH"}


if __name__ == "__main__":
    unittest.main()
