from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact

FEATURE_WINDOWS: dict[str, tuple[str, ...]] = {
    "pre_rth_only": ("pre_rth",),
    "through_10_00": ("pre_rth", "10:00"),
    "through_11_30": ("pre_rth", "10:00", "11:30"),
    "through_13_30": ("pre_rth", "10:00", "11:30", "13:30"),
}

PRIMARY_TARGET = "target_bad_playbook_day"
OPTIONAL_TARGETS = (
    "target_high_vol_mixed_weak_day",
    "target_prior_level_interaction_day",
    "target_power_hour_expansion_day",
)
DISALLOWED_TARGETS = {"target_best_phase_group", "target_worst_phase_group", "target_no_trade_or_reduce_risk_day"}
MODEL_NAMES = ("majority_class_baseline", "univariate_threshold_stump", "logistic_regression_numpy")
THRESHOLDS = (0.30, 0.40, 0.50, 0.60, 0.70)
RANDOM_SEED = 1729
MIN_CLASS_EXAMPLES = 50


@dataclass(frozen=True)
class MlBaselineAConfig:
    dataset_path: Path
    feature_dictionary_path: Path
    label_dictionary_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "ml-baseline-a-r1"
    l2_penalty: float = 0.01
    learning_rate: float = 0.05
    iterations: int = 900


@dataclass(frozen=True)
class Preprocessor:
    raw_features: tuple[str, ...]
    encoded_features: tuple[str, ...]
    numeric_features: tuple[str, ...]
    categorical_levels: dict[str, tuple[str, ...]]
    medians: pd.Series
    means: pd.Series
    stds: pd.Series


@dataclass(frozen=True)
class LogisticModel:
    coefficients: np.ndarray
    intercept: float
    preprocessor: Preprocessor
    l2_penalty: float
    iterations: int
    learning_rate: float
    random_seed: int


@dataclass(frozen=True)
class StumpModel:
    feature: str
    threshold: float
    direction: str
    validation_score: float
    preprocessor: Preprocessor


def build_ml_baseline_a(project_root: Path, run_id: str = "ml-baseline-a-r1") -> dict[str, Any]:
    config = MlBaselineAConfig(
        dataset_path=project_root / "outputs" / "ml_dataset_a_day_regime.csv",
        feature_dictionary_path=project_root / "outputs" / "ml_dataset_a_feature_dictionary.json",
        label_dictionary_path=project_root / "outputs" / "ml_dataset_a_label_dictionary.json",
        output_dir=project_root / "outputs",
        report_dir=project_root / "reports",
        artifact_dir=project_root / "artifacts" / "ml_baseline_a_regime_classifier" / run_id,
        run_id=run_id,
    )
    return run_ml_baseline_a(config)


