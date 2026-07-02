#!/usr/bin/env python3
"""Minimal real-call smoke tests for MiMo-V2.5 audio APIs.

This script is intentionally small and conservative. It validates that the
current API key/base URL/auth mode can complete one preset TTS call, one preset
streaming TTS call, and one ASR call against a local wav/mp3 file.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from mimo_audio_common import (
    data_url_from_audio_file,
    dump_json_file,
    endpoint_from_base_url,
    extract_asr_text,
    extract_tts_audio_base64,
    load_json_file,
    post_json,
    resolve_api_key,
    resolve_base_url,
    stream_json_events,
)
from mimo_tts_batch import extract_stream_audio_chunks, write_pcm16_wav


def build_tts_payload(*, stream: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": "mimo-v2.5-tts",
        "messages": [
            {
                "role": "user",
                "content": "用清晰、自然、适合课程旁白的语气朗读，语速中等偏慢。",
            },
            {
                "role": "assistant",
                "content": "这是一段 MiMo 语音合成连通性测试。",
            },
        ],
        "audio": {
            "format": "pcm16" if stream else "wav",
            "voice": "冰糖",
        },
    }
    if stream:
        payload["stream"] = True
    return payload


def build_asr_payload(audio_path: Path, language: str) -> Dict[str, Any]:
    return {
        "model": "mimo-v2.5-asr",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": data_url_from_audio_file(audio_path),
                        },
                    }
                ],
            }
        ],
        "asr_options": {"language": language},
    }


def run_smoke_tests(args: argparse.Namespace) -> int:
    config = load_json_file(Path(args.config)) if args.config else {}
    api_key = resolve_api_key(args, config)
    base_url = resolve_base_url(args, config)
    endpoint = endpoint_from_base_url(base_url)
    auth_mode = str(args.auth_mode or config.get("auth_mode") or "api-key")
    timeout = int(args.timeout or config.get("timeout") or 120)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tests: List[Dict[str, Any]] = []

    if args.dry_run:
        tests.append({"name": "tts_non_stream", "status": "dry_run", "payload": build_tts_payload(stream=False)})
        if not args.skip_stream:
            tests.append({"name": "tts_stream", "status": "dry_run", "payload": build_tts_payload(stream=True)})
        if not args.skip_asr:
            asr_audio = Path(args.asr_audio)
            data_url_from_audio_file(asr_audio)
            tests.append({"name": "asr", "status": "dry_run", "audio": str(asr_audio), "payload_shape": "input_audio.data data URL"})
        dump_json_file(out_dir / "smoke_manifest.json", {"dry_run": True, "tests": tests})
        print(f"[DRY] smoke manifest: {out_dir / 'smoke_manifest.json'}")
        return 0

    if not api_key:
        raise RuntimeError("MIMO_API_KEY is required unless --dry-run is used")

    # 1) Non-stream preset TTS
    try:
        response = post_json(endpoint, api_key, build_tts_payload(stream=False), timeout=timeout, auth_mode=auth_mode)
        audio = base64.b64decode(extract_tts_audio_base64(response), validate=True)
        output = out_dir / "tts_preset.wav"
        output.write_bytes(audio)
        tests.append({"name": "tts_non_stream", "status": "success", "path": str(output), "bytes": len(audio)})
        print(f"[OK] tts_non_stream -> {output} ({len(audio)} bytes)")
    except Exception as exc:  # noqa: BLE001
        tests.append({"name": "tts_non_stream", "status": "failed", "error": str(exc)})
        print(f"[FAIL] tts_non_stream: {exc}")
        if args.stop_on_error:
            dump_json_file(out_dir / "smoke_manifest.json", {"tests": tests})
            return 1

    # 2) Streaming preset TTS
    if not args.skip_stream:
        try:
            events = list(stream_json_events(endpoint, api_key, build_tts_payload(stream=True), timeout=timeout, auth_mode=auth_mode))
            pcm = extract_stream_audio_chunks(events)
            if not pcm:
                raise RuntimeError("stream response did not include audio chunks")
            output = out_dir / "tts_stream.wav"
            write_pcm16_wav(output, pcm)
            tests.append({"name": "tts_stream", "status": "success", "path": str(output), "pcm_bytes": len(pcm), "events": len(events)})
            print(f"[OK] tts_stream -> {output} ({len(pcm)} pcm bytes, {len(events)} events)")
        except Exception as exc:  # noqa: BLE001
            tests.append({"name": "tts_stream", "status": "failed", "error": str(exc)})
            print(f"[FAIL] tts_stream: {exc}")
            if args.stop_on_error:
                dump_json_file(out_dir / "smoke_manifest.json", {"tests": tests})
                return 1

    # 3) ASR
    if not args.skip_asr:
        try:
            audio_path = Path(args.asr_audio)
            payload = build_asr_payload(audio_path, args.language)
            response = post_json(endpoint, api_key, payload, timeout=timeout, auth_mode=auth_mode)
            transcript = extract_asr_text(response)
            transcript_path = out_dir / "asr_transcript.txt"
            transcript_path.write_text(transcript, encoding="utf-8")
            tests.append({"name": "asr", "status": "success", "audio": str(audio_path), "path": str(transcript_path), "text_chars": len(transcript)})
            print(f"[OK] asr -> {transcript_path} ({len(transcript)} chars)")
        except Exception as exc:  # noqa: BLE001
            tests.append({"name": "asr", "status": "failed", "error": str(exc)})
            print(f"[FAIL] asr: {exc}")
            if args.stop_on_error:
                dump_json_file(out_dir / "smoke_manifest.json", {"tests": tests})
                return 1

    manifest = {"generated_at_unix": int(time.time()), "base_url": base_url, "auth_mode": auth_mode, "tests": tests}
    dump_json_file(out_dir / "smoke_manifest.json", manifest)
    failed = any(t.get("status") == "failed" for t in tests)
    print(f"[DONE] smoke manifest: {out_dir / 'smoke_manifest.json'}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run minimal real-call smoke tests for MiMo-V2.5 TTS/ASR")
    p.add_argument("--config", help="Optional config JSON")
    p.add_argument("--api-key", help="API key override; takes precedence over env")
    p.add_argument("--base-url", help="Base URL override")
    p.add_argument("--auth-mode", choices=["api-key", "bearer"], help="Authentication header mode; default api-key")
    p.add_argument("--out-dir", default="output/smoke", help="Smoke test output directory")
    p.add_argument("--timeout", type=int)
    p.add_argument("--asr-audio", default="examples/silence_sample.wav", help="Local wav/mp3 file for ASR smoke test")
    p.add_argument("--language", choices=["auto", "zh", "en"], default="auto")
    p.add_argument("--skip-stream", action="store_true")
    p.add_argument("--skip-asr", action="store_true")
    p.add_argument("--stop-on-error", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Validate payloads/files without API calls")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run_smoke_tests(args)
    except Exception as exc:  # noqa: BLE001
        if args.verbose:
            traceback.print_exc()
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
