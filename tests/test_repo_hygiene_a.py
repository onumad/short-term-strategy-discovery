from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_REQUIREMENTS = [
    "pandas>=2.2",
    "numpy>=2.0",
    "matplotlib>=3.9",
    "databento>=0.80",
    "pyarrow>=15",
    "joblib>=1.4",
    "tqdm>=4.66",
]

GENERATED_ARTIFACT_FOLDERS = [
    "data/raw/",
    "outputs/",
    "reports/",
    "artifacts/",
    "charts/",
    "trade_logs/",
]


def _non_empty_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class RepoHygieneATests(unittest.TestCase):
    def test_requirements_has_exactly_one_dependency_per_line(self) -> None:
        lines = _non_empty_lines(PROJECT_ROOT / "requirements.txt")

        self.assertEqual(lines, EXPECTED_REQUIREMENTS)
        for line in lines:
            self.assertNotIn(" ", line)
            self.assertNotIn("\t", line)
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+[<>=!~].+")

    def test_gitignore_has_required_sections(self) -> None:
        lines = _non_empty_lines(PROJECT_ROOT / ".gitignore")

        self.assertIn("# Python", lines)
        self.assertIn("# OS/editor noise", lines)
        self.assertIn("# Generated/local research artifacts", lines)

    def test_gitignore_has_generated_artifact_folders_on_separate_lines(self) -> None:
        lines = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

        for folder in GENERATED_ARTIFACT_FOLDERS:
            self.assertIn(folder, lines)
            self.assertEqual(lines.count(folder), 1)

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
