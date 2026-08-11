import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "mimo-token-plan-asr-llm-pipeline" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mimo_podcast_tool import load_validated_timeline_report, parse_transcript_blocks
from visual_reader import render_visual_brief


EXAMPLE = ROOT / "examples" / "yao-shunyu-interview"
TRANSCRIPT = EXAMPLE / "calibrated-transcript.txt"
REPORT = EXAMPLE / "window-by-window-analysis.md"
MANIFEST = EXAMPLE / "visual-brief-manifest.v2.json"
OUTPUT = ROOT / "docs" / "index.html"
SOURCE_URL = "https://www.bilibili.com/video/BV1YR5E6EE9o"


def sourced(text, *windows):
    return {"text": text, "source_windows": list(windows)}


def interpretation(title, text, *windows):
    return {"title": title, "text": text, "source_windows": list(windows)}


def process(title, windows, items):
    return {
        "type": "process",
        "title": sourced(title, *windows),
        "items": [sourced(text, *item_windows) for text, item_windows in items],
    }


def comparison(title, windows, items):
    return {
        "type": "comparison",
        "title": sourced(title, *windows),
        "items": [
            {"label": label, "value": value, "source_windows": list(item_windows)}
            for label, value, item_windows in items
        ],
    }


def relationship(title, windows, items):
    return {
        "type": "relationship",
        "title": sourced(title, *windows),
        "items": [
            {"from": start, "to": end, "label": label, "source_windows": list(item_windows)}
            for start, end, label, item_windows in items
        ],
    }


def split_summary(summary, titles, windows):
    sentences = re.findall(r"[^。！？]+[。！？]?", summary)
    groups = []
    quotient, remainder = divmod(len(sentences), len(titles))
    cursor = 0
    for index in range(len(titles)):
        size = quotient + (1 if index < remainder else 0)
        groups.append("".join(sentences[cursor:cursor + size]))
        cursor += size
    return [
        {"title": sourced(title, *windows), "text": sourced(text, *windows)}
        for title, text in zip(titles, groups)
    ]


