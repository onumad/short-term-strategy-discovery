from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.audit import AuditConfig, audit_project, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local Databento OHLCV CSV files.")
    parser.add_argument("--raw-dir", default=PROJECT_ROOT / "data" / "raw", type=Path)
    parser.add_argument("--output", default=PROJECT_ROOT / "data_audit.md", type=Path)
    parser.add_argument("--no-write", action="store_true", help="Print audit without writing markdown.")
    args = parser.parse_args()

    report = audit_project(AuditConfig(raw_dir=args.raw_dir))
    markdown = render_markdown(report)

    if args.no_write:
        print(markdown)
    else:
        args.output.write_text(markdown, encoding="utf-8")
        print(f"Wrote {args.output}")
        print(
            "Latest shared complete session: "
            f"{report['shared_complete_sessions'][-1] if report['shared_complete_sessions'] else 'n/a'}"
        )
        recent = report["recent_window"]
        if recent:
            print(f"Recent research window: {recent[0]} through {recent[-1]} ({len(recent)} sessions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
