from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase7d import (  # noqa: E402
    Phase7DConfig,
    Phase7DPolicy,
    phase7d_policy_grid,
    render_phase7d_report,
    run_phase7d_payout_diagnostic,
)


class Phase7DTests(unittest.TestCase):
    def test_policy_grid_is_deterministic_and_bounded(self) -> None:
        config = Phase7DConfig(funded_quantities=(1, 2), daily_profit_targets=(None, 200.0), daily_loss_lockouts=(None, 300.0))

        policies = phase7d_policy_grid(config)

        self.assertEqual([policy.policy_id for policy in policies], [policy.policy_id for policy in phase7d_policy_grid(config)])
        self.assertEqual(len(policies), 8)
        self.assertIn(Phase7DPolicy(2, 200.0, 300.0), policies)

    def test_run_payout_diagnostic_replays_matched_window_and_flags_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-phase7d-") as tmp:
            path = Path(tmp) / "trades.csv"
            path.write_text(
                "combo_id,trading_session,net_pnl,same_bar_stop_target_ambiguity,component_family\n"
                "combo_a,2025-12-28,9999,0,ignored\n"
                "combo_a,2025-12-29,1200,0,vwap_pullback_continuation\n"
                "combo_a,2025-12-30,900,1,opening_drive_continuation\n"
                "combo_a,2025-12-31,300,0,vwap_pullback_continuation\n"
                "combo_a,2026-01-02,300,0,vwap_pullback_continuation\n"
                "combo_a,2026-01-05,300,0,vwap_pullback_continuation\n"
                "combo_a,2026-01-06,300,0,vwap_pullback_continuation\n"
                "combo_a,2026-01-07,300,0,vwap_pullback_continuation\n",
                encoding="utf-8",
            )
            config = Phase7DConfig(
                funded_quantities=(1,),
                daily_profit_targets=(None,),
                daily_loss_lockouts=(None,),
                evaluation_target=2_000,
                payout_threshold=500,
                trader_profit_split=0.5,
                min_funded_profit_days=4,
            )

            results = run_phase7d_payout_diagnostic(path, config)

        self.assertEqual(len(results), 1)
        row = results.iloc[0]
        self.assertTrue(bool(row["success"]))
        self.assertEqual(row["evaluation_pass_date"], "2025-12-30")
        self.assertEqual(row["payout_date"], "2026-01-06")
        self.assertEqual(int(row["same_bar_stop_target_ambiguity_count"]), 1)
        self.assertIn("same-bar ambiguity remains", row["phase7d_notes"])

    def test_render_report_does_not_promote_phase7b_rejected_candidates(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-phase7d-report-") as tmp:
            path = Path(tmp) / "trades.csv"
            path.write_text(
                "combo_id,trading_session,net_pnl,same_bar_stop_target_ambiguity,component_family\n"
                "combo_a,2025-12-29,-1200,0,vwap_pullback_continuation\n",
                encoding="utf-8",
            )
            config = Phase7DConfig(funded_quantities=(1,), daily_profit_targets=(None,), daily_loss_lockouts=(None,))
            results = run_phase7d_payout_diagnostic(path, config)
            report = render_phase7d_report(results, config, Path(tmp) / "results.csv", Path(tmp) / "report.md")

        self.assertIn("No live trading", report)
        self.assertIn("does not override Phase 7B rejection labels", report)
        self.assertIn("Rows scored", report)


if __name__ == "__main__":
    unittest.main()
