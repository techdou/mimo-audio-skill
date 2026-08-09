from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from voice_profiles import apply_profile, find_profile, list_profiles, validate_profile


class ProfileTests(unittest.TestCase):
    def test_builtin_profiles_validate_without_errors(self):
        profiles = [p for p in list_profiles() if p.get("source") == "builtin"]
        self.assertGreaterEqual(len(profiles), 4)
        for profile in profiles:
            errors = [i for i in validate_profile(profile) if i["level"] == "error"]
            self.assertEqual(errors, [], f"{profile['name']} has validation errors: {errors}")

    def test_personal_clone_profile_exists(self):
        profile = find_profile("douge-lecture")
        self.assertEqual(profile["model"], "mimo-v2.5-tts-voiceclone")
        self.assertTrue(profile.get("voice_sample_path"))
        errors = [i for i in validate_profile(profile) if i["level"] == "error"]
        self.assertEqual(errors, [])

    def test_apply_profile_fills_missing_fields_only(self):
        profile = find_profile("lecture-natural")
        segments = [
            {
                "index": 1,
                "title": "t1",
                "filename": "01.wav",
                "speech_text": "这是一段测试文本，用于确认模板注入行为。",
            },
            {
                "index": 2,
                "title": "t2",
                "filename": "02.wav",
                "model": "mimo-v2.5-tts-voicedesign",
                "voice_design_prompt": "自定义音色，不应被覆盖。",
                "speech_text": "这是第二段测试文本，用于确认显式字段不被覆盖。",
            },
        ]
        apply_profile(profile, segments)
        self.assertEqual(segments[0]["model"], "mimo-v2.5-tts")
        self.assertEqual(segments[0]["voice"], "冰糖")
        self.assertEqual(segments[0]["style_instruction"], profile["style_instruction"])
        self.assertEqual(segments[1]["model"], "mimo-v2.5-tts-voicedesign")
        self.assertEqual(segments[1]["voice_design_prompt"], "自定义音色，不应被覆盖。")

    def test_apply_profile_overwrite(self):
        profile = find_profile("lecture-natural")
        segments = [
            {
                "index": 1,
                "title": "t",
                "filename": "01.wav",
                "model": "mimo-v2.5-tts-voicedesign",
                "speech_text": "覆盖模式测试。",
            }
        ]
        apply_profile(profile, segments, overwrite=True)
        self.assertEqual(segments[0]["model"], "mimo-v2.5-tts")


if __name__ == "__main__":
    unittest.main()
