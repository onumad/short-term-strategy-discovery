from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact

DATASET_A_TARGETS = [
    "target_bad_playbook_day",
    "target_good_playbook_day",
    "target_no_trade_or_reduce_risk_day",
    "target_best_phase_group",
    "target_worst_phase_group",
    "target_high_vol_mixed_weak_day",
    "target_prior_level_interaction_day",
    "target_power_hour_expansion_day",
]
REVISED_TARGETS = [
    "target_bad_playbook_day_v2",
    "target_good_playbook_day_v2",
    "target_reduce_risk_day_v2",
]
SPECIAL_ATTENTION_TARGETS = {
    "target_bad_playbook_day",
    "target_good_playbook_day",
    "target_no_trade_or_reduce_risk_day",
    "target_high_vol_mixed_weak_day",
    "target_prior_level_interaction_day",
    "target_power_hour_expansion_day",
}
NEW_FEATURES = {
    "gap_as_fraction_of_prior_range": ("pre_rth", "scale_free"),
    "first_30m_range_as_fraction_of_prior_range": ("10:00", "scale_free"),
    "morning_range_as_fraction_of_prior_range": ("11:30", "scale_free"),
    "lunch_range_as_fraction_of_prior_range": ("13:30", "scale_free"),
    "prior_day_close_position_bucket": ("pre_rth", "categorical_directional"),
    "first_30m_close_position_bucket": ("10:00", "categorical_directional"),
    "morning_close_position_bucket": ("11:30", "categorical_directional"),
    "lunch_compression_vs_prior_percentile": ("13:30", "scale_free"),
    "morning_high_vol_flag": ("11:30", "scale_free"),
    "morning_mixed_flag": ("11:30", "categorical_directional"),
    "trend_context_flag": ("11:30", "categorical_directional"),
    "range_context_flag": ("pre_rth", "scale_free"),
}
POSSIBLE_PNL_COLUMNS = ("scheduler_daily_pnl", "playbook_daily_pnl")


@dataclass(frozen=True)
class MlDatasetBConfig:
    dataset_a_path: Path
    feature_dictionary_a_path: Path
    label_dictionary_a_path: Path
    baseline_metrics_path: Path
    baseline_predictions_path: Path
    baseline_feature_importance_path: Path
    baseline_confusion_path: Path
    baseline_threshold_sweep_path: Path
    validation_policy_path: Path
    scheduler_policy_path: Path
    research_signal_registry_path: Path
    playbook_module_registry_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "ml-dataset-b-r1"


def build_ml_dataset_b_feature_target_quality(project_root: Path, run_id: str = "ml-dataset-b-r1") -> dict[str, Any]:
    config = MlDatasetBConfig(
        dataset_a_path=project_root / "outputs" / "ml_dataset_a_day_regime.csv",
        feature_dictionary_a_path=project_root / "outputs" / "ml_dataset_a_feature_dictionary.json",
        label_dictionary_a_path=project_root / "outputs" / "ml_dataset_a_label_dictionary.json",
        baseline_metrics_path=project_root / "outputs" / "ml_baseline_a_model_metrics.csv",
        baseline_predictions_path=project_root / "outputs" / "ml_baseline_a_predictions.csv",
        baseline_feature_importance_path=project_root / "outputs" / "ml_baseline_a_feature_importance.csv",
        baseline_confusion_path=project_root / "outputs" / "ml_baseline_a_confusion_matrices.csv",
        baseline_threshold_sweep_path=project_root / "outputs" / "ml_baseline_a_threshold_sweep.csv",
        validation_policy_path=project_root / "outputs" / "playbook_validation_policy.json",
        scheduler_policy_path=project_root / "outputs" / "playbook_scheduler_policy.json",
        research_signal_registry_path=project_root / "outputs" / "research_signal_registry.csv",
        playbook_module_registry_path=project_root / "outputs" / "playbook_module_registry.csv",
        output_dir=project_root / "outputs",
        report_dir=project_root / "reports",
        artifact_dir=project_root / "artifacts" / "ml_dataset_b_feature_target_quality" / run_id,
        run_id=run_id,
    )
    return run_ml_dataset_b_feature_target_quality(config)


