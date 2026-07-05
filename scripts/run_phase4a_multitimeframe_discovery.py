from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase4a import run_phase4a


def main() -> int:
    if os.environ.get("PHASE4A_SKIP_TESTS") != "1":
        print("Tier 1: running Phase 4A infrastructure tests")
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_phase4a"],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode

    print("Tier 2/3: running controlled Phase 4A family sweep")
    result = run_phase4a(PROJECT_ROOT)
    ranked = result["ranked"]
    top = result["top"]
    paper = int((ranked["label"] == "paper_trade_candidate").sum())
    print("Planned variants by family:")
    for _, row in result["variant_counts"].iterrows():
        print(f"  {row['strategy_family']}: {int(row['planned_variants'])}")
    print(f"Tested {len(ranked)} Phase 4A variants")
    print(f"Paper-trade candidates: {paper}")
    if not top.empty:
        best = top.iloc[0]
        print(f"Best ranked candidate: {best['candidate_id']} ({best['label']})")
        print(f"Best net PnL: ${best['net_pnl']:.2f}")
    print(f"Wrote {result['paths']['ranked']}")
    print(f"Wrote {result['paths']['top']}")
    print(f"Wrote {result['paths']['family_summary']}")
    print(f"Wrote {result['paths']['timeframe_summary']}")
    print(f"Wrote {result['paths']['report']}")
    print(f"Wrote trade logs under {result['paths']['trade_logs']}")
    print(f"Wrote charts under {result['paths']['charts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
