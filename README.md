# 播客视频转时间线摘要 Skill

完整文档：

- [中文说明](README.zh.md)
- [English README](README.en.md)

这个仓库发布的是 `mimo-token-plan-asr-llm-pipeline` skill，用来让 CodeBuddy、Qoder Work、Codex 等 AI 编程 Agent 把播客、视频、网页链接或已有转写稿，整理成带时间点的深度摘要 Markdown 报告。

它适合长音频和长视频内容。最终报告会包含：

- 按时间窗口生成的章节，例如 `00:00-00:03 开场主题`
- 先经 LLM 校对的转写稿：补标点、断句、修正错别字、英文术语、人名和公司名
- 每个时间段讲了什么的概括
- 只基于转写文本的关键引用
- 转写说明
- 方便快速浏览的“核心观点速览”表格

## 最推荐的安装方式

如果你的 AI 编程软件支持从 GitHub 安装 skill，请优先粘贴这个 **skill 子目录链接**：

```text
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline
```

也可以直接把下面这段话发给 AI IDE：

```text
请从这个 GitHub 子目录安装 skill：
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline

只安装 mimo-token-plan-asr-llm-pipeline/ 这个目录。安装后的 skill 根目录必须直接包含 SKILL.md、scripts/、references/。
不要把仓库根目录的 README.md、README.en.md、README.zh.md 当作 skill 文件复制进去。
```

不要只粘贴仓库根地址作为自动安装地址。这个仓库根目录是说明文档入口，真正的 skill 在子目录里；如果安装器只检查根目录有没有 `SKILL.md`，直接粘根地址可能安装失败。

## Skill 目录结构

真正需要安装的是这个目录：

```text
mimo-token-plan-asr-llm-pipeline/
  SKILL.md
  scripts/
  references/
```

根目录的 `README.md`、`README.zh.md`、`README.en.md` 只是 GitHub 说明文档。

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

## 继续阅读

- [中文完整说明](README.zh.md)：包含依赖、ASR provider、总结方式、命令示例和验证方式。
- [English README](README.en.md)：英文完整说明，包含安装、provider、使用示例和验证方式。
