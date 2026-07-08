from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .module_pruning_audit_a import SEED_SUSPECT_MODULE, duplicate_base
from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact
from .playbook_scheduler_b_priority_retest import PHASES, markdown_table
from .playbook_scheduler_c_pruning_retest import SEED_CLUSTER_TOKENS, identify_seed_suspect_cluster
from .portfolio_audit_b import RESEARCH_ONLY_GUARDRAIL, split_signal_key

OFFICIAL_GATES_CHANGED = False
PAPER_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True
LIVE_TRADING_APPROVED = False
REGISTRY_MUTATION = False
OVERLAY_VERSION = "playbook_module_deduplication_b_v1"
RECOMMENDATION_OPTIONS = {
    "playbook_scheduler_d_overlay_retest",
    "module_registry_c_apply_deprioritization_after_review",
    "phase16a_targeted_regime_module_scout",
    "validation_framework_audit_c_fold_design",
}

REVIEW_ACTIONS = (
    "keep_representative",
    "deprioritize_redundant",
    "deprioritize_harmful",
    "deprioritize_low_contribution",
    "park_do_not_schedule",
    "keep_for_diversification",
    "needs_manual_review",
)


def load_playbook_module_deduplication_b_inputs(output_dir: Path) -> dict[str, Any]:
    required: dict[str, Path] = {
        "playbook_module_registry": output_dir / "playbook_module_registry.csv",
        "research_signal_registry": output_dir / "research_signal_registry.csv",
        "module_pruning_diagnostics": output_dir / "module_pruning_audit_a_module_diagnostics.csv",
        "module_pruning_variants": output_dir / "module_pruning_audit_a_pruning_variants.csv",
        "module_pruning_results": output_dir / "module_pruning_audit_a_portfolio_results.csv",
        "module_pruning_redundancy_pairs": output_dir / "module_pruning_audit_a_redundancy_pairs.csv",
        "module_pruning_recommendation": output_dir / "module_pruning_audit_a_next_action_recommendation.json",
        "scheduler_c_results": output_dir / "playbook_scheduler_c_pruning_policy_results.csv",
        "scheduler_c_daily": output_dir / "playbook_scheduler_c_daily_pnl.csv",
        "scheduler_c_folds": output_dir / "playbook_scheduler_c_walk_forward_folds.csv",
        "scheduler_c_concentration": output_dir / "playbook_scheduler_c_concentration.csv",
        "scheduler_c_overlap": output_dir / "playbook_scheduler_c_overlap_summary.csv",
        "scheduler_c_acceptance": output_dir / "playbook_scheduler_c_module_acceptance_summary.csv",
        "scheduler_c_pruned_summary": output_dir / "playbook_scheduler_c_pruned_module_summary.csv",
        "scheduler_c_recommendation": output_dir / "playbook_scheduler_c_next_action_recommendation.json",
        "scheduler_b_acceptance": output_dir / "playbook_scheduler_b_module_acceptance_summary.csv",
        "scheduler_b_recommendation": output_dir / "playbook_scheduler_b_next_action_recommendation.json",
    }
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Module Deduplication B input(s): {missing}")
    return {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}


def run_playbook_module_deduplication_b(output_dir: Path) -> dict[str, Any]:
    data = load_playbook_module_deduplication_b_inputs(output_dir)
    modules = normalize_modules(data["playbook_module_registry"])
    research = normalize_research_registry(data["research_signal_registry"])
    diagnostics = normalize_diagnostics(data["module_pruning_diagnostics"])
    review_base = enrich_module_review_base(modules, research, diagnostics, data["scheduler_b_acceptance"], data["scheduler_c_acceptance"])
    selected_keys = scheduler_c_selected_keys(data["scheduler_c_pruned_summary"], data["scheduler_c_acceptance"], review_base)
    seed_cluster = identify_seed_suspect_cluster([k for k in review_base["signal_key"].astype(str).tolist() if k in selected_keys or k == SEED_SUSPECT_MODULE])
    cluster_pairs = build_cluster_edges(review_base, data["module_pruning_redundancy_pairs"], data["scheduler_c_overlap"], seed_cluster)
    clusters = build_redundancy_clusters(review_base, cluster_pairs, seed_cluster)
    cluster_df = cluster_rows(clusters, review_base, cluster_pairs, seed_cluster)
    representative_df = select_representative_modules(clusters, review_base)
    module_review = build_module_review(review_base, cluster_df, representative_df, selected_keys)
    deprio = module_review[module_review["candidate_action"].isin(["deprioritize_redundant", "deprioritize_harmful", "deprioritize_low_contribution"])].copy()
    overlay = build_scheduler_overlay(module_review, representative_df, data)
    recommendation = make_next_action_recommendation(module_review, cluster_df, data, overlay)
    return {
        "redundancy_clusters": cluster_df,
        "module_review": module_review,
        "representative_modules": representative_df,
        "deprioritization_candidates": deprio.sort_values(["candidate_action", "cluster_id", "signal_key"]).reset_index(drop=True),
        "scheduler_overlay": overlay,
        "next_action_recommendation": recommendation,
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "seed_cluster_modules": seed_cluster,
        "inputs_loaded": loaded_input_names(),
    }


