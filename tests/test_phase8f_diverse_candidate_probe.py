from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8f_diverse_candidate_probe import Phase8FConfig, render_phase8f_report, select_phase8f_specs


class Phase8FDiverseCandidateProbeTests(unittest.TestCase):
    def _event_results(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "hypothesis_id": "MNQ_vwap_pullback_continuation_tf5_long_only_a25f2113",
                    "instrument": "MNQ",
                    "timeframe": 5,
                    "side": "long_only",
                    "family": "vwap_pullback_continuation",
                    "phase8e_label": "backtest_candidate",
                    "phase8e_score": 61.2,
                },
                {
                    "hypothesis_id": "MNQ_vwap_reclaim_rejection_tf1_long_only_bdbad7c5",
                    "instrument": "MNQ",
                    "timeframe": 1,
                    "side": "long_only",
                    "family": "vwap_reclaim_rejection",
                    "phase8e_label": "backtest_candidate",
                    "phase8e_score": 61.1,
                },
                {
                    "hypothesis_id": "MNQ_opening_range_fade_tf3_long_only_ad380f25",
                    "instrument": "MNQ",
                    "timeframe": 3,
                    "side": "long_only",
                    "family": "opening_range_fade",
                    "phase8e_label": "backtest_candidate",
                    "phase8e_score": 27.4,
                },
                {
                    "hypothesis_id": "MNQ_volatility_compression_breakout_tf15_long_only_aea99b32",
                    "instrument": "MNQ",
                    "timeframe": 15,
                    "side": "long_only",
                    "family": "volatility_compression_breakout",
                    "phase8e_label": "backtest_candidate",
                    "phase8e_score": 43.7,
                },
            ]
        )

    def test_select_phase8f_specs_maps_supported_event_candidates_to_strategy_specs(self) -> None:
        specs = select_phase8f_specs(self._event_results(), Phase8FConfig(max_specs=3))
        payload = [json.loads(spec.to_json()) for spec in specs]

        self.assertEqual(len(specs), 3)
        self.assertEqual(len({spec.family for spec in specs}), 3)
        self.assertIn("vwap_pullback_continuation", {spec.family for spec in specs})
        self.assertIn("vwap_reclaim_rejection", {spec.family for spec in specs})
        self.assertIn("opening_range_failure", {spec.family for spec in specs})
        self.assertTrue(all(spec.instrument == "MNQ" for spec in specs))
        self.assertTrue(all(spec.risk.params.get("side_filter") == "long" for spec in specs))
        json.dumps(payload)

    def test_render_phase8f_report_includes_guardrails_and_bounded_decision(self) -> None:
        results = pd.DataFrame(
            [
                {
                    "phase8f_rank": 1,
                    "candidate_id": "MNQ_vwap_reclaim_rejection_tf1_x",
                    "instrument": "MNQ",
                    "family": "vwap_reclaim_rejection",
                    "phase8f_label": "rejected",
                    "phase8f_score": -10.0,
                    "net_pnl": -100.0,
                    "slippage_4_ticks_net_pnl": -200.0,
                    "trades": 100,
                    "active_session_pct": 0.5,
                    "max_drawdown": -500.0,
                    "phase8f_notes": "negative net PnL",
                }
            ]
        )
        report = render_phase8f_report(
            results,
            Phase8FConfig(max_specs=3),
            results_path=Path("outputs/phase8f_diverse_candidate_probe_results.csv"),
            report_path=Path("reports/phase8f_diverse_candidate_probe_report.md"),
            run_artifact_dir=Path("artifacts/phase8f_diverse_candidate_probe/test-run"),
        )

        self.assertIn("# Phase 8F Diverse Candidate Probe", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("at most `3`", report)
        self.assertIn("outputs/phase8f_diverse_candidate_probe_results.csv", report)


if __name__ == "__main__":
    unittest.main()
