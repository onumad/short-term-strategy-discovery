from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase7c import render_phase7c_report, run_phase7c_assumption_drift_audit  # noqa: E402


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    comparisons_path = output_dir / "phase7c_assumption_drift.csv"
    report_path = report_dir / "phase7c_assumption_drift_report.md"

    result = run_phase7c_assumption_drift_audit(PROJECT_ROOT)
    result.comparisons.to_csv(comparisons_path, index=False)
    report_path.write_text(render_phase7c_report(result, comparisons_path, report_path), encoding="utf-8")

    high_count = int((result.comparisons["severity"] == "high").sum()) if not result.comparisons.empty else 0
    print("Phase 7C MGC legacy assumption drift audit complete.")
    print(f"Comparisons: {comparisons_path}")
    print(f"Report: {report_path}")
    print(f"Rows: {len(result.comparisons)}; high-severity drift axes: {high_count}")
    print("Recommended next phase: bounded Phase 7D payout-path / matched-window diagnostic using existing deterministic trade logs.")


if __name__ == "__main__":
    main()
