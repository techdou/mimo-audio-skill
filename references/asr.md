# MiMo ASR 说明

ASR 入口脚本是：

```bash
python scripts/mimo_asr_transcribe.py --config templates/config.example.json --audio output/audio/*.wav --language zh --out-dir output/asr --manifest output/asr_manifest.json
```

## 适用场景

- 用 ASR 转写已生成音频，检查播报是否完整。
- 为字幕生成提供更接近音频内容的文本。
- 给课程音频生成转写稿。

## 语言参数

- `auto`：自动识别。
- `zh`：中文。
- `en`：英文。

课程中文讲义建议使用 `zh`，比 `auto` 更稳定。

## 注意

ASR 输入支持 `.wav` / `.mp3`。脚本会自动转成 `data:audio/...;base64,...` 格式。
