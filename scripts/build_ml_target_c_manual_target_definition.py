from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL  # noqa: E402
from short_term_edge.ml_target_c_manual_target_definition import (  # noqa: E402
    build_ml_target_c_manual_target_definition,
)


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "ml-target-c-r1")
    result = build_ml_target_c_manual_target_definition(PROJECT_ROOT, run_id=run_id)
    dataset = result["dataset"]
    recommendation = result["next_action_recommendation"]
    readiness = result["target_readiness_summary"]
    print("ML Target C manual target definition review complete.")
    print(f"Rows: {len(dataset)}")
    print(f"Date range: {dataset['trading_session'].min()} to {dataset['trading_session'].max()}")
    print(f"Trainable targets: {readiness.loc[readiness['trainable_for_baseline_b'].eq(True), 'target_name'].astype(str).tolist()}")
    print(f"Next action: {recommendation.get('next_action')}")
    print(f"Dataset: {PROJECT_ROOT / 'outputs' / 'ml_target_c_day_regime.csv'}")
    print(f"Report: {PROJECT_ROOT / 'reports' / 'ml_target_c_manual_target_definition_report.md'}")
    print(f"Run artifacts: {PROJECT_ROOT / 'artifacts' / 'ml_target_c_manual_target_definition' / run_id}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
