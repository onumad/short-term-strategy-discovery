from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data_loader import load_ohlcv_csv
from .ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL
from .ml_dataset_b_feature_target_quality import markdown_table
from .phase10b_overnight_range_targeted_retest import (
    _add_cost_waterfall as add_phase10b_costs,
    _as_10a_spec,
    _build_base_trade_pool,
    apply_phase10b_pre_entry_filters,
    build_phase10b_specs,
)
from .phase11a_opening_range_fade_confirmation import (
    build_phase11a_feature_bars,
    build_phase11a_specs,
    generate_phase11a_signals,
    simulate_phase11a_trades,
)
from .phase13a_uncorrelated_family_scout import (
    build_phase13a_feature_bars,
    build_phase13a_specs,
    generate_phase13a_signals,
    simulate_phase13a_trades,
)
from .phase14a_prior_level_reaction_scout import (
    build_phase14a_feature_bars,
    build_phase14a_specs,
    generate_phase14a_signals,
    simulate_phase14a_trades,
)
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact
from .playbook_scheduler_b_priority_retest import construct_scheduled_trades

TARGETS_D = [
    "target_default_scheduler_active_day_d",
    "target_default_scheduler_active_day_loss_d",
    "target_default_scheduler_active_day_large_loss_d",
    "target_any_default_module_opportunity_d",
    "target_missed_default_module_opportunity_d",
    "target_bad_regime_d",
    "target_prior_level_interaction_day",
    "target_power_hour_expansion_day",
]
DIAGNOSTIC_TARGETS_D = {
    "target_bad_regime_d",
    "target_prior_level_interaction_day",
    "target_power_hour_expansion_day",
}
TRAINABILITY_RULES = {
    "min_total_non_null_rows": 300,
    "min_overall_true": 50,
    "min_overall_false": 50,
    "min_train_true": 30,
    "min_train_false": 30,
    "min_validation_true": 15,
    "min_validation_false": 15,
    "min_holdout_true": 15,
    "min_holdout_false": 15,
}
OUTCOME_STATUSES = (
    "missing_source_day",
    "no_trade_day",
    "active_day",
    "active_day_positive",
    "active_day_negative",
    "active_day_zero_result",
)


@dataclass(frozen=True)
class MlTargetDConfig:
    project_root: Path
    dataset_c_path: Path
    label_dictionary_c_path: Path
    leakage_audit_b_path: Path
    scheduler_policy_path: Path
    module_registry_path: Path
    raw_data_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "ml-target-d-r1"


def build_ml_target_d_playbook_label_backfill(project_root: Path, run_id: str = "ml-target-d-r1") -> dict[str, Any]:
    outputs = project_root / "outputs"
    config = MlTargetDConfig(
        project_root=project_root,
        dataset_c_path=outputs / "ml_target_c_day_regime.csv",
        label_dictionary_c_path=outputs / "ml_target_c_label_dictionary.json",
        leakage_audit_b_path=outputs / "ml_dataset_b_leakage_audit.csv",
        scheduler_policy_path=outputs / "playbook_scheduler_policy.json",
        module_registry_path=outputs / "playbook_module_registry.csv",
        raw_data_path=project_root / "data" / "raw" / "mnq_1m_databento_20230101_20260703.csv",
        output_dir=outputs,
        report_dir=project_root / "reports",
        artifact_dir=project_root / "artifacts" / "ml_target_d_playbook_label_backfill" / run_id,
        run_id=run_id,
    )
    return run_ml_target_d_playbook_label_backfill(config)


def run_ml_target_d_playbook_label_backfill(config: MlTargetDConfig) -> dict[str, Any]:
    for directory in (config.output_dir, config.report_dir, config.artifact_dir):
        ensure_directory(directory)
    dataset_c = pd.read_csv(config.dataset_c_path)
    label_c = json.loads(config.label_dictionary_c_path.read_text(encoding="utf-8"))
    leakage_audit_b = pd.read_csv(config.leakage_audit_b_path)
    policy = json.loads(config.scheduler_policy_path.read_text(encoding="utf-8"))
    registry = pd.read_csv(config.module_registry_path)
    validate_inputs(dataset_c, label_c, policy, registry)

    sessions = dataset_c["trading_session"].astype(str).tolist()
    universe = audit_default_scheduler_universe(policy, registry)
    bars = load_ohlcv_csv(config.raw_data_path)
    bars = bars[bars["trading_session"].astype(str).isin(set(sessions))].copy()
    replay = replay_default_modules(bars, universe["default_signal_keys"])
    module_daily = build_module_daily_outcome(sessions, universe, replay)
    playbook_daily, accepted = build_playbook_daily_outcome(sessions, universe, replay)
    coverage = build_coverage_audit(dataset_c, universe, module_daily, playbook_daily, replay)
    split_assignments, split_summary = build_coverage_aligned_splits(dataset_c, playbook_daily, module_daily)
    dataset_d, threshold_info = build_dataset_d(dataset_c, playbook_daily, module_daily, split_assignments)
    balance = build_target_balance_by_split(dataset_d, split_assignments)
    readiness = build_target_readiness_summary(balance, dataset_c, leakage_audit_b)
    labels = build_label_dictionary_d(label_c, readiness, threshold_info)
    recommendation = build_next_action_recommendation(readiness, coverage, dataset_d)
    paths = write_outputs(
        config,
        dataset_d,
        playbook_daily,
        module_daily,
        coverage,
        split_summary,
        balance,
        labels,
        readiness,
        recommendation,
        threshold_info,
        universe,
    )
    return {
        "dataset": dataset_d,
        "playbook_daily_outcome": playbook_daily,
        "module_daily_outcome": module_daily,
        "coverage_audit": coverage,
        "split_summary": split_summary,
        "target_balance_by_split": balance,
        "target_readiness_summary": readiness,
        "label_dictionary": labels,
        "next_action_recommendation": recommendation,
        "threshold_info": threshold_info,
        "universe": universe,
        "accepted_trades": accepted,
        "paths": paths,
    }


