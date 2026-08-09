#!/usr/bin/env python3
"""Validate MiMo TTS narration segments before synthesis."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from segment_validation import load_segments_from_data, summarize_issues, validate_segments


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate segments.json for MiMo-V2.5-TTS batch synthesis")
    parser.add_argument("--segments", required=True, help="segments JSON path")
    parser.add_argument("--min-chars", type=int, default=20)
    parser.add_argument("--max-chars", type=int, default=1000)
    parser.add_argument("--fail-on-warning", action="store_true")
    parser.add_argument("--report", help="Optional JSON validation report output path")
    args = parser.parse_args()

    path = Path(args.segments)
    if not path.exists():
        print(f"[ERROR] segments file not found: {path}", file=sys.stderr)
        return 1
    with path.open("r", encoding="utf-8") as f:
        data: Any = json.load(f)
    segments = load_segments_from_data(data)
    issues = validate_segments(segments, min_chars=args.min_chars, max_chars=args.max_chars)
    summary = summarize_issues(issues)

    print(f"[VALIDATE] total={summary['total']} errors={summary['errors']} warnings={summary['warnings']}")
    for issue in issues:
        idx = "-" if issue.index is None else f"{issue.index:02d}"
        print(f"[{issue.level.upper()}] segment={idx} field={issue.field}: {issue.message}")

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with Path(args.report).open("w", encoding="utf-8") as f:
            json.dump({"summary": summary, "issues": [i.to_dict() for i in issues]}, f, ensure_ascii=False, indent=2)
        print(f"[DONE] report: {args.report}")

    if summary["errors"] > 0:
        return 1
    if args.fail_on_warning and summary["warnings"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
