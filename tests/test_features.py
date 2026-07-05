from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.features import build_feature_frame


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


if __name__ == "__main__":
    unittest.main()
