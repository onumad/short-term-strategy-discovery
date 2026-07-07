from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ai_search import spec_to_phase4_candidate
from short_term_edge.phase7a import Phase7AConfig, rank_phase7a_results, select_mgc_reproduction_specs


class Phase7ATests(unittest.TestCase):
    def test_select_mgc_reproduction_specs_ports_old_project_families(self) -> None:
        specs = select_mgc_reproduction_specs(Phase7AConfig(max_specs=12, min_specs=8))

        self.assertLessEqual(len(specs), 12)
        self.assertGreaterEqual(len(specs), 8)
        self.assertEqual({spec.instrument for spec in specs}, {"MGC"})
        self.assertIn("vwap_pullback_continuation", {spec.family for spec in specs})
        self.assertIn("opening_drive_continuation", {spec.family for spec in specs})
        self.assertIn("short", {spec.risk.params.get("side_filter", "both") for spec in specs})
        self.assertEqual([spec.canonical_id() for spec in specs], [spec.canonical_id() for spec in select_mgc_reproduction_specs(Phase7AConfig(max_specs=12, min_specs=8))])

    def test_spec_to_phase4_candidate_supports_ported_vwap_pullback_and_opening_drive(self) -> None:
        specs = select_mgc_reproduction_specs(Phase7AConfig(max_specs=12, min_specs=8))
        by_family = {spec.family: spec for spec in specs}

        vwap = spec_to_phase4_candidate(by_family["vwap_pullback_continuation"])
        drive = spec_to_phase4_candidate(by_family["opening_drive_continuation"])

        self.assertEqual(vwap.family, "vwap_pullback_continuation")
        self.assertEqual(vwap.params["pullback_ref"], "vwap")
        self.assertEqual(vwap.params["side_filter"], "short")
        self.assertGreater(vwap.params["stop_ticks"], 0)
        self.assertEqual(drive.family, "opening_drive_continuation")
        self.assertGreater(drive.params["drive_minutes"], 0)
        self.assertGreater(drive.params["minimum_drive_ticks"], 0)

    def test_rank_phase7a_results_prefers_cost_resilient_stable_mgc_candidate(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "candidate_id": "raw_fragile",
                    "family": "opening_drive_continuation",
                    "net_pnl": 3000.0,
                    "slippage_4_ticks_net_pnl": -50.0,
                    "trades": 180,
                    "active_session_pct": 0.30,
                    "max_drawdown": -900.0,
                    "best_day_concentration": 0.20,
                    "best_trade_concentration": 0.14,
                    "validation_pnl": 500.0,
                    "holdout_pnl": 400.0,
                    "same_bar_stop_target_ambiguity_count": 0,
                },
                {
                    "candidate_id": "stable_candidate",
                    "family": "vwap_pullback_continuation",
                    "net_pnl": 1200.0,
                    "slippage_4_ticks_net_pnl": 700.0,
                    "trades": 90,
                    "active_session_pct": 0.18,
                    "max_drawdown": -500.0,
                    "best_day_concentration": 0.18,
                    "best_trade_concentration": 0.12,
                    "validation_pnl": 250.0,
                    "holdout_pnl": 200.0,
                    "same_bar_stop_target_ambiguity_count": 0,
                },
            ]
        )

        ranked = rank_phase7a_results(rows)

        self.assertEqual(ranked.iloc[0]["candidate_id"], "stable_candidate")
        self.assertEqual(ranked.iloc[0]["phase7a_label"], "mgc_reproduction_prefilter_survivor")


if __name__ == "__main__":
    unittest.main()
