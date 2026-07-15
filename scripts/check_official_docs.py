#!/usr/bin/env python3
"""Check whether local MiMo rules are still in sync with official docs and API.

Two complementary checks:
  1. API layer: GET /v1/models — are the models this skill uses still alive?
  2. Doc layer:  fetch the .md source via llms.txt — extract preset voices,
     languages, formats and diff against templates/known_rules.json.

Design: stdlib-only. The .md sources contain HTML tables; we parse them with
html.parser (standard library), not beautifulsoup4.

Exit codes:
  0  no issues, or only INFO-level
  1  WARNING or CRITICAL found (when --fail-on warning, the default)
  2  could not complete the check (network error, config missing, etc.)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Make sibling module importable regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mimo_audio_common import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_DOC_CACHE_DIR,
    DocCache,
    MiMoHTTPError,
    fetch_text,
    list_models,
    load_json_file,
    resolve_api_key,
    resolve_base_url,
)

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KNOWN_RULES = SKILL_ROOT / "templates" / "known_rules.json"
DEFAULT_CONFIG = SKILL_ROOT / "templates" / "config.example.json"


# ---- severity constants ----
CRITICAL = "CRITICAL"
WARNING = "WARNING"
INFO = "INFO"


# ---------------------------------------------------------------------------
# HTML table extraction — pull text out of <td> cells from the .md HTML tables.
# ---------------------------------------------------------------------------

class _TableTextExtractor(HTMLParser):
    """Collect rows from the first <table> whose cells contain given keywords."""

    def __init__(self, keywords: Set[str]):
        super().__init__()
        self._keywords = keywords
        self._in_table = False
        self._in_cell = False
        self._current_row: List[str] = []
        self._current_cell: List[str] = []
        self._matched_rows: List[List[str]] = []
        self._row_has_keyword = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._current_row = []
            self._row_has_keyword = False
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._in_table = False
        elif self._in_table and tag == "tr":
            if self._row_has_keyword:
                self._matched_rows.append(self._current_row)
        elif self._in_table and tag in ("td", "th"):
            cell_text = "".join(self._current_cell).strip()
            cell_text = re.sub(r"`([^`]+)`", r"\1", cell_text)  # strip backticks
            self._current_row.append(cell_text)
            joined = "".join(cell_text.lower())
            if any(kw.lower() in joined for kw in self._keywords):
                self._row_has_keyword = True
            self._in_cell = False

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data)

    @property
    def rows(self) -> List[List[str]]:
        return self._matched_rows


def _extract_code_fenced_values(md: str, pattern: str) -> List[str]:
    """Extract values from inline-code spans in the .md body matching a regex."""
    # The .md sources use backtick-wrapped values like `mimo-v2.5-tts`.
    return re.findall(pattern, md)


# ---------------------------------------------------------------------------
# Rule extraction from official .md text
# ---------------------------------------------------------------------------

def extract_tts_rules(md_text: str) -> Dict[str, Any]:
    """Extract preset voices and model IDs from TTS doc markdown.

    The .md source has two tables: a model table and a preset-voice table.
    Voice IDs appear in the voice table's second column as either backtick-
    wrapped code spans (e.g. `mimo_default`) or bare CJK words (e.g. 冰糖).
    We rely on the known, stable voice-name set rather than generic table
    parsing, because the table headers themselves contain false positives
    like 'Voice', 'Function', 'Gender'.
    """
    model_ids = sorted(set(re.findall(r"`(mimo-v2\.5-tts[a-z\-]*)`", md_text)))
    # Voice names: the official set is a fixed vocabulary. Match each as a
    # whole word so that partial substrings don't cause false positives.
    voice_pattern = re.compile(
        r"`?(mimo_default|冰糖|茉莉|苏打|白桦|Mia|Chloe|Milo|Dean)`?"
    )
    voices: Set[str] = set()
    for m in voice_pattern.finditer(md_text):
        voices.add(m.group(1))
    return {
        "models": model_ids,
        "preset_voices": sorted(voices),
    }


def extract_asr_rules(md_text: str) -> Dict[str, Any]:
    """Extract language list and model ID from ASR doc markdown."""
    model_ids = sorted(set(re.findall(r"`(mimo-v2\.5-asr)`", md_text)))
    # Language values appear as auto/zh/en in code spans or prose.
    langs: Set[str] = set()
    for m in re.findall(r"`(auto|zh|en)`", md_text):
        langs.add(m)
    return {
        "models": model_ids,
        "languages": sorted(langs),
    }


# ---------------------------------------------------------------------------
# Diff logic
# ---------------------------------------------------------------------------

def _diff_lists(name: str, local: List[str], remote: List[str], section: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    local_set = set(local)
    remote_set = set(remote)
    missing = local_set - remote_set  # in local but not in remote = possibly removed
    added = remote_set - local_set    # in remote but not in local = newly available
    for item in sorted(missing):
        issues.append({
            "severity": WARNING,
            "section": section,
            "message": f"{name} '{item}' is in local rules but NOT found in official docs. It may have been removed or renamed.",
        })
    for item in sorted(added):
        issues.append({
            "severity": INFO,
            "section": section,
            "message": f"{name} '{item}' appears in official docs but is not in local rules. Consider adding it.",
        })
    return issues


def check_docs(known_rules: Dict[str, Any], cache: DocCache, ttl_hours: float, force_refresh: bool) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Fetch official .md sources and diff against local rules. Returns (issues, extracted)."""
    issues: List[Dict[str, str]] = []
    extracted: Dict[str, Any] = {"tts": {}, "asr": {}}
    urls = known_rules.get("source_urls", {})

    # --- TTS ---
    tts_url = urls.get("tts_md")
    if tts_url:
        md_text = cache.get(tts_url, ttl_hours) if not force_refresh else None
        if md_text is None:
            try:
                md_text = fetch_text(tts_url)
                cache.set(tts_url, md_text)
            except Exception as exc:
                issues.append({"severity": WARNING, "section": "tts", "message": f"Could not fetch TTS doc ({tts_url}): {exc}"})
                md_text = ""
        if md_text:
            tts_remote = extract_tts_rules(md_text)
            extracted["tts"] = tts_remote
            local = known_rules.get("tts", {})
            issues += _diff_lists("TTS model", local.get("models", []), tts_remote.get("models", []), "tts")
            issues += _diff_lists("Preset voice", local.get("preset_voices", []), tts_remote.get("preset_voices", []), "tts")

    # --- ASR ---
    asr_url = urls.get("asr_md")
    if asr_url:
        md_text = cache.get(asr_url, ttl_hours) if not force_refresh else None
        if md_text is None:
            try:
                md_text = fetch_text(asr_url)
                cache.set(asr_url, md_text)
            except Exception as exc:
                issues.append({"severity": WARNING, "section": "asr", "message": f"Could not fetch ASR doc ({asr_url}): {exc}"})
                md_text = ""
        if md_text:
            asr_remote = extract_asr_rules(md_text)
            extracted["asr"] = asr_remote
            local = known_rules.get("asr", {})
            issues += _diff_lists("ASR model", local.get("models", []), asr_remote.get("models", []), "asr")
            issues += _diff_lists("ASR language", local.get("languages", []), asr_remote.get("languages", []), "asr")

    return issues, extracted


