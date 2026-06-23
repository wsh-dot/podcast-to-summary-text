---
name: mimo-token-plan-asr-llm-pipeline
description: 使用 ASR API（MiMo Token Plan、阿里 Qwen ASR、腾讯 ASR）或已有 transcript 将音频/视频/URL（含小宇宙链接）转写为带时间窗口的稿件，并生成播客深度摘要报告：时间点章节、每段内容概括、关键引用、转写说明、核心观点速览表；任务开始时必须进入串行询问阶段，先让用户选择 ASR 来源，收到回答后再选择总结方式，默认用当前 IDE/Agent 模型总结，也可用 MiMo/Kimi/智谱/阿里/腾讯/MiniMax 等 LLM API 或导出 prompts 手动总结。Use when working with ASR API credentials, MiMo ASR, Alibaba Qwen ASR, Tencent ASR, 小米 MiMo 语音识别, token plan 音频转文字, 小宇宙转写, 播客笔记, 带时间点摘要, podcast notes, timeline podcast summary, IDE agent summary, API LLM summary, manual prompt workflow, sequential start-of-task choice prompt.
---

# MiMo Token Plan 时间线播客摘要

用 `scripts/mimo_podcast_tool.py` 处理音频、视频、URL 或已有 transcript，生成逐窗口播客深度解读。报告必须是 `timeline`：每个 `[HH:MM-HH:MM]` transcript 窗口对应一个 `## HH:MM-HH:MM 主题` 章节，并在结尾生成“核心观点速览”表。

## Start-of-task Selection

Before running audio/video/URL ASR, enter a short serial inquiry stage and resolve two choices one at a time:

1. ASR source and credentials. Audio/video/URL input requires one ASR API credential unless the user provides an existing windowed transcript.
2. Summary mode. Ask at task start when the user did not specify it. Recommend `ide-agent`.

Ask only one question per turn. Do not ask the summary-mode question until the ASR-source answer has been received and recorded. Treat both answers as execution context for the rest of the skill.

If an interactive choice UI is available, use it for the current single question. Recommended choices:

- First question ASR source: `MiMo ASR`, `Alibaba Qwen ASR`, `Tencent ASR`, `Existing transcript`.
- Second question summary mode: `Current IDE/Agent model (Recommended)`, `API LLM`, `Manual prompt export`.

If no interactive choice UI is available, ask the first question exactly like this and wait:

```text
请先确认 ASR 转写来源：

1. MiMo ASR：请提供 MiMo Token Plan API key
2. 阿里 Qwen ASR：请提供 DashScope / Aliyun API key
3. 腾讯 ASR：请提供 SecretId / SecretKey
4. 已有 transcript：请提供带 [HH:MM-HH:MM] 窗口的 txt 文件
```

After the ASR-source answer is received, ask the second question exactly like this and wait:

```text
ASR 来源已确认。总结阶段用哪种方式？

1. 当前 IDE/Agent 模型总结（推荐，无需 LLM API）
2. 指定 LLM API 总结，例如 MiMo / Kimi / 智谱 / 阿里 / 腾讯 / MiniMax
3. 只导出 prompts，我手动总结
```

If the user does not answer the summary-mode choice, use `ide-agent`. Do not treat a MiMo `--api-key` as consent to use MiMo LLM; it may be ASR-only unless the user asks for API LLM summary.

Do not run ASR, download media, or call any LLM until both answers are available in context: ASR source and summary mode.

## Execution Routes

### `ide-agent` Summary (Default)

Use when no LLM API was selected, or when the user says to use the current IDE / programming tool model.

1. Run ASR only and save the windowed transcript:
   ```bash
   python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
   python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider aliyun-qwen --asr-api-key "sk-xxxx"
   ```
2. Agent reads the transcript and writes one batch file per 6 windows under `<base_name>_agent_sections/batch_*.md`.
3. Merge and validate:
   ```bash
   python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
   ```

### `api-llm` Summary

Use only when the user explicitly selects a LLM API provider or provides `--llm-provider` / `--llm-api-key`.

```bash
python scripts/mimo_podcast_tool.py input.mp3 --asr-provider mimo --api-key "tp-xxxx" --llm-provider kimi --llm-api-key "sk-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider zhipu --llm-api-key "sk-xxxx"
```

### `manual` Fallback

