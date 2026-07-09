from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL, build_ml_dataset_a  # noqa: E402


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "ml-dataset-a-r1")
    result = build_ml_dataset_a(PROJECT_ROOT, run_id=run_id)
    dataset = result["dataset"]
    recommendation = result["next_action_recommendation"]
    print("ML Dataset A day-regime build complete.")
    print(f"Rows: {len(dataset)}")
    print(f"Date range: {dataset['trading_session'].min()} to {dataset['trading_session'].max()}")
    print(f"Target bad playbook day balance: {dataset['target_bad_playbook_day'].value_counts().to_dict()}")
    print(f"Next action: {recommendation.get('next_action')}")
    print(f"Dataset: {PROJECT_ROOT / 'outputs' / 'ml_dataset_a_day_regime.csv'}")
    print(f"Report: {PROJECT_ROOT / 'reports' / 'ml_dataset_a_day_regime_report.md'}")
    print(f"Run artifacts: {PROJECT_ROOT / 'artifacts' / 'ml_dataset_a_day_regime' / run_id}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
