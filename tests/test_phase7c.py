from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase7c import (  # noqa: E402
    build_assumption_drift_comparisons,
    collect_legacy_mgc_combo_summary,
    render_phase7c_report,
    run_phase7c_assumption_drift_audit,
)


class Phase7CTests(unittest.TestCase):
    def test_collect_legacy_summary_mines_readme_without_writing_to_legacy_repo(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-phase7c-") as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                """
Run the current mixed MGC combo search:
`vwap-pb2-sb6-r1-cd3-q1-side-short+od10-md4-bo1-sb1-r2-q1+or5-bo1-sb1-r2-q1`
python -m trading_bot.cli combo-tournament data/processed/mgc_6mo_2025-12-29_to_2026-06-26.csv --symbol MGC --max-trades-per-day 5
python -m trading_bot.cli walk-forward-combo-payout data/processed/mgc_6mo_2025-12-29_to_2026-06-26.csv --symbol MGC --quantity 2 --max-trades-per-day 4 --train-days 30 --test-days 20 --phase-daily-profit-targets none,200 --stress-slippage-ticks-per-side 1,2,3
The current `max4 30x20` path passes evaluation on 2026-02-17, reaches the payout-first objective on 2026-03-23 with 513.0000 estimated payout, and later shows a stitched max-loss breach on 2026-04-06.
""",
                encoding="utf-8",
            )

            summary = collect_legacy_mgc_combo_summary(readme)

        self.assertEqual(summary["instrument"], "MGC")
        self.assertEqual(summary["data_period"], "2025-12-29 to 2026-06-26")
        self.assertIn("payout-first", summary["objective"])
        self.assertIn("30", summary["walk_forward"])
        self.assertIn("q2", summary["quantity"])

    def test_build_assumption_drift_is_deterministic_and_prioritizes_high_severity(self) -> None:
        legacy = {
            "objective": "payout-first funded-policy objective with restarts",
            "data_period": "2025-12-29 to 2026-06-26",
            "quantity": "q2",
            "max_trades_per_day": "4/5/20 variants",
            "risk_policy": "phase-aware funded policy grid",
            "cost_slippage": "stress scenarios",
        }
        current = {
            "objective": "strict net-PnL research gates",
            "data_period": "2026-04-06 to 2026-07-02",
            "quantity": "q1",
            "max_trades_per_day": "3/4 variants",
            "risk_policy": "fixed daily lockouts",
            "cost_slippage": "4 ticks per side aggregate stress",
            "same_bar_policy": "stop-first with rejection flag",
        }

        first = build_assumption_drift_comparisons(legacy, current)
        second = build_assumption_drift_comparisons(legacy, current)

        self.assertEqual([row.to_dict() for row in first], [row.to_dict() for row in second])
        high_axes = {row.axis for row in first if row.severity == "high"}
        self.assertIn("optimization objective", high_axes)
        self.assertIn("data window", high_axes)
        self.assertIn("same-bar ambiguity", high_axes)
        self.assertTrue(all("live" not in row.recommended_action.lower() for row in first))

    def test_render_report_keeps_research_guardrails_and_next_phase(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-phase7c-project-") as tmp:
            root = Path(tmp)
            (root / "outputs").mkdir()
            (root / "outputs" / "phase7b_mgc_combo_results.csv").write_text(
                "combo_id,phase7b_label,net_pnl,slippage_4_ticks_net_pnl,phase7b_notes\ncombo,rejected,-1,-2,fails stress\n",
                encoding="utf-8",
            )
            result = run_phase7c_assumption_drift_audit(root, legacy_readme=Path(tmp) / "missing.md")
            report = render_phase7c_report(result, root / "outputs" / "phase7c.csv", root / "reports" / "phase7c.md")

        self.assertIsInstance(result.comparisons, pd.DataFrame)
        self.assertIn("No live trading", report)
        self.assertIn("Phase 7D payout-path / matched-window diagnostic", report)
        self.assertIn("optimization objective", report)


if __name__ == "__main__":
    unittest.main()
