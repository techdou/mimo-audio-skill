#!/usr/bin/env python3
"""Generate SRT or WebVTT subtitles from TTS manifest, segments, or ASR transcripts.

This is designed for voiceover timelines: one caption block per generated audio
segment. It does not perform word-level alignment.
"""
from __future__ import annotations

import argparse
import json
import re
import wave
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mimo_logger import setup_logger


def read_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_segments_text(path: Optional[str]) -> Dict[int, str]:
    data = read_json(path)
    raw = data.get("segments", data if isinstance(data, list) else [])
    mapping: Dict[int, str] = {}
    if isinstance(raw, list):
        for fallback, seg in enumerate(raw, start=1):
            if isinstance(seg, dict):
                try:
                    idx = int(seg.get("index") or fallback)
                except (TypeError, ValueError):
                    idx = fallback
                mapping[idx] = str(seg.get("speech_text") or seg.get("content") or "").strip()
    return mapping


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        return wf.getnframes() / float(rate) if rate else 0.0


def fmt_time(seconds: float, *, vtt: bool = False) -> str:
    seconds = max(0.0, seconds)
    ms = int(round((seconds - int(seconds)) * 1000))
    whole = int(seconds)
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    sep = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def clean_caption(text: str, max_line_chars: int = 36) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return "（无字幕文本）"
    # Keep punctuation but insert line breaks for readability.
    lines: List[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= max_line_chars and char in "，。！？；,.!?; ":
            lines.append(current.strip())
            current = ""
    if current.strip():
        lines.append(current.strip())
    return "\n".join(lines) if lines else text


def transcript_text_for_index(asr_manifest: Dict[str, Any], index: int, fallback_audio_stem: str) -> str:
    for item in asr_manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        transcript_path = item.get("transcript_path")
        audio_path = item.get("audio_path")
        if not transcript_path:
            continue
        stem = Path(str(audio_path or transcript_path)).stem
        if stem == fallback_audio_stem or stem.startswith(f"{index:02d}_"):
            p = Path(str(transcript_path))
            if p.exists():
                return p.read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def build_cues(tts_manifest: Dict[str, Any], segments_text: Dict[int, str], asr_manifest: Dict[str, Any], gap_seconds: float) -> List[Tuple[int, float, float, str, str]]:
    cues: List[Tuple[int, float, float, str, str]] = []
    current = 0.0
    segments = [s for s in tts_manifest.get("segments", []) if isinstance(s, dict)]
    segments.sort(key=lambda s: int(s.get("index") or 0))
    for fallback, seg in enumerate(segments, start=1):
        idx = int(seg.get("index") or fallback)
        audio_path = Path(str(seg.get("audio_path") or ""))
        title = str(seg.get("title") or f"Segment {idx}")
        dur = seg.get("duration_seconds")
        if dur is None and audio_path.exists():
            try:
                dur = wav_duration(audio_path)
            except Exception:
                dur = 3.0
        dur = float(dur or 3.0)
        text = str(seg.get("speech_text") or "").strip()
        if not text:
            text = segments_text.get(idx, "")
        if asr_manifest:
            asr_text = transcript_text_for_index(asr_manifest, idx, audio_path.stem)
            if asr_text:
                text = asr_text
        start = current
        end = current + dur
        cues.append((idx, start, end, title, clean_caption(text)))
        current = end + gap_seconds
    return cues


def write_srt(cues: List[Tuple[int, float, float, str, str]], path: Path) -> None:
    lines: List[str] = []
    for number, (_, start, end, _title, text) in enumerate(cues, start=1):
        lines.extend([str(number), f"{fmt_time(start)} --> {fmt_time(end)}", text, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_vtt(cues: List[Tuple[int, float, float, str, str]], path: Path) -> None:
    lines: List[str] = ["WEBVTT", ""]
    for _, start, end, title, text in cues:
        lines.extend([title, f"{fmt_time(start, vtt=True)} --> {fmt_time(end, vtt=True)}", text, ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SRT/WebVTT from MiMo audio manifest")
    parser.add_argument("--manifest", required=True, help="TTS audio manifest")
    parser.add_argument("--segments", help="Original segments JSON for speech_text fallback")
    parser.add_argument("--asr-manifest", help="Optional ASR manifest; transcripts override original text")
    parser.add_argument("--srt", help="SRT output path")
    parser.add_argument("--vtt", help="WebVTT output path")
    parser.add_argument("--gap-seconds", type=float, default=0.35, help="Assumed gap between merged segments")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logger = setup_logger("generate_srt", verbose=args.verbose)
    if not args.srt and not args.vtt:
        logger.error("Provide --srt and/or --vtt")
        return 1
    tts_manifest = read_json(args.manifest)
    seg_text = load_segments_text(args.segments)
    asr_manifest = read_json(args.asr_manifest)
    cues = build_cues(tts_manifest, seg_text, asr_manifest, args.gap_seconds)
    if not cues:
        logger.error("No cues generated. Check manifest segments[].audio_path.")
        return 1
    if args.srt:
        write_srt(cues, Path(args.srt))
        logger.info(f"SRT written: {args.srt}")
    if args.vtt:
        write_vtt(cues, Path(args.vtt))
        logger.info(f"VTT written: {args.vtt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