def run_ml_baseline_a(config: MlBaselineAConfig) -> dict[str, Any]:
    ensure_directory(config.output_dir)
    ensure_directory(config.report_dir)
    ensure_directory(config.artifact_dir)
    dataset = pd.read_csv(config.dataset_path)
    feature_dictionary = json.loads(config.feature_dictionary_path.read_text(encoding="utf-8"))
    label_dictionary = json.loads(config.label_dictionary_path.read_text(encoding="utf-8"))

    validate_inputs(dataset, feature_dictionary, label_dictionary)
    feature_sets = build_feature_sets(feature_dictionary, label_dictionary)
    target_plan = select_trainable_targets(dataset)

    metric_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    importance_rows: list[dict[str, Any]] = []
    confusion_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    availability_rows: list[dict[str, Any]] = []
    trained_model_cards: list[dict[str, Any]] = []

    for window_name, raw_features in feature_sets.items():
        availability_rows.append({
            "availability_window": window_name,
            "availability_times": ",".join(FEATURE_WINDOWS[window_name]),
            "feature_count": len(raw_features),
            "features": ",".join(raw_features),
            "post_session_diagnostic_features": 0,
        })

    for target_name in target_plan["trained_targets"]:
        y_all = to_binary_target(dataset[target_name])
        for window_name, raw_features in feature_sets.items():
            train_mask = dataset["chronological_split"].astype(str).eq("discovery")
            validation_mask = dataset["chronological_split"].astype(str).eq("validation")
            preprocessor = fit_preprocessor(dataset.loc[train_mask], raw_features)
            x_train = transform_features(dataset.loc[train_mask], preprocessor)
            y_train = y_all.loc[train_mask].to_numpy(dtype=float)
            majority_class = int(np.mean(y_train) >= 0.5)

            models: dict[str, Any] = {
                "majority_class_baseline": majority_class,
                "univariate_threshold_stump": fit_univariate_threshold_stump(dataset, y_all, preprocessor, validation_mask),
                "logistic_regression_numpy": fit_logistic_regression_numpy(x_train, y_train, preprocessor, config),
            }

            best_validation_threshold = 0.50
            logistic_model = models["logistic_regression_numpy"]
            val_scores = predict_logistic(dataset.loc[validation_mask], logistic_model)
            if len(val_scores):
                sweep_candidates = []
                for threshold in THRESHOLDS:
                    m = compute_metrics(y_all.loc[validation_mask].to_numpy(dtype=int), (val_scores >= threshold).astype(int), val_scores)
                    row = {
                        "target_name": target_name,
                        "availability_window": window_name,
                        "model_name": "logistic_regression_numpy",
                        "split": "validation",
                        "threshold": threshold,
                        "selected_for_holdout_diagnostic": False,
                        **m,
                    }
                    threshold_rows.append(row)
                    sweep_candidates.append((threshold, float(m["f1"]), float(m["balanced_accuracy"])))
                sweep_candidates.sort(key=lambda item: (item[1], item[2], -abs(item[0] - 0.5)), reverse=True)
                best_validation_threshold = float(sweep_candidates[0][0])
                for row in threshold_rows:
                    if row["target_name"] == target_name and row["availability_window"] == window_name and row["split"] == "validation" and float(row["threshold"]) == best_validation_threshold:
                        row["selected_for_holdout_diagnostic"] = True

            for model_name, model in models.items():
                threshold = 0.50
                for split in ("discovery", "validation", "holdout"):
                    split_mask = dataset["chronological_split"].astype(str).eq(split)
                    y_true = y_all.loc[split_mask].to_numpy(dtype=int)
                    y_pred, y_score = predict_model(dataset.loc[split_mask], model_name, model, threshold)
                    metrics = compute_metrics(y_true, y_pred, y_score)
                    metric_row = {
                        "target_name": target_name,
                        "availability_window": window_name,
                        "model_name": model_name,
                        "split": split,
                        "threshold": threshold,
                        "is_holdout": split == "holdout",
                        **metrics,
                    }
                    metric_rows.append(metric_row)
                    confusion_rows.append({
                        "target_name": target_name,
                        "availability_window": window_name,
                        "model_name": model_name,
                        "split": split,
                        "threshold": threshold,
                        "true_positive": metrics["true_positive"],
                        "false_positive": metrics["false_positive"],
                        "true_negative": metrics["true_negative"],
                        "false_negative": metrics["false_negative"],
                    })
                    prediction_frames.append(build_prediction_frame(dataset.loc[split_mask], y_true, y_pred, y_score, target_name, window_name, model_name, threshold))

                if model_name == "logistic_regression_numpy":
                    holdout_mask = dataset["chronological_split"].astype(str).eq("holdout")
                    y_true = y_all.loc[holdout_mask].to_numpy(dtype=int)
                    y_pred, y_score = predict_model(dataset.loc[holdout_mask], model_name, model, best_validation_threshold)
                    metrics = compute_metrics(y_true, y_pred, y_score)
                    threshold_rows.append({
                        "target_name": target_name,
                        "availability_window": window_name,
                        "model_name": model_name,
                        "split": "holdout_diagnostic_best_validation_threshold",
                        "threshold": best_validation_threshold,
                        "selected_for_holdout_diagnostic": True,
                        **metrics,
                    })

            importance_rows.extend(logistic_feature_importance_rows(target_name, window_name, logistic_model, feature_dictionary))
            importance_rows.append(stump_importance_row(target_name, window_name, models["univariate_threshold_stump"], feature_dictionary))
            trained_model_cards.append(model_card_for_target(target_name, window_name, raw_features, target_plan, config, feature_dictionary))

    metrics_df = pd.DataFrame(metric_rows)
    predictions_df = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else empty_predictions_frame()
    feature_importance_df = pd.DataFrame(importance_rows)
    confusion_df = pd.DataFrame(confusion_rows)
    threshold_df = pd.DataFrame(threshold_rows)
    availability_df = pd.DataFrame(availability_rows)
    model_cards = build_model_cards(trained_model_cards, target_plan, feature_sets)
    recommendation = build_next_action_recommendation(metrics_df, target_plan)

    paths = write_outputs(config, metrics_df, predictions_df, feature_importance_df, confusion_df, threshold_df, availability_df, model_cards, recommendation)
    report_text = render_report(dataset, target_plan, metrics_df, feature_importance_df, recommendation, paths)
    report_path = config.report_dir / "ml_baseline_a_regime_classifier_report.md"
    ensure_directory(report_path.parent)
    report_path.write_text(report_text, encoding="utf-8")
    (config.artifact_dir / report_path.name).write_text(report_text, encoding="utf-8")
    paths["report"] = report_path
    write_json_artifact({
        "run_id": config.run_id,
        "research_only": True,
        "model_trained": bool(target_plan["trained_targets"]),
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "generated_strategy_signals": False,
        "paths": {k: str(v) for k, v in paths.items()},
    }, config.artifact_dir / "manifest.json")
    return {
        "metrics": metrics_df,
        "predictions": predictions_df,
        "feature_importance": feature_importance_df,
        "confusion_matrices": confusion_df,
        "threshold_sweep": threshold_df,
        "availability_window_summary": availability_df,
        "model_cards": model_cards,
        "next_action_recommendation": recommendation,
        "target_plan": target_plan,
        "feature_sets": feature_sets,
        "paths": paths,
    }


