# Podcast To Summary Text Skill

[Back to default README](README.md) | [中文说明](README.zh.md)

This directory is the installable root of the `mimo-token-plan-asr-llm-pipeline` skill. It helps an AI coding agent turn podcasts, videos, URLs, or existing transcripts into timestamped deep-summary Markdown reports.

## Core Capabilities

- Supports local audio, local video, URLs available through `yt-dlp`, Bilibili URLs through BBDown with optional cookies, and existing transcripts.
- Default quality chain: raw ASR transcript -> LLM proofreading -> LLM summary.
- Generates strict timeline reports by default.
- Maps every `[HH:MM-HH:MM]` transcript window to one report section.
- LLM proofreading adds punctuation, sentence boundaries, and fixes typos, English terms, person names, and company names while preserving window labels.
- Adds a final core ideas table.
- Separates ASR transcription from LLM proofreading/summarization: ASR API credentials are required, LLM API credentials are optional.
- Recommends the current IDE/Agent model for proofreading and summarization by default.

## Directory Structure

```text
mimo-token-plan-asr-llm-pipeline/
  SKILL.md
  README.md
  README.zh.md
  README.en.md
  scripts/
  references/
```

`SKILL.md` contains the skill instructions read by the AI IDE. `scripts/` contains transcription, batching, merge, and validation logic. `references/` contains API, provider, and report-format references.

## Quick Install

If CodeBuddy, Qoder Work, Codex, or another AI IDE supports installing a skill from GitHub, paste this subdirectory URL:

```text
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline
```

Recommended prompt for your AI IDE:

```text
Install the skill from this GitHub subdirectory:
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline

Install only the mimo-token-plan-asr-llm-pipeline/ directory. The installed skill root must directly contain SKILL.md, scripts/, and references/.
```

## Manual Install

Clone the repository:

```bash
git clone https://github.com/wsh-dot/podcast-to-summary-text.git
```

Install for Codex Skills on Windows PowerShell:

```powershell
mkdir "$env:USERPROFILE\.codex\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.codex\skills\mimo-token-plan-asr-llm-pipeline"
```

Install for Qoder Work Skills on Windows PowerShell:

```powershell
mkdir "$env:USERPROFILE\.qoderworkcn\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.qoderworkcn\skills\mimo-token-plan-asr-llm-pipeline"
```

For other AI IDEs, copy the whole `mimo-token-plan-asr-llm-pipeline/` directory into that IDE's skills directory.

## Dependencies

Python packages:

```bash
pip install openai yt-dlp
```

System dependency:

```bash
ffmpeg
```

On Windows:

```powershell
winget install Gyan.FFmpeg
```

Tencent ASR support also requires:

```bash
pip install tencentcloud-sdk-python
```

Bilibili URLs work best with BBDown. For login-gated or risk-controlled content, provide a browser cookie:

```powershell
$env:BBDOWN_PATH = "C:\Tools\BBDown\BBDown.exe"
$env:BILIBILI_COOKIE = "SESSDATA=...; bili_jct=...; DedeUserID=..."
```

## Default Workflow

When the agent invokes this skill, it should ask one question at a time:

1. ASR source: MiMo ASR, Alibaba Qwen ASR, Tencent ASR, or existing transcript.
2. Proofreading and summary mode: current IDE/Agent model, API LLM, or prompt export only.

Recommended defaults:

- ASR: the user provides credentials for the selected ASR provider.
- Summary: `ide-agent`, which means the current IDE/Agent model proofreads ASR windows first and then writes timeline sections.

## Common Commands

Transcribe only and save a windowed transcript:

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
```

Transcribe a Bilibili URL:

```bash
python scripts/mimo_podcast_tool.py "https://www.bilibili.com/video/BV..." --transcribe-only --api-key "tp-xxxx" --bilibili-cookie "SESSDATA=..."
```

Use an existing transcript and export prompts for the current IDE/Agent model:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
```

Use an API LLM to generate only the calibrated transcript:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --proofread-only --llm-provider kimi --llm-api-key "sk-xxxx"
```

Use an existing transcript and an API LLM to generate the report. The script proofreads first, then summarizes:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider kimi --llm-api-key "sk-xxxx"
```

Run self-tests:

```bash
python scripts/mimo_podcast_tool.py --self-test
```

## More References

- [providers.en.md](references/providers.en.md): ASR and LLM provider boundaries.
- [bilibili-download.md](references/bilibili-download.md): Bilibili BBDown/cookie download notes.
- [proofreading.en.md](references/proofreading.en.md): ASR proofreading rules.
- [proofreading.md](references/proofreading.md): Chinese ASR proofreading reference.
- [timeline-report-format.en.md](references/timeline-report-format.en.md): timeline report format.
- [api-reference.en.md](references/api-reference.en.md): MiMo Token Plan API reference.
