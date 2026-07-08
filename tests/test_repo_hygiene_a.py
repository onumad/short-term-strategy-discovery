from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PACKAGES = {
    "pandas",
    "numpy",
    "matplotlib",
    "databento",
    "pyarrow",
    "joblib",
    "tqdm",
}

GENERATED_IGNORES = {
    "data/raw/",
    "outputs/",
    "reports/",
    "artifacts/",
    "charts/",
    "trade_logs/",
    "*.pyc",
    "__pycache__/",
    ".venv/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".ipynb_checkpoints/",
}


class RepoHygieneATests(unittest.TestCase):
    def test_requirements_has_one_dependency_per_non_empty_line(self) -> None:
        lines = [line.strip() for line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreater(len(lines), 0)
        for line in lines:
            self.assertNotIn(" ", line)
            self.assertNotIn("\t", line)
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+[<>=!~].+")

    def test_requirements_contains_expected_package_names(self) -> None:
        lines = [line.strip() for line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
        names = {line.split(">=", 1)[0].split("==", 1)[0] for line in lines}
        self.assertEqual(names, EXPECTED_PACKAGES)

    def test_gitignore_includes_generated_artifact_folders(self) -> None:
        gitignore_lines = set((PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
        self.assertTrue(GENERATED_IGNORES.issubset(gitignore_lines))

    def test_repo_hygiene_plan_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "repo_hygiene_a_plan.md").exists())

    def test_report_includes_research_only_no_paper_trading_guardrail(self) -> None:
        report_path = PROJECT_ROOT / "reports" / "repo_hygiene_a_label_safety_report.md"
        report = report_path.read_text(encoding="utf-8")
        self.assertIn("research/simulation only", report.lower())
        self.assertIn("paper trading not approved", report.lower())
        self.assertIn("official gates unchanged", report.lower())


if __name__ == "__main__":
    unittest.main()
