#!/usr/bin/env python3
"""Merge multiple WAV files into one WAV file using stdlib wave."""
from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from mimo_logger import JsonlLogger, setup_logger


def files_from_manifest(manifest_path: Path) -> List[Path]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    ordered = sorted([s for s in segments if isinstance(s, dict) and s.get("audio_path")], key=lambda s: int(s.get("index") or 0))
    return [Path(str(s["audio_path"])) for s in ordered]


def read_params(path: Path):
    with wave.open(str(path), "rb") as wf:
        return wf.getparams()


def merge_wavs(files: List[Path], output: Path, *, silence_ms: int = 0, strict_params: bool = True) -> Dict[str, Any]:
    if not files:
        raise ValueError("no wav files to merge")
    existing = [p for p in files if p.exists()]
    missing = [str(p) for p in files if not p.exists()]
    if not existing:
        raise FileNotFoundError("no input wav files exist")
    first_params = read_params(existing[0])
    nchannels, sampwidth, framerate = first_params.nchannels, first_params.sampwidth, first_params.framerate
    silence_frames = int(framerate * silence_ms / 1000)
    silence_bytes = b"\x00" * silence_frames * nchannels * sampwidth
    output.parent.mkdir(parents=True, exist_ok=True)
    total_frames = 0
    merged_count = 0
    with wave.open(str(output), "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for idx, path in enumerate(existing):
            with wave.open(str(path), "rb") as wf:
                params = wf.getparams()
                compatible = (params.nchannels, params.sampwidth, params.framerate) == (nchannels, sampwidth, framerate)
                if not compatible:
                    msg = f"incompatible WAV params for {path}: {params}; expected channels={nchannels}, width={sampwidth}, rate={framerate}"
                    if strict_params:
                        raise ValueError(msg)
                    continue
                data = wf.readframes(wf.getnframes())
                out.writeframes(data)
                total_frames += wf.getnframes()
                merged_count += 1
                if silence_ms > 0 and idx < len(existing) - 1:
                    out.writeframes(silence_bytes)
                    total_frames += silence_frames
    return {
        "output": str(output),
        "merged_count": merged_count,
        "missing": missing,
        "duration_seconds": round(total_frames / float(framerate), 3),
        "sample_rate": framerate,
        "channels": nchannels,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Merge segment wav files into one course wav")
    parser.add_argument("--manifest", help="TTS manifest containing segments[].audio_path")
    parser.add_argument("--audio", nargs="*", help="Explicit wav files or directories")
    parser.add_argument("--output", default="output/full_course.wav", help="Merged wav output")
    parser.add_argument("--silence-ms", type=int, default=350, help="Silence inserted between segments")
    parser.add_argument("--non-strict-params", action="store_true", help="Skip files with incompatible WAV params instead of failing")
    parser.add_argument("--summary", default="output/merge_manifest.json", help="Merge summary output JSON")
    parser.add_argument("--jsonl-log")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logger = setup_logger("merge_wav", verbose=args.verbose)
    jsonl = JsonlLogger(args.jsonl_log)
    files: List[Path] = []
    if args.manifest:
        files.extend(files_from_manifest(Path(args.manifest)))
    if args.audio:
        for a in args.audio:
            p = Path(a)
            files.extend(sorted(p.glob("*.wav")) if p.is_dir() else [p])
    try:
        result = merge_wavs(files, Path(args.output), silence_ms=args.silence_ms, strict_params=not args.non_strict_params)
        Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        jsonl.write("merge", **result)
        logger.info(f"Merged {result['merged_count']} wav file(s): {result['output']} ({result['duration_seconds']}s)")
        if result["missing"]:
            logger.warning(f"Missing files skipped: {len(result['missing'])}")
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Merge failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
