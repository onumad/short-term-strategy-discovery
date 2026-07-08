from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs"
REP = ROOT / "reports"
ART = ROOT / "artifacts" / "research_signal_registry" / "research-signal-registry-d"
ART.mkdir(parents=True, exist_ok=True)

PHASE = "phase15a"
PHASE_LABEL = "phase15a_positive_uncorrelated_research_signal"
SOURCE_REPORT = "reports/phase15a_trend_power_continuation_scout_report.md"
REC_D = {
    "next_action": "portfolio_audit_d_with_phase15a_trend_power_modules",
    "rationale": "Phase 15A added positive uncorrelated trend/power continuation modules to the playbook registry; test whether they improve combined playbook stability despite limited target-gap coverage.",
    "official_gates_changed": False,
    "paper_trading_approved": False,
}

MARKET_CONDITION = {
    "trend_day_late_pullback_continuation": "trend_day",
    "power_hour_continuation": "power_hour_expansion",
    "low_volatility_late_expansion": "low_volatility_day",
}
MODULE_FAMILY = {
    "trend_day_late_pullback_continuation": "trend_continuation",
    "power_hour_continuation": "trend_continuation",
    "low_volatility_late_expansion": "range_expansion",
}
RULES = {
    "trend_day_late_pullback_continuation": "On a qualified morning trend day, short the late-session EMA20 pullback resume after close confirmation, filled at next bar open.",
    "power_hour_continuation": "On a qualified power-hour continuation day, trade the late range continuation after close confirmation, filled at next bar open.",
    "low_volatility_late_expansion": "On a qualified low-volatility day, trade the late range expansion after close confirmation, filled at next bar open.",
}
GAP_CAVEAT = "Phase 15A positive candidates had incremental_gap_days_covered = 0; record them as uncorrelated diversifier modules, not confirmed gap-filling modules."


def sanitize_json(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(k): sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json(v) for v in obj]
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return obj