def check_models(api_key: Optional[str], base_url: str, auth_mode: str, known_rules: Dict[str, Any]) -> Tuple[List[Dict[str, str]], List[str]]:
    """GET /v1/models and verify skill's models still exist. Returns (issues, remote_model_ids)."""
    issues: List[Dict[str, str]] = []
    if not api_key:
        issues.append({"severity": INFO, "section": "models", "message": "No API key available; skipping /v1/models check."})
        return issues, []
    try:
        remote_ids = list_models(api_key, base_url, auth_mode)
    except MiMoHTTPError as exc:
        issues.append({"severity": WARNING, "section": "models", "message": f"/v1/models returned HTTP {exc.status_code}: {exc.body[:200]}"})
        return issues, []
    except Exception as exc:
        issues.append({"severity": WARNING, "section": "models", "message": f"Could not query /v1/models: {exc}"})
        return issues, []
    remote_set = set(remote_ids)
    # All models this skill depends on.
    expected: List[str] = []
    expected += known_rules.get("tts", {}).get("models", [])
    expected += known_rules.get("asr", {}).get("models", [])
    for model_id in expected:
        if model_id not in remote_set:
            issues.append({
                "severity": CRITICAL,
                "section": "models",
                "message": f"Model '{model_id}' is used by this skill but NOT listed in /v1/models. It may have been deprecated or renamed.",
            })
    return issues, remote_ids


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}


def format_text(issues: List[Dict[str, str]], extracted: Dict[str, Any], remote_models: List[str]) -> str:
    if not issues:
        lines = ["[OK] Local rules match official docs. No issues found."]
    else:
        lines = [f"[CHECK] {len(issues)} issue(s) found:"]
        for issue in sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i["severity"], 9)):
            lines.append(f"  [{issue['severity']}] ({issue['section']}) {issue['message']}")
    if remote_models:
        lines.append("")
        lines.append(f"Remote /v1/models ({len(remote_models)}): {', '.join(sorted(remote_models))}")
    if extracted.get("tts"):
        t = extracted["tts"]
        lines.append(f"TTS remote voices ({len(t.get('preset_voices', []))}): {', '.join(t.get('preset_voices', []))}")
    if extracted.get("asr"):
        a = extracted["asr"]
        lines.append(f"ASR remote languages ({len(a.get('languages', []))}): {', '.join(a.get('languages', []))}")
    return "\n".join(lines)


