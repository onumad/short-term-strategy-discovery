from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase10b_causal_v2_validation import (  # noqa: E402
    DEFINITION_VERSION,
    attach_causal_percentiles,
    build_causal_v2_specs,
    make_recommendation,
)
from short_term_edge.phase10b_overnight_range_targeted_retest import build_phase10b_specs  # noqa: E402


class Phase10BCausalV2ValidationTests(unittest.TestCase):
    def test_new_ids_preserve_historical_id_and_definition(self) -> None:
        old = next(spec for spec in build_phase10b_specs() if spec.range_filter == "exclude_widest_20")
        new = build_causal_v2_specs([old.candidate_id], 20)[0]
        self.assertNotEqual(new.candidate_id, old.candidate_id)
        self.assertTrue(new.candidate_id.endswith("_causalv2_prior20"))
        self.assertEqual(new.historical_candidate_id, old.candidate_id)
        self.assertEqual(new.to_dict()["definition_version"], DEFINITION_VERSION)

    def test_causal_attachment_uses_only_causal_column(self) -> None:
        trades = pd.DataFrame(
            {"trading_session": ["a", "b"], "overnight_range_percentile": [0.99, 0.01], "value": [1, 2]}
        )
        levels = pd.DataFrame(
            {
                "trading_session": ["a", "b"],
                "causal_expanding_percentile": [np.nan, 0.75],
                "prior_session_count": [0, 20],
                "causal_percentile_available": [False, True],
            }
        )
        out = attach_causal_percentiles(trades, levels)
        self.assertTrue(pd.isna(out.loc[0, "overnight_range_percentile"]))
        self.assertEqual(out.loc[1, "overnight_range_percentile"], 0.75)
        self.assertEqual(out["historical_full_sample_percentile_not_used"].tolist(), [0.99, 0.01])

    def test_future_values_cannot_change_attached_historical_percentiles(self) -> None:
        from short_term_edge.ml_backfill_e_phase10b_causality_audit import build_session_percentile_comparison

        base = pd.DataFrame({"trading_session": list("abcdef"), "overnight_range_points": [1, 4, 2, 7, 3, 8]})
        extended = pd.concat(
            [base, pd.DataFrame({"trading_session": ["g", "h"], "overnight_range_points": [100, 0.5]})],
            ignore_index=True,
        )
        first = build_session_percentile_comparison(base, 2)
        second = build_session_percentile_comparison(extended, 2)
        np.testing.assert_allclose(
            first["causal_expanding_percentile"], second.iloc[: len(first)]["causal_expanding_percentile"], equal_nan=True
        )

    def test_all_ranges_is_not_migrated(self) -> None:
        old = next(spec for spec in build_phase10b_specs() if spec.range_filter == "all_ranges")
        with self.assertRaisesRegex(ValueError, "only for quarantined"):
            build_causal_v2_specs([old.candidate_id], 20)

    def test_nonpassing_positive_signal_does_not_resume_registry_or_backfill(self) -> None:
        candidates = pd.DataFrame(
            [
                {
                    "phase10b_causal_v2_label": "phase10b_causal_v2_rejected_concentration",
                    "stress_pnl": 1.0,
                    "validation_pnl": 1.0,
                    "holdout_pnl": 1.0,
                    "walk_forward_stress_pnl": 1.0,
                    "candidate_id": "x",
                }
            ]
        )
        rec = make_recommendation({"candidate_results": candidates})
        self.assertEqual(rec["next_action"], "park_causal_v2_as_nontradable_research_signal")
        self.assertFalse(rec["registry_mutated"])
        self.assertFalse(rec["scheduler_policy_mutated"])
        self.assertFalse(rec["model_trained"])


if __name__ == "__main__":
    unittest.main()
