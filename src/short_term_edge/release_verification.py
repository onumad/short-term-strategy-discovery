"""Independent verification for research release manifests and frozen models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .experiments.artifacts import MANIFEST_SCHEMA_VERSION, content_sha256


RESEARCH_APPROVAL_FLAGS = (
    "approved_as_signal_input",
    "paper_trading_approved",
    "shadow_execution_approved",
    "live_trading_approved",
)


@dataclass
class VerificationResult:
    subject: str
    checks: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def check(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.errors.append(message)

    def merge(self, other: "VerificationResult") -> None:
        self.checks += other.checks
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def verify_research_manifest(
    manifest_path: Path,
    project_root: Path,
    *,
    require_clean_provenance: bool = False,
    verify_model_bundle: bool = True,
) -> VerificationResult:
    """Rehash a v2 manifest and enforce the research-only approval boundary."""
    result = VerificationResult(subject=str(manifest_path))
    manifest = _read_json_object(manifest_path, result, "manifest")
    if manifest is None:
        return result

    result.check(manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION, f"unsupported manifest schema: {manifest.get('schema_version')!r}")
    result.check(manifest.get("authorization_stage") == "research", "manifest authorization_stage must be research")
    approval = manifest.get("approval_state")
    result.check(isinstance(approval, Mapping), "manifest approval_state must be an object")
    if isinstance(approval, Mapping):
        for flag in RESEARCH_APPROVAL_FLAGS:
            result.check(approval.get(flag) is False, f"manifest {flag} must be false")

    provenance = manifest.get("provenance")
    result.check(isinstance(provenance, Mapping), "manifest provenance must be an object")
    if isinstance(provenance, Mapping):
        result.check(provenance.get("content_hash_algorithm") == "sha256", "manifest hash algorithm must be sha256")
        source_revision = provenance.get("source_revision")
        result.check(isinstance(source_revision, str) and len(source_revision) == 40, "manifest source_revision must be a full Git SHA")
        if require_clean_provenance:
            result.check(provenance.get("dirty_worktree") is False, "release manifest was produced from a dirty worktree")

    for group_name in ("input_artifacts", "output_artifacts", "legacy_output_artifacts"):
        records = manifest.get(group_name, [] if group_name == "input_artifacts" else {})
        if isinstance(records, Mapping):
            iterable: Iterable[Any] = records.values()
        elif isinstance(records, list):
            iterable = records
        else:
            result.check(False, f"manifest {group_name} must be an object or list")
            continue
        for index, record in enumerate(iterable):
            _verify_artifact_record(record, project_root, result, f"{group_name}[{index}]")

    if verify_model_bundle and _declares_model_bundle(manifest):
        model_record = _named_artifact_record(manifest.get("legacy_output_artifacts"), "model_bundle")
        if model_record is None:
            result.check(False, "model release manifest does not record a model_bundle artifact")
        else:
            bundle_path = _safe_project_path(project_root, model_record.get("path"), result, "model_bundle")
            if bundle_path is not None and bundle_path.is_file():
                result.merge(verify_frozen_model_bundle(bundle_path))
    return result


def verify_frozen_model_bundle(bundle_path: Path) -> VerificationResult:
    """Validate and deserialize every model in a frozen Baseline B bundle."""
    result = VerificationResult(subject=str(bundle_path))
    bundle = _read_json_object(bundle_path, result, "model bundle")
    if bundle is None:
        return result
    result.check(bundle.get("schema_version") == "ml_baseline_b_model_bundle/v1", "unsupported model bundle schema")
    result.check(bundle.get("authorization_stage") == "research", "model bundle authorization_stage must be research")
    for flag in ("approved_as_signal_input", "paper_trading_approved", "live_trading_approved"):
        result.check(bundle.get(flag) is False, f"model bundle {flag} must be false")
    result.check(bundle.get("confirmatory_evidence") is False, "frozen Baseline B must not claim confirmatory evidence")
    models = bundle.get("models")
    result.check(isinstance(models, list), "model bundle models must be a list")
    if not isinstance(models, list):
        return result
    result.check(bundle.get("model_count") == len(models), "model bundle count does not match models")
    try:
        from .ml_baseline_b_coverage_classifier import deserialize_logistic_model
    except ImportError as exc:
        result.errors.append(f"cannot import model deserializer: {exc}")
        return result
    for index, payload in enumerate(models):
        result.check(isinstance(payload, Mapping), f"model[{index}] must be an object")
        if not isinstance(payload, Mapping):
            continue
        try:
            model = deserialize_logistic_model(payload)
        except (KeyError, TypeError, ValueError) as exc:
            result.errors.append(f"model[{index}] cannot be deserialized: {exc}")
            continue
        result.check(len(model.coefficients) == len(model.preprocessor.encoded_features), f"model[{index}] feature/coefficient mismatch")
    return result


def _verify_artifact_record(record: Any, project_root: Path, result: VerificationResult, label: str) -> None:
    result.check(isinstance(record, Mapping), f"{label} must be an object")
    if not isinstance(record, Mapping):
        return
    path = _safe_project_path(project_root, record.get("path"), result, label)
    if path is None:
        return
    recorded_exists = record.get("exists")
    result.check(isinstance(recorded_exists, bool), f"{label}.exists must be boolean")
    actual_exists = path.is_file()
    result.check(recorded_exists == actual_exists, f"{label} existence mismatch: {record.get('path')}")
    if not actual_exists:
        return
    result.check(record.get("size_bytes") == path.stat().st_size, f"{label} size mismatch: {record.get('path')}")
    recorded_hash = record.get("sha256")
    result.check(isinstance(recorded_hash, str) and len(recorded_hash) == 64, f"{label} has invalid sha256")
    if isinstance(recorded_hash, str):
        result.check(recorded_hash == content_sha256(path), f"{label} hash mismatch: {record.get('path')}")


def _safe_project_path(project_root: Path, value: Any, result: VerificationResult, label: str) -> Path | None:
    result.check(isinstance(value, str) and bool(value), f"{label}.path must be a non-empty string")
    if not isinstance(value, str) or not value:
        return None
    root = project_root.resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        result.errors.append(f"{label}.path escapes project root: {value}")
        return None
    return candidate


def _read_json_object(path: Path, result: VerificationResult, label: str) -> dict[str, Any] | None:
    result.check(path.is_file(), f"{label} file is missing: {path}")
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result.errors.append(f"cannot read {label}: {exc}")
        return None
    result.check(isinstance(payload, dict), f"{label} must contain a JSON object")
    return payload if isinstance(payload, dict) else None


def _declares_model_bundle(manifest: Mapping[str, Any]) -> bool:
    versions = manifest.get("schema_versions")
    return isinstance(versions, Mapping) and "model_bundle" in versions


def _named_artifact_record(records: Any, name: str) -> Mapping[str, Any] | None:
    if not isinstance(records, Mapping):
        return None
    record = records.get(name)
    return record if isinstance(record, Mapping) else None
