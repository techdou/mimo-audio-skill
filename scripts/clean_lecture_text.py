#!/usr/bin/env python3
"""Clean lecture text before narration rewriting.

Supports .txt, .md, .html, .htm. Optionally supports .docx if python-docx is installed.
This script does not perform intelligent rewriting. It only removes obvious markup/noise.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Iterable, Optional

HTML_TAG_RE = re.compile(r"<[^>]+>")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
URL_RE = re.compile(r"https?://\S+")
MULTI_SPACE_RE = re.compile(r"[ \t]+")
MULTI_BLANK_RE = re.compile(r"\n{3,}")


def read_input(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".html", ".htm"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        try:
            from docx import Document  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Reading .docx requires optional dependency: pip install python-docx") from exc
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    raise ValueError(f"unsupported file type: {suffix}")


def remove_markdown_tables(text: str) -> str:
    lines = text.splitlines()
    kept = []
    for line in lines:
        stripped = line.strip()
        # Drop obvious Markdown table separator rows and dense table rows.
        if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", stripped):
            continue
        if stripped.count("|") >= 3:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 3:
                kept.append("；".join(c for c in cells if c))
                continue
        kept.append(line)
    return "\n".join(kept)


def clean_text(text: str, keep_urls: bool = False, keep_code: bool = False) -> str:
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")

    if not keep_code:
        text = CODE_BLOCK_RE.sub("\n[代码内容已省略]\n", text)
    else:
        text = text.replace("```", "")

    text = MD_IMAGE_RE.sub("", text)
    text = MD_LINK_RE.sub(r"\1", text)
    text = INLINE_CODE_RE.sub(r"\1", text)
    text = HTML_TAG_RE.sub(" ", text)

    if not keep_urls:
        text = URL_RE.sub("", text)

    text = remove_markdown_tables(text)

    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned_lines.append("")
            continue

        # Remove common Markdown heading/list markers but keep the title text.
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = re.sub(r"^\d+[.)、]\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        line = line.replace("---", "")
        line = MULTI_SPACE_RE.sub(" ", line).strip()

        # Drop likely page/footer noise.
        if re.fullmatch(r"第?\s*\d+\s*页", line):
            continue
        if line.lower() in {"references", "bibliography", "参考文献"}:
            break

        if line:
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = MULTI_BLANK_RE.sub("\n\n", text).strip() + "\n"
    return text


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean lecture notes before narration rewriting")
    parser.add_argument("--input", required=True, help="Input .txt/.md/.html/.docx file")
    parser.add_argument("--output", required=True, help="Output cleaned .txt file")
    parser.add_argument("--keep-urls", action="store_true", help="Keep URLs instead of removing them")
    parser.add_argument("--keep-code", action="store_true", help="Keep code block text instead of replacing with a placeholder")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    text = read_input(input_path)
    cleaned = clean_text(text, keep_urls=args.keep_urls, keep_code=args.keep_code)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cleaned, encoding="utf-8")
    print(f"Cleaned text written: {output_path}")
    print(f"Characters: {len(cleaned)}")


if __name__ == "__main__":
    main()
