from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase6b import Phase6BConfig, _limit_specs_for_run, rank_phase6b_results, run_phase6b_search, select_ambiguity_reduction_specs


class Phase6BTests(unittest.TestCase):
    def test_phase6b_specs_are_mnq_only_deterministic_bounded_and_ambiguity_reducing(self) -> None:
        config = Phase6BConfig(max_specs=24)

        first = select_ambiguity_reduction_specs(config)
        second = select_ambiguity_reduction_specs(config)

        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertLessEqual(len(first), 24)
        self.assertGreaterEqual(len(first), 16)
        self.assertEqual({spec.instrument for spec in first}, {"MNQ"})
        self.assertTrue(all(spec.risk.params.get("max_trades_per_day") == 1 for spec in first))
        self.assertTrue(any(float(spec.entry.params.get("min_range", 0.0)) >= 20.0 for spec in first if "min_range" in spec.entry.params))
        self.assertTrue(any(spec.risk.params.get("stop_after_first_loser") is True for spec in first))
        self.assertTrue(all("Phase 6B ambiguity reduction" in spec.notes for spec in first))

    def test_phase6b_ranking_promotes_lower_concentration_and_drawdown_over_raw_net(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "high_raw_fragile",
                    "instrument": "MNQ",
                    "family": "opening_range_breakout",
                    "timeframe": 1,
                    "net_pnl": 7500.0,
                    "slippage_4_ticks_net_pnl": 1400.0,
                    "trades": 160,
                    "active_session_pct": 0.30,
                    "max_drawdown": -4200.0,
                    "best_day_concentration": 0.58,
                    "best_trade_concentration": 0.36,
                    "validation_pnl": 900.0,
                    "holdout_pnl": 600.0,
                },
                {
                    "candidate_id": "cleaner_lower_raw",
                    "instrument": "MNQ",
                    "family": "opening_range_breakout",
                    "timeframe": 5,
                    "net_pnl": 2600.0,
                    "slippage_4_ticks_net_pnl": 1200.0,
                    "trades": 110,
                    "active_session_pct": 0.24,
                    "max_drawdown": -1400.0,
                    "best_day_concentration": 0.22,
                    "best_trade_concentration": 0.14,
                    "validation_pnl": 300.0,
                    "holdout_pnl": 200.0,
                },
            ]
        )

        ranked = rank_phase6b_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "cleaner_lower_raw")
        self.assertEqual(ranked.iloc[0]["phase6b_label"], "prefilter_survivor")
        self.assertEqual(
            ranked.loc[ranked["candidate_id"].eq("high_raw_fragile"), "phase6b_label"].iloc[0],
            "rejected",
        )
        self.assertIn("concentration", ranked.loc[ranked["candidate_id"].eq("high_raw_fragile"), "phase6b_notes"].iloc[0])

    def test_phase6b_run_zero_new_specs_refreshes_checkpoint_without_data_load(self) -> None:
        specs = select_ambiguity_reduction_specs(Phase6BConfig(max_specs=16, min_specs=16))[:1]
        checkpoint_path = PROJECT_ROOT / ".hermes" / "tmp_phase6b_zero_refresh_test.csv"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            "candidate_id,instrument,family,timeframe,ranking_score,net_pnl,slippage_4_ticks_net_pnl,trades,active_session_pct,max_drawdown,best_day_concentration,best_trade_concentration,validation_pnl,holdout_pnl,risk_notes\n"
            f"{specs[0].canonical_id()},MNQ,{specs[0].family},{specs[0].timeframe},1,1000,800,90,0.25,-900,0.2,0.1,200,200,existing\n",
            encoding="utf-8",
        )
        try:
            result = run_phase6b_search(
                PROJECT_ROOT / "path_that_should_not_be_read",
                Phase6BConfig(max_specs=16, min_specs=16, max_new_specs_per_run=0),
                checkpoint_path=checkpoint_path,
            )
        finally:
            checkpoint_path.unlink(missing_ok=True)

        self.assertEqual(result.search_results.iloc[0]["candidate_id"], specs[0].canonical_id())
        self.assertEqual(result.complete_sessions, [])

    def test_limit_specs_for_run_keeps_completed_and_caps_new_phase6b_work(self) -> None:
        specs = select_ambiguity_reduction_specs(Phase6BConfig(max_specs=16, min_specs=16))[:4]
        checkpoint_path = PROJECT_ROOT / ".hermes" / "tmp_phase6b_batch_test.csv"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(f"candidate_id\n{specs[0].canonical_id()}\n", encoding="utf-8")
        try:
            limited = _limit_specs_for_run(specs, checkpoint_path, max_new_specs=2)
        finally:
            checkpoint_path.unlink(missing_ok=True)

        self.assertEqual([spec.canonical_id() for spec in limited], [spec.canonical_id() for spec in specs[:3]])


if __name__ == "__main__":
    unittest.main()
