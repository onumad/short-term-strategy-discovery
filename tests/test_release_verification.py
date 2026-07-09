from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import content_sha256  # noqa: E402
from short_term_edge.release_verification import verify_frozen_model_bundle, verify_research_manifest  # noqa: E402


class ReleaseVerificationTests(unittest.TestCase):
    def test_manifest_rehashes_artifacts_and_enforces_research_flags(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-verification-") as tmp:
            root = Path(tmp)
            artifact = root / "artifacts" / "unit" / "results.csv"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("value\n1\n", encoding="utf-8")
            manifest_path = artifact.parent / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest(root, artifact)), encoding="utf-8")

            result = verify_research_manifest(manifest_path, root, require_clean_provenance=True)

            self.assertTrue(result.passed, result.errors)
            self.assertGreater(result.checks, 10)

    def test_manifest_detects_hash_tampering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-verification-") as tmp:
            root = Path(tmp)
            artifact = root / "artifacts" / "unit" / "results.csv"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("value\n1\n", encoding="utf-8")
            manifest_path = artifact.parent / "manifest.json"
            manifest_path.write_text(json.dumps(_manifest(root, artifact)), encoding="utf-8")
            artifact.write_text("value\n2\n", encoding="utf-8")

            result = verify_research_manifest(manifest_path, root)

            self.assertFalse(result.passed)
            self.assertTrue(any("hash mismatch" in error for error in result.errors))

    def test_manifest_rejects_path_escape_and_approval(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-verification-") as tmp:
            root = Path(tmp)
            artifact = root / "results.csv"
            artifact.write_text("value\n1\n", encoding="utf-8")
            manifest = _manifest(root, artifact)
            manifest["approval_state"]["paper_trading_approved"] = True
            manifest["output_artifacts"]["results"]["path"] = "../outside.csv"
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = verify_research_manifest(manifest_path, root)

            self.assertFalse(result.passed)
            self.assertTrue(any("paper_trading_approved" in error for error in result.errors))
            self.assertTrue(any("escapes project root" in error for error in result.errors))

    def test_frozen_model_bundle_fails_closed_on_bad_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="release-verification-") as tmp:
            bundle_path = Path(tmp) / "bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "schema_version": "ml_baseline_b_model_bundle/v1",
                        "authorization_stage": "research",
                        "approved_as_signal_input": False,
                        "paper_trading_approved": False,
                        "live_trading_approved": False,
                        "confirmatory_evidence": False,
                        "model_count": 1,
                        "models": [{"model_type": "unsupported"}],
                    }
                ),
                encoding="utf-8",
            )

            result = verify_frozen_model_bundle(bundle_path)

            self.assertFalse(result.passed)
            self.assertTrue(any("cannot be deserialized" in error for error in result.errors))


def _manifest(root: Path, artifact: Path) -> dict[str, object]:
    record = {
        "path": artifact.relative_to(root).as_posix(),
        "exists": True,
        "size_bytes": artifact.stat().st_size,
        "sha256": content_sha256(artifact),
    }
    return {
        "schema_version": "research_run_manifest/v2",
        "authorization_stage": "research",
        "approval_state": {
            "approved_as_signal_input": False,
            "paper_trading_approved": False,
            "shadow_execution_approved": False,
            "live_trading_approved": False,
        },
        "provenance": {
            "source_revision": "a" * 40,
            "dirty_worktree": False,
            "content_hash_algorithm": "sha256",
        },
        "input_artifacts": [],
        "output_artifacts": {"results": record},
        "legacy_output_artifacts": {},
        "schema_versions": {},
    }


if __name__ == "__main__":
    unittest.main()