def build_manifest(blocks):
    windows = [block["window"] for block in blocks]
    chapter_windows = [windows[0:18], windows[18:36], windows[36:48], windows[48:66], windows[66:77]]
    summaries = [
        "开场从 Gemini、OpenAI、Anthropic 的相对位置谈起。姚舜宇认为，今天的模型差距仍真实存在，却很难只靠基准榜单说明；当评测趋于饱和，关键变成谁先找到尚未被定义好的任务。OpenClaw、Manus、Cursor 等产品又说明另一层竞争：模型能力可以被快速追平，真正拉开体验的是任务编排、上下文管理和产品入口。Coding 之所以成为第一个高价值突破口，是因为代码天然具备可执行反馈、GitHub 数据与明确奖励。它把研究和软件工作显著加速，但是否直接减少岗位，要看组织如何重新分配被释放的时间，而不是把“效率提升”简单等同于“人员替代”。",
        "访谈把中国 AI 的优势放在更宽的产业背景里：硬件供应链、消费产品和多模态生成能够形成不同于美国模型实验室的路线，Seedance、豆包与机器人机会都来自这种组合。随后话题转入姚舜宇的成长经历。他并非沿着一条预设的 AI 精英路径前进，而是在中学机会、物理竞赛和大学研究中不断换方向。凝聚态与拓扑物理训练让他习惯从结构、对称性和实验反馈理解问题；对高能理论的犹疑也来自同一标准：缺少可验证数据时，优美理论可能长期无法被检验。这段经历解释了他后来为什么看重实验闭环、清晰定义和可证伪性。转向 AI 不是抛弃物理，而是选择一个能更快试错、能让想法接受现实反馈的研究场。",
        "进入 Anthropic 后，姚舜宇参与了 Claude 3.7 相关工作，也亲历大规模强化学习从不确定探索变成可运行工程。这里的难点不是一个神秘公式，而是环境、奖励、数据、基础设施与训练稳定性的共同约束。组织采取更明确的自上而下目标，让团队集中资源补齐关键链条；Coding 因反馈清晰而成为重要训练场。Claude 3.7 的进步因此更适合解释为集体成果，而不是某位研究员的单点发明。Anthropic 的高度专注带来纵向深度，也形成边界：多模态生成、底层工程和更广的研究方向不是其主要投入。离开这家公司，既有文化与价值观因素，也有重新扩展学习面的动机。",
        "Google DeepMind 提供的是横向广度：预训练、后训练、多模态、硬件和产品处于同一大系统。Gemini 2.5 是模型追赶的信号，Nano Banana 则展示了另一种决定性力量——爆款产品先把用户带入应用，后续模型再完成留存。姚舜宇当前更关心 ML coding 与 long horizon。前者可加速从芯片到模型的全栈 AI 研发；后者试图让模型在有限上下文里完成更长任务，通过选择性遗忘、外部记录和检索持续维护状态。更远的一步，是让 AI 独立完成研究循环。聊天机器人、搜索和 Super App 因而都不是终局答案，竞争仍围绕新交互形态、上下文管理与端到端执行展开。",
        "最后一部分把技术判断落到组织与职业。学术项目强调个人负责，公司研究则要求对整个系统负责；每个指标都可能被优化甚至被钻空子，因此可靠、能理解他人工作的研究者比单纯聪明更稀缺。中美公司也形成不同商业路径：美国企业软件偏直接收费，中国消费产品擅长先构建复杂循环，再从生态变现。对年轻人而言，纯语言模型已不再是蓝海，但多模态、机器人、世界模型和科学问题仍有空间。姚舜宇对“英雄”的理解也随之变化：早期范式跳变可能属于少数先驱，规模化阶段更像英雄集体。直接表达可以有锋芒，但判断必须定义清楚、逻辑自洽并接受客观检验。",
    ]
    card_titles = [
        ["榜单之外定义任务", "产品入口放大能力", "代码反馈形成闭环", "效率不等于替代"],
        ["产业组合塑造优势", "成长路径来自试错", "物理训练强调证伪", "反馈决定研究选择"],
        ["强化学习依赖系统", "明确目标补齐链条", "突破来自团队协作", "专注也形成边界"],
        ["横向广度成为优势", "产品完成获客留存", "外部记忆延长任务", "研究循环仍待突破"],
        ["系统责任高于单点", "商业路径各有循环", "新方向仍有空白", "可靠协作替代英雄叙事"],
    ]
    visuals = [
        [
            relationship("前沿 AI 的三层竞争", ["00:21-00:24", "00:24-00:27", "00:45-00:48"], [
                ("模型能力", "可完成的任务", "提供上限", ["00:03-00:06", "00:24-00:27"]),
                ("任务编排", "稳定工作流", "降低使用成本", ["00:21-00:24", "00:27-00:30"]),
                ("产品分发", "用户习惯", "放大影响", ["00:42-00:45", "00:45-00:48"]),
            ]),
            process("为什么 Coding 最先突破", ["00:30-00:33", "00:33-00:36"], [
                ("海量公开代码形成训练数据", ["00:30-00:33"]),
                ("程序能执行并返回明确结果", ["00:30-00:33"]),
                ("模型可反复尝试并修正", ["00:33-00:36"]),
                ("能力进入真实软件工作流", ["00:33-00:36", "00:36-00:39"]),
            ]),
        ],
        [
            comparison("两类产业优势", ["00:54-00:57", "00:57-01:00", "01:03-01:06"], [
                ("美国实验室", "模型、企业软件与直接变现", ["00:54-00:57", "01:03-01:06"]),
                ("中国团队", "供应链、消费产品与多模态组合", ["00:57-01:00", "01:03-01:06"]),
            ]),
            process("研究选择的反馈尺度", ["01:18-01:21", "01:33-01:36", "01:39-01:42"], [
                ("提出结构或理论假设", ["01:18-01:21"]),
                ("寻找实验与数据约束", ["01:33-01:36", "01:39-01:42"]),
                ("根据反馈修正理解", ["01:39-01:42"]),
                ("选择能持续闭环的研究场", ["01:42-01:45", "01:45-01:48"]),
            ]),
        ],
        [relationship("大规模强化学习不是单一算法", ["01:54-01:57", "02:00-02:03", "02:03-02:06"], [
            ("任务环境", "可执行反馈", "定义行为", ["01:54-01:57", "02:00-02:03"]),
            ("奖励与数据", "训练方向", "提供信号", ["02:00-02:03"]),
            ("基础设施", "稳定规模化", "保证运行", ["02:03-02:06", "02:06-02:09"]),
        ])],
        [
            process("Long horizon 的记忆循环", ["02:42-02:45", "02:45-02:48"], [
                ("在有限上下文中执行当前步骤", ["02:42-02:45"]),
                ("丢弃与目标无关的细节", ["02:42-02:45"]),
                ("把关键状态写入外部记忆", ["02:45-02:48"]),
                ("按需检索并继续长期任务", ["02:45-02:48"]),
            ]),
            process("产品如何放大模型追赶", ["02:48-02:51", "02:51-02:54"], [
                ("Gemini 2.5 建立能力可信度", ["02:48-02:51"]),
                ("Nano Banana 制造爆款入口", ["02:51-02:54"]),
                ("大量用户进入 Gemini 应用", ["02:51-02:54"]),
                ("后续模型把流量转成留存", ["02:51-02:54"]),
            ]),
        ],
        [comparison("两个时代的研究推进方式", ["03:18-03:21", "03:39-03:42"], [
            ("范式跳变期", "少数洞见或小团队找到关键方向", ["03:39-03:42"]),
            ("规模化阶段", "可靠组织把能力稳定推向产品与系统", ["03:18-03:21"]),
        ])],
    ]
    chapter_titles = [
        "模型竞赛真正争的是什么",
        "从中国产品到物理学训练",
        "Anthropic：一次大规模强化学习跃迁",
        "Google：把广度变成系统能力",
        "没有终局，只有更可靠的系统",
    ]
    evidence = [
        [("00:24-00:27", "产品外壳与底层模型的护城河并不相同"), ("00:30-00:33", "代码任务拥有清晰反馈与大规模数据"), ("00:45-00:48", "模型能力与产品入口共同决定市场竞争")],
        [("00:57-01:00", "多模态与硬件生态为中国团队提供差异化入口"), ("01:18-01:21", "物理训练强调结构、模型与可验证反馈"), ("01:39-01:42", "缺少实验反馈会让理论方向难以收敛")],
        [("02:03-02:06", "大尺度强化学习需要环境与工程系统共同成立"), ("02:18-02:21", "Claude 3.7 的能力来自团队协作而非单点英雄"), ("02:21-02:24", "高度专注意味着研究广度上的主动取舍")],
        [("02:42-02:45", "长期任务依赖选择性遗忘、记录与检索"), ("02:51-02:54", "Nano Banana 获客后由新模型承接留存"), ("03:09-03:12", "ML coding 与 long horizon 是当前重点方向")],
        [("03:18-03:21", "公司研究要求个体对组织整体结果负责"), ("03:30-03:33", "人才稀缺更多来自训练环境与真实机会"), ("03:33-03:36", "语言模型之外仍有大量未开垦问题")],
    ]
    chapters = []
    for index, windows_for_chapter in enumerate(chapter_windows):
        chapters.append({
            "id": ["models-products-and-coding", "china-products-and-physics", "anthropic-and-claude", "gemini-long-horizon", "organizations-and-careers"][index],
            "title": sourced(chapter_titles[index], *windows_for_chapter),
            "summary": sourced(summaries[index], *windows_for_chapter),
            "summary_cards": split_summary(summaries[index], card_titles[index], windows_for_chapter),
            "source_windows": windows_for_chapter,
            "evidence": [{"window": window, "label": label} for window, label in evidence[index]],
            "visuals": visuals[index],
        })
    return {
        "version": 2,
        "one_line_overview": sourced("AI 竞争正在从单点模型突破转向可验证的系统能力。", "00:03-00:06", "02:03-02:06", "03:18-03:21"),
        "overview": sourced("这场近四小时访谈不是一份模型榜单，而是一张前沿 AI 的工作地图。姚舜宇从 Anthropic 到 Google DeepMind 的经历，把模型竞争、产品分发、强化学习、长期任务、组织协作与个人选择连在一起。最重要的判断是：能力突破正在从少数洞见转向大规模系统工程，但真正未被解决的问题仍很多。", "00:00-00:03", "00:42-00:45", "01:48-01:51", "02:30-02:33", "03:09-03:12", "03:30-03:33"),
        "core_insights": [
            sourced("前沿模型的短期差距会快速缩小，单一基准也越来越难代表真实价值。竞争正转向谁能定义新问题、把能力嵌入产品，并通过分发和留存形成用户习惯。", "00:03-00:06", "00:24-00:27", "00:45-00:48", "02:51-02:54", "03:06-03:09"),
            sourced("Coding 最先爆发并非偶然：代码有清晰反馈、海量数据和可执行环境。下一步是让模型跨更长时间保持目标，把写代码、跑实验、分析结果和提出新假设连成研究闭环。", "00:30-00:33", "00:33-00:36", "02:36-02:39", "02:42-02:45", "03:09-03:12"),
            sourced("大模型进入规模化阶段后，个人英雄主义的解释力下降。可靠的人、清晰的评价框架、跨团队协作和对整体结果负责，决定实验室能否把偶然突破变成稳定能力。", "02:27-02:30", "02:30-02:33", "03:15-03:18", "03:18-03:21", "03:30-03:33"),
            sourced("年轻人的机会没有消失，只是热点已经迁移。纯语言模型不再是蓝海，多模态、机器人、世界模型与 AI for Science 仍有空白；比追随热点更重要的是找到尚未定义好的问题。", "00:57-01:00", "01:03-01:06", "03:12-03:15", "03:33-03:36", "03:36-03:39"),
        ],
        "developer_takeaways": [
            interpretation("RAG 与上下文工程", "把上下文理解为可维护的任务状态，而不只是一次检索：区分当前目标、外部记录、选择性遗忘与按需取回，并为每次状态更新保留来源。这样才能让 Agent 在有限上下文中持续执行长任务。可以从带 checkpoint 的编码任务开始，测量跨阶段状态恢复是否准确。", "02:42-02:45", "02:45-02:48"),
            interpretation("模型训练与行为数据", "代码任务的价值来自数据、执行环境和明确反馈同时存在；大规模强化学习还依赖环境、奖励、基础设施与稳定性共同成立。因此训练 Agent 时不应只保存输入输出，还要记录工具调用、执行结果、失败重试和奖励依据，用可复现轨迹驱动后续训练与评测。", "00:30-00:33", "00:33-00:36", "02:00-02:03", "02:03-02:06"),
            interpretation("Agent 构建与可靠性", "把 Agent 当作系统工程而不是单次模型调用：明确任务定义、工具边界、评价指标和整体负责人，并假设任何单一指标都会被过度优化。上线时应同时观察任务成功率、无效工具调用、恢复次数和人工接管率，用多指标约束局部最优。", "02:03-02:06", "03:18-03:21", "03:27-03:30"),
            interpretation("Agent 开发学习路径", "先做代码这类反馈清晰的单 Agent 任务，掌握工具调用与自动验证；再加入外部记忆和 checkpoint，练习长任务恢复；随后构建能运行实验、分析结果并提出下一步假设的闭环。每一阶段先有可执行评测，再扩大任务跨度和自主程度。", "00:30-00:33", "00:33-00:36", "02:42-02:45", "03:09-03:12"),
            interpretation("从能力到产品闭环", "模型领先并不自动变成用户价值，任务编排、产品入口、分发和留存会共同决定结果。开发者应把模型升级与工作流改造分开评估：用同一任务集比较模型替换前后效果，再通过产品实验验证入口、交互和留存是否真正放大能力。", "00:21-00:24", "00:24-00:27", "00:42-00:45", "00:45-00:48", "02:51-02:54"),
        ],
        "critical_thinking": [
            interpretation("岗位影响缺少因果证据", "访谈提出效率提升未必直接减少岗位，但现有材料没有提供招聘、产出和组织调整的对照数据。这个判断应视为待验证假设，需要按团队和任务类型追踪自动化前后的岗位结构，而不能从个别工具体验直接外推。", "00:36-00:39", "00:39-00:42"),
            interpretation("模型与产品贡献难拆分", "Nano Banana 与 Gemini 的案例说明产品入口可能放大模型追赶，但访谈没有隔离模型质量、渠道曝光和交互设计各自的贡献。需要通过版本分流、渠道控制和留存分层，才能判断增长来自能力本身还是分发优势。", "02:48-02:51", "02:51-02:54"),
            interpretation("组织经验不宜普遍化", "Anthropic 与 Google 的专注或广度取舍来自特定规模、人才和战略背景。单一访谈能解释个人观察，却不足以证明哪种组织结构普遍更优；应比较不同团队在相似任务、预算和时间范围内的交付稳定性。", "02:21-02:24", "02:24-02:27", "03:18-03:21"),
        ],
        "further_questions": [
            interpretation("怎样评测 Long-horizon Agent", "建立 30 分钟、2 小时和跨天三档任务集，记录目标保持率、checkpoint 恢复准确率、无效上下文占比和最终成功率；比较无外部记忆、摘要记忆与结构化状态存储三种方案。", "02:42-02:45", "02:45-02:48"),
            interpretation("怎样拆分模型和产品价值", "对同一工作流做二维实验：固定界面替换模型、固定模型替换任务编排；分别测任务成功率、完成时长、次日复用和人工接管率，以确定下一笔投入应放在模型、Agent 编排还是产品入口。", "00:21-00:24", "00:24-00:27", "00:45-00:48"),
            interpretation("怎样构建研究型 Agent", "从代码修复闭环扩展到小型实验闭环：Agent 提出假设、修改实验、运行、读取结果并决定下一步。先限定工具和预算，评测假设质量、实验可复现性及失败恢复，再逐步增加自主回合。", "00:33-00:36", "02:36-02:39", "03:09-03:12"),
            interpretation("怎样选择 Agent 学习项目", "优先选择结果可自动判定、工具接口稳定、失败可回滚的真实任务；每完成一类任务，再加入记忆、并发或多角色协作中的一个变量。用连续四周的成功率和复盘数据判断是否进入下一阶段。", "00:30-00:33", "03:18-03:21", "03:30-03:33"),
        ],
        "chapters": chapters,
    }


def main():
    transcript = TRANSCRIPT.read_text(encoding="utf-8")
    blocks = parse_transcript_blocks(transcript)
    if len(blocks) != 77:
        raise RuntimeError(f"expected 77 transcript windows, got {len(blocks)}")
    report = load_validated_timeline_report(REPORT, transcript)
    manifest = build_manifest(blocks)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_visual_brief(
        calibrated_transcript_blocks=blocks,
        validated_timeline_report=report,
        trusted_metadata={"title": "对姚舜宇的4小时访谈", "duration_seconds": 13740},
        media_source={"kind": "video", "url": SOURCE_URL},
        manifest=manifest,
        output_destination=OUTPUT,
    )
    print(f"wrote {MANIFEST}")
    print(f"rendered {OUTPUT}")


if __name__ == "__main__":
    main()
