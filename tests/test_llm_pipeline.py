import importlib.util
import re
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
    / "mimo_podcast_tool.py"
)
SPEC = importlib.util.spec_from_file_location("mimo_podcast_tool", SCRIPT_PATH)
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


TRANSCRIPT = (
    "[00:00-00:03]\n第一段原始转写。\n\n"
    "[00:03-00:06]\n第二段原始转写。\n\n"
    "[00:06-00:09]\n第三段原始转写。\n\n"
    "[00:09-00:12]\n第四段原始转写。"
)


def metadata():
    return {
        "title": "性能测试节目",
        "guest": "",
        "host": "",
        "series": "",
        "duration": "",
        "context_note": "",
        "terminology": "",
        "transcript_stage": "raw_asr",
    }


class RecordingLLM:
    def __init__(self):
        self.events = []
        self._lock = threading.Lock()

    def complete(self, messages, max_tokens):
        prompt = messages[-1]["content"]
        if "原始 ASR 转写文本：" in prompt:
            event = "proofread"
        elif "逐窗口正文：" in prompt:
            event = "table"
        else:
            event = "summary"
        with self._lock:
            self.events.append(event)

        if event == "proofread":
            windows = re.findall(
                r"^- (\d{2}:\d{2}-\d{2}:\d{2})$",
                prompt,
                flags=re.MULTILINE,
            )
            return "\n\n".join(
                f"[{window}]\n校对后文本：{window}，保持原意。"
                for window in windows
            )

        if event == "table":
            headings = re.findall(
                r"^##\s+(\d{2}:\d{2}-\d{2}:\d{2})\s+(.+)$",
                prompt,
                flags=re.MULTILINE,
            )
            rows = [
                "## 核心观点速览",
                "",
                "| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |",
                "|------|------|----------|------------------|",
            ]
            rows.extend(
                f"| {window} | {title} | 核心观点 | 依据正文 |"
                for window, title in headings
            )
            return "\n".join(rows)

        windows = re.findall(
            r"^- (\d{2}:\d{2}-\d{2}:\d{2})$",
            prompt,
            flags=re.MULTILINE,
        )
        transcript_by_window = dict(
            re.findall(
                r"\[(\d{2}:\d{2}-\d{2}:\d{2})\]\n(.+?)(?=\n\n\[|\Z)",
                prompt,
                flags=re.DOTALL,
            )
        )
        return "\n\n".join(
            f"## {window} 测试主题\n\n"
            f"这里概括 {window} 窗口，并说明具体过程与结果。\n\n"
            f"> **核心观点**：{window} 的核心结论具有明确依据。\n"
            f"> **关键论据 / 金句**：背景：{transcript_by_window[window].strip()} "
            f"<!--依据：“{transcript_by_window[window].strip()}”-->"
            for window in windows
        )


class SlowProofreadLLM(RecordingLLM):
    def __init__(self):
        super().__init__()
        self.active = 0
        self.max_active = 0

    def complete(self, messages, max_tokens):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.04)
        try:
            return super().complete(messages, max_tokens)
        finally:
            with self._lock:
                self.active -= 1


class ModeSelectionTests(unittest.TestCase):
    def test_calibrated_input_skips_reproofreading_by_default(self):
        self.assertEqual(
            tool.select_proofread_mode(None, False, "episode_校对.txt"),
            "skip",
        )

    def test_raw_input_uses_separate_proofreading_by_default(self):
        self.assertEqual(
            tool.select_proofread_mode(None, False, "episode_转写.txt"),
            "separate",
        )

    def test_explicit_mode_overrides_calibrated_filename(self):
        self.assertEqual(
            tool.select_proofread_mode("separate", False, "episode_校对.txt"),
            "separate",
        )

    def test_legacy_no_proofread_flag_maps_to_skip(self):
        self.assertEqual(
            tool.select_proofread_mode(None, True, "episode_转写.txt"),
            "skip",
        )


