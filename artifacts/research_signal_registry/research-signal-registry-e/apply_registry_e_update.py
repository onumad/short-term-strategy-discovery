from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs"
REP = ROOT / "reports"
ART = ROOT / "artifacts" / "research_signal_registry" / "research-signal-registry-e"
ART.mkdir(parents=True, exist_ok=True)

PHASE = "phase16a"
SOURCE_REPORT = "reports/phase16a_high_vol_mixed_regime_scout_report.md"
DECISION_TO_ADD = "add_to_registry_as_rare_setup_diversifier"
REC_E = {
    "next_action": "playbook_framework_e_rare_module_policy_integration",
    "rationale": "Phase 16A rare high-vol mixed modules were added as rare setup diversifiers; integrate rare-module policy into future playbook evaluation before Portfolio Audit E.",
    "official_gates_changed": False,
    "paper_trading_approved": False,
    "rare_module_track_enabled": True,
}

MARKET_CONDITION = {
    "high_vol_mixed_late_resolution_breakout": "high_volatility_day",
    "high_vol_mixed_midpoint_reclaim": "high_volatility_day",
    "high_vol_mixed_extreme_fade": "high_volatility_day",
}
MODULE_FAMILY = {
    "high_vol_mixed_late_resolution_breakout": "range_expansion",
    "high_vol_mixed_midpoint_reclaim": "range_reversion",
    "high_vol_mixed_extreme_fade": "sweep_reversal",
}
TOP_RULE = "On a broad high-volatility mixed morning, buy the late lunch-range breakout after close confirmation, filled at the next bar open."
CAVEAT = (
    "Phase 16A rare modules are low-activity and fold adequacy is not fully interpretable. "
    "They are accepted only as rare setup diversifier research modules, not as watchlist, "
    "paper-review, or paper-trading candidates."
)
WATCHLIST_NOTE = (
    "Phase 16A watchlist labels are not registry watchlist/review approval; all five "
    "watchlist-labeled rows from the Rare Module Validation Track remain excluded, are not "
    "review_packet_candidate, and are not paper-approved."
)


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


def plain_rule(row: pd.Series) -> str:
    source_family = str(row["module_family"])
    regime = str(row["regime_variant"]).replace("_", " ")
    confirmation = str(row["confirmation_model"])
    exit_variant = str(row["exit_variant"])
    side = "buy" if str(row["side"]) == "long" else "sell"
    if (
        source_family == "high_vol_mixed_late_resolution_breakout"
        and str(row["regime_variant"]) == "broad_high_vol_mixed"
        and confirmation == "close_confirm_fill_next_open"
        and exit_variant == "structure_target_time_exit"
    ):
        return TOP_RULE
    if source_family == "high_vol_mixed_late_resolution_breakout":
        setup = "late lunch-range breakout"
    elif source_family == "high_vol_mixed_midpoint_reclaim":
        setup = "midpoint reclaim"
    else:
        setup = "high-volatility extreme fade"
    confirm = "close confirmation" if confirmation == "close_confirm_fill_next_open" else "two-bar confirmation"
    return f"On a {regime} morning, {side} the {setup} after {confirm}, filled at the next bar open."


