from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ai_search import SearchConfig, propose_strategy_specs, run_bounded_search


class AISearchTests(unittest.TestCase):
    def test_proposals_are_deterministic_and_bounded(self) -> None:
        config = SearchConfig(symbols=("MNQ", "MGC"), max_candidates=5)
        first = [spec.to_json() for spec in propose_strategy_specs(config)]
        second = [spec.to_json() for spec in propose_strategy_specs(config)]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)
        self.assertTrue(first[0].find("MNQ") >= 0)

    def test_search_requires_existing_project_data(self) -> None:
        config = SearchConfig(symbols=("MNQ",), max_candidates=2, recent_sessions=2)
        with self.assertRaises(FileNotFoundError):
            run_bounded_search(Path("C:/definitely/not/a/real/project"), config)

    def test_unsupported_symbol_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            list(propose_strategy_specs(SearchConfig(symbols=("ES",), max_candidates=1)))


if __name__ == "__main__":
    unittest.main()
