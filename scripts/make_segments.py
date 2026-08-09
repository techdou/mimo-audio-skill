#!/usr/bin/env python3
"""Create rough MiMo TTS segment JSON from cleaned narration text.

This is a helper, not a replacement for agent-based narration rewriting.
It preserves text as much as possible and splits by headings/paragraphs.
Works for lecture notes, novel excerpts, podcast scripts, marketing copy —
any text that should become spoken audio.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List, Optional

DEFAULT_STYLE = (
    "用温柔、清晰、适合课程讲解的语气朗读，语速中等偏慢，声音自然亲切。"
    "遇到重要概念时适当停顿，遇到步骤、定义、对比和案例时保持清楚的节奏感。"
)
DEFAULT_TITLE_PREFIX = "内容片段"

SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


def slugify(text: str, fallback: str) -> str:
    # Conservative pinyin-free slug: keep ascii, otherwise fallback.
    ascii_text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return ascii_text[:50] if ascii_text else fallback


def split_sentences(paragraph: str) -> List[str]:
    pieces = [p.strip() for p in SENTENCE_SPLIT_RE.split(paragraph) if p.strip()]
    return pieces or [paragraph.strip()]


def make_chunks(text: str, max_chars: int) -> List[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append("\n".join(current).strip())
            current = []
            current_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            flush()
            buf: List[str] = []
            buf_len = 0
            for sentence in split_sentences(paragraph):
                if buf and buf_len + len(sentence) > max_chars:
                    chunks.append("".join(buf).strip())
                    buf = []
                    buf_len = 0
                buf.append(sentence)
                buf_len += len(sentence)
            if buf:
                chunks.append("".join(buf).strip())
            continue

        if current and current_len + len(paragraph) > max_chars:
            flush()
        current.append(paragraph)
        current_len += len(paragraph)

    flush()
    return chunks


def infer_title(chunk: str, index: int, title_prefix: str) -> str:
    first_line = chunk.splitlines()[0].strip()
    first_line = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", first_line)
    first_line = re.sub(r"^\d+[.)、]\s*", "", first_line)
    if len(first_line) <= 24 and not first_line.endswith(("。", "！", "？")):
        return first_line
    return f"{title_prefix}{index:02d}"


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Make rough MiMo TTS segments from cleaned narration text")
    parser.add_argument("--input", required=True, help="Input cleaned text file")
    parser.add_argument("--output", required=True, help="Output segments JSON")
    parser.add_argument("--title-prefix", default=DEFAULT_TITLE_PREFIX, help="Fallback title prefix")
    parser.add_argument("--max-chars", type=int, default=650, help="Approximate max Chinese characters per segment")
    parser.add_argument("--style", default=None, help="Style instruction for all segments (overrides profile)")
    parser.add_argument("--model", help="Default model (profile wins over CLI when both absent)")
    parser.add_argument("--voice", help="Default preset voice")
    parser.add_argument("--voice-sample-path", help="Voice sample path for voiceclone")
    parser.add_argument("--voice-design-prompt", help="Voice design prompt for voicedesign")
    parser.add_argument("--profile", help="Voice/style profile name (personal or built-in)")
    parser.add_argument("--profile-file", help="Voice/style profile JSON file path")
    parser.add_argument("--format", default="wav", help="Default audio format")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    text = input_path.read_text(encoding="utf-8", errors="replace")
    chunks = make_chunks(text, max_chars=args.max_chars)

    profile: Optional[dict] = None
    if args.profile or args.profile_file:
        from voice_profiles import find_profile
        profile = find_profile(args.profile, args.profile_file)

    default_model = args.model or (profile or {}).get("model") or "mimo-v2.5-tts"
    default_voice = args.voice or (profile or {}).get("voice") or "冰糖"
    default_style = args.style or (profile or {}).get("style_instruction") or DEFAULT_STYLE
    default_voice_sample = args.voice_sample_path or (profile or {}).get("voice_sample_path") or ""
    default_voice_design = args.voice_design_prompt or (profile or {}).get("voice_design_prompt") or ""

    segments = []
    for i, chunk in enumerate(chunks, start=1):
        title = infer_title(chunk, i, args.title_prefix)
        slug = slugify(title, f"segment_{i:02d}")
        segment = {
            "index": i,
            "title": title,
            "filename": f"{i:02d}_{slug}.{args.format}",
            "model": default_model,
            "format": args.format,
            "style_instruction": default_style,
            "speech_text": chunk,
        }
        if default_model == "mimo-v2.5-tts-voiceclone":
            if default_voice_sample:
                segment["voice_sample_path"] = default_voice_sample
        elif default_model == "mimo-v2.5-tts-voicedesign":
            if default_voice_design:
                segment["voice_design_prompt"] = default_voice_design
        else:
            segment["voice"] = default_voice
        segments.append(segment)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)

    print(f"Segments written: {output_path}")
    print(f"Segment count: {len(segments)}")


if __name__ == "__main__":
    main()
