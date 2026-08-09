# Changelog

## v2.2.0

Skills 格式合规升级：按官方 SKILL.md 规范（name/description frontmatter + 正文指令）重写元数据与正文，优化 Agent 匹配调用。

### Changed

- SKILL.md 改为标准 YAML frontmatter（`name` / `description` / `metadata.short-description`），description 精简为"工作流 + 触发/不触发条件"，正文以 Use/Do not use 开头。
- 文档目录 `docs/` 更名为规范推荐的 `references/`，SKILL.md、README、references 内部互链同步更新。
- 正文瘦身：API 细节、自检、排错等移入 references，SKILL.md 只保留路由、模板要点、输出约定。

## v2.1.0

技能更名与样本更新：`mimo-lecture-audio-skill` → `mimo-audio-skill`。

### Changed

- 技能目录、项目名、SKILL/README/LICENSE 中的名称统一改为 `mimo-audio-skill`。
- `profiles/douge-lecture.json` 的克隆样本更新为 `C:/Users/DouXiulu/Downloads/douge.wav`。
- 同步更新外部引用：`ai-promo-video`、`remotion-video` 中对旧技能名的文字引用。

## v2.0.0

通用化升级：从"讲义音频 Skill"扩展为"通用口播/有声内容合成 Skill"，新增可复用的音色风格模板系统。

### Added

- 新增 `scripts/voice_profiles.py`：音色模板管理器，支持 `list / get / create / validate / apply`。
- 新增 `templates/profiles/`：内置模板 lecture-natural、podcast-casual、novel-narration、short-video、example-personal-clone。
- 新增 `profiles/`：个人模板目录（gitignored），内置 `douge-lecture.json`（豆哥 voiceclone 克隆音色基准）。
- 新增 `docs/profiles.md`：模板字段、位置、使用方式与设计取舍。
- 新增 `examples/novel_sample.md`、`examples/podcast_sample.md`：非讲义场景示例。
- `mimo_tts_batch.py` 新增 `--profile` / `--profile-file`：合成前把模板注入 segments 缺失字段。
- `make_segments.py` 新增 `--profile` / `--profile-file` / `--voice-sample-path` / `--voice-design-prompt`。
- `run_pipeline.py` 新增 `--profile` / `--profile-file` / `--text-kind`（lecture/novel/podcast/marketing）和 `--title` 别名。

### Changed

- `SKILL.md` / `README.md` 重写为通用口播/有声内容合成说明，讲义降级为其中一个场景。
- `make_segments.py` 默认标题前缀改为"内容片段"，`--style` 默认值改为 None（显式传参才覆盖 profile）。
- 校验脚本和 TTS 批处理文案从"lecture"泛化为"narration"。

### Design

- Profile 只做缺省值注入，不覆盖显式字段，单段特殊处理仍可行。
- 个人模板与内置模板分离，个人样本路径不随仓库分发。

## v1.4.0

自更新增强版:新增运行时官方文档同步校验,防止模型下线后 skill 静默失效。

### Added

- 新增 `scripts/check_official_docs.py`:核心校验器,双层检测——
  - API 层:`GET /v1/models` 探测 skill 依赖的 4 个模型是否仍存在(CRITICAL)。
  - 文档层:通过 `llms.txt` → `.md` 纯文本源,提取音色/语言/格式,与 `templates/known_rules.json` 做 diff(WARNING / INFO)。
  - 支持 `--format json/text`、`--force-refresh`、`--fail-on critical/warning/info`、`--no-models`。
  - 提供 `run_check()` 公共入口供 TTS / ASR / pipeline 预检查调用。
- 新增 `templates/known_rules.json`:本地规则快照,作为 diff 基准。
- 新增 `docs/self_update.md`:自更新机制设计文档。
- `mimo_audio_common.py` 新增三个基础函数:`fetch_text(url)`、`list_models(api_key, base_url)`、`DocCache` 文件缓存类。
- `mimo_tts_batch.py` / `mimo_asr_transcribe.py` 预检查阶段接入 doc check;新增 `--check-docs`(阻断)和 `--skip-check`(跳过)参数。
- `run_pipeline.py` 新增 `--check-docs` / `--skip-check`,校验结果透传给子脚本。
- `config.example.json` 新增 `doc_check_enabled` / `doc_check_ttl_hours` / `known_rules_path` / `official_doc_urls` 字段。

### Changed

- `docs/mimo_v25_audio_rules.md` 对齐官方文档(2026-07-15 快照),补齐 6 处差距:ASR 方言支持、`optimize_text_preview`、唱歌模式标签、音频标签控制、导演模式、voiceclone 风格指令。头部加官方文档 URL 和 snapshot_date。
- `SKILL.md` 版本升至 1.4.0,加 Self-update guard 说明和 check_official_docs.py 路由。

### Design

- 保持 stdlib-only:`.md` 源中的 HTML 表格用已知音色名正则匹配,不引入 beautifulsoup4。
- 默认非阻断:缓存未过期时零网络开销静默通过;过期时后台刷新不阻断当前运行。
- doc check 失败只降级为 advisory,绝不阻断合成流程(除非显式 `--check-docs`)。

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