def normalize_modules(modules: pd.DataFrame) -> pd.DataFrame:
    out = modules.copy()
    if "signal_key" not in out:
        out["signal_key"] = out.apply(lambda r: f"{r.get('phase')}::{r.get('candidate_id', r.get('module_id'))}", axis=1)
    for col in ("module_id", "candidate_id"):
        if col not in out:
            out[col] = out["signal_key"].astype(str).str.split("::", n=1).str[-1]
    if "phase" not in out:
        out["phase"] = out["signal_key"].astype(str).str.split("::", n=1).str[0]
    return out.drop_duplicates("signal_key").reset_index(drop=True)


def normalize_research_registry(research: pd.DataFrame) -> pd.DataFrame:
    out = research.copy()
    if "signal_key" not in out:
        out["signal_key"] = out.apply(lambda r: f"{r.get('phase')}::{r.get('candidate_id')}", axis=1)
    return out.drop_duplicates("signal_key").reset_index(drop=True)


def normalize_diagnostics(diagnostics: pd.DataFrame) -> pd.DataFrame:
    out = diagnostics.copy()
    if "signal_key" not in out and {"phase", "candidate_id"}.issubset(out.columns):
        out["signal_key"] = out.apply(lambda r: f"{r.get('phase')}::{r.get('candidate_id')}", axis=1)
    return out.drop_duplicates("signal_key").reset_index(drop=True) if "signal_key" in out else pd.DataFrame(columns=["signal_key"])


def enrich_module_review_base(modules: pd.DataFrame, research: pd.DataFrame, diagnostics: pd.DataFrame, scheduler_b_acceptance: pd.DataFrame, scheduler_c_acceptance: pd.DataFrame) -> pd.DataFrame:
    base = modules.copy()
    research_cols = [c for c in ["signal_key", "family", "bootstrap_or_null_classification", "revisit_condition"] if c in research]
    if research_cols:
        base = base.merge(research[research_cols], on="signal_key", how="left", suffixes=("", "_research"))
    diag_cols = [c for c in diagnostics.columns if c != "phase" and c != "candidate_id"]
    if diag_cols:
        base = base.merge(diagnostics[diag_cols], on="signal_key", how="left", suffixes=("", "_pruning_a"))
    b = _acceptance_agg(scheduler_b_acceptance, ["diagnostic_filter"], required_filter=("diagnostic_filter", "no_filter_baseline"), prefix="scheduler_b")
    c = _acceptance_agg(scheduler_c_acceptance, ["pruning_variant"], required_filter=("pruning_variant", "no_pruning_baseline"), prefix="scheduler_c")
    if not b.empty:
        base = base.merge(b, on="signal_key", how="left")
    if not c.empty:
        base = base.merge(c, on="signal_key", how="left")
    for col in numeric_columns():
        if col not in base:
            base[col] = 0.0
        base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0.0)
    for col in ("source_family", "module_family", "portfolio_role", "plain_english_rule", "signal_evidence_status", "tradability_status", "research_track", "portfolio_contribution_status"):
        if col not in base:
            base[col] = ""
        base[col] = base[col].fillna("").astype(str)
    base["duplicate_base"] = base["candidate_id"].astype(str).map(semantic_duplicate_base)
    base["base_rule"] = base["candidate_id"].astype(str).map(base_rule_token)
    base["side"] = base["candidate_id"].astype(str).map(side_token)
    return base.sort_values(["phase", "candidate_id", "signal_key"]).reset_index(drop=True)


