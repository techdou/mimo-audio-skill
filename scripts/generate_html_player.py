#!/usr/bin/env python3
"""Generate a lightweight HTML audio review page from a MiMo TTS manifest."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from mimo_logger import setup_logger


def load_segments_text(path: Optional[str]) -> Dict[int, str]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    raw = data.get("segments", data if isinstance(data, list) else [])
    mapping: Dict[int, str] = {}
    if isinstance(raw, list):
        for fallback, seg in enumerate(raw, start=1):
            if isinstance(seg, dict):
                mapping[int(seg.get("index") or fallback)] = str(seg.get("speech_text") or seg.get("content") or "")
    return mapping


def relpath(path: str, base_file: Path) -> str:
    try:
        return os.path.relpath(path, start=str(base_file.parent)).replace(os.sep, "/")
    except Exception:
        return path.replace(os.sep, "/")


def render(manifest: Dict[str, Any], output: Path, *, title: str, segments_text: Dict[int, str], vtt_path: Optional[str] = None, srt_path: Optional[str] = None) -> str:
    segments = [s for s in manifest.get("segments", []) if isinstance(s, dict)]
    segments.sort(key=lambda s: int(s.get("index") or 0))
    total_duration = manifest.get("duration_summary", {}).get("total_duration_seconds")
    cards: List[str] = []
    for fallback, seg in enumerate(segments, start=1):
        idx = int(seg.get("index") or fallback)
        title_text = html.escape(str(seg.get("title") or f"Segment {idx}"))
        audio_path = str(seg.get("audio_path") or "")
        src = html.escape(relpath(audio_path, output)) if audio_path else ""
        status = html.escape(str(seg.get("status") or "unknown"))
        duration = seg.get("duration_seconds")
        text = str(seg.get("speech_text") or segments_text.get(idx, "")).strip()
        text_html = html.escape(text)
        filename = html.escape(str(seg.get("filename") or Path(audio_path).name))
        model = html.escape(str(seg.get("model") or ""))
        voice = html.escape(str(seg.get("voice") or ""))
        track_html = ""
        if vtt_path:
            track_html = f'<track kind="subtitles" srclang="zh" label="字幕" src="{html.escape(relpath(vtt_path, output))}">' 
        audio_html = f'<audio controls preload="metadata" src="{src}">{track_html}</audio>' if src else "<p class='muted'>无音频路径</p>"
        cards.append(f"""
        <section class="card">
          <div class="card-head">
            <div><span class="idx">{idx:02d}</span><h2>{title_text}</h2></div>
            <span class="status status-{status}">{status}</span>
          </div>
          {audio_html}
          <div class="meta"><span>{filename}</span><span>{model}</span><span>{voice}</span><span>{duration or '-'}s</span></div>
          <details><summary>查看播报文本</summary><p>{text_html}</p></details>
        </section>
        """)
    subtitle_links = []
    if srt_path:
        subtitle_links.append(f'<a href="{html.escape(relpath(srt_path, output))}">下载 SRT</a>')
    if vtt_path:
        subtitle_links.append(f'<a href="{html.escape(relpath(vtt_path, output))}">下载 VTT</a>')
    subtitle_html = " · ".join(subtitle_links)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#faf9f6; --card:#fff; --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb; --accent:#2563eb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding:40px 20px 72px; }}
.hero {{ margin-bottom:28px; padding:28px; border:1px solid var(--line); background:linear-gradient(180deg,#fff,#fbfbfa); border-radius:22px; }}
h1 {{ margin:0 0 10px; font-size:30px; }}
.summary {{ color:var(--muted); display:flex; gap:16px; flex-wrap:wrap; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:20px; margin:16px 0; box-shadow:0 6px 24px rgba(15,23,42,.04); }}
.card-head {{ display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:12px; }}
.card-head > div {{ display:flex; align-items:center; gap:12px; }}
h2 {{ margin:0; font-size:20px; }}
.idx {{ display:inline-flex; align-items:center; justify-content:center; min-width:42px; height:32px; border-radius:999px; background:#eef2ff; color:#3730a3; font-weight:700; }}
audio {{ width:100%; margin:8px 0 10px; }}
.meta {{ display:flex; flex-wrap:wrap; gap:8px; color:var(--muted); font-size:13px; }}
.meta span {{ border:1px solid var(--line); border-radius:999px; padding:2px 8px; }}
.status {{ font-size:12px; border-radius:999px; padding:3px 10px; background:#f3f4f6; color:#374151; }}
.status-success {{ background:#ecfdf5; color:#047857; }}
.status-failed {{ background:#fef2f2; color:#b91c1c; }}
.status-dry_run {{ background:#eff6ff; color:#1d4ed8; }}
details {{ margin-top:10px; }}
details p {{ white-space:pre-wrap; color:#374151; }}
.muted {{ color:var(--muted); }}
.links a {{ color:var(--accent); }}
</style>
</head>
<body><main>
  <section class="hero">
    <h1>{html.escape(title)}</h1>
    <div class="summary"><span>片段：{len(segments)}</span><span>总时长：{total_duration or '-'} 秒</span><span class="links">{subtitle_html}</span></div>
  </section>
  {''.join(cards)}
</main></body></html>
"""


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate HTML player page from TTS manifest")
    parser.add_argument("--manifest", required=True, help="TTS audio manifest")
    parser.add_argument("--segments", help="Original segments JSON for speech text fallback")
    parser.add_argument("--output", default="output/player.html", help="HTML output path")
    parser.add_argument("--title", default="MiMo 讲义音频播放页")
    parser.add_argument("--srt", help="Optional SRT link")
    parser.add_argument("--vtt", help="Optional VTT link and audio track")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logger = setup_logger("html_player", verbose=args.verbose)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    html_text = render(manifest, output, title=args.title, segments_text=load_segments_text(args.segments), srt_path=args.srt, vtt_path=args.vtt)
    output.write_text(html_text, encoding="utf-8")
    logger.info(f"HTML player written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