def validate_inputs(dataset: pd.DataFrame, feature_dictionary: dict[str, Any], label_dictionary: dict[str, Any]) -> None:
    required = {"trading_session", "chronological_split", PRIMARY_TARGET}
    missing = sorted(required - set(dataset.columns))
    if missing:
        raise ValueError(f"ML Dataset A missing required columns: {missing}")
    expected_splits = {"discovery", "validation", "holdout"}
    found_splits = set(dataset["chronological_split"].astype(str))
    if not expected_splits <= found_splits:
        raise ValueError(f"ML Dataset A must include discovery/validation/holdout splits, found {sorted(found_splits)}")
    label_targets = {name for name, meta in label_dictionary.items() if bool(meta.get("is_target")) or meta.get("role") == "target"}
    overlap = sorted(set(feature_dictionary) & label_targets)
    if overlap:
        raise ValueError(f"Feature dictionary leaks target columns: {overlap}")


def build_feature_sets(feature_dictionary: dict[str, Any], label_dictionary: dict[str, Any] | None = None) -> dict[str, tuple[str, ...]]:
    label_dictionary = label_dictionary or {}
    label_columns = set(label_dictionary)
    out: dict[str, tuple[str, ...]] = {}
    for window_name, allowed_times in FEATURE_WINDOWS.items():
        selected = []
        for feature, meta in sorted(feature_dictionary.items()):
            availability_time = str(meta.get("availability_time", ""))
            if availability_time == "post_session_diagnostic":
                continue
            if availability_time in allowed_times:
                if feature.startswith("target_") or feature in label_columns or "pnl" in feature.lower():
                    raise ValueError(f"Unsafe feature selected: {feature}")
                selected.append(feature)
        out[window_name] = tuple(selected)
    return out