def main() -> None:
    research_path = OUT / "research_signal_registry.csv"
    playbook_path = OUT / "playbook_module_registry.csv"
    phase_path = OUT / "phase16a_candidate_results.csv"
    review_path = OUT / "rare_module_validation_track_phase16a_candidates.csv"
    decisions_path = OUT / "rare_module_validation_track_registration_decisions.csv"

    research_before_raw = pd.read_csv(research_path)
    playbook_before_raw = pd.read_csv(playbook_path)
    phase = pd.read_csv(phase_path)
    review = pd.read_csv(review_path)
    decisions = pd.read_csv(decisions_path)

    add_decisions = decisions[decisions["registration_decision"].astype(str).eq(DECISION_TO_ADD)].copy()
    if len(add_decisions) != 3:
        raise SystemExit(f"Expected exactly 3 Phase 16A add decisions, found {len(add_decisions)}")
    if add_decisions["label"].astype(str).str.contains("watchlist", case=False, na=False).any():
        raise SystemExit("Rare Module Validation Track add decisions include a watchlist-labeled row")
    if not add_decisions["watchlist_hygiene_status"].astype(str).eq("not_watchlist_label").all():
        raise SystemExit("Add decisions must be not_watchlist_label only")

    watchlist_review = review[review["label"].astype(str).eq("phase16a_watchlist_needs_more_history")].copy()
    if len(watchlist_review) != 5:
        raise SystemExit(f"Expected exactly 5 Phase 16A watchlist rows in rare-module review, found {len(watchlist_review)}")
    if watchlist_review["registration_decision"].astype(str).ne("reject_from_registry").any():
        raise SystemExit("All Phase 16A review watchlist rows must be rejected from registry")
    if watchlist_review["tradability_status"].astype(str).eq("review_packet_candidate").any():
        raise SystemExit("A Phase 16A watchlist row was marked review_packet_candidate")
    watchlist_ids = set(watchlist_review["candidate_id"].astype(str))

    add_ids = list(add_decisions["candidate_id"].astype(str))
    add = phase[phase["candidate_id"].astype(str).isin(add_ids)].copy()
    if len(add) != 3:
        raise SystemExit("Could not locate exactly 3 Phase 16A add rows in phase candidate results")
    add["_order"] = add["candidate_id"].astype(str).map({cid: idx for idx, cid in enumerate(add_ids)})
    add = add.sort_values(["phase16a_rank", "_order"]).drop(columns=["_order"])
    if set(add["candidate_id"].astype(str)).intersection(watchlist_ids):
        raise SystemExit("A rare-module-review watchlist row would be added to registry")
    if add["paper_trading_approved"].astype(bool).any():
        raise SystemExit("A Phase 16A add row has paper_trading_approved true")
    if add["official_gates_passed"].astype(bool).any():
        raise SystemExit("A Phase 16A add row has official_gates_passed true")

    decision_by_id = add_decisions.set_index("candidate_id")
    for cid in add["candidate_id"].astype(str):
        d = decision_by_id.loc[cid]
        if str(d["signal_evidence_status"]) != "positive_research_signal":
            raise SystemExit(f"Unexpected signal evidence for {cid}")
        if str(d["tradability_status"]) != "not_tradable_low_activity":
            raise SystemExit(f"Unexpected tradability for {cid}")
        if str(d["recommended_research_track"]) != "rare_setup_research_signal":
            raise SystemExit(f"Unexpected research track for {cid}")
        if str(d["recommended_portfolio_role"]) != "diversifier_module":
            raise SystemExit(f"Unexpected portfolio role for {cid}")
        if str(d["fold_adequacy_status"]) != "low_activity_not_fully_interpretable":
            raise SystemExit(f"Unexpected fold adequacy status for {cid}")

    # Idempotency: replace only prior Phase 16A rows, preserving all other rows unchanged.
    research_base = research_before_raw[~research_before_raw["phase"].astype(str).eq(PHASE)].copy()
    playbook_base = playbook_before_raw[~playbook_before_raw["phase"].astype(str).eq(PHASE)].copy()
    research_rows_before = len(research_base)
    playbook_rows_before = len(playbook_base)

    research_new: list[dict[str, object]] = []
    playbook_new: list[dict[str, object]] = []
    for _, r in add.iterrows():
        candidate_id = str(r["candidate_id"])
        source_family = str(r["module_family"])
        if source_family not in MARKET_CONDITION:
            raise SystemExit(f"Missing market condition mapping for {source_family}")
        rule = plain_rule(r)
        fold_status = str(decision_by_id.loc[candidate_id]["fold_adequacy_status"])
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
                "bootstrap_or_null_classification": "phase16a_positive_uncorrelated_research_signal",
                "signal_evidence_status": "positive_research_signal",
                "tradability_status": "not_tradable_low_activity",
                "research_track": "rare_setup_research_signal",
                "revisit_condition": f"{CAVEAT} Revisit only through rare-module policy integration and future playbook evaluation; no paper trading unless unchanged official gates pass. fold_adequacy_status={fold_status}.",
                "source_report": SOURCE_REPORT,
            }
        )
        playbook_new.append(
            {
                "module_id": candidate_id,
                "phase": PHASE,
                "candidate_id": candidate_id,
                "source_family": source_family,
                "market_condition": MARKET_CONDITION[source_family],
                "module_family": MODULE_FAMILY[source_family],
                "portfolio_role": "diversifier_module",
                "plain_english_rule": rule,
                "signal_evidence_status": "positive_research_signal",
                "tradability_status": "not_tradable_low_activity",
                "research_track": "rare_setup_research_signal",
                "portfolio_contribution_status": f"not_evaluated_until_playbook_framework_e_rare_module_policy_integration; fold_adequacy_status={fold_status}",
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
                "level_source": str(r["regime_variant"]),
                "source_window": f"regime {r['regime_build_start']}-{r['regime_build_end']}; lunch {r['lunch_build_start']}-{r['lunch_build_end']}",
                "trade_window": f"{r['trade_start']}-{r['trade_end']}",
                "source_report": SOURCE_REPORT,
            }
        )

    research = pd.concat([research_base, pd.DataFrame(research_new)], ignore_index=True)
    playbook = pd.concat([playbook_base, pd.DataFrame(playbook_new)], ignore_index=True)
    research = research[list(research_before_raw.columns)]
    playbook = playbook[list(playbook_before_raw.columns)]

    if set(research[research["phase"].astype(str).eq(PHASE)]["candidate_id"].astype(str)).intersection(watchlist_ids):
        raise SystemExit("A rare-module-review watchlist row was added to research registry")
    if set(playbook[playbook["phase"].astype(str).eq(PHASE)]["candidate_id"].astype(str)).intersection(watchlist_ids):
        raise SystemExit("A rare-module-review watchlist row was added to playbook registry")

    research.to_csv(research_path, index=False)
    playbook.to_csv(playbook_path, index=False)
    strict_dump(research.to_dict(orient="records"), OUT / "research_signal_registry.json")
    strict_dump(playbook.to_dict(orient="records"), OUT / "playbook_module_registry.json")
    strict_dump(REC_E, OUT / "research_signal_registry_e_next_action_recommendation.json")

    rec_main = dict(REC_E)
    rec_main["registry_counts"] = {str(k): int(v) for k, v in research["research_track"].value_counts().sort_index().items()}
    rec_main["phase16a_rows_added"] = int(len(add))
    rec_main["phase16a_watchlist_rows_excluded"] = int(len(watchlist_review))
    rec_main["rare_module_caveat"] = CAVEAT
    rec_main["watchlist_hygiene_note"] = WATCHLIST_NOTE
    rec_main["research_signal_registry_e_recommendation"] = "outputs/research_signal_registry_e_next_action_recommendation.json"
    strict_dump(rec_main, OUT / "research_signal_registry_next_action_recommendation.json")

    table_rows = []
    module_lines = []
    for _, r in add.iterrows():
        source_family = str(r["module_family"])
        cid = str(r["candidate_id"])
        table_rows.append(
            f"| {int(r['phase16a_rank'])} | `{cid}` | {source_family} | {MARKET_CONDITION[source_family]} | {MODULE_FAMILY[source_family]} | diversifier_module | "
            f"{float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | "
            f"{float(r['holdout_pnl']):.2f} | {float(r['walk_forward_stress_pnl']):.2f} | "
            f"{float(r['average_correlation_to_registry']):.3f} | {int(r['trades'])} | low_activity_not_fully_interpretable |"
        )
        module_lines.append(
            f"| `{cid}` | {MARKET_CONDITION[source_family]} | {MODULE_FAMILY[source_family]} | diversifier_module | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal | low_activity_not_fully_interpretable | false | false |"
        )

    watchlist_lines = []
    for _, r in watchlist_review.iterrows():
        watchlist_lines.append(f"| `{r['candidate_id']}` | {r['watchlist_hygiene_status']} | {r['registration_decision']} |")

    update_report = f"""# Research Signal Registry E - Phase 16A Rare Module Update

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

This additive update adds the three Phase 16A rows approved by the Rare Module Validation Track for `registration_decision={DECISION_TO_ADD}` to the research signal registry and playbook module registry. It does not generate new signals, rerun Phase 16A, rerun the Rare Module Validation Track, change candidate results, change official promotion gates, promote candidates, or approve paper trading.

## Inputs Used

- outputs/research_signal_registry.csv / .json
- outputs/research_signal_registry_next_action_recommendation.json
- outputs/playbook_module_registry.csv / .json
- outputs/playbook_module_registry_schema.json
- outputs/playbook_module_taxonomy.json
- outputs/phase16a_candidate_results.csv
- outputs/phase16a_correlation_to_registry.csv
- outputs/phase16a_correlation_to_playbook.csv
- outputs/phase16a_gap_coverage_summary.csv
- outputs/phase16a_fold_view_summary.csv
- outputs/phase16a_module_fold_adequacy.csv
- outputs/phase16a_next_action_recommendation.json
- reports/phase16a_high_vol_mixed_regime_scout_report.md
- outputs/rare_module_validation_track_phase16a_candidates.csv
- outputs/rare_module_validation_track_adequacy_summary.csv
- outputs/rare_module_validation_track_registration_decisions.csv
- outputs/rare_module_validation_track_policy.json
- outputs/rare_module_validation_track_next_action_recommendation.json
- reports/rare_module_validation_track_review_report.md

## Phase 16A Rows Added

- Rows added: `{len(add)}`
- Research signal registry rows before/after: `{research_rows_before}` -> `{len(research)}`
- Playbook module registry rows before/after: `{playbook_rows_before}` -> `{len(playbook)}`
- Classification applied: `positive_research_signal`, `not_tradable_low_activity`, `rare_setup_research_signal`, `diversifier_module`, `low_activity_not_fully_interpretable`.
- Paper trading approved: `false`.
- Official gates passed: `false`.
- Top Phase 16A rule: {TOP_RULE}

| Rank | Candidate | Source family | Market condition | Module family | Portfolio role | Net | Stress | Validation | Holdout | WF stress | Avg registry corr | Trades | Fold adequacy |
| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
{chr(10).join(table_rows)}

## Rare-Module Caveat

{CAVEAT}

## Watchlist Hygiene

{WATCHLIST_NOTE}

| Excluded watchlist candidate | Hygiene status | Registration decision |
| --- | --- | --- |
{chr(10).join(watchlist_lines)}

## Recommendation

- Next action: `{REC_E['next_action']}`
- Rationale: {REC_E['rationale']}
- Official gates changed: `false`
- Paper trading approved: `false`
- Rare module track enabled: `true`
"""
    (REP / "research_signal_registry_e_phase16a_update_report.md").write_text(update_report, encoding="utf-8")

    research_addendum = f"""
## Registry E - Phase 16A Rare Module Addendum

Phase 16A added 3 Rare Module Validation Track-approved high-volatility mixed morning modules as rare setup diversifiers. All are `positive_research_signal`, `not_tradable_low_activity`, `rare_setup_research_signal`, with `portfolio_role=diversifier_module`, `fold_adequacy_status=low_activity_not_fully_interpretable`, `paper_trading_approved=false`, and `official_gates_passed=false`.

Rare-module caveat: {CAVEAT}

Watchlist hygiene: {WATCHLIST_NOTE}

Next action: `{REC_E['next_action']}`.
"""
    replace_addendum(REP / "research_signal_registry_report.md", "## Registry E - Phase 16A Rare Module Addendum", research_addendum)

    playbook_report = f"""# Playbook Module Registry - Phase 16A Rare Module Addendum

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Purpose

This registry maps Rare Module Validation Track-approved Phase 16A high-volatility mixed morning research signals into playbook module fields for rare-module policy integration. It preserves official gates and paper-trading blocks.

## Counts

- Total module rows: `{len(playbook)}`
- Phase 16A rows: `{len(add)}`
- Phase 16A diversifier modules: `{len(add)}`
- Phase 16A watchlist rows excluded: `{len(watchlist_review)}`

## Phase 16A Modules

| Module | Market condition | Family | Portfolio role | Evidence | Tradability | Track | Fold adequacy | Official gates | Paper trading |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(module_lines)}

## Rare-Module Caveat

{CAVEAT}

## Watchlist Hygiene

{WATCHLIST_NOTE}

## Next Action

`{REC_E['next_action']}` - {REC_E['rationale']}
"""
    (REP / "playbook_module_registry_report.md").write_text(playbook_report, encoding="utf-8")

    artifact_map = {
        "research_signal_registry.csv": research_path,
        "research_signal_registry.json": OUT / "research_signal_registry.json",
        "research_signal_registry_next_action_recommendation.json": OUT / "research_signal_registry_next_action_recommendation.json",
        "research_signal_registry_e_next_action_recommendation.json": OUT / "research_signal_registry_e_next_action_recommendation.json",
        "research_signal_registry_report.md": REP / "research_signal_registry_report.md",
        "research_signal_registry_e_phase16a_update_report.md": REP / "research_signal_registry_e_phase16a_update_report.md",
        "playbook_module_registry.csv": playbook_path,
        "playbook_module_registry.json": OUT / "playbook_module_registry.json",
        "playbook_module_registry_report.md": REP / "playbook_module_registry_report.md",
        "playbook_module_registry_schema.json": OUT / "playbook_module_registry_schema.json",
        "playbook_module_taxonomy.json": OUT / "playbook_module_taxonomy.json",
        "apply_registry_e_update.py": ART / "apply_registry_e_update.py",
    }
    for name, src in artifact_map.items():
        (ART / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = {
        "run_id": "research-signal-registry-e",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_registration_decision": DECISION_TO_ADD,
        "phase16a_rows_added": int(len(add)),
        "phase16a_watchlist_rows_excluded": int(len(watchlist_review)),
        "research_registry_rows_before": int(research_rows_before),
        "research_registry_rows_after": int(len(research)),
        "playbook_module_registry_rows_before": int(playbook_rows_before),
        "playbook_module_registry_rows_after": int(len(playbook)),
        "rare_module_caveat": CAVEAT,
        "watchlist_hygiene_note": WATCHLIST_NOTE,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "phase16a_not_rerun": True,
        "rare_module_validation_track_not_rerun": True,
        "artifact_files": sorted(artifact_map),
    }
    strict_dump(manifest, ART / "manifest.json")

    print(f"Added {len(add)} Phase 16A rows")
    print(f"Research registry rows: {research_rows_before} -> {len(research)}")
    print(f"Playbook module registry rows: {playbook_rows_before} -> {len(playbook)}")
    print(f"Excluded Phase 16A watchlist rows: {len(watchlist_review)}")
    print(f"Artifact dir: {ART}")


if __name__ == "__main__":
    main()