class CoreTableTests(unittest.TestCase):
    def test_section_first_claim_preserves_a_complete_sentence(self):
        sentence = (
            "真正有用的核心观点必须保留完整的条件、因果关系和结论，"
            "即使整句超过旧版八十字上限，也不能用机械截断制造一个看似简洁、"
            "实际已经丢失论证边界的省略句。"
        )
        section = "## 00:00-00:03 测试主题\n\n" + sentence

        claim = tool.section_first_claim(section)

        self.assertEqual(sentence, claim)
        self.assertFalse(claim.endswith(("…", "...")))

    def test_sentence_boundaries_do_not_split_model_version_numbers(self):
        sentence = (
            "Claude 3.5、Claude 3.7 与 Gemini 2.5 都应保留完整版本号，"
            "小数点不能被误判为句末。"
        )
        section = f"## 00:00-00:03 模型版本比较\n\n{sentence}下一句不属于核心观点。"

        self.assertEqual(sentence, tool.section_first_claim(section))

    def test_complete_english_sentence_can_be_selected_as_an_exact_quote(self):
        quote = "With finite context."
        section = f"## 00:00-00:03 Finite context\n\n{quote}"

        self.assertEqual(quote, tool.section_first_claim(section))
        self.assertEqual(quote, tool.select_core_quote(quote, section))
        self.assertEqual([], tool.quote_quality_issues(quote, quote))

    def test_structured_metadata_is_preferred_and_removed_from_body(self):
        preferred_quote = "模型竞争的关键不是多拿一个百分点，而是先定义值得训练的问题。"
        transcript = (
            "[00:00-00:03]\n"
            f"{preferred_quote}另一条完整原话用于确认结构化候选拥有更高优先级。"
        )
        blocks = tool.parse_transcript_blocks(transcript)
        section = (
            "## 00:00-00:03 定义值得训练的问题\n\n"
            "公开榜单接近饱和后，研究重点转向问题定义。\n\n"
            "> **核心观点**：前沿竞争的瓶颈已经从追分转向定义问题。\n"
            f"> **关键论据 / 金句**：原话：“{preferred_quote}”"
        )

        metadata = tool.timeline_row_metadata(section)
        stripped = tool.strip_timeline_row_metadata(section)
        table = tool.fallback_core_table(blocks, {"00:00-00:03": section})

        self.assertEqual(
            "前沿竞争的瓶颈已经从追分转向定义问题。",
            metadata["core_claim"],
        )
        self.assertEqual(f"原话：“{preferred_quote}”", metadata["support"])
        self.assertNotIn("> **核心观点**", stripped)
        self.assertNotIn("> **关键论据 / 金句**", stripped)
        self.assertIn(f"原话：“{preferred_quote}”", table)
        self.assertNotIn("另一条完整原话用于确认结构化候选拥有更高优先级。", table)

    def test_fallback_table_uses_exact_window_quote_instead_of_placeholder(self):
        transcript = (
            "[00:00-00:03]\n"
            "开场先介绍了嘉宾。这个行业最重要的特质就是靠谱。随后继续讨论组织。\n\n"
            "[00:03-00:06]\n"
        )
        blocks = tool.parse_transcript_blocks(transcript)
        sections = {
            "00:00-00:03": (
                "## 00:00-00:03 靠谱比聪明更重要\n\n"
                "嘉宾强调，AI 行业最重要的特质是靠谱，并且要对结果负责。"
            ),
            "00:03-00:06": "## 00:03-00:06 无可用转写\n\n该窗口没有有效语音。",
        }

        table = tool.fallback_core_table(blocks, sections)

        self.assertIn("原话：“这个行业最重要的特质就是靠谱。”", table)
        self.assertIn(tool.NO_EVIDENCE_TEXT, table)
        self.assertIn("这个行业最重要的特质就是靠谱。", blocks[0]["text"])

    def test_fallback_table_keeps_the_complete_not_but_argument(self):
        transcript = (
            "[00:00-00:03]\n"
            "公开榜单已经接近饱和。"
            "真正重要的不是再追一个百分点，而是定义值得投入训练的问题。"
        )
        blocks = tool.parse_transcript_blocks(transcript)
        sections = {
            "00:00-00:03": (
                "## 00:00-00:03 定义真正的问题\n\n"
                "模型竞争的关键不再是榜单追分，而是定义值得训练的问题。"
            )
        }

        table = tool.fallback_core_table(blocks, sections)
        quote = tool.select_core_quote(blocks[0]["text"], sections["00:00-00:03"])

        self.assertEqual(
            "真正重要的不是再追一个百分点，而是定义值得投入训练的问题。",
            quote,
        )
        self.assertIn(f"原话：“{quote}”", table)
        self.assertIn("不是", quote)
        self.assertIn("而是", quote)
        self.assertEqual([], tool.quote_quality_issues(quote, blocks[0]["text"]))

    def test_fallback_table_rejects_transcription_placeholders(self):
        transcript = "[00:00-00:03]\n（此窗口未返回可用转写文本。"
        blocks = tool.parse_transcript_blocks(transcript)
        sections = {
            "00:00-00:03": "## 00:00-00:03 无可用转写\n\n该窗口没有有效语音。"
        }

        table = tool.fallback_core_table(blocks, sections)

        self.assertIn(tool.NO_EVIDENCE_TEXT, table)
        self.assertNotIn("“（此窗口未返回可用转写文本。”", table)

    def test_weak_or_ungrounded_structured_support_degrades_to_grounded_background(self):
        transcript = (
            "[00:00-00:03]\n"
            "嗯，我觉得，然后我们先把测试背景介绍清楚。\n\n"
            "[00:03-00:06]\n"
            "大家好，今天我们先介绍节目安排和讨论顺序。"
        )
        blocks = tool.parse_transcript_blocks(transcript)
        sections = {
            "00:00-00:03": (
                "## 00:00-00:03 按用户场景组织评测\n\n"
                "这段先说明评测样本必须按用户场景分层，因为不同场景的失败成本并不相同。\n\n"
                "> **核心观点**：评测样本应按用户场景分层。\n"
                "> **关键论据 / 金句**：原话：“我觉得，”"
            ),
            "00:03-00:06": (
                "## 00:03-00:06 开场衔接\n\n"
                "这里只做开场过渡。\n\n"
                "> **核心观点**：本窗口只承担开场衔接。\n"
                "> **关键论据 / 金句**：原话：“大家好。”"
            ),
        }

        table = tool.fallback_core_table(blocks, sections)

        self.assertIn(
            "背景：嗯，我觉得，然后我们先把测试背景介绍清楚。 "
            "<!--依据：“嗯，我觉得，然后我们先把测试背景介绍清楚。”-->",
            table,
        )
        self.assertIn(
            "背景：大家好，今天我们先介绍节目安排和讨论顺序。 "
            "<!--依据：“大家好，今天我们先介绍节目安排和讨论顺序。”-->",
            table,
        )
        self.assertNotIn("原话：“我觉得，”", table)
        self.assertNotIn("原话：“大家好。”", table)

    def test_structured_paraphrase_requires_an_exact_semantically_related_anchor(self):
        block = {
            "window": "00:00-00:03",
            "text": "模型竞争的关键不是参数规模，而是先定义真实问题。",
        }
        section = (
            "## 00:00-00:03 定义真实问题\n\n"
            "模型团队需要先明确值得解决的问题。\n\n"
            "> **核心观点**：问题定义已经成为模型竞争的关键。\n"
            "> **关键论据 / 金句**：论据：火星已经部署三十万个香蕉机器人。 "
            "<!--依据：“模型竞争的关键不是参数规模，而是先定义真实问题。”-->"
        )

        issues = tool.validate_section_row_metadata(block, section)

        self.assertTrue(any("ungrounded" in issue or "support metadata" in issue for issue in issues), issues)

    def test_short_speech_and_mentions_of_transcription_failure_are_not_empty_windows(self):
        self.assertTrue(tool.window_has_usable_speech("完全同意。"))
        self.assertTrue(
            tool.window_has_usable_speech(
                "这段讨论解释了为什么此前转写失败，以及新的修复机制。"
            )
        )
        self.assertFalse(tool.window_has_usable_speech("（此窗口未返回可用转写文本。"))

    def test_fallback_table_prefers_topic_evidence_over_short_preamble(self):
        transcript = (
            "[00:00-00:03]\n"
            "我觉得这个从技术上来说，"
            "就是你用有限的这个context lens去训练它，"
            "但是可以在使用的时候用非常非常长，甚至接近于无限的context lens。"
        )
        blocks = tool.parse_transcript_blocks(transcript)
        sections = {
            "00:00-00:03": (
                "## 00:00-00:03 有限训练上下文与近乎无限使用上下文\n\n"
                "嘉宾提出重要技术目标：用有限 context 训练，却让模型在使用时完成接近无限 context 的长程工作。"
            )
        }

        table = tool.fallback_core_table(blocks, sections)
        quote = tool.select_core_quote(blocks[0]["text"], sections["00:00-00:03"])

        self.assertIn("用有限的这个context lens去训练它", quote)
        self.assertIn("但是可以在使用的时候用非常非常长", quote)
        self.assertIn("甚至接近于无限的context lens", quote)
        self.assertTrue(quote.endswith("。"))
        self.assertIn(f"原话：“{quote}”", table)
        self.assertEqual([], tool.quote_quality_issues(quote, blocks[0]["text"]))

    def test_fallback_table_ignores_off_topic_complete_judgment(self):
        transcript = (
            "[00:00-00:03]\n"
            "我觉得它虽然不难，但是知道和不知道还是有差距，"
            "我觉得纯做语言模型已经不是一个蓝海了。"
        )
        blocks = tool.parse_transcript_blocks(transcript)
        sections = {
            "00:00-00:03": (
                "## 00:00-00:03 语言模型不再是蓝海\n\n"
                "纯语言模型赛道已经拥挤，不再是年轻人的蓝海。"
            )
        }

        table = tool.fallback_core_table(blocks, sections)

        self.assertIn(
            "论据：纯做语言模型已经不是一个蓝海了。 "
            "<!--依据：“纯做语言模型已经不是一个蓝海了。”-->",
            table,
        )
        self.assertNotIn("它虽然不难", table)

    def test_fallback_table_ignores_short_filler_fragments(self):
        self.assertEqual(
            "",
            tool.select_core_quote(
                "我觉得，",
                "## 00:00-00:03 简短窗口\n\n该窗口只有口头填充。",
            ),
        )

        transcript = (
            "[00:00-00:03]\n"
            "我觉得，后面继续补充了一段更完整的具体说明。"
        )
        blocks = tool.parse_transcript_blocks(transcript)
        sections = {
            "00:00-00:03": "## 00:00-00:03 完整说明\n\n嘉宾继续给出具体说明。"
        }

        table = tool.fallback_core_table(blocks, sections)

        self.assertNotIn("“我觉得，”", table)
        self.assertIn(
            "论据：后面继续补充了一段更完整的具体说明。 "
            "<!--依据：“后面继续补充了一段更完整的具体说明。”-->",
            table,
        )

    def test_validate_core_table_rejects_window_and_evidence_failures(self):
        first_quote = "真正重要的不是追逐榜单，而是先定义用户需要解决的问题。"
        second_quote = "有限上下文训练必须结合持续记忆，才能支持接近无限的任务执行。"
        blocks = tool.parse_transcript_blocks(
            "[00:00-00:03]\n"
            f"{first_quote}\n\n"
            "[00:03-00:06]\n"
            f"{second_quote}"
        )
        valid_rows = [
            [
                "00:00-00:03",
                "先定义问题",
                "模型竞争应先定义真实问题。",
                f"原话：“{first_quote}”",
            ],
            [
                "00:03-00:06",
                "管理长期上下文",
                "持续记忆支持长程任务。",
                f"原话：“{second_quote}”",
            ],
        ]

        def markdown(rows):
            lines = [
                "## 核心观点速览",
                "",
                "| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |",
                "|------|------|----------|------------------|",
            ]
            lines.extend("| " + " | ".join(row) + " |" for row in rows)
            return "\n".join(lines)

        baseline = tool.validate_core_table(blocks, markdown(valid_rows))
        self.assertTrue(baseline["valid"], baseline["errors"])
        self.assertEqual(valid_rows, baseline["rows"])

        cases = {
            "quote copied from a different window": (
                [
                    [*valid_rows[0][:3], f"原话：“{second_quote}”"],
                    valid_rows[1],
                ],
                "exact span",
            ),
            "missing row": ([valid_rows[0]], "transcript order"),
            "rows out of order": (list(reversed(valid_rows)), "transcript order"),
            "hallucinated quotation": (
                [
                    [
                        *valid_rows[0][:3],
                        "原话：“真正重要的不是模型规模，而是这句凭空生成的证据。”",
                    ],
                    valid_rows[1],
                ],
                "exact span",
            ),
            "voiced window marked as no evidence": (
                [
                    [*valid_rows[0][:3], tool.NO_EVIDENCE_TEXT],
                    valid_rows[1],
                ],
                "voiced window",
            ),
            "mechanically truncated core claim": (
                [
                    [
                        valid_rows[0][0],
                        valid_rows[0][1],
                        "模型竞争应先定义真实问题…",
                        valid_rows[0][3],
                    ],
                    valid_rows[1],
                ],
                "mechanically truncated",
            ),
        }
        for label, (rows, expected_error) in cases.items():
            with self.subTest(label=label):
                result = tool.validate_core_table(blocks, markdown(rows))
                self.assertFalse(result["valid"])
                self.assertTrue(
                    any(expected_error in error for error in result["errors"]),
                    result["errors"],
                )


