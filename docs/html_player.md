# HTML 播放页说明

HTML 播放页是可选能力。只有当你需要批量检查一套讲义音频时才使用。

## 生成独立播放页

```bash
python scripts/generate_html_player.py --manifest output/audio_manifest.json --segments output/segments.json --output output/player.html --title "AI 通识课音频"
```

## 给已有讲义 HTML 注入音频

如果你已经有一个设计好的讲义 HTML，不要重新生成 HTML；只注入音频块：

```bash
python scripts/inject_audio_to_html.py --html lecture.html --manifest output/audio_manifest.json --output lecture_with_audio.html
```

这个脚本会在 `</body>` 前追加一个小型音频面板，不改变原页面主体结构。
