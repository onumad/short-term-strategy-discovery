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

from short_term_edge.ml_backfill_e_phase10b_causality_audit import (  # noqa: E402
    build_eligibility_drift_summary,
    build_module_audit,
    build_recommendation,
    build_session_percentile_comparison,
    detect_unsafe_phase10b_specs,
)
from short_term_edge.phase10b_overnight_range_targeted_retest import build_phase10b_specs  # noqa: E402


class MlBackfillEPhase10BCausalityAuditTests(unittest.TestCase):
    def test_detects_exactly_six_default_unsafe_modules(self) -> None:
        policy, registry = _synthetic_policy_registry()
        unsafe = detect_unsafe_phase10b_specs(policy, registry, build_phase10b_specs())
        self.assertEqual(len(unsafe), 6)
        self.assertEqual({spec.range_filter for spec in unsafe}, {"exclude_narrowest_20", "exclude_widest_20"})

    def test_future_sessions_do_not_change_past_causal_percentiles(self) -> None:
        base = pd.DataFrame({"trading_session": [f"2025-01-{i:02d}" for i in range(1, 7)], "overnight_range_points": [1, 4, 2, 7, 3, 8]})
        first = build_session_percentile_comparison(base, minimum_prior_sessions=2)
        extended = pd.concat([base, pd.DataFrame({"trading_session": ["2025-01-07", "2025-01-08"], "overnight_range_points": [100, .5]})], ignore_index=True)
        second = build_session_percentile_comparison(extended, minimum_prior_sessions=2)
        np.testing.assert_allclose(
            first["causal_expanding_percentile"].to_numpy(),
            second.iloc[: len(first)]["causal_expanding_percentile"].to_numpy(),
            equal_nan=True,
        )
        self.assertFalse(np.allclose(first["full_sample_percentile"], second.iloc[: len(first)]["full_sample_percentile"]))

    def test_causal_warmup_is_unknown_not_false_or_zero(self) -> None:
        levels = pd.DataFrame({"trading_session": ["a", "b", "c"], "overnight_range_points": [1.0, 2.0, 3.0]})
        comparison = build_session_percentile_comparison(levels, minimum_prior_sessions=2)
        self.assertTrue(comparison.loc[:1, "causal_expanding_percentile"].isna().all())
        self.assertFalse(comparison.loc[:1, "causal_percentile_available"].any())

    def test_missing_target_d_coverage_is_not_treated_as_zero(self) -> None:
        spec = next(s for s in build_phase10b_specs() if s.range_filter != "all_ranges")
        target = pd.DataFrame({
            "phase": ["phase10b"], "candidate_id": [spec.candidate_id],
            "outcome_status": ["missing_source_day"], "reliable_outcome_coverage": [False],
        })
        audit = build_module_audit([spec], target)
        self.assertEqual(audit.loc[0, "target_d_backfill_status"], "unavailable_for_backfill")
        self.assertEqual(audit.loc[0, "target_d_missing_source_rows"], 1)
        self.assertFalse(bool(audit.loc[0, "missing_coverage_treated_as_zero"]))

    def test_drift_and_recommendation_are_deterministic_and_guarded(self) -> None:
        specs = [s for s in build_phase10b_specs() if s.range_filter != "all_ranges"][:2]
        comparison = build_session_percentile_comparison(
            pd.DataFrame({"trading_session": [str(i) for i in range(30)], "overnight_range_points": list(range(29, -1, -1))}),
            minimum_prior_sessions=5,
        )
        first = build_eligibility_drift_summary(specs, comparison)
        second = build_eligibility_drift_summary(specs, comparison)
        pd.testing.assert_frame_equal(first, second)
        audit = pd.DataFrame({"noncausal_definition_detected": [True] * len(specs)})
        rec = build_recommendation(audit, first)
        self.assertEqual(rec["next_action"], "module_registry_f_quarantine_noncausal_phase10b_modules")
        self.assertFalse(rec["registry_mutated"])
        self.assertFalse(rec["scheduler_policy_mutated"])
        self.assertFalse(rec["strategy_replayed"])
        self.assertFalse(rec["model_trained"])
        self.assertFalse(rec["official_gates_changed"])
        self.assertFalse(rec["paper_trading_approved"])
        self.assertFalse(rec["live_trading_approved"])

    def test_audit_source_does_not_replay_or_mutate(self) -> None:
        source = (PROJECT_ROOT / "src" / "short_term_edge" / "ml_backfill_e_phase10b_causality_audit.py").read_text(encoding="utf-8").lower()
        for token in ("run_phase10b_retest", "_simulate_trades", ".fit(", "git commit", "to_csv(config.module_registry_path"):
            self.assertNotIn(token, source)


def _synthetic_policy_registry() -> tuple[dict, pd.DataFrame]:
    specs = build_phase10b_specs()
    selected = [
        spec
        for spec in specs
        if spec.axis == "primary_short_midday_breakout"
        and spec.gap_filter == "all_gaps"
        and (
            (spec.range_filter == "exclude_narrowest_20" and spec.touch_filter == "all_touches")
            or spec.range_filter == "exclude_widest_20"
        )
    ]
    keys = [f"phase10b::{spec.candidate_id}" for spec in selected]
    policy = {"recommended_default_scheduler_universe": {"signal_keys": keys}}
    registry = pd.DataFrame(
        {
            "phase": ["phase10b"] * len(selected),
            "candidate_id": [spec.candidate_id for spec in selected],
        }
    )
    return policy, registry


if __name__ == "__main__":
    unittest.main()
