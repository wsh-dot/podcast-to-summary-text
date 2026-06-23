# 播客视频转时间线摘要 Skill

[返回默认说明](README.md) | [English README](README.en.md)

这个目录是 `mimo-token-plan-asr-llm-pipeline` 的 skill 根目录。它用来帮助 AI 编程 Agent 把播客、视频、网页链接或已有转写稿，整理成带时间点的深度摘要 Markdown 报告。

## 核心能力

- 支持本地音频、本地视频、`yt-dlp` 可访问的 URL，以及已有 transcript。
- 默认生成严格的时间线报告。
- 每个 `[HH:MM-HH:MM]` 转写窗口对应一个报告章节。
- 报告末尾生成“核心观点速览”表格。
- ASR 转写和 LLM 总结分离：ASR API 必需，LLM API 可选。
- 默认推荐使用当前 IDE/Agent 模型总结，减少额外 LLM API 依赖。

## 目录结构

```text
mimo-token-plan-asr-llm-pipeline/
  SKILL.md
  README.md
  README.zh.md
  README.en.md
  scripts/
  references/
```

`SKILL.md` 是 AI IDE 读取的 skill 指令；`scripts/` 是转写、分批、合并和校验脚本；`references/` 是 API、provider 和报告格式参考。

## 快速安装

如果 CodeBuddy、Qoder Work、Codex 或其它 AI IDE 支持从 GitHub 安装 skill，请粘贴这个子目录链接：

```text
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline
```

推荐发给 AI IDE 的安装提示：

```text
请从这个 GitHub 子目录安装 skill：
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline

只安装 mimo-token-plan-asr-llm-pipeline/ 这个目录。安装后的 skill 根目录必须直接包含 SKILL.md、scripts/、references/。
```

## 手动安装

先 clone 仓库：

```bash
git clone https://github.com/wsh-dot/podcast-to-summary-text.git
```

安装到 Codex Skills，Windows PowerShell：

```powershell
mkdir "$env:USERPROFILE\.codex\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.codex\skills\mimo-token-plan-asr-llm-pipeline"
```

安装到 Qoder Work Skills，Windows PowerShell：

```powershell
mkdir "$env:USERPROFILE\.qoderworkcn\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.qoderworkcn\skills\mimo-token-plan-asr-llm-pipeline"
```

其它 AI IDE 也类似：把 `mimo-token-plan-asr-llm-pipeline/` 整个目录复制到该 IDE 的 skills 目录。

## 依赖

Python 包：

```bash
pip install openai yt-dlp
```

系统依赖：

```bash
ffmpeg
```

Windows 可使用：

```powershell
winget install Gyan.FFmpeg
```

如果使用腾讯 ASR，还需要：

```bash
pip install tencentcloud-sdk-python
```

## 默认流程

Agent 调用这个 skill 时，应该先一个问题一个问题地确认：

1. ASR 转写来源：MiMo ASR、阿里 Qwen ASR、腾讯 ASR，或已有 transcript。
2. 总结方式：当前 IDE/Agent 模型总结、API LLM 总结，或只导出 prompts。

默认推荐：

- ASR：由用户提供对应 provider 的 API 凭证。
- 总结：`ide-agent`，也就是当前 IDE/Agent 模型总结。

## 常用命令

只做 ASR 转写，保存带时间窗口的 transcript：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
```

使用已有 transcript，并导出给当前 IDE/Agent 分批总结的 prompts：

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
```

使用已有 transcript 和 API LLM 生成报告：

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider kimi --llm-api-key "sk-xxxx"
```

运行自检：

```bash
python scripts/mimo_podcast_tool.py --self-test
```

## 更多参考

- [providers.md](references/providers.md)：ASR 和 LLM provider 边界。
- [providers.en.md](references/providers.en.md)：ASR 和 LLM provider 英文参考。
- [timeline-report-format.md](references/timeline-report-format.md)：时间线报告格式。
- [timeline-report-format.en.md](references/timeline-report-format.en.md)：时间线报告格式英文参考。
- [api-reference.md](references/api-reference.md)：MiMo Token Plan API 参考。
- [api-reference.en.md](references/api-reference.en.md)：MiMo Token Plan API 英文参考。
