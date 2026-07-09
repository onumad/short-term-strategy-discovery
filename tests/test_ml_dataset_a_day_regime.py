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

from short_term_edge.ml_dataset_a_day_regime import (
    AVAILABILITY_TIME,
    PARTIAL_SESSIONS,
    TARGET_COLUMNS,
    add_split_columns,
    build_day_regime_features,
    build_feature_dictionary,
    build_label_dictionary,
    build_ml_dataset_a,
    complete_rth_sessions,
    load_mnq_raw_data,
)


class MlDatasetADayRegimeTests(unittest.TestCase):
    def test_loads_mnq_raw_data(self) -> None:
        raw = PROJECT_ROOT / "data" / "raw" / "mnq_1m_databento_20230101_20260703.csv"
        bars = load_mnq_raw_data(raw)
        self.assertFalse(bars.empty)
        self.assertTrue(bars["symbol"].astype(str).str.upper().str.contains("MNQ").all())

    def test_excludes_known_partial_20260703_and_one_row_per_complete_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = _write_synthetic_raw(Path(tmp) / "raw.csv")
            bars = load_mnq_raw_data(raw)
            sessions = complete_rth_sessions(bars, PARTIAL_SESSIONS)
            features = build_day_regime_features(raw)
            self.assertNotIn("2026-07-03", sessions)
            self.assertNotIn("2026-07-03", set(features["trading_session"].astype(str)))
            self.assertEqual(len(features), features["trading_session"].nunique())

    def test_prior_session_features_use_only_prior_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = _write_synthetic_raw(Path(tmp) / "raw.csv")
            features = build_day_regime_features(raw)
            second = features.iloc[1]
            first = features.iloc[0]
            self.assertEqual(second["prior_rth_close"], 489.25)
            self.assertTrue(pd.isna(first["prior_rth_close"]))

    def test_intraday_availability_windows_are_labeled(self) -> None:
        self.assertEqual(AVAILABILITY_TIME["first_30m_range"], "10:00")
        self.assertEqual(AVAILABILITY_TIME["morning_0930_1130_range"], "11:30")
        self.assertEqual(AVAILABILITY_TIME["lunch_1130_1330_range"], "13:30")
        self.assertEqual(AVAILABILITY_TIME["power_hour_range"], "post_session_diagnostic")

    def test_first30_morning_midday_features_match_windowed_synthetic_bars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw = _write_synthetic_raw(Path(tmp) / "raw.csv")
            features = build_day_regime_features(raw)
            first = features.iloc[0]
            self.assertEqual(first["first_30m_direction"], "up")
            self.assertEqual(first["morning_0930_1130_direction"], "up")
            self.assertEqual(first["lunch_direction"], "up")
            self.assertAlmostEqual(float(first["first_30m_range"]), 30.0)
            self.assertAlmostEqual(float(first["morning_0930_1130_range"]), 120.0)
            self.assertAlmostEqual(float(first["lunch_1130_1330_range"]), 120.0)

    def test_feature_dictionary_includes_availability_time_for_every_feature(self) -> None:
        dictionary = build_feature_dictionary()
        self.assertEqual(set(dictionary), set(AVAILABILITY_TIME))
        self.assertTrue(all(item["availability_time"] for item in dictionary.values()))

    def test_label_dictionary_marks_targets_and_targets_are_not_features(self) -> None:
        frame = pd.DataFrame({"trading_session": ["2026-01-02"], "first_30m_range": [1.0], "target_bad_playbook_day": [False], "playbook_daily_pnl": [0.0]})
        dictionary = build_label_dictionary(frame)
        self.assertEqual(dictionary["target_bad_playbook_day"]["role"], "target")
        self.assertNotIn("target_bad_playbook_day", build_feature_dictionary())

    def test_chronological_splits_are_deterministic(self) -> None:
        frame = pd.DataFrame({"trading_session": pd.date_range("2026-01-01", periods=20, freq="D").strftime("%Y-%m-%d")})
        first = add_split_columns(frame)
        second = add_split_columns(frame)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(set(first["chronological_split"]), {"discovery", "validation", "holdout"})

    def test_missing_optional_phase_files_handled_with_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "data" / "raw"
            raw_dir.mkdir(parents=True)
            _write_synthetic_raw(raw_dir / "mnq_1m_databento_20230101_20260703.csv")
            outputs = root / "outputs"
            outputs.mkdir()
            _write_minimal_policy_files(outputs)
            result = build_ml_dataset_a(root, run_id="unit-test")
            self.assertTrue(result["warnings"])
            self.assertTrue((outputs / "ml_dataset_a_day_regime.csv").exists())
            self.assertIn("phase10b_active", result["dataset"].columns)

    def test_no_model_training_is_performed(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_dataset_a_day_regime.py").read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertNotIn("sklearn", lowered)
        self.assertNotIn("fit(", lowered)
        self.assertNotIn("train_test_split", lowered)

    def test_official_gates_are_not_changed_and_paper_trading_false(self) -> None:
        for name in ["playbook_validation_policy.json", "playbook_scheduler_policy.json", "playbook_rare_module_policy.json"]:
            path = PROJECT_ROOT / "outputs" / name
            policy = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(bool(policy.get("official_gates_changed", False)))
            self.assertFalse(bool(policy.get("paper_trading_approved", False)))

    def test_report_includes_research_only_guardrail_after_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "data" / "raw"
            raw_dir.mkdir(parents=True)
            _write_synthetic_raw(raw_dir / "mnq_1m_databento_20230101_20260703.csv")
            (root / "outputs").mkdir()
            _write_minimal_policy_files(root / "outputs")
            build_ml_dataset_a(root, run_id="unit-test")
            report = (root / "reports" / "ml_dataset_a_day_regime_report.md").read_text(encoding="utf-8")
            self.assertIn("Research/simulation only", report)
            self.assertIn("No model training was performed", report)



def _write_synthetic_raw(path: Path) -> Path:
    rows = []
    for day, base, minutes in [
        ("2026-01-02", 100.0, 390),
        ("2026-01-05", 200.0, 390),
        ("2026-01-06", 300.0, 390),
        ("2026-07-03", 400.0, 120),
    ]:
        start = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
        for i in range(minutes):
            ts = start + pd.Timedelta(minutes=i)
            price = base + float(i)
            rows.append({
                "timestamp": ts.isoformat(),
                "symbol": "MNQ",
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.25,
                "volume": 10 + i,
            })
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_minimal_policy_files(output_dir: Path) -> None:
    policy = {"policy_name": "unit", "official_gates_changed": False, "paper_trading_approved": False, "live_trading_approved": False}
    for name in ["playbook_validation_policy.json", "playbook_scheduler_policy.json", "playbook_rare_module_policy.json"]:
        (output_dir / name).write_text(json.dumps(policy), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