def _acceptance_agg(frame: pd.DataFrame, group_filter_cols: list[str], required_filter: tuple[str, str], prefix: str) -> pd.DataFrame:
    if frame.empty or "signal_key" not in frame:
        return pd.DataFrame()
    seg = frame.copy()
    col, val = required_filter
    if col in seg:
        seg = seg[seg[col].astype(str).eq(val)].copy()
    if seg.empty:
        return pd.DataFrame()
    for c in ("accepted_trade_count", "accepted_net_pnl", "skipped_trade_count", "skipped_net_pnl"):
        if c not in seg:
            seg[c] = 0
        seg[c] = pd.to_numeric(seg[c], errors="coerce").fillna(0.0)
    out = seg.groupby("signal_key", as_index=False).agg(
        **{
            f"{prefix}_accepted_trade_count": ("accepted_trade_count", "sum"),
            f"{prefix}_accepted_net_pnl": ("accepted_net_pnl", "sum"),
            f"{prefix}_skipped_trade_count": ("skipped_trade_count", "sum"),
            f"{prefix}_skipped_net_pnl": ("skipped_net_pnl", "sum"),
        }
    )
    return out


def numeric_columns() -> list[str]:
    return [
        "net_pnl",
        "stress_pnl",
        "validation_pnl",
        "holdout_pnl",
        "walk_forward_stress_pnl",
        "positive_wf_test_folds_pct",
        "trades",
        "active_days",
        "best_day_concentration",
        "best_trade_concentration",
        "average_correlation_to_registry",
        "max_correlation_to_registry",
        "average_daily_correlation_to_other_modules",
        "max_daily_correlation_to_other_modules",
        "overlap_rate_with_other_modules",
        "scheduler_b_net_contribution",
        "accepted_net_pnl",
        "contribution_in_weak_folds",
        "scheduler_b_accepted_trade_count",
        "scheduler_b_accepted_net_pnl",
        "scheduler_c_accepted_trade_count",
        "scheduler_c_accepted_net_pnl",
    ]


def scheduler_c_selected_keys(pruned_summary: pd.DataFrame, acceptance: pd.DataFrame, review_base: pd.DataFrame) -> set[str]:
    if not pruned_summary.empty and "pruning_variant" in pruned_summary:
        row = pruned_summary[pruned_summary["pruning_variant"].astype(str).eq("no_pruning_baseline")]
        if not row.empty:
            removed = set(_split_modules(row.iloc[0].get("removed_modules", "")))
            if "module_kept" in acceptance and "signal_key" in acceptance:
                keys = set(acceptance.loc[acceptance["module_kept"].astype(bool), "signal_key"].astype(str))
                if keys:
                    return keys - removed
    if "signal_key" in acceptance:
        return set(acceptance["signal_key"].astype(str))
    return set(review_base["signal_key"].astype(str))


def build_cluster_edges(review_base: pd.DataFrame, redundancy_pairs: pd.DataFrame, overlap: pd.DataFrame, seed_cluster: list[str]) -> pd.DataFrame:
    keys = set(review_base["signal_key"].astype(str))
    rows: list[dict[str, Any]] = []
    if not redundancy_pairs.empty:
        for _, r in redundancy_pairs.iterrows():
            a, b = str(r.get("signal_a", "")), str(r.get("signal_b", ""))
            if a in keys and b in keys:
                rows.append({
                    "signal_a": a,
                    "signal_b": b,
                    "edge_reason": str(r.get("dedupe_reason", "module_pruning_a_redundancy_pair")),
                    "daily_pnl_correlation": _num(r.get("daily_pnl_correlation")),
                    "overlap_rate": None,
                    "source": "module_pruning_a_redundancy_pairs",
                })
    grouped = review_base.groupby(["phase", "source_family", "module_family", "side", "base_rule", "duplicate_base"], dropna=False)
    for _, group in grouped:
        group_keys = sorted(group["signal_key"].astype(str).tolist())
        if len(group_keys) <= 1:
            continue
        for i, a in enumerate(group_keys):
            for b in group_keys[i + 1 :]:
                rows.append({"signal_a": a, "signal_b": b, "edge_reason": "same_phase_family_side_base_rule_sibling_pattern", "daily_pnl_correlation": None, "overlap_rate": None, "source": "candidate_id_similarity"})
    for i, a in enumerate(seed_cluster):
        for b in seed_cluster[i + 1 :]:
            if a in keys and b in keys:
                rows.append({"signal_a": a, "signal_b": b, "edge_reason": "phase10b_seed_cluster_required_review", "daily_pnl_correlation": None, "overlap_rate": None, "source": "required_seed_cluster"})
    if rows:
        out = pd.DataFrame(rows).drop_duplicates(["signal_a", "signal_b", "edge_reason"]).sort_values(["signal_a", "signal_b", "edge_reason"]).reset_index(drop=True)
    else:
        out = pd.DataFrame(columns=["signal_a", "signal_b", "edge_reason", "daily_pnl_correlation", "overlap_rate", "source"])
    return out


