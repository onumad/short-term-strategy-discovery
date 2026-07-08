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
from short_term_edge.playbook_rare_module_policy import (
    append_framework_e_report_note,
    build_playbook_framework_e_artifacts,
    write_json,
)

EXPERIMENT_NAME = "playbook_framework_e"
RUN_ID = "playbook-framework-e-r1"
RUN_COMMAND = "./.venv/Scripts/python.exe scripts/build_playbook_rare_module_policy_integration.py"


def main() -> None:
    result = build_playbook_framework_e_artifacts(PROJECT_ROOT)

    outputs_dir = PROJECT_ROOT / "outputs"
    reports_dir = PROJECT_ROOT / "reports"
    outputs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    policy_path = outputs_dir / "playbook_rare_module_policy.json"
    reporting_guidelines_path = outputs_dir / "playbook_rare_module_reporting_guidelines.json"
    portfolio_rules_path = outputs_dir / "playbook_rare_module_portfolio_audit_rules.json"
    schema_additions_path = outputs_dir / "playbook_rare_module_registry_schema_additions.json"
    recommendation_path = outputs_dir / "playbook_framework_e_next_action_recommendation.json"
    report_path = reports_dir / "playbook_framework_e_rare_module_policy_integration_report.md"

    write_json(policy_path, result["policy"])
    write_json(reporting_guidelines_path, result["reporting_guidelines"])
    write_json(portfolio_rules_path, result["portfolio_audit_rules"])
    write_json(schema_additions_path, result["registry_schema_additions"])
    write_json(recommendation_path, result["recommendation"])
    report_path.write_text(result["report"], encoding="utf-8")

    write_json(outputs_dir / "playbook_evaluation_config.json", result["updated_playbook_evaluation_config"])
    write_json(outputs_dir / "playbook_labeling_rules.json", result["updated_playbook_labeling_rules"])
    write_json(outputs_dir / "playbook_module_taxonomy.json", result["updated_playbook_module_taxonomy"])
    if result["updated_playbook_module_registry_schema"] is not None:
        write_json(outputs_dir / "playbook_module_registry_schema.json", result["updated_playbook_module_registry_schema"])

    for report_name in ["research_signal_registry_report.md", "playbook_module_registry_report.md"]:
        path = reports_dir / report_name
        if path.exists():
            path.write_text(append_framework_e_report_note(path.read_text(encoding="utf-8")), encoding="utf-8")

    objective_path = PROJECT_ROOT / "playbook_research_objective.md"
    if objective_path.exists():
        objective_path.write_text(append_framework_e_report_note(objective_path.read_text(encoding="utf-8")), encoding="utf-8")

    run_id = os.environ.get("EXPERIMENT_RUN_ID", RUN_ID)
    paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id)
    result_row = pd.DataFrame(
        [
            {
                "framework": EXPERIMENT_NAME,
                "phase16a_rare_modules_present_in_registry": result["policy"]["phase16a_registry_evidence_summary"]["phase16a_rare_modules_present_in_registry"],
                "official_gates_changed": False,
                "paper_trading_approved": False,
                "live_trading_approved": False,
                "new_strategy_signals_generated": False,
                "strategy_searches_run": False,
                "candidate_results_changed": False,
                "next_action": result["recommendation"]["next_action"],
            }
        ]
    )
    result_row.to_csv(paths.results_path, index=False)
    write_json(paths.specs_path, result["policy"])
    paths.report_path.write_text(result["report"], encoding="utf-8")
    write_json(paths.run_dir / "playbook_rare_module_reporting_guidelines.json", result["reporting_guidelines"])
    write_json(paths.run_dir / "playbook_rare_module_portfolio_audit_rules.json", result["portfolio_audit_rules"])
    write_json(paths.run_dir / "playbook_rare_module_registry_schema_additions.json", result["registry_schema_additions"])
    write_json(paths.run_dir / "next_action_recommendation.json", result["recommendation"])
    result["phase16a_rare_modules"].to_csv(paths.run_dir / "phase16a_rare_modules_in_registry.csv", index=False)

    write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={"source": "existing rare-module validation and registry artifacts only"},
        selected_specs_count=0,
        results=result_row,
        legacy_artifacts={
            "policy": policy_path,
            "reporting_guidelines": reporting_guidelines_path,
            "portfolio_audit_rules": portfolio_rules_path,
            "registry_schema_additions": schema_additions_path,
            "next_action_recommendation": recommendation_path,
            "report": report_path,
        },
        guardrails=(
            "research/simulation only",
            "no new signals generated",
            "no strategy searches run",
            "candidate results unchanged",
            "official gates unchanged",
            "paper trading not approved",
            "live trading not approved",
        ),
        data_files=(),
    )

    print(f"Wrote policy: {policy_path}")
    print(f"Wrote reporting guidelines: {reporting_guidelines_path}")
    print(f"Wrote portfolio audit rules: {portfolio_rules_path}")
    print(f"Wrote registry schema additions: {schema_additions_path}")
    print(f"Wrote recommendation: {recommendation_path}")
    print(f"Wrote report: {report_path}")
    print(f"Wrote artifacts: {paths.run_dir}")


if __name__ == "__main__":
    main()
