#!/usr/bin/env python3
"""Transcribe local wav/mp3 files with MiMo-V2.5-ASR."""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from mimo_audio_common import (
    data_url_from_audio_file,
    dump_json_file,
    endpoint_from_base_url,
    extract_asr_text,
    load_json_file,
    post_json,
    resolve_api_key,
    resolve_base_url,
    stream_json_events,
)

DEFAULT_MODEL = "mimo-v2.5-asr"
DEFAULT_LANGUAGE = "auto"
DEFAULT_OUT_DIR = "output/asr"
DEFAULT_MANIFEST = "output/asr_manifest.json"
SUPPORTED_LANGUAGES = {"auto", "zh", "en"}


@dataclass
class ASRResult:
    audio_path: str
    transcript_path: str
    raw_response_path: Optional[str]
    model: str
    language: str
    status: str
    text_chars: int = 0
    error: Optional[str] = None


def build_payload(audio_path: Path, *, model: str, language: str) -> Dict[str, Any]:
    data_url = data_url_from_audio_file(audio_path)
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": data_url,
                        },
                    }
                ],
            }
        ],
        "asr_options": {
            "language": language,
        },
    }


def extract_stream_text(events: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for event in events:
        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        first = choices[0]
        if not isinstance(first, dict):
            continue
        delta = first.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
        message = first.get("message")
        if isinstance(message, dict):
            text = extract_asr_text({"choices": [{"message": message}]})
            if text:
                parts.append(text)
    return "".join(parts).strip()


def transcribe_files(args: argparse.Namespace) -> int:
    config = load_json_file(Path(args.config)) if args.config else {}
    api_key = resolve_api_key(args, config)
    base_url = resolve_base_url(args, config)
    endpoint = endpoint_from_base_url(base_url)
    auth_mode = str(args.auth_mode or config.get("auth_mode") or "api-key")

    model = str(args.model or config.get("default_asr_model") or DEFAULT_MODEL)
    language = str(args.language or config.get("default_asr_language") or DEFAULT_LANGUAGE)
    out_dir = Path(args.out_dir or config.get("default_asr_output_dir") or DEFAULT_OUT_DIR)
    manifest_path = Path(args.manifest or config.get("default_asr_manifest") or DEFAULT_MANIFEST)
    raw_dir = Path(args.raw_dir or config.get("default_asr_raw_response_dir") or "output/asr_raw_responses")
    timeout = int(args.timeout or config.get("timeout") or 120)
    retries = int(args.retries if args.retries is not None else config.get("retries", 2))
    sleep_between = float(args.sleep_between if args.sleep_between is not None else config.get("sleep_between", 0.0))

    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("--language must be one of: auto, zh, en")
    if model != DEFAULT_MODEL:
        raise ValueError("currently only mimo-v2.5-asr is supported for ASR")
    if not args.dry_run and not api_key:
        raise RuntimeError("MIMO_API_KEY is required unless --dry-run is used")

    # --- Official-doc sync check (self-update guard) ---
    doc_check_enabled = bool(config.get("doc_check_enabled", True))
    if doc_check_enabled and not getattr(args, "skip_check", False):
        try:
            import check_official_docs as _cod
            issues, _extracted, _models = _cod.run_check(config, args, api_key_override=api_key, base_url_override=base_url)
            critical = [i for i in issues if i["severity"] == _cod.CRITICAL]
            warnings = [i for i in issues if i["severity"] == _cod.WARNING]
            if critical:
                print(f"[DOC-CHECK] {len(critical)} CRITICAL issue(s) detected:")
                for i in critical:
                    print(f"  [CRITICAL] ({i['section']}) {i['message']}")
                if getattr(args, "check_docs", False):
                    raise RuntimeError(
                        "Official-doc check found CRITICAL issues (model may be deprecated). "
                        "Use --skip-check to override at your own risk."
                    )
                else:
                    print("[DOC-CHECK] Running in non-blocking mode; continuing despite CRITICAL issues. Use --check-docs to enforce.")
            elif warnings and getattr(args, "check_docs", False):
                print(f"[DOC-CHECK] {len(warnings)} WARNING(s):")
                for i in warnings:
                    print(f"  [WARNING] ({i['section']}) {i['message']}")
                raise RuntimeError("Official-doc check found warnings and --check-docs is enabled.")
            elif warnings:
                print(f"[DOC-CHECK] {len(warnings)} WARNING(s) (non-blocking). Run check_official_docs.py for details.")
        except RuntimeError:
            raise
        except Exception as exc:
            if getattr(args, "verbose", False):
                print(f"[DOC-CHECK] Skipped due to error: {exc}")

    audio_files = [Path(p) for p in args.audio]
    if not audio_files:
        raise ValueError("provide at least one --audio path")
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.save_raw_response:
        raw_dir.mkdir(parents=True, exist_ok=True)

    results: List[ASRResult] = []
    for audio_path in audio_files:
        transcript_path = out_dir / f"{audio_path.stem}.txt"
        raw_path = raw_dir / f"{audio_path.stem}.json"
        try:
            if not audio_path.exists():
                raise FileNotFoundError(f"audio file not found: {audio_path}")
            if transcript_path.exists() and not args.overwrite and not args.dry_run:
                results.append(ASRResult(str(audio_path), str(transcript_path), None, model, language, "skipped", transcript_path.read_text(encoding="utf-8", errors="ignore").__len__(), "file exists; use --overwrite"))
                print(f"[SKIP] {audio_path} -> {transcript_path}")
                continue
            if args.dry_run:
                # Also validates file type and base64 size without calling API.
                data_url_from_audio_file(audio_path)
                results.append(ASRResult(str(audio_path), str(transcript_path), None, model, language, "dry_run"))
                print(f"[DRY]  {audio_path} language={language}")
                continue

            assert api_key is not None
            payload = build_payload(audio_path, model=model, language=language)
            if args.stream:
                payload["stream"] = True

            last_exc: Optional[Exception] = None
            response: Optional[Dict[str, Any]] = None
            text = ""
            for attempt in range(1, retries + 2):
                try:
                    if args.stream:
                        events = list(stream_json_events(endpoint, api_key, payload, timeout=timeout, auth_mode=auth_mode))
                        text = extract_stream_text(events)
                        response = {"stream_events": events}
                    else:
                        response = post_json(endpoint, api_key, payload, timeout=timeout, auth_mode=auth_mode)
                        text = extract_asr_text(response)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt > retries:
                        raise
                    retry_after = getattr(exc, "retry_after", None)
                    sleep_seconds = float(retry_after) if retry_after is not None else min(2 ** attempt, 30)
                    print(f"[WARN] {audio_path.name} attempt {attempt} failed; retrying in {sleep_seconds:.1f}s: {exc}")
                    time.sleep(sleep_seconds)
            if response is None:
                raise RuntimeError(last_exc or "unknown ASR failure")
            transcript_path.write_text(text, encoding="utf-8")
            raw_response_path = None
            if args.save_raw_response:
                raw_response_path = str(raw_path)
                dump_json_file(raw_path, response)
            results.append(ASRResult(str(audio_path), str(transcript_path), raw_response_path, model, language, "success", len(text)))
            print(f"[OK]   {audio_path} -> {transcript_path} ({len(text)} chars)")
            if sleep_between > 0:
                time.sleep(sleep_between)
        except Exception as exc:  # noqa: BLE001
            if args.verbose:
                traceback.print_exc()
            results.append(ASRResult(str(audio_path), str(transcript_path), None, model, language, "failed", error=str(exc)))
            print(f"[FAIL] {audio_path}: {exc}")
            if args.stop_on_error:
                break

    manifest = {
        "generated_at_unix": int(time.time()),
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "dry_run": sum(1 for r in results if r.status == "dry_run"),
        },
        "items": [asdict(r) for r in results],
    }
    dump_json_file(manifest_path, manifest)
    print(f"[DONE] manifest: {manifest_path}")
    return 1 if any(r.status == "failed" for r in results) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transcribe wav/mp3 audio with MiMo-V2.5-ASR")
    p.add_argument("--audio", nargs="+", required=True, help="One or more .wav/.mp3 files")
    p.add_argument("--config", help="Optional config JSON")
    p.add_argument("--out-dir", help="Transcript output directory")
    p.add_argument("--manifest", help="ASR manifest output path")
    p.add_argument("--raw-dir", help="Raw response output directory")
    p.add_argument("--api-key", help="API key override")
    p.add_argument("--base-url", help="Base URL override")
    p.add_argument("--auth-mode", choices=["api-key", "bearer"], help="Authentication header mode; default api-key")
    p.add_argument("--model", help="ASR model; default mimo-v2.5-asr")
    p.add_argument("--language", choices=sorted(SUPPORTED_LANGUAGES), help="Recognition language: auto, zh, en")
    p.add_argument("--timeout", type=int)
    p.add_argument("--retries", type=int)
    p.add_argument("--sleep-between", type=float)
    p.add_argument("--stream", action="store_true", help="Use streaming ASR response")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--save-raw-response", action="store_true")
    p.add_argument("--stop-on-error", action="store_true")
    p.add_argument("--check-docs", action="store_true", help="Run official-doc sync check before transcription (blocking)")
    p.add_argument("--skip-check", action="store_true", help="Skip the official-doc pre-flight check entirely")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return transcribe_files(args)
    except Exception as exc:  # noqa: BLE001
        if args.verbose:
            traceback.print_exc()
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