def validate_inputs(dataset: pd.DataFrame, labels: dict[str, Any], policy: dict[str, Any], registry: pd.DataFrame) -> None:
    required = {"trading_session", "chronological_split", "recent_oos_like"}
    missing = sorted(required - set(dataset.columns))
    if missing:
        raise ValueError(f"Dataset C is missing required columns: {missing}")
    if not labels:
        raise ValueError("Dataset C label dictionary is empty")
    if policy.get("default_include_rare_modules_in_scheduler") is not False:
        raise ValueError("Default scheduler policy must exclude rare modules")
    for column in ("phase", "candidate_id", "research_track", "portfolio_role"):
        if column not in registry:
            raise ValueError(f"Module registry missing {column}")


def audit_default_scheduler_universe(policy: dict[str, Any], registry: pd.DataFrame) -> dict[str, Any]:
    configured = policy["recommended_default_scheduler_universe"]
    default_keys = [str(v) for v in configured.get("signal_keys", [])]
    rare_keys = [f"{row.phase}::{row.candidate_id}" for row in registry.itertuples(index=False) if _is_rare_row(row)]
    registry_keys = set(registry["phase"].astype(str) + "::" + registry["candidate_id"].astype(str))
    missing = [key for key in default_keys if key not in registry_keys]
    overlap = sorted(set(default_keys).intersection(rare_keys))
    if missing:
        raise ValueError(f"Policy default modules missing from registry: {missing}")
    if overlap:
        raise ValueError(f"Rare modules present in default scheduler universe: {overlap}")
    return {
        "default_signal_keys": default_keys,
        "rare_signal_keys": sorted(rare_keys),
        "default_module_count": len(default_keys),
        "rare_module_count_excluded": len(rare_keys),
        "rare_modules_default_scheduler_included": False,
    }


def _is_rare_row(row: Any) -> bool:
    return (
        str(getattr(row, "research_track", "")) == "rare_setup_research_signal"
        or str(getattr(row, "portfolio_role", "")) == "rare_setup_module"
        or "rare" in str(getattr(row, "portfolio_contribution_status", "")).lower()
    )


def replay_default_modules(bars: pd.DataFrame, signal_keys: list[str]) -> dict[str, Any]:
    by_phase: dict[str, list[str]] = {}
    for key in signal_keys:
        phase, candidate = key.split("::", 1)
        by_phase.setdefault(phase, []).append(candidate)
    trades: list[pd.DataFrame] = []
    status: dict[str, dict[str, Any]] = {}
    replay_handlers = {
        "phase10b": _replay_phase10b,
        "phase11a": _replay_phase11a,
        "phase13a": _replay_phase13a,
        "phase14a": _replay_phase14a,
    }
    for phase, candidates in sorted(by_phase.items()):
        handler = replay_handlers.get(phase)
        if handler is None:
            for candidate in candidates:
                status[f"{phase}::{candidate}"] = {"backfill_status": "unavailable_for_backfill", "reason": "No faithful existing replay handler for phase"}
            continue
        replay_candidates = list(candidates)
        if phase == "phase10b":
            phase10b_specs = {spec.candidate_id: spec for spec in build_phase10b_specs()}
            unsafe = [candidate for candidate in candidates if phase10b_specs[candidate].range_filter != "all_ranges"]
            replay_candidates = [candidate for candidate in candidates if candidate not in unsafe]
            for candidate in unsafe:
                status[f"{phase}::{candidate}"] = {
                    "backfill_status": "unavailable_for_backfill",
                    "reason": "Existing range-filter definition uses full-sample percentile rank; causal full-history replay would require changing or approximating the registered module.",
                }
        try:
            phase_trades = handler(bars, replay_candidates)
        except Exception as exc:  # fail closed: never approximate unavailable labels
            for candidate in replay_candidates:
                status[f"{phase}::{candidate}"] = {"backfill_status": "unavailable_for_backfill", "reason": f"Existing replay failed: {type(exc).__name__}: {exc}"}
            continue
        for candidate in replay_candidates:
            key = f"{phase}::{candidate}"
            status[key] = {"backfill_status": "backfilled", "reason": "Replayed with existing deterministic phase spec and simulator"}
        if not phase_trades.empty:
            phase_trades = phase_trades.copy()
            phase_trades["phase"] = phase
            phase_trades["signal_key"] = phase_trades["phase"].astype(str) + "::" + phase_trades["candidate_id"].astype(str)
            trades.append(phase_trades)
    combined = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    if not combined.empty:
        combined["entry_time"] = pd.to_datetime(combined["entry_time"], utc=True)
        combined["exit_time"] = pd.to_datetime(combined["exit_time"], utc=True)
        combined["trading_session"] = combined["trading_session"].astype(str)
        combined["net_pnl"] = pd.to_numeric(combined["net_pnl"], errors="raise")
    return {"trades": combined, "module_status": status}


