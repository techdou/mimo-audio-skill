#!/usr/bin/env python3
"""Batch synthesize lecture narration segments with MiMo-V2.5-TTS.

Supports:
- preset TTS: mimo-v2.5-tts
- text voice design: mimo-v2.5-tts-voicedesign
- voice clone with data URI or local .mp3/.wav sample: mimo-v2.5-tts-voiceclone
- non-stream WAV output
- low-latency-compatible streaming PCM16 output converted to WAV
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import traceback
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mimo_audio_common import (
    MiMoHTTPError,
    data_url_from_audio_file,
    dump_json_file,
    endpoint_from_base_url,
    extract_tts_audio_base64,
    load_json_file,
    post_json,
    resolve_api_key,
    resolve_base_url,
    stream_json_events,
    strip_data_uri_prefix,
)
from segment_validation import summarize_issues, validate_segments

DEFAULT_MODEL = "mimo-v2.5-tts"
DEFAULT_VOICE = "冰糖"
DEFAULT_FORMAT = "wav"
DEFAULT_OUT_DIR = "output/audio"
DEFAULT_MANIFEST = "output/audio_manifest.json"
DEFAULT_STYLE = (
    "用温柔、清晰、适合课程讲解的语气朗读，语速中等偏慢，声音自然亲切。"
    "遇到重要概念时适当停顿，遇到步骤、定义、对比和案例时保持清楚的节奏感。"
)
SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
PCM16_SAMPLE_RATE = 24000


@dataclass
class SegmentResult:
    index: int
    title: str
    filename: str
    audio_path: str
    model: str
    voice: Optional[str]
    format: str
    status: str
    stream: bool = False
    bytes_written: int = 0
    error: Optional[str] = None
    speech_text: Optional[str] = None
    raw_response_path: Optional[str] = None


def load_segments(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"segments file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        segments = data
    elif isinstance(data, dict) and isinstance(data.get("segments"), list):
        segments = data["segments"]
    else:
        raise ValueError("segments JSON must be either a list or an object with a 'segments' list")
    if not segments:
        raise ValueError("segments list is empty")
    for i, seg in enumerate(segments, start=1):
        if not isinstance(seg, dict):
            raise ValueError(f"segment #{i} must be an object")
    return segments


def safe_filename(filename: str, index: int, fmt: str, stream: bool = False) -> str:
    fmt = fmt.lower().strip()
    suffix = ".wav" if fmt in {"wav", "pcm16"} else f".{fmt}"
    filename = (filename or "").strip().replace(" ", "_")
    if not filename:
        filename = f"{index:02d}_segment{suffix}"
    filename = SAFE_FILENAME_RE.sub("_", filename).strip("._-")
    if not filename:
        filename = f"{index:02d}_segment{suffix}"
    if not filename.lower().endswith(suffix):
        filename = f"{Path(filename).stem or f'{index:02d}_segment'}{suffix}"
    return filename


def get_audio_field(segment: Dict[str, Any]) -> Dict[str, Any]:
    audio = segment.get("audio")
    return dict(audio) if isinstance(audio, dict) else {}


def _prefix_speech_text(segment: Dict[str, Any], speech_text: str) -> str:
    tags = segment.get("speech_prefix_tags") or segment.get("assistant_prefix_tags") or segment.get("style_tags")
    if not tags:
        return speech_text
    if isinstance(tags, str):
        prefix = tags.strip()
    elif isinstance(tags, list):
        cleaned = [str(t).strip().strip("()（）[]") for t in tags if str(t).strip()]
        prefix = "(" + " ".join(cleaned) + ")" if cleaned else ""
    else:
        prefix = ""
    return f"{prefix}{speech_text}" if prefix else speech_text


def build_payload(
    segment: Dict[str, Any],
    index: int,
    *,
    default_model: str,
    default_voice: Optional[str],
    default_format: str,
    default_style: str,
    force_stream: bool = False,
) -> Tuple[Dict[str, Any], str, Optional[str], str, str, str, bool]:
    title = str(segment.get("title") or f"Segment {index}").strip()
    speech_text = str(segment.get("speech_text") or segment.get("content") or "").strip()
    if not speech_text:
        raise ValueError(f"segment #{index} has empty speech_text")
    speech_text = _prefix_speech_text(segment, speech_text)

    model = str(segment.get("model") or default_model).strip()
    style_instruction = str(segment.get("style_instruction") or default_style).strip()
    voice_design_prompt = str(segment.get("voice_design_prompt") or segment.get("voice_description") or "").strip()

    audio_obj: Dict[str, Any] = get_audio_field(segment)
    stream = bool(force_stream or segment.get("stream", False))
    fmt = str(segment.get("format") or audio_obj.get("format") or ("pcm16" if stream else default_format)).strip().lower()
    if stream:
        fmt = "pcm16"
    audio_obj["format"] = fmt

    voice = segment.get("voice", audio_obj.get("voice", default_voice))
    if voice is not None:
        voice = str(voice)

    if model == "mimo-v2.5-tts-voicedesign":
        audio_obj.pop("voice", None)
        if "optimize_text_preview" not in audio_obj:
            audio_obj["optimize_text_preview"] = bool(segment.get("optimize_text_preview", True))
        user_content = "\n".join(p for p in [voice_design_prompt, style_instruction] if p).strip() or default_style
        voice_for_manifest = "voice-design"
    elif model == "mimo-v2.5-tts-voiceclone":
        voice_sample_path = str(segment.get("voice_sample_path") or audio_obj.pop("voice_sample_path", "")).strip()
        if voice_sample_path:
            voice = data_url_from_audio_file(Path(voice_sample_path))
        if not voice:
            raise ValueError(f"segment #{index} uses voiceclone but has no voice/audio.voice data URI or voice_sample_path")
        audio_obj["voice"] = voice
        user_content = style_instruction
        voice_for_manifest = "voiceclone"
    else:
        if voice:
            audio_obj["voice"] = voice
        user_content = style_instruction
        voice_for_manifest = voice

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": speech_text},
        ],
        "audio": audio_obj,
    }
    if stream:
        payload["stream"] = True

    for optional_key in ("temperature", "top_p", "max_tokens"):
        if optional_key in segment:
            payload[optional_key] = segment[optional_key]

    return payload, title, voice_for_manifest, fmt, model, speech_text, stream


def extract_stream_audio_chunks(events: List[Dict[str, Any]]) -> bytes:
    chunks: List[bytes] = []
    for event in events:
        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        first = choices[0]
        delta = first.get("delta") if isinstance(first, dict) else None
        message = first.get("message") if isinstance(first, dict) else None
        audio_obj = None
        if isinstance(delta, dict):
            audio_obj = delta.get("audio")
        if audio_obj is None and isinstance(message, dict):
            audio_obj = message.get("audio")
        if isinstance(audio_obj, dict) and isinstance(audio_obj.get("data"), str):
            chunks.append(base64.b64decode(strip_data_uri_prefix(audio_obj["data"])))
    return b"".join(chunks)


def write_pcm16_wav(path: Path, pcm_bytes: bytes, sample_rate: int = PCM16_SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def failed_segment_keys(manifest_path: Path) -> Tuple[set[int], set[str]]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"--failed-only requires an existing manifest: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    failed_indices: set[int] = set()
    failed_filenames: set[str] = set()
    for item in manifest.get("segments", []):
        if item.get("status") == "failed":
            try:
                failed_indices.add(int(item.get("index")))
            except (TypeError, ValueError):
                pass
            if item.get("filename"):
                failed_filenames.add(str(item["filename"]).lower())
    return failed_indices, failed_filenames


def filter_failed_only(segments: List[Dict[str, Any]], manifest_path: Path, default_format: str) -> List[Dict[str, Any]]:
    failed_indices, failed_filenames = failed_segment_keys(manifest_path)
    filtered: List[Dict[str, Any]] = []
    for loop_index, segment in enumerate(segments, start=1):
        index = int(segment.get("index") or loop_index)
        stream = bool(segment.get("stream", False))
        fmt = str(segment.get("format") or get_audio_field(segment).get("format") or ("pcm16" if stream else default_format)).lower()
        filename = safe_filename(str(segment.get("filename") or ""), index, fmt, stream=stream).lower()
        if index in failed_indices or filename in failed_filenames:
            filtered.append(segment)
    return filtered


def cfg_get(args: argparse.Namespace, config: Dict[str, Any], attr: str, key: str, default: Any) -> Any:
    value = getattr(args, attr, None)
    if value is not None:
        return value
    return config.get(key, default)


def write_manifest(path: Path, results: List[SegmentResult], source_segments: Path, dry_run: bool, validation_summary: Dict[str, int]) -> None:
    payload = {
        "source_segments": str(source_segments),
        "dry_run": dry_run,
        "generated_at_unix": int(time.time()),
        "validation_summary": validation_summary,
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "dry_run": sum(1 for r in results if r.status == "dry_run"),
        },
        "segments": [asdict(r) for r in results],
    }
    dump_json_file(path, payload)


def synthesize_batch(args: argparse.Namespace) -> int:
    config = load_json_file(Path(args.config)) if args.config else {}
    segments_path = Path(args.segments)
    out_dir = Path(cfg_get(args, config, "out_dir", "default_output_dir", DEFAULT_OUT_DIR))
    manifest_path = Path(cfg_get(args, config, "manifest", "default_manifest", DEFAULT_MANIFEST))
    raw_dir = Path(cfg_get(args, config, "raw_dir", "default_raw_response_dir", "output/raw_responses"))
    out_dir.mkdir(parents=True, exist_ok=True)

    default_model = str(cfg_get(args, config, "default_model", "default_model", DEFAULT_MODEL))
    default_voice_raw = cfg_get(args, config, "default_voice", "default_voice", DEFAULT_VOICE)
    default_voice = None if default_voice_raw in (None, "") else str(default_voice_raw)
    default_format = str(cfg_get(args, config, "default_format", "default_format", DEFAULT_FORMAT)).lower()
    default_style = str(cfg_get(args, config, "default_style", "default_style_instruction", DEFAULT_STYLE))
    timeout = int(cfg_get(args, config, "timeout", "timeout", 120))
    retries = int(cfg_get(args, config, "retries", "retries", 2))
    sleep_between = float(cfg_get(args, config, "sleep_between", "sleep_between", 0.0))
    min_chars = int(cfg_get(args, config, "min_chars", "min_chars", 20))
    max_chars = int(cfg_get(args, config, "max_chars", "max_chars", 1000))
    force_stream_all = bool(args.stream_all)

    api_key = resolve_api_key(args, config)
    base_url = resolve_base_url(args, config)
    endpoint = endpoint_from_base_url(base_url)
    auth_mode = str(args.auth_mode or config.get("auth_mode") or "api-key")

    segments = load_segments(segments_path)
    if args.failed_only:
        segments = filter_failed_only(segments, manifest_path, default_format)
        print(f"[INFO] --failed-only selected {len(segments)} segment(s)")
        if not segments:
            print("[INFO] No failed segments found in existing manifest")
            return 0

    if args.stream or args.stream_all:
        stream_selected = 0
        for seg in segments:
            seg_model = str(seg.get("model") or default_model).strip()
            if args.stream_all or seg_model == "mimo-v2.5-tts":
                seg["stream"] = True
                seg["format"] = "pcm16"
                stream_selected += 1
        if args.stream and not args.stream_all:
            skipped = len(segments) - stream_selected
            if skipped:
                print(f"[INFO] --stream applied to {stream_selected} preset TTS segment(s); {skipped} voicedesign/voiceclone segment(s) kept non-stream. Use --stream-all to force compatibility streaming for all models.")

    issues = validate_segments(segments, min_chars=min_chars, max_chars=max_chars)
    validation_summary = summarize_issues(issues)
    if issues:
        print(f"[VALIDATE] errors={validation_summary['errors']}, warnings={validation_summary['warnings']}")
        for issue in issues[:80]:
            idx = "-" if issue.index is None else f"{issue.index:02d}"
            print(f"[{issue.level.upper()}] segment={idx} field={issue.field}: {issue.message}")
        if len(issues) > 80:
            print(f"[VALIDATE] ... {len(issues) - 80} more issue(s) omitted")
    if validation_summary["errors"] > 0:
        raise RuntimeError("segment validation failed; fix errors before synthesis")
    if args.strict and validation_summary["warnings"] > 0:
        raise RuntimeError("segment validation produced warnings and --strict is enabled")

    if not args.dry_run and not api_key:
        raise RuntimeError("MIMO_API_KEY is required unless --dry-run is used")

    results: List[SegmentResult] = []
    for loop_index, segment in enumerate(segments, start=1):
        index = int(segment.get("index") or loop_index)
        title = str(segment.get("title") or f"Segment {index}")
        try:
            payload, title, voice, fmt, model, speech_text, stream = build_payload(
                segment=segment,
                index=index,
                default_model=default_model,
                default_voice=default_voice,
                default_format=default_format,
                default_style=default_style,
                force_stream=force_stream_all,
            )
            filename = safe_filename(str(segment.get("filename") or ""), index, fmt, stream=stream)
            audio_path = out_dir / filename

            if audio_path.exists() and not args.overwrite and not args.dry_run:
                results.append(SegmentResult(index, title, filename, str(audio_path), model, voice, fmt, "skipped", stream, audio_path.stat().st_size, "file exists; use --overwrite to regenerate", speech_text if args.include_text_in_manifest else None))
                print(f"[SKIP] {index:02d} {filename} already exists")
                continue

            if args.dry_run:
                results.append(SegmentResult(index, title, filename, str(audio_path), model, voice, fmt, "dry_run", stream, speech_text=speech_text if args.include_text_in_manifest else None))
                print(f"[DRY]  {index:02d} {filename}: {len(speech_text)} chars, model={model}, stream={stream}")
                continue

            assert api_key is not None
            def do_call() -> Tuple[bytes, Optional[Dict[str, Any]]]:
                if stream:
                    events = list(stream_json_events(endpoint, api_key, payload, timeout=timeout, auth_mode=auth_mode))
                    pcm_bytes = extract_stream_audio_chunks(events)
                    if not pcm_bytes:
                        # Fallback if provider returned a final non-delta response in stream mode.
                        for event in reversed(events):
                            try:
                                b64 = extract_tts_audio_base64(event)
                                pcm_bytes = base64.b64decode(b64, validate=True)
                                break
                            except Exception:
                                continue
                    if not pcm_bytes:
                        raise ValueError("stream response did not contain audio chunks")
                    return pcm_bytes, {"stream_events": events[-5:] if args.save_raw_response else []}
                response = post_json(endpoint, api_key, payload, timeout=timeout, auth_mode=auth_mode)
                b64 = extract_tts_audio_base64(response)
                return base64.b64decode(b64, validate=True), response if args.save_raw_response else None

            try:
                audio_bytes, raw_response = None, None
                last_exc = None
                for attempt in range(1, retries + 2):
                    try:
                        audio_bytes, raw_response = do_call()
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        if attempt > retries:
                            raise
                        retry_after = getattr(exc, "retry_after", None)
                        sleep_seconds = float(retry_after) if isinstance(exc, MiMoHTTPError) and exc.status_code == 429 and retry_after is not None else min(2 ** attempt, 30)
                        print(f"[WARN] {index:02d} attempt {attempt} failed; retrying in {sleep_seconds:.1f}s: {exc}")
                        time.sleep(sleep_seconds)
                if audio_bytes is None:
                    raise RuntimeError(last_exc or "unknown synthesis failure")

                if stream:
                    write_pcm16_wav(audio_path, audio_bytes)
                    bytes_written = audio_path.stat().st_size
                else:
                    audio_path.parent.mkdir(parents=True, exist_ok=True)
                    audio_path.write_bytes(audio_bytes)
                    bytes_written = len(audio_bytes)

                raw_response_path = None
                if args.save_raw_response and raw_response is not None:
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    raw_response_path = str(raw_dir / f"{Path(filename).stem}.json")
                    dump_json_file(Path(raw_response_path), raw_response)

                results.append(SegmentResult(index, title, filename, str(audio_path), model, voice, fmt, "success", stream, bytes_written, speech_text=speech_text if args.include_text_in_manifest else None, raw_response_path=raw_response_path))
                print(f"[OK]   {index:02d} {filename}: {bytes_written} bytes")
            except Exception:
                raise

            if sleep_between > 0:
                time.sleep(sleep_between)
        except Exception as exc:  # noqa: BLE001
            if args.verbose:
                traceback.print_exc()
            fmt = str(segment.get("format") or get_audio_field(segment).get("format") or default_format).lower()
            stream = bool(force_stream_all or segment.get("stream", False))
            filename = safe_filename(str(segment.get("filename") or ""), index, fmt, stream=stream)
            results.append(SegmentResult(index, title, filename, str(out_dir / filename), str(segment.get("model") or default_model), str(segment.get("voice") or "") or None, fmt, "failed", stream, error=str(exc)))
            print(f"[FAIL] {index:02d} {filename}: {exc}")
            if args.stop_on_error:
                break

    write_manifest(manifest_path, results, segments_path, args.dry_run, validation_summary)
    print(f"[DONE] manifest: {manifest_path}")
    failed = sum(1 for r in results if r.status == "failed")
    return 1 if failed else 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch synthesize lecture segments with MiMo-V2.5-TTS")
    parser.add_argument("--segments", required=True, help="Path to segments JSON")
    parser.add_argument("--config", help="Optional config JSON")
    parser.add_argument("--out-dir", help="Output audio directory")
    parser.add_argument("--manifest", help="Manifest output path")
    parser.add_argument("--raw-dir", help="Raw response output directory")
    parser.add_argument("--api-key", help="API key override; takes precedence over env")
    parser.add_argument("--base-url", help="Base URL override, e.g. https://api.xiaomimimo.com/v1")
    parser.add_argument("--auth-mode", choices=["api-key", "bearer"], help="Authentication header mode; default api-key")
    parser.add_argument("--default-model", help="Default TTS model")
    parser.add_argument("--default-voice", help="Default preset voice")
    parser.add_argument("--default-format", help="Default output format: wav or pcm16")
    parser.add_argument("--default-style", help="Default style instruction")
    parser.add_argument("--timeout", type=int, help="HTTP timeout seconds")
    parser.add_argument("--retries", type=int, help="Retry count per segment")
    parser.add_argument("--sleep-between", type=float, help="Sleep seconds between successful calls")
    parser.add_argument("--min-chars", type=int, help="Validation min chars")
    parser.add_argument("--max-chars", type=int, help="Validation max chars")
    parser.add_argument("--stream", action="store_true", help="Enable streaming only for mimo-v2.5-tts preset segments; outputs WAV from 24kHz PCM16 chunks")
    parser.add_argument("--stream-all", action="store_true", help="Force compatibility streaming for all TTS models, including voicedesign/voiceclone")
    parser.add_argument("--dry-run", action="store_true", help="Validate and plan without API calls")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing audio files")
    parser.add_argument("--failed-only", action="store_true", help="Only rerun failed items from existing manifest")
    parser.add_argument("--strict", action="store_true", help="Treat validation warnings as errors")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop batch on first segment failure")
    parser.add_argument("--include-text-in-manifest", action="store_true", help="Include speech_text in manifest")
    parser.add_argument("--save-raw-response", action="store_true", help="Save raw API responses for debugging")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        return synthesize_batch(args)
    except Exception as exc:  # noqa: BLE001
        if args.verbose:
            traceback.print_exc()
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
