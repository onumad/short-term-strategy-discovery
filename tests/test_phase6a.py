from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase6a import Phase6AConfig, _limit_specs_for_run, rank_phase6a_results, run_phase6a_expansion, select_phase6a_specs


class Phase6ATests(unittest.TestCase):
    def test_select_phase6a_specs_expands_dimensions_without_live_trading_scope(self) -> None:
        config = Phase6AConfig(max_specs=48, min_specs=40)

        first = select_phase6a_specs(config)
        second = select_phase6a_specs(config)

        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertGreaterEqual(len(first), 40)
        self.assertLessEqual(len(first), 48)
        self.assertEqual({spec.instrument for spec in first}, {"MNQ"})
        self.assertIn(2, {int(spec.timeframe) for spec in first})
        self.assertIn(90, {int(spec.entry.params.get("or_minutes", 0)) for spec in first if "or_minutes" in spec.entry.params})
        self.assertTrue(any(spec.exit.params.get("stop_ticks") == 20 for spec in first))
        self.assertTrue(all("deterministic Phase 6A" in spec.notes for spec in first))

    def test_rank_phase6a_results_keeps_strict_research_gates_and_watchlist_label(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "robust_candidate",
                    "instrument": "MNQ",
                    "family": "vwap_reclaim_rejection",
                    "timeframe": 2,
                    "net_pnl": 2600.0,
                    "slippage_4_ticks_net_pnl": 850.0,
                    "trades": 160,
                    "active_session_pct": 0.34,
                    "max_drawdown": -950.0,
                    "best_day_concentration": 0.18,
                    "best_trade_concentration": 0.12,
                    "validation_pnl": 300.0,
                    "holdout_pnl": -100.0,
                    "risk_notes": "negative holdout PnL",
                },
                {
                    "candidate_id": "fragile_candidate",
                    "instrument": "MNQ",
                    "family": "opening_range_breakout",
                    "timeframe": 1,
                    "net_pnl": 6200.0,
                    "slippage_4_ticks_net_pnl": -400.0,
                    "trades": 300,
                    "active_session_pct": 0.88,
                    "max_drawdown": -3600.0,
                    "best_day_concentration": 0.62,
                    "best_trade_concentration": 0.41,
                    "validation_pnl": 1200.0,
                    "holdout_pnl": 700.0,
                    "risk_notes": "fails 4-tick slippage",
                },
            ]
        )

        ranked = rank_phase6a_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "robust_candidate")
        self.assertEqual(ranked.iloc[0]["phase6a_label"], "watchlist_needs_walk_forward")
        self.assertEqual(
            ranked.loc[ranked["candidate_id"].eq("fragile_candidate"), "phase6a_label"].iloc[0],
            "rejected",
        )
        self.assertIn("4-tick slippage", ranked.loc[ranked["candidate_id"].eq("fragile_candidate"), "phase6a_notes"].iloc[0])

    def test_limit_specs_for_run_keeps_completed_and_caps_new_work(self) -> None:
        specs = select_phase6a_specs(Phase6AConfig(max_specs=48, min_specs=40))[:5]
        checkpoint_path = PROJECT_ROOT / ".hermes" / "tmp_phase6a_batch_test.csv"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(f"candidate_id\n{specs[0].canonical_id()}\n", encoding="utf-8")
        try:
            limited = _limit_specs_for_run(specs, checkpoint_path, max_new_specs=2)
        finally:
            checkpoint_path.unlink(missing_ok=True)

        self.assertEqual([spec.canonical_id() for spec in limited], [spec.canonical_id() for spec in specs[:3]])

    def test_limit_specs_for_run_allows_zero_new_specs_for_checkpoint_refresh(self) -> None:
        Phase6AConfig(max_new_specs_per_run=0).validate()
        specs = select_phase6a_specs(Phase6AConfig(max_specs=48, min_specs=40))[:4]
        checkpoint_path = PROJECT_ROOT / ".hermes" / "tmp_phase6a_refresh_test.csv"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            f"candidate_id\n{specs[0].canonical_id()}\n{specs[1].canonical_id()}\n",
            encoding="utf-8",
        )
        try:
            limited = _limit_specs_for_run(specs, checkpoint_path, max_new_specs=0)
        finally:
            checkpoint_path.unlink(missing_ok=True)

        self.assertEqual([spec.canonical_id() for spec in limited], [spec.canonical_id() for spec in specs[:2]])

    def test_run_phase6a_expansion_zero_new_specs_refreshes_checkpoint_without_data_load(self) -> None:
        specs = select_phase6a_specs(Phase6AConfig(max_specs=48, min_specs=40))[:1]
        checkpoint_path = PROJECT_ROOT / ".hermes" / "tmp_phase6a_zero_refresh_test.csv"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            "candidate_id,instrument,family,timeframe,ranking_score,net_pnl,slippage_4_ticks_net_pnl,trades,active_session_pct,max_drawdown,best_day_concentration,best_trade_concentration,validation_pnl,holdout_pnl,risk_notes\n"
            f"{specs[0].canonical_id()},MNQ,{specs[0].family},{specs[0].timeframe},1,10,5,80,0.5,-100,0.1,0.1,1,1,existing\n",
            encoding="utf-8",
        )
        try:
            result = run_phase6a_expansion(
                PROJECT_ROOT / "path_that_should_not_be_read",
                Phase6AConfig(max_new_specs_per_run=0),
                checkpoint_path=checkpoint_path,
            )
        finally:
            checkpoint_path.unlink(missing_ok=True)

        self.assertEqual(result.search_results.iloc[0]["candidate_id"], specs[0].canonical_id())
        self.assertEqual(result.complete_sessions, [])

    def test_rank_phase6a_results_handles_resumed_ranked_checkpoint_rows(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "phase5n_rank": 1,
                    "candidate_id": "checkpoint_candidate",
                    "instrument": "MNQ",
                    "family": "prior_session_levels",
                    "timeframe": 2,
                    "net_pnl": 1500.0,
                    "slippage_4_ticks_net_pnl": 500.0,
                    "trades": 100,
                    "active_session_pct": 0.25,
                    "max_drawdown": -700.0,
                    "best_day_concentration": 0.12,
                    "best_trade_concentration": 0.10,
                    "validation_pnl": 100.0,
                    "holdout_pnl": 100.0,
                }
            ]
        )

        ranked = rank_phase6a_results(rows)

        self.assertEqual(ranked.iloc[0]["phase6a_rank"], 1)
        self.assertNotIn("phase5n_rank", ranked.columns)


if __name__ == "__main__":
    unittest.main()
