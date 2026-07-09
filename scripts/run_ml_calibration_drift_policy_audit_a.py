from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_calibration_drift_policy_audit_a import build_ml_calibration_drift_policy_audit_a  # noqa: E402


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "ml-calibration-drift-policy-audit-a-r1")
    result = build_ml_calibration_drift_policy_audit_a(PROJECT_ROOT, run_id=run_id)
    recommendation = result["next_action_recommendation"]
    print("ML Calibration, Drift, and Policy-Impact Audit A complete.")
    print(f"Replay sessions: {len(result['scheduler_parity'])}")
    print(f"Replay parity passed: {result['scheduler_parity']['parity_pass'].all()}")
    print(f"Selected threshold: {result['calibrator']['threshold']}")
    print(f"Framework metric review eligible: {recommendation['framework_metric_review_eligible']}")
    print(f"Approved as signal input: {recommendation['approved_as_signal_input']}")
    print(f"Next action: {recommendation['next_action']}")
    print(f"Report: {result['paths']['report']}")
    print(f"Run artifacts: {PROJECT_ROOT / 'artifacts' / 'ml_calibration_drift_policy_audit_a' / run_id}")


if __name__ == "__main__":
    main()