def strict_dump(obj: object, path: Path) -> None:
    text = json.dumps(sanitize_json(obj), indent=2, sort_keys=False, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")


def replace_addendum(path: Path, marker: str, text: str) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in original:
        original = original.split(marker)[0].rstrip() + "\n"
    path.write_text(original.rstrip() + "\n" + text, encoding="utf-8")


def bool_false(_: object = None) -> bool:
    return False


def main() -> None:
    research_path = OUT / "research_signal_registry.csv"
    playbook_path = OUT / "playbook_module_registry.csv"
    phase_path = OUT / "phase15a_candidate_results.csv"

    research_before_raw = pd.read_csv(research_path)
    playbook_before_raw = pd.read_csv(playbook_path)
    phase = pd.read_csv(phase_path)
    positives = phase[phase["phase15a_label"].astype(str).eq(PHASE_LABEL)].sort_values("phase15a_rank").copy()
    if len(positives) != 3:
        raise SystemExit(f"Expected exactly 3 {PHASE_LABEL} rows, found {len(positives)}")
    if int(positives.iloc[0]["phase15a_rank"]) != 1:
        raise SystemExit("Top Phase 15A candidate is not included in positive uncorrelated rows")
    if positives["incremental_gap_days_covered"].astype(float).sum() != 0:
        raise SystemExit("Expected Phase 15A positives to have zero incremental gap coverage")

    # Idempotency: replace only prior Phase 15A rows, preserving all other rows unchanged.
    research_base = research_before_raw[~research_before_raw["phase"].astype(str).eq(PHASE)].copy()
    playbook_base = playbook_before_raw[~playbook_before_raw["phase"].astype(str).eq(PHASE)].copy()
    research_rows_before = len(research_base)
    playbook_rows_before = len(playbook_base)

    research_new: list[dict[str, object]] = []
    playbook_new: list[dict[str, object]] = []
    for _, r in positives.iterrows():
        candidate_id = str(r["candidate_id"])
        source_family = str(r["module_family"])
        market_condition = MARKET_CONDITION[source_family]
        module_family = MODULE_FAMILY[source_family]
        rule = RULES[source_family]
        tradability = "not_tradable_low_activity"
        research_new.append(
            {
                "phase": PHASE,
                "candidate_id": candidate_id,
                "family": source_family,
                "plain_english_rule": rule,
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
                "tradability_status": tradability,
                "research_track": "rare_setup_research_signal",
                "revisit_condition": "Revisit through Portfolio Audit D to test whether this uncorrelated trend/power continuation diversifier improves combined playbook stability; not a confirmed gap-filling module because incremental gap coverage was zero; no paper trading unless unchanged official gates pass.",
                "source_report": SOURCE_REPORT,
            }
        )
        playbook_new.append(
            {
                "module_id": candidate_id,
                "phase": PHASE,
                "candidate_id": candidate_id,
                "source_family": source_family,
                "market_condition": market_condition,
                "module_family": module_family,
                "portfolio_role": "diversifier_module",
                "plain_english_rule": rule,
                "signal_evidence_status": "positive_research_signal",
                "tradability_status": tradability,
                "research_track": "rare_setup_research_signal",
                "portfolio_contribution_status": "not_evaluated_until_portfolio_audit_d_uncorrelated_not_confirmed_gap_filler",
                "official_gates_passed": bool_false(),
                "paper_trading_approved": bool_false(),
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
                "level_source": str(r["trigger_model"]),
                "source_window": f"{r['build_start']}-{r['build_end']}",
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
    strict_dump(REC_D, OUT / "research_signal_registry_d_next_action_recommendation.json")

    rec_main = dict(REC_D)
    rec_main["registry_counts"] = {str(k): int(v) for k, v in research["research_track"].value_counts().sort_index().items()}
    rec_main["phase15a_rows_added"] = int(len(positives))
    rec_main["gap_coverage_caveat"] = GAP_CAVEAT
    rec_main["research_signal_registry_d_recommendation"] = "outputs/research_signal_registry_d_next_action_recommendation.json"
    strict_dump(rec_main, OUT / "research_signal_registry_next_action_recommendation.json")

    table_rows = []
    module_lines = []
    for _, r in positives.iterrows():
        source_family = str(r["module_family"])
        table_rows.append(
            f"| {int(r['phase15a_rank'])} | `{r['candidate_id']}` | {source_family} | {MARKET_CONDITION[source_family]} | {MODULE_FAMILY[source_family]} | diversifier_module | "
            f"{float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | "
            f"{float(r['holdout_pnl']):.2f} | {float(r['walk_forward_stress_pnl']):.2f} | "
            f"{float(r['average_correlation_to_registry']):.3f} | {int(r['incremental_gap_days_covered'])} |"
        )
        module_lines.append(
            f"| `{r['candidate_id']}` | {MARKET_CONDITION[source_family]} | {MODULE_FAMILY[source_family]} | diversifier_module | positive_research_signal | not_tradable_low_activity | false | false | {int(r['incremental_gap_days_covered'])} |"
        )

    update_report = f"""# Research Signal Registry D - Phase 15A Update

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

This additive update adds accepted Phase 15A positive uncorrelated trend/power continuation research signals to the research signal registry and playbook module registry for Portfolio Audit D. It does not generate new signals, rerun Phase 15A, change candidate results, change official promotion gates, promote candidates, or approve paper trading.

## Inputs Used

- outputs/research_signal_registry.csv / .json
- outputs/playbook_module_registry.csv / .json
- outputs/playbook_module_registry_schema.json
- outputs/playbook_module_taxonomy.json
- outputs/phase15a_candidate_results.csv
- outputs/phase15a_correlation_to_registry.csv
- outputs/phase15a_correlation_to_playbook.csv
- outputs/phase15a_gap_coverage_summary.csv
- outputs/phase15a_next_action_recommendation.json
- reports/phase15a_trend_power_continuation_scout_report.md

## Phase 15A Rows Added

- Rows added: `{len(positives)}`
- Research signal registry rows before/after: `{research_rows_before}` -> `{len(research)}`
- Playbook module registry rows before/after: `{playbook_rows_before}` -> `{len(playbook)}`
- Classification applied: `positive_research_signal`, `not_tradable_low_activity`, `rare_setup_research_signal`, `diversifier_module`.
- Paper trading approved: `false`.
- Official gates passed: `false`.
- Top Phase 15A candidate included: `{positives.iloc[0]['candidate_id']}`.

| Rank | Candidate | Source family | Market condition | Module family | Portfolio role | Net | Stress | Validation | Holdout | WF stress | Avg registry corr | Incremental gap days |
| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(table_rows)}

## Gap-Coverage Caveat

{GAP_CAVEAT}

## Recommendation

- Next action: `{REC_D['next_action']}`
- Rationale: {REC_D['rationale']}
- Official gates changed: `false`
- Paper trading approved: `false`
"""
    (REP / "research_signal_registry_d_phase15a_update_report.md").write_text(update_report, encoding="utf-8")

    research_addendum = f"""
## Registry D - Phase 15A Addendum

Phase 15A added 3 positive uncorrelated trend/power continuation research signals for Portfolio Audit D. All are positive research signals but remain `not_tradable_low_activity`, `rare_setup_research_signal`, with `portfolio_role=diversifier_module`, `paper_trading_approved=false`, and `official_gates_passed=false`.

Gap-coverage caveat: {GAP_CAVEAT}

Next action: `{REC_D['next_action']}`.
"""
    replace_addendum(REP / "research_signal_registry_report.md", "## Registry D - Phase 15A Addendum", research_addendum)

    playbook_report = f"""# Playbook Module Registry - Phase 15A Addendum

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Purpose

This registry maps positive uncorrelated Phase 15A trend/power continuation research signals into playbook module fields for Portfolio Audit D. It preserves official gates and paper-trading blocks.

## Counts

- Total module rows: `{len(playbook)}`
- Phase 15A rows: `{len(positives)}`
- Phase 15A diversifier modules: `{len(positives)}`

## Phase 15A Modules

| Module | Market condition | Family | Portfolio role | Evidence | Tradability | Official gates | Paper trading | Incremental gap days |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |
{chr(10).join(module_lines)}

## Gap-Coverage Caveat

{GAP_CAVEAT}

## Next Action

`{REC_D['next_action']}` - {REC_D['rationale']}
"""
    (REP / "playbook_module_registry_report.md").write_text(playbook_report, encoding="utf-8")

    artifact_map = {
        "research_signal_registry.csv": research_path,
        "research_signal_registry.json": OUT / "research_signal_registry.json",
        "research_signal_registry_next_action_recommendation.json": OUT / "research_signal_registry_next_action_recommendation.json",
        "research_signal_registry_d_next_action_recommendation.json": OUT / "research_signal_registry_d_next_action_recommendation.json",
        "research_signal_registry_report.md": REP / "research_signal_registry_report.md",
        "research_signal_registry_d_phase15a_update_report.md": REP / "research_signal_registry_d_phase15a_update_report.md",
        "playbook_module_registry.csv": playbook_path,
        "playbook_module_registry.json": OUT / "playbook_module_registry.json",
        "playbook_module_registry_report.md": REP / "playbook_module_registry_report.md",
        "playbook_module_registry_schema.json": OUT / "playbook_module_registry_schema.json",
        "playbook_module_taxonomy.json": OUT / "playbook_module_taxonomy.json",
        "apply_registry_d_update.py": ART / "apply_registry_d_update.py",
    }
    for name, src in artifact_map.items():
        (ART / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = {
        "run_id": "research-signal-registry-d",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_phase15a_positive_label": PHASE_LABEL,
        "phase15a_rows_added": int(len(positives)),
        "research_registry_rows_before": int(research_rows_before),
        "research_registry_rows_after": int(len(research)),
        "playbook_module_registry_rows_before": int(playbook_rows_before),
        "playbook_module_registry_rows_after": int(len(playbook)),
        "top_phase15a_candidate_included": str(positives.iloc[0]["candidate_id"]),
        "gap_coverage_caveat": GAP_CAVEAT,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "phase15a_not_rerun": True,
        "artifact_files": sorted(artifact_map),
    }
    strict_dump(manifest, ART / "manifest.json")

    print(f"Added {len(positives)} Phase 15A rows")
    print(f"Research registry rows: {research_rows_before} -> {len(research)}")
    print(f"Playbook module registry rows: {playbook_rows_before} -> {len(playbook)}")
    print(f"Artifact dir: {ART}")


if __name__ == "__main__":
    main()
