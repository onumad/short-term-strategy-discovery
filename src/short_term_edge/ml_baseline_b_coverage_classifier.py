from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .ml_baseline_a_regime_classifier import (
    FEATURE_WINDOWS,
    MODEL_NAMES,
    MlBaselineAConfig,
    build_prediction_frame,
    compute_metrics,
    fit_logistic_regression_numpy,
    fit_preprocessor,
    fit_univariate_threshold_stump,
    logistic_feature_importance_rows,
    predict_model,
    stump_importance_row,
    transform_features,
)
from .ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact


TARGETS = (
    "target_default_scheduler_active_day_loss_d",
    "target_default_scheduler_active_day_large_loss_d",
)
SPLIT_VARIANTS = (
    "active_coverage_chronological_split",
    "rolling_labeled_fold_1",
    "rolling_labeled_fold_2",
    "rolling_labeled_fold_3",
)
PRIMARY_SPLIT = SPLIT_VARIANTS[0]


@dataclass(frozen=True)
class MlBaselineBConfig:
    project_root: Path
    dataset_path: Path
    feature_dictionary_path: Path
    label_dictionary_path: Path
    readiness_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "ml-baseline-b-r1"
    l2_penalty: float = 0.01
    learning_rate: float = 0.05
    iterations: int = 900


def build_ml_baseline_b(project_root: Path, run_id: str = "ml-baseline-b-r1") -> dict[str, Any]:
    outputs = project_root / "outputs"
    return run_ml_baseline_b(
        MlBaselineBConfig(
            project_root=project_root,
            dataset_path=outputs / "ml_target_d_day_regime.csv",
            feature_dictionary_path=outputs / "ml_dataset_b_feature_dictionary.json",
            label_dictionary_path=outputs / "ml_target_d_label_dictionary.json",
            readiness_path=outputs / "ml_target_d_target_readiness_summary.csv",
            output_dir=outputs,
            report_dir=project_root / "reports",
            artifact_dir=project_root / "artifacts" / "ml_baseline_b_coverage_classifier" / run_id,
            run_id=run_id,
        )
    )


