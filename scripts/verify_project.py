"""Cross-platform verification entry point for local development and CI."""

from __future__ import annotations

import argparse
import compileall
import importlib.metadata
import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.release_verification import verify_research_manifest  # noqa: E402


QUICK_TESTS = (
    "tests.test_experiment_artifacts",
    "tests.test_features",
    "tests.test_framework_g_policy_contracts",
    "tests.test_framework_g_research_release",
    "tests.test_label_safety",
    "tests.test_release_verification",
)
CORE_LOCKED_PACKAGES = {
    "duckdb": "1.5.4",
    "hypothesis": "6.156.4",
    "numpy": "2.4.6",
    "pandas": "3.0.3",
    "pandera": "0.32.1",
    "ruff": "0.15.21",
    "scikit-learn": "1.9.0",
    "scipy": "1.17.1",
}
RELEASE_MANIFESTS = (
    Path("artifacts/ml_baseline_b_coverage_classifier/ml-baseline-b-r2-frozen/manifest.json"),
    Path("artifacts/framework_g_research_release/framework-g-r2-foundation/manifest.json"),
)
LINT_PATHS = (
    "src/short_term_edge/release_verification.py",
    "scripts/run_project_python.py",
    "scripts/verify_project.py",
    "tests/test_release_verification.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full", "release"), default="quick")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    root = args.project_root.resolve()
    failures: list[str] = []

    _check_python(failures)
    _check_locked_packages(failures)
    _compile_sources(root, failures)
    _check_tracked_json(root, failures)
    _check_private_keys(root, failures)
    _run_ruff(root, failures)
    if args.profile == "quick":
        _run_named_tests(failures)
    else:
        _run_full_tests(root, failures)
    if args.profile == "release":
        _check_clean_git(root, failures)
        _check_local_data(root, failures)
        _verify_release_manifests(root, failures)

    if failures:
        print(f"Verification profile {args.profile!r} failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Verification profile {args.profile!r} passed.")
    return 0


def _check_python(failures: list[str]) -> None:
    if sys.version_info[:2] != (3, 11):
        failures.append(f"Python 3.11 required; found {sys.version.split()[0]}")


def _check_locked_packages(failures: list[str]) -> None:
    for name, expected in CORE_LOCKED_PACKAGES.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            failures.append(f"locked package is missing: {name}=={expected}")
            continue
        if actual != expected:
            failures.append(f"locked package mismatch: {name}=={actual}, expected {expected}")


def _compile_sources(root: Path, failures: list[str]) -> None:
    for relative in ("src", "scripts", "tests"):
        if not compileall.compile_dir(root / relative, quiet=1, force=True):
            failures.append(f"Python compilation failed under {relative}")


def _tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=False)
    if result.returncode != 0:
        return []
    return [root / value.decode("utf-8") for value in result.stdout.split(b"\0") if value]


def _check_tracked_json(root: Path, failures: list[str]) -> None:
    for path in _tracked_files(root):
        if path.suffix.lower() != ".json":
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            failures.append(f"invalid tracked JSON {path.relative_to(root)}: {exc}")


def _check_private_keys(root: Path, failures: list[str]) -> None:
    marker = "-" * 5 + "BEGIN "
    suffix = "PRIVATE " + "KEY" + "-" * 5
    for path in _tracked_files(root):
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".parquet"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if marker in text and suffix in text:
            failures.append(f"possible private key in tracked file {path.relative_to(root)}")


def _run_ruff(root: Path, failures: list[str]) -> None:
    command = [sys.executable, "-m", "ruff", "check", *LINT_PATHS]
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode != 0:
        failures.append("Ruff failed for foundation tooling files")


def _run_named_tests(failures: list[str]) -> None:
    suite = unittest.defaultTestLoader.loadTestsFromNames(QUICK_TESTS)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        failures.append("hermetic quick test suite failed")


def _run_full_tests(root: Path, failures: list[str]) -> None:
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        failures.append("full unit test suite failed")


def _check_clean_git(root: Path, failures: list[str]) -> None:
    completed = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        failures.append("could not inspect Git worktree")
    elif completed.stdout.strip():
        failures.append("release verification requires a clean Git worktree")


def _check_local_data(root: Path, failures: list[str]) -> None:
    if not any((root / "data" / "raw").glob("*.csv")):
        failures.append("release verification requires at least one local data/raw CSV")


def _verify_release_manifests(root: Path, failures: list[str]) -> None:
    for relative in RELEASE_MANIFESTS:
        result = verify_research_manifest(root / relative, root, require_clean_provenance=True)
        if not result.passed:
            failures.extend(f"{relative}: {error}" for error in result.errors)
        else:
            print(f"Verified {relative} ({result.checks} checks).")


if __name__ == "__main__":
    raise SystemExit(main())
