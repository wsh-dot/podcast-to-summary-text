# Podcast to Summary Text Skill / 播客视频转时间线摘要 Skill

English | [中文](#中文说明)

This repository publishes the `mimo-token-plan-asr-llm-pipeline` skill.

该仓库发布的是 `mimo-token-plan-asr-llm-pipeline` skill。

The installable skill folder is:

可安装的 skill 目录是：

```text
mimo-token-plan-asr-llm-pipeline/
  SKILL.md
  scripts/
  references/
```

The root `README.md` is GitHub documentation only. Do not copy it into the skill folder unless your AI IDE explicitly asks for it.

根目录的 `README.md` 只是 GitHub 说明文档。除非你的 AI IDE 明确要求，否则不要把它复制进 skill 目录。

---

## English

### What This Skill Does

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

### Supported Inputs

- Local audio: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`
- Local video: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`
- URLs supported by `yt-dlp`, such as many podcast pages, YouTube links, and Bilibili links when access is available
- Existing transcripts with `[HH:MM-HH:MM]` windows

### Summary Modes

The skill separates ASR transcription from summary generation.

ASR credentials are required when starting from audio, video, or URL input. LLM credentials are optional.

The agent should ask one question at a time at task start:

1. Which ASR source should be used?
2. After the ASR answer is recorded, which summary mode should be used?

Summary modes:

- `ide-agent`: use the current IDE/Agent model to summarize, then use the script to merge and validate. This is the recommended default.
- `api-llm`: use an API LLM provider such as MiMo, Kimi, Zhipu, Alibaba, Tencent, MiniMax, or an OpenAI-compatible endpoint.
- `manual`: export prompts and let the user paste model outputs manually.

### Installation

Clone this repository:

```bash
git clone https://github.com/wsh-dot/podcast-to-summary-text.git
```

#### Install For Codex Skills

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

#### Install For Qoder Work Skills

Windows PowerShell:

```powershell
mkdir "$env:USERPROFILE\.qoderworkcn\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.qoderworkcn\skills\mimo-token-plan-asr-llm-pipeline"
```

For other AI IDEs, copy the `mimo-token-plan-asr-llm-pipeline/` folder into the IDE's skills directory.

### Dependencies

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

### ASR Credentials

Choose one ASR source:

| ASR source | Credential |
|---|---|
| MiMo ASR | `--api-key`, `--asr-api-key`, or `MIMO_API_KEY` |
| Alibaba Qwen ASR | `--asr-provider aliyun-qwen --asr-api-key`, `DASHSCOPE_API_KEY`, or `ALIYUN_API_KEY` |
| Tencent ASR | `--asr-provider tencent --tencent-secret-id --tencent-secret-key` |
| Existing transcript | No ASR API credential; use `--transcript-input` |

Do not commit API keys, cookies, browser profiles, or exported credentials.

### Common Commands

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

### URL And Cookie Notes

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

### Verification

Run:

```bash
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/mimo_podcast_tool.py
python scripts/mimo_podcast_tool.py --help
```

The self-test does not call any external API.

---

## 中文说明

### 这个 Skill 有什么用

这个 skill 用来帮助 AI 编程 Agent 把播客、视频、网页链接或已有转写稿，整理成带时间点的深度摘要 Markdown 报告。

它适合长音频和长视频内容。最终报告会包含：

- 带时间点的章节
- 每个 ASR 转写窗口对应一个报告章节
- 每个时间段讲了什么的概括
- 只在转写稿有依据时保留短引用
- 转写说明
- 方便快速浏览的“核心观点速览”表格

默认报告是严格的时间线报告：

```markdown
# 标题

> 转写说明...

## 00:00-00:03 开场主题

## 00:03-00:06 下一个主题

## 核心观点速览

| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |
```

### 支持的输入

- 本地音频：`.mp3`、`.wav`、`.m4a`、`.flac`、`.ogg`、`.aac`
- 本地视频：`.mp4`、`.mkv`、`.avi`、`.mov`、`.webm`、`.flv`
- `yt-dlp` 支持的 URL，例如很多播客页面、YouTube 链接、可访问的 B 站链接
- 已有的带 `[HH:MM-HH:MM]` 时间窗口的 transcript

### 总结方式

这个 skill 把 ASR 转写和 LLM 总结拆开处理。

如果从音频、视频或 URL 开始，必须提供 ASR 凭证。LLM API 凭证不是必须的。

Agent 在任务开始时应该一个问题一个问题地询问：

1. ASR 转写来源用哪个？
2. 等 ASR 来源回答并记录后，再问总结方式用哪个？

总结方式有三种：

- `ide-agent`：用当前 IDE/Agent 模型总结，再用脚本合并和校验。默认推荐这个。
- `api-llm`：用 MiMo、Kimi、智谱、阿里、腾讯、MiniMax 或 OpenAI-compatible API 总结。
- `manual`：只导出 prompts，用户自己复制到其它模型里总结。

### 安装方式

先 clone 仓库：

```bash
git clone https://github.com/wsh-dot/podcast-to-summary-text.git
```

#### 安装到 Codex Skills

Windows PowerShell：

```powershell
mkdir "$env:USERPROFILE\.codex\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.codex\skills\mimo-token-plan-asr-llm-pipeline"
```

macOS / Linux：

```bash
mkdir -p ~/.codex/skills
cp -R ./podcast-to-summary-text/mimo-token-plan-asr-llm-pipeline ~/.codex/skills/
```

#### 安装到 Qoder Work Skills

Windows PowerShell：

```powershell
mkdir "$env:USERPROFILE\.qoderworkcn\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.qoderworkcn\skills\mimo-token-plan-asr-llm-pipeline"
```

如果你的 AI IDE 使用其它 skill 目录，把 `mimo-token-plan-asr-llm-pipeline/` 整个目录复制进去即可。

### 依赖

Python 包：

```bash
pip install openai yt-dlp
```

系统依赖：

```bash
ffmpeg
```

Windows：

```powershell
winget install Gyan.FFmpeg
```

如果使用腾讯 ASR，还需要：

```bash
pip install tencentcloud-sdk-python
```

### ASR 凭证

选择一个 ASR 来源：

| ASR 来源 | 凭证 |
|---|---|
| MiMo ASR | `--api-key`、`--asr-api-key` 或 `MIMO_API_KEY` |
| 阿里 Qwen ASR | `--asr-provider aliyun-qwen --asr-api-key`、`DASHSCOPE_API_KEY` 或 `ALIYUN_API_KEY` |
| 腾讯 ASR | `--asr-provider tencent --tencent-secret-id --tencent-secret-key` |
| 已有 transcript | 不需要 ASR API，使用 `--transcript-input` |

不要提交 API key、cookies、浏览器 profile 或导出的凭证文件。

### 常用命令

进入 skill 目录：

```bash
cd podcast-to-summary-text/mimo-token-plan-asr-llm-pipeline
```

MiMo ASR，然后用当前 IDE/Agent 模型总结：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

阿里 Qwen ASR，然后用当前 IDE/Agent 模型总结：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider aliyun-qwen --asr-api-key "sk-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

已有 transcript，然后用 API LLM 总结：

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider kimi --llm-api-key "sk-xxxx"
```

手动导出 prompts：

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_ide_prompts/sections
```

### URL 和 Cookie 说明

URL 输入通过 `yt-dlp` 处理。

公开播客链接通常可以直接处理。B 站和 YouTube 链接可能因为视频权限、地区限制、年龄限制、会员状态或反爬检查而需要 cookies 或浏览器登录态。

需要登录态的视频可以尝试：

```bash
yt-dlp --cookies-from-browser chrome "https://www.bilibili.com/video/BV..."
```

或者：

```bash
yt-dlp --cookies cookies.txt "https://www.bilibili.com/video/BV..."
```

Cookies 是敏感凭证。不要打印、写进报告或提交到仓库。

### 验证安装

运行：

```bash
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/mimo_podcast_tool.py
python scripts/mimo_podcast_tool.py --help
```

`--self-test` 不会调用任何外部 API。
