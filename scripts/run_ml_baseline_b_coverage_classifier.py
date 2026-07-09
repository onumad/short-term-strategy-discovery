from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_baseline_b_coverage_classifier import build_ml_baseline_b  # noqa: E402


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "ml-baseline-b-r1")
    result = build_ml_baseline_b(PROJECT_ROOT, run_id)
    recommendation = result["next_action_recommendation"]
    print("ML Baseline B coverage classifier complete.")
    print(f"Metric rows: {len(result['metrics'])}")
    print(f"Stable model/windows: {recommendation['stable_model_window_count']}")
    print(f"Next action: {recommendation['next_action']}")
    print(f"Report: {result['paths']['report']}")


if __name__ == "__main__":
    main()
