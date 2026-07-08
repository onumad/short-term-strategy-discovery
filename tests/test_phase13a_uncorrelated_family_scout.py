from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase13a_uncorrelated_family_scout import (  # noqa: E402
    Phase13AConfig,
    Phase13ASpec,
    build_phase13a_feature_bars,
    build_phase13a_specs,
    compute_intraday_range_levels,
    compute_prior_rth_levels,
    daily_correlation_to_matrix,
    generate_phase13a_signals,
    make_phase13a_recommendation,
    render_phase13a_report,
    run_phase13a_scout,
    simulate_phase13a_trades,
)


class Phase13AUncorrelatedFamilyScoutTests(unittest.TestCase):
    def test_matrix_builds_exact_48_specs_and_excludes_disallowed_families(self) -> None:
        specs = build_phase13a_specs()
        self.assertEqual(len(specs), 48)
        names = " ".join(s.family for s in specs).lower()
        for banned in ("overnight", "opening_range", "opening_drive", "vwap", "volatility_compression", "mgc"):
            self.assertNotIn(banned, names)

    def test_lunch_and_power_ranges_use_only_build_window_and_freeze(self) -> None:
        bars = self._bars_for_ranges()
        lunch = compute_intraday_range_levels(bars, "lunch_range_breakout")
        power = compute_intraday_range_levels(bars, "power_hour_range_breakout")
        self.assertEqual(float(lunch.iloc[0]["level_high"]), 110.0)
        self.assertEqual(float(lunch.iloc[0]["level_low"]), 100.0)
        self.assertEqual(float(power.iloc[0]["level_high"]), 120.0)
        self.assertEqual(float(power.iloc[0]["level_low"]), 115.0)
        spec = Phase13ASpec("lunch_range_breakout", "long", "close_confirm_fill_next_open", "hard_stop_time_exit")
        features = build_phase13a_feature_bars(bars, spec)
        after = features[features["timestamp"].dt.strftime("%H:%M").ge("13:00")]
        self.assertTrue(after["level_high"].eq(110.0).all())

    def test_prior_rth_levels_use_only_prior_session_and_no_overnight_fields(self) -> None:
        bars = self._bars_for_prior()
        levels = compute_prior_rth_levels(bars)
        today = levels[levels["trading_session"].astype(str).eq("2026-01-03")].iloc[0]
        self.assertEqual(float(today["level_high"]), 210.0)
        self.assertEqual(float(today["level_low"]), 190.0)
        spec = Phase13ASpec("prior_rth_high_low_breakout", "long", "close_confirm_fill_next_open", "hard_stop_time_exit")
        features = build_phase13a_feature_bars(bars, spec)
        self.assertFalse(any("overnight" in c or "opening_range" in c or "opening_drive" in c for c in features.columns))

    def test_entry_models_next_open_windows_max_one_and_ambiguity(self) -> None:
        bars = self._breakout_trade_bars()
        spec = Phase13ASpec("lunch_range_breakout", "long", "close_confirm_fill_next_open", "structure_target_time_exit")
        features = build_phase13a_feature_bars(bars, spec)
        signals = generate_phase13a_signals(features, spec)
        self.assertEqual(len(signals), 1)
        self.assertGreater(pd.Timestamp(signals[0]["entry_time"]), pd.Timestamp(signals[0]["signal_time"]))
        self.assertGreaterEqual(pd.Timestamp(signals[0]["entry_time"]).hour * 60 + pd.Timestamp(signals[0]["entry_time"]).minute, 13 * 60)
        trades, invalid = simulate_phase13a_trades(features, signals, spec)
        self.assertEqual(invalid, 0)
        self.assertEqual(len(trades), 1)
        self.assertEqual(int(trades.iloc[0]["same_bar_ambiguity"]), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "stop_same_bar_conservative")
        two = Phase13ASpec("lunch_range_breakout", "long", "two_bar_confirm_fill_next_open", "hard_stop_time_exit")
        two_signals = generate_phase13a_signals(build_phase13a_feature_bars(bars, two), two)
        self.assertTrue(pd.Timestamp(two_signals[0]["entry_time"]) > pd.Timestamp(two_signals[0]["confirmation_time"]))

    def test_correlation_labeling_gates_and_report_guardrail(self) -> None:
        cand = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "net_pnl": [1.0, -1.0, 1.0]})
        matrix = pd.DataFrame({"trading_session": ["2026-01-01", "2026-01-02", "2026-01-03"], "reg": [1.0, -1.0, 1.0]})
        self.assertEqual(daily_correlation_to_matrix(cand, matrix)["max_abs_correlation"], 1.0)
        bars = self._breakout_trade_bars()
        result = run_phase13a_scout(bars, matrix, pd.DataFrame(), Phase13AConfig(max_specs=1, recent_sessions=3, min_trades=1, min_active_days=1))
        self.assertEqual(len(result["candidate_results"]), 1)
        self.assertNotEqual(result["candidate_results"].iloc[0]["phase13a_label"], "phase13a_candidate_for_paper_review")
        self.assertFalse(bool(result["candidate_results"].iloc[0]["paper_trading_approved"]))
        rec = make_phase13a_recommendation(result)
        report = render_phase13a_report(result, rec, Path("reports/phase13a_uncorrelated_family_scout_report.md"))
        self.assertIn("Research/simulation only. No live trading", report)

    def _bars_for_ranges(self) -> pd.DataFrame:
        rows = []
        for ts, high, low, close in [
            ("2026-01-02 11:30", 110, 105, 108),
            ("2026-01-02 12:00", 108, 100, 101),
            ("2026-01-02 13:00", 150, 130, 140),
            ("2026-01-02 13:30", 120, 116, 119),
            ("2026-01-02 14:00", 118, 115, 116),
            ("2026-01-02 14:30", 160, 140, 150),
        ]:
            rows.append(self._row(ts, high - 1, high, low, close, "2026-01-02"))
        return pd.DataFrame(rows)

    def _bars_for_prior(self) -> pd.DataFrame:
        rows = []
        for session, base in [("2026-01-02", 200), ("2026-01-03", 300)]:
            for hhmm in ("09:30", "10:00", "15:55"):
                rows.append(self._row(f"{session} {hhmm}", base, base + 10, base - 10, base, session))
        return pd.DataFrame(rows)

    def _breakout_trade_bars(self) -> pd.DataFrame:
        rows = []
        times = ["11:30", "12:00", "12:30", "13:00", "13:05", "13:10", "13:15"]
        values = [
            (100, 110, 100, 105),
            (105, 108, 102, 104),
            (104, 109, 101, 103),
            (111, 112, 110, 111.5),
            (112, 113, 111, 112.5),
            (112.5, 123, 98, 100),
            (100, 101, 99, 100),
        ]
        for hhmm, vals in zip(times, values):
            rows.append(self._row(f"2026-01-02 {hhmm}", *vals, session="2026-01-02"))
        return pd.DataFrame(rows)

    def _row(self, ts: str, open_: float, high: float, low: float, close: float, session: str) -> dict[str, object]:
        return {
            "timestamp": pd.Timestamp(ts, tz="America/New_York"),
            "symbol": "MNQ",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1,
            "trading_session": session,
            "session_segment": "RTH",
        }


if __name__ == "__main__":
    unittest.main()
