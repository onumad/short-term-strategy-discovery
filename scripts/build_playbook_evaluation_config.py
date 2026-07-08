from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import prepare_experiment_run, write_experiment_manifest
from short_term_edge.playbook_evaluation import (
    RECOMMENDATION,
    build_labeling_rules,
    build_playbook_evaluation_config,
    build_reporting_guidelines,
    classify_existing_registry_rows,
    load_playbook_taxonomy,
    render_alignment_report,
    write_json,
)


def main() -> None:
    taxonomy = load_playbook_taxonomy(PROJECT_ROOT)
    registry_path = PROJECT_ROOT / "outputs" / "research_signal_registry.csv"
    registry = pd.read_csv(registry_path)
    classified_registry = classify_existing_registry_rows(registry)

    config = build_playbook_evaluation_config(taxonomy)
    labeling_rules = build_labeling_rules(taxonomy)
    reporting_guidelines = build_reporting_guidelines()

    outputs_dir = PROJECT_ROOT / "outputs"
    reports_dir = PROJECT_ROOT / "reports"
    outputs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    config_path = outputs_dir / "playbook_evaluation_config.json"
    labeling_path = outputs_dir / "playbook_labeling_rules.json"
    reporting_path = outputs_dir / "playbook_reporting_guidelines.json"
    recommendation_path = outputs_dir / "playbook_framework_c_next_action_recommendation.json"
    report_path = reports_dir / "playbook_framework_c_evaluation_alignment_report.md"

    write_json(config_path, config)
    write_json(labeling_path, labeling_rules)
    write_json(reporting_path, reporting_guidelines)
    write_json(recommendation_path, RECOMMENDATION)
    report = render_alignment_report(
        registry_rows=len(classified_registry),
        config=config,
        recommendation=RECOMMENDATION,
    )
    report_path.write_text(report, encoding="utf-8")

    run_id = os.environ.get("EXPERIMENT_RUN_ID", "playbook-framework-c")
    paths = prepare_experiment_run(PROJECT_ROOT, "playbook_framework_c", run_id)
    result_row = pd.DataFrame(
        [
            {
                "framework": "playbook_framework_c",
                "registry_rows_checked": len(classified_registry),
                "official_gates_changed": False,
                "paper_trading_approved": False,
                "next_action": RECOMMENDATION["next_action"],
            }
        ]
    )
    result_row.to_csv(paths.results_path, index=False)
    write_json(paths.specs_path, config)
    paths.report_path.write_text(report, encoding="utf-8")
    write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=paths,
        experiment_name="playbook_framework_c",
        command="./.venv/Scripts/python.exe scripts/build_playbook_evaluation_config.py",
        config={"source": "existing docs/config/registry outputs only"},
        selected_specs_count=0,
        results=result_row,
        legacy_artifacts={
            "playbook_evaluation_config": config_path,
            "playbook_labeling_rules": labeling_path,
            "playbook_reporting_guidelines": reporting_path,
            "next_action_recommendation": recommendation_path,
            "report": report_path,
        },
        guardrails=(
            "research/simulation only",
            "no new signals generated",
            "official gates unchanged",
            "paper trading not approved",
        ),
        data_files=(),
    )
    print(f"Wrote Playbook Framework C config: {config_path}")
    print(f"Wrote recommendation: {recommendation_path}")
    print(f"Wrote report: {report_path}")
    print(f"Wrote artifacts: {paths.run_dir}")


if __name__ == "__main__":
    main()
