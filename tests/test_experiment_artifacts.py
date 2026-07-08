from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import list_local_data_files, prepare_experiment_run, write_experiment_manifest


class ExperimentArtifactsTests(unittest.TestCase):
    def test_prepare_experiment_run_creates_run_scoped_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-experiment-artifacts-") as tmp:
            root = Path(tmp)

            paths = prepare_experiment_run(root, "phase8a_mgc_clean_family", run_id="2026-07-06_120000")

        self.assertEqual(paths.run_dir, root / "artifacts" / "phase8a_mgc_clean_family" / "2026-07-06_120000")
        self.assertEqual(paths.results_path.name, "results.csv")
        self.assertEqual(paths.specs_path.name, "specs.json")
        self.assertEqual(paths.report_path.name, "report.md")
        self.assertEqual(paths.manifest_path.name, "manifest.json")

    def test_write_experiment_manifest_records_counts_paths_guardrails_and_data_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-experiment-artifacts-") as tmp:
            root = Path(tmp)
            data_file = root / "data" / "raw" / "MGC_1m.csv"
            data_file.parent.mkdir(parents=True)
            data_file.write_text("timestamp,symbol,open,high,low,close,volume\n", encoding="utf-8")
            paths = prepare_experiment_run(root, "phase8a_mgc_clean_family", run_id="2026-07-06_120000")
            results = pd.DataFrame(
                [
                    {"candidate_id": "a", "family": "opening_range_breakout", "phase8a_label": "rejected"},
                    {"candidate_id": "b", "family": "vwap_reclaim_rejection", "phase8a_label": "mgc_clean_family_watchlist"},
                ]
            )

            manifest = write_experiment_manifest(
                project_root=root,
                paths=paths,
                experiment_name="phase8a_mgc_clean_family",
                command="PHASE8A_MAX_NEW_SPECS=0 python scripts/run_phase8a_mgc_clean_family_search.py",
                config={"symbol": "MGC", "max_specs": 12, "timeframes": [1, 3]},
                selected_specs_count=12,
                results=results,
                legacy_artifacts={"results": root / "outputs" / "phase8a_mgc_clean_family_results.csv"},
                guardrails=["research/simulation only", "no live trading"],
                data_files=[data_file],
            )
            saved = json.loads(paths.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest, saved)
        self.assertEqual(saved["experiment"], "phase8a_mgc_clean_family")
        self.assertEqual(saved["run_id"], "2026-07-06_120000")
        self.assertEqual(saved["selected_specs_count"], 12)
        self.assertEqual(saved["result_row_count"], 2)
        self.assertEqual(saved["label_counts"], {"rejected": 1, "mgc_clean_family_watchlist": 1})
        self.assertEqual(saved["family_counts"], {"opening_range_breakout": 1, "vwap_reclaim_rejection": 1})
        self.assertEqual(saved["artifacts"]["results"], "artifacts/phase8a_mgc_clean_family/2026-07-06_120000/results.csv")
        self.assertEqual(saved["legacy_artifacts"]["results"], "outputs/phase8a_mgc_clean_family_results.csv")
        self.assertEqual(saved["data_files"], ["data/raw/MGC_1m.csv"])
        self.assertIn("research/simulation only", saved["guardrails"])
        self.assertIn("git", saved)

    def test_write_experiment_manifest_counts_non_phase_label_columns(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-experiment-artifacts-") as tmp:
            root = Path(tmp)
            paths = prepare_experiment_run(root, "phase8g_event_execution_calibration", run_id="phase8g-test")
            results = pd.DataFrame(
                [
                    {"family": "vwap_reclaim_rejection", "phase8e_label": "backtest_candidate", "calibration_label": "concentrated"},
                    {"family": "vwap_reclaim_rejection", "phase8e_label": "backtest_candidate", "calibration_label": "concentrated"},
                    {"family": "volatility_compression_breakout", "phase8e_label": "backtest_candidate", "calibration_label": "rejected_timing_cost"},
                ]
            )

            manifest = write_experiment_manifest(
                project_root=root,
                paths=paths,
                experiment_name="phase8g_event_execution_calibration",
                command="python scripts/run_phase8g_event_execution_calibration.py",
                config={},
                selected_specs_count=3,
                results=results,
            )

        self.assertEqual(manifest["label_counts"], {"concentrated": 2, "rejected_timing_cost": 1})

    def test_list_local_data_files_can_filter_by_symbol(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hermes-experiment-artifacts-") as tmp:
            root = Path(tmp)
            raw = root / "data" / "raw"
            raw.mkdir(parents=True)
            mgc = raw / "mgc_1m_databento.csv"
            mnq = raw / "mnq_1m_databento.csv"
            other = raw / "notes.txt"
            for path in (mgc, mnq, other):
                path.write_text("fixture", encoding="utf-8")

            all_csvs = list_local_data_files(root)
            mgc_only = list_local_data_files(root, symbol="MGC")

        self.assertEqual(all_csvs, [mgc, mnq])
        self.assertEqual(mgc_only, [mgc])


if __name__ == "__main__":
    unittest.main()
