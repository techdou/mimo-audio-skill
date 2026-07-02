#!/usr/bin/env python3
"""Inject a compact audio list into an existing HTML lecture page.

This script does not redesign the original lecture HTML. It appends a small
review/player block before </body>; if </body> is absent, it appends to the end.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from mimo_logger import setup_logger


def relpath(path: str, base_file: Path) -> str:
    try:
        return os.path.relpath(path, start=str(base_file.parent)).replace(os.sep, "/")
    except Exception:
        return path.replace(os.sep, "/")


def build_block(manifest: Dict[str, Any], output: Path, title: str) -> str:
    segments = [s for s in manifest.get("segments", []) if isinstance(s, dict)]
    segments.sort(key=lambda s: int(s.get("index") or 0))
    items: List[str] = []
    for fallback, seg in enumerate(segments, start=1):
        idx = int(seg.get("index") or fallback)
        name = html.escape(str(seg.get("title") or f"音频片段 {idx}"))
        audio_path = str(seg.get("audio_path") or "")
        src = html.escape(relpath(audio_path, output))
        items.append(f"""
        <div class="mimo-audio-item">
          <div class="mimo-audio-title"><strong>{idx:02d}</strong> {name}</div>
          <audio controls preload="metadata" src="{src}"></audio>
        </div>""")
    return f"""
<!-- MiMo Lecture Audio Skill injected block start -->
<section id="mimo-lecture-audio" class="mimo-audio-panel">
  <style>
    .mimo-audio-panel {{ max-width: 980px; margin: 32px auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 18px; background: #fff; color: #1f2937; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; }}
    .mimo-audio-panel h2 {{ margin: 0 0 14px; font-size: 22px; }}
    .mimo-audio-item {{ border-top: 1px solid #f1f5f9; padding: 14px 0; }}
    .mimo-audio-title {{ margin-bottom: 8px; color: #374151; }}
    .mimo-audio-item audio {{ width: 100%; }}
  </style>
  <h2>{html.escape(title)}</h2>
  {''.join(items)}
</section>
<!-- MiMo Lecture Audio Skill injected block end -->
"""


def inject_html(input_html: Path, manifest_path: Path, output: Path, title: str) -> None:
    original = input_html.read_text(encoding="utf-8", errors="replace")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    block = build_block(manifest, output, title)
    marker = "</body>"
    lower = original.lower()
    pos = lower.rfind(marker)
    if pos >= 0:
        result = original[:pos] + block + original[pos:]
    else:
        result = original + "\n" + block
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result, encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inject MiMo audio controls into an existing HTML file")
    parser.add_argument("--html", required=True, help="Existing lecture HTML file")
    parser.add_argument("--manifest", required=True, help="TTS manifest with audio paths")
    parser.add_argument("--output", required=True, help="Output HTML file")
    parser.add_argument("--title", default="讲义配套音频")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logger = setup_logger("inject_html", verbose=args.verbose)
    try:
        inject_html(Path(args.html), Path(args.manifest), Path(args.output), args.title)
        logger.info(f"Injected HTML written: {args.output}")
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error(f"HTML injection failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
