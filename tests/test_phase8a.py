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

from short_term_edge.phase8a import (
    Phase8AConfig,
    rank_phase8a_results,
    render_phase8a_report,
    run_phase8a_mgc_clean_family_search,
    select_mgc_clean_family_specs,
    write_phase8a_specs,
)


class Phase8ATests(unittest.TestCase):
    def test_select_mgc_clean_family_specs_is_mgc_only_bounded_and_deterministic(self) -> None:
        config = Phase8AConfig(max_specs=12, min_specs=6, timeframes=(1, 3))

        first = select_mgc_clean_family_specs(config)
        second = select_mgc_clean_family_specs(config)

        self.assertGreaterEqual(len(first), 6)
        self.assertLessEqual(len(first), 12)
        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertEqual({spec.instrument for spec in first}, {"MGC"})
        self.assertEqual({spec.family for spec in first}, {"opening_range_breakout", "prior_session_levels", "vwap_reclaim_rejection"})
        self.assertEqual({spec.timeframe for spec in first}, {1, 3})
        self.assertEqual(sum(1 for spec in first if spec.timeframe == 1), sum(1 for spec in first if spec.timeframe == 3))

    def test_rank_phase8a_results_prefers_clean_cost_resilient_candidate(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "raw_fragile",
                    "net_pnl": 4000.0,
                    "slippage_4_ticks_net_pnl": -100.0,
                    "trades": 140,
                    "active_session_pct": 0.35,
                    "max_drawdown": -1800.0,
                    "best_day_concentration": 0.40,
                    "best_trade_concentration": 0.20,
                    "validation_pnl": 900.0,
                    "holdout_pnl": 800.0,
                    "same_bar_stop_target_ambiguity_count": 12,
                    "phase5n_rank": 1,
                    "phase5n_score": 99.0,
                    "phase5n_label": "stale",
                    "phase5n_notes": "stale phase label",
                },
                {
                    "candidate_id": "clean_candidate",
                    "net_pnl": 1500.0,
                    "slippage_4_ticks_net_pnl": 800.0,
                    "trades": 90,
                    "active_session_pct": 0.22,
                    "max_drawdown": -450.0,
                    "best_day_concentration": 0.14,
                    "best_trade_concentration": 0.09,
                    "validation_pnl": 250.0,
                    "holdout_pnl": 200.0,
                    "same_bar_stop_target_ambiguity_count": 0,
                    "phase5n_rank": 2,
                    "phase5n_score": 50.0,
                    "phase5n_label": "stale",
                    "phase5n_notes": "stale phase label",
                },
            ]
        )

        ranked = rank_phase8a_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "clean_candidate")
        self.assertEqual(ranked.iloc[0]["phase8a_label"], "mgc_clean_family_prefilter_survivor")
        self.assertFalse(any(column.startswith("phase5n_") for column in ranked.columns))

    def test_run_phase8a_zero_new_specs_refreshes_checkpoint_without_data_load(self) -> None:
        selected = select_mgc_clean_family_specs(Phase8AConfig(max_specs=6, min_specs=6, timeframes=(1,)))
        valid = selected[0]
        with tempfile.TemporaryDirectory(prefix="hermes-phase8a-") as tmp:
            checkpoint = Path(tmp) / "checkpoint.csv"
            checkpoint.write_text(
                "candidate_id,instrument,family,net_pnl,slippage_4_ticks_net_pnl,trades,active_session_pct,max_drawdown,best_day_concentration,best_trade_concentration,validation_pnl,holdout_pnl,same_bar_stop_target_ambiguity_count\n"
                f"{valid.canonical_id()},MGC,{valid.family},1000,500,60,0.2,-400,0.1,0.08,100,100,0\n"
                "legacy_candidate,MGC,vwap_pullback_continuation,900,700,70,0.2,-300,0.1,0.08,80,70,0\n",
                encoding="utf-8",
            )

            result = run_phase8a_mgc_clean_family_search(
                Path(tmp) / "missing-project",
                Phase8AConfig(max_specs=6, min_specs=6, max_new_specs_per_run=0, timeframes=(1,)),
                checkpoint_path=checkpoint,
            )

        self.assertEqual(len(result.specs), 6)
        self.assertEqual(result.complete_sessions, [])
        self.assertEqual(len(result.search_results), 1)
        self.assertEqual(result.search_results.iloc[0]["candidate_id"], valid.canonical_id())
        self.assertEqual(result.search_results.iloc[0]["phase8a_label"], "mgc_clean_family_prefilter_survivor")

    def test_write_phase8a_specs_writes_serializable_json(self) -> None:
        specs = select_mgc_clean_family_specs(Phase8AConfig(max_specs=6, min_specs=6, timeframes=(1,)))
        with tempfile.TemporaryDirectory(prefix="hermes-phase8a-") as tmp:
            path = Path(tmp) / "specs.json"
            write_phase8a_specs(specs, path)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(len(payload), 6)
        self.assertTrue(all(row["instrument"] == "MGC" for row in payload))
        self.assertTrue(all("canonical_id" in row for row in payload))

    def test_render_phase8a_report_includes_guardrails_and_outputs(self) -> None:
        results = rank_phase8a_results(
            pd.DataFrame(
                [
                    {
                        "candidate_id": "candidate_a",
                        "family": "opening_range_breakout",
                        "phase8a_label": "rejected",
                        "net_pnl": -10.0,
                        "slippage_4_ticks_net_pnl": -20.0,
                        "trades": 10,
                        "active_session_pct": 0.05,
                        "max_drawdown": -50.0,
                        "best_day_concentration": 1.0,
                        "best_trade_concentration": 1.0,
                        "validation_pnl": -5.0,
                        "holdout_pnl": -5.0,
                        "same_bar_stop_target_ambiguity_count": 1,
                        "base_cost": 3.22,
                        "stress_cost": 5.22,
                    }
                ]
            )
        )

        report = render_phase8a_report(
            Phase8AConfig(max_specs=6, min_specs=6, max_new_specs_per_run=2, timeframes=(1,)),
            results,
            selected_specs_count=6,
            complete_sessions_count=877,
            results_path=Path("outputs/phase8a.csv"),
            specs_path=Path("outputs/specs.json"),
            report_path=Path("reports/phase8a.md"),
        )

        self.assertIn("No live trading", report)
        self.assertIn("Phase 8A pivots away from the failed Phase 7 legacy combo", report)
        self.assertIn("outputs/phase8a.csv", report)
        self.assertIn("Rows scored: `1` / selected specs: `6`", report)
        self.assertIn("Cost assumptions", report)
        self.assertIn("base cost", report)
        self.assertIn("PHASE8A_MAX_NEW_SPECS=2", report)
        self.assertIn("mgc_clean_family_prefilter_survivor", report)


if __name__ == "__main__":
    unittest.main()
