from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs"
REP = ROOT / "reports"
ART = ROOT / "artifacts" / "research_signal_registry" / "research-signal-registry-c"
ART.mkdir(parents=True, exist_ok=True)

PHASE_LABEL = "phase14a_positive_uncorrelated_research_signal"
RULE = "Short rejection from prior RTH midpoint after close-confirmed failure to hold above the level, filled at next bar open."
SOURCE_REPORT = "reports/phase14a_prior_level_reaction_scout_report.md"
REC_C = {
    "next_action": "portfolio_audit_c_with_phase14a_prior_level_modules",
    "rationale": "Phase 14A added positive uncorrelated prior-RTH midpoint reaction modules to the playbook registry; test whether they improve combined playbook stability.",
    "official_gates_changed": False,
    "paper_trading_approved": False,
}


def strict_dump(obj: object, path: Path) -> None:
    obj = sanitize_json(obj)
    text = json.dumps(obj, indent=2, sort_keys=False, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def sanitize_json(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(k): sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json(v) for v in obj]
    if pd.isna(obj):
        return None
    return obj


def replace_addendum(path: Path, marker: str, text: str) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in original:
        original = original.split(marker)[0].rstrip() + "\n"
    path.write_text(original.rstrip() + "\n" + text, encoding="utf-8")


def main() -> None:
    research_path = OUT / "research_signal_registry.csv"
    playbook_path = OUT / "playbook_module_registry.csv"
    phase_path = OUT / "phase14a_candidate_results.csv"

    research_before_raw = pd.read_csv(research_path)
    playbook_before_raw = pd.read_csv(playbook_path)
    phase = pd.read_csv(phase_path)
    positives = phase[phase["phase14a_label"].astype(str).eq(PHASE_LABEL)].sort_values("phase14a_rank").copy()
    if len(positives) != 2:
        raise SystemExit(f"Expected exactly 2 {PHASE_LABEL} rows, found {len(positives)}")

    # Idempotency: replace only prior Phase 14A rows, preserving all existing rows unchanged.
    research_base = research_before_raw[~research_before_raw["phase"].astype(str).eq("phase14a")].copy()
    playbook_base = playbook_before_raw[~playbook_before_raw["phase"].astype(str).eq("phase14a")].copy()
    research_rows_before = len(research_base)
    playbook_rows_before = len(playbook_base)

    research_new: list[dict[str, object]] = []
    playbook_new: list[dict[str, object]] = []
    for _, r in positives.iterrows():
        candidate_id = str(r["candidate_id"])
        research_new.append(
            {
                "phase": "phase14a",
                "candidate_id": candidate_id,
                "family": "prior_level_reaction",
                "plain_english_rule": RULE,
                "net_pnl": float(r["net_pnl"]),
                "stress_pnl": float(r["stress_pnl"]),
                "validation_pnl": float(r["validation_pnl"]),
                "holdout_pnl": float(r["holdout_pnl"]),
                "walk_forward_stress_pnl": float(r["walk_forward_stress_pnl"]),
                "positive_wf_test_folds_pct": float(r["positive_wf_test_folds_pct"]),
                "trades": int(r["trades"]),
                "active_days": int(r["active_days"]),
                "best_day_concentration": float(r["best_day_concentration"]),
                "best_trade_concentration": float(r["best_trade_concentration"]),
                "bootstrap_or_null_classification": PHASE_LABEL,
                "signal_evidence_status": "positive_research_signal",
                "tradability_status": "not_tradable_concentrated",
                "research_track": "parked_research_signal",
                "revisit_condition": "Revisit through Portfolio Audit C to test whether this uncorrelated prior-level reaction module improves combined playbook stability; no paper trading unless unchanged official gates pass.",
                "source_report": SOURCE_REPORT,
            }
        )
        playbook_new.append(
            {
                "module_id": candidate_id,
                "phase": "phase14a",
                "candidate_id": candidate_id,
                "source_family": "prior_level_reaction",
                "market_condition": "prior_level_interaction",
                "module_family": "prior_level_reaction",
                "portfolio_role": "diversifier_module",
                "plain_english_rule": RULE,
                "signal_evidence_status": "positive_research_signal",
                "tradability_status": "not_tradable_concentrated",
                "research_track": "parked_research_signal",
                "portfolio_contribution_status": "not_evaluated_until_portfolio_audit_c",
                "official_gates_passed": False,
                "paper_trading_approved": False,
                "net_pnl": float(r["net_pnl"]),
                "stress_pnl": float(r["stress_pnl"]),
                "validation_pnl": float(r["validation_pnl"]),
                "holdout_pnl": float(r["holdout_pnl"]),
                "walk_forward_stress_pnl": float(r["walk_forward_stress_pnl"]),
                "positive_wf_test_folds_pct": float(r["positive_wf_test_folds_pct"]),
                "trades": int(r["trades"]),
                "active_days": int(r["active_days"]),
                "best_day_concentration": float(r["best_day_concentration"]),
                "best_trade_concentration": float(r["best_trade_concentration"]),
                "average_correlation_to_registry": float(r["average_correlation_to_registry"]),
                "max_correlation_to_registry": float(r["max_correlation_to_registry"]),
                "average_correlation_to_portfolio_audit": float(r["average_correlation_to_playbook"]),
                "max_correlation_to_portfolio_audit": float(r["max_correlation_to_playbook"]),
                "level_source": str(r["traded_level_source"]),
                "source_window": "prior_rth_session",
                "trade_window": f"{r['trade_start']}-{r['trade_end']}",
                "source_report": SOURCE_REPORT,
            }
        )

    research = pd.concat([research_base, pd.DataFrame(research_new)], ignore_index=True)
    playbook = pd.concat([playbook_base, pd.DataFrame(playbook_new)], ignore_index=True)
    research = research[list(research_before_raw.columns)]
    playbook = playbook[list(playbook_before_raw.columns)]

    research.to_csv(research_path, index=False)
    playbook.to_csv(playbook_path, index=False)
    strict_dump(research.to_dict(orient="records"), OUT / "research_signal_registry.json")
    strict_dump(playbook.to_dict(orient="records"), OUT / "playbook_module_registry.json")
    strict_dump(REC_C, OUT / "research_signal_registry_c_next_action_recommendation.json")

    rec_main = dict(REC_C)
    rec_main["registry_counts"] = {str(k): int(v) for k, v in research["research_track"].value_counts().sort_index().items()}
    rec_main["phase14a_rows_added"] = int(len(positives))
    rec_main["research_signal_registry_c_recommendation"] = "outputs/research_signal_registry_c_next_action_recommendation.json"
    strict_dump(rec_main, OUT / "research_signal_registry_next_action_recommendation.json")

    table_rows = []
    for _, r in positives.iterrows():
        table_rows.append(
            f"| {int(r['phase14a_rank'])} | `{r['candidate_id']}` | diversifier_module | "
            f"{float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | "
            f"{float(r['holdout_pnl']):.2f} | {float(r['walk_forward_stress_pnl']):.2f} | "
            f"{float(r['average_correlation_to_registry']):.3f} | {float(r['max_correlation_to_registry']):.3f} |"
        )
    update_report = f"""# Research Signal Registry C - Phase 14A Update

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

This additive update adds accepted Phase 14A positive uncorrelated prior-level reaction research signals to the research signal registry and playbook module registry for Portfolio Audit C. It does not generate new signals, rerun Phase 14A, change candidate results, change official promotion gates, promote candidates, or approve paper trading.

## Inputs Used

- outputs/research_signal_registry.csv / .json
- outputs/playbook_module_registry.csv / .json
- outputs/playbook_module_registry_schema.json
- outputs/playbook_module_taxonomy.json
- outputs/phase14a_candidate_results.csv
- outputs/phase14a_correlation_to_registry.csv
- outputs/phase14a_correlation_to_playbook.csv
- outputs/phase14a_gap_coverage_summary.csv
- outputs/phase14a_next_action_recommendation.json
- reports/phase14a_prior_level_reaction_scout_report.md

## Phase 14A Rows Added

- Rows added: `{len(positives)}`
- Research signal registry rows before/after: `{research_rows_before}` -> `{len(research)}`
- Playbook module registry rows before/after: `{playbook_rows_before}` -> `{len(playbook)}`
- Classification applied to both rows: `positive_research_signal`, `not_tradable_concentrated`, `parked_research_signal`, `prior_level_interaction`, `prior_level_reaction`, `diversifier_module`.
- Plain-English rule: {RULE}
- Paper trading approved: `false`.
- Official gates passed: `false`.

| Rank | Candidate | Portfolio role | Net | Stress | Validation | Holdout | WF stress | Avg registry corr | Max registry corr |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(table_rows)}

## Watchlist Label Hygiene

Phase 14A rows labeled `phase14a_watchlist_needs_more_history` were not added to the registry and were not treated as review, watchlist, or paper-approved modules. Under the requested hygiene rule, Phase 14A watchlist rows require positive stress, validation, holdout, and walk-forward stress PnL before being treated as true watchlist modules; no such rows were promoted or approved here.

## Recommendation

- Next action: `{REC_C['next_action']}`
- Rationale: {REC_C['rationale']}
- Official gates changed: `false`
- Paper trading approved: `false`
"""
    (REP / "research_signal_registry_c_phase14a_update_report.md").write_text(update_report, encoding="utf-8")

    research_addendum = f"""
## Registry C - Phase 14A Addendum

Phase 14A added 2 positive uncorrelated prior-level reaction research signals for Portfolio Audit C. Both are positive research signals but remain `not_tradable_concentrated`, `parked_research_signal`, with `portfolio_role=diversifier_module`, `market_condition=prior_level_interaction`, `module_family=prior_level_reaction`, `paper_trading_approved=false`, and `official_gates_passed=false`.

Watchlist hygiene: Phase 14A `phase14a_watchlist_needs_more_history` rows were not treated as review/paper-approved modules.

Next action: `{REC_C['next_action']}`.
"""
    replace_addendum(REP / "research_signal_registry_report.md", "## Registry C - Phase 14A Addendum", research_addendum)

    module_lines = []
    for _, r in positives.iterrows():
        module_lines.append(
            f"| `{r['candidate_id']}` | prior_level_interaction | prior_level_reaction | diversifier_module | positive_research_signal | not_tradable_concentrated | false | false |"
        )
    playbook_report = f"""# Playbook Module Registry - Phase 14A Addendum

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Purpose

This registry maps parked research signals into playbook module fields for Portfolio Audit C. It preserves official gates and paper-trading blocks.

## Counts

- Total module rows: `{len(playbook)}`
- Phase 14A rows: `{len(positives)}`
- Phase 14A diversifier modules: `{len(positives)}`

## Phase 14A Modules

| Module | Market condition | Family | Portfolio role | Evidence | Tradability | Official gates | Paper trading |
| --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(module_lines)}

## Watchlist Label Hygiene

No Phase 14A `phase14a_watchlist_needs_more_history` row is marked review, paper-approved, or included as a true watchlist module in this update.

## Next Action

`{REC_C['next_action']}` - {REC_C['rationale']}
"""
    (REP / "playbook_module_registry_report.md").write_text(playbook_report, encoding="utf-8")

    artifact_map = {
        "research_signal_registry.csv": research_path,
        "research_signal_registry.json": OUT / "research_signal_registry.json",
        "research_signal_registry_next_action_recommendation.json": OUT / "research_signal_registry_next_action_recommendation.json",
        "research_signal_registry_c_next_action_recommendation.json": OUT / "research_signal_registry_c_next_action_recommendation.json",
        "research_signal_registry_report.md": REP / "research_signal_registry_report.md",
        "research_signal_registry_c_phase14a_update_report.md": REP / "research_signal_registry_c_phase14a_update_report.md",
        "playbook_module_registry.csv": playbook_path,
        "playbook_module_registry.json": OUT / "playbook_module_registry.json",
        "playbook_module_registry_report.md": REP / "playbook_module_registry_report.md",
        "playbook_module_registry_schema.json": OUT / "playbook_module_registry_schema.json",
        "playbook_module_taxonomy.json": OUT / "playbook_module_taxonomy.json",
    }
    for name, src in artifact_map.items():
        (ART / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = {
        "run_id": "research-signal-registry-c",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_phase14a_positive_label": PHASE_LABEL,
        "phase14a_rows_added": int(len(positives)),
        "research_registry_rows_before": int(research_rows_before),
        "research_registry_rows_after": int(len(research)),
        "playbook_module_registry_rows_before": int(playbook_rows_before),
        "playbook_module_registry_rows_after": int(len(playbook)),
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "phase14a_not_rerun": True,
        "watchlist_rows_not_promoted": True,
        "artifact_files": sorted(artifact_map),
    }
    strict_dump(manifest, ART / "manifest.json")

    print(f"Added {len(positives)} Phase 14A rows")
    print(f"Research registry rows: {research_rows_before} -> {len(research)}")
    print(f"Playbook module registry rows: {playbook_rows_before} -> {len(playbook)}")
    print(f"Artifact dir: {ART}")


if __name__ == "__main__":
    main()
