#!/usr/bin/env python3
"""Manage reusable MiMo voice/style profiles.

A profile bundles model + voice selection (preset / voicedesign / voiceclone)
with a style instruction and optional audio tags, so the same TTS pipeline can
be reused across lecture, novel narration, podcast, short-video and personal
clone scenarios without repeating per-segment fields.

Profile locations (personal takes precedence over built-in):
  <skill>/profiles/*.json           personal profiles (gitignored)
  <skill>/templates/profiles/*.json built-in profiles
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SKILL_ROOT = Path(__file__).resolve().parents[1]
PERSONAL_PROFILE_DIR = SKILL_ROOT / "profiles"
BUILTIN_PROFILE_DIR = SKILL_ROOT / "templates" / "profiles"

SUPPORTED_MODELS = {
    "mimo-v2.5-tts",
    "mimo-v2.5-tts-voicedesign",
    "mimo-v2.5-tts-voiceclone",
}
PRESET_VOICES = {"mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"}
VAGUE_VOICE_WORDS = ("普通的", "正常的", "随便", "都可以", "默认", "外国的")
VOICE_SAMPLE_SUFFIXES = {".wav", ".mp3"}
DATA_AUDIO_RE = re.compile(r"^data:audio/(wav|mpeg|mp3);base64,", re.IGNORECASE)


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"profile must be a JSON object: {path}")
    return data


def profile_dirs() -> List[Path]:
    return [PERSONAL_PROFILE_DIR, BUILTIN_PROFILE_DIR]


def list_profiles() -> List[Dict[str, Any]]:
    profiles: List[Dict[str, Any]] = []
    for directory in profile_dirs():
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            data = _load_json(path)
            data.setdefault("name", path.stem)
            data["source"] = "personal" if directory == PERSONAL_PROFILE_DIR else "builtin"
            profiles.append(data)
    return profiles


def find_profile(name: Optional[str] = None, profile_file: Optional[str] = None) -> Dict[str, Any]:
    if profile_file:
        path = Path(profile_file)
        if not path.exists():
            raise FileNotFoundError(f"profile file not found: {path}")
        return _load_json(path)
    if not name:
        raise ValueError("either --profile NAME or --profile-file PATH is required")
    for directory in profile_dirs():
        path = directory / f"{name}.json"
        if path.exists():
            return _load_json(path)
    raise FileNotFoundError(f"profile not found: {name} (searched {PERSONAL_PROFILE_DIR} and {BUILTIN_PROFILE_DIR})")


def validate_profile(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    name = str(profile.get("name") or "").strip()
    if not name:
        issues.append({"level": "error", "field": "name", "message": "profile name is required"})

    model = str(profile.get("model") or "").strip()
    if not model:
        issues.append({"level": "error", "field": "model", "message": "profile model is required"})
    elif model not in SUPPORTED_MODELS:
        issues.append({"level": "error", "field": "model", "message": f"unsupported model: {model}"})

    voice = profile.get("voice")
    voice_design_prompt = str(profile.get("voice_design_prompt") or "").strip()
    voice_sample_path = str(profile.get("voice_sample_path") or "").strip()

    if model == "mimo-v2.5-tts-voicedesign":
        if voice:
            issues.append({"level": "warning", "field": "voice", "message": "voicedesign does not use preset voice; remove voice"})
        if not voice_design_prompt:
            issues.append({"level": "warning", "field": "voice_design_prompt", "message": "voicedesign should include a 1-4 sentence voice_design_prompt"})
        elif any(word in voice_design_prompt for word in VAGUE_VOICE_WORDS):
            issues.append({"level": "warning", "field": "voice_design_prompt", "message": "voice_design_prompt contains vague terms; describe age, timbre, tempo, emotion or role concretely"})
    elif model == "mimo-v2.5-tts-voiceclone":
        if voice_sample_path:
            if Path(voice_sample_path).suffix.lower() not in VOICE_SAMPLE_SUFFIXES:
                issues.append({"level": "error", "field": "voice_sample_path", "message": "voice sample must be .wav or .mp3"})
            elif not Path(voice_sample_path).exists():
                issues.append({"level": "warning", "field": "voice_sample_path", "message": f"voice sample not found on disk: {voice_sample_path}"})
        elif not voice or not DATA_AUDIO_RE.match(str(voice)):
            issues.append({"level": "error", "field": "voice_sample_path", "message": "voiceclone requires voice_sample_path or a data:audio/...;base64 voice"})
    else:
        if voice and str(voice) not in PRESET_VOICES:
            issues.append({"level": "warning", "field": "voice", "message": f"unknown preset voice '{voice}'; known voices: {', '.join(sorted(PRESET_VOICES))}"})

    style = str(profile.get("style_instruction") or "").strip()
    if not style:
        issues.append({"level": "warning", "field": "style_instruction", "message": "profile has no style_instruction; segments will fall back to defaults"})
    return issues


def apply_profile(profile: Dict[str, Any], segments: List[Dict[str, Any]], overwrite: bool = False) -> List[Dict[str, Any]]:
    """Fill profile fields into segments that do not already define them."""
    model = str(profile.get("model") or "").strip()
    voice = profile.get("voice")
    voice_design_prompt = str(profile.get("voice_design_prompt") or "").strip()
    voice_sample_path = str(profile.get("voice_sample_path") or "").strip()
    style_instruction = str(profile.get("style_instruction") or "").strip()
    speech_prefix_tags = profile.get("speech_prefix_tags")

    for segment in segments:
        if model and (overwrite or not str(segment.get("model") or "").strip()):
            segment["model"] = model
        if voice and (overwrite or "voice" not in segment):
            segment["voice"] = voice
        if voice_design_prompt and (overwrite or not str(segment.get("voice_design_prompt") or "").strip()):
            segment["voice_design_prompt"] = voice_design_prompt
        if voice_sample_path and (overwrite or not str(segment.get("voice_sample_path") or "").strip()):
            segment["voice_sample_path"] = voice_sample_path
        if style_instruction and (overwrite or not str(segment.get("style_instruction") or "").strip()):
            segment["style_instruction"] = style_instruction
        if speech_prefix_tags and (overwrite or "speech_prefix_tags" not in segment):
            segment["speech_prefix_tags"] = speech_prefix_tags
    return segments


def _print_profiles(profiles: List[Dict[str, Any]]) -> None:
    if not profiles:
        print("(no profiles found)")
        return
    for profile in profiles:
        model = str(profile.get("model") or "-")
        label = str(profile.get("label") or profile["name"])
        print(f"{profile['name']:<24} [{profile.get('source', '?')}] {model}")
        print(f"    {label}: {str(profile.get('description') or '').strip()}")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage reusable MiMo voice/style profiles")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("list", help="List all profiles (personal first, then built-in)")

    p_get = sub.add_parser("get", help="Show one profile")
    p_get.add_argument("name", help="Profile name")

    p_validate = sub.add_parser("validate", help="Validate a profile")
    p_validate.add_argument("name", help="Profile name")
    p_validate.add_argument("--profile-file", help="Validate a profile JSON file instead")

    p_create = sub.add_parser("create", help="Create a personal profile in <skill>/profiles/")
    p_create.add_argument("--name", required=True, help="Profile name (filename stem)")
    p_create.add_argument("--json", help="Full profile JSON string")
    p_create.add_argument("--file", help="Copy an existing profile JSON into the personal directory")

    p_apply = sub.add_parser("apply", help="Fill missing segment fields from a profile")
    p_apply.add_argument("--profile", help="Profile name")
    p_apply.add_argument("--profile-file", help="Profile JSON file path")
    p_apply.add_argument("--segments", required=True, help="Input segments JSON")
    p_apply.add_argument("--output", required=True, help="Output segments JSON")
    p_apply.add_argument("--overwrite", action="store_true", help="Override existing per-segment fields too")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.action == "list":
            _print_profiles(list_profiles())
            return 0

        if args.action == "get":
            profile = find_profile(args.name)
            print(json.dumps(profile, ensure_ascii=False, indent=2))
            return 0

        if args.action == "validate":
            profile = find_profile(args.name, args.profile_file)
            issues = validate_profile(profile)
            for issue in issues:
                print(f"[{issue['level'].upper()}] {issue['field']}: {issue['message']}")
            errors = sum(1 for i in issues if i["level"] == "error")
            print(f"[VALIDATE] errors={errors} warnings={sum(1 for i in issues if i['level'] == 'warning')}")
            return 1 if errors else 0

        if args.action == "create":
            PERSONAL_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            if args.json:
                profile = json.loads(args.json)
                if not isinstance(profile, dict):
                    raise ValueError("--json must be a JSON object")
            elif args.file:
                profile = _load_json(Path(args.file))
            else:
                raise ValueError("create requires --json or --file")
            profile["name"] = args.name
            issues = validate_profile(profile)
            for issue in issues:
                print(f"[{issue['level'].upper()}] {issue['field']}: {issue['message']}")
            if any(i["level"] == "error" for i in issues):
                raise ValueError("profile validation failed; fix errors before saving")
            target = PERSONAL_PROFILE_DIR / f"{args.name}.json"
            with target.open("w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
            print(f"[DONE] personal profile written: {target}")
            return 0

        if args.action == "apply":
            profile = find_profile(args.profile, args.profile_file)
            with Path(args.segments).open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                segments = data
            elif isinstance(data, dict) and isinstance(data.get("segments"), list):
                segments = data["segments"]
            else:
                raise ValueError("segments JSON must be a list or an object with a 'segments' list")
            apply_profile(profile, segments, overwrite=args.overwrite)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[DONE] profile '{profile.get('name', '?')}' applied to {len(segments)} segment(s): {output}")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
