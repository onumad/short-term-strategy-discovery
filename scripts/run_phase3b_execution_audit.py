from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase3b import run_phase3b


def main() -> int:
    result = run_phase3b(PROJECT_ROOT)
    summary = result["overlap_summary"]
    metrics = result["mode_metrics"]
    no_overlap = metrics.loc[metrics["mode"] == "B_one_open_position"].iloc[0]
    print(f"Overlap pairs: {summary['overlapping_trade_pairs']}")
    print(f"Max simultaneous baseline exposure: {summary['max_simultaneous_exposure']} MNQ")
    print(f"No-overlap label: {no_overlap['phase3b_label']}")
    print(f"No-overlap net PnL: ${no_overlap['net_pnl']:.2f}")
    print(f"Wrote {result['paths']['execution_report']}")
    print(f"Wrote {result['paths']['updated_plan']}")
    print(f"Wrote {result['paths']['execution_modes']}")
    print(f"Wrote {result['paths']['overlap_audit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
