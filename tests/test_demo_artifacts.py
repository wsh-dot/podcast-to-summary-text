import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "mimo-token-plan-asr-llm-pipeline" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mimo_podcast_tool import (
    NO_EVIDENCE_TEXT,
    core_table_rows,
    parse_transcript_blocks,
    quote_quality_issues,
    validate_core_table,
)
from visual_brief import validate_visual_brief


class PublishedDemoTests(unittest.TestCase):
    def test_window_analysis_core_table_is_complete_ordered_and_grounded(self):
        example = ROOT / "examples" / "yao-shunyu-interview"
        transcript = (example / "calibrated-transcript.txt").read_text(
            encoding="utf-8"
        )
        report = (example / "window-by-window-analysis.md").read_text(
            encoding="utf-8"
        )
        blocks = parse_transcript_blocks(transcript)
        block_by_window = {block["window"]: block for block in blocks}

        rows, parse_errors = core_table_rows(report)
        validation = validate_core_table(blocks, report)

        self.assertEqual([], parse_errors)
        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual(77, len(blocks))
        self.assertEqual(77, len(rows))
        self.assertEqual(
            [block["window"] for block in blocks],
            [row[0] for row in rows],
        )

        no_evidence_windows = []
        quote_by_window = {}
        for window, _chapter, claim, support in rows:
            self.assertNotIn("…", claim, window)
            self.assertNotIn("...", claim, window)
            if support == NO_EVIDENCE_TEXT:
                no_evidence_windows.append(window)
                continue

            quote_match = re.fullmatch(r"原话[：:]\s*[“\"](.+?)[”\"]", support)
            if quote_match:
                quote = quote_match.group(1)
                quote_by_window[window] = quote
                block_text = block_by_window[window]["text"]
                self.assertIn(quote, block_text, window)
                self.assertEqual(
                    [],
                    quote_quality_issues(quote, block_text),
                    window,
                )

        self.assertEqual(["03:48-03:49"], no_evidence_windows)
        self.assertEqual(
            "大家都已经开始不那么担心一件事AI是不是能够做得到，"
            "而是担心这件事儿是不是被良好定义。",
            quote_by_window["00:06-00:09"],
        )
        self.assertEqual(
            "With finite context, use as infinite context.",
            quote_by_window["00:24-00:27"],
        )

    def test_online_demo_is_a_valid_v2_offline_reader(self):
        example = ROOT / "examples" / "yao-shunyu-interview"
        transcript = (example / "calibrated-transcript.txt").read_text(encoding="utf-8")
        manifest = json.loads(
            (example / "visual-brief-manifest.v2.json").read_text(encoding="utf-8")
        )
        page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        blocks = parse_transcript_blocks(transcript)

        validate_visual_brief(
            blocks,
            manifest,
            {"kind": "video", "url": "https://www.bilibili.com/video/BV1YR5E6EE9o"},
        )
        self.assertEqual(2, manifest["version"])
        self.assertEqual(77, len(blocks))
        self.assertEqual(5, len(manifest["chapters"]))
        self.assertEqual(8, sum(len(chapter["visuals"]) for chapter in manifest["chapters"]))
        self.assertEqual(5, page.count('class="chapter-section"'))
        self.assertEqual(
            sum(len(chapter["summary_cards"]) for chapter in manifest["chapters"]),
            page.count('class="summary-card"'),
        )
        for required in (
            "one-line-overview",
            "给 AI 应用开发者的启发",
            "需要验证的假设",
            "值得继续探索",
            "Agent 开发学习路径",
            "对姚舜宇的4小时访谈",
        ):
            self.assertIn(required, page)
        self.assertNotIn("对姚顺宇的4小时访谈", page)
        self.assertIsNone(re.search(r'<(?:script|img|link)[^>]+(?:src|href)="https?://', page))


if __name__ == "__main__":
    unittest.main()
