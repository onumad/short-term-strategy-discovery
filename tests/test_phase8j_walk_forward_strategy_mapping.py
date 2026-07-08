from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8j_walk_forward_strategy_mapping import (
    Phase8JConfig,
    apply_phase8j_strategy_spec,
    build_phase8j_strategy_spec,
    render_phase8j_report,
    run_phase8j_walk_forward,
    summarize_phase8j_walk_forward,
)
from short_term_edge.strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


class Phase8JWalkForwardStrategyMappingTests(unittest.TestCase):
    def _source_trades(self) -> pd.DataFrame:
        rows = []
        for index, session in enumerate(pd.date_range("2026-01-02", periods=6, freq="B")):
            entry = pd.Timestamp(f"{session.date()} 09:45", tz="America/New_York")
            rows.append(
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_a25f2113",
                    "instrument": "MNQ",
                    "family": "vwap_pullback_continuation",
                    "timeframe": 5,
                    "entry_delay": "next_5m_close",
                    "exit_shape": "horizon_close_15m",
                    "event_time": entry - pd.Timedelta(minutes=5),
                    "entry_time": entry,
                    "exit_time": entry + pd.Timedelta(minutes=15),
                    "trading_session": str(session.date()),
                    "side": "long",
                    "net_pnl": 100.0 + index,
                    "stress_net_pnl": 90.0 + index,
                }
            )
        return pd.DataFrame(rows)

    def _phase8i_results(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "phase8i_rank": 1,
                    "filter_id": "time_window:pre_14_00",
                    "filter_family": "time_window",
                    "filter_params_json": '{"end": "14:00", "start": "09:30"}',
                    "phase8i_label": "phase8i_filter_candidate",
                    "phase8i_score": 110.0,
                }
            ]
        )

    def test_horizon_close_strategy_spec_round_trip_is_allowed_for_research_mapping(self) -> None:
        spec = StrategySpec(
            instrument="MNQ",
            family="vwap_pullback_continuation",
            timeframe=5,
            entry=EntryRule("vwap_pullback", {"source_hypothesis_id": "hyp", "entry_delay": "next_5m_close"}),
            exit=ExitRule("horizon_close", {"time_stop_minutes": 15}),
            risk=RiskRule("one_open_position", {"max_trades_per_day": 3, "entry_filter_id": "time_window:pre_14_00"}),
        ).validate()

        self.assertEqual(StrategySpec.from_json(spec.to_json()), spec)
        self.assertIn("MNQ_vwap_pullback_continuation_tf5", spec.canonical_id())

    def test_build_phase8j_strategy_spec_records_source_filter_and_horizon_exit(self) -> None:
        spec = build_phase8j_strategy_spec(self._source_trades(), self._phase8i_results(), Phase8JConfig())

        self.assertEqual(spec.instrument, "MNQ")
        self.assertEqual(spec.family, "vwap_pullback_continuation")
        self.assertEqual(spec.entry.name, "vwap_pullback")
        self.assertEqual(spec.exit.name, "horizon_close")
        self.assertEqual(spec.exit.params["time_stop_minutes"], 15)
        self.assertEqual(spec.risk.params["entry_filter_id"], "time_window:pre_14_00")
        self.assertEqual(spec.risk.params["entry_filter_end"], "14:00")
        self.assertIn("Phase 8J", spec.notes)

    def test_apply_phase8j_strategy_spec_filters_using_new_york_entry_time_only(self) -> None:
        trades = pd.DataFrame(
            [
                {"entry_time": "2025-10-31 13:59:00-04:00", "trading_session": "2025-10-31", "net_pnl": 1.0},
                {"entry_time": "2025-11-03 14:00:00-05:00", "trading_session": "2025-11-03", "net_pnl": 2.0},
            ]
        )
        spec = build_phase8j_strategy_spec(self._source_trades(), self._phase8i_results(), Phase8JConfig())

        filtered = apply_phase8j_strategy_spec(trades, spec)

        self.assertEqual(filtered["net_pnl"].tolist(), [1.0])
        self.assertEqual(filtered.iloc[0]["phase8j_entry_filter"], "time_window:pre_14_00")

    def test_walk_forward_scores_chronological_folds_and_candidate_label(self) -> None:
        config = Phase8JConfig(train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3, min_test_trades=1, concentration_limit=1.0, trade_concentration_limit=1.0)
        spec = build_phase8j_strategy_spec(self._source_trades(), self._phase8i_results(), config)
        filtered = apply_phase8j_strategy_spec(self._source_trades(), spec)

        fold_results = run_phase8j_walk_forward(filtered, spec, config)
        summary = summarize_phase8j_walk_forward(fold_results, spec, config)

        self.assertEqual(len(fold_results), 9)
        self.assertEqual(fold_results["fold"].nunique(), 3)
        self.assertEqual(set(fold_results["segment"]), {"train", "validation", "test"})
        first = fold_results[fold_results["fold"].eq(1)]
        self.assertLess(first[first["segment"].eq("train")].iloc[0]["segment_end"], first[first["segment"].eq("test")].iloc[0]["segment_start"])
        self.assertEqual(summary.iloc[0]["phase8j_label"], "phase8j_strategy_mapping_candidate")
        self.assertEqual(int(summary.iloc[0]["test_positive_folds"]), 3)

    def test_render_phase8j_report_includes_guardrails_outputs_and_label(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "candidate_id": "MNQ_vwap_pullback_continuation_tf5_test",
                    "phase8j_label": "phase8j_strategy_mapping_candidate",
                    "phase8j_score": 42.0,
                    "folds": 3,
                    "test_net_pnl": 300.0,
                    "test_stress_net_pnl": 270.0,
                    "test_trades": 3,
                    "test_positive_fold_pct": 1.0,
                    "worst_test_fold_pnl": 90.0,
                    "max_test_drawdown": 0.0,
                    "test_best_day_concentration": 0.3,
                    "phase8j_notes": "survives bounded walk-forward mapping diagnostic",
                }
            ]
        )
        report = render_phase8j_report(
            summary,
            pd.DataFrame(),
            StrategySpec(
                instrument="MNQ",
                family="vwap_pullback_continuation",
                timeframe=5,
                entry=EntryRule("vwap_pullback", {}),
                exit=ExitRule("horizon_close", {"time_stop_minutes": 15}),
                risk=RiskRule("one_open_position", {"max_trades_per_day": 3}),
            ),
            Phase8JConfig(),
            spec_path=Path("outputs/phase8j_strategy_spec.json"),
            filtered_trade_log_path=Path("outputs/phase8j_filtered_trade_log.csv"),
            fold_results_path=Path("outputs/phase8j_walk_forward_folds.csv"),
            summary_path=Path("outputs/phase8j_walk_forward_summary.csv"),
            report_path=Path("reports/phase8j_walk_forward_strategy_mapping_report.md"),
            run_artifact_dir=Path("artifacts/phase8j_walk_forward_strategy_mapping/test-run"),
        )

        self.assertIn("# Phase 8J Walk-Forward Strategy Mapping", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("No paper-trading promotion", report)
        self.assertIn("phase8j_strategy_mapping_candidate", report)
        self.assertIn("outputs/phase8j_strategy_spec.json", report)


if __name__ == "__main__":
    unittest.main()
