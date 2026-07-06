from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase6_synthesis import render_phase6_failure_synthesis  # noqa: E402


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    phase6a_path = output_dir / "phase6a_expansion_results.csv"
    phase6b_path = output_dir / "phase6b_ambiguity_reduction_results.csv"
    report_path = report_dir / "phase6_failure_synthesis_report.md"

    if not phase6a_path.exists():
        raise FileNotFoundError(f"Phase 6A results not found: {phase6a_path}")
    if not phase6b_path.exists():
        raise FileNotFoundError(f"Phase 6B results not found: {phase6b_path}")

    report_dir.mkdir(parents=True, exist_ok=True)
    phase6a_results = pd.read_csv(phase6a_path)
    phase6b_results = pd.read_csv(phase6b_path)
    report = render_phase6_failure_synthesis(phase6a_results, phase6b_results)
    report_path.write_text(report, encoding="utf-8")

    phase6a_count = phase6a_results["candidate_id"].nunique() if "candidate_id" in phase6a_results.columns else len(phase6a_results)
    phase6b_count = phase6b_results["candidate_id"].nunique() if "candidate_id" in phase6b_results.columns else len(phase6b_results)
    phase6b_labels = phase6b_results["phase6b_label"].value_counts().to_dict() if "phase6b_label" in phase6b_results.columns else {}
    print("Phase 6 failure synthesis complete.")
    print(f"Phase 6A candidates: {phase6a_count}")
    print(f"Phase 6B candidates: {phase6b_count}")
    print(f"Phase 6B label counts: {phase6b_labels}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