def run_ml_baseline_b(config: MlBaselineBConfig) -> dict[str, Any]:
    for directory in (config.output_dir, config.report_dir, config.artifact_dir):
        ensure_directory(directory)
    dataset = pd.read_csv(config.dataset_path)
    feature_dictionary = json.loads(config.feature_dictionary_path.read_text(encoding="utf-8"))
    label_dictionary = json.loads(config.label_dictionary_path.read_text(encoding="utf-8"))
    readiness = pd.read_csv(config.readiness_path)
    feature_sets = build_feature_sets(feature_dictionary, label_dictionary)
    validate_inputs(dataset, feature_sets, label_dictionary, readiness)

    metrics_rows: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    importance_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    for target in TARGETS:
        for split_variant in SPLIT_VARIANTS:
            labeled = dataset[dataset[target].notna() & dataset[split_variant].isin(["train", "validation", "holdout"])].copy()
            labeled["chronological_split"] = labeled[split_variant].astype(str)
            y_all = labeled[target].map(_as_bool).astype(int)
            for window_name, features in feature_sets.items():
                train_mask = labeled["chronological_split"].eq("train")
                validation_mask = labeled["chronological_split"].eq("validation")
                preprocessor = fit_preprocessor(labeled.loc[train_mask], features)
                x_train = transform_features(labeled.loc[train_mask], preprocessor)
                y_train = y_all.loc[train_mask].to_numpy(dtype=float)
                baseline_config = MlBaselineAConfig(
                    dataset_path=config.dataset_path,
                    feature_dictionary_path=config.feature_dictionary_path,
                    label_dictionary_path=config.label_dictionary_path,
                    output_dir=config.output_dir,
                    report_dir=config.report_dir,
                    artifact_dir=config.artifact_dir,
                    run_id=config.run_id,
                    l2_penalty=config.l2_penalty,
                    learning_rate=config.learning_rate,
                    iterations=config.iterations,
                )
                models: dict[str, Any] = {
                    "majority_class_baseline": int(np.mean(y_train) >= 0.5),
                    "univariate_threshold_stump": fit_univariate_threshold_stump(
                        labeled, y_all, preprocessor, validation_mask
                    ),
                    "logistic_regression_numpy": fit_logistic_regression_numpy(
                        x_train, y_train, preprocessor, baseline_config
                    ),
                }
                for model_name, model in models.items():
                    for split in ("train", "validation", "holdout"):
                        mask = labeled["chronological_split"].eq(split)
                        y_true = y_all.loc[mask].to_numpy(dtype=int)
                        y_pred, y_score = predict_model(labeled.loc[mask], model_name, model, 0.5)
                        metrics_rows.append(
                            {
                                "target_name": target,
                                "split_variant": split_variant,
                                "availability_window": window_name,
                                "model_name": model_name,
                                "split": split,
                                "threshold": 0.5,
                                **compute_metrics(y_true, y_pred, y_score),
                            }
                        )
                        predictions = build_prediction_frame(
                            labeled.loc[mask], y_true, y_pred, y_score, target, window_name, model_name, 0.5
                        )
                        predictions.insert(2, "split_variant", split_variant)
                        prediction_frames.append(predictions)
                if split_variant == PRIMARY_SPLIT:
                    importance_rows.extend(
                        {
                            **row,
                            "split_variant": split_variant,
                        }
                        for row in logistic_feature_importance_rows(
                            target, window_name, models["logistic_regression_numpy"], feature_dictionary
                        )
                    )
                    importance_rows.append(
                        {
                            **stump_importance_row(
                                target, window_name, models["univariate_threshold_stump"], feature_dictionary
                            ),
                            "split_variant": split_variant,
                        }
                    )
                    model_rows.append(
                        {
                            "target_name": target,
                            "split_variant": split_variant,
                            "availability_window": window_name,
                            "feature_count": len(features),
                            "features": list(features),
                            "models": list(MODEL_NAMES),
                            "training_rows": int(train_mask.sum()),
                            "validation_rows": int(validation_mask.sum()),
                            "holdout_rows": int(labeled["chronological_split"].eq("holdout").sum()),
                        }
                    )

    metrics = pd.DataFrame(metrics_rows)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    importance = pd.DataFrame(importance_rows)
    stability = build_stability_summary(metrics)
    recommendation = build_recommendation(metrics, stability)
    model_card = build_model_card(config, feature_sets, model_rows, recommendation)
    paths = write_outputs(config, metrics, predictions, importance, stability, model_card, recommendation)
    paths["report"] = config.report_dir / "ml_baseline_b_coverage_classifier_report.md"
    paths["report"].write_text(render_report(metrics, stability, recommendation), encoding="utf-8")
    shutil.copy2(paths["report"], config.artifact_dir / paths["report"].name)
    manifest = {
        "run_id": config.run_id,
        "research_only": True,
        "model_trained": True,
        "generated_strategy_signals": False,
        "registry_mutated": False,
        "scheduler_policy_mutated": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "next_action": recommendation["next_action"],
        "files": sorted(path.name for path in paths.values()),
    }
    paths["manifest"] = write_json_artifact(manifest, config.artifact_dir / "manifest.json")
    return {
        "metrics": metrics,
        "predictions": predictions,
        "feature_importance": importance,
        "stability_summary": stability,
        "model_card": model_card,
        "next_action_recommendation": recommendation,
        "paths": paths,
    }


def build_feature_sets(
    feature_dictionary: dict[str, Any], label_dictionary: dict[str, Any]
) -> dict[str, tuple[str, ...]]:
    targets = {name for name, meta in label_dictionary.items() if bool(meta.get("is_target", False))}
    out: dict[str, tuple[str, ...]] = {}
    for window_name, allowed_times in FEATURE_WINDOWS.items():
        selected = []
        for feature, meta in sorted(feature_dictionary.items()):
            if not bool(meta.get("use_in_baseline_b", False)) or str(meta.get("role")) != "feature":
                continue
            if str(meta.get("availability_time")) not in allowed_times:
                continue
            if feature in targets or feature.startswith("target_") or "pnl" in feature.lower():
                raise ValueError(f"Unsafe Baseline B feature selected: {feature}")
            selected.append(feature)
        out[window_name] = tuple(selected)
    return out


