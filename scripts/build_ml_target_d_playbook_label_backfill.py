from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL  # noqa: E402
from short_term_edge.ml_target_d_playbook_label_backfill import (  # noqa: E402
    build_ml_target_d_playbook_label_backfill,
)


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "ml-target-d-r1")
    result = build_ml_target_d_playbook_label_backfill(PROJECT_ROOT, run_id=run_id)
    recommendation = result["next_action_recommendation"]
    readiness = result["target_readiness_summary"]
    passing = readiness[readiness["trainable_for_baseline_b"].eq(True)]
    print("ML Target D playbook label backfill complete.")
    print(f"Rows: {len(result['dataset'])}")
    print(f"Backfilled modules: {(result['coverage_audit'].set_index('audit_item').loc['backfilled_module_count', 'value'])}")
    print(f"Trainable target/split pairs: {len(passing)}")
    print(f"Next action: {recommendation['next_action']}")
    print(f"Report: {PROJECT_ROOT / 'reports' / 'ml_target_d_playbook_label_backfill_report.md'}")
    print(f"Run artifacts: {PROJECT_ROOT / 'artifacts' / 'ml_target_d_playbook_label_backfill' / run_id}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
