from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.discovery import run_phase2
from short_term_edge.reporting import write_phase2_report


def main() -> int:
    result = run_phase2(PROJECT_ROOT)
    write_phase2_report(result, PROJECT_ROOT)
    ranked = result["ranked"]
    top = result["top"]
    paper = int((ranked["label"] == "paper_trade_candidate").sum())
    print(f"Tested {len(ranked)} strategy variants")
    print(f"Wrote {result['paths']['ranked']}")
    print(f"Wrote {result['paths']['top']}")
    print(f"Wrote {result['paths']['report']}")
    if not top.empty:
        print(f"Best Phase 3 candidate: {top.iloc[0]['candidate_id']}")
    print(f"Paper-trade candidates: {paper}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
