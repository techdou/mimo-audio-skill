#!/usr/bin/env python3
"""Shared helpers for MiMo audio scripts.

Standard-library only helpers for OpenAI-compatible MiMo /chat/completions calls.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_ENDPOINT_PATH = "/chat/completions"
AUDIO_SAMPLE_MAX_BASE64_BYTES = 10 * 1024 * 1024
SUPPORTED_AUDIO_SAMPLE_SUFFIXES = {".wav", ".mp3"}
SUPPORTED_AUDIO_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}


class MiMoHTTPError(RuntimeError):
    """HTTP error that preserves status code and Retry-After header."""

    def __init__(self, status_code: int, body: str, retry_after: Optional[float] = None):
        super().__init__(f"HTTP {status_code}: {body[:1000]}")
        self.status_code = status_code
        self.body = body
        self.retry_after = retry_after


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def dump_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def resolve_api_key(args: Any, config: Dict[str, Any]) -> Optional[str]:
    env_name = str(config.get("api_key_env", "MIMO_API_KEY"))
    return getattr(args, "api_key", None) or os.getenv(env_name) or config.get("api_key")


def resolve_base_url(args: Any, config: Dict[str, Any]) -> str:
    env_name = str(config.get("base_url_env", "MIMO_BASE_URL"))
    base_url = (
        getattr(args, "base_url", None)
        or os.getenv(env_name)
        or config.get("default_base_url")
        or DEFAULT_BASE_URL
    )
    return str(base_url).rstrip("/")


def endpoint_from_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + DEFAULT_ENDPOINT_PATH


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        seconds = float(value)
        return seconds if seconds >= 0 else None
    except ValueError:
        return None


def build_auth_headers(api_key: str, auth_mode: str = "api-key") -> Dict[str, str]:
    """Build MiMo authentication headers.

    Official examples use either `api-key: <key>` or OpenAI-style
    `Authorization: Bearer <key>`. This helper intentionally sends only
    one authentication mode at a time to avoid ambiguous credentials.
    """
    mode = (auth_mode or "api-key").strip().lower()
    if mode in {"api-key", "apikey", "api_key"}:
        return {"api-key": api_key}
    if mode in {"bearer", "authorization"}:
        return {"Authorization": f"Bearer {api_key}"}
    raise ValueError("auth_mode must be 'api-key' or 'bearer'")


def post_json(url: str, api_key: str, payload: Dict[str, Any], timeout: int = 120, auth_mode: str = "api-key") -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            **build_auth_headers(api_key, auth_mode),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise MiMoHTTPError(exc.code, body, parse_retry_after(exc.headers.get("Retry-After"))) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"response is not valid JSON: {exc}") from exc


def stream_json_events(url: str, api_key: str, payload: Dict[str, Any], timeout: int = 120, auth_mode: str = "api-key") -> Generator[Dict[str, Any], None, None]:
    """Yield JSON payloads from an SSE-style OpenAI-compatible stream."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **build_auth_headers(api_key, auth_mode),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            buffer = ""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        value = line[len("data:"):].strip()
                        if value == "[DONE]":
                            return
                        try:
                            yield json.loads(value)
                        except json.JSONDecodeError:
                            continue
            # Some compatible endpoints return a single JSON object despite stream=True.
            leftover = buffer.strip()
            if leftover.startswith("{"):
                try:
                    yield json.loads(leftover)
                except json.JSONDecodeError:
                    pass
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise MiMoHTTPError(exc.code, body, parse_retry_after(exc.headers.get("Retry-After"))) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error: {exc}") from exc


def data_url_from_audio_file(path: Path, *, max_base64_bytes: int = AUDIO_SAMPLE_MAX_BASE64_BYTES) -> str:
    if not path.exists():
        raise FileNotFoundError(f"audio file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_AUDIO_SAMPLE_SUFFIXES:
        raise ValueError(f"unsupported audio format {suffix}; only .wav and .mp3 are supported")
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("utf-8")
    if len(encoded.encode("utf-8")) > max_base64_bytes:
        raise ValueError(
            f"base64-encoded audio sample exceeds {max_base64_bytes} bytes; "
            "shorten/compress the mp3/wav sample"
        )
    mime = SUPPORTED_AUDIO_MIME.get(suffix) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return f"data:{mime};base64,{encoded}"


def strip_data_uri_prefix(data: str) -> str:
    data = data.strip()
    if data.startswith("data:") and "," in data:
        return data.split(",", 1)[1]
    return data


def extract_choice_message(response: Dict[str, Any]) -> Dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("response does not contain choices[0].message") from exc
    if not isinstance(message, dict):
        raise ValueError("choices[0].message is not an object")
    return message


def extract_tts_audio_base64(response: Dict[str, Any]) -> str:
    message = extract_choice_message(response)
    try:
        data = message["audio"]["data"]
    except (KeyError, TypeError) as exc:
        raise ValueError("response does not contain choices[0].message.audio.data") from exc
    if not isinstance(data, str) or not data.strip():
        raise ValueError("audio data is empty or not a string")
    return strip_data_uri_prefix(data)


def extract_text_from_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return ""


def extract_asr_text(response: Dict[str, Any]) -> str:
    """Best-effort ASR text extractor, preserving raw JSON separately if needed."""
    message = extract_choice_message(response)
    content = message.get("content")
    text = extract_text_from_message_content(content)
    if text:
        return text
    for key in ("text", "transcript", "transcription"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Last-resort patterns for provider-specific payloads.
    for key in ("asr", "audio", "result"):
        obj = message.get(key)
        if isinstance(obj, dict):
            for nested_key in ("text", "transcript", "transcription", "content"):
                value = obj.get(nested_key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def with_retries(callable_obj, *, retries: int, sleep_cap: float = 30.0, verbose: bool = False):
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 2):
        try:
            return callable_obj()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt > retries:
                break
            retry_after = getattr(exc, "retry_after", None)
            if isinstance(exc, MiMoHTTPError) and exc.status_code == 429 and retry_after is not None:
                sleep_seconds = float(retry_after)
            elif isinstance(exc, MiMoHTTPError) and exc.status_code >= 500:
                sleep_seconds = min(2 ** attempt, sleep_cap)
            else:
                sleep_seconds = min(2 ** attempt, sleep_cap)
            if verbose:
                print(f"[WARN] attempt {attempt} failed; retrying in {sleep_seconds:.1f}s: {exc}")
            time.sleep(sleep_seconds)
    assert last_exc is not None
    raise last_exc
