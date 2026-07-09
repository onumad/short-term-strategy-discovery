from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL
from .ml_dataset_b_feature_target_quality import markdown_table
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact

NEW_AUDIT_COLUMNS = [
    "playbook_active_day_c",
    "scheduler_active_day_c",
    "any_module_active_day_c",
    "default_scheduler_module_active_day_c",
    "rare_module_active_day_c",
    "no_trade_day_c",
    "missing_pnl_source_day_c",
]

REVISED_TARGETS_C = [
    "target_active_day_loss_c",
    "target_active_day_large_loss_c",
    "target_any_module_active_day_c",
    "target_no_trade_but_module_positive_c",
    "target_bad_regime_c",
]

DIAGNOSTIC_TARGETS_C = [
    "target_prior_level_interaction_day",
    "target_power_hour_expansion_day",
]

CANDIDATE_TARGETS_C = [*REVISED_TARGETS_C, *DIAGNOSTIC_TARGETS_C]
PHASE_GROUPS = ["phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a", "phase16a", "phase17a"]
RARE_PHASE_GROUPS = {"phase16a", "phase17a"}
DEFAULT_SCHEDULER_PHASE_GROUPS = [p for p in PHASE_GROUPS if p not in RARE_PHASE_GROUPS]
TRAINABILITY_RULES = {
    "min_total_non_null_rows": 300,
    "min_overall_true": 50,
    "min_overall_false": 50,
    "min_discovery_true": 30,
    "min_discovery_false": 30,
    "min_validation_true": 15,
    "min_validation_false": 15,
    "min_holdout_true": 15,
    "min_holdout_false": 15,
}


@dataclass(frozen=True)
class MlTargetCConfig:
    dataset_b_path: Path
    label_dictionary_b_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    candidate_pnl_sources: dict[str, Path]
    run_id: str = "ml-target-c-r1"


def build_ml_target_c_manual_target_definition(project_root: Path, run_id: str = "ml-target-c-r1") -> dict[str, Any]:
    outputs = project_root / "outputs"
    candidate_sources = {
        "portfolio_audit_e_portfolio_daily_pnl": outputs / "portfolio_audit_e_portfolio_daily_pnl.csv",
        "playbook_scheduler_e_daily_pnl": outputs / "playbook_scheduler_e_daily_pnl.csv",
        "playbook_scheduler_d_daily_pnl": outputs / "playbook_scheduler_d_daily_pnl.csv",
        "playbook_scheduler_c_daily_pnl": outputs / "playbook_scheduler_c_daily_pnl.csv",
    }
    for phase in PHASE_GROUPS:
        candidate_sources[f"{phase}_daily_pnl"] = outputs / f"{phase}_daily_pnl.csv"
    config = MlTargetCConfig(
        dataset_b_path=outputs / "ml_dataset_b_day_regime.csv",
        label_dictionary_b_path=outputs / "ml_dataset_b_label_dictionary.json",
        output_dir=outputs,
        report_dir=project_root / "reports",
        artifact_dir=project_root / "artifacts" / "ml_target_c_manual_target_definition" / run_id,
        candidate_pnl_sources=candidate_sources,
        run_id=run_id,
    )
    return run_ml_target_c_manual_target_definition(config)


def run_ml_target_c_manual_target_definition(config: MlTargetCConfig) -> dict[str, Any]:
    ensure_directory(config.output_dir)
    ensure_directory(config.report_dir)
    ensure_directory(config.artifact_dir)
    dataset_b = pd.read_csv(config.dataset_b_path)
    label_dict_b = json.loads(config.label_dictionary_b_path.read_text(encoding="utf-8"))
    validate_dataset_b(dataset_b, label_dict_b)

    pnl_source_coverage = build_pnl_source_coverage(dataset_b, config.candidate_pnl_sources)
    dataset_c, threshold_info = build_dataset_c(dataset_b)
    active_day_audit = build_active_day_audit(dataset_c)
    target_balance = build_target_balance_by_split(dataset_c, CANDIDATE_TARGETS_C)
    target_quality = build_target_quality_summary(dataset_c, target_balance, threshold_info)
    readiness = build_target_readiness_summary(target_quality)
    label_dictionary = build_label_dictionary_c(label_dict_b, dataset_c, readiness, threshold_info)
    recommendation = build_next_action_recommendation(dataset_c, readiness, pnl_source_coverage, target_quality, threshold_info)
    paths = write_outputs(config, dataset_c, label_dictionary, target_balance, target_quality, pnl_source_coverage, active_day_audit, readiness, recommendation, threshold_info)
    return {
        "dataset": dataset_c,
        "label_dictionary": label_dictionary,
        "target_balance_by_split": target_balance,
        "target_quality_summary": target_quality,
        "pnl_source_coverage": pnl_source_coverage,
        "active_day_audit": active_day_audit,
        "target_readiness_summary": readiness,
        "next_action_recommendation": recommendation,
        "threshold_info": threshold_info,
        "paths": paths,
    }


