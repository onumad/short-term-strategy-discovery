from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("phase8a_runner", PROJECT_ROOT / "scripts" / "run_phase8a_mgc_clean_family_search.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load Phase 8A runner module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Phase8ARunnerTests(unittest.TestCase):
    def test_phase8a_repro_command_includes_max_new_specs_and_optional_run_id(self) -> None:
        runner = _load_runner_module()

        with_run_id = runner._phase8a_repro_command(max_new_specs=0, run_id="phase8a-r1-smoke")
        without_run_id = runner._phase8a_repro_command(max_new_specs=1, run_id=None)

        self.assertEqual(
            with_run_id,
            "EXPERIMENT_RUN_ID=phase8a-r1-smoke PHASE8A_MAX_NEW_SPECS=0 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py",
        )
        self.assertEqual(
            without_run_id,
            "PHASE8A_MAX_NEW_SPECS=1 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py",
        )


if __name__ == "__main__":
    unittest.main()