def select_trainable_targets(dataset: pd.DataFrame) -> dict[str, Any]:
    candidates = (PRIMARY_TARGET, *OPTIONAL_TARGETS, "target_no_trade_or_reduce_risk_day")
    trained: list[str] = []
    skipped: dict[str, str] = {}
    balances: dict[str, dict[str, int]] = {}
    for target in candidates:
        if target not in dataset.columns:
            skipped[target] = "missing from ML Dataset A"
            continue
        if target in DISALLOWED_TARGETS or target == "target_no_trade_or_reduce_risk_day":
            counts = to_binary_target(dataset[target]).value_counts().to_dict() if dataset[target].nunique(dropna=False) > 1 else dataset[target].value_counts(dropna=False).to_dict()
            balances[target] = {str(k): int(v) for k, v in counts.items()}
            skipped[target] = "explicitly excluded for ML Baseline A or single-class risk target"
            continue
        y = to_binary_target(dataset[target])
        counts = y.value_counts().to_dict()
        false_count = int(counts.get(0, 0))
        true_count = int(counts.get(1, 0))
        balances[target] = {"false": false_count, "true": true_count}
        if min(false_count, true_count) < MIN_CLASS_EXAMPLES:
            skipped[target] = f"fewer than {MIN_CLASS_EXAMPLES} examples in at least one class"
        else:
            trained.append(target)
    return {"trained_targets": trained, "skipped_targets": skipped, "target_balances": balances, "min_class_examples": MIN_CLASS_EXAMPLES}


def to_binary_target(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.astype(int)
    lowered = series.astype(str).str.lower()
    if set(lowered.dropna().unique()) <= {"true", "false", "1", "0", "nan"}:
        return lowered.isin({"true", "1"}).astype(int)
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all():
        return (numeric != 0).astype(int)
    raise ValueError(f"Target is not binary: {series.name}")


def fit_preprocessor(train: pd.DataFrame, raw_features: tuple[str, ...]) -> Preprocessor:
    numeric_features: list[str] = []
    categorical_levels: dict[str, tuple[str, ...]] = {}
    encoded_parts = []
    encoded_names: list[str] = []
    for feature in raw_features:
        values = train[feature]
        if pd.api.types.is_bool_dtype(values) or pd.api.types.is_numeric_dtype(values):
            numeric_features.append(feature)
            encoded_names.append(feature)
            encoded_parts.append(pd.to_numeric(values, errors="coerce").astype(float).rename(feature))
        else:
            normalized = values.fillna("__missing__").astype(str)
            levels = tuple(sorted(normalized.unique().tolist()))
            categorical_levels[feature] = levels
            for level in levels:
                name = f"{feature}={level}"
                encoded_names.append(name)
                encoded_parts.append(normalized.eq(level).astype(float).rename(name))
    encoded = pd.concat(encoded_parts, axis=1) if encoded_parts else pd.DataFrame(index=train.index)
    medians = encoded.median(axis=0, numeric_only=True).fillna(0.0)
    filled = encoded.fillna(medians)
    means = filled.mean(axis=0)
    stds = filled.std(axis=0, ddof=0).replace(0.0, 1.0).fillna(1.0)
    return Preprocessor(tuple(raw_features), tuple(encoded_names), tuple(numeric_features), categorical_levels, medians, means, stds)


def transform_features(frame: pd.DataFrame, preprocessor: Preprocessor, *, standardize: bool = True) -> np.ndarray:
    columns = []
    for feature in preprocessor.raw_features:
        if feature in preprocessor.categorical_levels:
            normalized = frame[feature].fillna("__missing__").astype(str)
            for level in preprocessor.categorical_levels[feature]:
                columns.append(normalized.eq(level).astype(float).rename(f"{feature}={level}"))
        else:
            columns.append(pd.to_numeric(frame[feature], errors="coerce").astype(float).rename(feature))
    encoded = pd.concat(columns, axis=1) if columns else pd.DataFrame(index=frame.index)
    encoded = encoded.reindex(columns=list(preprocessor.encoded_features), fill_value=0.0)
    encoded = encoded.fillna(preprocessor.medians)
    if standardize:
        encoded = (encoded - preprocessor.means) / preprocessor.stds
    return encoded.to_numpy(dtype=float)


def fit_logistic_regression_numpy(x_train: np.ndarray, y_train: np.ndarray, preprocessor: Preprocessor, config: MlBaselineAConfig) -> LogisticModel:
    rng = np.random.default_rng(RANDOM_SEED)
    coefficients = rng.normal(0.0, 0.001, size=x_train.shape[1]) if x_train.shape[1] else np.zeros(0)
    intercept = 0.0
    n = max(len(y_train), 1)
    for _ in range(config.iterations):
        logits = np.clip(x_train @ coefficients + intercept, -40.0, 40.0)
        probs = 1.0 / (1.0 + np.exp(-logits))
        error = probs - y_train
        grad_w = (x_train.T @ error) / n + config.l2_penalty * coefficients
        grad_b = float(np.mean(error))
        coefficients -= config.learning_rate * grad_w
        intercept -= config.learning_rate * grad_b
    return LogisticModel(coefficients, float(intercept), preprocessor, config.l2_penalty, config.iterations, config.learning_rate, RANDOM_SEED)


def predict_logistic(frame: pd.DataFrame, model: LogisticModel) -> np.ndarray:
    x = transform_features(frame, model.preprocessor)
    logits = np.clip(x @ model.coefficients + model.intercept, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-logits))


