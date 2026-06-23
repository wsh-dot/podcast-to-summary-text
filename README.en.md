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
- URLs supported by `yt-dlp`, such as many podcast pages, YouTube links, and Bilibili links when access is available
- Existing transcripts with `[HH:MM-HH:MM]` windows

## Summary Modes

The skill separates ASR transcription from summary generation.

ASR credentials are required when starting from audio, video, or URL input. LLM credentials are optional.

The agent should ask one question at a time at task start:

1. Which ASR source should be used?
2. After the ASR answer is recorded, which summary mode should be used?

Summary modes:

- `ide-agent`: use the current IDE/Agent model to summarize, then use the script to merge and validate. This is the recommended default.
- `api-llm`: use an API LLM provider such as MiMo, Kimi, Zhipu, Alibaba, Tencent, MiniMax, or an OpenAI-compatible endpoint.
- `manual`: export prompts and let the user paste model outputs manually.

## Installation

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
| Tencent ASR | `--asr-provider tencent --tencent-secret-id --tencent-secret-key` |
| Existing transcript | No ASR API credential; use `--transcript-input` |

Do not commit API keys, cookies, browser profiles, or exported credentials.

## Common Commands

Run commands from the skill directory:

```bash
cd podcast-to-summary-text/mimo-token-plan-asr-llm-pipeline
```

MiMo ASR, then IDE/Agent summary:

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

Alibaba Qwen ASR, then IDE/Agent summary:

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider aliyun-qwen --asr-api-key "sk-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

Existing transcript, then API LLM summary:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider kimi --llm-api-key "sk-xxxx"
```

Manual prompt export:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_ide_prompts/sections
```

## URL And Cookie Notes

URL input is handled through `yt-dlp`.

Public podcast URLs often work directly. Bilibili and YouTube links may require cookies or browser login state depending on the video, region, age restriction, membership status, or anti-bot checks.

For login-required videos:

```bash
yt-dlp --cookies-from-browser chrome "https://www.bilibili.com/video/BV..."
```

or:

```bash
yt-dlp --cookies cookies.txt "https://www.bilibili.com/video/BV..."
```

Cookies are sensitive credentials. Do not print them, store them in reports, or commit them.

## Verification

Run:

```bash
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/mimo_podcast_tool.py
python scripts/mimo_podcast_tool.py --help
```

The self-test does not call any external API.
