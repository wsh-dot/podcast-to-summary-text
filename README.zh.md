# 播客视频转时间线摘要 Skill

该仓库发布的是 `mimo-token-plan-asr-llm-pipeline` skill。

可安装的 skill 目录是：

```text
mimo-token-plan-asr-llm-pipeline/
  SKILL.md
  scripts/
  references/
```

根目录说明文件只用于 GitHub 展示。除非你的 AI IDE 明确要求，否则不要把这些说明文件复制进 skill 目录。

## 这个 Skill 有什么用

这个 skill 用来帮助 AI 编程 Agent 把播客、视频、网页链接或已有转写稿，整理成带时间点的深度摘要 Markdown 报告。

它适合长音频和长视频内容。最终报告会包含：

- 带时间点的章节
- 每个 ASR 转写窗口对应一个报告章节
- ASR 原始文本会先经 LLM 校对，再进入总结阶段
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

## 支持的输入

- 本地音频：`.mp3`、`.wav`、`.m4a`、`.flac`、`.ogg`、`.aac`
- 本地视频：`.mp4`、`.mkv`、`.avi`、`.mov`、`.webm`、`.flv`
- Bilibili/B站 URL：固定使用 BBDown，首次运行自动下载并校验 1.6.3
- `yt-dlp` 支持的其它 URL，例如小宇宙播客页面和 YouTube 链接
- 已有的带 `[HH:MM-HH:MM]` 时间窗口的 transcript

## 校对和总结方式

这个 skill 把 ASR 转写、LLM 校对和 LLM 总结拆开处理。ASR 原始文本通常没有标点、错别字多、英文术语和人名公司名容易识别错，所以默认先让 LLM 校对，再让 LLM 总结。

如果从音频、视频或 URL 开始，必须提供 ASR 凭证。LLM API 凭证不是必须的。

Agent 在任务开始时应该一个问题一个问题地询问：

1. ASR 转写来源用哪个？
2. 等 ASR 来源回答并记录后，再问校对和总结方式用哪个？

校对和总结方式有三种：

- `ide-agent`：用当前 IDE/Agent 模型先校对 ASR，再总结；最后用脚本合并和校验。默认推荐这个。
- `api-llm`：用 MiMo、Kimi、智谱、阿里、腾讯、MiniMax 或 OpenAI-compatible API 自动校对和总结。
- `manual`：只导出 prompts，用户自己复制到其它模型里完成校对和总结。

API LLM 默认按批次执行“校对后立即摘要”，最多 2 路并发。只需要最终报告时可用 `--proofread-mode inline` 合并两阶段；已有 `_校对.txt` 会自动跳过重复校对。遇到 provider 限流时使用 `--llm-concurrency 1`。

## 安装方式

### AI IDE 快速安装

如果 CodeBuddy、Qoder Work、Codex 或其它 AI 编程软件支持从 GitHub 安装 skill，优先粘贴这个 **skill 子目录链接**：

```text
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline
```

也可以直接把下面这段话发给你的 AI IDE：

```text
请从这个 GitHub 子目录安装 skill：
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline

只安装 mimo-token-plan-asr-llm-pipeline/ 这个目录。安装后的 skill 根目录必须直接包含 SKILL.md、scripts/、references/。
不要把仓库根目录的 README.md、README.en.md、README.zh.md 当作 skill 文件复制进去。
```

不建议只粘贴仓库根地址 `https://github.com/wsh-dot/podcast-to-summary-text` 作为自动安装地址。这个仓库根目录是说明文档入口，真正的 skill 在子目录里；如果安装器只检查根目录有没有 `SKILL.md`，直接粘根地址可能安装失败。

如果 AI IDE 不支持从 GitHub 子目录自动安装，请使用下面的手动安装方式。

先 clone 仓库：

```bash
git clone https://github.com/wsh-dot/podcast-to-summary-text.git
```

### 安装到 Codex Skills

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

### 安装到 Qoder Work Skills

Windows PowerShell：

```powershell
mkdir "$env:USERPROFILE\.qoderworkcn\skills" -Force
Copy-Item -Recurse ".\podcast-to-summary-text\mimo-token-plan-asr-llm-pipeline" "$env:USERPROFILE\.qoderworkcn\skills\mimo-token-plan-asr-llm-pipeline"
```

如果你的 AI IDE 使用其它 skill 目录，把 `mimo-token-plan-asr-llm-pipeline/` 整个目录复制进去即可。

## 依赖

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

## ASR 凭证

选择一个 ASR 来源：

| ASR 来源 | 凭证 |
|---|---|
| MiMo ASR | `--api-key`、`--asr-api-key` 或 `MIMO_API_KEY` |
| 阿里 Qwen ASR | `--asr-provider aliyun-qwen --asr-api-key`、`DASHSCOPE_API_KEY` 或 `ALIYUN_API_KEY` |
| 腾讯 ASR | `--asr-provider tencent --tencent-secret-id --tencent-secret-key` |
| 已有 transcript | 不需要 ASR API，使用 `--transcript-input` |

不要提交 API key、cookies、浏览器 profile 或导出的凭证文件。

## 常用命令

进入 skill 目录：

```bash
cd podcast-to-summary-text/mimo-token-plan-asr-llm-pipeline
```

MiMo ASR，然后用当前 IDE/Agent 模型校对和总结：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

阿里 Qwen ASR，然后用当前 IDE/Agent 模型校对和总结：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider aliyun-qwen --asr-api-key "sk-xxxx"
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_agent_sections
```

已有 transcript，然后用 API LLM 自动校对和总结：

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --llm-provider kimi --llm-api-key "sk-xxxx"
```

手动导出 prompts：

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_ide_prompts/sections
```

## URL 和 Cookie 说明

B站链接固定使用 BBDown，失败时不会回退 `yt-dlp`。首次运行会从官方 Release 下载并校验固定版本 1.6.3；也可以通过 `--bbdown-path` 或 `BBDOWN_PATH` 使用已有可执行文件。小宇宙、YouTube 和其它普通 URL 仍由 `yt-dlp` 处理。

B站需要登录态时传入网页 cookie：

```bash
python scripts/mimo_podcast_tool.py "https://www.bilibili.com/video/BV..." --transcribe-only --api-key "tp-xxxx" --bilibili-cookie "SESSDATA=..."
```

使用 `--no-bbdown-auto-install` 可关闭自动安装；关闭后必须配置 BBDown 路径。

Cookies 是敏感凭证。不要打印、写进报告或提交到仓库。

## 验证安装

运行：

```bash
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/mimo_podcast_tool.py
python scripts/mimo_podcast_tool.py --help
```

`--self-test` 不会调用任何外部 API。