def validate_dataset_b(dataset: pd.DataFrame, label_dict: dict[str, Any]) -> None:
    required = {"trading_session", "chronological_split", "recent_oos_like", "scheduler_daily_pnl", "playbook_daily_pnl"}
    missing = sorted(required - set(dataset.columns))
    if missing:
        raise ValueError(f"Dataset B is missing required columns: {missing}")
    if not label_dict:
        raise ValueError("Dataset B label dictionary is empty")


def bool_series(values: Any, index: pd.Index | None = None) -> pd.Series:
    if isinstance(values, pd.Series):
        if values.dtype == bool:
            return values.fillna(False)
        return values.astype(str).str.lower().isin({"true", "1", "yes"}).fillna(False)
    if index is None:
        return pd.Series(dtype=bool)
    return pd.Series(False, index=index, dtype=bool)


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype="float64")


def build_dataset_c(dataset_b: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = dataset_b.copy()
    out["playbook_active_day_c"] = bool_series(out.get("playbook_active_day"), out.index)
    if "scheduler_no_trade_day" in out.columns:
        out["scheduler_active_day_c"] = ~bool_series(out["scheduler_no_trade_day"], out.index)
    else:
        out["scheduler_active_day_c"] = bool_series(out.get("scheduler_positive_day"), out.index) | bool_series(out.get("scheduler_negative_day"), out.index) | numeric_column(out, "scheduler_daily_pnl").ne(0)
    phase_active_cols = []
    for phase in PHASE_GROUPS:
        active_col = f"{phase}_active"
        pnl_col = f"{phase}_daily_pnl"
        if active_col in out.columns:
            active = bool_series(out[active_col], out.index)
        else:
            active = numeric_column(out, pnl_col).notna() & numeric_column(out, pnl_col).ne(0)
        out[f"{phase}_active_c"] = active
        phase_active_cols.append(f"{phase}_active_c")
    out["any_module_active_day_c"] = out[phase_active_cols].any(axis=1)
    out["default_scheduler_module_active_day_c"] = out[[f"{p}_active_c" for p in DEFAULT_SCHEDULER_PHASE_GROUPS]].any(axis=1)
    out["rare_module_active_day_c"] = out[[f"{p}_active_c" for p in RARE_PHASE_GROUPS]].any(axis=1)
    selected_pnl = choose_selected_pnl(out)
    selected_active = out["scheduler_active_day_c"] | out["playbook_active_day_c"]
    out["selected_scheduler_or_playbook_pnl_c"] = selected_pnl
    out["missing_pnl_source_day_c"] = selected_pnl.isna()
    out["no_trade_day_c"] = (~selected_active) & (~out["missing_pnl_source_day_c"])

    active_valid = selected_active & selected_pnl.notna()
    out["target_active_day_loss_c"] = nullable_bool(np.where(active_valid, selected_pnl.lt(0), np.nan), out.index)

    discovery_active_pnl = selected_pnl[active_valid & out["chronological_split"].astype(str).eq("discovery")]
    discovery_negative_count = int(discovery_active_pnl.lt(0).sum())
    threshold_available = discovery_negative_count >= 30 and int(discovery_active_pnl.notna().sum()) >= 60
    large_loss_threshold = float(discovery_active_pnl.quantile(0.25)) if threshold_available else np.nan
    out["target_active_day_large_loss_c"] = nullable_bool(np.where(active_valid & threshold_available, selected_pnl.le(large_loss_threshold), np.nan), out.index)

    out["target_any_module_active_day_c"] = out["default_scheduler_module_active_day_c"].astype(bool)
    default_module_positive = pd.Series(False, index=out.index)
    for phase in DEFAULT_SCHEDULER_PHASE_GROUPS:
        default_module_positive |= numeric_column(out, f"{phase}_daily_pnl").gt(0)
    missed_mask = out["no_trade_day_c"] & (~out["missing_pnl_source_day_c"])
    out["target_no_trade_but_module_positive_c"] = nullable_bool(np.where(missed_mask, default_module_positive, np.nan), out.index)

    weak_fold = bool_series(out.get("playbook_weak_fold_day"), out.index)
    high_vol_adverse = bool_series(out.get("target_high_vol_mixed_weak_day"), out.index) | (bool_series(out.get("strict_high_vol_mixed_flag"), out.index) & active_valid & selected_pnl.lt(0))
    bad = (active_valid & selected_pnl.lt(0)) | weak_fold | high_vol_adverse
    good_active = active_valid & selected_pnl.gt(0) & (~weak_fold) & (~high_vol_adverse)
    out["target_bad_regime_c"] = nullable_bool(np.where(bad, True, np.where(good_active, False, np.nan)), out.index)

    threshold_info = {
        "thresholds_fit_split": "discovery",
        "selected_pnl_source_rule": "scheduler_daily_pnl on scheduler active days, otherwise playbook_daily_pnl on playbook active days; no missing PnL is imputed as zero",
        "large_loss_threshold_rule": "25th percentile of discovery active-day selected scheduler/playbook PnL, only when discovery has at least 30 negative active days and 60 active observations",
        "large_loss_threshold": large_loss_threshold if np.isfinite(large_loss_threshold) else None,
        "discovery_active_rows_used_for_large_loss_threshold": int(discovery_active_pnl.notna().sum()),
        "discovery_negative_examples_for_large_loss_threshold": discovery_negative_count,
        "large_loss_threshold_available": bool(threshold_available),
    }
    return out, threshold_info


def choose_selected_pnl(frame: pd.DataFrame) -> pd.Series:
    scheduler = numeric_column(frame, "scheduler_daily_pnl")
    playbook = numeric_column(frame, "playbook_daily_pnl")
    selected = pd.Series(np.nan, index=frame.index, dtype="float64")
    selected.loc[frame["scheduler_active_day_c"]] = scheduler.loc[frame["scheduler_active_day_c"]]
    fallback = frame["playbook_active_day_c"] & selected.isna()
    selected.loc[fallback] = playbook.loc[fallback]
    no_trade = (~frame["scheduler_active_day_c"]) & (~frame["playbook_active_day_c"])
    selected.loc[no_trade & scheduler.notna()] = scheduler.loc[no_trade & scheduler.notna()]
    selected.loc[no_trade & scheduler.isna() & playbook.notna()] = playbook.loc[no_trade & scheduler.isna() & playbook.notna()]
    return selected


def nullable_bool(values: Any, index: pd.Index) -> pd.Series:
    return pd.Series(values, index=index, dtype="object").map(lambda v: np.nan if pd.isna(v) else bool(v))


def build_pnl_source_coverage(dataset: pd.DataFrame, sources: dict[str, Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    sessions = dataset[["trading_session", "chronological_split"]].copy()
    sessions["trading_session"] = sessions["trading_session"].astype(str)
    for name, path in sources.items():
        if not path.exists():
            rows.append(missing_source_row(name, path, sessions))
            continue
        frame = pd.read_csv(path)
        if "trading_session" not in frame.columns or "net_pnl" not in frame.columns:
            rows.append(missing_source_row(name, path, sessions, present=True, note="missing required trading_session/net_pnl columns"))
            continue
        frame = frame.copy()
        frame["trading_session"] = frame["trading_session"].astype(str)
        pnl = pd.to_numeric(frame["net_pnl"], errors="coerce")
        group_cols = [c for c in frame.columns if c not in {"trading_session", "net_pnl", "stress_pnl", "trades"}]
        variant_count = int(frame[group_cols].drop_duplicates().shape[0]) if group_cols else 1
        by_day = frame.assign(_pnl=pnl).groupby("trading_session").agg(rows=("_pnl", "size"), net_pnl_sum=("_pnl", "sum"), positive_rows=("_pnl", lambda s: int((s > 0).sum())), negative_rows=("_pnl", lambda s: int((s < 0).sum())), zero_rows=("_pnl", lambda s: int((s == 0).sum()))).reset_index()
        merged = sessions.merge(by_day, on="trading_session", how="left")
        coverage = split_coverage(merged)
        zero_day_count = int(by_day["net_pnl_sum"].eq(0).sum())
        if zero_day_count == 0:
            zero_meaning = "no zero-pnl days observed; missing dates are missing_source_day, not zero"
        elif "trades" in frame.columns:
            zero_meaning = "active_day_zero_result"
        else:
            zero_meaning = "ambiguous_or_variant_zero; missing dates are missing_source_day, not zero"
        suitable = name in {"playbook_scheduler_e_daily_pnl", "portfolio_audit_e_portfolio_daily_pnl"} and variant_count == 1
        if variant_count > 1:
            suitability_note = "multi-variant diagnostic source; suitable only after selecting one policy/variant, not as pooled ML target PnL"
        elif name.startswith("phase"):
            suitability_note = "module-level active rows; suitable for opportunity/activity diagnostics, not selected scheduler/playbook PnL target"
        else:
            suitability_note = "candidate selected daily PnL source if policy row matches Dataset B selected policy"
        rows.append({
            "pnl_source": name,
            "path": str(path),
            "present": True,
            "rows": int(len(frame)),
            "unique_trading_days": int(frame["trading_session"].nunique()),
            "date_start": str(frame["trading_session"].min()),
            "date_end": str(frame["trading_session"].max()),
            "active_days": int(by_day["net_pnl_sum"].notna().sum()),
            "zero_pnl_days": zero_day_count,
            "positive_days": int(by_day["net_pnl_sum"].gt(0).sum()),
            "negative_days": int(by_day["net_pnl_sum"].lt(0).sum()),
            "variant_count": variant_count,
            "discovery_covered_days": coverage["discovery"],
            "validation_covered_days": coverage["validation"],
            "holdout_covered_days": coverage["holdout"],
            "dataset_days_missing_from_source": int(merged["rows"].isna().sum()),
            "zero_meaning": zero_meaning,
            "missing_pnl_handling": "missing_source_day; not treated as zero",
            "suitable_for_ml_target_construction": bool(suitable),
            "suitability_note": suitability_note,
        })
    return pd.DataFrame(rows)


def missing_source_row(name: str, path: Path, sessions: pd.DataFrame, present: bool = False, note: str = "source file not present") -> dict[str, Any]:
    return {
        "pnl_source": name,
        "path": str(path),
        "present": present,
        "rows": 0,
        "unique_trading_days": 0,
        "date_start": "",
        "date_end": "",
        "active_days": 0,
        "zero_pnl_days": 0,
        "positive_days": 0,
        "negative_days": 0,
        "variant_count": 0,
        "discovery_covered_days": 0,
        "validation_covered_days": 0,
        "holdout_covered_days": 0,
        "dataset_days_missing_from_source": int(len(sessions)),
        "zero_meaning": "not applicable; source missing",
        "missing_pnl_handling": "missing_source_day; not treated as zero",
        "suitable_for_ml_target_construction": False,
        "suitability_note": note,
    }


def split_coverage(merged: pd.DataFrame) -> dict[str, int]:
    return {split: int(merged[merged["chronological_split"].astype(str).eq(split)]["rows"].notna().sum()) for split in ["discovery", "validation", "holdout"]}


def build_active_day_audit(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for split_name, mask in split_masks(dataset):
        seg = dataset.loc[mask]
        rows.append({
            "split": split_name,
            "rows": int(len(seg)),
            "playbook_active_days": int(seg["playbook_active_day_c"].sum()),
            "scheduler_active_days": int(seg["scheduler_active_day_c"].sum()),
            "any_module_active_days": int(seg["any_module_active_day_c"].sum()),
            "default_scheduler_module_active_days": int(seg["default_scheduler_module_active_day_c"].sum()),
            "rare_module_active_days": int(seg["rare_module_active_day_c"].sum()),
            "no_trade_days": int(seg["no_trade_day_c"].sum()),
            "missing_pnl_source_days": int(seg["missing_pnl_source_day_c"].sum()),
            "selected_active_zero_result_days": int(((seg["scheduler_active_day_c"] | seg["playbook_active_day_c"]) & pd.to_numeric(seg["selected_scheduler_or_playbook_pnl_c"], errors="coerce").eq(0)).sum()),
        })
    return pd.DataFrame(rows)


def split_masks(dataset: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    masks = [("full", pd.Series(True, index=dataset.index))]
    for split in ("discovery", "validation", "holdout"):
        masks.append((split, dataset["chronological_split"].astype(str).eq(split)))
    masks.append(("recent_oos_like", bool_series(dataset["recent_oos_like"], dataset.index)))
    return masks


def build_target_balance_by_split(dataset: pd.DataFrame, targets: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target in targets:
        if target not in dataset.columns:
            continue
        for split_name, mask in split_masks(dataset):
            seg = dataset.loc[mask, target]
            non_null = seg.dropna()
            counts = non_null.astype(str).value_counts().to_dict()
            true_count = int(counts.get("True", counts.get("1", 0)))
            false_count = int(counts.get("False", counts.get("0", 0)))
            rows.append({
                "target_name": target,
                "split": split_name,
                "rows": int(len(seg)),
                "non_null_rows": int(non_null.shape[0]),
                "null_rows": int(seg.isna().sum()),
                "true_count": true_count,
                "false_count": false_count,
                "positive_rate_non_null": round(true_count / int(non_null.shape[0]), 6) if int(non_null.shape[0]) else np.nan,
                "class_counts_json": json.dumps({str(k): int(v) for k, v in counts.items()}, sort_keys=True),
            })
    return pd.DataFrame(rows)


def row_for(frame: pd.DataFrame, target: str, split: str) -> dict[str, Any]:
    rows = frame[frame["target_name"].eq(target) & frame["split"].eq(split)]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def build_target_quality_summary(dataset: pd.DataFrame, balance: pd.DataFrame, threshold_info: dict[str, Any]) -> pd.DataFrame:
    rows = []
    leakage_free_targets = set(CANDIDATE_TARGETS_C)
    for target in CANDIDATE_TARGETS_C:
        if target not in dataset.columns:
            continue
        full = row_for(balance, target, "full")
        disc = row_for(balance, target, "discovery")
        val = row_for(balance, target, "validation")
        hold = row_for(balance, target, "holdout")
        recent = row_for(balance, target, "recent_oos_like")
        diagnostic_only = target in DIAGNOSTIC_TARGETS_C or target == "target_bad_regime_c"
        rows.append({
            "target_name": target,
            "target_type": target_type(target),
            "total_non_null_rows": int(full.get("non_null_rows", 0)),
            "true_count": int(full.get("true_count", 0)),
            "false_count": int(full.get("false_count", 0)),
            "discovery_true": int(disc.get("true_count", 0)),
            "discovery_false": int(disc.get("false_count", 0)),
            "validation_true": int(val.get("true_count", 0)),
            "validation_false": int(val.get("false_count", 0)),
            "holdout_true": int(hold.get("true_count", 0)),
            "holdout_false": int(hold.get("false_count", 0)),
            "recent_oos_like_true": int(recent.get("true_count", 0)),
            "recent_oos_like_false": int(recent.get("false_count", 0)),
            "discovery_positive_rate": disc.get("positive_rate_non_null", np.nan),
            "validation_positive_rate": val.get("positive_rate_non_null", np.nan),
            "holdout_positive_rate": hold.get("positive_rate_non_null", np.nan),
            "no_leakage_flags": target in leakage_free_targets,
            "uses_future_information_as_feature": False,
            "diagnostic_only": diagnostic_only,
            "large_loss_threshold_available": bool(threshold_info.get("large_loss_threshold_available")) if target == "target_active_day_large_loss_c" else "",
            "quality_notes": target_quality_note(target, threshold_info),
        })
    return pd.DataFrame(rows)


def target_type(target: str) -> str:
    if target == "target_any_module_active_day_c":
        return "opportunity_classification"
    if target == "target_no_trade_but_module_positive_c":
        return "missed_opportunity_diagnostic"
    if target in DIAGNOSTIC_TARGETS_C:
        return "stable_diagnostic_regime"
    if target == "target_bad_regime_c":
        return "diagnostic_regime_composite"
    return "active_day_pnl_quality"


def target_quality_note(target: str, threshold_info: dict[str, Any]) -> str:
    if target == "target_active_day_large_loss_c" and not threshold_info.get("large_loss_threshold_available"):
        return "Large-loss threshold not available because discovery active-day negative examples were below the minimum."
    if target in DIAGNOSTIC_TARGETS_C:
        return "Carried forward from Dataset B only as diagnostic unless readiness rules pass and Strategy Agent approves prediction use."
    if target == "target_bad_regime_c":
        return "Composite includes post-session weak/adverse diagnostics; diagnostic-only unless redefined with prediction-time features."
    return "Defined without imputing missing/no-trade PnL as active-day zero."


def build_target_readiness_summary(quality: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in quality.to_dict("records"):
        checks = {
            "total_non_null_rows>=300": int(row["total_non_null_rows"]) >= 300,
            "overall_true>=50": int(row["true_count"]) >= 50,
            "overall_false>=50": int(row["false_count"]) >= 50,
            "discovery_true>=30": int(row["discovery_true"]) >= 30,
            "discovery_false>=30": int(row["discovery_false"]) >= 30,
            "validation_true>=15": int(row["validation_true"]) >= 15,
            "validation_false>=15": int(row["validation_false"]) >= 15,
            "holdout_true>=15": int(row["holdout_true"]) >= 15,
            "holdout_false>=15": int(row["holdout_false"]) >= 15,
            "no_leakage_flags": bool(row["no_leakage_flags"]),
            "not_future_feature_target": not bool(row["uses_future_information_as_feature"]),
            "not_diagnostic_only": not bool(row["diagnostic_only"]),
        }
        trainable = all(checks.values())
        failed = [name for name, ok in checks.items() if not ok]
        out = {k: row[k] for k in ["target_name", "target_type", "total_non_null_rows", "true_count", "false_count", "discovery_true", "discovery_false", "validation_true", "validation_false", "holdout_true", "holdout_false", "recent_oos_like_true", "recent_oos_like_false"]}
        out.update({
            "trainable_for_baseline_b": trainable,
            "readiness_decision": "trainable_for_baseline_b" if trainable else "not_trainable",
            "failed_rules_json": json.dumps(failed, sort_keys=True),
            "diagnostic_only": bool(row["diagnostic_only"]),
            "no_leakage_flags": bool(row["no_leakage_flags"]),
        })
        rows.append(out)
    return pd.DataFrame(rows)


def build_label_dictionary_c(label_dict_b: dict[str, Any], dataset: pd.DataFrame, readiness: pd.DataFrame, threshold_info: dict[str, Any]) -> dict[str, Any]:
    out = dict(label_dict_b)
    readiness_map = readiness.set_index("target_name")["trainable_for_baseline_b"].to_dict() if not readiness.empty else {}
    for column in NEW_AUDIT_COLUMNS + [f"{p}_active_c" for p in PHASE_GROUPS] + ["selected_scheduler_or_playbook_pnl_c"]:
        if column in dataset.columns:
            out[column] = {
                "role": "audit_column",
                "is_target": False,
                "is_feature": False,
                "definition": audit_column_definition(column),
                "allowed_values": "boolean" if column != "selected_scheduler_or_playbook_pnl_c" else "numeric or blank",
                "null_meaning": "not applicable" if column != "selected_scheduler_or_playbook_pnl_c" else "selected scheduler/playbook PnL source missing",
                "prediction_use": "not a feature; audit/diagnostic only",
                "target_type": "active_day_audit",
                "trainable_for_baseline_b": False,
                "leakage_notes": "Outcome/audit metadata; keep out of feature dictionary.",
            }
    target_definitions = target_definitions_c(threshold_info)
    for target in CANDIDATE_TARGETS_C:
        if target in dataset.columns:
            out[target] = {
                "role": "target",
                "is_target": True,
                "is_feature": False,
                "definition": target_definitions[target],
                "allowed_values": "True, False, blank/null",
                "null_meaning": target_null_meaning(target),
                "prediction_use": prediction_use(target, bool(readiness_map.get(target, False))),
                "target_type": target_type(target),
                "trainable_for_baseline_b": bool(readiness_map.get(target, False)),
                "leakage_notes": leakage_notes(target),
            }
    return dict(sorted(out.items()))


def audit_column_definition(column: str) -> str:
    definitions = {
        "playbook_active_day_c": "Dataset C explicit playbook active-day audit flag from Dataset B playbook_active_day.",
        "scheduler_active_day_c": "Dataset C explicit scheduler active-day audit flag from Dataset B scheduler no-trade/positive/negative/PnL indicators.",
        "any_module_active_day_c": "True when any phase10b-phase17a module group is active on the session.",
        "default_scheduler_module_active_day_c": "True when any non-rare/default-scheduler-eligible phase group is active on the session.",
        "rare_module_active_day_c": "True when rare module groups phase16a or phase17a are active on the session.",
        "no_trade_day_c": "True when selected scheduler/playbook is inactive and selected PnL source is present.",
        "missing_pnl_source_day_c": "True when selected scheduler/playbook daily PnL source is missing; missing is never treated as zero.",
        "selected_scheduler_or_playbook_pnl_c": "Selected daily PnL used for Dataset C target construction.",
    }
    return definitions.get(column, f"Dataset C active audit flag for {column}.")


def target_definitions_c(threshold_info: dict[str, Any]) -> dict[str, str]:
    threshold = threshold_info.get("large_loss_threshold")
    return {
        "target_active_day_loss_c": "Among selected scheduler/playbook active days only, true when selected daily PnL < 0, false when selected daily PnL > 0, blank on no-trade or missing-source days.",
        "target_active_day_large_loss_c": f"Among selected scheduler/playbook active days only, true when selected daily PnL <= discovery active-day 25th percentile threshold ({threshold}); blank on no-trade/missing days or when discovery active negatives are insufficient.",
        "target_any_module_active_day_c": "Opportunity target: true when any non-rare/default-scheduler-eligible module group was active, false otherwise; not a PnL-quality label.",
        "target_no_trade_but_module_positive_c": "Missed-opportunity diagnostic: true when selected scheduler/playbook had no trade but at least one default-scheduler-eligible non-rare module group had positive daily PnL; blank when selected scheduler/playbook was active or source missing.",
        "target_bad_regime_c": "Composite bad-regime diagnostic: true for active-day loss, weak-fold day, or high-vol mixed adverse regime; false for active-day profitable days without weak/adverse flags; blank when information is insufficient.",
        "target_prior_level_interaction_day": "Dataset B diagnostic target carried forward only if split balance is adequate.",
        "target_power_hour_expansion_day": "Dataset B diagnostic target carried forward only if split balance is adequate.",
    }


def target_null_meaning(target: str) -> str:
    if target in {"target_active_day_loss_c", "target_active_day_large_loss_c"}:
        return "No selected scheduler/playbook active trade or selected PnL source missing."
    if target == "target_no_trade_but_module_positive_c":
        return "Selected scheduler/playbook was active or selected PnL source was missing."
    if target == "target_bad_regime_c":
        return "Insufficient information to classify without using no-trade zero as active-day evidence."
    return "Missing original diagnostic label."


def prediction_use(target: str, trainable: bool) -> str:
    if trainable:
        return "candidate for ML Baseline B training after Strategy Agent review"
    if target == "target_any_module_active_day_c":
        return "opportunity diagnostic; not trainable until readiness rules pass"
    return "diagnostic-only; not trainable for Baseline B under Dataset C readiness rules"


def leakage_notes(target: str) -> str:
    if target == "target_bad_regime_c":
        return "Uses post-session outcome/regime labels; not a feature and diagnostic-only unless reworked for prediction-time availability."
    return "Target/outcome label only; excluded from feature dictionary and not used as a feature."


def build_next_action_recommendation(dataset: pd.DataFrame, readiness: pd.DataFrame, coverage: pd.DataFrame, quality: pd.DataFrame, threshold_info: dict[str, Any]) -> dict[str, Any]:
    trainable = readiness[readiness["trainable_for_baseline_b"].eq(True)] if not readiness.empty else pd.DataFrame()
    ambiguous_zero_sources = coverage[coverage["present"].eq(True) & coverage["zero_meaning"].astype(str).str.contains("ambiguous", case=False, na=False)]
    missing_selected = int(dataset["missing_pnl_source_day_c"].sum()) if "missing_pnl_source_day_c" in dataset else 0
    if not trainable.empty:
        next_action = "ml_baseline_b_train_active_day_or_regime_classifier"
        rationale = "At least one Dataset C target passes all minimum row, class-balance, split, leakage, and diagnostic-use readiness rules."
    elif missing_selected > 0 or not ambiguous_zero_sources.empty:
        next_action = "manual_review_required_before_ml"
        rationale = "At least one PnL source still has ambiguous zero semantics or missing-source ambiguity; manual review is required before ML training."
    elif bool(quality["total_non_null_rows"].lt(300).any()) or bool((quality[["discovery_true", "discovery_false", "validation_true", "validation_false", "holdout_true", "holdout_false"]] < [30, 30, 15, 15, 15, 15]).any().any()):
        next_action = "insufficient_stable_targets_for_ml_training"
        rationale = "No Dataset C target passes trainability because target sparsity or split imbalance remains after excluding no-trade/missing PnL mass."
    else:
        next_action = "ml_dataset_d_expand_features_before_training"
        rationale = "Target counts are closer to usable but remaining failures are feature/diagnostic-definition related."
    return {
        "next_action": next_action,
        "rationale": rationale,
        "dataset_rows": int(len(dataset)),
        "date_range": {"start": str(dataset["trading_session"].min()), "end": str(dataset["trading_session"].max())},
        "trainable_targets_for_baseline_b": trainable["target_name"].astype(str).tolist() if not trainable.empty else [],
        "best_trainable_target": str(trainable.iloc[0]["target_name"]) if not trainable.empty else None,
        "threshold_info": threshold_info,
        "research_only": True,
        "model_trained": False,
        "generated_strategy_signals": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def write_outputs(config: MlTargetCConfig, dataset: pd.DataFrame, label_dictionary: dict[str, Any], target_balance: pd.DataFrame, target_quality: pd.DataFrame, pnl_source_coverage: pd.DataFrame, active_day_audit: pd.DataFrame, readiness: pd.DataFrame, recommendation: dict[str, Any], threshold_info: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "report": config.report_dir / "ml_target_c_manual_target_definition_report.md",
        "dataset": config.output_dir / "ml_target_c_day_regime.csv",
        "label_dictionary": config.output_dir / "ml_target_c_label_dictionary.json",
        "target_balance": config.output_dir / "ml_target_c_target_balance_by_split.csv",
        "target_quality": config.output_dir / "ml_target_c_target_quality_summary.csv",
        "pnl_source_coverage": config.output_dir / "ml_target_c_pnl_source_coverage.csv",
        "active_day_audit": config.output_dir / "ml_target_c_active_day_audit.csv",
        "target_readiness": config.output_dir / "ml_target_c_target_readiness_summary.csv",
        "recommendation": config.output_dir / "ml_target_c_next_action_recommendation.json",
    }
    write_csv_artifact(dataset, paths["dataset"])
    write_json_artifact(label_dictionary, paths["label_dictionary"])
    for key, frame in [("target_balance", target_balance), ("target_quality", target_quality), ("pnl_source_coverage", pnl_source_coverage), ("active_day_audit", active_day_audit), ("target_readiness", readiness)]:
        write_csv_artifact(frame, paths[key])
    write_json_artifact(recommendation, paths["recommendation"])
    report = render_report(dataset, target_balance, target_quality, pnl_source_coverage, active_day_audit, readiness, recommendation, threshold_info, paths)
    ensure_directory(paths["report"].parent)
    paths["report"].write_text(report, encoding="utf-8")
    for path in paths.values():
        dest = config.artifact_dir / path.name
        ensure_directory(dest.parent)
        dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    write_json_artifact({
        "run_id": config.run_id,
        "research_only": True,
        "model_trained": False,
        "generated_strategy_signals": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "paths": {k: str(v) for k, v in paths.items()},
    }, config.artifact_dir / "manifest.json")
    return paths


def render_report(dataset: pd.DataFrame, target_balance: pd.DataFrame, target_quality: pd.DataFrame, coverage: pd.DataFrame, active_audit: pd.DataFrame, readiness: pd.DataFrame, recommendation: dict[str, Any], threshold_info: dict[str, Any], paths: dict[str, Path]) -> str:
    lines = [
        "# ML Target C — Manual Target Definition Review",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "This is a research-only target-definition audit. No model training, strategy signals, live predictions, broker adapters, order routing, webhooks, credentials, automated execution, official gate changes, candidate promotion, paper-trading approval, or live-trading approval were produced.",
        "",
        f"Rows: {len(dataset)}",
        f"Date range: {dataset['trading_session'].min()} to {dataset['trading_session'].max()}",
        f"Large-loss threshold info: {json.dumps(threshold_info, sort_keys=True)}",
        "",
        "## PnL source coverage audit",
        markdown_table(coverage[["pnl_source", "present", "rows", "unique_trading_days", "date_start", "date_end", "active_days", "zero_pnl_days", "positive_days", "negative_days", "discovery_covered_days", "validation_covered_days", "holdout_covered_days", "dataset_days_missing_from_source", "zero_meaning", "suitable_for_ml_target_construction"]]),
        "",
        "## Active-day audit",
        markdown_table(active_audit),
        "",
        "## Revised targets created",
        markdown_table(target_quality[["target_name", "target_type", "total_non_null_rows", "true_count", "false_count", "discovery_true", "discovery_false", "validation_true", "validation_false", "holdout_true", "holdout_false", "diagnostic_only"]]),
        "",
        "## Target balance by split",
        markdown_table(target_balance[["target_name", "split", "non_null_rows", "null_rows", "true_count", "false_count", "positive_rate_non_null"]]),
        "",
        "## Target readiness",
        markdown_table(readiness[["target_name", "readiness_decision", "trainable_for_baseline_b", "failed_rules_json"]]),
        "",
        "## Recommendation",
        f"Next action: {recommendation['next_action']}",
        f"Rationale: {recommendation['rationale']}",
        f"Best trainable target: {recommendation.get('best_trainable_target')}",
        "",
        "## Output artifacts",
    ]
    lines.extend(f"- {name}: {path}" for name, path in paths.items())
    return "\n".join(lines) + "\n"
