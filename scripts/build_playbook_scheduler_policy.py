from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import prepare_experiment_run, write_experiment_manifest
from short_term_edge.playbook_scheduler_policy import (
    append_scheduler_f_objective_note,
    build_playbook_scheduler_f_artifacts,
    write_json,
)

EXPERIMENT_NAME = "playbook_scheduler_f"
RUN_ID = "playbook-scheduler-f-r1"
RUN_COMMAND = "./.venv/Scripts/python.exe scripts/build_playbook_scheduler_policy.py"


def main() -> None:
    result = build_playbook_scheduler_f_artifacts(PROJECT_ROOT)

    outputs_dir = PROJECT_ROOT / "outputs"
    reports_dir = PROJECT_ROOT / "reports"
    outputs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    policy_path = outputs_dir / "playbook_scheduler_policy.json"
    recommendation_path = outputs_dir / "playbook_scheduler_f_next_action_recommendation.json"
    report_path = reports_dir / "playbook_scheduler_f_rare_module_exclusion_policy_report.md"

    write_json(policy_path, result["policy"])
    write_json(recommendation_path, result["recommendation"])
    report_path.write_text(result["report"], encoding="utf-8")

    objective_path = PROJECT_ROOT / "playbook_research_objective.md"
    if objective_path.exists():
        existing_objective = objective_path.read_text(encoding="utf-8")
        updated_objective = append_scheduler_f_objective_note(existing_objective)
        if updated_objective != existing_objective:
            objective_path.write_text(updated_objective, encoding="utf-8")

    run_id = os.environ.get("EXPERIMENT_RUN_ID", RUN_ID)
    paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id)
    result["result_row"].to_csv(paths.results_path, index=False)
    write_json(paths.specs_path, result["policy"])
    paths.report_path.write_text(result["report"], encoding="utf-8")
    write_json(paths.run_dir / "playbook_scheduler_policy.json", result["policy"])
    write_json(paths.run_dir / "next_action_recommendation.json", result["recommendation"])
    result["rare_modules"].to_csv(paths.run_dir / "rare_modules_registry_only_excluded.csv", index=False)
    result["default_scheduler_universe"].to_csv(paths.run_dir / "recommended_default_scheduler_universe.csv", index=False)

    write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={"source": "existing Scheduler E, registry, and rare-module policy artifacts only"},
        selected_specs_count=0,
        results=result["result_row"],
        legacy_artifacts={
            "policy": policy_path,
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
            "rare modules excluded from default scheduler",
        ),
        data_files=(),
    )

    print(f"Wrote scheduler policy: {policy_path}")
    print(f"Wrote recommendation: {recommendation_path}")
    print(f"Wrote report: {report_path}")
    print(f"Wrote artifacts: {paths.run_dir}")


if __name__ == "__main__":
    main()
