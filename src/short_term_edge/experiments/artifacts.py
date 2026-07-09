"""Run-scoped experiment artifact helpers.

These helpers keep research outputs reproducible without changing strategy logic.
Legacy `outputs/` and `reports/` files can still be written for compatibility,
while every run also gets a provenance-preserving artifact directory.
"""

from __future__ import annotations

import json
import hashlib
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


MANIFEST_SCHEMA_VERSION = "research_run_manifest/v2"
AUTHORIZATION_STAGES = {"research", "paper", "shadow", "controlled_live"}


@dataclass(frozen=True)
class ExperimentRunPaths:
    experiment_name: str
    run_id: str
    run_dir: Path
    results_path: Path
    specs_path: Path
    report_path: Path
    manifest_path: Path


def prepare_experiment_run(project_root: Path, experiment_name: str, run_id: str | None = None) -> ExperimentRunPaths:
    """Create and return standard artifact paths for one experiment run."""
    safe_name = _safe_path_segment(experiment_name)
    safe_run_id = _safe_path_segment(run_id or _timestamp_run_id())
    run_dir = project_root / "artifacts" / safe_name / safe_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return ExperimentRunPaths(
        experiment_name=safe_name,
        run_id=safe_run_id,
        run_dir=run_dir,
        results_path=run_dir / "results.csv",
        specs_path=run_dir / "specs.json",
        report_path=run_dir / "report.md",
        manifest_path=run_dir / "manifest.json",
    )


def write_experiment_manifest(
    *,
    project_root: Path,
    paths: ExperimentRunPaths,
    experiment_name: str,
    command: str,
    config: Mapping[str, Any],
    selected_specs_count: int,
    results: pd.DataFrame,
    legacy_artifacts: Mapping[str, Path] | None = None,
    guardrails: Sequence[str] = (),
    data_files: Sequence[Path] = (),
    release_id: str | None = None,
    authorization_stage: str = "research",
    schema_versions: Mapping[str, str] | None = None,
    source_versions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Write a deterministic JSON manifest describing one research run."""
    if authorization_stage not in AUTHORIZATION_STAGES:
        raise ValueError(f"unknown authorization_stage: {authorization_stage}")
    if authorization_stage != "research":
        raise ValueError("research experiment manifests cannot promote authorization_stage")
    git_state = _git_state(project_root)
    artifact_paths = {
        "results": paths.results_path,
        "specs": paths.specs_path,
        "report": paths.report_path,
        "manifest": paths.manifest_path,
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "release_id": release_id or f"{paths.experiment_name}:{paths.run_id}",
        "authorization_stage": authorization_stage,
        "approval_state": {
            "approved_as_signal_input": False,
            "paper_trading_approved": False,
            "shadow_execution_approved": False,
            "live_trading_approved": False,
        },
        "experiment": experiment_name,
        "run_id": paths.run_id,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "command": command,
        "config": _jsonable(config),
        "selected_specs_count": int(selected_specs_count),
        "result_row_count": int(len(results)),
        "label_counts": _counts(results, _label_column(results)),
        "family_counts": _counts(results, "family"),
        "artifacts": {name: _relative(project_root, path) for name, path in artifact_paths.items()},
        "legacy_artifacts": {name: _relative(project_root, path) for name, path in (legacy_artifacts or {}).items()},
        "data_files": [_relative(project_root, path) for path in data_files],
        "input_artifacts": [_artifact_record(project_root, path) for path in data_files],
        "output_artifacts": {
            name: _artifact_record(project_root, path)
            for name, path in artifact_paths.items()
            if name != "manifest"
        },
        "legacy_output_artifacts": {
            name: _artifact_record(project_root, path) for name, path in (legacy_artifacts or {}).items()
        },
        "schema_versions": dict(schema_versions or {}),
        "source_versions": dict(source_versions or {}),
        "runtime": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
        },
        "guardrails": list(guardrails),
        "git": git_state,
        "provenance": {
            "source_revision": _git_output(project_root, "rev-parse", "HEAD"),
            "dirty_worktree": bool(git_state.get("status_short")),
            "content_hash_algorithm": "sha256",
        },
    }
    paths.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def list_local_data_files(project_root: Path, symbol: str | None = None) -> list[Path]:
    """Return local raw CSV inputs that a research run may have used."""
    raw_dir = project_root / "data" / "raw"
    if not raw_dir.exists():
        return []
    files = sorted(path for path in raw_dir.glob("*.csv") if path.is_file())
    if symbol is None:
        return files
    prefix = symbol.lower()
    return [path for path in files if path.name.lower().startswith(prefix)]


def _timestamp_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")


def _safe_path_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-._")
    if not cleaned:
        raise ValueError("path segment cannot be empty")
    return cleaned


def _label_column(results: pd.DataFrame) -> str:
    label_columns = [column for column in results.columns if column.endswith("_label")]
    if label_columns:
        return label_columns[-1]
    return "label"


def _counts(results: pd.DataFrame, column: str) -> dict[str, int]:
    if results.empty or column not in results.columns:
        return {}
    values = results[column].fillna("missing").astype(str)
    return {key: int(value) for key, value in values.value_counts().sort_index().to_dict().items()}


def _relative(project_root: Path, path: Path) -> str:
    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def content_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(project_root: Path, path: Path) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": _relative(project_root, path),
        "exists": exists,
        "size_bytes": int(path.stat().st_size) if exists else None,
        "sha256": content_sha256(path) if exists else None,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _git_state(project_root: Path) -> dict[str, str]:
    return {
        "commit": _git_output(project_root, "rev-parse", "--short", "HEAD"),
        "branch": _git_output(project_root, "branch", "--show-current"),
        "status_short": _git_output(project_root, "status", "--short"),
    }


def _git_output(project_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
