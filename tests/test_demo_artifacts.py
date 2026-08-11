import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "mimo-token-plan-asr-llm-pipeline" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mimo_podcast_tool import parse_transcript_blocks
from visual_brief import validate_visual_brief


class PublishedDemoTests(unittest.TestCase):
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
