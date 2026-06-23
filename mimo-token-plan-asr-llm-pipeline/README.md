# 播客视频转时间线摘要 Skill

完整文档：

- [中文完整说明](README.zh.md)
- [English README](README.en.md)

这个目录就是可安装的 skill 根目录。安装后，AI 编程 Agent 会读取这里的 `SKILL.md`，并使用 `scripts/` 和 `references/` 中的脚本与参考文档。

## 这个 Skill 有什么用

`mimo-token-plan-asr-llm-pipeline` 用来把播客、视频、网页链接或已有转写稿整理成带时间点的深度摘要 Markdown 报告。

最终报告通常包含：

- 按时间窗口生成的章节，例如 `00:00-00:03 开场主题`
- 每个时间段讲了什么的概括
- 只基于转写文本的关键引用
- 转写说明
- “核心观点速览”表格

## 安装方式

如果你的 AI IDE 支持从 GitHub 安装 skill，请粘贴这个子目录链接：

```text
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline
```

也可以把下面这段话发给 AI IDE：

```text
请从这个 GitHub 子目录安装 skill：
https://github.com/wsh-dot/podcast-to-summary-text/tree/main/mimo-token-plan-asr-llm-pipeline

只安装 mimo-token-plan-asr-llm-pipeline/ 这个目录。安装后的 skill 根目录必须直接包含 SKILL.md、scripts/、references/。
```

如果手动安装，把整个 `mimo-token-plan-asr-llm-pipeline/` 目录复制到你的 AI IDE skills 目录即可。

## 使用流程

任务开始时，Agent 应该先按顺序询问两件事：

1. ASR 转写来源和凭证：MiMo ASR、阿里 Qwen ASR、腾讯 ASR，或已有 transcript。
2. 总结方式：默认推荐当前 IDE/Agent 模型总结，也可以选择 LLM API 总结或手动导出 prompts。

更多命令示例、依赖安装和 provider 说明请看 [中文完整说明](README.zh.md)。