def build_redundancy_clusters(review_base: pd.DataFrame, edges: pd.DataFrame, seed_cluster: list[str]) -> dict[str, list[str]]:
    keys = review_base["signal_key"].astype(str).tolist()
    parent = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        if a not in parent or b not in parent:
            return
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for _, row in edges.iterrows():
        union(str(row["signal_a"]), str(row["signal_b"]))
    for i, a in enumerate(seed_cluster):
        for b in seed_cluster[i + 1 :]:
            union(a, b)
    raw: dict[str, list[str]] = {}
    for key in keys:
        root = find(key)
        raw.setdefault(root, []).append(key)
    return {f"cluster_{i:02d}": sorted(members) for i, members in enumerate(sorted(raw.values(), key=lambda m: (m[0], len(m))), start=1) if len(members) > 1}


def cluster_rows(clusters: dict[str, list[str]], review_base: pd.DataFrame, edges: pd.DataFrame, seed_cluster: list[str]) -> pd.DataFrame:
    meta = review_base.set_index("signal_key")
    edge_map: dict[str, list[str]] = {cid: [] for cid in clusters}
    for cid, members in clusters.items():
        member_set = set(members)
        reasons = sorted(set(edges.loc[edges["signal_a"].isin(member_set) & edges["signal_b"].isin(member_set), "edge_reason"].astype(str))) if not edges.empty else []
        edge_map[cid] = reasons
    rows = []
    seed_set = set(seed_cluster)
    for cid, members in clusters.items():
        phases = sorted({str(meta.loc[k].get("phase", split_signal_key(k)[0])) for k in members if k in meta.index})
        rows.append({
            "cluster_id": cid,
            "cluster_size": len(members),
            "phases": ";".join(phases),
            "is_phase10b_seed_cluster": bool(seed_set.intersection(members)),
            "cluster_reason": ";".join(edge_map.get(cid, [])),
            "members": ";".join(members),
        })
    return pd.DataFrame(rows).sort_values(["is_phase10b_seed_cluster", "cluster_size", "cluster_id"], ascending=[False, False, True]).reset_index(drop=True) if rows else pd.DataFrame(columns=["cluster_id", "cluster_size", "phases", "is_phase10b_seed_cluster", "cluster_reason", "members"])


def select_representative_modules(clusters: dict[str, list[str]], review_base: pd.DataFrame) -> pd.DataFrame:
    meta = review_base.set_index("signal_key")
    rows = []
    for cid, members in clusters.items():
        ranked = sorted(members, key=lambda key: representative_score(key, meta.loc[key] if key in meta.index else pd.Series(dtype=object)))
        rep = ranked[0]
        rep_row = meta.loc[rep]
        rows.append({
            "cluster_id": cid,
            "representative_module": rep,
            "cluster_members": ";".join(sorted(members)),
            "selection_rationale": representative_rationale(rep_row),
            "validation_pnl": round(_num(rep_row.get("validation_pnl")), 2),
            "holdout_pnl": round(_num(rep_row.get("holdout_pnl")), 2),
            "stress_pnl": round(_num(rep_row.get("stress_pnl", rep_row.get("walk_forward_stress_pnl"))), 2),
            "best_day_concentration": round(_num(rep_row.get("best_day_concentration")), 6),
            "best_trade_concentration": round(_num(rep_row.get("best_trade_concentration")), 6),
            "average_correlation": round(avg_corr_value(rep_row), 6),
            "scheduler_b_accepted_net_pnl": round(_num(rep_row.get("scheduler_b_accepted_net_pnl", rep_row.get("scheduler_b_net_contribution"))), 2),
            "scheduler_c_accepted_net_pnl": round(_num(rep_row.get("scheduler_c_accepted_net_pnl")), 2),
            "weak_fold_harm": round(_num(rep_row.get("contribution_in_weak_folds")), 2),
        })
    return pd.DataFrame(rows).sort_values(["cluster_id", "representative_module"]).reset_index(drop=True) if rows else pd.DataFrame(columns=["cluster_id", "representative_module", "cluster_members", "selection_rationale"])


