from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from segment_validation import validate_segments, summarize_issues
from mimo_tts_batch import safe_filename


class ValidationTests(unittest.TestCase):
    def test_valid_segment_has_no_errors(self):
        issues = validate_segments([
            {
                "index": 1,
                "title": "导入",
                "filename": "01_intro.wav",
                "model": "mimo-v2.5-tts",
                "voice": "冰糖",
                "format": "wav",
                "speech_text": "同学们好，今天我们来学习人工智能工具的基本使用方法。"
            }
        ])
        summary = summarize_issues(issues)
        self.assertEqual(summary["errors"], 0)

    def test_voiceclone_requires_sample(self):
        issues = validate_segments([
            {
                "index": 1,
                "title": "clone",
                "filename": "01_clone.wav",
                "model": "mimo-v2.5-tts-voiceclone",
                "speech_text": "这是一段音色克隆测试文本。"
            }
        ])
        self.assertGreater(summarize_issues(issues)["errors"], 0)

    def test_safe_filename_wav_for_pcm16(self):
        self.assertTrue(safe_filename("demo.pcm16", 1, "pcm16").endswith(".wav"))


if __name__ == "__main__":
    unittest.main()