def fit_univariate_threshold_stump(dataset: pd.DataFrame, y_all: pd.Series, preprocessor: Preprocessor, validation_mask: pd.Series) -> StumpModel:
    train_mask = dataset["chronological_split"].astype(str).eq("discovery")
    x_train = transform_features(dataset.loc[train_mask], preprocessor, standardize=False)
    x_val = transform_features(dataset.loc[validation_mask], preprocessor, standardize=False)
    y_val = y_all.loc[validation_mask].to_numpy(dtype=int)
    best = ("", 0.0, "ge", -1.0, -1.0)
    for idx, feature in enumerate(preprocessor.encoded_features):
        values = x_train[:, idx]
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            continue
        unique = np.unique(finite)
        if unique.size > 25:
            thresholds = np.unique(np.quantile(finite, np.linspace(0.05, 0.95, 19)))
        else:
            thresholds = unique
        for threshold in thresholds:
            for direction in ("ge", "le"):
                pred = (x_val[:, idx] >= threshold).astype(int) if direction == "ge" else (x_val[:, idx] <= threshold).astype(int)
                metrics = compute_metrics(y_val, pred, pred.astype(float))
                score = float(metrics["f1"])
                bal = float(metrics["balanced_accuracy"])
                if (score, bal) > (best[3], best[4]):
                    best = (feature, float(threshold), direction, score, bal)
    if not best[0]:
        best = (preprocessor.encoded_features[0] if preprocessor.encoded_features else "constant", 0.0, "ge", 0.0, 0.0)
    return StumpModel(best[0], best[1], best[2], best[3], preprocessor)


def predict_model(frame: pd.DataFrame, model_name: str, model: Any, threshold: float) -> tuple[np.ndarray, np.ndarray | None]:
    if model_name == "majority_class_baseline":
        pred = np.full(len(frame), int(model), dtype=int)
        return pred, np.full(len(frame), float(model), dtype=float)
    if model_name == "logistic_regression_numpy":
        score = predict_logistic(frame, model)
        return (score >= threshold).astype(int), score
    if model_name == "univariate_threshold_stump":
        x = transform_features(frame, model.preprocessor, standardize=False)
        idx = list(model.preprocessor.encoded_features).index(model.feature) if model.feature in model.preprocessor.encoded_features else 0
        pred = (x[:, idx] >= model.threshold).astype(int) if model.direction == "ge" else (x[:, idx] <= model.threshold).astype(int)
        return pred, pred.astype(float)
    raise ValueError(f"Unknown model: {model_name}")


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_score: np.ndarray | None = None) -> dict[str, Any]:
    y_true = y_true.astype(int)
    y_pred = y_pred.astype(int)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    total = len(y_true)
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    balanced_accuracy = (recall + specificity) / 2.0
    return {
        "accuracy": round(float(accuracy), 6),
        "precision": round(float(precision), 6),
        "recall": round(float(recall), 6),
        "f1": round(float(f1), 6),
        "balanced_accuracy": round(float(balanced_accuracy), 6),
        "roc_auc": round(float(roc_auc(y_true, y_score)), 6) if y_score is not None else np.nan,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "predicted_positive_rate": round(float(y_pred.mean()), 6) if total else 0.0,
        "baseline_positive_rate": round(float(y_true.mean()), 6) if total else 0.0,
    }


