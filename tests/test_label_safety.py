from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.label_safety import (  # noqa: E402
    is_legacy_promotion_like_label,
    label_implies_paper_trading_approval,
    normalize_tradability_status_from_label,
    validate_no_paper_trading_approval,
)


class LabelSafetyTests(unittest.TestCase):
    def test_missing_paper_trading_approved_defaults_false(self) -> None:
        guarded = validate_no_paper_trading_approval({"label": "research_signal"})

        self.assertFalse(guarded["paper_trading_approved"])
        self.assertFalse(guarded["label_implies_paper_trading_approval"])

    def test_paper_test_candidate_does_not_imply_approval(self) -> None:
        label = "paper_test_candidate"
        guarded = validate_no_paper_trading_approval({"label": label})

        self.assertTrue(is_legacy_promotion_like_label(label))
        self.assertFalse(label_implies_paper_trading_approval(label))
        self.assertFalse(guarded["paper_trading_approved"])
        self.assertEqual(
            guarded["tradability_status_from_label"],
            "legacy_research_label_no_paper_approval",
        )

    def test_candidate_for_paper_review_does_not_imply_approval(self) -> None:
        label = "candidate_for_paper_review"
        guarded = validate_no_paper_trading_approval({"label": label})

        self.assertFalse(label_implies_paper_trading_approval(label))
        self.assertFalse(guarded["paper_trading_approved"])
        self.assertEqual(
            guarded["tradability_status_from_label"],
            "review_packet_candidate_no_paper_approval",
        )

    def test_watchlist_needs_more_history_does_not_imply_approval(self) -> None:
        label = "watchlist_needs_more_history"
        guarded = validate_no_paper_trading_approval({"label": label})

        self.assertFalse(label_implies_paper_trading_approval(label))
        self.assertFalse(guarded["paper_trading_approved"])
        self.assertEqual(
            guarded["tradability_status_from_label"],
            "research_watchlist_needs_more_history",
        )

    def test_explicit_paper_trading_approved_false_is_normalized_false(self) -> None:
        guarded = validate_no_paper_trading_approval(
            {"label": "candidate_for_paper_review", "paper_trading_approved": "false"}
        )

        self.assertFalse(guarded["paper_trading_approved"])

    def test_explicit_true_paper_trading_approved_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "paper_trading_approved"):
            validate_no_paper_trading_approval(
                {"label": "approved_promotion_candidate", "paper_trading_approved": True}
            )

    def test_official_gates_changed_true_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "official_gates_changed"):
            validate_no_paper_trading_approval(
                {"label": "approved_promotion_candidate", "official_gates_changed": True}
            )

    def test_official_gates_passed_true_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "official_gates_passed"):
            validate_no_paper_trading_approval(
                {"label": "approved_promotion_candidate", "official_gates_passed": True}
            )

    def test_false_gates_are_preserved_false(self) -> None:
        guarded = validate_no_paper_trading_approval(
            {"label": "review_candidate", "official_gates_changed": False}
        )

        self.assertFalse(guarded["official_gates_changed"])
        self.assertFalse(guarded["official_gates_passed"])
        self.assertFalse(guarded["paper_trading_approved"])

    def test_unknown_labels_do_not_imply_approval(self) -> None:
        label = "unclassified_research_signal"
        guarded = validate_no_paper_trading_approval({"label": label})

        self.assertFalse(is_legacy_promotion_like_label(label))
        self.assertFalse(label_implies_paper_trading_approval(label))
        self.assertFalse(guarded["paper_trading_approved"])
        self.assertEqual(
            normalize_tradability_status_from_label(label),
            "research_only_unknown_label",
        )


if __name__ == "__main__":
    unittest.main()