def representative_score(key: str, row: pd.Series) -> tuple[Any, ...]:
    validation = _num(row.get("validation_pnl"))
    holdout = _num(row.get("holdout_pnl"))
    stress = _num(row.get("stress_pnl", row.get("walk_forward_stress_pnl")))
    day = _num(row.get("best_day_concentration"), default=1.0)
    trade = _num(row.get("best_trade_concentration"), default=1.0)
    corr = avg_corr_value(row)
    contrib = _num(row.get("scheduler_c_accepted_net_pnl")) + _num(row.get("scheduler_b_accepted_net_pnl", row.get("scheduler_b_net_contribution")))
    weak_harm = _num(row.get("contribution_in_weak_folds"))
    plain = str(row.get("plain_english_rule", ""))
    return (
        0 if validation > 0 else 1,
        0 if holdout > 0 else 1,
        0 if stress > 0 else 1,
        day,
        trade,
        corr,
        -contrib,
        weak_harm if weak_harm < 0 else 0,
        len(plain) if plain else 9999,
        key,
    )


def representative_rationale(row: pd.Series) -> str:
    parts = []
    if _num(row.get("validation_pnl")) > 0:
        parts.append("positive_validation")
    if _num(row.get("holdout_pnl")) > 0:
        parts.append("positive_holdout")
    if _num(row.get("stress_pnl", row.get("walk_forward_stress_pnl"))) > 0:
        parts.append("positive_stress")
    parts.append("lowest_concentration_correlation_contribution_tiebreak")
    return ";".join(parts)


def build_module_review(review_base: pd.DataFrame, cluster_df: pd.DataFrame, representatives: pd.DataFrame, selected_keys: set[str]) -> pd.DataFrame:
    cluster_by_member: dict[str, str] = {}
    for _, row in cluster_df.iterrows():
        for member in _split_modules(row.get("members", "")):
            cluster_by_member[member] = str(row["cluster_id"])
    rep_by_cluster = {str(r["cluster_id"]): str(r["representative_module"]) for _, r in representatives.iterrows()}
    rows = []
    for _, r in review_base.iterrows():
        key = str(r["signal_key"])
        cluster_id = cluster_by_member.get(key, "")
        rep = rep_by_cluster.get(cluster_id, "")
        action, reason = candidate_action_for_module(r, cluster_id, rep, key in selected_keys)
        rows.append({
            "signal_key": key,
            "phase": str(r.get("phase", split_signal_key(key)[0])),
            "candidate_id": str(r.get("candidate_id", split_signal_key(key)[1])),
            "cluster_id": cluster_id,
            "cluster_representative": rep,
            "candidate_action": action,
            "deprioritization_reason": reason,
            "currently_in_scheduler_c_universe": bool(key in selected_keys),
            "validation_pnl": round(_num(r.get("validation_pnl")), 2),
            "holdout_pnl": round(_num(r.get("holdout_pnl")), 2),
            "stress_pnl": round(_num(r.get("stress_pnl", r.get("walk_forward_stress_pnl"))), 2),
            "best_day_concentration": round(_num(r.get("best_day_concentration")), 6),
            "best_trade_concentration": round(_num(r.get("best_trade_concentration")), 6),
            "average_correlation": round(avg_corr_value(r), 6),
            "overlap_rate": round(_num(r.get("overlap_rate_with_other_modules")), 6),
            "scheduler_b_accepted_net_pnl": round(_num(r.get("scheduler_b_accepted_net_pnl", r.get("scheduler_b_net_contribution"))), 2),
            "scheduler_c_accepted_net_pnl": round(_num(r.get("scheduler_c_accepted_net_pnl")), 2),
            "weak_fold_harm": round(_num(r.get("contribution_in_weak_folds")), 2),
            "portfolio_role": str(r.get("portfolio_role", "")),
            "signal_evidence_status": str(r.get("signal_evidence_status", "")),
            "tradability_status": str(r.get("tradability_status", "")),
            "plain_english_rule": str(r.get("plain_english_rule", "")),
        })
    return pd.DataFrame(rows).sort_values(["cluster_id", "candidate_action", "signal_key"]).reset_index(drop=True)