def roc_auc(y_true: np.ndarray, y_score: np.ndarray | None) -> float:
    if y_score is None or len(np.unique(y_true)) < 2:
        return float("nan")
    scores = np.asarray(y_score, dtype=float)
    order = np.argsort(scores)
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=float)
    start = 0
    while start < len(scores):
        end = start + 1
        while end < len(scores) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        avg_rank = (start + 1 + end) / 2.0
        ranks[order[start:end]] = avg_rank
        start = end
    pos = y_true == 1
    n_pos = int(pos.sum())
    n_neg = int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def build_prediction_frame(frame: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, y_score: np.ndarray | None, target_name: str, window_name: str, model_name: str, threshold: float) -> pd.DataFrame:
    return pd.DataFrame({
        "session_date": frame["trading_session"].astype(str).to_numpy(),
        "chronological_split": frame["chronological_split"].astype(str).to_numpy(),
        "target_name": target_name,
        "availability_window": window_name,
        "model_name": model_name,
        "y_true": y_true.astype(int),
        "y_pred": y_pred.astype(int),
        "y_score": y_score if y_score is not None else np.nan,
        "threshold": threshold,
        "is_holdout": frame["chronological_split"].astype(str).eq("holdout").to_numpy(),
    })


def empty_predictions_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["session_date", "chronological_split", "target_name", "availability_window", "model_name", "y_true", "y_pred", "y_score", "threshold", "is_holdout"])


