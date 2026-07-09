from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ml_backfill_e_phase10b_causality_audit import (  # noqa: E402
    build_ml_backfill_e_phase10b_causality_audit,
)


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "ml-backfill-e-r1")
    minimum = int(os.environ.get("MINIMUM_PRIOR_SESSIONS", "20"))
    result = build_ml_backfill_e_phase10b_causality_audit(PROJECT_ROOT, run_id, minimum)
    print("ML Backfill E Phase 10B causality audit complete.")
    print(f"Unsafe modules: {len(result['module_audit'])}")
    print(f"Comparable sessions: {int(result['session_percentile_comparison']['causal_percentile_available'].sum())}")
    print(f"Next action: {result['next_action_recommendation']['next_action']}")
    print("Research-only: no strategy replay, model training, approval, or gate change.")


if __name__ == "__main__":
    main()
