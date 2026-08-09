# Self-Update Guard Design

本 skill 内置运行时官方文档同步校验,防止小米 MiMo API 迭代(模型下线、参数变更、音色增减)后 skill 静默失效。

## 为什么需要

小米 MiMo 的模型迭代速度很快——**V2 系列已于 2026.6.30 正式下线**。如果 skill 把模型名和调用规则硬编码在脚本里,一旦模型被弃用,用户会在合成失败后才意识到问题,且错误信息可能晦涩难懂。

自更新机制在调用 API **之前**就做检查,把"模型不存在""参数变了"这类问题提前暴露出来。

## 两层检测

### API 层:`GET /v1/models`

- 调用 OpenAI 兼容的 `/v1/models` 端点(带 api_key)。
- 取回服务端实际可用的模型 ID 列表。
- 检查 skill 依赖的 4 个模型是否仍存在:
  - `mimo-v2.5-tts`
  - `mimo-v2.5-tts-voicedesign`
  - `mimo-v2.5-tts-voiceclone`
  - `mimo-v2.5-asr`
- 任一缺失 → **CRITICAL**(模型可能已下线/改名)。

### 文档层:`llms.txt` → `.md` 源

- 小米提供了 LLM 友好的文档源:`https://mimo.mi.com/llms.txt` 是索引,指向 `.md` 纯文本(不是 JS 渲染的 HTML 页面)。
- 脚本 fetch TTS 和 ASR 的 `.md` 源,用正则提取关键规则:
  - TTS:模型列表、预置音色集合。
  - ASR:模型列表、语言列表。
- 跟 `templates/known_rules.json` 做 diff:
  - 本地有但官方没有 → **WARNING**(可能被移除/改名)。
  - 官方有但本地没有 → **INFO**(新增能力,建议跟进)。

## 缓存机制

- 抓取的 `.md` 源缓存在 `output/.doc_cache/` 下,按 URL SHA256 hash 命名。
- TTL 默认 24 小时(config 里 `doc_check_ttl_hours` 可调)。
- 缓存未过期 → 直接读文件,零网络开销。
- `--force-refresh` 跳过缓存强制重抓。

## 运行时行为矩阵

| 场景 | 默认行为 | 可控 |
|---|---|---|
| 缓存未过期 | 读缓存静默通过 | — |
| 缓存过期 | 后台刷新不阻断,下次生效 | `--check-docs` 改为同步阻断 |
| 模型下线 (CRITICAL) | 打印警告但继续 | `--check-docs` 升级为阻断;`--skip-check` 完全跳过 |
| 规则变化 (WARNING) | 提示但继续执行 | `--check-docs` 或 `--fail-on warning` 升级为阻断 |
| 文档结构变化 (INFO) | 提示人工检查 | — |
| doc check 自身出错 | 静默降级,绝不阻断合成 | `--verbose` 看错误详情 |

**核心原则:doc check 永远只是 advisory,默认不阻断合成流程。** 只有用户显式 `--check-docs` 时才升级为阻断。这样保证网络抖动或文档页临时挂掉不会让用户没法干活。

## 怎么用

### 独立运行

```bash
# 完整检查(API + 文档),需要 API key
python scripts/check_official_docs.py

# 只查文档层,不调 API
python scripts/check_official_docs.py --no-models

# JSON 格式输出,方便程序处理
python scripts/check_official_docs.py --format json

# 强制刷新缓存
python scripts/check_official_docs.py --force-refresh
```

### 在合成流程中

```bash
# 正常合成(默认非阻断 doc check,缓存有效时零开销)
python scripts/mimo_tts_batch.py --config templates/config.example.json --segments output/segments.json

# 要求合成前必须通过 doc check(阻断)
python scripts/mimo_tts_batch.py ... --check-docs

# 完全跳过 doc check
python scripts/mimo_tts_batch.py ... --skip-check

# pipeline 级别
python scripts/run_pipeline.py --input lecture.md --tts --check-docs
```

## 怎么更新 known_rules.json

当 check 报 WARNING/INFO 提示官方文档有变化时:

1. 跑 `python scripts/check_official_docs.py --force-refresh --no-models --format json` 看具体差异。
2. 对照官方文档页确认变化内容。
3. 手动编辑 `templates/known_rules.json`,更新对应的模型列表/音色/语言/格式。
4. 更新 `snapshot_date` 字段为当天日期。
5. 同步更新 `references/mimo_v25_audio_rules.md`(人工可读副本)。
6. 跑一次 `check_official_docs.py` 确认零 issue。

`known_rules.json` 故意不自动覆写——规则变化需要人确认语义,自动写入可能引入错误。

## 官方文档 URL

| 用途 | URL |
|---|---|
| TTS 人类可读页 | https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5 |
| ASR 人类可读页 | https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition |
| LLM 友好索引 | https://mimo.mi.com/llms.txt |
| TTS .md 源 | https://mimo.mi.com/static/docs/quick-start/usage-guide/audio/speech-synthesis-v2.5.md |
| ASR .md 源 | https://mimo.mi.com/static/docs/quick-start/usage-guide/audio/Speech-Recognition.md |

`.md` 源是脚本实际抓取的目标,因为它们是纯文本,Python urllib 直接可读,不需要 headless browser。
