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
        return "\n\n".join(
            f"## {window} 测试主题\n\n这里概括 {window} 窗口。"
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
            ["proofread", "summary", "proofread", "summary", "table"],
        )
        self.assertIn("校对后文本", calibrated)
        validation = tool.validate_timeline_report(TRANSCRIPT, report)
        self.assertEqual(validation["found_count"], 4)
        self.assertFalse(validation["missing"])

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
        self.assertEqual(llm.events, ["summary", "table"])
        self.assertIn("摘要生成时在窗口内部完成 LLM 校对", report)
        validation = tool.validate_timeline_report(TRANSCRIPT, report)
        self.assertEqual(validation["found_count"], 4)
        self.assertFalse(validation["missing"])


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
