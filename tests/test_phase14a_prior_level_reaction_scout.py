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

from short_term_edge.phase14a_prior_level_reaction_scout import (  # noqa: E402
    Phase14AConfig,
    Phase14ASpec,
    build_phase14a_feature_bars,
    build_phase14a_specs,
    compute_prior_rth_close_midpoint_levels,
    daily_correlation_to_matrix,
    generate_phase14a_signals,
    make_phase14a_recommendation,
    render_phase14a_report,
    run_phase14a_scout,
    simulate_phase14a_trades,
)


class Phase14APriorLevelReactionScoutTests(unittest.TestCase):
    def test_matrix_builds_exact_48_and_excludes_banned_levels(self) -> None:
        specs = build_phase14a_specs()
        self.assertEqual(len(specs), 48)
        text = json.dumps([s.to_dict() for s in specs]).lower()
        for required in ("prior_rth_close", "prior_rth_midpoint"):
            self.assertIn(required, text)
        for banned in ("prior_rth_high_low_breakout", "overnight", "opening_range", "opening_drive", "vwap", "volatility", "mgc"):
            self.assertNotIn(banned, text)
        self.assertFalse(any(s.level_type in {"prior_rth_high", "prior_rth_low"} for s in specs))

    def test_prior_rth_close_midpoint_uses_previous_complete_rth_session(self) -> None:
        bars = self._prior_level_bars(extra_current_extreme=True)
        levels = compute_prior_rth_close_midpoint_levels(bars)
        today = levels[levels["trading_session"].astype(str).eq("2026-01-03")].iloc[0]
        self.assertEqual(float(today["prior_rth_close"]), 200.0)
        self.assertEqual(float(today["prior_rth_midpoint"]), 200.0)
        self.assertEqual(str(today["prior_rth_session"]), "2026-01-02")
        spec = Phase14ASpec("prior_rth_close", "breakout_hold", "long", "close_confirm_fill_next_open", "hard_stop_time_exit")
        features = build_phase14a_feature_bars(bars, spec)
        self.assertFalse(any("overnight" in c or "opening_range" in c or "opening_drive" in c or "prior_rth_high" == c or "prior_rth_low" == c for c in features.columns))

    def test_interaction_families_long_short_and_confirmation_entries(self) -> None:
        cases = [
            ("reclaim_after_breach", "long"),
            ("reclaim_after_breach", "short"),
            ("rejection_from_level", "long"),
            ("rejection_from_level", "short"),
            ("breakout_hold", "long"),
            ("breakout_hold", "short"),
        ]
        for family, side in cases:
            with self.subTest(family=family, side=side):
                spec = Phase14ASpec("prior_rth_close", family, side, "close_confirm_fill_next_open", "hard_stop_time_exit")
                features = build_phase14a_feature_bars(self._signal_bars(family, side), spec)
                signals = generate_phase14a_signals(features, spec)
                self.assertGreaterEqual(len(signals), 1)
                self.assertGreater(pd.Timestamp(signals[0]["entry_time"]), pd.Timestamp(signals[0]["signal_time"]))
                minute = pd.Timestamp(signals[0]["entry_time"]).hour * 60 + pd.Timestamp(signals[0]["entry_time"]).minute
                self.assertGreaterEqual(minute, 10 * 60)
                self.assertLess(minute, 15 * 60 + 30)
        two = Phase14ASpec("prior_rth_close", "breakout_hold", "long", "two_bar_confirm_fill_next_open", "hard_stop_time_exit")
        two_signals = generate_phase14a_signals(build_phase14a_feature_bars(self._signal_bars("breakout_hold", "long"), two), two)
        self.assertGreater(pd.Timestamp(two_signals[0]["entry_time"]), pd.Timestamp(two_signals[0]["confirmation_time"]))

    def test_stops_invalid_risk_same_bar_ambiguity_and_max_one_day(self) -> None:
        spec = Phase14ASpec("prior_rth_close", "breakout_hold", "long", "close_confirm_fill_next_open", "structure_target_time_exit")
        features = build_phase14a_feature_bars(self._ambiguity_bars(), spec)
        signals = generate_phase14a_signals(features, spec)
        trades, invalid = simulate_phase14a_trades(features, signals, spec)
        self.assertEqual(invalid, 0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "stop_same_bar_conservative")
        self.assertEqual(int(trades.iloc[0]["same_bar_ambiguity"]), 1)
        bad_signal = dict(signals[0])
        bad_signal["signal_low"] = 9999.0
        bad, invalid_bad = simulate_phase14a_trades(features, [bad_signal], spec)
        self.assertEqual(len(bad), 0)
        self.assertEqual(invalid_bad, 1)

    def test_correlation_gap_recommendation_and_guardrails(self) -> None:
        cand = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "net_pnl": [1.0, -1.0, 1.0]})
        matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "reg": [1.0, -1.0, 1.0]})
        self.assertEqual(daily_correlation_to_matrix(cand, matrix)["max_abs_correlation"], 1.0)
        bars = self._signal_bars("breakout_hold", "long", sessions=6)
        gaps = pd.DataFrame({"trading_session": sorted(bars["trading_session"].astype(str).unique()), "prior_rth_high_low_interaction": True})
        result = run_phase14a_scout(bars, pd.DataFrame(), pd.DataFrame(columns=["trading_session", "net_pnl"]), gaps, Phase14AConfig(max_specs=1, recent_sessions=6, train_sessions=1, validation_sessions=1, test_sessions=1, step_sessions=1, min_trades=1, min_active_days=1))
        self.assertEqual(len(result["candidate_results"]), 1)
        row = result["candidate_results"].iloc[0]
        self.assertFalse(bool(row["paper_trading_approved"]))
        self.assertFalse(bool(row["official_gates_passed"]))
        self.assertGreaterEqual(int(row["gap_days_covered"]), 1)
        rec = make_phase14a_recommendation(result)
        self.assertFalse(rec["paper_trading_approved"])
        self.assertFalse(rec["official_gates_changed"])
        report = render_phase14a_report(result, rec, Path("reports/phase14a_prior_level_reaction_scout_report.md"))
        self.assertIn("Research/simulation only. No live trading", report)

    def _prior_level_bars(self, extra_current_extreme: bool = False) -> pd.DataFrame:
        rows = []
        for hhmm, vals in [("09:30", (200, 210, 190, 205)), ("15:55", (205, 210, 190, 200))]:
            rows.append(self._row(f"2026-01-02 {hhmm}", *vals, session="2026-01-02"))
        for hhmm, vals in [("09:30", (300, 500 if extra_current_extreme else 310, 100 if extra_current_extreme else 290, 300)), ("10:00", (200, 205, 195, 202)), ("10:05", (202, 206, 201, 203))]:
            rows.append(self._row(f"2026-01-03 {hhmm}", *vals, session="2026-01-03"))
        return pd.DataFrame(rows)

    def _signal_bars(self, family: str, side: str, sessions: int = 2) -> pd.DataFrame:
        rows = []
        for n in range(sessions):
            day = f"2026-01-{2+n:02d}"
            prev = f"2026-01-{1+n:02d}"
            rows.extend([self._row(f"{prev} 09:30", 200, 210, 190, 200, prev), self._row(f"{prev} 15:55", 200, 210, 190, 200, prev)])
            if side == "long":
                seq = [("09:55", 198, 199, 197, 198), ("10:00", 198, 199, 197, 198.5), ("10:05", 199, 202, 198, 201), ("10:10", 201, 203, 200.5, 202), ("10:15", 202, 204, 201, 203), ("10:20", 203, 204, 202, 203)]
                if family == "rejection_from_level":
                    seq[2] = ("10:05", 202, 203, 199.75, 201)
                elif family == "breakout_hold":
                    seq[1] = ("10:00", 199, 200, 198, 199.5)
                    seq[2] = ("10:05", 199.5, 202, 199, 201)
            else:
                seq = [("09:55", 202, 203, 201, 202), ("10:00", 202, 203, 201, 201.5), ("10:05", 201, 202, 198, 199), ("10:10", 199, 199.5, 197, 198), ("10:15", 198, 199, 196, 197), ("10:20", 197, 198, 196, 197)]
                if family == "rejection_from_level":
                    seq[2] = ("10:05", 198, 200.25, 197, 199)
                elif family == "breakout_hold":
                    seq[1] = ("10:00", 201, 202, 200, 200.5)
                    seq[2] = ("10:05", 200.5, 201, 198, 199)
            for hhmm, vals in [(x[0], x[1:]) for x in seq]:
                rows.append(self._row(f"{day} {hhmm}", *vals, session=day))
        return pd.DataFrame(rows)

    def _ambiguity_bars(self) -> pd.DataFrame:
        rows = [self._row("2026-01-02 09:30", 200, 210, 190, 200, "2026-01-02"), self._row("2026-01-02 15:55", 200, 210, 190, 200, "2026-01-02")]
        for hhmm, vals in [
            ("10:00", (199, 200, 198, 199.5)),
            ("10:05", (199.5, 202, 199, 201)),
            ("10:10", (201, 202, 200.5, 201.5)),
            ("10:15", (201.5, 230, 190, 200)),
        ]:
            rows.append(self._row(f"2026-01-03 {hhmm}", *vals, session="2026-01-03"))
        return pd.DataFrame(rows)

    def _row(self, ts: str, open_: float, high: float, low: float, close: float, session: str) -> dict[str, object]:
        return {"timestamp": pd.Timestamp(ts, tz="America/New_York"), "symbol": "MNQ", "open": open_, "high": high, "low": low, "close": close, "volume": 1, "trading_session": session, "session_segment": "RTH"}


if __name__ == "__main__":
    unittest.main()