def validate_inputs(
    dataset: pd.DataFrame,
    feature_sets: dict[str, tuple[str, ...]],
    labels: dict[str, Any],
    readiness: pd.DataFrame,
) -> None:
    required = {"trading_session", *TARGETS, *SPLIT_VARIANTS}
    required.update(feature for features in feature_sets.values() for feature in features)
    if missing := sorted(required - set(dataset.columns)):
        raise ValueError(f"ML Target D dataset missing columns: {missing}")
    for target in TARGETS:
        if not bool(labels.get(target, {}).get("trainable_for_baseline_b", False)):
            raise ValueError(f"Target not approved for Baseline B: {target}")
        for split_variant in SPLIT_VARIANTS:
            ready = readiness[
                readiness["target_name"].eq(target)
                & readiness["split_variant"].eq(split_variant)
                & readiness["trainable_for_baseline_b"].map(_as_bool)
            ]
            if ready.empty:
                raise ValueError(f"Target/split pair is not ready: {target} / {split_variant}")
    for window_name, features in feature_sets.items():
        if not features:
            raise ValueError(f"Feature window is empty: {window_name}")


def build_stability_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["target_name", "availability_window", "model_name"]
    for key, group in metrics[metrics["split"].eq("holdout")].groupby(keys):
        target, window, model = key
        majority = metrics[
            metrics["target_name"].eq(target)
            & metrics["availability_window"].eq(window)
            & metrics["model_name"].eq("majority_class_baseline")
            & metrics["split"].eq("holdout")
        ][["split_variant", "f1", "balanced_accuracy"]]
        joined = group.merge(majority, on="split_variant", suffixes=("", "_majority"))
        joined["beats_majority"] = (
            (joined["f1"] >= joined["f1_majority"] + 0.02)
            & (joined["balanced_accuracy"] >= joined["balanced_accuracy_majority"] + 0.02)
        )
        rolling = joined[joined["split_variant"].str.startswith("rolling_labeled_fold_")]
        primary = joined[joined["split_variant"].eq(PRIMARY_SPLIT)]
        rows.append(
            {
                "target_name": target,
                "availability_window": window,
                "model_name": model,
                "primary_holdout_beats_majority": bool(primary["beats_majority"].any()),
                "rolling_holdouts_beating_majority": int(rolling["beats_majority"].sum()),
                "rolling_holdout_count": int(len(rolling)),
                "stable_holdout_improvement": bool(
                    primary["beats_majority"].any() and int(rolling["beats_majority"].sum()) >= 2
                ),
                "mean_holdout_balanced_accuracy": round(float(joined["balanced_accuracy"].mean()), 6),
                "mean_holdout_f1": round(float(joined["f1"].mean()), 6),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["stable_holdout_improvement", "mean_holdout_balanced_accuracy", "mean_holdout_f1"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def build_recommendation(metrics: pd.DataFrame, stability: pd.DataFrame) -> dict[str, Any]:
    stable = stability[
        ~stability["model_name"].eq("majority_class_baseline")
        & stability["stable_holdout_improvement"].map(_as_bool)
    ]
    base = {
        "research_only": True,
        "model_trained": True,
        "generated_strategy_signals": False,
        "registry_mutated": False,
        "scheduler_policy_mutated": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "stable_model_window_count": int(len(stable)),
    }
    if stable.empty:
        return {
            **base,
            "next_action": "stop_ml_baseline_b_insufficient_stable_signal",
            "rationale": "No fixed baseline model/window beat the majority classifier on the primary holdout and at least two of three rolling holdouts.",
        }
    top = stable.iloc[0].to_dict()
    return {
        **base,
        "next_action": "ml_baseline_b_calibration_and_policy_impact_diagnostic",
        "rationale": "At least one fixed baseline model/window showed stable holdout improvement; calibration and counterfactual policy impact remain required before any use as a signal input.",
        "top_stable_model": top,
    }


def build_model_card(
    config: MlBaselineBConfig,
    feature_sets: dict[str, tuple[str, ...]],
    model_rows: list[dict[str, Any]],
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "research_only": True,
        "allowed_use": "offline diagnostic prediction of replayed default-scheduler active-day loss classes",
        "disallowed_use": "orders, sizing, risk overrides, scheduler mutation, paper or live trading",
        "targets": list(TARGETS),
        "split_variants": list(SPLIT_VARIANTS),
        "feature_windows": {key: list(value) for key, value in feature_sets.items()},
        "models": list(MODEL_NAMES),
        "random_seed": 1729,
        "l2_penalty": config.l2_penalty,
        "learning_rate": config.learning_rate,
        "iterations": config.iterations,
        "preprocessing_fit_rule": "fit separately on each target/split training partition only",
        "threshold_rule": "fixed 0.50; no holdout threshold tuning",
        "model_rows": model_rows,
        "recommendation": recommendation,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def write_outputs(
    config: MlBaselineBConfig,
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    importance: pd.DataFrame,
    stability: pd.DataFrame,
    model_card: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, Path]:
    paths = {
        "metrics": config.output_dir / "ml_baseline_b_model_metrics.csv",
        "predictions": config.output_dir / "ml_baseline_b_predictions.csv",
        "feature_importance": config.output_dir / "ml_baseline_b_feature_importance.csv",
        "stability": config.output_dir / "ml_baseline_b_stability_summary.csv",
        "model_card": config.output_dir / "ml_baseline_b_model_card.json",
        "recommendation": config.output_dir / "ml_baseline_b_next_action_recommendation.json",
    }
    for key, frame in (
        ("metrics", metrics),
        ("predictions", predictions),
        ("feature_importance", importance),
        ("stability", stability),
    ):
        write_csv_artifact(frame, paths[key])
        shutil.copy2(paths[key], config.artifact_dir / paths[key].name)
    write_json_artifact(model_card, paths["model_card"])
    write_json_artifact(recommendation, paths["recommendation"])
    shutil.copy2(paths["model_card"], config.artifact_dir / paths["model_card"].name)
    shutil.copy2(paths["recommendation"], config.artifact_dir / paths["recommendation"].name)
    return paths


def render_report(metrics: pd.DataFrame, stability: pd.DataFrame, recommendation: dict[str, Any]) -> str:
    top = stability[~stability["model_name"].eq("majority_class_baseline")].head(10)
    lines = [
        "# ML Baseline B — Coverage-Aligned Loss Classifier",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "No strategy signals, scheduler changes, risk overrides, paper approval, or live approval were produced.",
        "",
        "## Scope",
        f"- Targets: `{list(TARGETS)}`",
        f"- Split variants: `{list(SPLIT_VARIANTS)}`",
        f"- Metric rows: `{len(metrics)}`",
        "- Preprocessing and model fitting occur separately on each chronological training partition.",
        "- Holdout partitions are used only for final diagnostics; classification threshold is fixed at 0.50.",
        "",
        "## Holdout stability",
        "| Target | Window | Model | Primary beat | Rolling beats | Mean balanced accuracy | Mean F1 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for _, row in top.iterrows():
        lines.append(
            f"| {row['target_name']} | {row['availability_window']} | {row['model_name']} | "
            f"{row['primary_holdout_beats_majority']} | {row['rolling_holdouts_beating_majority']}/3 | "
            f"{row['mean_holdout_balanced_accuracy']:.3f} | {row['mean_holdout_f1']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            f"- Next action: `{recommendation['next_action']}`",
            f"- Rationale: {recommendation['rationale']}",
            "",
            "## Guardrails",
            "- `generated_strategy_signals: false`",
            "- `registry_mutated: false`",
            "- `scheduler_policy_mutated: false`",
            "- `paper_trading_approved: false`",
            "- `live_trading_approved: false`",
        ]
    )
    return "\n".join(lines) + "\n"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