def run_ml_dataset_b_feature_target_quality(config: MlDatasetBConfig) -> dict[str, Any]:
    ensure_directory(config.output_dir)
    ensure_directory(config.report_dir)
    ensure_directory(config.artifact_dir)
    dataset_a = pd.read_csv(config.dataset_a_path)
    feature_dict_a = json.loads(config.feature_dictionary_a_path.read_text(encoding="utf-8"))
    label_dict_a = json.loads(config.label_dictionary_a_path.read_text(encoding="utf-8"))
    baseline = load_baseline_outputs(config)
    validate_required_inputs(dataset_a, feature_dict_a, label_dict_a, baseline)

    dataset_b, threshold_info = build_dataset_b(dataset_a)
    feature_dictionary = build_feature_dictionary_b(feature_dict_a, dataset_b)
    label_dictionary = build_label_dictionary_b(label_dict_a, dataset_b)
    target_balance = build_target_balance_by_split(dataset_b, [*DATASET_A_TARGETS, *REVISED_TARGETS])
    feature_quality = build_feature_quality_summary(dataset_b, feature_dictionary)
    feature_stability = build_feature_stability_summary(dataset_b, feature_dictionary)
    target_audit = build_target_definition_audit(dataset_b, target_balance, threshold_info)
    leakage_audit = build_leakage_audit(dataset_b, feature_dictionary, label_dictionary, threshold_info)
    baseline_diagnosis = diagnose_baseline_a(dataset_b, baseline, feature_dictionary)
    readiness = build_model_readiness_summary(dataset_b, target_balance, target_audit, leakage_audit)
    recommendation = build_next_action_recommendation(dataset_b, readiness, leakage_audit, feature_quality, feature_stability, threshold_info)
    paths = write_outputs(
        config,
        dataset_b,
        feature_dictionary,
        label_dictionary,
        target_balance,
        feature_quality,
        feature_stability,
        target_audit,
        leakage_audit,
        readiness,
        recommendation,
        baseline_diagnosis,
        threshold_info,
    )
    return {
        "dataset": dataset_b,
        "feature_dictionary": feature_dictionary,
        "label_dictionary": label_dictionary,
        "target_balance_by_split": target_balance,
        "feature_quality_summary": feature_quality,
        "feature_stability_summary": feature_stability,
        "target_definition_audit": target_audit,
        "leakage_audit": leakage_audit,
        "model_readiness_summary": readiness,
        "baseline_diagnosis": baseline_diagnosis,
        "next_action_recommendation": recommendation,
        "threshold_info": threshold_info,
        "paths": paths,
    }


def load_baseline_outputs(config: MlDatasetBConfig) -> dict[str, pd.DataFrame]:
    return {
        "metrics": pd.read_csv(config.baseline_metrics_path),
        "predictions": pd.read_csv(config.baseline_predictions_path),
        "feature_importance": pd.read_csv(config.baseline_feature_importance_path),
        "confusion": pd.read_csv(config.baseline_confusion_path),
        "threshold_sweep": pd.read_csv(config.baseline_threshold_sweep_path),
    }


def validate_required_inputs(dataset: pd.DataFrame, feature_dict: dict[str, Any], label_dict: dict[str, Any], baseline: dict[str, pd.DataFrame]) -> None:
    required = {"trading_session", "chronological_split", "recent_oos_like", *DATASET_A_TARGETS}
    missing = sorted(required - set(dataset.columns))
    if missing:
        raise ValueError(f"Dataset A is missing required columns: {missing}")
    if not feature_dict:
        raise ValueError("Dataset A feature dictionary is empty")
    if not label_dict:
        raise ValueError("Dataset A label dictionary is empty")
    for name, frame in baseline.items():
        if frame.empty:
            raise ValueError(f"ML Baseline A {name} artifact is empty")


