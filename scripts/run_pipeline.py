#!/usr/bin/env python3
"""Optional orchestrator for MiMo lecture audio workflows.

The pipeline is intentionally opt-in and modular. It does not replace the
single-purpose scripts; it simply routes common combinations.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional

from mimo_logger import JsonlLogger, setup_logger

SCRIPT_DIR = Path(__file__).resolve().parent


def run_cmd(cmd: List[str], *, dry_run: bool, logger, jsonl: JsonlLogger) -> int:
    logger.info("$ " + " ".join(str(c) for c in cmd))
    jsonl.write("command", cmd=cmd, dry_run=dry_run)
    if dry_run:
        return 0
    result = subprocess.run(cmd, text=True)
    jsonl.write("command_result", cmd=cmd, returncode=result.returncode)
    return result.returncode


def zip_dir(source_dir: Path, output_zip: Path) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in source_dir.rglob("*"):
            if path.is_file() and path != output_zip:
                zf.write(path, path.relative_to(source_dir))


def collect_wavs(audio_dir: Path) -> List[str]:
    return [str(p) for p in sorted(audio_dir.glob("*.wav"))]


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run an optional modular MiMo lecture audio pipeline")
    parser.add_argument("--input", help="Lecture source file (.md/.txt/.html/.docx) used when --segments is not provided")
    parser.add_argument("--segments", help="Existing segments JSON; skips clean/make segmentation")
    parser.add_argument("--config", default="templates/config.example.json", help="Config JSON")
    parser.add_argument("--out-dir", default="output/course_audio", help="Pipeline output root")
    parser.add_argument("--course-title", default="MiMo 讲义音频")

    # Optional workflow switches. If no switch is provided, default to --tts only.
    parser.add_argument("--tts", action="store_true", help="Generate MiMo TTS audio")
    parser.add_argument("--asr-check", action="store_true", help="Transcribe generated audio for QA")
    parser.add_argument("--srt", action="store_true", help="Generate SRT subtitles")
    parser.add_argument("--vtt", action="store_true", help="Generate WebVTT subtitles")
    parser.add_argument("--html-player", action="store_true", help="Generate a standalone audio review HTML page")
    parser.add_argument("--inject-html", help="Existing HTML file to receive an injected audio block")
    parser.add_argument("--merge", action="store_true", help="Merge generated wav files into full_course.wav")
    parser.add_argument("--duration", action="store_true", help="Measure per-segment audio duration")
    parser.add_argument("--zip", action="store_true", help="Package pipeline output as ZIP")

    # Common pass-through controls
    parser.add_argument("--stream", action="store_true", help="Pass --stream to TTS preset model only")
    parser.add_argument("--stream-all", action="store_true", help="Pass --stream-all to TTS")
    parser.add_argument("--asr-language", default="zh", choices=["auto", "zh", "en"])
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=4, help="Local post-processing workers; API generation remains rate-limited by sleep-between")
    parser.add_argument("--sleep-between", type=float, help="Pass rate-limit sleep between MiMo API calls")
    parser.add_argument("--log-file", help="Human-readable log file")
    parser.add_argument("--jsonl-log", help="JSONL pipeline log")
    parser.add_argument("--check-docs", action="store_true", help="Run official-doc sync check before pipeline (blocking on CRITICAL/WARNING)")
    parser.add_argument("--skip-check", action="store_true", help="Skip the official-doc pre-flight check entirely")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logger = setup_logger("pipeline", verbose=args.verbose, log_file=args.log_file)
    jsonl = JsonlLogger(args.jsonl_log)
    root = Path(args.out_dir)
    work = root / "work"
    audio_dir = root / "audio"
    asr_dir = root / "asr"
    subtitles_dir = root / "subtitles"
    player_html = root / "player.html"
    tts_manifest = root / "audio_manifest.json"
    asr_manifest = root / "asr_manifest.json"
    segments_path = Path(args.segments) if args.segments else work / "segments.json"
    cleaned_path = work / "cleaned.txt"

    action_flags = [args.tts, args.asr_check, args.srt, args.vtt, args.html_player, bool(args.inject_html), args.merge, args.duration, args.zip]
    if not any(action_flags):
        args.tts = True
        logger.info("No action flag provided; defaulting to --tts only.")

    if not args.segments:
        if not args.input:
            logger.error("Provide --segments, or provide --input so the pipeline can clean and segment it.")
            return 1
        rc = run_cmd([sys.executable, str(SCRIPT_DIR / "clean_lecture_text.py"), "--input", args.input, "--output", str(cleaned_path)], dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc
        rc = run_cmd([sys.executable, str(SCRIPT_DIR / "make_segments.py"), "--input", str(cleaned_path), "--output", str(segments_path)], dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc

    rc = run_cmd([sys.executable, str(SCRIPT_DIR / "validate_segments.py"), "--segments", str(segments_path)], dry_run=args.dry_run, logger=logger, jsonl=jsonl)
    if rc:
        return rc

    # --- Official-doc sync check at pipeline level ---
    config_data = {}
    config_file = Path(args.config)
    if config_file.exists():
        config_data = json.loads(config_file.read_text(encoding="utf-8"))
    doc_check_enabled = bool(config_data.get("doc_check_enabled", True))
    if doc_check_enabled and not args.skip_check:
        check_cmd = [sys.executable, str(SCRIPT_DIR / "check_official_docs.py"), "--config", args.config, "--format", "text"]
        if args.check_docs:
            check_cmd += ["--fail-on", "warning"]
        else:
            check_cmd += ["--fail-on", "critical"]
        rc = run_cmd(check_cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc and args.check_docs:
            logger.error("Official-doc check failed; aborting pipeline. Use --skip-check to override.")
            return rc
        elif rc:
            logger.info("Official-doc check reported issues (non-blocking); continuing pipeline.")

    if args.tts:
        cmd = [sys.executable, str(SCRIPT_DIR / "mimo_tts_batch.py"), "--config", args.config, "--segments", str(segments_path), "--out-dir", str(audio_dir), "--manifest", str(tts_manifest), "--include-text-in-manifest"]
        if args.stream:
            cmd.append("--stream")
        if args.stream_all:
            cmd.append("--stream-all")
        if args.overwrite:
            cmd.append("--overwrite")
        if args.check_docs:
            cmd.append("--check-docs")
        if args.skip_check:
            cmd.append("--skip-check")
        if args.sleep_between is not None:
            cmd += ["--sleep-between", str(args.sleep_between)]
        rc = run_cmd(cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc
    elif not tts_manifest.exists() and (args.duration or args.merge or args.srt or args.vtt or args.html_player or args.asr_check):
        logger.error(f"Missing TTS manifest: {tts_manifest}. Run --tts first or place an existing manifest there.")
        return 1

    if args.duration:
        cmd = [sys.executable, str(SCRIPT_DIR / "audio_duration.py"), "--manifest", str(tts_manifest), "--output", str(root / "duration_manifest.json"), "--update-manifest", "--concurrency", str(args.concurrency)]
        rc = run_cmd(cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc

    if args.asr_check:
        # Use manifest audio paths when possible; fall back to directory scan.
        audio_files = collect_wavs(audio_dir)
        if not audio_files and tts_manifest.exists():
            data = json.loads(tts_manifest.read_text(encoding="utf-8"))
            audio_files = [str(s.get("audio_path")) for s in data.get("segments", []) if isinstance(s, dict) and s.get("audio_path")]
        if not audio_files:
            logger.error("No audio files found for --asr-check")
            return 1
        cmd = [sys.executable, str(SCRIPT_DIR / "mimo_asr_transcribe.py"), "--config", args.config, "--audio", *audio_files, "--language", args.asr_language, "--out-dir", str(asr_dir), "--manifest", str(asr_manifest), "--overwrite"]
        if args.check_docs:
            cmd.append("--check-docs")
        if args.skip_check:
            cmd.append("--skip-check")
        rc = run_cmd(cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc

    srt_path = subtitles_dir / "course.srt"
    vtt_path = subtitles_dir / "course.vtt"
    if args.srt or args.vtt:
        cmd = [sys.executable, str(SCRIPT_DIR / "generate_srt.py"), "--manifest", str(tts_manifest), "--segments", str(segments_path)]
        if args.asr_check and asr_manifest.exists():
            cmd += ["--asr-manifest", str(asr_manifest)]
        if args.srt:
            cmd += ["--srt", str(srt_path)]
        if args.vtt:
            cmd += ["--vtt", str(vtt_path)]
        rc = run_cmd(cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc

    if args.merge:
        cmd = [sys.executable, str(SCRIPT_DIR / "merge_wav.py"), "--manifest", str(tts_manifest), "--output", str(root / "full_course.wav"), "--summary", str(root / "merge_manifest.json")]
        rc = run_cmd(cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc

    if args.html_player:
        cmd = [sys.executable, str(SCRIPT_DIR / "generate_html_player.py"), "--manifest", str(tts_manifest), "--segments", str(segments_path), "--output", str(player_html), "--title", args.course_title]
        if args.srt:
            cmd += ["--srt", str(srt_path)]
        if args.vtt:
            cmd += ["--vtt", str(vtt_path)]
        rc = run_cmd(cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc

    if args.inject_html:
        output_html = root / (Path(args.inject_html).stem + "_with_audio.html")
        cmd = [sys.executable, str(SCRIPT_DIR / "inject_audio_to_html.py"), "--html", args.inject_html, "--manifest", str(tts_manifest), "--output", str(output_html), "--title", "讲义配套音频"]
        rc = run_cmd(cmd, dry_run=args.dry_run, logger=logger, jsonl=jsonl)
        if rc:
            return rc

    if args.zip:
        zip_path = root.with_suffix(".zip")
        if args.dry_run:
            logger.info(f"[dry-run] would create ZIP: {zip_path}")
        else:
            zip_dir(root, zip_path)
            logger.info(f"ZIP written: {zip_path}")

    logger.info(f"Pipeline complete: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
