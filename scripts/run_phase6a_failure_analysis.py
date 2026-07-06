from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase6a_analysis import render_failure_analysis_report, summarize_failure_modes  # noqa: E402


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    results_path = output_dir / "phase6a_expansion_results.csv"
    failure_modes_path = output_dir / "phase6a_failure_modes.csv"
    report_path = report_dir / "phase6a_failure_analysis_report.md"

    if not results_path.exists():
        raise FileNotFoundError(f"Phase 6A results not found: {results_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    results = pd.read_csv(results_path)
    failure_modes = summarize_failure_modes(results)
    failure_modes.to_csv(failure_modes_path)
    report_path.write_text(render_failure_analysis_report(results, failure_modes), encoding="utf-8")

    label_counts = results["phase6a_label"].value_counts().to_dict() if "phase6a_label" in results.columns else {}
    print("Phase 6A failure-mode analysis complete.")
    print(f"Analyzed candidates: {results['candidate_id'].nunique() if 'candidate_id' in results.columns else len(results)}")
    print(f"Label counts: {label_counts}")
    print(f"Failure modes: {failure_modes_path}")
    print(f"Report: {report_path}")
    if not failure_modes.empty:
        top = failure_modes.iloc[0]
        print(f"Top failure mode: {failure_modes.index[0]} ({int(top['count'])})")


if __name__ == "__main__":
    main()
