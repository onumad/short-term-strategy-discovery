from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8d_hypothesis_queue import (
    Phase8DConfig,
    build_phase8d_hypothesis_queue,
    render_phase8d_report,
)


class Phase8DHypothesisQueueTests(unittest.TestCase):
    def test_hypothesis_queue_is_broad_diverse_and_serializable(self) -> None:
        queue = build_phase8d_hypothesis_queue(Phase8DConfig(max_hypotheses=60))
        records = queue.to_dict("records")
        json.dumps(records)

        self.assertGreaterEqual(len(queue), 30)
        self.assertIn("MGC", set(queue["instrument"]))
        self.assertIn("MNQ", set(queue["instrument"]))
        self.assertIn("long_only", set(queue["side"]))
        self.assertIn("short_only", set(queue["side"]))
        self.assertTrue(any(int(tf) != 1 for tf in queue["timeframe"]))
        self.assertGreaterEqual(queue["family"].nunique(), 8)
        self.assertEqual(queue["hypothesis_id"].nunique(), len(queue))

    def test_top_ten_is_not_single_family_or_single_side(self) -> None:
        queue = build_phase8d_hypothesis_queue(Phase8DConfig(max_hypotheses=60))
        top = queue.head(10)

        self.assertLessEqual(int(top["family"].value_counts().max()), 3)
        self.assertIn("long_only", set(top["side"]))
        self.assertIn("short_only", set(top["side"]))
        self.assertIn("MGC", set(top["instrument"]))
        self.assertIn("MNQ", set(top["instrument"]))
        self.assertTrue(any(int(tf) != 1 for tf in top["timeframe"]))

    def test_render_phase8d_report_includes_guardrails_and_kill_conditions(self) -> None:
        queue = build_phase8d_hypothesis_queue(Phase8DConfig(max_hypotheses=36))
        report = render_phase8d_report(
            queue,
            Phase8DConfig(max_hypotheses=36),
            queue_path=Path("outputs/phase8d_hypothesis_queue.csv"),
            report_path=Path("reports/phase8d_hypothesis_queue_report.md"),
            run_artifact_dir=Path("artifacts/phase8d_hypothesis_queue/test-run"),
        )

        self.assertIn("# Phase 8D Broad Hypothesis Queue", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("Kill Conditions", report)
        self.assertIn("outputs/phase8d_hypothesis_queue.csv", report)
        self.assertIn("artifacts/phase8d_hypothesis_queue/test-run", report)


if __name__ == "__main__":
    unittest.main()
