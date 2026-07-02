# MiMo TTS 说明

本 Skill 的主能力是把讲义分段文本合成为音频。TTS 入口脚本是：

```bash
python scripts/mimo_tts_batch.py --config templates/config.example.json --segments examples/segments.sample.json --out-dir output/audio --manifest output/audio_manifest.json
```

## 模型路由

- `mimo-v2.5-tts`：默认模型，使用预置音色，适合讲义播报。
- `mimo-v2.5-tts-voicedesign`：通过 `voice_design_prompt` 设计音色。
- `mimo-v2.5-tts-voiceclone`：通过 `voice_sample_path` 或 data URL 克隆音色。

## 消息规则

- `user.content`：语气、风格、音色描述。
- `assistant.content`：真正要合成的讲稿文本。
- `audio.format`：普通批处理用 `wav`；流式用 `pcm16`，脚本会写入 `.wav` 容器。

## 流式规则

```bash
python scripts/mimo_tts_batch.py --segments output/segments.json --stream
```

`--stream` 只对 `mimo-v2.5-tts` 预置模型生效。若确实要对 voice design / voice clone 使用兼容流式，显式使用：

```bash
python scripts/mimo_tts_batch.py --segments output/segments.json --stream-all
```

## 失败重跑

```bash
python scripts/mimo_tts_batch.py --segments output/segments.json --manifest output/audio_manifest.json --failed-only
```
