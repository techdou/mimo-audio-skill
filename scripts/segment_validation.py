#!/usr/bin/env python3
"""Validation helpers for MiMo lecture TTS segments."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SUPPORTED_TTS_MODELS = {
    "mimo-v2.5-tts",
    "mimo-v2.5-tts-voicedesign",
    "mimo-v2.5-tts-voiceclone",
}
SUPPORTED_ASR_MODEL = "mimo-v2.5-asr"
SUPPORTED_TTS_OUTPUT_FORMATS = {"wav", "pcm16"}
PRESET_VOICES = {"mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"}
VOICE_SAMPLE_SUFFIXES = {".wav", ".mp3"}
VALID_LANGUAGES = {"auto", "zh", "en"}

HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
MARKDOWN_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
FILENAME_RE = re.compile(r"^[a-zA-Z0-9._-]+\.wav$")
DATA_AUDIO_RE = re.compile(r"^data:audio/(wav|mpeg|mp3);base64,", re.IGNORECASE)
VAGUE_VOICE_WORDS = ("普通的", "正常的", "随便", "都可以", "默认", "外国的")
AUDIO_TAG_RE = re.compile(r"[\[（(][^\]\)）]{1,24}[\]\)）]")


@dataclass
class ValidationIssue:
    level: str  # error|warning
    index: Optional[int]
    field: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_segments_from_data(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        segments = data
    elif isinstance(data, dict) and isinstance(data.get("segments"), list):
        segments = data["segments"]
    else:
        raise ValueError("segments JSON must be either a list or an object with a 'segments' list")
    return segments


def _has_markdown_table(text: str) -> bool:
    lines = text.splitlines()
    if any(MARKDOWN_TABLE_SEP_RE.match(line) for line in lines):
        return True
    pipe_lines = [line for line in lines if line.count("|") >= 2]
    return len(pipe_lines) >= 2


def _audio_obj(segment: Dict[str, Any]) -> Dict[str, Any]:
    audio = segment.get("audio")
    return audio if isinstance(audio, dict) else {}


def _word_like_sentence_count(text: str) -> int:
    parts = re.split(r"[。！？!?；;\n]+", text.strip())
    return len([p for p in parts if p.strip()])


def validate_segment(
    segment: Dict[str, Any],
    fallback_index: int,
    *,
    min_chars: int = 20,
    max_chars: int = 1000,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    raw_index = segment.get("index", fallback_index)
    try:
        index = int(raw_index)
    except (TypeError, ValueError):
        index = fallback_index
        issues.append(ValidationIssue("error", fallback_index, "index", "index must be a positive integer"))

    if index <= 0:
        issues.append(ValidationIssue("error", index, "index", "index must be greater than 0"))

    title = str(segment.get("title") or "").strip()
    if not title:
        issues.append(ValidationIssue("error", index, "title", "title is required"))

    audio_obj = _audio_obj(segment)
    model = str(segment.get("model") or "mimo-v2.5-tts").strip()
    fmt = str(segment.get("format") or audio_obj.get("format") or "wav").strip().lower()
    stream = bool(segment.get("stream", False))

    if model not in SUPPORTED_TTS_MODELS:
        issues.append(ValidationIssue("error", index, "model", f"unsupported TTS model: {model}"))

    if fmt not in SUPPORTED_TTS_OUTPUT_FORMATS:
        issues.append(ValidationIssue("error", index, "format", f"unsupported TTS output format: {fmt}; use wav or pcm16"))

    if stream and fmt != "pcm16":
        issues.append(ValidationIssue("error", index, "format", "streaming TTS must use format=pcm16"))
    if not stream and fmt == "pcm16":
        issues.append(ValidationIssue("warning", index, "format", "pcm16 is intended for streaming output; use wav for normal batch synthesis"))
    if stream and model != "mimo-v2.5-tts":
        issues.append(ValidationIssue("warning", index, "stream", "voicedesign/voiceclone streaming currently behaves as compatibility mode; preset TTS is the low-latency streaming path"))

    speech_text = str(segment.get("speech_text") or segment.get("content") or "").strip()
    if not speech_text:
        issues.append(ValidationIssue("error", index, "speech_text", "speech_text is required and becomes assistant.content"))
    else:
        length = len(speech_text)
        if length < min_chars:
            issues.append(ValidationIssue("warning", index, "speech_text", f"speech_text is short ({length} chars); consider merging it with adjacent content"))
        if length > max_chars:
            issues.append(ValidationIssue("warning", index, "speech_text", f"speech_text is long ({length} chars); consider splitting it before TTS"))
        if HTML_TAG_RE.search(speech_text):
            issues.append(ValidationIssue("warning", index, "speech_text", "speech_text appears to contain raw HTML tags"))
        if "```" in speech_text:
            issues.append(ValidationIssue("warning", index, "speech_text", "speech_text contains Markdown code fences; confirm code should be narrated"))
        if URL_RE.search(speech_text):
            issues.append(ValidationIssue("warning", index, "speech_text", "speech_text contains raw URLs; rewrite them for spoken narration"))
        if _has_markdown_table(speech_text):
            issues.append(ValidationIssue("warning", index, "speech_text", "speech_text appears to contain a Markdown table; summarize it before narration"))
        if len(re.findall(r"[，,]", speech_text)) > 12 and _word_like_sentence_count(speech_text) <= 2:
            issues.append(ValidationIssue("warning", index, "speech_text", "speech_text may contain overly long sentences; split for better narration rhythm"))

    filename = str(segment.get("filename") or "").strip()
    if not filename:
        issues.append(ValidationIssue("warning", index, "filename", "filename is empty; batch script will auto-generate one"))
    else:
        if " " in filename:
            issues.append(ValidationIssue("warning", index, "filename", "filename contains spaces; use underscores or hyphens"))
        if CJK_RE.search(filename):
            issues.append(ValidationIssue("warning", index, "filename", "filename contains Chinese characters; use ASCII for portability"))
        if not FILENAME_RE.match(filename):
            issues.append(ValidationIssue("warning", index, "filename", "filename should match ^[a-zA-Z0-9._-]+.wav; pcm16 stream chunks are written into a WAV container"))
        # This skill writes normal WAV responses and streaming PCM16 chunks into a WAV container.
        if not filename.lower().endswith(".wav"):
            issues.append(ValidationIssue("warning", index, "filename", "filename suffix should be .wav; format=pcm16 describes API chunks, not the output container"))

    voice = segment.get("voice", audio_obj.get("voice"))
    voice_design_prompt = str(segment.get("voice_design_prompt") or segment.get("voice_description") or "").strip()
    style_instruction = str(segment.get("style_instruction") or "").strip()
    voice_sample_path = str(segment.get("voice_sample_path") or audio_obj.get("voice_sample_path") or "").strip()

    if model == "mimo-v2.5-tts-voicedesign":
        if voice:
            issues.append(ValidationIssue("warning", index, "voice", "voicedesign does not use preset voice; remove voice/audio.voice"))
        if not voice_design_prompt:
            issues.append(ValidationIssue("warning", index, "voice_design_prompt", "voicedesign should include a 1-4 sentence voice_design_prompt"))
        if voice_design_prompt:
            if _word_like_sentence_count(voice_design_prompt) > 4 or len(voice_design_prompt) > 350:
                issues.append(ValidationIssue("warning", index, "voice_design_prompt", "voice_design_prompt should usually be concise: 1-4 sentences"))
            if any(word in voice_design_prompt for word in VAGUE_VOICE_WORDS):
                issues.append(ValidationIssue("warning", index, "voice_design_prompt", "voice_design_prompt contains vague terms; describe age, timbre, tempo, emotion, or role more concretely"))
    elif model == "mimo-v2.5-tts-voiceclone":
        voice_value = str(voice or "").strip()
        if voice_sample_path:
            suffix = Path(voice_sample_path).suffix.lower()
            if suffix not in VOICE_SAMPLE_SUFFIXES:
                issues.append(ValidationIssue("error", index, "voice_sample_path", "voice sample must be .wav or .mp3"))
        elif not voice_value:
            issues.append(ValidationIssue("error", index, "voice", "voiceclone requires voice data URI or voice_sample_path"))
        elif not DATA_AUDIO_RE.match(voice_value):
            issues.append(ValidationIssue("error", index, "voice", "voiceclone voice must be data:audio/wav;base64,... or data:audio/mpeg;base64,..."))
    else:
        if voice and str(voice) not in PRESET_VOICES:
            issues.append(ValidationIssue("warning", index, "voice", f"unknown preset voice '{voice}'; known voices: {', '.join(sorted(PRESET_VOICES))}"))
        if not voice:
            issues.append(ValidationIssue("warning", index, "voice", "preset TTS segment has no voice; default voice will be used"))

    if style_instruction and AUDIO_TAG_RE.search(style_instruction):
        issues.append(ValidationIssue("warning", index, "style_instruction", "audio tags belong in assistant speech_text/prefix tags, not only in style_instruction"))

    return issues


def validate_segments(
    segments: Iterable[Dict[str, Any]],
    *,
    min_chars: int = 20,
    max_chars: int = 1000,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    seen_filenames = set()
    seen_indices = set()
    count = 0

    for fallback_index, segment in enumerate(segments, start=1):
        count += 1
        if not isinstance(segment, dict):
            issues.append(ValidationIssue("error", fallback_index, "segment", "segment must be a JSON object"))
            continue
        raw_index = segment.get("index", fallback_index)
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = fallback_index
        if index in seen_indices:
            issues.append(ValidationIssue("warning", index, "index", "duplicate index"))
        seen_indices.add(index)

        filename = str(segment.get("filename") or "").strip()
        if filename:
            lowered = filename.lower()
            if lowered in seen_filenames:
                issues.append(ValidationIssue("error", index, "filename", "duplicate filename"))
            seen_filenames.add(lowered)

        issues.extend(validate_segment(segment, fallback_index, min_chars=min_chars, max_chars=max_chars))

    if count == 0:
        issues.append(ValidationIssue("error", None, "segments", "segments list is empty"))
    return issues


def summarize_issues(issues: Iterable[ValidationIssue]) -> Dict[str, int]:
    materialized = list(issues)
    return {
        "errors": sum(1 for i in materialized if i.level == "error"),
        "warnings": sum(1 for i in materialized if i.level == "warning"),
        "total": len(materialized),
    }