def candidate_action_for_module(row: pd.Series, cluster_id: str, representative: str, in_scheduler: bool) -> tuple[str, str]:
    key = str(row.get("signal_key"))
    if cluster_id and key == representative:
        return "keep_representative", "selected as deterministic representative for redundancy cluster"
    harmful = _truthy(row.get("harmful_when_accepted", False)) or _num(row.get("accepted_net_pnl")) < 0 or _num(row.get("scheduler_c_accepted_net_pnl")) < 0
    low_contribution = _num(row.get("scheduler_b_accepted_net_pnl", row.get("scheduler_b_net_contribution"))) <= 0 and _num(row.get("scheduler_c_accepted_net_pnl")) <= 0
    if cluster_id:
        return "deprioritize_redundant", "non-representative member of deterministic redundancy cluster"
    if harmful:
        return "deprioritize_harmful", "negative accepted contribution or harmful-when-accepted diagnostic"
    if low_contribution and in_scheduler:
        return "deprioritize_low_contribution", "non-positive accepted contribution in Scheduler B/C baseline evidence"
    phase = str(row.get("phase", ""))
    if phase in {"phase13a", "phase14a", "phase15a"} and (_num(row.get("validation_pnl")) > 0 or _num(row.get("holdout_pnl")) > 0):
        return "keep_for_diversification", "non-cluster diversifier with positive split evidence"
    if not in_scheduler or str(row.get("portfolio_role", "")).lower() == "parked_module":
        return "park_do_not_schedule", "not in current Scheduler C universe or parked module without representative role"
    return "needs_manual_review", "not redundant, harmful, or clear diversifier under deterministic review rules"


def build_scheduler_overlay(module_review: pd.DataFrame, representatives: pd.DataFrame, data: dict[str, Any]) -> dict[str, Any]:
    keep_actions = {"keep_representative", "keep_for_diversification", "needs_manual_review"}
    deprio_actions = {"deprioritize_redundant", "deprioritize_harmful", "deprioritize_low_contribution"}
    keep = sorted(module_review.loc[module_review["candidate_action"].isin(keep_actions), "signal_key"].astype(str).tolist())
    deprio = sorted(module_review.loc[module_review["candidate_action"].isin(deprio_actions), "signal_key"].astype(str).tolist())
    park = sorted(module_review.loc[module_review["candidate_action"].eq("park_do_not_schedule"), "signal_key"].astype(str).tolist())
    reason = {str(r["signal_key"]): str(r["deprioritization_reason"]) for _, r in module_review[module_review["candidate_action"].isin(deprio_actions.union({"park_do_not_schedule"}))].iterrows()}
    reps = {str(r["cluster_id"]): str(r["representative_module"]) for _, r in representatives.iterrows()}
    return {
        "overlay_version": OVERLAY_VERSION,
        "created_from": loaded_input_names(),
        "registry_mutation": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "modules_to_keep": keep,
        "modules_to_deprioritize": deprio,
        "modules_to_park": park,
        "cluster_representatives": reps,
        "deprioritization_reason_by_module": reason,
        "recommended_priority_policy": "schedule representatives before redundant non-representatives; keep overlay diagnostic-only until Scheduler D retest",
        "recommended_future_scheduler_test": "playbook_scheduler_d_overlay_retest",
    }


