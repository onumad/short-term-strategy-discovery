from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.conditional_specialist_framework_h import build_conditional_specialist_framework_h  # noqa: E402


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "conditional-specialist-framework-h-r1")
    result = build_conditional_specialist_framework_h(PROJECT_ROOT, run_id=run_id)
    recommendation = result["recommendation"]
    print("Conditional Specialist Framework H complete.")
    print(f"Registered modules: {len(result['activation_contracts'])}")
    print(f"Historical replay modules: {len(result['historical_replay_universe'])}")
    print(f"Default-admitted modules: {len(result['default_admission_universe'])}")
    print(f"No trade is valid: {result['policy']['no_trade_is_valid']}")
    print(f"Next action: {recommendation['next_action']}")
    print(f"Report: {result['paths']['report']}")
    print(f"Run artifacts: {PROJECT_ROOT / 'artifacts' / 'conditional_specialist_framework_h' / run_id}")


if __name__ == "__main__":
    main()
