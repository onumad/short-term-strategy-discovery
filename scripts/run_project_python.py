"""Run a command with the repository virtual environment's Python."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    candidates = (root / ".venv" / "Scripts" / "python.exe", root / ".venv" / "bin" / "python")
    python = next((candidate for candidate in candidates if candidate.is_file()), None)
    if python is None:
        print("Project virtual environment not found under .venv", file=sys.stderr)
        return 2
    if len(sys.argv) == 1:
        print("No Python arguments supplied", file=sys.stderr)
        return 2
    return subprocess.run([str(python), *sys.argv[1:]], cwd=root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