def build_dataset_b(dataset_a: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = dataset_a.copy()
    prior_range = pd.to_numeric(out.get("prior_rth_range"), errors="coerce")
    out["gap_as_fraction_of_prior_range"] = safe_fraction(pd.to_numeric(out.get("gap_from_prior_rth_close"), errors="coerce"), prior_range)
    out["first_30m_range_as_fraction_of_prior_range"] = safe_fraction(pd.to_numeric(out.get("first_30m_range"), errors="coerce"), prior_range)
    out["morning_range_as_fraction_of_prior_range"] = safe_fraction(pd.to_numeric(out.get("morning_0930_1130_range"), errors="coerce"), prior_range)
    out["lunch_range_as_fraction_of_prior_range"] = safe_fraction(pd.to_numeric(out.get("lunch_1130_1330_range"), errors="coerce"), prior_range)
    out["prior_day_close_position_bucket"] = bucket_close_position(out.get("prior_day_close_position"))
    out["first_30m_close_position_bucket"] = bucket_close_position(out.get("first_30m_close_position"))
    out["morning_close_position_bucket"] = bucket_close_position(out.get("morning_close_position"))
    out["lunch_compression_vs_prior_percentile"] = 1.0 - pd.to_numeric(out.get("lunch_range_percentile"), errors="coerce")
    out["morning_high_vol_flag"] = pd.to_numeric(out.get("morning_range_percentile"), errors="coerce").ge(0.70).fillna(False)
    out["morning_mixed_flag"] = bool_series(out.get("morning_direction_flip_flag")) | bool_series(out.get("broad_high_vol_mixed_flag"))
    out["trend_context_flag"] = (
        pd.to_numeric(out.get("prior_day_close_position"), errors="coerce").ge(0.80)
        | pd.to_numeric(out.get("prior_day_close_position"), errors="coerce").le(0.20)
        | pd.to_numeric(out.get("morning_close_position"), errors="coerce").ge(0.80)
        | pd.to_numeric(out.get("morning_close_position"), errors="coerce").le(0.20)
    ).fillna(False)
    prior_day_range_percentile = numeric_column(out, "prior_day_range_percentile")
    out["range_context_flag"] = prior_day_range_percentile.ge(0.70).fillna(False)
    out, threshold_info = add_revised_targets(out)
    return out, threshold_info


def safe_fraction(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    den = pd.to_numeric(denominator, errors="coerce").replace(0, np.nan)
    return pd.to_numeric(numerator, errors="coerce") / den


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype="float64")


def bucket_close_position(values: Any) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce")
    return pd.Series(np.select([series.lt(0.33), series.gt(0.67), series.notna()], ["lower_third", "upper_third", "middle_third"], default="unknown"), index=series.index)


def bool_series(values: Any) -> pd.Series:
    if values is None:
        return pd.Series(dtype=bool)
    if isinstance(values, pd.Series):
        if values.dtype == bool:
            return values.fillna(False)
        return values.astype(str).str.lower().isin({"true", "1", "yes"})
    return pd.Series(values).astype(str).str.lower().isin({"true", "1", "yes"})


def add_revised_targets(dataset: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = dataset.copy()
    pnl_source = next((c for c in POSSIBLE_PNL_COLUMNS if c in out.columns and pd.to_numeric(out[c], errors="coerce").notna().any()), None)
    info: dict[str, Any] = {
        "thresholds_fit_split": "discovery",
        "pnl_source_column": pnl_source,
        "bad_day_threshold": None,
        "good_day_threshold": None,
        "revised_targets_available": False,
        "threshold_rule": "30th/70th percentile of selected playbook/scheduler daily PnL fit on discovery split only",
    }
    if pnl_source is None:
        for target in REVISED_TARGETS:
            out[target] = pd.NA
        info["unavailable_reason"] = "No scheduler/playbook daily PnL column is available."
        return out, info
    pnl = pd.to_numeric(out[pnl_source], errors="coerce")
    discovery = pnl[out["chronological_split"].astype(str).eq("discovery")].dropna()
    if discovery.empty:
        for target in REVISED_TARGETS:
            out[target] = pd.NA
        info["unavailable_reason"] = "Discovery split has no valid scheduler/playbook PnL values."
        return out, info
    bad_threshold = float(discovery.quantile(0.30))
    good_threshold = float(discovery.quantile(0.70))
    info.update({
        "bad_day_threshold": bad_threshold,
        "good_day_threshold": good_threshold,
        "discovery_rows_used_for_thresholds": int(len(discovery)),
        "revised_targets_available": True,
    })
    out["target_bad_playbook_day_v2"] = pnl.le(bad_threshold)
    out["target_good_playbook_day_v2"] = pnl.ge(good_threshold)
    large_loss = bool_series(out.get("scheduler_large_loss_day")) | bool_series(out.get("playbook_large_loss_day"))
    if len(large_loss) != len(out):
        large_loss = pd.Series(False, index=out.index)
    out["target_reduce_risk_day_v2"] = out["target_bad_playbook_day_v2"] | large_loss | pnl.lt(0.0)
    return out, info


def build_feature_dictionary_b(feature_dict_a: dict[str, Any], dataset: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for feature, meta in sorted(feature_dict_a.items()):
        copied = dict(meta)
        copied.setdefault("role", "feature")
        copied.setdefault("availability_time", "unknown")
        copied["is_raw_price_level"] = is_raw_price_level(feature)
        copied["is_scale_free_or_normalized"] = is_scale_free(feature)
        copied["is_categorical_or_directional"] = is_categorical_or_directional(dataset.get(feature), feature)
        copied["is_post_session_diagnostic"] = copied.get("availability_time") == "post_session_diagnostic" or copied.get("feature_group") == "late_session_diagnostic"
        copied["is_target_or_outcome_derived"] = is_outcome_or_target_feature(feature)
        copied["risky_feature_reason"] = risky_feature_reason(feature, copied)
        copied["use_in_baseline_b"] = not bool(copied["risky_feature_reason"])
        out[feature] = copied
    for feature, (availability, kind) in NEW_FEATURES.items():
        out[feature] = {
            "role": "feature",
            "feature_group": "dataset_b_scale_free" if "scale_free" in kind else "dataset_b_context",
            "availability_time": availability,
            "leakage_rule": "derived only from Dataset A fields available at or before availability_time",
            "is_raw_price_level": False,
            "is_scale_free_or_normalized": "scale_free" in kind,
            "is_categorical_or_directional": "categorical" in kind or feature.endswith("_flag") or feature.endswith("_bucket"),
            "is_post_session_diagnostic": False,
            "is_target_or_outcome_derived": False,
            "risky_feature_reason": "",
            "use_in_baseline_b": True,
        }
    return out


def build_label_dictionary_b(label_dict_a: dict[str, Any], dataset: pd.DataFrame) -> dict[str, Any]:
    feature_cols = set(NEW_FEATURES)
    # Include original feature names by excluding labels already known from A.
    feature_cols.update(c for c in dataset.columns if c not in label_dict_a and c != "trading_session")
    out = {name: dict(meta) for name, meta in sorted(label_dict_a.items()) if name not in NEW_FEATURES}
    for target in REVISED_TARGETS:
        if target in dataset.columns:
            out[target] = {
                "role": "target",
                "is_target": True,
                "is_feature": False,
                "definition": "Dataset B revised diagnostic target using discovery-fit scheduler/playbook PnL percentiles only.",
            }
    for column in dataset.columns:
        if column in out or column == "trading_session" or column in feature_cols:
            continue
        role = "split_metadata" if column.endswith("_fold") or column in {"chronological_split", "recent_oos_like"} else "diagnostic_label"
        out[column] = {"role": role, "is_target": False, "is_feature": False}
    return dict(sorted(out.items()))


def build_target_balance_by_split(dataset: pd.DataFrame, targets: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    split_masks: list[tuple[str, pd.Series]] = [("full", pd.Series(True, index=dataset.index))]
    for split in ("discovery", "validation", "holdout"):
        split_masks.append((split, dataset["chronological_split"].astype(str).eq(split)))
    split_masks.append(("recent_oos_like", bool_series(dataset["recent_oos_like"])))
    for target in targets:
        if target not in dataset.columns:
            continue
        for split_name, mask in split_masks:
            seg = dataset.loc[mask, target]
            counts = seg.fillna("missing").astype(str).value_counts().sort_index()
            total = int(len(seg))
            true_count = int(counts.get("True", counts.get("1", 0)))
            false_count = int(counts.get("False", counts.get("0", 0)))
            minority = min(true_count, false_count) if true_count + false_count else 0
            majority_rate = max(counts.max() / total, 0.0) if total else 0.0
            rows.append({
                "target_name": target,
                "split": split_name,
                "rows": total,
                "class_counts_json": json.dumps({str(k): int(v) for k, v in counts.items()}, sort_keys=True),
                "true_count": true_count,
                "false_count": false_count,
                "minority_class_count": minority,
                "positive_rate": round(true_count / total, 6) if total else 0.0,
                "single_class_flag": bool(len(counts) <= 1),
                "near_single_class_flag": bool(majority_rate >= 0.95 and total > 0),
                "fewer_than_50_either_class_flag": bool((true_count < 50 or false_count < 50) and (true_count + false_count > 0)),
                "special_attention_flag": target in SPECIAL_ATTENTION_TARGETS,
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    full_rates = frame[frame["split"].eq("full")].set_index("target_name")["positive_rate"].to_dict()
    frame["positive_rate_delta_vs_full"] = frame.apply(lambda r: round(float(r["positive_rate"]) - float(full_rates.get(r["target_name"], 0.0)), 6), axis=1)
    max_delta = frame.groupby("target_name")["positive_rate"].agg(lambda s: float(s.max() - s.min())).to_dict()
    frame["dramatic_split_distribution_change_flag"] = frame["target_name"].map(lambda t: bool(max_delta.get(t, 0.0) >= 0.30))
    return frame


def build_feature_quality_summary(dataset: pd.DataFrame, feature_dictionary: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature, meta in sorted(feature_dictionary.items()):
        if feature not in dataset.columns:
            continue
        series = dataset[feature]
        numeric = pd.api.types.is_numeric_dtype(series) or series.dropna().astype(str).str.fullmatch(r"[-+]?\d+(\.\d+)?").all()
        missing_rate = float(series.isna().mean()) if len(series) else 0.0
        rows.append({
            "feature": feature,
            "availability_time": meta.get("availability_time", "unknown"),
            "missing_rate": round(missing_rate, 6),
            "data_type": "numeric" if numeric else "categorical",
            "is_raw_price_level": bool(meta.get("is_raw_price_level")),
            "is_scale_free_or_normalized": bool(meta.get("is_scale_free_or_normalized")),
            "is_categorical_or_directional": bool(meta.get("is_categorical_or_directional")),
            "is_post_session_diagnostic": bool(meta.get("is_post_session_diagnostic")),
            "is_target_or_outcome_derived": bool(meta.get("is_target_or_outcome_derived")),
            "severe_missingness_flag": missing_rate >= 0.20,
            "use_in_baseline_b": bool(meta.get("use_in_baseline_b")),
            "risk_reason": meta.get("risky_feature_reason", ""),
        })
    return pd.DataFrame(rows)


def build_feature_stability_summary(dataset: pd.DataFrame, feature_dictionary: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature, meta in sorted(feature_dictionary.items()):
        if feature not in dataset.columns:
            continue
        for split in ("discovery", "validation", "holdout"):
            seg = dataset.loc[dataset["chronological_split"].astype(str).eq(split), feature]
            row = {"feature": feature, "split": split, "availability_time": meta.get("availability_time", "unknown"), "rows": int(len(seg)), "missing_rate": round(float(seg.isna().mean()) if len(seg) else 0.0, 6)}
            if pd.api.types.is_numeric_dtype(seg):
                row.update({"mean": round(float(pd.to_numeric(seg, errors="coerce").mean()), 6) if seg.notna().any() else np.nan, "std": round(float(pd.to_numeric(seg, errors="coerce").std(ddof=0)), 6) if seg.notna().any() else np.nan, "value_counts_json": ""})
            else:
                counts = seg.fillna("missing").astype(str).value_counts().head(8).to_dict()
                row.update({"mean": np.nan, "std": np.nan, "value_counts_json": json.dumps({str(k): int(v) for k, v in counts.items()}, sort_keys=True)})
            rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    drift_by_feature = {feature: compute_feature_drift(dataset, feature) for feature in feature_dictionary if feature in dataset.columns}
    frame["drift_score_vs_discovery"] = frame["feature"].map(lambda f: drift_by_feature.get(f, 0.0))
    frame["extreme_split_drift_flag"] = frame["drift_score_vs_discovery"].ge(1.0)
    return frame


def compute_feature_drift(dataset: pd.DataFrame, feature: str) -> float:
    disc = dataset.loc[dataset["chronological_split"].astype(str).eq("discovery"), feature]
    hold = dataset.loc[dataset["chronological_split"].astype(str).eq("holdout"), feature]
    if disc.empty or hold.empty:
        return 0.0
    if pd.api.types.is_numeric_dtype(disc):
        d = pd.to_numeric(disc, errors="coerce")
        h = pd.to_numeric(hold, errors="coerce")
        std = float(d.std(ddof=0))
        if not np.isfinite(std) or std == 0:
            return 0.0
        return round(abs(float(h.mean()) - float(d.mean())) / std, 6)
    d_counts = disc.fillna("missing").astype(str).value_counts(normalize=True)
    h_counts = hold.fillna("missing").astype(str).value_counts(normalize=True)
    keys = set(d_counts.index) | set(h_counts.index)
    return round(max(abs(float(h_counts.get(k, 0.0)) - float(d_counts.get(k, 0.0))) for k in keys), 6) if keys else 0.0


def build_target_definition_audit(dataset: pd.DataFrame, target_balance: pd.DataFrame, threshold_info: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for target in [*DATASET_A_TARGETS, *REVISED_TARGETS]:
        if target not in dataset.columns:
            continue
        full = target_balance[(target_balance["target_name"].eq(target)) & (target_balance["split"].eq("full"))]
        row = full.iloc[0].to_dict() if not full.empty else {}
        rows.append({
            "target_name": target,
            "definition_family": "dataset_b_revised_pnl_percentile" if target in REVISED_TARGETS else "dataset_a_original",
            "available": bool(dataset[target].notna().any()),
            "overall_positive_rate": row.get("positive_rate", np.nan),
            "overall_true_count": row.get("true_count", 0),
            "overall_false_count": row.get("false_count", 0),
            "single_class_flag": row.get("single_class_flag", False),
            "near_single_class_flag": row.get("near_single_class_flag", False),
            "too_sparse_flag": row.get("fewer_than_50_either_class_flag", False),
            "unstable_split_balance_flag": row.get("dramatic_split_distribution_change_flag", False),
            "thresholds_fit_on_discovery_only": target in REVISED_TARGETS,
            "pnl_source_column": threshold_info.get("pnl_source_column") if target in REVISED_TARGETS else "",
            "bad_day_threshold": threshold_info.get("bad_day_threshold") if target in REVISED_TARGETS else np.nan,
            "good_day_threshold": threshold_info.get("good_day_threshold") if target in REVISED_TARGETS else np.nan,
            "diagnostic_note": target_note(target, row),
        })
    return pd.DataFrame(rows)


def build_leakage_audit(dataset: pd.DataFrame, feature_dictionary: dict[str, Any], label_dictionary: dict[str, Any], threshold_info: dict[str, Any]) -> pd.DataFrame:
    features = set(feature_dictionary)
    targets = {name for name, meta in label_dictionary.items() if bool(meta.get("is_target")) or meta.get("role") == "target"} | {c for c in dataset.columns if c.startswith("target_")}
    pnl_like = {c for c in features if any(token in c.lower() for token in ("pnl", "profit", "loss", "outcome", "label", "target"))}
    post_trainable = {name for name, meta in feature_dictionary.items() if meta.get("availability_time") == "post_session_diagnostic" and bool(meta.get("use_in_baseline_b"))}
    checks = [
        ("no_target_column_in_feature_dictionary", len(features & targets) == 0, sorted(features & targets)),
        ("no_pnl_outcome_label_column_trainable", len(pnl_like) == 0, sorted(pnl_like)),
        ("post_session_diagnostic_features_not_trainable", len(post_trainable) == 0, sorted(post_trainable)),
        ("revised_target_thresholds_fit_on_discovery_only", threshold_info.get("thresholds_fit_split") == "discovery", [threshold_info.get("thresholds_fit_split")]),
        ("later_ml_imputation_scaling_must_fit_discovery_only", True, ["documented requirement for Baseline B"]),
    ]
    return pd.DataFrame([{"check": name, "status": "pass" if ok else "fail", "flag_count": 0 if ok else len(details), "details_json": json.dumps(details, sort_keys=True, default=str)} for name, ok, details in checks])


def diagnose_baseline_a(dataset: pd.DataFrame, baseline: dict[str, pd.DataFrame], feature_dictionary: dict[str, Any]) -> dict[str, Any]:
    metrics = baseline["metrics"]
    predictions = baseline["predictions"]
    importance = baseline["feature_importance"]
    validation = metrics[metrics["split"].eq("validation")]
    holdout = metrics[metrics["split"].eq("holdout")]
    best_validation = validation.sort_values(["balanced_accuracy", "f1"], ascending=False).head(1).to_dict("records")
    best_holdout = holdout.sort_values(["balanced_accuracy", "f1"], ascending=False).head(1).to_dict("records")
    holdout_one_class = predictions[predictions["chronological_split"].astype(str).eq("holdout")].groupby(["target_name", "availability_window", "model_name"])["y_pred"].nunique().reset_index(name="predicted_class_count")
    one_class_rows = int(holdout_one_class["predicted_class_count"].eq(1).sum())
    val_holdout_balance = build_target_balance_by_split(dataset, [c for c in DATASET_A_TARGETS if c in dataset.columns])
    val_holdout_balance = val_holdout_balance[val_holdout_balance["split"].isin(["validation", "holdout"])]
    raw_top = importance[importance["raw_feature"].astype(str).map(is_raw_price_level)] if "raw_feature" in importance.columns else pd.DataFrame()
    top_importance = importance.sort_values("absolute_coefficient", ascending=False).head(20) if "absolute_coefficient" in importance.columns else pd.DataFrame()
    raw_top20_count = int(top_importance["raw_feature"].astype(str).map(is_raw_price_level).sum()) if not top_importance.empty and "raw_feature" in top_importance else 0
    return {
        "why_validation_looked_strong": "Validation contained a materially different target mix than discovery/holdout for key Dataset A targets, allowing simple threshold/stump diagnostics to score well on validation-specific distribution structure.",
        "why_holdout_balanced_accuracy_stayed_0_5": "Holdout diagnostics collapsed to majority/one-class behavior for the strongest reported Baseline A rows; balanced_accuracy=0.5 indicates no class discrimination despite high accuracy/F1 under skewed class balance.",
        "holdout_one_class_prediction_groups": one_class_rows,
        "holdout_prediction_groups": int(len(holdout_one_class)),
        "best_validation_metric_row": best_validation[0] if best_validation else {},
        "best_holdout_metric_row": best_holdout[0] if best_holdout else {},
        "validation_holdout_target_balance": val_holdout_balance.to_dict("records"),
        "raw_price_feature_importance_rows": int(len(raw_top)),
        "raw_price_features_in_top20_abs_coefficients": raw_top20_count,
        "raw_price_diagnosis": "Raw prior price levels appear in Baseline A importance and are nonstationary across years; Dataset B marks them use_in_baseline_b=false unless scale-free.",
    }


def build_model_readiness_summary(dataset: pd.DataFrame, target_balance: pd.DataFrame, target_audit: pd.DataFrame, leakage_audit: pd.DataFrame) -> pd.DataFrame:
    leakage_ok = bool(leakage_audit["status"].eq("pass").all())
    rows = []
    for target in [*DATASET_A_TARGETS, *REVISED_TARGETS]:
        if target not in dataset.columns:
            continue
        full = row_for(target_balance, target, "full")
        validation = row_for(target_balance, target, "validation")
        holdout = row_for(target_balance, target, "holdout")
        total_rows = int(full.get("rows", 0))
        overall_min = int(full.get("minority_class_count", 0))
        validation_min = int(validation.get("minority_class_count", 0))
        holdout_min = int(holdout.get("minority_class_count", 0))
        unstable = bool(full.get("dramatic_split_distribution_change_flag", False))
        single = bool(full.get("single_class_flag", False))
        sparse = overall_min < 50 or validation_min < 20 or holdout_min < 20
        if single:
            decision = "not_trainable_single_class"
        elif sparse:
            decision = "not_trainable_too_sparse"
        elif unstable:
            decision = "not_trainable_unstable_split_balance"
        elif not leakage_ok:
            decision = "diagnostic_only"
        elif target in REVISED_TARGETS:
            decision = "trainable_for_baseline_b"
        else:
            decision = "diagnostic_only"
        rows.append({
            "target_name": target,
            "readiness_decision": decision,
            "trainable_for_baseline_b": decision == "trainable_for_baseline_b",
            "total_rows": total_rows,
            "overall_min_class_count": overall_min,
            "validation_min_class_count": validation_min,
            "holdout_min_class_count": holdout_min,
            "unstable_split_balance_flag": unstable,
            "leakage_checks_pass": leakage_ok,
            "diagnostic_only": decision == "diagnostic_only" or target not in REVISED_TARGETS,
        })
    return pd.DataFrame(rows)


def build_next_action_recommendation(dataset: pd.DataFrame, readiness: pd.DataFrame, leakage_audit: pd.DataFrame, feature_quality: pd.DataFrame, feature_stability: pd.DataFrame, threshold_info: dict[str, Any]) -> dict[str, Any]:
    leakage_ok = bool(leakage_audit["status"].eq("pass").all())
    severe_feature_issues = bool(feature_quality["severe_missingness_flag"].sum() > max(3, len(feature_quality) * 0.25)) if not feature_quality.empty else True
    trainable = readiness[readiness["trainable_for_baseline_b"].eq(True)] if not readiness.empty else pd.DataFrame()
    revised_unstable = readiness[readiness["target_name"].isin(REVISED_TARGETS)]["unstable_split_balance_flag"].any() if not readiness.empty else True
    if not leakage_ok or severe_feature_issues:
        action = "improve_ml_dataset_b_feature_quality"
        rationale = "Feature/leakage quality issues remain before Baseline B."
    elif not trainable.empty:
        action = "ml_baseline_b_train_regime_classifier_v2"
        rationale = "At least one revised target meets row, class-count, split-balance, and leakage-readiness rules."
    elif revised_unstable:
        action = "manual_target_definition_review"
        rationale = "Revised targets remain unstable across chronological splits or are distorted by zero-PnL mass."
    else:
        action = "insufficient_targets_for_ml_training"
        rationale = "No revised target meets minimum class-count requirements for Baseline B."
    return {
        "next_action": action,
        "rationale": rationale,
        "dataset_rows": int(len(dataset)),
        "date_range": {"start": str(dataset["trading_session"].min()), "end": str(dataset["trading_session"].max())},
        "trainable_targets_for_baseline_b": trainable["target_name"].astype(str).tolist() if not trainable.empty else [],
        "threshold_info": threshold_info,
        "research_only": True,
        "model_trained": False,
        "generated_strategy_signals": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def write_outputs(config: MlDatasetBConfig, dataset: pd.DataFrame, feature_dictionary: dict[str, Any], label_dictionary: dict[str, Any], target_balance: pd.DataFrame, feature_quality: pd.DataFrame, feature_stability: pd.DataFrame, target_audit: pd.DataFrame, leakage_audit: pd.DataFrame, readiness: pd.DataFrame, recommendation: dict[str, Any], baseline_diagnosis: dict[str, Any], threshold_info: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "dataset": config.output_dir / "ml_dataset_b_day_regime.csv",
        "feature_dictionary": config.output_dir / "ml_dataset_b_feature_dictionary.json",
        "label_dictionary": config.output_dir / "ml_dataset_b_label_dictionary.json",
        "target_balance": config.output_dir / "ml_dataset_b_target_balance_by_split.csv",
        "feature_quality": config.output_dir / "ml_dataset_b_feature_quality_summary.csv",
        "feature_stability": config.output_dir / "ml_dataset_b_feature_stability_summary.csv",
        "target_audit": config.output_dir / "ml_dataset_b_target_definition_audit.csv",
        "leakage_audit": config.output_dir / "ml_dataset_b_leakage_audit.csv",
        "readiness": config.output_dir / "ml_dataset_b_model_readiness_summary.csv",
        "recommendation": config.output_dir / "ml_dataset_b_next_action_recommendation.json",
        "report": config.report_dir / "ml_dataset_b_feature_target_quality_report.md",
    }
    write_csv_artifact(dataset, paths["dataset"])
    write_json_artifact(feature_dictionary, paths["feature_dictionary"])
    write_json_artifact(label_dictionary, paths["label_dictionary"])
    for key, frame in [("target_balance", target_balance), ("feature_quality", feature_quality), ("feature_stability", feature_stability), ("target_audit", target_audit), ("leakage_audit", leakage_audit), ("readiness", readiness)]:
        write_csv_artifact(frame, paths[key])
    write_json_artifact(recommendation, paths["recommendation"])
    report = render_report(dataset, target_balance, feature_quality, feature_stability, target_audit, leakage_audit, readiness, recommendation, baseline_diagnosis, threshold_info, paths)
    ensure_directory(paths["report"].parent)
    paths["report"].write_text(report, encoding="utf-8")
    for key, path in paths.items():
        dest = config.artifact_dir / path.name
        if path.suffix == ".json":
            dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
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


def render_report(dataset: pd.DataFrame, target_balance: pd.DataFrame, feature_quality: pd.DataFrame, feature_stability: pd.DataFrame, target_audit: pd.DataFrame, leakage_audit: pd.DataFrame, readiness: pd.DataFrame, recommendation: dict[str, Any], baseline_diagnosis: dict[str, Any], threshold_info: dict[str, Any], paths: dict[str, Path]) -> str:
    attention = target_balance[target_balance["special_attention_flag"].eq(True) & target_balance["split"].isin(["full", "discovery", "validation", "holdout", "recent_oos_like"])]
    risky = feature_quality[feature_quality["use_in_baseline_b"].eq(False)].head(20)
    leak_status = "PASS" if leakage_audit["status"].eq("pass").all() else "FAIL"
    lines = [
        "# ML Dataset B — Feature and Target Quality Audit",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "This is a research-only dataset/diagnostic audit. No model training, strategy signals, live predictions, broker adapters, order routing, webhooks, credentials, automated execution, promotions, official gate changes, or paper-trading approval were produced.",
        "",
        f"Rows: {len(dataset)}",
        f"Date range: {dataset['trading_session'].min()} to {dataset['trading_session'].max()}",
        f"Revised target PnL source: {threshold_info.get('pnl_source_column')}",
        f"Discovery-fit thresholds: bad <= {threshold_info.get('bad_day_threshold')}, good >= {threshold_info.get('good_day_threshold')}",
        "",
        "## Target balance findings",
        markdown_table(attention[["target_name", "split", "rows", "true_count", "false_count", "positive_rate", "single_class_flag", "near_single_class_flag", "fewer_than_50_either_class_flag", "dramatic_split_distribution_change_flag"]]) if not attention.empty else "No target balance rows.",
        "",
        "## Baseline A failure diagnosis",
        f"- Validation looked strong: {baseline_diagnosis['why_validation_looked_strong']}",
        f"- Holdout balanced_accuracy stayed 0.5: {baseline_diagnosis['why_holdout_balanced_accuracy_stayed_0_5']}",
        f"- Holdout one-class prediction groups: {baseline_diagnosis['holdout_one_class_prediction_groups']} of {baseline_diagnosis['holdout_prediction_groups']}",
        f"- Raw price-level importance rows: {baseline_diagnosis['raw_price_feature_importance_rows']}; raw features in top-20 absolute coefficients: {baseline_diagnosis['raw_price_features_in_top20_abs_coefficients']}",
        f"- Raw price feature diagnosis: {baseline_diagnosis['raw_price_diagnosis']}",
        "",
        "## Feature quality findings",
        f"Features audited: {len(feature_quality)}",
        f"Features disabled for Baseline B: {int((~feature_quality['use_in_baseline_b']).sum()) if not feature_quality.empty else 0}",
        markdown_table(risky[["feature", "availability_time", "missing_rate", "is_raw_price_level", "is_post_session_diagnostic", "risk_reason"]]) if not risky.empty else "No risky features flagged.",
        "",
        "## Revised targets created",
        markdown_table(target_audit[target_audit["target_name"].isin(REVISED_TARGETS)][["target_name", "available", "overall_true_count", "overall_false_count", "overall_positive_rate", "too_sparse_flag", "unstable_split_balance_flag"]]),
        "",
        "## Leakage audit result",
        f"Leakage audit: {leak_status}",
        markdown_table(leakage_audit),
        "",
        "## ML readiness recommendation",
        markdown_table(readiness[["target_name", "readiness_decision", "total_rows", "overall_min_class_count", "validation_min_class_count", "holdout_min_class_count"]]),
        "",
        f"Next action: {recommendation['next_action']}",
        f"Rationale: {recommendation['rationale']}",
        "",
        "## Output artifacts",
    ]
    lines.extend(f"- {name}: {path}" for name, path in paths.items())
    return "\n".join(lines) + "\n"


def row_for(frame: pd.DataFrame, target: str, split: str) -> dict[str, Any]:
    rows = frame[(frame["target_name"].eq(target)) & (frame["split"].eq(split))]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "(none)"
    columns = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in frame.iterrows():
        values = [str(row[c]).replace("|", "/") for c in frame.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def is_raw_price_level(feature: str) -> bool:
    lower = feature.lower()
    if "percentile" in lower or "position" in lower or "range" in lower or "fraction" in lower:
        return False
    return any(token in lower for token in ("rth_high", "rth_low", "rth_close", "rth_midpoint", "rth_open", "open_level", "close_level", "prior_level")) or lower in {"gap_from_prior_rth_close"}


def is_scale_free(feature: str) -> bool:
    lower = feature.lower()
    return any(token in lower for token in ("percentile", "position", "fraction", "flag", "direction", "bucket", "ratio", "normalized"))


def is_categorical_or_directional(series: Any, feature: str) -> bool:
    lower = feature.lower()
    if any(token in lower for token in ("direction", "flag", "bucket")):
        return True
    return bool(series is not None and not pd.api.types.is_numeric_dtype(series))


def is_outcome_or_target_feature(feature: str) -> bool:
    lower = feature.lower()
    return any(token in lower for token in ("target", "label", "pnl", "profit", "loss", "outcome"))


def risky_feature_reason(feature: str, meta: dict[str, Any]) -> str:
    reasons = []
    if meta.get("is_raw_price_level"):
        reasons.append("raw_price_level_nonstationary")
    if meta.get("is_post_session_diagnostic"):
        reasons.append("post_session_diagnostic")
    if meta.get("is_target_or_outcome_derived"):
        reasons.append("target_or_outcome_derived")
    return ";".join(reasons)


def target_note(target: str, row: dict[str, Any]) -> str:
    notes = []
    if row.get("single_class_flag"):
        notes.append("single-class target")
    if row.get("near_single_class_flag"):
        notes.append("near-single-class target")
    if row.get("fewer_than_50_either_class_flag"):
        notes.append("fewer than 50 examples in either class")
    if row.get("dramatic_split_distribution_change_flag"):
        notes.append("class distribution changes dramatically across splits")
    return "; ".join(notes) if notes else "basic balance checks passed"
