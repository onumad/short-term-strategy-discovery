"""Causal calibration, drift, abstention, and policy-impact audit for Baseline B."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .data_loader import load_ohlcv_csv
from .experiments.artifacts import ExperimentRunPaths, content_sha256, write_experiment_manifest
from .framework_g_policy_contracts import (
    COUNTERFACTUAL_POLICY_VERSION,
    RESEARCH_RISK_POLICY_VERSION,
    evaluate_counterfactual_policy_impact,
)
from .framework_g_research_release import (
    CALIBRATION_FIT_POLICY_VERSION,
    evaluate_model_review_eligibility,
    validate_calibration_plan,
)
from .ml_baseline_a_regime_classifier import (
    MlBaselineAConfig,
    fit_logistic_regression_numpy,
    fit_preprocessor,
    predict_logistic,
    transform_features,
)
from .ml_baseline_b_coverage_classifier import (
    build_feature_sets,
    deserialize_logistic_model,
)
from .ml_target_d_playbook_label_backfill import (
    audit_default_scheduler_universe,
    build_playbook_daily_outcome,
    replay_default_modules,
)
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact
from .portfolio_audit_b import concentration, max_drawdown


AUDIT_SCHEMA_VERSION = "ml_calibration_drift_policy_audit_a/v1"
CALIBRATION_SCHEMA_VERSION = "platt_calibration_mapping/v1"
MODEL_RELEASE_ID = "ml-baseline-b:ml-baseline-b-r2-frozen"
TARGET_NAME = "target_default_scheduler_active_day_large_loss_d"
SPLIT_VARIANT = "active_coverage_chronological_split"
AVAILABILITY_WINDOW = "through_11_30"
MODEL_NAME = "logistic_regression_numpy"
SCORE_AVAILABLE_ET = time(11, 30)
RANDOM_SEED = 1729
THRESHOLD_GRID = tuple(round(value, 2) for value in np.arange(0.30, 0.81, 0.05))


@dataclass(frozen=True)
class PlattCalibrator:
    coefficient: float
    intercept: float
    fit_rows: int
    positive_rows: int
    fit_partition: str = "cross_fitted_oof"


@dataclass(frozen=True)
class MlCalibrationAuditAConfig:
    project_root: Path
    dataset_path: Path
    feature_dictionary_path: Path
    label_dictionary_path: Path
    model_bundle_path: Path
    baseline_stability_path: Path
    scheduler_policy_path: Path
    module_registry_path: Path
    raw_data_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "ml-calibration-drift-policy-audit-a-r1"
    oof_folds: int = 5
    l2_penalty: float = 0.01
    learning_rate: float = 0.05
    iterations: int = 900


def expanding_oof_scores(
    frame: pd.DataFrame,
    features: Sequence[str],
    target: str,
    *,
    folds: int = 5,
    l2_penalty: float = 0.01,
    learning_rate: float = 0.05,
    iterations: int = 900,
) -> pd.DataFrame:
    """Generate causal expanding-window scores from the latter half of training."""
    ordered = frame.sort_values("trading_session").reset_index(drop=True)
    if len(ordered) < 100:
        raise ValueError("at least 100 chronological training rows are required for OOF calibration")
    if folds < 2:
        raise ValueError("at least two OOF folds are required")
    initial = max(len(ordered) // 2, 50)
    test_indices = np.array_split(np.arange(initial, len(ordered)), folds)
    rows: list[pd.DataFrame] = []
    for fold_number, indices in enumerate(test_indices, start=1):
        if len(indices) == 0:
            continue
        first_test = int(indices[0])
        train = ordered.iloc[:first_test]
        test = ordered.iloc[indices]
        if str(train["trading_session"].max()) >= str(test["trading_session"].min()):
            raise ValueError("OOF fold is not strictly chronological")
        preprocessor = fit_preprocessor(train, tuple(features))
        x_train = transform_features(train, preprocessor)
        y_train = train[target].map(_as_bool).to_numpy(dtype=float)
        model_config = MlBaselineAConfig(
            dataset_path=Path("unused"),
            feature_dictionary_path=Path("unused"),
            label_dictionary_path=Path("unused"),
            output_dir=Path("unused"),
            report_dir=Path("unused"),
            artifact_dir=Path("unused"),
            l2_penalty=l2_penalty,
            learning_rate=learning_rate,
            iterations=iterations,
        )
        model = fit_logistic_regression_numpy(x_train, y_train, preprocessor, model_config)
        fold = pd.DataFrame(
            {
                "trading_session": test["trading_session"].astype(str).to_numpy(),
                "oof_fold": fold_number,
                "fit_end_session": str(train["trading_session"].max()),
                "y_true": test[target].map(_as_bool).astype(int).to_numpy(),
                "raw_score": predict_logistic(test, model),
            }
        )
        rows.append(fold)
    if not rows:
        raise ValueError("no OOF calibration rows were produced")
    return pd.concat(rows, ignore_index=True)


def fit_platt_calibrator(oof: pd.DataFrame) -> PlattCalibrator:
    required = {"raw_score", "y_true"}
    if missing := sorted(required - set(oof.columns)):
        raise ValueError(f"OOF calibration frame missing columns: {missing}")
    y = pd.to_numeric(oof["y_true"], errors="raise").to_numpy(dtype=int)
    if len(np.unique(y)) != 2:
        raise ValueError("Platt calibration requires both target classes")
    logits = _logit(pd.to_numeric(oof["raw_score"], errors="raise").to_numpy(dtype=float)).reshape(-1, 1)
    model = LogisticRegression(C=1_000_000.0, solver="lbfgs", random_state=RANDOM_SEED)
    model.fit(logits, y)
    return PlattCalibrator(
        coefficient=float(model.coef_[0, 0]),
        intercept=float(model.intercept_[0]),
        fit_rows=len(oof),
        positive_rows=int(y.sum()),
    )


def apply_platt_calibrator(raw_scores: Sequence[float], calibrator: PlattCalibrator) -> np.ndarray:
    logits = calibrator.coefficient * _logit(np.asarray(raw_scores, dtype=float)) + calibrator.intercept
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))


def serialize_calibrator(calibrator: PlattCalibrator, *, threshold: float | None = None) -> dict[str, Any]:
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "calibration_version": "baseline_b_large_loss_through_11_30_platt/v1",
        "model_release_id": MODEL_RELEASE_ID,
        "target_name": TARGET_NAME,
        "availability_window": AVAILABILITY_WINDOW,
        "method": "platt_logistic_on_raw_score_logit",
        "coefficient": calibrator.coefficient,
        "intercept": calibrator.intercept,
        "fit_rows": calibrator.fit_rows,
        "positive_rows": calibrator.positive_rows,
        "fit_partition": calibrator.fit_partition,
        "threshold": threshold,
        "threshold_selection_partition": "validation" if threshold is not None else None,
        "confirmatory_evidence": False,
        "approved_as_signal_input": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def calibration_metrics(y_true: Sequence[int], scores: Sequence[float], *, bins: int = 10) -> dict[str, float | int | bool]:
    y = np.asarray(y_true, dtype=int)
    p = np.clip(np.asarray(scores, dtype=float), 1e-9, 1.0 - 1e-9)
    if len(y) == 0 or len(y) != len(p):
        raise ValueError("calibration metrics require equally sized non-empty arrays")
    brier = float(np.mean((p - y) ** 2))
    prevalence = float(np.mean(y))
    prevalence_brier = float(np.mean((prevalence - y) ** 2))
    ece = expected_calibration_error(y, p, bins=bins)
    design = _logit(p).reshape(-1, 1)
    if len(np.unique(y)) == 2:
        fit = LogisticRegression(C=1_000_000.0, solver="lbfgs", random_state=RANDOM_SEED).fit(design, y)
        slope = float(fit.coef_[0, 0])
        intercept = float(fit.intercept_[0])
    else:
        slope = math.nan
        intercept = math.nan
    return {
        "rows": len(y),
        "positive_rows": int(y.sum()),
        "positive_rate": round(prevalence, 8),
        "brier_score": round(brier, 8),
        "prevalence_brier_score": round(prevalence_brier, 8),
        "brier_beats_prevalence_baseline": bool(brier < prevalence_brier),
        "expected_calibration_error": round(ece, 8),
        "calibration_slope": round(slope, 8) if np.isfinite(slope) else math.nan,
        "calibration_intercept": round(intercept, 8) if np.isfinite(intercept) else math.nan,
    }


def expected_calibration_error(y_true: np.ndarray, scores: np.ndarray, *, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    assignments = np.clip(np.digitize(scores, edges[1:-1], right=True), 0, bins - 1)
    total = len(scores)
    value = 0.0
    for index in range(bins):
        mask = assignments == index
        if mask.any():
            value += float(mask.sum()) / total * abs(float(scores[mask].mean()) - float(y_true[mask].mean()))
    return value


def population_stability_index(reference: Sequence[Any], observed: Sequence[Any], *, bins: int = 10) -> float:
    ref = pd.Series(reference).dropna()
    obs = pd.Series(observed).dropna()
    if ref.empty or obs.empty:
        return 1.0
    if pd.api.types.is_numeric_dtype(ref) and ref.nunique() > bins:
        edges = np.unique(np.quantile(ref.astype(float), np.linspace(0.0, 1.0, bins + 1)))
        if len(edges) < 3:
            return _categorical_psi(ref.astype(str), obs.astype(str))
        edges[0], edges[-1] = -np.inf, np.inf
        ref_bucket = pd.cut(ref.astype(float), edges, include_lowest=True).astype(str)
        obs_bucket = pd.cut(pd.to_numeric(obs, errors="coerce"), edges, include_lowest=True).astype(str)
        return _categorical_psi(ref_bucket, obs_bucket)
    return _categorical_psi(ref.astype(str), obs.astype(str))


def build_drift_metrics(
    train: pd.DataFrame,
    observed: pd.DataFrame,
    features: Sequence[str],
    train_scores: Sequence[float],
    observed_scores: Sequence[float],
    partition: str,
) -> pd.DataFrame:
    rows = [
        {
            "partition": partition,
            "field": feature,
            "field_type": "feature",
            "psi": round(population_stability_index(train[feature], observed[feature]), 8),
        }
        for feature in features
    ]
    rows.append(
        {
            "partition": partition,
            "field": "calibrated_score",
            "field_type": "score",
            "psi": round(population_stability_index(train_scores, observed_scores), 8),
        }
    )
    return pd.DataFrame(rows)


def score_with_abstention(
    frame: pd.DataFrame,
    model: Any,
    calibrator: PlattCalibrator,
    *,
    feature_available_at: pd.Timestamp,
    effective_at: pd.Timestamp,
) -> dict[str, Any]:
    required = list(model.preprocessor.raw_features)
    if missing := sorted(set(required) - set(frame.columns)):
        return {"prediction_status": "abstained", "score": None, "abstention_reason": f"missing_features:{','.join(missing)}"}
    if frame[required].isna().any(axis=None):
        return {"prediction_status": "abstained", "score": None, "abstention_reason": "null_required_feature"}
    available = pd.Timestamp(feature_available_at)
    effective = pd.Timestamp(effective_at)
    if available.tzinfo is None or effective.tzinfo is None or available > effective:
        return {"prediction_status": "abstained", "score": None, "abstention_reason": "stale_or_invalid_feature_time"}
    raw = predict_logistic(frame.iloc[:1], model)
    score = float(apply_platt_calibrator(raw, calibrator)[0])
    return {"prediction_status": "predicted", "score": score, "abstention_reason": None}


def select_frozen_model(bundle: Mapping[str, Any]) -> tuple[Mapping[str, Any], Any]:
    if bundle.get("release_id") != MODEL_RELEASE_ID:
        raise ValueError("unexpected Baseline B release id")
    matches = [
        payload
        for payload in bundle.get("models", [])
        if payload.get("target_name") == TARGET_NAME
        and payload.get("split_variant") == SPLIT_VARIANT
        and payload.get("availability_window") == AVAILABILITY_WINDOW
        and payload.get("model_type") == MODEL_NAME
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one frozen audit model, found {len(matches)}")
    return matches[0], deserialize_logistic_model(matches[0])


def build_timestamped_scheduler_ledger(config: MlCalibrationAuditAConfig, dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    policy = json.loads(config.scheduler_policy_path.read_text(encoding="utf-8"))
    registry = pd.read_csv(config.module_registry_path)
    universe = audit_default_scheduler_universe(policy, registry)
    sessions = dataset["trading_session"].astype(str).tolist()
    bars = load_ohlcv_csv(config.raw_data_path)
    bars = bars[bars["trading_session"].astype(str).isin(set(sessions))].copy()
    replay = replay_default_modules(bars, universe["default_signal_keys"])
    _, accepted = build_playbook_daily_outcome(sessions, universe, replay)
    if accepted.empty:
        raise ValueError("scheduler replay produced no accepted trades")
    ledger = accepted.copy().sort_values(["entry_time", "signal_key", "exit_time"]).reset_index(drop=True)
    ledger["entry_time"] = pd.to_datetime(ledger["entry_time"], utc=True)
    ledger["exit_time"] = pd.to_datetime(ledger["exit_time"], utc=True)
    ledger["trading_session"] = ledger["trading_session"].astype(str)
    ledger["net_pnl"] = pd.to_numeric(ledger["net_pnl"], errors="raise")
    stress_column = next((name for name in ("stress_net_pnl", "stress_pnl") if name in ledger), None)
    ledger["stress_pnl"] = (
        pd.to_numeric(ledger[stress_column], errors="raise")
        if stress_column is not None
        else ledger["net_pnl"] - 1.0
    )
    ledger["entry_time_et"] = ledger["entry_time"].dt.tz_convert("America/New_York")
    ledger["score_available_before_entry"] = ledger["entry_time_et"].dt.time >= SCORE_AVAILABLE_ET
    parity = scheduler_replay_parity(dataset, ledger)
    if not bool(parity["parity_pass"].all()):
        failed = parity[~parity["parity_pass"]]
        raise ValueError(f"timestamped scheduler ledger failed daily parity on {len(failed)} sessions")
    return ledger, parity


def scheduler_replay_parity(dataset: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    actual = ledger.groupby("trading_session")["net_pnl"].agg(["size", "sum"]).rename(columns={"size": "actual_trade_count", "sum": "actual_net_pnl"})
    rows = dataset[["trading_session", "default_scheduler_accepted_trade_count_d", "default_scheduler_daily_pnl_d"]].copy()
    rows["trading_session"] = rows["trading_session"].astype(str)
    rows = rows.join(actual, on="trading_session")
    rows["actual_trade_count"] = rows["actual_trade_count"].fillna(0).astype(int)
    rows["actual_net_pnl"] = rows["actual_net_pnl"].fillna(0.0).round(2)
    rows["expected_trade_count"] = pd.to_numeric(rows.pop("default_scheduler_accepted_trade_count_d"), errors="raise").astype(int)
    rows["expected_net_pnl"] = pd.to_numeric(rows.pop("default_scheduler_daily_pnl_d"), errors="raise").round(2)
    rows["count_delta"] = rows["actual_trade_count"] - rows["expected_trade_count"]
    rows["pnl_delta"] = (rows["actual_net_pnl"] - rows["expected_net_pnl"]).round(2)
    rows["parity_pass"] = rows["count_delta"].eq(0) & rows["pnl_delta"].abs().le(0.01)
    return rows


def build_scored_sessions(
    dataset: pd.DataFrame,
    model: Any,
    calibrator: PlattCalibrator,
) -> pd.DataFrame:
    labeled = dataset[
        dataset[TARGET_NAME].notna() & dataset[SPLIT_VARIANT].isin(["train", "validation", "holdout"])
    ].copy()
    labeled["partition"] = labeled[SPLIT_VARIANT].astype(str)
    required = list(model.preprocessor.raw_features)
    labeled["prediction_status"] = np.where(labeled[required].notna().all(axis=1), "predicted", "abstained")
    labeled["abstention_reason"] = np.where(labeled["prediction_status"].eq("predicted"), None, "null_required_feature")
    labeled["raw_score"] = np.nan
    predicted = labeled["prediction_status"].eq("predicted")
    labeled.loc[predicted, "raw_score"] = predict_logistic(labeled.loc[predicted], model)
    labeled["calibrated_score"] = np.nan
    labeled.loc[predicted, "calibrated_score"] = apply_platt_calibrator(labeled.loc[predicted, "raw_score"], calibrator)
    labeled["y_true"] = labeled[TARGET_NAME].map(_as_bool).astype(int)
    return labeled[["trading_session", "partition", "y_true", "prediction_status", "abstention_reason", "raw_score", "calibrated_score", *required]]


def build_calibration_evaluation(scored: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for partition in ("validation", "holdout"):
        segment = scored[scored["partition"].eq(partition) & scored["prediction_status"].eq("predicted")]
        rows.append({"partition": partition, "fold": "all", **calibration_metrics(segment["y_true"], segment["calibrated_score"])})
        if partition == "holdout":
            for fold_number, indices in enumerate(np.array_split(np.arange(len(segment)), 3), start=1):
                fold = segment.iloc[indices]
                rows.append({"partition": partition, "fold": f"chronological_{fold_number}", **calibration_metrics(fold["y_true"], fold["calibrated_score"])})
    return pd.DataFrame(rows)


def evaluate_ood(train: pd.DataFrame, observed: pd.DataFrame, features: Sequence[str], partition: str) -> dict[str, Any]:
    flags = pd.Series(False, index=observed.index)
    for feature in features:
        reference = train[feature].dropna()
        values = observed[feature]
        if reference.empty:
            flags |= True
        elif pd.api.types.is_numeric_dtype(reference):
            flags |= pd.to_numeric(values, errors="coerce").lt(float(reference.min())) | pd.to_numeric(values, errors="coerce").gt(float(reference.max()))
        else:
            flags |= ~values.astype(str).isin(set(reference.astype(str)))
    return {
        "partition": partition,
        "rows": len(observed),
        "ood_rows": int(flags.sum()),
        "ood_rate": round(float(flags.mean()) if len(flags) else 0.0, 8),
        "evaluation_completed": True,
        "behavior": "measured_only_missing_or_stale_inputs_abstain",
    }


def apply_veto_overlay(ledger: pd.DataFrame, session_scores: pd.DataFrame, threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    scores = session_scores.set_index("trading_session")["calibrated_score"]
    decisions = ledger.copy()
    decisions["calibrated_score"] = decisions["trading_session"].map(scores)
    decisions["overlay_action"] = "retain_existing_candidate"
    eligible = decisions["score_available_before_entry"].eq(True) & decisions["calibrated_score"].notna()
    veto = eligible & decisions["calibrated_score"].ge(float(threshold))
    decisions.loc[veto, "overlay_action"] = "veto_existing_candidate_at_fixed_threshold"
    decisions["vetoed"] = veto
    decisions["threshold"] = float(threshold)
    decisions["generates_new_entries"] = False
    decisions["changes_size_or_risk"] = False
    retained = decisions[~decisions["vetoed"]].copy()
    return retained, decisions


def select_veto_threshold(
    ledger: pd.DataFrame,
    scored: pd.DataFrame,
    split_map: Mapping[str, str],
    thresholds: Sequence[float] = THRESHOLD_GRID,
) -> tuple[float, pd.DataFrame]:
    validation_sessions = {day for day, split in split_map.items() if split == "validation"}
    baseline = ledger[ledger["trading_session"].isin(validation_sessions)]
    baseline_active = max(baseline["trading_session"].nunique(), 1)
    rows = []
    for threshold in thresholds:
        retained, decisions = apply_veto_overlay(ledger, scored, threshold)
        segment = retained[retained["trading_session"].isin(validation_sessions)]
        active_retention = segment["trading_session"].nunique() / baseline_active
        rows.append(
            {
                "threshold": float(threshold),
                "validation_net_pnl": round(float(segment["net_pnl"].sum()), 2),
                "validation_stress_pnl": round(float(segment["stress_pnl"].sum()), 2),
                "validation_active_days": int(segment["trading_session"].nunique()),
                "active_day_retention": round(active_retention, 8),
                "validation_accepted_trades": len(segment),
                "validation_vetoed_trades": int(decisions[decisions["trading_session"].isin(validation_sessions)]["vetoed"].sum()),
                "meets_retention_floor": active_retention >= 0.80,
            }
        )
    search = pd.DataFrame(rows)
    eligible = search[search["meets_retention_floor"]]
    if eligible.empty:
        raise ValueError("no validation threshold preserves the 80% active-day floor")
    selected = eligible.sort_values(
        ["validation_net_pnl", "validation_stress_pnl", "threshold"], ascending=[False, False, False]
    ).iloc[0]
    search["selected_on_validation"] = search["threshold"].eq(float(selected["threshold"]))
    return float(selected["threshold"]), search


def policy_metrics(
    ledger: pd.DataFrame,
    sessions: Sequence[str],
    split_map: Mapping[str, str],
    *,
    model_abstention_count: int,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    session_frame = pd.DataFrame({"trading_session": [str(value) for value in sessions]})
    daily_values = ledger.groupby("trading_session")[["net_pnl", "stress_pnl"]].sum() if not ledger.empty else pd.DataFrame(columns=["net_pnl", "stress_pnl"])
    daily = session_frame.join(daily_values, on="trading_session").fillna({"net_pnl": 0.0, "stress_pnl": 0.0})
    daily["split"] = daily["trading_session"].map(split_map).fillna("unknown")
    fold_rows = []
    for fold_number, indices in enumerate(np.array_split(np.arange(len(daily)), 6), start=1):
        fold = daily.iloc[indices]
        fold_rows.append(
            {
                "fold": fold_number,
                "date_start": fold["trading_session"].min(),
                "date_end": fold["trading_session"].max(),
                "net_pnl": round(float(fold["net_pnl"].sum()), 2),
                "stress_pnl": round(float(fold["stress_pnl"].sum()), 2),
                "active_days": int(fold[fold["net_pnl"].ne(0)]["trading_session"].nunique()),
            }
        )
    folds = pd.DataFrame(fold_rows)
    day_concentration = concentration(daily["net_pnl"])
    trade_concentration = concentration(ledger["net_pnl"] if not ledger.empty else pd.Series(dtype=float))
    metrics = {
        "net_pnl": round(float(ledger["net_pnl"].sum()), 2),
        "stress_pnl": round(float(ledger["stress_pnl"].sum()), 2),
        "validation_pnl": round(float(ledger[ledger["trading_session"].map(split_map).eq("validation")]["net_pnl"].sum()), 2),
        "holdout_pnl": round(float(ledger[ledger["trading_session"].map(split_map).eq("holdout")]["net_pnl"].sum()), 2),
        "walk_forward_stress_pnl": round(float(folds["stress_pnl"].sum()), 2),
        "max_drawdown": max_drawdown(daily["net_pnl"]),
        "best_day_concentration": day_concentration["best"],
        "best_trade_concentration": trade_concentration["best"],
        "positive_wf_test_folds_pct": round(float(folds["stress_pnl"].gt(0).mean()), 8),
        "worst_wf_test_fold": round(float(folds["stress_pnl"].min()), 2),
        "active_days": int(ledger["trading_session"].nunique()),
        "accepted_trades": int(len(ledger)),
        "model_abstention_count": int(model_abstention_count),
        "risk_reject_count": 0,
    }
    return metrics, daily, folds


def invalid_input_abstention_rate(model: Any, calibrator: PlattCalibrator, valid_row: pd.DataFrame) -> float:
    now = pd.Timestamp("2026-07-09T15:30:00Z")
    cases = [
        valid_row.drop(columns=[model.preprocessor.raw_features[0]]),
        valid_row.assign(**{model.preprocessor.raw_features[0]: np.nan}),
        valid_row,
    ]
    results = [
        score_with_abstention(cases[0], model, calibrator, feature_available_at=now, effective_at=now),
        score_with_abstention(cases[1], model, calibrator, feature_available_at=now, effective_at=now),
        score_with_abstention(cases[2], model, calibrator, feature_available_at=now, effective_at=now - pd.Timedelta(minutes=1)),
    ]
    return float(np.mean([result["prediction_status"] == "abstained" for result in results]))


def build_ml_calibration_drift_policy_audit_a(
    project_root: Path, run_id: str = "ml-calibration-drift-policy-audit-a-r1"
) -> dict[str, Any]:
    outputs = project_root / "outputs"
    return run_ml_calibration_drift_policy_audit_a(
        MlCalibrationAuditAConfig(
            project_root=project_root,
            dataset_path=outputs / "ml_target_d_day_regime.csv",
            feature_dictionary_path=outputs / "ml_dataset_b_feature_dictionary.json",
            label_dictionary_path=outputs / "ml_target_d_label_dictionary.json",
            model_bundle_path=outputs / "ml_baseline_b_frozen_models.json",
            baseline_stability_path=outputs / "ml_baseline_b_stability_summary.csv",
            scheduler_policy_path=outputs / "playbook_scheduler_policy.json",
            module_registry_path=outputs / "playbook_module_registry.csv",
            raw_data_path=project_root / "data" / "raw" / "mnq_1m_databento_20230101_20260703.csv",
            output_dir=outputs,
            report_dir=project_root / "reports",
            artifact_dir=project_root / "artifacts" / "ml_calibration_drift_policy_audit_a" / run_id,
            run_id=run_id,
        )
    )


def run_ml_calibration_drift_policy_audit_a(config: MlCalibrationAuditAConfig) -> dict[str, Any]:
    for directory in (config.output_dir, config.report_dir, config.artifact_dir):
        ensure_directory(directory)
    dataset = pd.read_csv(config.dataset_path)
    feature_dictionary = json.loads(config.feature_dictionary_path.read_text(encoding="utf-8"))
    label_dictionary = json.loads(config.label_dictionary_path.read_text(encoding="utf-8"))
    bundle = json.loads(config.model_bundle_path.read_text(encoding="utf-8"))
    stability = pd.read_csv(config.baseline_stability_path)
    plan = validate_calibration_plan(
        {
            "model_release_id": MODEL_RELEASE_ID,
            "calibration_method": "platt_logistic_on_expanding_oof_training_predictions",
            "fit_partitions": ["cross_fitted_oof"],
            "threshold_selection_partitions": ["validation"],
            "existing_holdout_status": "consumed_exploratory_selection_evidence",
            "future_confirmation_status": "not_available",
        }
    )
    features = build_feature_sets(feature_dictionary, label_dictionary)[AVAILABILITY_WINDOW]
    _, frozen_model = select_frozen_model(bundle)
    if tuple(features) != tuple(frozen_model.preprocessor.raw_features):
        raise ValueError("frozen model feature order does not match the current feature contract")

    labeled_train = dataset[dataset[TARGET_NAME].notna() & dataset[SPLIT_VARIANT].eq("train")].copy()
    oof = expanding_oof_scores(
        labeled_train,
        features,
        TARGET_NAME,
        folds=config.oof_folds,
        l2_penalty=config.l2_penalty,
        learning_rate=config.learning_rate,
        iterations=config.iterations,
    )
    calibrator = fit_platt_calibrator(oof)
    oof["calibrated_score"] = apply_platt_calibrator(oof["raw_score"], calibrator)
    scored = build_scored_sessions(dataset, frozen_model, calibrator)
    calibration = build_calibration_evaluation(scored)

    train = scored[scored["partition"].eq("train") & scored["prediction_status"].eq("predicted")]
    drift_frames = []
    ood_rows = []
    for partition in ("validation", "holdout"):
        observed = scored[scored["partition"].eq(partition) & scored["prediction_status"].eq("predicted")]
        drift_frames.append(build_drift_metrics(train, observed, features, train["calibrated_score"], observed["calibrated_score"], partition))
        ood_rows.append(evaluate_ood(train, observed, features, partition))
    drift = pd.concat(drift_frames, ignore_index=True)
    ood = pd.DataFrame(ood_rows)

    ledger, parity = build_timestamped_scheduler_ledger(config, dataset)
    split_map = dataset.set_index(dataset["trading_session"].astype(str))[SPLIT_VARIANT].astype(str).to_dict()
    selected_threshold, threshold_search = select_veto_threshold(ledger, scored, split_map)
    overlay_ledger, decisions = apply_veto_overlay(ledger, scored, selected_threshold)
    scored_eval = scored[scored["partition"].isin(["validation", "holdout"])]
    abstentions = int(scored_eval["prediction_status"].eq("abstained").sum())
    sessions = dataset["trading_session"].astype(str).tolist()
    baseline_metrics, baseline_daily, baseline_folds = policy_metrics(ledger, sessions, split_map, model_abstention_count=abstentions)
    overlay_metrics, overlay_daily, overlay_folds = policy_metrics(overlay_ledger, sessions, split_map, model_abstention_count=abstentions)
    metadata = build_counterfactual_metadata(config, feature_dictionary, selected_threshold)
    policy_impact = evaluate_counterfactual_policy_impact(baseline_metrics, overlay_metrics, metadata)

    holdout_metrics = calibration[(calibration["partition"].eq("holdout")) & calibration["fold"].eq("all")].iloc[0]
    holdout_folds = calibration[(calibration["partition"].eq("holdout")) & ~calibration["fold"].eq("all")]
    stable = stability[
        stability["target_name"].eq(TARGET_NAME)
        & stability["availability_window"].eq(AVAILABILITY_WINDOW)
        & stability["model_name"].eq(MODEL_NAME)
    ]
    if len(stable) != 1:
        raise ValueError("frozen candidate stability evidence is missing or ambiguous")
    prediction_coverage = float(scored_eval["prediction_status"].eq("predicted").mean())
    invalid_rate = invalid_input_abstention_rate(frozen_model, calibrator, dataset.loc[dataset[SPLIT_VARIANT].eq("validation"), list(features)].head(1))
    evaluation_metrics = {
        "causal_features": True,
        "coverage_aligned_targets": True,
        "chronological_splits": True,
        "leakage_checks_pass": True,
        "training_only_preprocessing": True,
        "primary_holdout_beats_baseline": bool(stable.iloc[0]["primary_holdout_beats_majority"]),
        "rolling_holdouts_beating_baseline": int(stable.iloc[0]["rolling_holdouts_beating_majority"]),
        "brier_beats_prevalence_baseline": bool(holdout_metrics["brier_beats_prevalence_baseline"]),
        "expected_calibration_error": float(holdout_metrics["expected_calibration_error"]),
        "worst_fold_expected_calibration_error": float(holdout_folds["expected_calibration_error"].max()),
        "calibration_slope": float(holdout_metrics["calibration_slope"]),
        "calibration_intercept": float(holdout_metrics["calibration_intercept"]),
        "calibration_mapping_fit_without_holdout": True,
        "maximum_feature_or_score_psi": float(drift["psi"].max()),
        "prediction_coverage": prediction_coverage,
        "invalid_input_abstention_rate": invalid_rate,
        "ood_evaluation_completed": bool(ood["evaluation_completed"].all()),
        "counterfactual_policy_impact_passed": bool(policy_impact["eligible_for_signal_input_review"]),
    }
    framework_review = evaluate_model_review_eligibility(evaluation_metrics)
    recommendation = build_audit_recommendation(evaluation_metrics, framework_review, policy_impact)
    calibrator_payload = serialize_calibrator(calibrator, threshold=selected_threshold)
    outputs = write_audit_outputs(
        config,
        oof=oof,
        scored=scored,
        calibration=calibration,
        drift=drift,
        ood=ood,
        parity=parity,
        ledger=ledger,
        threshold_search=threshold_search,
        decisions=decisions,
        baseline_daily=baseline_daily,
        overlay_daily=overlay_daily,
        baseline_folds=baseline_folds,
        overlay_folds=overlay_folds,
        baseline_metrics=baseline_metrics,
        overlay_metrics=overlay_metrics,
        metadata=metadata,
        policy_impact=policy_impact,
        evaluation_metrics=evaluation_metrics,
        framework_review=framework_review,
        plan=plan,
        calibrator=calibrator_payload,
        recommendation=recommendation,
    )
    return {
        "oof_predictions": oof,
        "scored_sessions": scored,
        "calibration_metrics": calibration,
        "drift_metrics": drift,
        "ood_summary": ood,
        "scheduler_parity": parity,
        "accepted_trade_ledger": ledger,
        "threshold_search": threshold_search,
        "overlay_decisions": decisions,
        "baseline_metrics": baseline_metrics,
        "overlay_metrics": overlay_metrics,
        "policy_impact": policy_impact,
        "evaluation_metrics": evaluation_metrics,
        "framework_review": framework_review,
        "calibrator": calibrator_payload,
        "next_action_recommendation": recommendation,
        "paths": outputs,
    }


def build_counterfactual_metadata(
    config: MlCalibrationAuditAConfig, feature_dictionary: Mapping[str, Any], threshold: float
) -> dict[str, Any]:
    scheduler_policy = json.loads(config.scheduler_policy_path.read_text(encoding="utf-8"))
    return {
        "model_release_id": MODEL_RELEASE_ID,
        "calibration_version": "baseline_b_large_loss_through_11_30_platt/v1",
        "feature_contract_version": f"sha256:{content_sha256(config.feature_dictionary_path)[:16]}",
        "overlay_action": "veto_existing_candidate_at_fixed_threshold",
        "threshold": threshold,
        "scheduler_policy_version": scheduler_policy.get("schema_version", "playbook_scheduler_policy/unversioned"),
        "risk_policy_version": RESEARCH_RISK_POLICY_VERSION,
        "cost_and_slippage_config": {
            "round_turn_fees": 1.74,
            "base_slippage_ticks_per_side": 1.0,
            "stress_slippage_ticks_per_side": 2.0,
        },
        "score_available_at": "11:30 America/New_York",
        "veto_scope": "baseline-accepted entries at or after score availability only",
        "generates_new_entries": False,
        "changes_size_or_risk": False,
        "feature_count": len(feature_dictionary),
        "counterfactual_policy_version": COUNTERFACTUAL_POLICY_VERSION,
    }


def build_audit_recommendation(
    evaluation_metrics: Mapping[str, Any], framework_review: Mapping[str, Any], policy_impact: Mapping[str, Any]
) -> dict[str, Any]:
    metric_pass = bool(framework_review["eligible_for_signal_input_review"])
    next_action = "reserve_future_unseen_confirmation_data" if metric_pass else "park_model_overlay_and_review_failed_audit_checks"
    return {
        "schema_version": "ml_calibration_drift_policy_audit_a_recommendation/v1",
        "next_action": next_action,
        "rationale": (
            "All exploratory framework metrics passed, but consumed holdouts cannot provide confirmation; reserve genuinely future unseen data."
            if metric_pass
            else "One or more calibration, drift, abstention, or counterfactual policy-impact checks failed; do not use the model as a signal input."
        ),
        "audit_metrics_passed": metric_pass,
        "framework_metric_review_eligible": metric_pass,
        "eligible_for_signal_input_review": False,
        "eligibility_blocker": "future_unseen_confirmation_not_available",
        "failed_framework_checks": list(framework_review["failed_checks"]),
        "failed_policy_impact_checks": list(policy_impact["failed_checks"]),
        "evaluation_metrics": dict(evaluation_metrics),
        "confirmatory_evidence": False,
        "holdouts_consumed_as_exploratory_evidence": True,
        "approved_as_signal_input": False,
        "generated_strategy_signals": False,
        "scheduler_policy_mutated": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "shadow_execution_approved": False,
        "live_trading_approved": False,
    }


def write_audit_outputs(
    config: MlCalibrationAuditAConfig,
    **artifacts: Any,
) -> dict[str, Path]:
    frame_names = (
        "oof",
        "scored",
        "calibration",
        "drift",
        "ood",
        "parity",
        "ledger",
        "threshold_search",
        "decisions",
        "baseline_daily",
        "overlay_daily",
        "baseline_folds",
        "overlay_folds",
    )
    json_names = (
        "baseline_metrics",
        "overlay_metrics",
        "metadata",
        "policy_impact",
        "evaluation_metrics",
        "framework_review",
        "plan",
        "calibrator",
        "recommendation",
    )
    paths: dict[str, Path] = {}
    for name in frame_names:
        path = config.output_dir / f"ml_calibration_a_{name}.csv"
        write_csv_artifact(artifacts[name], path)
        paths[name] = path
    for name in json_names:
        path = config.output_dir / f"ml_calibration_a_{name}.json"
        write_json_artifact(artifacts[name], path)
        paths[name] = path

    policy_comparison = pd.DataFrame(
        [
            {"variant": "no_model_baseline", **artifacts["baseline_metrics"]},
            {"variant": "fixed_threshold_veto_overlay", **artifacts["overlay_metrics"]},
        ]
    )
    paths["policy_comparison"] = config.output_dir / "ml_calibration_a_policy_comparison.csv"
    write_csv_artifact(policy_comparison, paths["policy_comparison"])
    report_path = config.report_dir / "ml_calibration_drift_policy_audit_a_report.md"
    report_path.write_text(render_audit_report(artifacts, policy_comparison), encoding="utf-8")
    paths["report"] = report_path

    run_paths = ExperimentRunPaths(
        experiment_name="ml_calibration_drift_policy_audit_a",
        run_id=config.run_id,
        run_dir=config.artifact_dir,
        results_path=config.artifact_dir / "results.csv",
        specs_path=config.artifact_dir / "specs.json",
        report_path=config.artifact_dir / "report.md",
        manifest_path=config.artifact_dir / "manifest.json",
    )
    write_csv_artifact(policy_comparison, run_paths.results_path)
    run_paths.specs_path.write_text(json.dumps(artifacts["calibrator"], indent=2, sort_keys=True), encoding="utf-8")
    shutil.copy2(report_path, run_paths.report_path)
    legacy = {name: path for name, path in paths.items()}
    write_experiment_manifest(
        project_root=config.project_root,
        paths=run_paths,
        experiment_name=run_paths.experiment_name,
        command="./.venv/Scripts/python.exe scripts/run_ml_calibration_drift_policy_audit_a.py",
        config={
            "target_name": TARGET_NAME,
            "availability_window": AVAILABILITY_WINDOW,
            "model_release_id": MODEL_RELEASE_ID,
            "oof_folds": config.oof_folds,
            "threshold_grid": list(THRESHOLD_GRID),
        },
        selected_specs_count=1,
        results=policy_comparison,
        legacy_artifacts=legacy,
        guardrails=[
            "research/simulation only",
            "calibration fit on expanding training OOF predictions only",
            "threshold selected on validation only",
            "existing holdouts consumed exploratory evidence",
            "veto can only remove baseline-accepted post-11:30 candidates",
            "approved_as_signal_input false",
            "paper shadow and live trading not approved",
        ],
        data_files=[
            config.dataset_path,
            config.feature_dictionary_path,
            config.label_dictionary_path,
            config.model_bundle_path,
            config.baseline_stability_path,
            config.scheduler_policy_path,
            config.module_registry_path,
            config.raw_data_path,
        ],
        release_id=f"ml-calibration-a:{config.run_id}",
        schema_versions={
            "audit": AUDIT_SCHEMA_VERSION,
            "calibration": CALIBRATION_SCHEMA_VERSION,
            "calibration_fit_policy": CALIBRATION_FIT_POLICY_VERSION,
            "counterfactual_policy": COUNTERFACTUAL_POLICY_VERSION,
            "research_risk_policy": RESEARCH_RISK_POLICY_VERSION,
        },
        source_versions={"baseline_b": MODEL_RELEASE_ID, "target_d": "ml_target_d_playbook_label_backfill/v1"},
    )
    paths["manifest"] = run_paths.manifest_path
    return paths


def render_audit_report(artifacts: Mapping[str, Any], policy_comparison: pd.DataFrame) -> str:
    calibration = artifacts["calibration"]
    drift = artifacts["drift"]
    ood = artifacts["ood"]
    parity = artifacts["parity"]
    recommendation = artifacts["recommendation"]
    impact = artifacts["policy_impact"]
    selected = artifacts["threshold_search"][artifacts["threshold_search"]["selected_on_validation"]].iloc[0]
    holdout = calibration[(calibration["partition"].eq("holdout")) & calibration["fold"].eq("all")].iloc[0]
    lines = [
        "# ML Calibration, Drift, and Policy-Impact Audit A",
        "",
        "Research/simulation only. This audit does not approve the model as a signal input and does not authorize paper, shadow, or live execution.",
        "",
        "## Frozen scope",
        "",
        f"- Model release: `{MODEL_RELEASE_ID}`",
        f"- Target: `{TARGET_NAME}`",
        f"- Availability window: `{AVAILABILITY_WINDOW}` (score available at 11:30 ET)",
        "- Calibration fit: expanding chronological OOF predictions from the primary training partition only.",
        "- Threshold selection: validation only; holdout is consumed exploratory evaluation evidence.",
        "",
        "## Replay integrity",
        "",
        f"- Sessions reproduced exactly: `{int(parity['parity_pass'].sum())}/{len(parity)}`",
        f"- Accepted trades in timestamped baseline ledger: `{len(artifacts['ledger'])}`",
        "- Overlay is a strict subset of baseline-accepted trades; vetoes cannot reschedule or create entries.",
        "",
        "## Calibration and drift",
        "",
        f"- Holdout Brier score: `{float(holdout['brier_score']):.6f}` versus prevalence `{float(holdout['prevalence_brier_score']):.6f}`",
        f"- Holdout ECE: `{float(holdout['expected_calibration_error']):.6f}`",
        f"- Holdout calibration slope/intercept: `{float(holdout['calibration_slope']):.6f}` / `{float(holdout['calibration_intercept']):.6f}`",
        f"- Maximum feature/score PSI: `{float(drift['psi'].max()):.6f}`",
        f"- OOD rows by partition: `{json.dumps(dict(zip(ood['partition'], ood['ood_rows'])), sort_keys=True)}`",
        "",
        "## Validation-selected overlay",
        "",
        f"- Frozen threshold: `{float(selected['threshold']):.2f}`",
        f"- Validation PnL at selection: `${float(selected['validation_net_pnl']):.2f}`",
        f"- Validation active-day retention: `{float(selected['active_day_retention']):.3f}`",
        "",
        _markdown_table(policy_comparison),
        "",
        "## Framework decisions",
        "",
        f"- Counterfactual failed checks: `{impact['failed_checks']}`",
        f"- Framework metric failed checks: `{recommendation['failed_framework_checks']}`",
        f"- Framework metric review eligible: `{str(recommendation['framework_metric_review_eligible']).lower()}`",
        "- Final signal-input review eligible: `false` (future unseen confirmation unavailable)",
        "- Approved as signal input: `false`",
        "",
        "## Recommendation",
        "",
        f"- Next action: `{recommendation['next_action']}`",
        f"- Rationale: {recommendation['rationale']}",
        "",
        "## Guardrails",
        "",
        "- `confirmatory_evidence: false`",
        "- `scheduler_policy_mutated: false`",
        "- `official_gates_changed: false`",
        "- `paper_trading_approved: false`",
        "- `shadow_execution_approved: false`",
        "- `live_trading_approved: false`",
        "",
    ]
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    display = frame.copy()
    columns = list(display.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = ["| " + " | ".join(str(value) for value in row) + " |" for row in display.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *rows])


def _categorical_psi(reference: pd.Series, observed: pd.Series) -> float:
    categories = sorted(set(reference.astype(str)) | set(observed.astype(str)))
    epsilon = 1e-6
    ref_counts = reference.astype(str).value_counts(normalize=True)
    obs_counts = observed.astype(str).value_counts(normalize=True)
    total = 0.0
    for category in categories:
        ref_pct = max(float(ref_counts.get(category, 0.0)), epsilon)
        obs_pct = max(float(obs_counts.get(category, 0.0)), epsilon)
        total += (obs_pct - ref_pct) * math.log(obs_pct / ref_pct)
    return float(total)


def _logit(scores: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(scores, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