def logistic_feature_importance_rows(target_name: str, window_name: str, model: LogisticModel, feature_dictionary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    coefs = list(zip(model.preprocessor.encoded_features, model.coefficients))
    ranked = sorted(coefs, key=lambda item: abs(float(item[1])), reverse=True)
    rank_by_name = {name: idx + 1 for idx, (name, _) in enumerate(ranked)}
    for feature_name, coef in coefs:
        raw_feature = feature_name.split("=", 1)[0]
        meta = feature_dictionary.get(raw_feature, {})
        rows.append({
            "target_name": target_name,
            "availability_window": window_name,
            "model_name": "logistic_regression_numpy",
            "feature": feature_name,
            "raw_feature": raw_feature,
            "coefficient": round(float(coef), 8),
            "absolute_coefficient": round(abs(float(coef)), 8),
            "absolute_coefficient_rank": rank_by_name[feature_name],
            "sign": "positive" if coef > 0 else "negative" if coef < 0 else "zero",
            "availability_time": meta.get("availability_time", "unknown"),
            "feature_group": meta.get("feature_group", "unknown"),
            "selected_feature": "",
            "threshold": np.nan,
            "direction": "",
            "validation_score": np.nan,
        })
    return rows


def stump_importance_row(target_name: str, window_name: str, model: StumpModel, feature_dictionary: dict[str, Any]) -> dict[str, Any]:
    raw_feature = model.feature.split("=", 1)[0]
    meta = feature_dictionary.get(raw_feature, {})
    return {
        "target_name": target_name,
        "availability_window": window_name,
        "model_name": "univariate_threshold_stump",
        "feature": model.feature,
        "raw_feature": raw_feature,
        "coefficient": np.nan,
        "absolute_coefficient": np.nan,
        "absolute_coefficient_rank": np.nan,
        "sign": "",
        "availability_time": meta.get("availability_time", "unknown"),
        "feature_group": meta.get("feature_group", "unknown"),
        "selected_feature": model.feature,
        "threshold": model.threshold,
        "direction": model.direction,
        "validation_score": round(float(model.validation_score), 6),
    }


def model_card_for_target(target_name: str, window_name: str, raw_features: tuple[str, ...], target_plan: dict[str, Any], config: MlBaselineAConfig, feature_dictionary: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_name": target_name,
        "availability_window": window_name,
        "models": list(MODEL_NAMES),
        "feature_count": len(raw_features),
        "feature_availability_times": sorted({feature_dictionary[f]["availability_time"] for f in raw_features}),
        "l2_penalty": config.l2_penalty,
        "learning_rate": config.learning_rate,
        "iterations": config.iterations,
        "random_seed": RANDOM_SEED,
        "target_balance": target_plan["target_balances"].get(target_name, {}),
    }


def build_model_cards(cards: list[dict[str, Any]], target_plan: dict[str, Any], feature_sets: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    return {
        "research_only": True,
        "live_trading_approved": False,
        "paper_trading_approved": False,
        "official_gates_changed": False,
        "model_trained": bool(target_plan["trained_targets"]),
        "allowed_use": "diagnostic regime classification only",
        "disallowed_use": "live entries, live exits, sizing, automated trading",
        "feature_availability_windows": {name: list(features) for name, features in feature_sets.items()},
        "target_definitions": target_plan["target_balances"],
        "trained_targets": target_plan["trained_targets"],
        "skipped_targets": target_plan["skipped_targets"],
        "leakage_controls": [
            "features are selected only from ML Dataset A feature_dictionary availability_time",
            "post_session_diagnostic fields are excluded from every trainable window",
            "target, label, PnL, split metadata, and diagnostic label columns are not used as features",
            "imputation medians and standardization means/stds are fit on discovery split only",
            "holdout is never used for fitting or threshold selection",
        ],
        "limitations": [
            "pandas/numpy deterministic baselines only; no package installs and no hyperparameter search",
            "outputs are diagnostic evidence only and do not generate strategy signals",
            "holdout metrics are final diagnostics, not training feedback",
        ],
        "model_cards_by_target_window": cards,
    }


def build_next_action_recommendation(metrics: pd.DataFrame, target_plan: dict[str, Any]) -> dict[str, Any]:
    if PRIMARY_TARGET not in target_plan["trained_targets"]:
        action = "collect_more_data_before_ml"
        rationale = "Primary target class balance is inadequate for ML Baseline A."
    elif metrics.empty:
        action = "insufficient_ml_signal"
        rationale = "No model metrics were produced."
    else:
        primary = metrics[metrics["target_name"].eq(PRIMARY_TARGET)]
        majority = primary[primary["model_name"].eq("majority_class_baseline")]
        models = primary[~primary["model_name"].eq("majority_class_baseline")]
        val_good = split_beats_majority(models, majority, "validation")
        holdout_good = split_beats_majority(models, majority, "holdout")
        if val_good and holdout_good:
            action = "ml_baseline_b_regime_filter_backtest_diagnostic"
            rationale = "At least one diagnostic model/window meaningfully beat the majority baseline on both validation and final holdout."
        elif val_good and not holdout_good:
            action = "improve_ml_dataset_a_feature_quality"
            rationale = "Validation improved over majority baseline, but holdout did not confirm the diagnostic edge."
        else:
            action = "insufficient_ml_signal"
            rationale = "Diagnostic classifiers did not meaningfully beat the majority baseline on validation."
    return {
        "next_action": action,
        "rationale": rationale,
        "research_only": True,
        "model_trained": bool(target_plan["trained_targets"]),
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "generated_strategy_signals": False,
        "trained_targets": target_plan["trained_targets"],
        "skipped_targets": target_plan["skipped_targets"],
    }


def split_beats_majority(models: pd.DataFrame, majority: pd.DataFrame, split: str) -> bool:
    model_split = models[models["split"].eq(split)]
    majority_split = majority[majority["split"].eq(split)]
    if model_split.empty or majority_split.empty:
        return False
    joined = model_split.merge(majority_split[["availability_window", "f1", "balanced_accuracy"]], on="availability_window", suffixes=("", "_majority"))
    if joined.empty:
        return False
    improved = (joined["f1"] >= joined["f1_majority"] + 0.02) & (joined["balanced_accuracy"] >= joined["balanced_accuracy_majority"] + 0.02)
    return bool(improved.any())


def write_outputs(config: MlBaselineAConfig, metrics: pd.DataFrame, predictions: pd.DataFrame, feature_importance: pd.DataFrame, confusion: pd.DataFrame, threshold: pd.DataFrame, availability: pd.DataFrame, model_cards: dict[str, Any], recommendation: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "metrics": config.output_dir / "ml_baseline_a_model_metrics.csv",
        "predictions": config.output_dir / "ml_baseline_a_predictions.csv",
        "feature_importance": config.output_dir / "ml_baseline_a_feature_importance.csv",
        "confusion_matrices": config.output_dir / "ml_baseline_a_confusion_matrices.csv",
        "threshold_sweep": config.output_dir / "ml_baseline_a_threshold_sweep.csv",
        "availability_window_summary": config.output_dir / "ml_baseline_a_availability_window_summary.csv",
        "model_cards": config.output_dir / "ml_baseline_a_model_cards.json",
        "recommendation": config.output_dir / "ml_baseline_a_next_action_recommendation.json",
    }
    for key, frame in [("metrics", metrics), ("predictions", predictions), ("feature_importance", feature_importance), ("confusion_matrices", confusion), ("threshold_sweep", threshold), ("availability_window_summary", availability)]:
        write_csv_artifact(frame, paths[key])
        write_csv_artifact(frame, config.artifact_dir / paths[key].name)
    write_json_artifact(model_cards, paths["model_cards"])
    write_json_artifact(recommendation, paths["recommendation"])
    write_json_artifact(model_cards, config.artifact_dir / paths["model_cards"].name)
    write_json_artifact(recommendation, config.artifact_dir / paths["recommendation"].name)
    return paths


def render_report(dataset: pd.DataFrame, target_plan: dict[str, Any], metrics: pd.DataFrame, feature_importance: pd.DataFrame, recommendation: dict[str, Any], paths: dict[str, Path]) -> str:
    lines = [
        "# ML Baseline A — Regime Classifier",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "This is not a trading strategy phase. No strategy signals, live predictions, broker adapters, order routing, webhooks, credentials, automated execution, paper-trading approval, promotions, or official gate changes were produced.",
        "",
        f"Rows: {len(dataset)}",
        f"Date range: {dataset['trading_session'].min()} to {dataset['trading_session'].max()}",
        f"Trained targets: {target_plan['trained_targets']}",
        f"Skipped targets: {target_plan['skipped_targets']}",
        f"Feature windows: {list(FEATURE_WINDOWS)}",
        f"Models: {list(MODEL_NAMES)}",
        "",
        "## Validation / holdout diagnostics",
    ]
    if not metrics.empty:
        primary = metrics[(metrics["target_name"].eq(PRIMARY_TARGET)) & (metrics["split"].isin(["validation", "holdout"]))]
        summary = primary.sort_values(["split", "balanced_accuracy", "f1"], ascending=[True, False, False]).groupby("split").head(5)
        for _, row in summary.iterrows():
            lines.append(f"- {row['split']} {row['availability_window']} {row['model_name']}: f1={row['f1']}, balanced_accuracy={row['balanced_accuracy']}, accuracy={row['accuracy']}, roc_auc={row['roc_auc']}")
    lines.extend(["", "## Top diagnostic features"])
    if not feature_importance.empty:
        top = feature_importance[(feature_importance["target_name"].eq(PRIMARY_TARGET)) & (feature_importance["model_name"].eq("logistic_regression_numpy"))].sort_values("absolute_coefficient_rank").head(10)
        for _, row in top.iterrows():
            lines.append(f"- {row['availability_window']} {row['feature']}: coef={row['coefficient']} ({row['sign']}), availability={row['availability_time']}, group={row['feature_group']}")
    lines.extend([
        "",
        "## Leakage controls",
        "- Trainable feature windows exclude post_session_diagnostic fields.",
        "- Target, label, PnL, future-outcome, split-metadata, and diagnostic label columns are not trainable features.",
        "- Discovery split only is used to fit imputation medians and scaling means/stds.",
        "- Holdout is final diagnostic only and is not used for fitting or threshold selection.",
        "",
        f"Next action: {recommendation['next_action']}",
        f"Rationale: {recommendation['rationale']}",
        "",
        "## Output artifacts",
    ])
    for key, path in paths.items():
        lines.append(f"- {key}: {path}")
    return "\n".join(lines) + "\n"
