#!/usr/bin/env python3
"""Measure WAV durations and optionally enrich a MiMo TTS manifest."""
from __future__ import annotations

import argparse
import json
import sys
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from mimo_logger import JsonlLogger, setup_logger


@dataclass
class DurationItem:
    audio_path: str
    duration_seconds: Optional[float]
    sample_rate: Optional[int]
    channels: Optional[int]
    frames: Optional[int]
    status: str
    error: Optional[str] = None


def wav_duration(path: Path) -> DurationItem:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()
            duration = frames / float(rate) if rate else 0.0
        return DurationItem(str(path), round(duration, 3), rate, channels, frames, "success")
    except Exception as exc:  # noqa: BLE001
        return DurationItem(str(path), None, None, None, None, "failed", str(exc))


def collect_audio_files(args: argparse.Namespace, manifest: Optional[Dict[str, Any]]) -> List[Path]:
    files: List[Path] = []
    if args.audio:
        for item in args.audio:
            p = Path(item)
            if p.is_dir():
                files.extend(sorted(p.glob("*.wav")))
            else:
                files.append(p)
    if manifest:
        for seg in manifest.get("segments", []):
            if isinstance(seg, dict) and seg.get("audio_path"):
                files.append(Path(str(seg["audio_path"])))
    # de-duplicate preserving order
    seen = set()
    result = []
    for p in files:
        key = str(p)
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def enrich_manifest(manifest: Dict[str, Any], duration_by_path: Dict[str, DurationItem]) -> Dict[str, Any]:
    for seg in manifest.get("segments", []):
        if not isinstance(seg, dict):
            continue
        audio_path = str(seg.get("audio_path", ""))
        item = duration_by_path.get(audio_path)
        if item and item.status == "success":
            seg["duration_seconds"] = item.duration_seconds
            seg["sample_rate"] = item.sample_rate
            seg["channels"] = item.channels
    manifest["duration_summary"] = {
        "total_duration_seconds": round(sum((i.duration_seconds or 0.0) for i in duration_by_path.values() if i.status == "success"), 3),
        "measured_count": sum(1 for i in duration_by_path.values() if i.status == "success"),
        "failed_count": sum(1 for i in duration_by_path.values() if i.status == "failed"),
    }
    return manifest


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Measure .wav durations and optionally update a TTS manifest")
    parser.add_argument("--audio", nargs="*", help="One or more wav files or directories")
    parser.add_argument("--manifest", help="Optional TTS manifest to read audio_path values from")
    parser.add_argument("--output", default="output/duration_manifest.json", help="Duration manifest output path")
    parser.add_argument("--update-manifest", action="store_true", help="Write measured duration fields back to --manifest")
    parser.add_argument("--concurrency", type=int, default=4, help="Number of local duration workers")
    parser.add_argument("--jsonl-log", help="Optional JSONL log path")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logger = setup_logger("audio_duration", verbose=args.verbose)
    jsonl = JsonlLogger(args.jsonl_log)
    manifest = None
    if args.manifest:
        with Path(args.manifest).open("r", encoding="utf-8") as f:
            manifest = json.load(f)
    files = collect_audio_files(args, manifest)
    if not files:
        logger.error("No audio files found. Provide --audio or --manifest.")
        return 1

    items: List[DurationItem] = []
    workers = max(1, int(args.concurrency or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(wav_duration, p): p for p in files}
        for future in as_completed(futures):
            item = future.result()
            items.append(item)
            jsonl.write("duration", **asdict(item))
            if item.status == "success":
                logger.info(f"{item.audio_path}: {item.duration_seconds}s")
            else:
                logger.warning(f"{item.audio_path}: {item.error}")

    items.sort(key=lambda x: x.audio_path)
    payload = {
        "summary": {
            "total": len(items),
            "success": sum(1 for i in items if i.status == "success"),
            "failed": sum(1 for i in items if i.status == "failed"),
            "total_duration_seconds": round(sum((i.duration_seconds or 0.0) for i in items if i.status == "success"), 3),
        },
        "items": [asdict(i) for i in items],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Duration manifest written: {out}")

    if args.update_manifest and manifest is not None and args.manifest:
        duration_by_path = {i.audio_path: i for i in items}
        enriched = enrich_manifest(manifest, duration_by_path)
        Path(args.manifest).write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Updated TTS manifest: {args.manifest}")
    return 1 if payload["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
