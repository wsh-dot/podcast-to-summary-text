# Podcast To Summary Text Skill

[Back to default README](README.md) | [中文说明](README.zh.md)

This directory is the installable root of the `mimo-token-plan-asr-llm-pipeline` skill. It helps an AI coding agent turn podcasts, videos, URLs, or existing transcripts into timestamped deep-summary Markdown reports.

## Core Capabilities

- Supports local audio, local video, URLs available through `yt-dlp`, and existing transcripts.
- Generates strict timeline reports by default.
- Maps every `[HH:MM-HH:MM]` transcript window to one report section.
- Adds a final core ideas table.
- Separates ASR transcription from LLM summarization: ASR API credentials are required, LLM API credentials are optional.
- Recommends the current IDE/Agent model for summarization by default.

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

## Default Workflow

When the agent invokes this skill, it should ask one question at a time:

1. ASR source: MiMo ASR, Alibaba Qwen ASR, Tencent ASR, or existing transcript.
2. Summary mode: current IDE/Agent model, API LLM, or prompt export only.

Recommended defaults:

- ASR: the user provides credentials for the selected ASR provider.
- Summary: `ide-agent`, which means the current IDE/Agent model writes the timeline sections.

## Common Commands

Transcribe only and save a windowed transcript:

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
```

Use an existing transcript and export prompts for the current IDE/Agent model:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
```

Use an existing transcript and an API LLM to generate the report:

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider kimi --llm-api-key "sk-xxxx"
```

Run self-tests:

```bash
python scripts/mimo_podcast_tool.py --self-test
```

## More References

- [providers.md](references/providers.md): ASR and LLM provider boundaries.
- [timeline-report-format.md](references/timeline-report-format.md): timeline report format.
- [api-reference.md](references/api-reference.md): MiMo Token Plan API reference.