def make_next_action_recommendation(module_review: pd.DataFrame, cluster_df: pd.DataFrame, data: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    harmful_count = int(module_review["candidate_action"].eq("deprioritize_harmful").sum())
    cluster_count = int(len(cluster_df))
    deprio_count = int(len(overlay["modules_to_deprioritize"]))
    scheduler_c_rep = str(data.get("scheduler_c_recommendation", {}).get("next_action", ""))
    pruning_a_rep = str(data.get("module_pruning_recommendation", {}).get("next_action", ""))
    clear = cluster_count > 0 and deprio_count > 0 and ("deduplication" in scheduler_c_rep or "pruning" in scheduler_c_rep or "scheduler_c" in pruning_a_rep or "scheduler" in pruning_a_rep)
    if harmful_count >= max(5, safe_divide(len(module_review), 4) * len(module_review)):
        action = "module_registry_c_apply_deprioritization_after_review"
        rationale = "Many modules are harmful across accepted-contribution diagnostics; registry application still requires explicit review."
    elif clear:
        action = "playbook_scheduler_d_overlay_retest"
        rationale = "Deduplication overlay is clear and based on replicated Module Pruning Audit A plus Scheduler C pruning evidence."
    elif cluster_count == 0 or deprio_count == 0:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Deduplication evidence is ambiguous or produced no clear deprioritization set."
    else:
        action = "validation_framework_audit_c_fold_design"
        rationale = "Deduplication evidence exists, but fold instability remains insufficiently explained by the overlay alone."
    return {
        "next_action": action,
        "rationale": rationale,
        "redundancy_cluster_count": cluster_count,
        "modules_to_keep_count": len(overlay["modules_to_keep"]),
        "modules_to_deprioritize_count": len(overlay["modules_to_deprioritize"]),
        "modules_to_park_count": len(overlay["modules_to_park"]),
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "seed_cluster_decision": seed_cluster_decision(module_review),
        "registry_mutation": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
    }


def seed_cluster_decision(module_review: pd.DataFrame) -> str:
    seg = module_review[module_review["signal_key"].astype(str).isin(required_seed_cluster_from_review(module_review))]
    if seg.empty:
        return "needs_manual_review_seed_cluster_not_found"
    reps = seg[seg["candidate_action"].eq("keep_representative")]["signal_key"].astype(str).tolist()
    deprio = seg[seg["candidate_action"].eq("deprioritize_redundant")]["signal_key"].astype(str).tolist()
    return f"keep_representative={';'.join(reps)};deprioritize_redundant={';'.join(deprio)}"


def required_seed_cluster_from_review(module_review: pd.DataFrame) -> list[str]:
    keys = module_review["signal_key"].astype(str).tolist()
    return [k for k in keys if split_signal_key(k)[0] == "phase10b" and any(token in split_signal_key(k)[1] for token in SEED_CLUSTER_TOKENS) and "primary_short_midday_breakout" in k and "all_ranges_all_gaps" in k]


def render_playbook_module_deduplication_b_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    overlay = result["scheduler_overlay"]
    seed_review = result["module_review"][result["module_review"]["signal_key"].isin(result["seed_cluster_modules"])]
    lines = [
        "# Playbook Module Deduplication B — Review",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Research-only deduplication/deprioritization review using existing registries, Module Pruning Audit A, Scheduler B/C outputs, and phase trade logs only. No new signals were generated, no strategy searches were run, no official promotion gates were changed, no modules were removed from registries, no candidates were promoted, no paper trading was approved, and no live-trading functionality was added.",
        "",
        "## Why deduplication review was needed",
        "",
        "Module Pruning Audit A and Scheduler C both indicated that removing or deprioritizing high-redundancy module pairs can improve fold behavior and concentration. This review converts those diagnostics into an auditable proposed scheduler overlay only.",
        "",
        "## Evidence from Module Pruning Audit A",
        "",
        f"- Redundancy pairs loaded: `{len(result['redundancy_clusters'])}` clusters built from `outputs/module_pruning_audit_a_redundancy_pairs.csv` plus deterministic sibling similarity.",
        f"- Module diagnostics loaded: actions use accepted contribution, weak-fold harm, correlation, overlap, and harmful/skipped flags where available.",
        "",
        "## Evidence from Scheduler C",
        "",
        "- Scheduler C pruning/deprioritization outputs were loaded as replication evidence and as the source for current scheduler-universe membership.",
        "- The generated overlay is diagnostic-only and is not written into scheduler logic or live registries.",
        "",
        "## Redundancy clusters found",
        "",
        markdown_table(result["redundancy_clusters"]),
        "",
        "## Proposed representative modules",
        "",
        markdown_table(result["representative_modules"]),
        "",
        "## Proposed deprioritized modules",
        "",
        markdown_table(result["deprioritization_candidates"]),
        "",
        "## Phase 10B seed cluster treatment",
        "",
        f"Seed suspect: `{result['seed_suspect_module']}`",
        f"Seed cluster modules: `{';'.join(result['seed_cluster_modules'])}`",
        markdown_table(seed_review),
        "",
        "## Scheduler overlay summary",
        "",
        f"- Modules to keep: `{len(overlay['modules_to_keep'])}`",
        f"- Modules to deprioritize: `{len(overlay['modules_to_deprioritize'])}`",
        f"- Modules to park: `{len(overlay['modules_to_park'])}`",
        f"- Recommended future scheduler test: `{overlay['recommended_future_scheduler_test']}`",
        "",
        "## Guardrail confirmations",
        "",
        "No modules were removed: `true`.",
        "Registry files mutated: `false`.",
        "Official gates changed: `false`.",
        "Paper trading approved: `false`.",
        "New strategy signals generated: `false`.",
        "Live trading approved: `false`.",
        "",
        "## Recommended next test",
        "",
        f"Next action: `{rec['next_action']}`",
        f"Rationale: {rec['rationale']}",
        "",
    ]
    return "\n".join(lines)


def write_playbook_module_deduplication_b_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "redundancy_clusters": output_dir / "playbook_module_deduplication_b_redundancy_clusters.csv",
        "module_review": output_dir / "playbook_module_deduplication_b_module_review.csv",
        "representative_modules": output_dir / "playbook_module_deduplication_b_representative_modules.csv",
        "deprioritization_candidates": output_dir / "playbook_module_deduplication_b_deprioritization_candidates.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    overlay_path = output_dir / "playbook_module_deduplication_b_scheduler_overlay.json"
    rec_path = output_dir / "playbook_module_deduplication_b_next_action_recommendation.json"
    write_json_artifact(result["scheduler_overlay"], overlay_path)
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_playbook_module_deduplication_b_report(result), encoding="utf-8")
    paths["scheduler_overlay"] = overlay_path
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def loaded_input_names() -> list[str]:
    return [
        "outputs/playbook_module_registry.csv",
        "outputs/research_signal_registry.csv",
        "outputs/module_pruning_audit_a_module_diagnostics.csv",
        "outputs/module_pruning_audit_a_pruning_variants.csv",
        "outputs/module_pruning_audit_a_portfolio_results.csv",
        "outputs/module_pruning_audit_a_redundancy_pairs.csv",
        "outputs/module_pruning_audit_a_next_action_recommendation.json",
        "outputs/playbook_scheduler_c_pruning_policy_results.csv",
        "outputs/playbook_scheduler_c_daily_pnl.csv",
        "outputs/playbook_scheduler_c_walk_forward_folds.csv",
        "outputs/playbook_scheduler_c_concentration.csv",
        "outputs/playbook_scheduler_c_overlap_summary.csv",
        "outputs/playbook_scheduler_c_module_acceptance_summary.csv",
        "outputs/playbook_scheduler_c_pruned_module_summary.csv",
        "outputs/playbook_scheduler_c_next_action_recommendation.json",
        "outputs/playbook_scheduler_b_module_acceptance_summary.csv",
        "outputs/playbook_scheduler_b_next_action_recommendation.json",
        *[f"outputs/{phase}_trade_logs.csv" for phase in PHASES],
    ]


def semantic_duplicate_base(candidate_id: str) -> str:
    return duplicate_base(str(candidate_id))


def base_rule_token(candidate_id: str) -> str:
    cid = str(candidate_id)
    cid = re.sub(r"_mt\d+", "", cid)
    cid = cid.replace("all_touches", "touch_pattern").replace("first_touch_only", "touch_pattern")
    return cid


def side_token(candidate_id: str) -> str:
    cid = str(candidate_id).lower()
    if "_short_" in cid or cid.endswith("_short"):
        return "short"
    if "_long_" in cid or cid.endswith("_long"):
        return "long"
    return "unknown"


def avg_corr_value(row: pd.Series) -> float:
    for col in ("average_daily_correlation_to_other_modules", "average_correlation_to_registry", "average_correlation_to_portfolio_audit"):
        if col in row and not pd.isna(row.get(col)):
            value = _num(row.get(col))
            if value != 0:
                return value
    return 0.0


def _split_modules(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [v for v in str(value).split(";") if v and v.lower() != "nan"]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
