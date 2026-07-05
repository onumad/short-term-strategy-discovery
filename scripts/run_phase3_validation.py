from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase3 import PRIMARY_CANDIDATE_ID, run_phase3


def main() -> int:
    result = run_phase3(PROJECT_ROOT)
    diagnostics = result["diagnostics"]
    primary = diagnostics.loc[diagnostics["candidate_id"] == PRIMARY_CANDIDATE_ID].iloc[0]
    print(f"Validated {len(diagnostics)} frozen Phase 3 candidates")
    print(f"Primary candidate: {PRIMARY_CANDIDATE_ID}")
    print(f"Primary Phase 3 label: {primary['phase3_label']}")
    print(f"Primary net PnL: ${primary['net_pnl']:.2f}")
    print(f"Wrote {result['paths']['validation_report']}")
    print(f"Wrote {result['paths']['manual_plan']}")
    print(f"Wrote {result['paths']['diagnostics']}")
    print(f"Wrote {result['paths']['daily_pnl']}")
    print(f"Wrote {result['paths']['trade_review']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
