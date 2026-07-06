from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5n import Phase5NConfig, rank_prefilter_results, score_prefilter_specs, select_prefilter_specs


class Phase5NTests(unittest.TestCase):
    def test_select_prefilter_specs_is_mnq_only_bounded_and_family_balanced(self) -> None:
        config = Phase5NConfig(max_specs=60)

        first = select_prefilter_specs(config)
        second = select_prefilter_specs(config)

        self.assertEqual([spec.canonical_id() for spec in first], [spec.canonical_id() for spec in second])
        self.assertEqual({spec.instrument for spec in first}, {"MNQ"})
        self.assertGreaterEqual(len(first), 40)
        self.assertLessEqual(len(first), 60)
        families = {spec.family for spec in first}
        self.assertEqual(
            families,
            {"opening_range_failure", "opening_range_breakout", "vwap_reclaim_rejection", "prior_session_levels"},
        )

    def test_rank_prefilter_results_strictly_penalizes_stress_concentration_activity_and_drawdown(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "high_pnl_brittle",
                    "instrument": "MNQ",
                    "family": "opening_range_failure",
                    "timeframe": 1,
                    "ranking_score": 70.0,
                    "net_pnl": 8000.0,
                    "slippage_4_ticks_net_pnl": -100.0,
                    "trades": 200,
                    "active_session_pct": 0.30,
                    "max_drawdown": -2600.0,
                    "best_day_concentration": 0.55,
                    "best_trade_concentration": 0.35,
                    "validation_pnl": 1000.0,
                    "holdout_pnl": 1000.0,
                    "risk_notes": "fails 4-tick slippage",
                },
                {
                    "candidate_id": "distributed_survivor",
                    "instrument": "MNQ",
                    "family": "prior_session_levels",
                    "timeframe": 3,
                    "ranking_score": 30.0,
                    "net_pnl": 2200.0,
                    "slippage_4_ticks_net_pnl": 900.0,
                    "trades": 180,
                    "active_session_pct": 0.48,
                    "max_drawdown": -700.0,
                    "best_day_concentration": 0.18,
                    "best_trade_concentration": 0.12,
                    "validation_pnl": 500.0,
                    "holdout_pnl": 450.0,
                    "risk_notes": "No major Phase 5A risk flags.",
                },
                {
                    "candidate_id": "too_quiet",
                    "instrument": "MNQ",
                    "family": "vwap_reclaim_rejection",
                    "timeframe": 1,
                    "ranking_score": 45.0,
                    "net_pnl": 1800.0,
                    "slippage_4_ticks_net_pnl": 1000.0,
                    "trades": 25,
                    "active_session_pct": 0.08,
                    "max_drawdown": -400.0,
                    "best_day_concentration": 0.16,
                    "best_trade_concentration": 0.10,
                    "validation_pnl": 300.0,
                    "holdout_pnl": 300.0,
                    "risk_notes": "low active-session coverage",
                },
            ]
        )

        ranked = rank_prefilter_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "distributed_survivor")
        self.assertEqual(ranked.iloc[0]["phase5n_label"], "prefilter_survivor")
        self.assertEqual(
            ranked.loc[ranked["candidate_id"].eq("high_pnl_brittle"), "phase5n_label"].iloc[0],
            "rejected",
        )
        self.assertIn(
            "insufficient active-day coverage",
            ranked.loc[ranked["candidate_id"].eq("too_quiet"), "phase5n_notes"].iloc[0],
        )

    def test_score_prefilter_specs_resumes_from_checkpoint_and_writes_each_batch(self) -> None:
        specs = select_prefilter_specs(Phase5NConfig(max_specs=40, min_specs=40))[:3]
        checkpoint_path = PROJECT_ROOT / ".hermes" / "tmp_phase5n_resume_test.csv"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            "candidate_id,instrument,family,timeframe,ranking_score,net_pnl,slippage_4_ticks_net_pnl,trades,active_session_pct,max_drawdown,best_day_concentration,best_trade_concentration,validation_pnl,holdout_pnl,risk_notes\n"
            f"{specs[0].canonical_id()},MNQ,{specs[0].family},{specs[0].timeframe},1,10,5,80,0.5,-100,0.1,0.1,1,1,existing\n",
            encoding="utf-8",
        )
        calls: list[str] = []

        class DummyScore:
            def __init__(self, spec) -> None:
                self.spec = spec

            def to_dict(self):
                return {
                    "candidate_id": self.spec.canonical_id(),
                    "instrument": self.spec.instrument,
                    "family": self.spec.family,
                    "timeframe": self.spec.timeframe,
                    "ranking_score": 1.0,
                    "net_pnl": 100.0,
                    "slippage_4_ticks_net_pnl": 50.0,
                    "trades": 100,
                    "active_session_pct": 0.5,
                    "max_drawdown": -100.0,
                    "best_day_concentration": 0.1,
                    "best_trade_concentration": 0.1,
                    "validation_pnl": 10.0,
                    "holdout_pnl": 10.0,
                    "risk_notes": "generated",
                }

        def score_func(spec, prepared, sessions):
            calls.append(spec.canonical_id())
            return DummyScore(spec)

        try:
            ranked = score_prefilter_specs(
                specs,
                prepared={},
                complete_sessions=[],
                checkpoint_path=checkpoint_path,
                batch_size=1,
                score_func=score_func,
            )
        finally:
            checkpoint_path.unlink(missing_ok=True)

        self.assertEqual(calls, [spec.canonical_id() for spec in specs[1:]])
        self.assertEqual(set(ranked["candidate_id"]), {spec.canonical_id() for spec in specs})
        self.assertIn("phase5n_rank", ranked.columns)


if __name__ == "__main__":
    unittest.main()
