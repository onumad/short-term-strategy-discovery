from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_baseline_a_regime_classifier import build_ml_baseline_a  # noqa: E402
from short_term_edge.ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL  # noqa: E402


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "ml-baseline-a-r1")
    result = build_ml_baseline_a(PROJECT_ROOT, run_id=run_id)
    recommendation = result["next_action_recommendation"]
    target_plan = result["target_plan"]
    metrics = result["metrics"]
    print("ML Baseline A regime classifier complete.")
    print(f"Run ID: {run_id}")
    print(f"Trained targets: {target_plan['trained_targets']}")
    print(f"Skipped targets: {target_plan['skipped_targets']}")
    print(f"Metric rows: {len(metrics)}")
    print(f"Next action: {recommendation.get('next_action')}")
    print(f"Report: {PROJECT_ROOT / 'reports' / 'ml_baseline_a_regime_classifier_report.md'}")
    print(f"Run artifacts: {PROJECT_ROOT / 'artifacts' / 'ml_baseline_a_regime_classifier' / run_id}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