def format_json(issues: List[Dict[str, str]], extracted: Dict[str, Any], remote_models: List[str]) -> str:
    return json.dumps({
        "issues": issues,
        "remote_models": remote_models,
        "extracted": extracted,
        "critical_count": sum(1 for i in issues if i["severity"] == CRITICAL),
        "warning_count": sum(1 for i in issues if i["severity"] == WARNING),
        "info_count": sum(1 for i in issues if i["severity"] == INFO),
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Public entry for other scripts to call
# ---------------------------------------------------------------------------

def run_check(
    config: Dict[str, Any],
    args: Any,
    *,
    known_rules_path: Optional[Path] = None,
    api_key_override: Optional[str] = None,
    base_url_override: Optional[str] = None,
) -> Tuple[List[Dict[str, str]], Dict[str, Any], List[str]]:
    """Run the full check. Returns (issues, extracted, remote_models).

    Designed to be called from mimo_tts_batch.py / mimo_asr_transcribe.py
    pre-flight hooks with minimal coupling.
    """
    rules_path = known_rules_path or Path(config.get("known_rules_path") or DEFAULT_KNOWN_RULES)
    if not rules_path.is_absolute():
        rules_path = SKILL_ROOT / rules_path
    known_rules = load_json_file(rules_path) if rules_path.exists() else {"tts": {}, "asr": {}, "source_urls": {}}

    ttl = float(config.get("doc_check_ttl_hours", 24))
    cache_dir = config.get("doc_check_cache_dir", DEFAULT_DOC_CACHE_DIR)
    cache = DocCache(cache_dir)
    force_refresh = bool(getattr(args, "force_refresh", False))

    doc_issues, extracted = check_docs(known_rules, cache, ttl, force_refresh)

    # API layer — only if we have a key and docs check didn't hard-fail.
    api_key = api_key_override or resolve_api_key(args, config)
    base_url = base_url_override or resolve_base_url(args, config)
    auth_mode = str(config.get("auth_mode", "api-key"))
    model_issues, remote_models = check_models(api_key, base_url, auth_mode, known_rules)

    return doc_issues + model_issues, extracted, remote_models


def has_blocking_issue(issues: List[Dict[str, str]], fail_on: str = WARNING) -> bool:
    """True if any issue is at or above the fail_on severity."""
    threshold = _SEVERITY_ORDER.get(fail_on, _SEVERITY_ORDER[WARNING])
    return any(_SEVERITY_ORDER.get(i["severity"], 9) <= threshold for i in issues)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check local MiMo rules against official docs and /v1/models.")
    p.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config JSON")
    p.add_argument("--known-rules", default=str(DEFAULT_KNOWN_RULES), help="Path to known_rules.json")
    p.add_argument("--api-key", default=None, help="API key (defaults to env/config)")
    p.add_argument("--base-url", default=None, help="Base URL override")
    p.add_argument("--auth-mode", default=None, choices=["api-key", "bearer"], help="Auth header mode")
    p.add_argument("--force-refresh", action="store_true", help="Ignore doc cache and re-fetch")
    p.add_argument("--format", default="text", choices=["text", "json"], help="Output format")
    p.add_argument("--fail-on", default="warning", choices=["critical", "warning", "info"], help="Exit non-zero at this severity")
    p.add_argument("--no-models", action="store_true", help="Skip /v1/models check (doc-only mode)")
    p.add_argument("--verbose", action="store_true")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    config_path = Path(args.config)
    config = load_json_file(config_path) if config_path.exists() else {}
    if args.known_rules:
        config["known_rules_path"] = args.known_rules
    if args.base_url:
        config["_cli_base_url"] = args.base_url
    # Resolve api_key/base_url via the shared helpers.
    class _Args:
        pass
    _a = _Args()
    _a.api_key = args.api_key
    _a.base_url = args.base_url
    _a.force_refresh = args.force_refresh

    rules_path = Path(args.known_rules) if args.known_rules else DEFAULT_KNOWN_RULES
    issues, extracted, remote_models = run_check(config, _a, known_rules_path=rules_path)

    if args.no_models:
        issues = [i for i in issues if i["section"] != "models"]
        remote_models = []

    if args.format == "json":
        print(format_json(issues, extracted, remote_models))
    else:
        print(format_text(issues, extracted, remote_models))

    fail_on = "warning" if args.fail_on == "warning" else ("critical" if args.fail_on == "critical" else "info")
    if has_blocking_issue(issues, fail_on):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
