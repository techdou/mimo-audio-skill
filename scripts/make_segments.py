#!/usr/bin/env python3
"""Create rough MiMo TTS segment JSON from cleaned text.

This is a helper, not a replacement for agent-based narration rewriting.
It preserves text as much as possible and splits by headings/paragraphs.
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
    parser = argparse.ArgumentParser(description="Make rough MiMo TTS segments from cleaned lecture text")
    parser.add_argument("--input", required=True, help="Input cleaned text file")
    parser.add_argument("--output", required=True, help="Output segments JSON")
    parser.add_argument("--title-prefix", default="课程片段", help="Fallback title prefix")
    parser.add_argument("--max-chars", type=int, default=650, help="Approximate max Chinese characters per segment")
    parser.add_argument("--style", default=DEFAULT_STYLE, help="Style instruction for all segments")
    parser.add_argument("--model", default="mimo-v2.5-tts", help="Default model")
    parser.add_argument("--voice", default="冰糖", help="Default voice")
    parser.add_argument("--format", default="wav", help="Default audio format")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    text = input_path.read_text(encoding="utf-8", errors="replace")
    chunks = make_chunks(text, max_chars=args.max_chars)

    segments = []
    for i, chunk in enumerate(chunks, start=1):
        title = infer_title(chunk, i, args.title_prefix)
        slug = slugify(title, f"segment_{i:02d}")
        segments.append(
            {
                "index": i,
                "title": title,
                "filename": f"{i:02d}_{slug}.{args.format}",
                "model": args.model,
                "voice": args.voice,
                "format": args.format,
                "style_instruction": args.style,
                "speech_text": chunk,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)

    print(f"Segments written: {output_path}")
    print(f"Segment count: {len(segments)}")


if __name__ == "__main__":
    main()
