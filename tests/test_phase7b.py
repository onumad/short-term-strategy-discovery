from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase7b import Phase7BConfig, apply_daily_risk_gates, rank_phase7b_results, select_mgc_combo_specs


class Phase7BTests(unittest.TestCase):
    def test_select_mgc_combo_specs_is_deterministic_and_ports_old_combo_shape(self) -> None:
        combos = select_mgc_combo_specs(Phase7BConfig(max_combos=6, min_combos=4))

        self.assertLessEqual(len(combos), 6)
        self.assertGreaterEqual(len(combos), 4)
        self.assertEqual({combo.symbol for combo in combos}, {"MGC"})
        self.assertEqual([combo.combo_id for combo in combos], [combo.combo_id for combo in select_mgc_combo_specs(Phase7BConfig(max_combos=6, min_combos=4))])
        self.assertTrue(any("vwap_pullback_continuation" in combo.component_families for combo in combos))
        self.assertTrue(any("opening_drive_continuation" in combo.component_families for combo in combos))
        self.assertTrue(any(combo.include_opening_range_breakout for combo in combos))
        self.assertIn("vwap_first", {combo.priority for combo in combos})

    def test_apply_daily_risk_gates_annotates_and_stops_after_daily_limits(self) -> None:
        trades = pd.DataFrame(
            [
                {"trading_session": "2026-01-02", "entry_time": "2026-01-02 09:35", "exit_time": "2026-01-02 09:40", "net_pnl": 120.0, "component_family": "opening_drive_continuation", "side": "long"},
                {"trading_session": "2026-01-02", "entry_time": "2026-01-02 09:41", "exit_time": "2026-01-02 09:45", "net_pnl": 150.0, "component_family": "vwap_pullback_continuation", "side": "short"},
                {"trading_session": "2026-01-02", "entry_time": "2026-01-02 09:46", "exit_time": "2026-01-02 09:50", "net_pnl": -80.0, "component_family": "opening_range_breakout", "side": "long"},
                {"trading_session": "2026-01-03", "entry_time": "2026-01-03 09:35", "exit_time": "2026-01-03 09:40", "net_pnl": -275.0, "component_family": "opening_drive_continuation", "side": "short"},
                {"trading_session": "2026-01-03", "entry_time": "2026-01-03 09:41", "exit_time": "2026-01-03 09:45", "net_pnl": 500.0, "component_family": "vwap_pullback_continuation", "side": "short"},
            ]
        )

        gated = apply_daily_risk_gates(trades, max_trades_per_day=3, daily_loss_limit=250.0, daily_profit_target=250.0)

        self.assertEqual(len(gated), 3)
        self.assertEqual(list(gated["daily_trade_number"]), [1, 2, 1])
        self.assertEqual(list(gated["daily_realized_pnl_before_trade"]), [0.0, 120.0, 0.0])
        self.assertEqual(list(gated["lockout_status"]), ["active", "active", "active"])
        self.assertNotIn("opening_range_breakout", set(gated["component_family"]))
        self.assertEqual(float(gated[gated["trading_session"] == "2026-01-03"]["net_pnl"].sum()), -275.0)

    def test_rank_phase7b_results_promotes_stable_combo_over_raw_fragile_combo(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "combo_id": "raw_fragile",
                    "net_pnl": 4000.0,
                    "slippage_4_ticks_net_pnl": -200.0,
                    "trades": 120,
                    "active_session_pct": 0.30,
                    "max_drawdown": -900.0,
                    "best_day_concentration": 0.18,
                    "best_trade_concentration": 0.12,
                    "validation_pnl": 800.0,
                    "holdout_pnl": 700.0,
                    "same_bar_stop_target_ambiguity_count": 0,
                },
                {
                    "combo_id": "stable_combo",
                    "net_pnl": 1500.0,
                    "slippage_4_ticks_net_pnl": 900.0,
                    "trades": 80,
                    "active_session_pct": 0.20,
                    "max_drawdown": -450.0,
                    "best_day_concentration": 0.16,
                    "best_trade_concentration": 0.10,
                    "validation_pnl": 300.0,
                    "holdout_pnl": 250.0,
                    "same_bar_stop_target_ambiguity_count": 0,
                },
            ]
        )

        ranked = rank_phase7b_results(rows)

        self.assertEqual(ranked.iloc[0]["combo_id"], "stable_combo")
        self.assertEqual(ranked.iloc[0]["phase7b_label"], "mgc_combo_prefilter_survivor")


if __name__ == "__main__":
    unittest.main()