Use only when the user asks to export prompts or manually paste model outputs.

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_ide_prompts/sections
```

## Input Decision

| User provides | Action |
|---|---|
| Local audio (`.mp3`, `.wav`, `.m4a`, `.flac`) | Require ASR provider credentials, then transcribe. |
| Local video (`.mp4`, `.mkv`, `.mov`, `.webm`) | Require ASR provider credentials, extract audio, then transcribe. |
| URL or 小宇宙 episode link | Require ASR provider credentials, use `yt-dlp` download path, then transcribe. |
| Existing windowed transcript `.txt` | Use `--transcript-input`, skip ASR API, then choose summary mode. |

## Dependencies

| Package / Binary | Purpose | Install |
|---|---|---|
| `openai` | MiMo and OpenAI-compatible API calls | `pip install openai` |
| `ffmpeg` | Audio chunking and video audio extraction | `winget install Gyan.FFmpeg` or equivalent |
| `yt-dlp` | URL downloads, including podcast pages when supported | `pip install yt-dlp` |
| `tencentcloud-sdk-python` | Tencent ASR only | `pip install tencentcloud-sdk-python` |

## Resource Loading

- Need exact MiMo endpoint/payload/auth/error details: read `references/api-reference.md`.
- Need report format, timecode rules, or prompt behavior: read `references/timeline-report-format.md`.
- Need Alibaba/Tencent/Zhipu/Kimi/MiniMax provider options: read `references/providers.md`.
- Need to modify script behavior: inspect `scripts/mimo_podcast_tool.py` after reading the relevant reference.
- Normal execution: do NOT load references; run the script.
- Do NOT load `providers.md` unless switching providers or changing provider defaults.

## Output Contract

```markdown
# [Title]

> **转写说明**：...

## 00:00-00:03 开场：[topic]

## 00:03-00:06 [topic]

## 核心观点速览

| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |
```

Every transcript window must produce exactly one matching time section. Do not merge adjacent windows, skip quiet/noisy windows, or invent timestamps.

## Provider Rule

Keep provider-specific logic in adapters:

- ASR adapter: media chunk -> text.
- LLM adapter: transcript windows -> report sections/table.
- Report engine: batching, validation, repair, merge.

ASR API is required for audio/video/URL input. Built-in ASR providers: `mimo`, `aliyun-qwen`, `tencent`.

LLM API is optional. Built-in LLM provider labels: `mimo`, `aliyun`, `tencent`, `zhipu`, `kimi`, `minimax`, `openai-compatible`. The current IDE model is not a script provider; use the `ide-agent` route.

## NEVER

- NEVER call `/audio/transcriptions`; MiMo Token Plan ASR uses `/chat/completions` with `input_audio`.
- NEVER use a `tp-` Token Plan key against `https://api.xiaomimimo.com/v1`; use `https://token-plan-sgp.xiaomimimo.com/v1`.
- NEVER send a long podcast as one base64 request; split audio first.
- NEVER continue from audio/video/URL input without an ASR API credential or an existing windowed transcript.
- NEVER default to API LLM summary just because an ASR API key was provided; ask for summary mode and default to `ide-agent`.
- NEVER generate timestamps more precise than transcript windows.
- NEVER merge or skip transcript windows in `timeline` reports.
- NEVER accept LLM-generated time windows that do not exist in the transcript; the report engine must ignore extras and repair missing windows.
- NEVER fabricate guests, hosts, exact quotes, missing windows, or program metadata.

## Quick Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: openai` | Missing SDK | Install `openai`; rerun `--self-test`. |
| `ffmpeg` not found | Missing binary | Install ffmpeg; confirm it is on PATH. |
| URL download fails | `yt-dlp` unsupported, stale, or blocked | Update `yt-dlp` or use a local media file. |
| HTTP 401 | Wrong key or endpoint | Token Plan keys must use `https://token-plan-sgp.xiaomimimo.com/v1`. |
| HTTP 404 | Wrong endpoint | Do not use `/audio/transcriptions`; use `/chat/completions` with `input_audio`. |
| HTTP 413 | Audio chunk too large after base64 expansion | Reduce `--segment-minutes` from 5 to 3 or 1. |
| User has ASR API but no LLM API | Normal case | Use `ide-agent` summary unless user selects API LLM. |
| Manual merge reports missing windows | IDE output skipped one or more required sections | Reopen the matching prompt and save a file containing the missing `## HH:MM-HH:MM` sections. |
| Report still misses windows after repair | Batch output repeatedly failed contract | Lower `--timeline-batch-size`; regenerate from `--transcript-input`. |

## Verification

```bash
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/mimo_podcast_tool.py
python scripts/mimo_podcast_tool.py --help
```

Check saved transcript contains `[HH:MM-HH:MM]` windows and the final report contains the same number of `## HH:MM-HH:MM` sections plus the core table.
