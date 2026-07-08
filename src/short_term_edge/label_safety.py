"""Research-only label safety helpers.

This module prevents legacy candidate/watchlist/paper-like labels from being
read as paper-trading approval. It is a guard/helper layer only: it does not
rewrite historical labels, change official gates, promote candidates, or approve
paper trading.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROMOTION_LIKE_TOKENS = (
    "paper",
    "paper_test",
    "watchlist",
    "candidate",
    "review",
    "approved",
    "approval",
    "promotion",
    "promote",
    "paper_review",
    "paper_trading",
)

RESEARCH_ONLY_TRADABILITY_STATUSES = {
    "candidate_for_paper_review": "review_packet_candidate_no_paper_approval",
    "paper_test_candidate": "legacy_research_label_no_paper_approval",
    "watchlist_needs_more_history": "research_watchlist_needs_more_history",
}


def _label_text(label: str | None) -> str:
    return str(label or "").strip().lower()


def is_legacy_promotion_like_label(label: str) -> bool:
    """Return true for labels that need an explicit no-paper-approval guard."""

    text = _label_text(label)
    return any(token in text for token in PROMOTION_LIKE_TOKENS)


def label_implies_paper_trading_approval(label: str) -> bool:
    """Labels never imply paper-trading approval in this project."""

    _ = label
    return False


def normalize_tradability_status_from_label(label: str) -> str:
    """Map legacy/review/watchlist labels to research-only status language."""

    text = _label_text(label)
    if not text:
        return "research_only_unknown_label"
    for token, status in RESEARCH_ONLY_TRADABILITY_STATUSES.items():
        if token in text:
            return status
    if "paper" in text or "approved" in text or "approval" in text:
        return "research_only_no_paper_approval"
    if "watchlist" in text:
        return "research_watchlist_no_paper_approval"
    if "review" in text or "candidate" in text or "promotion" in text or "promote" in text:
        return "research_review_language_no_paper_approval"
    return "research_only_unknown_label"


def _false_like(value: Any) -> bool:
    if value is False or value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "0", "false", "no", "n", "none", "null"}
    if isinstance(value, (int, float)):
        return value == 0
    return False


def validate_no_paper_trading_approval(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a guarded copy of a record with paper approval fail-closed.

    Missing ``paper_trading_approved`` defaults to ``False``. Explicit false-like
    values are preserved as false. Explicit true-like values raise, because this
    project's current outputs must not approve paper trading.
    """

    guarded = dict(record)
    label = str(guarded.get("label", guarded.get("phase_label", "")))
    explicit_value = guarded.get("paper_trading_approved", False)
    if not _false_like(explicit_value):
        raise ValueError("paper_trading_approved must remain false for current project outputs")
    for gate_key in ("official_gates_changed", "official_gates_passed"):
        if gate_key in guarded and not _false_like(guarded[gate_key]):
            raise ValueError(f"{gate_key} must remain false for current project outputs")

    guarded["paper_trading_approved"] = False
    guarded["label_implies_paper_trading_approval"] = label_implies_paper_trading_approval(label)
    guarded["legacy_promotion_like_label"] = is_legacy_promotion_like_label(label)
    guarded["tradability_status_from_label"] = normalize_tradability_status_from_label(label)
    guarded.setdefault("official_gates_changed", False)
    guarded.setdefault("official_gates_passed", False)
    return guarded
