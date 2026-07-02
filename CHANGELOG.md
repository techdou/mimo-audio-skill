# Changelog

## v1.3.0

模块化增强版，遵循渐进式披露设计。

### Added

- 新增 `scripts/run_pipeline.py`：可选调度器，默认只执行 TTS，其他能力必须显式开启。
- 新增 `scripts/generate_html_player.py`：从 TTS manifest 生成独立音频播放页。
- 新增 `scripts/inject_audio_to_html.py`：给已有讲义 HTML 注入音频播放器，不重做页面。
- 新增 `scripts/generate_srt.py`：生成 SRT / WebVTT 片段级字幕。
- 新增 `scripts/audio_duration.py`：统计 WAV 时长并可回写 manifest。
- 新增 `scripts/merge_wav.py`：合并分段 WAV 为 `full_course.wav`。
- 新增 `scripts/mimo_logger.py`：基础日志与 JSONL 事件日志。
- 新增 `tests/`：标准库 unittest 测试，包括 manifest、字幕、时长、合并和 HTML 生成。
- 新增 `pyproject.toml`：为后续 package 化提供元数据。
- 新增 `docs/tts.md`、`docs/asr.md`、`docs/subtitles.md`、`docs/html_player.md`、`docs/pipeline.md`。

### Changed

- `SKILL.md` 重构为任务路由型说明，只保留核心能力、触发条件和脚本选择规则。
- `README.md` 重写为快速开始和场景化命令。
- `templates/config.example.json` 增加 pipeline、字幕、合并和日志相关默认值。

### Design

- TTS 是主能力。
- ASR 是质检能力。
- HTML 是预览能力。
- SRT/VTT 是视频辅助能力。
- Merge 是发布辅助能力。
- Pipeline 是可选调度能力，不替代单一职责脚本。

## v1.2.1

官方文档严格对齐版。默认只发送一种认证 Header；`--stream` 默认只作用于 `mimo-v2.5-tts`；新增 smoke test。

## v1.2.0

增强版。新增 ASR、流式 TTS、音频标签、voice clone 本地样本转换和官方规则文档。

## v1.1.0

修复配置读取、API Key 优先级、分段校验、失败重跑和 429 处理。
