from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8m_risk_concentration_diagnostic import (  # noqa: E402
    Phase8MConfig,
    apply_phase8m_risk_controls,
    build_phase8m_candidate_specs,
    evaluate_phase8m_candidates,
    render_phase8m_report,
    remap_phase8m_exits,
)


class Phase8MRiskConcentrationDiagnosticTests(unittest.TestCase):
    def _trades(self) -> pd.DataFrame:
        rows = []
        sessions = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Monday"]
        minutes = ["09:45", "10:15", "10:45", "11:15", "12:45", "13:15"]
        pnls = [100.0, -80.0, 120.0, 90.0, -60.0, 110.0]
        for session, weekday, minute, pnl in zip(sessions, weekdays, minutes, pnls):
            entry = pd.Timestamp(f"{session} {minute}", tz="America/New_York")
            rows.append(
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_test",
                    "instrument": "MNQ",
                    "family": "vwap_pullback_continuation",
                    "timeframe": 5,
                    "side": "long",
                    "event_time": entry - pd.Timedelta(minutes=5),
                    "entry_time": entry,
                    "exit_time": entry + pd.Timedelta(minutes=15),
                    "trading_session": session,
                    "weekday": weekday,
                    "minute_bucket": f"{entry.hour:02d}:{(entry.minute // 30) * 30:02d}-{entry.hour:02d}:{(entry.minute // 30) * 30 + 30:02d}",
                    "rth_bucket": "10:00-11:00" if entry.hour == 10 else "other",
                    "entry_price": 20000.0,
                    "exit_price": 20000.0 + pnl / 2.0,
                    "exit_reason": "time_stop",
                    "gross_pnl": pnl + 2.74,
                    "net_pnl": pnl,
                    "stress_net_pnl": pnl - 1.0,
                    "risk_dollars": 100.0,
                    "same_bar_ambiguity": 0,
                }
            )
        duplicate = dict(rows[0])
        duplicate["entry_time"] = rows[0]["entry_time"] + pd.Timedelta(minutes=10)
        duplicate["exit_time"] = rows[0]["exit_time"] + pd.Timedelta(minutes=10)
        duplicate["event_time"] = rows[0]["event_time"] + pd.Timedelta(minutes=10)
        duplicate["net_pnl"] = 50.0
        duplicate["stress_net_pnl"] = 49.0
        rows.append(duplicate)
        return pd.DataFrame(rows)

    def _bars(self) -> pd.DataFrame:
        rows = []
        for session in ["2026-01-05", "2026-01-06"]:
            for minute in range(9 * 60 + 30, 14 * 60 + 1):
                ts = pd.Timestamp(f"{session} {minute // 60:02d}:{minute % 60:02d}", tz="America/New_York")
                base = 20000.0 + (minute - (9 * 60 + 30)) * 0.25
                rows.append(
                    {
                        "timestamp": ts,
                        "symbol": "MNQ",
                        "open": base,
                        "high": base + 2.0,
                        "low": base - 2.0,
                        "close": base + 0.5,
                        "volume": 10,
                        "trading_session": session,
                        "session_segment": "RTH",
                    }
                )
        return pd.DataFrame(rows)

    def test_build_phase8m_candidate_specs_is_bounded_and_marks_diagnostic_weekday_rules(self) -> None:
        config = Phase8MConfig(max_specs=200)
        specs = build_phase8m_candidate_specs(config)

        self.assertGreater(len(specs), 0)
        self.assertLessEqual(len(specs), 200)
        ids = [spec.candidate_id for spec in specs]
        self.assertIn("base_pre_14_00__horizon_close_15m__mt1_gap30_sal1_saw0_dl1.0_dpnone", ids)
        weekday_specs = [spec for spec in specs if "exclude_wednesday" in spec.base_filter]
        self.assertTrue(weekday_specs)
        self.assertTrue(all(spec.diagnostic_only for spec in weekday_specs))

    def test_apply_phase8m_risk_controls_uses_only_prior_accepted_trades_for_gaps_and_lockouts(self) -> None:
        config = Phase8MConfig()
        spec = [s for s in build_phase8m_candidate_specs(config) if s.max_trades_per_day == 1 and s.min_minutes_between_entries == 30 and s.stop_after_loss][0]
        filtered = apply_phase8m_risk_controls(self._trades(), spec)

        self.assertLessEqual(filtered.groupby("trading_session").size().max(), 1)
        self.assertEqual(filtered["phase8m_candidate_id"].nunique(), 1)
        self.assertTrue(filtered["risk_control_notes"].str.contains("max_trades_per_day").any() or len(filtered) < len(self._trades()))

    def test_remap_phase8m_exits_produces_executable_exit_models_without_same_bar_favorable_assumption(self) -> None:
        trades = self._trades().head(2)
        remapped = remap_phase8m_exits(trades, self._bars(), Phase8MConfig(exit_models=("horizon_close_15m", "fixed_r_1_5_time30", "vwap_failure_1_5_time30")))

        self.assertEqual(set(remapped["exit_model"]), {"horizon_close_15m", "fixed_r_1_5_time30", "vwap_failure_1_5_time30"})
        self.assertIn("risk_dollars", remapped.columns)
        self.assertTrue((remapped["risk_dollars"] > 0).all())
        self.assertTrue((remapped["same_bar_ambiguity"] >= 0).all())

    def test_evaluate_phase8m_candidates_reports_folds_daily_concentration_and_explicit_labels(self) -> None:
        config = Phase8MConfig(train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3, min_trades=2, min_active_session_pct=0.2, concentration_limit=1.0, trade_concentration_limit=1.0, max_specs=12)
        specs = build_phase8m_candidate_specs(config)
        results, logs, folds, daily, concentration, outliers = evaluate_phase8m_candidates(self._trades(), specs, config)

        self.assertEqual(len(results), len(specs))
        self.assertIn("phase8m_label", results.columns)
        self.assertTrue(set(results["phase8m_label"]).issubset({"phase8m_rejected_negative_stress", "phase8m_rejected_fold_instability", "phase8m_rejected_concentration", "phase8m_rejected_low_activity", "phase8m_watchlist_needs_more_history", "phase8m_candidate_for_paper_review"}))
        self.assertIn("walk_forward_test_pnl", results.columns)
        self.assertFalse(folds.empty)
        self.assertFalse(daily.empty)
        self.assertFalse(concentration.empty)
        self.assertIn("2026-01-07", set(outliers["session_date"].astype(str)))
        self.assertEqual(logs["phase8m_candidate_id"].nunique(), len(specs))

    def test_render_phase8m_report_includes_guardrails_outputs_and_abandon_decision_rule(self) -> None:
        config = Phase8MConfig(train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3, min_trades=2, max_specs=6)
        specs = build_phase8m_candidate_specs(config)
        results, logs, folds, daily, concentration, outliers = evaluate_phase8m_candidates(self._trades(), specs, config)
        report = render_phase8m_report(
            results,
            folds,
            concentration,
            outliers,
            config,
            results_path=Path("outputs/phase8m_candidate_results.csv"),
            filtered_trade_logs_path=Path("outputs/phase8m_filtered_trade_logs.csv"),
            fold_results_path=Path("outputs/phase8m_walk_forward_folds.csv"),
            daily_pnl_path=Path("outputs/phase8m_daily_pnl.csv"),
            concentration_path=Path("outputs/phase8m_concentration_diagnostics.csv"),
            outlier_path=Path("outputs/phase8m_outlier_session_diagnostics.csv"),
            specs_path=Path("outputs/phase8m_strategy_specs.json"),
            report_path=Path("reports/phase8m_risk_concentration_diagnostic_report.md"),
            run_artifact_dir=Path("artifacts/phase8m_mnq_vwap_risk_exit_concentration/test"),
        )

        self.assertIn("# Phase 8M MNQ VWAP Risk / Exit / Concentration Diagnostic", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No paper-trading promotion", report)
        self.assertIn("When To Abandon This Branch", report)
        self.assertIn("outputs/phase8m_candidate_results.csv", report)


if __name__ == "__main__":
    unittest.main()