def _selected_specs(specs: list[Any], candidates: list[str]) -> list[Any]:
    by_id = {spec.candidate_id: spec for spec in specs}
    missing = sorted(set(candidates) - set(by_id))
    if missing:
        raise ValueError(f"Configured module specs not found: {missing}")
    return [by_id[candidate] for candidate in candidates]


def _replay_phase10b(bars: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    specs = _selected_specs(build_phase10b_specs(), candidates)
    base = _build_base_trade_pool(bars, specs)
    frames = []
    for spec in specs:
        base_id = _as_10a_spec(spec).candidate_id
        frame = apply_phase10b_pre_entry_filters(base[base["base_candidate_id"].eq(base_id)], spec)
        if not frame.empty:
            frame = frame.copy()
            frame["candidate_id"] = spec.candidate_id
            add_phase10b_costs(frame)
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _replay_phase11a(bars: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    specs = _selected_specs(build_phase11a_specs(), candidates)
    cache: dict[str, pd.DataFrame] = {}
    frames = []
    for spec in specs:
        cache.setdefault(spec.or_window, build_phase11a_feature_bars(bars, spec))
        features = cache[spec.or_window]
        frame, _ = simulate_phase11a_trades(features, generate_phase11a_signals(features, spec), spec)
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _replay_phase13a(bars: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    specs = _selected_specs(build_phase13a_specs(), candidates)
    cache: dict[str, pd.DataFrame] = {}
    frames = []
    for spec in specs:
        cache.setdefault(spec.family, build_phase13a_feature_bars(bars, spec))
        features = cache[spec.family]
        frame, _ = simulate_phase13a_trades(features, generate_phase13a_signals(features, spec), spec)
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _replay_phase14a(bars: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    specs = _selected_specs(build_phase14a_specs(), candidates)
    cache: dict[str, pd.DataFrame] = {}
    frames = []
    for spec in specs:
        cache.setdefault(spec.level_type, build_phase14a_feature_bars(bars, spec))
        features = cache[spec.level_type]
        frame, _ = simulate_phase14a_trades(features, generate_phase14a_signals(features, spec), spec)
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_module_daily_outcome(sessions: list[str], universe: dict[str, Any], replay: dict[str, Any]) -> pd.DataFrame:
    trades = replay["trades"]
    grouped: dict[tuple[str, str], tuple[int, float]] = {}
    if not trades.empty:
        summary = trades.groupby(["signal_key", "trading_session"])["net_pnl"].agg(["size", "sum"])
        grouped = {(str(key), str(day)): (int(row["size"]), float(row["sum"])) for (key, day), row in summary.iterrows()}
    rows = []
    for key in universe["default_signal_keys"]:
        phase, candidate = key.split("::", 1)
        info = replay["module_status"].get(key, {"backfill_status": "unavailable_for_backfill", "reason": "missing replay status"})
        reliable = info["backfill_status"] == "backfilled"
        for day in sessions:
            trade_count, pnl = grouped.get((key, day), (0, 0.0))
            rows.append({
                "trading_session": day,
                "phase": phase,
                "candidate_id": candidate,
                "signal_key": key,
                "default_scheduler_eligible": True,
                "rare_module": False,
                "backfill_status": info["backfill_status"],
                "backfill_note": info["reason"],
                "reliable_outcome_coverage": reliable,
                "accepted_trade_count": trade_count if reliable else np.nan,
                "daily_net_pnl": round(pnl, 2) if reliable else np.nan,
                "active_day": bool(reliable and trade_count > 0),
                "outcome_status": outcome_status(reliable, trade_count, pnl),
            })
    return pd.DataFrame(rows)


def build_playbook_daily_outcome(sessions: list[str], universe: dict[str, Any], replay: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = replay["trades"]
    all_available = all(replay["module_status"].get(key, {}).get("backfill_status") == "backfilled" for key in universe["default_signal_keys"])
    accepted = pd.DataFrame()
    if all_available and not trades.empty:
        order = {key: rank for rank, key in enumerate(universe["default_signal_keys"])}
        accepted, _, _, _, _ = construct_scheduled_trades(trades, universe["default_signal_keys"], order, "one_trade_at_a_time_chronological")
    grouped: dict[str, tuple[int, float]] = {}
    if not accepted.empty:
        summary = accepted.groupby("trading_session")["net_pnl"].agg(["size", "sum"])
        grouped = {str(day): (int(row["size"]), float(row["sum"])) for day, row in summary.iterrows()}
    rows = []
    for day in sessions:
        trade_count, pnl = grouped.get(day, (0, 0.0))
        rows.append({
            "trading_session": day,
            "scheduler_policy_name": "playbook_scheduler_f_rare_module_exclusion_policy",
            "scheduler_priority_rule": "policy recommended_default_scheduler_universe signal_keys order",
            "scheduler_mode": "one_trade_at_a_time_chronological",
            "default_module_count": universe["default_module_count"],
            "rare_module_count_excluded": universe["rare_module_count_excluded"],
            "reliable_scheduler_coverage": all_available,
            "accepted_trade_count": trade_count if all_available else np.nan,
            "daily_net_pnl": round(pnl, 2) if all_available else np.nan,
            "active_day": bool(all_available and trade_count > 0),
            "outcome_status": outcome_status(all_available, trade_count, pnl),
        })
    return pd.DataFrame(rows), accepted


def outcome_status(reliable: bool, trade_count: int, pnl: float) -> str:
    if not reliable:
        return "missing_source_day"
    if trade_count == 0:
        return "no_trade_day"
    if pnl > 0:
        return "active_day_positive"
    if pnl < 0:
        return "active_day_negative"
    return "active_day_zero_result"


def build_coverage_audit(dataset: pd.DataFrame, universe: dict[str, Any], module_daily: pd.DataFrame, playbook_daily: pd.DataFrame, replay: dict[str, Any]) -> pd.DataFrame:
    sessions = dataset["trading_session"].astype(str)
    first_module = _first_true_date(module_daily, "reliable_outcome_coverage")
    first_scheduler = _first_true_date(playbook_daily, "reliable_scheduler_coverage")
    pre_mid_2025 = sessions.lt("2025-07-01")
    module_covered_days = set(module_daily.loc[module_daily["reliable_outcome_coverage"].eq(True), "trading_session"].astype(str))
    scheduler_covered_days = set(playbook_daily.loc[playbook_daily["reliable_scheduler_coverage"].eq(True), "trading_session"].astype(str))
    backfilled = sum(v.get("backfill_status") == "backfilled" for v in replay["module_status"].values())
    unavailable = universe["default_module_count"] - backfilled
    rows = [
        {"audit_item": "dataset_rows", "value": len(dataset), "status": "observed", "detail": f"{sessions.min()} to {sessions.max()}"},
        {"audit_item": "dataset_c_discovery_active_days", "value": int(pd.Series(dataset.get("scheduler_active_day_c", False)).fillna(False).astype(bool)[dataset["chronological_split"].eq("discovery")].sum()), "status": "diagnosed", "detail": "Dataset C used recent 252-session phase/scheduler artifacts, so discovery predates source coverage."},
        {"audit_item": "first_date_with_any_module_outcome_coverage", "value": first_module or "", "status": "backfilled" if first_module else "missing", "detail": "Reliable only after faithful deterministic replay; missing is never no-trade."},
        {"audit_item": "first_date_with_scheduler_playbook_coverage", "value": first_scheduler or "", "status": "backfilled" if first_scheduler else "missing", "detail": "Current default non-rare universe with chronological one-trade-at-a-time scheduling."},
        {"audit_item": "pre_mid_2025_rows", "value": int(pre_mid_2025.sum()), "status": "diagnosed", "detail": "These were missing outcome-label coverage in Dataset C, not established no-trade days."},
        {"audit_item": "pre_mid_2025_reliable_module_days", "value": int(sum(day in module_covered_days for day in sessions[pre_mid_2025])), "status": "backfilled", "detail": "Unique dataset days with reliable module replay coverage."},
        {"audit_item": "pre_mid_2025_reliable_scheduler_days", "value": int(sum(day in scheduler_covered_days for day in sessions[pre_mid_2025])), "status": "backfilled", "detail": "Unique dataset days with reliable scheduler replay coverage."},
        {"audit_item": "coverage_problem_classification", "value": "historical_labels_missing_and_split_misaligned", "status": "diagnosed", "detail": "Original active labels were unsuitable because recent-only outcomes omitted discovery and placed active rows in later splits."},
        {"audit_item": "default_module_count", "value": universe["default_module_count"], "status": "policy", "detail": "Non-rare modules listed by scheduler policy."},
        {"audit_item": "rare_module_count_excluded", "value": universe["rare_module_count_excluded"], "status": "policy", "detail": "Registry-only rare modules excluded from default scheduler labels."},
        {"audit_item": "backfilled_module_count", "value": backfilled, "status": "complete" if unavailable == 0 else "partial", "detail": "Faithfully replayed existing deterministic modules."},
        {"audit_item": "unavailable_module_count", "value": unavailable, "status": "complete" if unavailable == 0 else "manual_required", "detail": "Modules not approximated when faithful replay was unavailable."},
    ]
    return pd.DataFrame(rows)


def _first_true_date(frame: pd.DataFrame, column: str) -> str | None:
    rows = frame[frame[column].eq(True)]
    return str(rows["trading_session"].astype(str).min()) if not rows.empty else None


def build_coverage_aligned_splits(dataset: pd.DataFrame, playbook: pd.DataFrame, modules: pd.DataFrame) -> tuple[dict[str, pd.Series], pd.DataFrame]:
    index = dataset.index
    original = dataset["chronological_split"].astype(str).replace({"discovery": "train"})
    scheduler_reliable = playbook.set_index("trading_session")["reliable_scheduler_coverage"].reindex(dataset["trading_session"].astype(str)).fillna(False).to_numpy(dtype=bool)
    module_by_day = modules.groupby("trading_session")["reliable_outcome_coverage"].all()
    module_reliable = module_by_day.reindex(dataset["trading_session"].astype(str)).fillna(False).to_numpy(dtype=bool)
    module_any_covered = modules.groupby("trading_session")["reliable_outcome_coverage"].any().reindex(dataset["trading_session"].astype(str)).fillna(False).to_numpy(dtype=bool)
    module_any_active = modules.groupby("trading_session")["active_day"].any().reindex(dataset["trading_session"].astype(str)).fillna(False).to_numpy(dtype=bool)
    # A row is labeled when at least one revised outcome target is known. A positive
    # any-module target is known even if another module is unavailable; a negative is
    # known only when all default modules are covered.
    labeled_mask = pd.Series(scheduler_reliable | module_any_active | module_reliable, index=index)
    first_reliable = dataset.loc[module_any_covered, "trading_session"].astype(str).min() if module_any_covered.any() else None
    active_mask = pd.Series(module_any_covered, index=index) & dataset["trading_session"].astype(str).ge(first_reliable or "9999-12-31")
    variants: dict[str, pd.Series] = {
        "original_dataset_split": original,
        "labeled_coverage_chronological_split": chronological_labels(labeled_mask),
        "active_coverage_chronological_split": chronological_labels(active_mask),
    }
    covered_idx = dataset.index[labeled_mask].tolist()
    n = len(covered_idx)
    if n >= 300:
        for fold, train_frac in enumerate((0.40, 0.50, 0.60), start=1):
            train_end = int(n * train_frac)
            val_end = min(n, train_end + int(n * 0.10))
            hold_end = min(n, val_end + int(n * 0.10)) if fold < 3 else n
            labels = pd.Series("excluded", index=index, dtype="object")
            labels.loc[covered_idx[:train_end]] = "train"
            labels.loc[covered_idx[train_end:val_end]] = "validation"
            labels.loc[covered_idx[val_end:hold_end]] = "holdout"
            variants[f"rolling_labeled_fold_{fold}"] = labels
    scheduler_active = playbook.set_index("trading_session")["active_day"].reindex(dataset["trading_session"].astype(str)).fillna(False).to_numpy(dtype=bool)
    module_active_by_day = modules.groupby("trading_session")["active_day"].any()
    module_active = module_active_by_day.reindex(dataset["trading_session"].astype(str)).fillna(False).to_numpy(dtype=bool)
    rows = []
    dates = dataset["trading_session"].astype(str)
    for variant, labels in variants.items():
        for split in ("train", "validation", "holdout", "excluded"):
            mask = labels.eq(split)
            rows.append({
                "split_variant": variant,
                "split": split,
                "rows": int(mask.sum()),
                "date_start": dates[mask].min() if mask.any() else "",
                "date_end": dates[mask].max() if mask.any() else "",
                "scheduler_active_days": int((mask.to_numpy() & scheduler_active).sum()),
                "module_active_days": int((mask.to_numpy() & module_active).sum()),
                "chronological": True,
                "deterministic": True,
            })
    return variants, pd.DataFrame(rows)


def chronological_labels(mask: pd.Series) -> pd.Series:
    labels = pd.Series("excluded", index=mask.index, dtype="object")
    positions = mask.index[mask].tolist()
    n = len(positions)
    train_end = int(n * 0.60)
    validation_end = int(n * 0.80)
    labels.loc[positions[:train_end]] = "train"
    labels.loc[positions[train_end:validation_end]] = "validation"
    labels.loc[positions[validation_end:]] = "holdout"
    return labels


def build_dataset_d(dataset_c: pd.DataFrame, playbook: pd.DataFrame, module_daily: pd.DataFrame, splits: dict[str, pd.Series]) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = dataset_c.copy()
    out["original_dataset_split"] = out["chronological_split"].astype(str)
    out["labeled_coverage_chronological_split"] = splits["labeled_coverage_chronological_split"]
    out["active_coverage_chronological_split"] = splits["active_coverage_chronological_split"]
    for name, labels in splits.items():
        if name.startswith("rolling_labeled_fold_"):
            out[name] = labels
    play = playbook.set_index("trading_session").reindex(out["trading_session"].astype(str))
    out["default_scheduler_outcome_status_d"] = play["outcome_status"].to_numpy()
    out["default_scheduler_daily_pnl_d"] = pd.to_numeric(play["daily_net_pnl"], errors="coerce").to_numpy()
    out["default_scheduler_accepted_trade_count_d"] = pd.to_numeric(play["accepted_trade_count"], errors="coerce").to_numpy()
    scheduler_reliable = play["reliable_scheduler_coverage"].fillna(False).to_numpy(dtype=bool)
    active = scheduler_reliable & (out["default_scheduler_accepted_trade_count_d"].fillna(0).to_numpy() > 0)
    pnl = out["default_scheduler_daily_pnl_d"]
    out["target_default_scheduler_active_day_d"] = nullable_bool(np.where(scheduler_reliable, active, np.nan), out.index)
    out["target_default_scheduler_active_day_loss_d"] = nullable_bool(np.where(active & pnl.ne(0), pnl.lt(0), np.nan), out.index)

    training_mask = splits["labeled_coverage_chronological_split"].eq("train") & pd.Series(active, index=out.index)
    training_active_pnl = pnl[training_mask & pnl.notna()]
    threshold = float(training_active_pnl.quantile(0.25)) if len(training_active_pnl) else np.nan
    out["target_default_scheduler_active_day_large_loss_d"] = nullable_bool(np.where(active & pnl.notna() & np.isfinite(threshold), pnl.le(threshold), np.nan), out.index)

    modules = module_daily[module_daily["default_scheduler_eligible"].eq(True)].copy()
    day_summary = modules.groupby("trading_session").agg(
        reliable_module_coverage=("reliable_outcome_coverage", "all"),
        any_module_active=("accepted_trade_count", lambda s: bool(pd.to_numeric(s, errors="coerce").fillna(0).gt(0).any())),
        any_module_positive=("daily_net_pnl", lambda s: bool(pd.to_numeric(s, errors="coerce").gt(0).any())),
    )
    day_summary = day_summary.reindex(out["trading_session"].astype(str))
    module_reliable = day_summary["reliable_module_coverage"].fillna(False).to_numpy(dtype=bool)
    any_active = day_summary["any_module_active"].fillna(False).to_numpy(dtype=bool)
    any_positive = day_summary["any_module_positive"].fillna(False).to_numpy(dtype=bool)
    out["target_any_default_module_opportunity_d"] = nullable_bool(
        np.where(any_active, True, np.where(module_reliable, False, np.nan)), out.index
    )
    missed_eligible = scheduler_reliable & module_reliable & ~active
    out["target_missed_default_module_opportunity_d"] = nullable_bool(np.where(missed_eligible, any_positive, np.nan), out.index)

    weak = _bool_series(out.get("playbook_weak_fold_day"), out.index)
    high_vol_adverse = _bool_series(out.get("target_high_vol_mixed_weak_day"), out.index)
    bad = (active & pnl.lt(0).to_numpy()) | weak.to_numpy() | high_vol_adverse.to_numpy()
    good = active & pnl.gt(0).to_numpy() & ~weak.to_numpy() & ~high_vol_adverse.to_numpy()
    sufficient = scheduler_reliable & (active | weak.to_numpy() | high_vol_adverse.to_numpy())
    out["target_bad_regime_d"] = nullable_bool(np.where(sufficient, np.where(bad, True, np.where(good, False, np.nan)), np.nan), out.index)
    threshold_info = {
        "thresholds_fit_split_variant": "labeled_coverage_chronological_split",
        "thresholds_fit_split": "train",
        "large_loss_threshold_rule": "25th percentile of default scheduler active-day PnL in labeled-coverage training rows only",
        "large_loss_threshold": threshold if np.isfinite(threshold) else None,
        "training_active_rows_used": int(len(training_active_pnl)),
    }
    return out, threshold_info


def nullable_bool(values: Any, index: pd.Index) -> pd.Series:
    return pd.Series(values, index=index, dtype="object").map(lambda value: np.nan if pd.isna(value) else bool(value))


def _bool_series(values: Any, index: pd.Index) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.astype(str).str.lower().isin({"true", "1", "yes"}).fillna(False)
    return pd.Series(False, index=index, dtype=bool)


def build_target_balance_by_split(dataset: pd.DataFrame, splits: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    recent = _bool_series(dataset.get("recent_oos_like"), dataset.index)
    for variant, labels in splits.items():
        for target in TARGETS_D:
            if target not in dataset:
                continue
            masks = [("full", labels.ne("excluded")), ("train", labels.eq("train")), ("validation", labels.eq("validation")), ("holdout", labels.eq("holdout")), ("recent_oos_like", labels.ne("excluded") & recent)]
            for split, mask in masks:
                values = dataset.loc[mask, target].dropna()
                truth = values.map(lambda value: str(value).lower() in {"true", "1"})
                rows.append({
                    "split_variant": variant,
                    "target_name": target,
                    "split": split,
                    "rows": int(mask.sum()),
                    "non_null_rows": int(len(values)),
                    "null_rows": int(mask.sum() - len(values)),
                    "true_count": int(truth.sum()),
                    "false_count": int((~truth).sum()),
                    "positive_rate_non_null": round(float(truth.mean()), 6) if len(values) else np.nan,
                })
    return pd.DataFrame(rows)


def build_target_readiness_summary(balance: pd.DataFrame, dataset_c: pd.DataFrame, leakage_audit: pd.DataFrame | None = None) -> pd.DataFrame:
    leakage_free = _leakage_free(dataset_c, leakage_audit)
    rows = []
    for (variant, target), group in balance.groupby(["split_variant", "target_name"], sort=True):
        lookup = {row.split: row for row in group.itertuples(index=False)}
        full = lookup.get("full")
        train = lookup.get("train")
        validation = lookup.get("validation")
        holdout = lookup.get("holdout")
        recent = lookup.get("recent_oos_like")
        checks = {
            "total_non_null_rows>=300": bool(full and full.non_null_rows >= 300),
            "overall_true>=50": bool(full and full.true_count >= 50),
            "overall_false>=50": bool(full and full.false_count >= 50),
            "train_true>=30": bool(train and train.true_count >= 30),
            "train_false>=30": bool(train and train.false_count >= 30),
            "validation_true>=15": bool(validation and validation.true_count >= 15),
            "validation_false>=15": bool(validation and validation.false_count >= 15),
            "holdout_true>=15": bool(holdout and holdout.true_count >= 15),
            "holdout_false>=15": bool(holdout and holdout.false_count >= 15),
            "no_leakage_flags": leakage_free,
            "not_diagnostic_only": target not in DIAGNOSTIC_TARGETS_D,
        }
        trainable = all(checks.values())
        rows.append({
            "split_variant": variant,
            "target_name": target,
            "total_non_null_rows": int(full.non_null_rows if full else 0),
            "true_count": int(full.true_count if full else 0),
            "false_count": int(full.false_count if full else 0),
            "discovery_train_true": int(train.true_count if train else 0),
            "discovery_train_false": int(train.false_count if train else 0),
            "validation_true": int(validation.true_count if validation else 0),
            "validation_false": int(validation.false_count if validation else 0),
            "holdout_true": int(holdout.true_count if holdout else 0),
            "holdout_false": int(holdout.false_count if holdout else 0),
            "recent_oos_like_true": int(recent.true_count if recent else 0),
            "recent_oos_like_false": int(recent.false_count if recent else 0),
            "trainable_for_baseline_b": trainable,
            "failed_rules_json": json.dumps([name for name, passed in checks.items() if not passed], sort_keys=True),
            "no_leakage_flags": leakage_free,
            "diagnostic_only": target in DIAGNOSTIC_TARGETS_D,
        })
    return pd.DataFrame(rows)


def _leakage_free(dataset_c: pd.DataFrame, leakage_audit: pd.DataFrame | None = None) -> bool:
    if leakage_audit is None:
        return True
    required = {"status", "flag_count"}
    if not required.issubset(leakage_audit.columns):
        return False
    statuses_pass = leakage_audit["status"].astype(str).str.lower().eq("pass").all()
    no_flags = pd.to_numeric(leakage_audit["flag_count"], errors="coerce").fillna(1).eq(0).all()
    return bool(statuses_pass and no_flags)


def build_label_dictionary_d(label_c: dict[str, Any], readiness: pd.DataFrame, threshold_info: dict[str, Any]) -> dict[str, Any]:
    labels = dict(label_c)
    trainable = set(readiness.loc[readiness["trainable_for_baseline_b"].eq(True), "target_name"].astype(str))
    definitions = {
        "target_default_scheduler_active_day_d": "True when the replayed current default non-rare scheduler accepted at least one trade; false on reliable no-trade days; null when scheduler coverage is missing.",
        "target_default_scheduler_active_day_loss_d": "Among active days only, true when scheduler daily PnL is negative and false when positive; null on no-trade, zero-result, or missing-source days.",
        "target_default_scheduler_active_day_large_loss_d": f"Among active days, true at or below the labeled-training active-day 25th percentile ({threshold_info.get('large_loss_threshold')}); threshold fit on training only.",
        "target_any_default_module_opportunity_d": "True when any non-rare default-scheduler-eligible module traded; false only when reliable module coverage exists and none traded; null when coverage is missing.",
        "target_missed_default_module_opportunity_d": "On reliable scheduler no-trade days, true when any default module had positive daily PnL and false otherwise; null on scheduler-active or missing days.",
        "target_bad_regime_d": "Diagnostic composite: active-day loss or existing weak-fold/high-vol adverse label; false for profitable active days without adverse labels; null when insufficient.",
        "target_prior_level_interaction_day": "Carried-forward diagnostic-only target.",
        "target_power_hour_expansion_day": "Carried-forward diagnostic-only target.",
    }
    for target, definition in definitions.items():
        labels[target] = {
            "role": "target",
            "is_target": True,
            "is_feature": False,
            "definition": definition,
            "allowed_values": "True, False, blank/null",
            "null_meaning": "Insufficient reliable outcome coverage or target not applicable; null is never coerced to false or zero.",
            "prediction_use": "candidate for coverage-aligned baseline" if target in trainable else "not trainable under ML Target D readiness rules",
            "trainable_for_baseline_b": target in trainable,
            "diagnostic_only": target in DIAGNOSTIC_TARGETS_D,
            "leakage_notes": "Outcome label only; excluded from feature dictionary.",
        }
    return dict(sorted(labels.items()))


def build_next_action_recommendation(readiness: pd.DataFrame, coverage: pd.DataFrame, dataset: pd.DataFrame) -> dict[str, Any]:
    passing = readiness[readiness["trainable_for_baseline_b"].eq(True)].copy()
    unavailable = int(coverage.loc[coverage["audit_item"].eq("unavailable_module_count"), "value"].iloc[0])
    backfilled = int(coverage.loc[coverage["audit_item"].eq("backfilled_module_count"), "value"].iloc[0])
    default_count = int(coverage.loc[coverage["audit_item"].eq("default_module_count"), "value"].iloc[0])
    if not passing.empty:
        action = "ml_baseline_b_train_coverage_aligned_classifier"
        rationale = "At least one outcome target/split pair passes all coverage, sample, class-balance, chronological split, and leakage readiness rules."
    elif unavailable:
        action = "manual_module_backfill_required"
        rationale = "At least one default module could not be faithfully replayed; missing coverage was left null and must not be approximated."
    elif backfilled < default_count:
        action = "backfill_default_playbook_outcomes_first"
        rationale = "Backfill is feasible but incomplete for the current default scheduler universe."
    elif int(dataset["default_scheduler_outcome_status_d"].ne("missing_source_day").sum()) < 300:
        action = "insufficient_labeled_history_for_playbook_ml"
        rationale = "Reliable playbook outcome history remains below the minimum labeled-row requirement."
    else:
        action = "ml_dataset_e_regime_only_targets"
        rationale = "Playbook outcome targets remain split/class sparse after complete backfill; stable regime-only targets are the feasible next dataset track."
    best = passing.sort_values(["total_non_null_rows", "true_count"], ascending=[False, False]).iloc[0].to_dict() if not passing.empty else None
    return {
        "next_action": action,
        "rationale": rationale,
        "best_trainable_target": best.get("target_name") if best else None,
        "best_trainable_split_variant": best.get("split_variant") if best else None,
        "trainable_target_split_pairs": passing[["target_name", "split_variant"]].to_dict("records"),
        "research_only": True,
        "model_trained": False,
        "generated_strategy_signals": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "rare_modules_default_scheduler_included": False,
        "strategy_search_performed": False,
        "strategy_candidates_promoted": False,
    }


def write_outputs(config: MlTargetDConfig, dataset: pd.DataFrame, playbook: pd.DataFrame, modules: pd.DataFrame, coverage: pd.DataFrame, split_summary: pd.DataFrame, balance: pd.DataFrame, labels: dict[str, Any], readiness: pd.DataFrame, recommendation: dict[str, Any], threshold_info: dict[str, Any], universe: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "report": config.report_dir / "ml_target_d_playbook_label_backfill_report.md",
        "dataset": config.output_dir / "ml_target_d_day_regime.csv",
        "playbook_daily": config.output_dir / "ml_target_d_playbook_daily_outcome.csv",
        "module_daily": config.output_dir / "ml_target_d_module_daily_outcome.csv",
        "coverage": config.output_dir / "ml_target_d_coverage_audit.csv",
        "split_summary": config.output_dir / "ml_target_d_split_summary.csv",
        "target_balance": config.output_dir / "ml_target_d_target_balance_by_split.csv",
        "label_dictionary": config.output_dir / "ml_target_d_label_dictionary.json",
        "target_readiness": config.output_dir / "ml_target_d_target_readiness_summary.csv",
        "recommendation": config.output_dir / "ml_target_d_next_action_recommendation.json",
    }
    for key, frame in (("dataset", dataset), ("playbook_daily", playbook), ("module_daily", modules), ("coverage", coverage), ("split_summary", split_summary), ("target_balance", balance), ("target_readiness", readiness)):
        write_csv_artifact(frame, paths[key])
    write_json_artifact(labels, paths["label_dictionary"])
    write_json_artifact(recommendation, paths["recommendation"])
    paths["report"].write_text(render_report(dataset, playbook, modules, coverage, split_summary, readiness, recommendation, threshold_info, universe), encoding="utf-8")
    for path in paths.values():
        destination = config.artifact_dir / path.name
        destination.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    write_json_artifact({
        "run_id": config.run_id,
        "threshold_info": threshold_info,
        "research_only": True,
        "model_trained": False,
        "generated_strategy_signals": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "rare_modules_default_scheduler_included": False,
        "paths": {key: str(path) for key, path in paths.items()},
    }, config.artifact_dir / "manifest.json")
    return paths


def render_report(dataset: pd.DataFrame, playbook: pd.DataFrame, modules: pd.DataFrame, coverage: pd.DataFrame, split_summary: pd.DataFrame, readiness: pd.DataFrame, recommendation: dict[str, Any], threshold_info: dict[str, Any], universe: dict[str, Any]) -> str:
    passing = readiness[readiness["trainable_for_baseline_b"].eq(True)]
    return "\n".join([
        "# ML Target D — Playbook Label Backfill and Coverage-Aligned Splits",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "This is a research-only label-coverage audit. No model training, new strategy search, strategy signals, live predictions, candidate promotion, official gate changes, paper-trading approval, or live-trading approval were performed.",
        "",
        "## Coverage diagnosis",
        markdown_table(coverage),
        "",
        "Missing module or scheduler outcome coverage is always `missing_source_day`; it is never treated as a no-trade zero. Dataset C's 2023–mid-2025 rows lacked recent-window outcome artifacts and were not proven no-trade days.",
        "",
        "## Default scheduler universe and backfill feasibility",
        f"- Default non-rare modules: {universe['default_module_count']}",
        f"- Rare modules excluded: {universe['rare_module_count_excluded']}",
        f"- Module daily rows: {len(modules)}",
        f"- Scheduler daily rows: {len(playbook)}",
        "- Scheduler mode: one_trade_at_a_time_chronological; priority is the policy's recommended signal-key order.",
        "",
        "## Daily outcome labels",
        "Statuses distinguish missing_source_day, no_trade_day, active_day_positive, active_day_negative, and active_day_zero_result. `active_day` is represented by the three explicit active result statuses.",
        "",
        "## Coverage-aligned splits",
        markdown_table(split_summary),
        "",
        "## Large-loss threshold",
        json.dumps(threshold_info, sort_keys=True),
        "",
        "## Target readiness",
        markdown_table(readiness),
        "",
        f"Passing target/split pairs: {len(passing)}",
        f"Best pair: {recommendation.get('best_trainable_target')} / {recommendation.get('best_trainable_split_variant')}",
        "",
        "## Recommendation",
        json.dumps(recommendation, indent=2, sort_keys=True),
        "",
        "## Guardrails",
        "- research_only: true",
        "- model_trained: false",
        "- generated_strategy_signals: false",
        "- official_gates_changed: false",
        "- paper_trading_approved: false",
        "- live_trading_approved: false",
        "- rare_modules_default_scheduler_included: false",
        "",
    ])
