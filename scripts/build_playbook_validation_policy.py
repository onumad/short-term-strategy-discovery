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
from short_term_edge.playbook_validation_policy import (
    build_validation_framework_d_artifacts,
    write_json,
)

EXPERIMENT_NAME = "validation_framework_d"
RUN_ID = "validation-framework-d-r1"
RUN_COMMAND = "./.venv/Scripts/python.exe scripts/build_playbook_validation_policy.py"


def main() -> None:
    result = build_validation_framework_d_artifacts(PROJECT_ROOT)

    outputs_dir = PROJECT_ROOT / "outputs"
    reports_dir = PROJECT_ROOT / "reports"
    outputs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    policy_path = outputs_dir / "playbook_validation_policy.json"
    schema_path = outputs_dir / "playbook_fold_policy_schema.json"
    decision_table_path = outputs_dir / "validation_framework_d_fold_design_decision_table.csv"
    module_rules_path = outputs_dir / "validation_framework_d_module_fold_adequacy_rules.csv"
    playbook_rules_path = outputs_dir / "validation_framework_d_playbook_fold_reporting_rules.csv"
    recommendation_path = outputs_dir / "validation_framework_d_next_action_recommendation.json"
    report_path = reports_dir / "validation_framework_d_standardize_playbook_folds_report.md"

    write_json(policy_path, result["policy"])
    write_json(schema_path, result["schema"])
    result["decision_table"].to_csv(decision_table_path, index=False)
    result["module_rules"].to_csv(module_rules_path, index=False)
    result["playbook_rules"].to_csv(playbook_rules_path, index=False)
    write_json(recommendation_path, result["recommendation"])
    report_path.write_text(result["report"], encoding="utf-8")

    run_id = os.environ.get("EXPERIMENT_RUN_ID", RUN_ID)
    paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id)
    result_row = pd.DataFrame(
        [
            {
                "framework": EXPERIMENT_NAME,
                "standard_fold_views": len(result["policy"]["standard_fold_views"]),
                "validation_levels": len(result["policy"]["validation_levels"]),
                "official_gates_changed": False,
                "paper_trading_approved": False,
                "live_trading_approved": False,
                "new_strategy_signals_generated": False,
                "strategy_searches_run": False,
                "candidate_results_changed": False,
                "candidates_promoted": False,
                "next_action": result["recommendation"]["next_action"],
            }
        ]
    )
    result_row.to_csv(paths.results_path, index=False)
    write_json(paths.specs_path, result["policy"])
    paths.report_path.write_text(result["report"], encoding="utf-8")
    write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={"source": "existing Validation Framework Audit C and playbook framework artifacts only"},
        selected_specs_count=0,
        results=result_row,
        legacy_artifacts={
            "playbook_validation_policy": policy_path,
            "playbook_fold_policy_schema": schema_path,
            "fold_design_decision_table": decision_table_path,
            "module_fold_adequacy_rules": module_rules_path,
            "playbook_fold_reporting_rules": playbook_rules_path,
            "next_action_recommendation": recommendation_path,
            "report": report_path,
        },
        guardrails=(
            "research/simulation only",
            "no new signals generated",
            "no strategy searches run",
            "official gates unchanged",
            "paper trading not approved",
            "live trading not approved",
        ),
        data_files=(),
    )

    print(f"Wrote playbook validation policy: {policy_path}")
    print(f"Wrote fold policy schema: {schema_path}")
    print(f"Wrote fold design decision table: {decision_table_path}")
    print(f"Wrote module fold adequacy rules: {module_rules_path}")
    print(f"Wrote playbook fold reporting rules: {playbook_rules_path}")
    print(f"Wrote recommendation: {recommendation_path}")
    print(f"Wrote report: {report_path}")
    print(f"Wrote artifacts: {paths.run_dir}")


if __name__ == "__main__":
    main()
