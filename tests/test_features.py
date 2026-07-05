from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.features import PHASE5B_FEATURE_SCHEMA, build_feature_frame, build_phase5b_feature_dataset


def two_session_bars() -> pd.DataFrame:
    frames = []
    for session, base in [("2026-01-02", 100.0), ("2026-01-05", 200.0)]:
        timestamps = pd.date_range(f"{session} 09:30", periods=8, freq="min", tz="America/New_York")
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "symbol": "MNQ",
                    "open": [base + i for i in range(8)],
                    "high": [base + i + 1 for i in range(8)],
                    "low": [base + i - 1 for i in range(8)],
                    "close": [base + i + 0.5 for i in range(8)],
                    "volume": [10 + i for i in range(8)],
                    "trading_session": [pd.Timestamp(session).date()] * 8,
                    "session_segment": ["RTH"] * 8,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def phase5b_fixture() -> pd.DataFrame:
    frames = []
    for session, base in [("2026-01-02", 100.0), ("2026-01-05", 200.0)]:
        session_date = pd.Timestamp(session).date()
        eth_times = pd.date_range(f"{session} 08:00", periods=3, freq="min", tz="America/New_York")
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": eth_times,
                    "symbol": "MNQ",
                    "open": [base - 3, base - 2, base - 1],
                    "high": [base - 2, base - 1, base],
                    "low": [base - 5, base - 4, base - 3],
                    "close": [base - 2.5, base - 1.5, base - 0.5],
                    "volume": [5, 6, 7],
                    "trading_session": [session_date] * 3,
                    "session_segment": ["ETH"] * 3,
                }
            )
        )
        rth_times = pd.date_range(f"{session} 09:30", periods=35, freq="min", tz="America/New_York")
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": rth_times,
                    "symbol": "MNQ",
                    "open": [base + i for i in range(35)],
                    "high": [base + i + 1 for i in range(35)],
                    "low": [base + i - 1 for i in range(35)],
                    "close": [base + i + 0.5 for i in range(35)],
                    "volume": [10 + i for i in range(35)],
                    "trading_session": [session_date] * 35,
                    "session_segment": ["RTH"] * 35,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


class FeatureTests(unittest.TestCase):
    def test_opening_range_levels_are_unavailable_until_window_completes(self) -> None:
        features = build_feature_frame(two_session_bars(), opening_range_minutes=3, forward_minutes=2)
        first = features[features["trading_session"] == pd.Timestamp("2026-01-02").date()].reset_index(drop=True)
        self.assertTrue(pd.isna(first.loc[0, "or_high_3m"] ))
        self.assertTrue(pd.isna(first.loc[1, "or_high_3m"] ))
        self.assertTrue(pd.isna(first.loc[2, "or_high_3m"] ))
        self.assertEqual(float(first.loc[3, "or_high_3m"]), 103.0)

    def test_prior_session_levels_are_shifted(self) -> None:
        features = build_feature_frame(two_session_bars(), opening_range_minutes=3, forward_minutes=2)
        second = features[features["trading_session"] == pd.Timestamp("2026-01-05").date()].reset_index(drop=True)
        self.assertEqual(float(second.loc[0, "prior_session_high"]), 108.0)
        self.assertEqual(float(second.loc[0, "prior_session_low"]), 99.0)
        self.assertNotEqual(float(second.loc[0, "prior_session_high"]), float(second["high"].max()))

    def test_forward_labels_are_separate_future_columns(self) -> None:
        features = build_feature_frame(two_session_bars(), opening_range_minutes=3, forward_minutes=2)
        self.assertIn("label_forward_close_2m", features.columns)
        self.assertIn("label_forward_return_2m", features.columns)
        row = features.iloc[0]
        self.assertEqual(float(row["label_forward_close_2m"]), float(features.iloc[2]["close"]))
        self.assertNotIn("future_close", [c for c in features.columns if not c.startswith("label_")])

    def test_phase5b_schema_is_stable(self) -> None:
        features = build_phase5b_feature_dataset(phase5b_fixture(), symbols=("MNQ",))
        self.assertEqual(list(features.columns), PHASE5B_FEATURE_SCHEMA)
        self.assertEqual(len(features), 70)

    def test_phase5b_prior_and_opening_range_features_do_not_look_ahead(self) -> None:
        features = build_phase5b_feature_dataset(phase5b_fixture(), symbols=("MNQ",))
        second = features[features["trading_session"] == pd.Timestamp("2026-01-05").date()].reset_index(drop=True)
        self.assertEqual(float(second.loc[0, "prior_session_range"]), 36.0)
        self.assertEqual(float(second.loc[0, "prior_session_return"]), 34.5)
        self.assertEqual(float(second.loc[0, "overnight_range"]), 5.0)
        self.assertEqual(float(second.loc[0, "gap_from_prior_close"]), 65.5)
        self.assertTrue(pd.isna(second.loc[29, "or_width_30m"]))
        self.assertEqual(float(second.loc[30, "or_width_30m"]), 31.0)
        self.assertEqual(float(second.loc[0, "rth_cumulative_range"]), 2.0)
        self.assertEqual(float(second.loc[30, "rth_cumulative_range"]), 32.0)

    def test_phase5b_labels_remain_explicitly_separated(self) -> None:
        features = build_phase5b_feature_dataset(phase5b_fixture(), symbols=("MNQ",))
        label_columns = [column for column in features.columns if column.startswith("label_")]
        self.assertEqual(label_columns, ["label_forward_close_5m", "label_forward_return_5m"])
        self.assertNotIn("future_close", [c for c in features.columns if not c.startswith("label_")])


if __name__ == "__main__":
    unittest.main()
