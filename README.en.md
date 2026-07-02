# Podcast to Summary Text Skill

This repository publishes the `mimo-token-plan-asr-llm-pipeline` skill.

The installable skill folder is:

```text
mimo-token-plan-asr-llm-pipeline/
  SKILL.md
  scripts/
  references/
```

The root documentation files are for GitHub only. Do not copy them into the skill folder unless your AI IDE explicitly asks for them.

## What This Skill Does

This skill helps an AI coding agent turn podcasts, videos, URLs, or existing transcripts into timestamped deep-summary Markdown reports.

It is designed for long-form audio and video content. The final report contains:

- timestamped timeline sections
- one report section for each ASR transcript window
- LLM proofreading before summary: punctuation, sentence boundaries, typos, English terms, person names, and company names
- concise explanations of what each segment discussed
- short direct quotes only when supported by transcript text
- a transcription note
- a final core ideas table for quick scanning

The default report style is a strict timeline report:

```markdown
# Title

> Transcription note...

## 00:00-00:03 Opening topic

## 00:03-00:06 Next topic

## Core Ideas At A Glance

| Time | Section | Core Idea | Evidence / Quote |
```

## Supported Inputs

- Local audio: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`
- Local video: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`
- Bilibili URLs, exclusively through BBDown with pinned version 1.6.3 downloaded and verified on first use
- Other URLs supported by `yt-dlp`, including Xiaoyuzhou podcast pages and YouTube links
- Existing transcripts with `[HH:MM-HH:MM]` windows

## Proofreading And Summary Modes

The skill separates ASR transcription, LLM proofreading, and LLM summary generation. Raw ASR often lacks punctuation and contains typos, broken English terms, and misrecognized names, so the default flow proofreads before summarizing.

ASR credentials are required when starting from audio, video, or URL input. LLM credentials are optional.

The agent should ask one question at a time at task start:

1. Which ASR source should be used?
2. After the ASR answer is recorded, which proofreading/summary mode should be used?

Proofreading/summary modes:

- `ide-agent`: use the current IDE/Agent model to proofread ASR first, then summarize; the script merges and validates. This is the recommended default.
- `api-llm`: use an API LLM provider such as MiMo, Kimi, Zhipu, Alibaba, Tencent, MiniMax, or an OpenAI-compatible endpoint to proofread and summarize automatically.
- `manual`: export prompts and let the user paste model outputs manually for proofreading and summary.

API LLM mode now pipelines proofreading -> immediate summary per batch with bounded concurrency of 2. Use `--proofread-mode inline` when only the final report is needed; calibrated inputs skip duplicate proofreading automatically. Set `--llm-concurrency 1` for strict provider rate limits.

## Installation

### Quick Install In AI IDEs

If CodeBuddy, Qoder Work, Codex, or another AI coding IDE supports installing a skill from GitHub, paste this **skill subdirectory URL**:

```text
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline
```

You can also send this prompt to your AI IDE:

```text
Install the skill from this GitHub subdirectory:
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline

Install only the mimo-token-plan-asr-llm-pipeline/ directory. The installed skill root must directly contain SKILL.md, scripts/, and references/.
Do not copy the repository root README.md, README.en.md, or README.zh.md files into the installed skill folder.
```

Do not rely on the repository root URL `https://github.com/wsh-dot/podcast-to-summary-text` as an automatic install URL. The repository root is documentation only, while the actual skill is in a subdirectory. Strict installers that only look for `SKILL.md` at the repository root may fail.

If your AI IDE cannot install from a GitHub subdirectory, use the manual steps below.

Clone this repository:

```bash
git clone https://github.com/wsh-dot/podcast-to-summary-text.git
```

### Install For Codex Skills

Windows PowerShell:

```powershell
mkdir "$env:USERPROFILE\.codex\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.codex\skills\mimo-token-plan-asr-llm-pipeline"
```

macOS / Linux:

```bash
mkdir -p ~/.codex/skills
cp -R ./podcast-to-summary-text/mimo-token-plan-asr-llm-pipeline ~/.codex/skills/
```

### Install For Qoder Work Skills

Windows PowerShell:

```powershell
mkdir "$env:USERPROFILE\.qoderworkcn\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.qoderworkcn\skills\mimo-token-plan-asr-llm-pipeline"
```

For other AI IDEs, copy the `mimo-token-plan-asr-llm-pipeline/` folder into the IDE's skills directory.

## Dependencies

Python packages:

```bash
pip install openai yt-dlp
```

System dependency:

```bash
ffmpeg
```

Windows:

```powershell
winget install Gyan.FFmpeg
```

Tencent ASR support also requires:

```bash
pip install tencentcloud-sdk-python
```

## ASR Credentials

Choose one ASR source:

| ASR source | Credential |
|---|---|
| MiMo ASR | `--api-key`, `--asr-api-key`, or `MIMO_API_KEY` |
| Alibaba Qwen ASR | `--asr-provider aliyun-qwen --asr-api-key`, `DASHSCOPE_API_KEY`, or `ALIYUN_API_KEY` |
| StepFun ASR | `--asr-provider stepfun --asr-api-key`, `STEPFUN_API_KEY`, or `STEP_API_KEY`; add `--stepfun-plan` for Step Plan credits |
| Tencent ASR | `--asr-provider tencent --tencent-secret-id --tencent-secret-key` |
| Existing transcript | No ASR API credential; use `--transcript-input` |

Do not commit API keys, cookies, browser profiles, or exported credentials.

## Common Commands

Run commands from the skill directory:

```bash
cd podcast-to-summary-text/mimo-token-plan-asr-llm-pipeline
```

MiMo ASR, then IDE/Agent proofreading and summary:

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

Alibaba Qwen ASR, then IDE/Agent proofreading and summary:

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider aliyun-qwen --asr-api-key "sk-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

StepFun StepAudio 2.5 ASR using Step Plan subscription credits:

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider stepfun --stepfun-plan --asr-api-key "..."
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

Without `--stepfun-plan`, the standard platform `/v1` path is used. The script never falls back between the two billing paths.

Existing transcript, then API LLM proofreading and summary:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider kimi --llm-api-key "sk-xxxx"
```

Manual prompt export:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_ide_prompts/sections
```

## URL And Cookie Notes

Bilibili URLs always use BBDown and never fall back to `yt-dlp`. On first use the script downloads and verifies pinned version 1.6.3; use `--bbdown-path` or `BBDOWN_PATH` for an existing executable. Xiaoyuzhou, YouTube, and other ordinary URLs continue to use `yt-dlp`.

For Bilibili content requiring login state:

```bash
python scripts/mimo_podcast_tool.py "https://www.bilibili.com/video/BV..." --transcribe-only --api-key "tp-xxxx" --bilibili-cookie "SESSDATA=..."
```

Pass `--no-bbdown-auto-install` to disable automatic installation; a BBDown path is then required.

Cookies are sensitive credentials. Do not print them, store them in reports, or commit them.

## Verification

Run:

```bash
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/mimo_podcast_tool.py
python scripts/mimo_podcast_tool.py --help
```

The self-test does not call any external API.
