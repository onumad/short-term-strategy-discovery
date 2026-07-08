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
from short_term_edge.rare_module_validation_track import (
    build_rare_module_validation_track_artifacts,
    write_json,
)

EXPERIMENT_NAME = "rare_module_validation_track"
RUN_ID = "rare-module-validation-track-r1"
RUN_COMMAND = "EXPERIMENT_RUN_ID=rare-module-validation-track-r1 ./.venv/Scripts/python.exe scripts/run_rare_module_validation_track_review.py"


def main() -> None:
    result = build_rare_module_validation_track_artifacts(PROJECT_ROOT)

    outputs_dir = PROJECT_ROOT / "outputs"
    reports_dir = PROJECT_ROOT / "reports"
    outputs_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)

    candidate_review_path = outputs_dir / "rare_module_validation_track_phase16a_candidates.csv"
    adequacy_summary_path = outputs_dir / "rare_module_validation_track_adequacy_summary.csv"
    registration_decisions_path = outputs_dir / "rare_module_validation_track_registration_decisions.csv"
    policy_path = outputs_dir / "rare_module_validation_track_policy.json"
    recommendation_path = outputs_dir / "rare_module_validation_track_next_action_recommendation.json"
    report_path = reports_dir / "rare_module_validation_track_review_report.md"

    result["candidate_review"].to_csv(candidate_review_path, index=False)
    result["adequacy_summary"].to_csv(adequacy_summary_path, index=False)
    result["registration_decisions"].to_csv(registration_decisions_path, index=False)
    write_json(policy_path, result["policy"])
    write_json(recommendation_path, result["recommendation"])
    report_path.write_text(result["report"], encoding="utf-8")

    run_id = os.environ.get("EXPERIMENT_RUN_ID", RUN_ID)
    paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id)
    result_row = pd.DataFrame(
        [
            {
                "framework": EXPERIMENT_NAME,
                "phase16a_candidates_reviewed": len(result["candidate_review"]),
                "positive_uncorrelated_candidates": int(
                    result["candidate_review"]["label"].eq("phase16a_positive_uncorrelated_research_signal").sum()
                ),
                "watchlist_rows_reviewed": int(
                    result["candidate_review"]["label"].eq("phase16a_watchlist_needs_more_history").sum()
                ),
                "rare_registration_candidates": int(
                    result["registration_decisions"]["registration_decision"].isin(
                        ["add_to_registry_as_rare_setup_diversifier", "add_to_registry_as_priority_for_more_data"]
                    ).sum()
                ),
                "official_gates_changed": False,
                "paper_trading_approved": False,
                "live_trading_approved": False,
                "new_strategy_signals_generated": False,
                "strategy_searches_run": False,
                "candidate_results_changed": False,
                "registries_mutated": False,
                "next_action": result["recommendation"]["next_action"],
            }
        ]
    )
    result_row.to_csv(paths.results_path, index=False)
    write_json(paths.specs_path, result["policy"])
    paths.report_path.write_text(result["report"], encoding="utf-8")
    result["candidate_review"].to_csv(paths.run_dir / "phase16a_candidates.csv", index=False)
    result["adequacy_summary"].to_csv(paths.run_dir / "adequacy_summary.csv", index=False)
    result["registration_decisions"].to_csv(paths.run_dir / "registration_decisions.csv", index=False)
    write_json(paths.run_dir / "next_action_recommendation.json", result["recommendation"])

    write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={"source": "existing Phase 16A and Validation Framework D artifacts only"},
        selected_specs_count=0,
        results=result_row,
        legacy_artifacts={
            "candidate_review": candidate_review_path,
            "adequacy_summary": adequacy_summary_path,
            "registration_decisions": registration_decisions_path,
            "policy": policy_path,
            "next_action_recommendation": recommendation_path,
            "report": report_path,
        },
        guardrails=(
            "research/simulation only",
            "no new signals generated",
            "no strategy searches run",
            "candidate results unchanged",
            "registries not mutated",
            "official gates unchanged",
            "paper trading not approved",
            "live trading not approved",
        ),
        data_files=(),
    )

    print(f"Wrote candidate review: {candidate_review_path}")
    print(f"Wrote adequacy summary: {adequacy_summary_path}")
    print(f"Wrote registration decisions: {registration_decisions_path}")
    print(f"Wrote policy: {policy_path}")
    print(f"Wrote recommendation: {recommendation_path}")
    print(f"Wrote report: {report_path}")
    print(f"Wrote artifacts: {paths.run_dir}")


if __name__ == "__main__":
    main()
