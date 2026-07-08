from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.instruments import get_instrument  # noqa: E402
from short_term_edge.phase_common import (  # noqa: E402
    add_cost_waterfall,
    concentration_diagnostics,
    daily_pnl_summary,
    deterministic_json,
    ensure_directory,
    fold_summary,
    grouped_trade_summary,
    positive_concentration,
    safe_divide,
    serialize_specs,
    standard_zero_metrics,
    write_csv_artifact,
    write_json_artifact,
)


@dataclass(frozen=True)
class DummySpec:
    candidate_id: str
    value: int

    def to_dict(self) -> dict[str, object]:
        return {"candidate_id": self.candidate_id, "value": self.value}


class PhaseCommonTests(unittest.TestCase):
    def _trades(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"candidate_id": "a", "trading_session": "2026-01-02", "gross_pnl": 10.0, "net_pnl": 6.0, "stress_pnl": 4.0, "mfe": 8.0, "mae": 2.0, "bucket": "x"},
                {"candidate_id": "a", "trading_session": "2026-01-02", "gross_pnl": -2.0, "net_pnl": -6.0, "stress_pnl": -8.0, "mfe": 1.0, "mae": 6.0, "bucket": "x"},
                {"candidate_id": "b", "trading_session": "2026-01-03", "gross_pnl": 5.0, "net_pnl": 1.0, "stress_pnl": -1.0, "mfe": 5.0, "mae": 3.0, "bucket": "y"},
            ]
        )

    def test_artifact_directory_csv_and_json_writers_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_directory(root / "nested")
            self.assertTrue((root / "nested").is_dir())

            csv_path = write_csv_artifact(self._trades().head(1), root / "out" / "trades.csv")
            self.assertTrue(csv_path.exists())
            self.assertIn("candidate_id", csv_path.read_text(encoding="utf-8"))

            payload = {"z": 1, "a": 2}
            json_path = write_json_artifact(payload, root / "out" / "payload.json")
            self.assertEqual(json_path.read_text(encoding="utf-8"), deterministic_json(payload))
            self.assertEqual(list(json.loads(json_path.read_text(encoding="utf-8")).keys()), ["a", "z"])

    def test_cost_waterfall_uses_existing_instrument_costs_without_mutating_by_default(self) -> None:
        trades = self._trades().head(1)
        updated = add_cost_waterfall(trades, instrument_symbol="MNQ")
        self.assertNotIn("fees_only_pnl", trades.columns)
        self.assertEqual(float(updated.iloc[0]["fees_only_pnl"]), 10.0 - get_instrument("MNQ").base_cost)
        self.assertEqual(float(updated.iloc[0]["normal_slippage_pnl"]), 6.0)

    def test_summary_helpers_match_phase_shapes(self) -> None:
        trades = self._trades()
        daily = daily_pnl_summary(trades)
        self.assertEqual(set(daily.columns), {"candidate_id", "trading_session", "trades", "net_pnl", "stress_pnl"})
        self.assertEqual(int(daily.loc[daily["candidate_id"].eq("a"), "trades"].iloc[0]), 2)

        conc = concentration_diagnostics(trades)
        self.assertEqual(conc.iloc[0]["trading_session"], "2026-01-03")

        grouped = grouped_trade_summary(trades, "bucket", include_gross=True)
        self.assertEqual(list(grouped.columns), ["group", "trades", "gross_pnl", "net_pnl", "stress_pnl", "avg_mfe", "avg_mae"])
        self.assertEqual(grouped.iloc[0]["group"], "y")

    def test_math_fold_zero_and_spec_serialization_helpers(self) -> None:
        self.assertEqual(safe_divide(1, 3), 0.333333)
        self.assertEqual(safe_divide(1, 0), 0.0)
        self.assertEqual(positive_concentration(10.0, 40.0), 0.25)
        self.assertEqual(positive_concentration(-10.0, 40.0), 0.0)
        self.assertEqual(positive_concentration(10.0, -1.0), 1.0)

        folds = pd.DataFrame([{"net_pnl": 10.0, "stress_pnl": 9.0}, {"net_pnl": -2.0, "stress_pnl": -3.0}])
        self.assertEqual(fold_summary(folds), {"walk_forward_test_pnl": 8.0, "walk_forward_stress_pnl": 6.0, "positive_wf_test_folds_pct": 0.5, "worst_wf_test_fold": -3.0})
        self.assertEqual(standard_zero_metrics(include_gross_waterfall=True)["fees_only_pnl"], 0.0)

        specs = [DummySpec("b", 2), DummySpec("a", 1)]
        self.assertEqual(json.loads(serialize_specs(specs))[0]["candidate_id"], "b")


if __name__ == "__main__":
    unittest.main()
