from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_duration import wav_duration
from generate_srt import build_cues, write_srt, write_vtt
from generate_html_player import render
from merge_wav import merge_wavs


def make_wav(path: Path, seconds: float = 0.1, rate: int = 24000) -> None:
    frames = int(seconds * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)


class PostprocessTests(unittest.TestCase):
    def test_duration_and_merge(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "01.wav"
            b = root / "02.wav"
            make_wav(a, 0.1)
            make_wav(b, 0.2)
            item = wav_duration(a)
            self.assertEqual(item.status, "success")
            self.assertAlmostEqual(item.duration_seconds or 0, 0.1, places=2)
            result = merge_wavs([a, b], root / "full.wav", silence_ms=0)
            self.assertEqual(result["merged_count"], 2)
            self.assertTrue((root / "full.wav").exists())

    def test_srt_vtt_and_html(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "audio" / "01_intro.wav"
            make_wav(a, 0.1)
            manifest = {
                "segments": [
                    {"index": 1, "title": "导入", "filename": "01_intro.wav", "audio_path": str(a), "status": "success", "speech_text": "同学们好。"}
                ]
            }
            cues = build_cues(manifest, {}, {}, 0.35)
            self.assertEqual(len(cues), 1)
            srt = root / "course.srt"
            vtt = root / "course.vtt"
            write_srt(cues, srt)
            write_vtt(cues, vtt)
            self.assertIn("00:00:00,000", srt.read_text(encoding="utf-8"))
            self.assertIn("WEBVTT", vtt.read_text(encoding="utf-8"))
            html = render(manifest, root / "player.html", title="测试", segments_text={}, vtt_path=str(vtt))
            self.assertIn("<audio", html)
            self.assertIn("测试", html)


if __name__ == "__main__":
    unittest.main()