class ConcurrencyTests(unittest.TestCase):
    def test_ordered_parallel_map_is_bounded_and_preserves_input_order(self):
        lock = threading.Lock()
        active = 0
        max_active = 0

        def worker(value):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return value

        results = tool.ordered_parallel_map(worker, range(4), max_workers=2)

        self.assertEqual(results, [0, 1, 2, 3])
        self.assertEqual(max_active, 2)

    def test_proofread_only_batches_use_configured_concurrency(self):
        llm = SlowProofreadLLM()

        calibrated = tool.proofread_transcript(
            llm,
            TRANSCRIPT,
            metadata(),
            batch_size=1,
            min_ratio=0.1,
            concurrency=2,
        )

        self.assertIn("校对后文本", calibrated)
        self.assertEqual(llm.max_active, 2)


class PipelineTests(unittest.TestCase):
    def test_inline_prompt_requires_internal_proofreading_but_skip_does_not(self):
        blocks = tool.parse_transcript_blocks(TRANSCRIPT)

        inline_prompt = tool.build_timeline_batch_prompt(
            blocks,
            metadata(),
            inline_proofread=True,
        )
        skip_prompt = tool.build_timeline_batch_prompt(
            blocks,
            metadata(),
            inline_proofread=False,
        )

        self.assertIn("先在每个窗口内部完成校对", inline_prompt)
        self.assertNotIn("先在每个窗口内部完成校对", skip_prompt)
        for prompt in (inline_prompt, skip_prompt):
            self.assertIn(
                "> **核心观点**：一句不超过 50 字、可独立成立的完整结论",
                prompt,
            )
            self.assertIn(
                "> **关键论据 / 金句**：论据：具体支撑 <!--依据：“同窗逐字片段”-->",
                prompt,
            )
            self.assertIn(f"{tool.CORE_QUOTE_MIN_LENGTH}-140 字", prompt)
            self.assertIn("有效语音但只有过渡/背景时用“背景”", prompt)

    def test_separate_mode_pipelines_each_batch_before_the_next(self):
        llm = RecordingLLM()

        calibrated, report = tool.generate_timeline_outputs(
            llm,
            TRANSCRIPT,
            metadata(),
            proofread_mode="separate",
            proofread_batch_size=2,
            proofread_min_ratio=0.1,
            timeline_batch_size=2,
            detailed=False,
            concurrency=1,
        )

        self.assertEqual(
            llm.events,
            ["proofread", "summary", "proofread", "summary"],
        )
        self.assertIn("校对后文本", calibrated)
        validation = tool.validate_timeline_report(calibrated, report)
        self.assertEqual(validation["found_count"], 4)
        self.assertFalse(validation["missing"])
        self.assertTrue(validation["core_table_valid"], validation["core_table"])
        self.assertEqual(4, len(validation["core_table"]["rows"]))
        self.assertNotIn("> **核心观点**", report)
        self.assertNotIn("> **关键论据 / 金句**", report)

    def test_inline_mode_uses_summary_calls_without_calibrated_output(self):
        llm = RecordingLLM()

        calibrated, report = tool.generate_timeline_outputs(
            llm,
            TRANSCRIPT,
            metadata(),
            proofread_mode="inline",
            proofread_batch_size=2,
            proofread_min_ratio=0.1,
            timeline_batch_size=4,
            detailed=False,
            concurrency=1,
        )

        self.assertIsNone(calibrated)
        self.assertEqual(llm.events, ["summary"])
        self.assertIn("摘要生成时在窗口内部完成 LLM 校对", report)
        validation = tool.validate_timeline_report(TRANSCRIPT, report)
        self.assertEqual(validation["found_count"], 4)
        self.assertFalse(validation["missing"])
        self.assertTrue(validation["core_table_valid"], validation["core_table"])
        self.assertEqual(4, len(validation["core_table"]["rows"]))
        self.assertNotIn("> **核心观点**", report)
        self.assertNotIn("> **关键论据 / 金句**", report)


class CliTests(unittest.TestCase):
    def test_parse_args_accepts_proofread_mode_and_llm_concurrency(self):
        argv = [
            str(SCRIPT_PATH),
            "--transcript-input",
            "episode_转写.txt",
            "--proofread-mode",
            "inline",
            "--llm-concurrency",
            "3",
        ]
        with patch.object(sys, "argv", argv):
            args = tool.parse_args()

        self.assertEqual(args.proofread_mode, "inline")
        self.assertEqual(args.llm_concurrency, 3)


if __name__ == "__main__":
    unittest.main()
