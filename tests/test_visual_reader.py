import importlib.util
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
)
MODULE_PATH = SCRIPTS_DIR / "visual_reader.py"


def load_visual_reader():
    spec = importlib.util.spec_from_file_location("visual_reader", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


TRANSCRIPT_BLOCKS = [
    {"window": "00:00-00:30", "text": "Revenue grew 20 percent after the launch."},
    {"window": "00:30-01:00", "text": "Retention improved because onboarding became clearer."},
]


def sourced(text, *windows):
    return {"text": text, "source_windows": list(windows)}


def valid_manifest():
    return {
        "version": 1,
        "overview": sourced(
            "A launch changed growth and retention.",
            "00:00-00:30",
            "00:30-01:00",
        ),
        "core_insights": [
            sourced("Growth accelerated.", "00:00-00:30"),
            sourced("Onboarding improved retention.", "00:30-01:00"),
        ],
        "chapters": [
            {
                "id": "launch",
                "title": sourced("Launch effects", "00:00-00:30", "00:30-01:00"),
                "summary": sourced(
                    "The launch improved two business outcomes.",
                    "00:00-00:30",
                    "00:30-01:00",
                ),
                "source_windows": ["00:00-00:30", "00:30-01:00"],
                "evidence": [
                    {"window": "00:00-00:30", "label": "Growth evidence"},
                    {"window": "00:30-01:00", "label": "Retention evidence"},
                ],
                "visuals": [
                    {
                        "type": "process",
                        "title": sourced("Launch process", "00:00-00:30", "00:30-01:00"),
                        "items": [
                            sourced("Launch", "00:00-00:30"),
                            sourced("Clear onboarding", "00:30-01:00"),
                            sourced("Retention", "00:30-01:00"),
                        ],
                    },
                    {
                        "type": "comparison",
                        "title": sourced("Before and after", "00:00-00:30"),
                        "items": [
                            {"label": "Before", "value": "Slower", "source_windows": ["00:00-00:30"]},
                            {"label": "After", "value": "Faster", "source_windows": ["00:00-00:30"]},
                        ],
                    },
                    {
                        "type": "relationship",
                        "title": sourced("Outcome links", "00:30-01:00"),
                        "items": [
                            {
                                "from": "Onboarding",
                                "to": "Retention",
                                "label": "improves",
                                "source_windows": ["00:30-01:00"],
                            }
                        ],
                    },
                    {
                        "type": "metrics",
                        "title": sourced("Measured growth", "00:00-00:30"),
                        "items": [
                            {
                                "label": "Revenue growth",
                                "value": "20 percent",
                                "source_window": "00:00-00:30",
                                "source_sentence": "Revenue grew 20 percent after the launch.",
                            }
                        ],
                    },
                    {
                        "type": "concept",
                        "title": sourced("Core concept", "00:00-00:30", "00:30-01:00"),
                        "items": [
                            sourced("Clarity", "00:00-00:30"),
                            sourced("Activation", "00:00-00:30"),
                            sourced("Retention", "00:30-01:00"),
                        ],
                    },
                    {
                        "type": "quote",
                        "title": sourced("Verified quote", "00:30-01:00"),
                        "quote": "Retention improved because onboarding became clearer.",
                        "source_window": "00:30-01:00",
                    },
                ],
            }
        ],
    }


def compact_blocks():
    return [
        {"window": f"0{index}:00-0{index + 1}:00", "text": "中文证据支持全局概括和信息图。"}
        for index in range(5)
    ]


def compact_manifest():
    blocks = compact_blocks()
    windows = [block["window"] for block in blocks]
    visuals = [
        {
            "type": "process",
            "title": sourced("三步流程", windows[0]),
            "items": [sourced(text, windows[0]) for text in ("回收", "量产", "平台")],
        },
        {
            "type": "process",
            "title": sourced("排障时间线", windows[1]),
            "items": [sourced(f"阶段{index}", windows[1]) for index in range(5)],
        },
        {
            "type": "comparison",
            "title": sourced("组织对比", windows[2]),
            "items": [
                {"label": "传统模式", "value": "专业分工", "source_windows": [windows[2]]},
                {"label": "SpaceX", "value": "端到端责任", "source_windows": [windows[2]]},
            ],
        },
        {
            "type": "relationship",
            "title": sourced("工业化飞轮", windows[3]),
            "items": [
                {"from": "使命", "to": "工程", "label": "驱动", "source_windows": [windows[3]]},
                {"from": "工程", "to": "商业", "label": "形成", "source_windows": [windows[3]]},
                {"from": "商业", "to": "使命", "label": "反哺", "source_windows": [windows[3]]},
            ],
        },
        {
            "type": "concept",
            "title": sourced("产业分层", windows[4]),
            "items": [sourced(text, windows[4]) for text in ("发射", "在轨运营", "应用")],
        },
        {
            "type": "metrics",
            "title": sourced("关键指标", windows[4]),
            "items": [
                {
                    "label": "完整窗口",
                    "value": "5",
                    "source_window": windows[4],
                    "source_sentence": blocks[4]["text"],
                }
            ],
        },
    ]
    interpretation_item = lambda title, text, *source_windows: {
        "title": title,
        "text": text,
        "source_windows": list(source_windows),
    }
    return {
        "version": 2,
        "one_line_overview": sourced("证据必须转化为可执行行动。", *windows),
        "overview": sourced("完整阅读转写稿后形成的短篇全局解读。", *windows),
        "core_insights": [sourced(f"核心结论{index}", windows[index]) for index in range(4)],
        "developer_takeaways": [
            interpretation_item("RAG 上下文工程", "组合知识、权限与任务状态并保留引用。", windows[0]),
            interpretation_item("模型训练与数据", "保存行为轨迹、结果反馈和异常处理。", windows[1]),
            interpretation_item("Agent 构建可靠性", "定义工具边界、失败回退和业务指标。", windows[2]),
            interpretation_item("Agent 开发学习路径", "从单 Agent 可验证任务逐步学习到复杂协作。", windows[3]),
        ],
        "critical_thinking": [
            interpretation_item("效果归因仍需验证", "业务改善需要基线和对照实验支持。", windows[3]),
            interpretation_item("案例代表性有限", "单一案例不能直接外推全部行业。", windows[4]),
        ],
        "further_questions": [
            interpretation_item("建立任务评测集", "下一步应定义成功率与工具调用准确率。", windows[0]),
            interpretation_item("设计灰度上线", "用低峰流量验证权限和失败回退。", windows[4]),
        ],
        "chapters": [
            {
                "id": f"chapter-{index}",
                "title": sourced(f"主题{index + 1}", window),
                "summary": sourced(
                    "先识别问题边界。再根据证据形成判断。最后把结论转成行动。", window
                ),
                "summary_cards": [
                    {
                        "title": sourced("边界先于方案", window),
                        "text": sourced("先识别问题边界。", window),
                    },
                    {
                        "title": sourced("证据形成判断", window),
                        "text": sourced("再根据证据形成判断。", window),
                    },
                    {
                        "title": sourced("行动闭环落地", window),
                        "text": sourced("最后把结论转成行动。", window),
                    },
                ],
                "source_windows": [window],
                "evidence": [{"window": window, "label": "来源窗口"}],
                "visuals": ([visuals[index]] if index < 4 else visuals[4:]),
            }
            for index, window in enumerate(windows)
        ],
    }


class VisualReaderOrchestrationTests(unittest.TestCase):
    def assert_visual_failure(self, manifest, blocks=None, media_source=None):
        visual_reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "episode_visual_reader.html"
            transcript = root / "episode_calibrated.txt"
            report = root / "episode_timeline.md"
            transcript.write_text("existing transcript", encoding="utf-8")
            report.write_text("existing report", encoding="utf-8")
            with self.assertRaises(visual_reader.VisualStageError) as caught:
                visual_reader.render_visual_brief(
                    calibrated_transcript_blocks=blocks or TRANSCRIPT_BLOCKS,
                    validated_timeline_report="# Timeline\n\nValidated report.",
                    trusted_metadata={"title": "Launch review", "duration": "01:00"},
                    media_source=media_source or {"kind": "audio", "url": None},
                    manifest=manifest,
                    output_destination=destination,
                )

            self.assertIn("visual", str(caught.exception).lower())
            self.assertEqual(transcript.read_text(encoding="utf-8"), "existing transcript")
            self.assertEqual(report.read_text(encoding="utf-8"), "existing report")
    def test_valid_manifest_publishes_complete_offline_reader(self):
        visual_reader = load_visual_reader()
        blocks = copy.deepcopy(TRANSCRIPT_BLOCKS)
        blocks[0]["text"] += " TRANSCRIPT_ONLY_SENTINEL_7f4a"
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "episode_visual_reader.html"

            result = visual_reader.render_visual_brief(
                calibrated_transcript_blocks=blocks,
                validated_timeline_report="# Timeline\n\nValidated report.",
                trusted_metadata={"title": "Launch review", "duration": "01:00", "language": "en"},
                media_source={"kind": "audio", "url": None},
                manifest=valid_manifest(),
                output_destination=destination,
            )

            assets_dir = Path(temp_dir) / "episode_visual_reader_assets"
            html = destination.read_text(encoding="utf-8")
            self.assertEqual(result.html_path, destination)
            self.assertEqual(result.assets_dir, assets_dir)
            self.assertTrue((assets_dir / "frames").is_dir())
            for text in (
                "Launch review",
                "A launch changed growth and retention.",
                "Core insights",
                "Chapter navigation",
                "Launch effects",
                "Growth evidence",
                "process-visual",
                "comparison-visual",
                "relationship-visual",
                "metrics-visual",
                "concept-visual",
                "quote-visual",
                "<details",
                "mobile-chapter-nav",
                "prefers-reduced-motion",
                "Current chapter",
            ):
                self.assertIn(text, html)
            for forbidden in (
                "TRANSCRIPT_ONLY_SENTINEL_7f4a",
                "Calibrated transcript",
                "Expand all transcripts",
                "Collapse all transcripts",
                "data-disclosure",
                "transcript-block",
                "<h3>00:00-00:30</h3>",
            ):
                self.assertNotIn(forbidden, html)
            self.assertIn("<style>", html)
            self.assertIn('<html lang="en">', html)
            self.assertIn("<script>", html)
            self.assertIn("<symbol", html)
            self.assertIn('type="search"', html)
            self.assertIn('data-source-windows="00:00-00:30 00:30-01:00"', html)
            self.assertIn("--color-primary:#CC8800", html)
            self.assertIn("--color-secondary:#C55221", html)
            self.assertIn("--color-focus:#1D4ED8", html)
            self.assertIn('var(--font-display)', html)
            self.assertIn("input[type=search]:hover", html)
            self.assertIn("min-height:44px", html)
            self.assertNotIn("{&#x27;text&#x27;", html)
            self.assertNotIn("<link rel=", html)
            self.assertNotIn("src=\"http", html)

    def test_compact_long_chinese_reader_is_single_file_editorial_svg(self):
        visual_reader = load_visual_reader()
        blocks = compact_blocks()
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "compact.html"
            result = visual_reader.render_visual_brief(
                calibrated_transcript_blocks=blocks,
                validated_timeline_report="validated",
                trusted_metadata={"title": "短版解读", "duration_seconds": 3660},
                media_source={"kind": "remote-video", "url": "https://example.com/video"},
                manifest=compact_manifest(),
                output_destination=destination,
            )

            page = destination.read_text(encoding="utf-8")
            self.assertIsNone(result.assets_dir)
            self.assertFalse(destination.with_name("compact_assets").exists())
            for expected in (
                "compact-editorial",
                "insight-grid",
                "chapter-stack",
                "chapter-section",
                "summary-card-grid",
                "summary-card",
                "one-line-overview",
                "deep-interpretation",
                "takeaway-grid",
                "给 AI 应用开发者的启发",
                "需要验证的假设",
                "值得继续探索",
                "Agent 开发学习路径",
                "flow-diagram",
                "timeline-diagram",
                "comparison-diagram",
                "flywheel-diagram",
                "layered-diagram",
                "metrics-diagram",
                "<svg",
                "--color-primary:#CC8800",
                "--color-secondary:#C55221",
                "--color-focus:#1D4ED8",
                "--color-surface-apricot:#FBE9D8",
                "--color-surface-sand:#F2E6D2",
                "--color-surface-rose:#F7E3DC",
                ".summary-card:nth-child(4n+2)",
                ".chapter-section:nth-child(even) .summary-card:nth-child(4n+1)",
                "grid-template-columns:repeat(2,minmax(0,1fr))",
                "@media(max-width:680px)",
                "@media(hover:none)",
                "min-height:44px",
            ):
                self.assertIn(expected, page)
            self.assertEqual(page.count('class="chapter-section"'), len(compact_manifest()["chapters"]))
            expected_card_count = sum(
                len(chapter["summary_cards"])
                for chapter in compact_manifest()["chapters"]
            )
            self.assertEqual(page.count('class="summary-card"'), expected_card_count)
            for chapter in compact_manifest()["chapters"]:
                cards = chapter["summary_cards"]
                self.assertEqual(
                    "".join(card["text"]["text"] for card in cards),
                    chapter["summary"]["text"],
                )
                for card in cards:
                    self.assertIn(card["title"]["text"], page)
                    self.assertIn(card["text"]["text"], page)
                    self.assertFalse(
                        card["text"]["text"].startswith(card["title"]["text"])
                    )
                for evidence in chapter["evidence"]:
                    self.assertIn(evidence["label"], page)
            for forbidden in (
                "<img",
                "type=\"search\"",
                "Current chapter",
                "Chapter navigation",
                "visual-brief-data",
                "TRANSCRIPT_ONLY_SENTINEL",
            ):
                self.assertNotIn(forbidden, page)

    def test_version_two_rejects_long_one_line_overview(self):
        manifest = compact_manifest()
        manifest["one_line_overview"]["text"] = "过" * 51
        self.assert_visual_failure(
            manifest,
            blocks=compact_blocks(),
            media_source={"kind": "audio", "url": None},
        )

    def test_compact_reader_rejects_summary_title_that_repeats_body_opening(self):
        manifest = compact_manifest()
        manifest["chapters"][0]["summary_cards"][0]["title"]["text"] = "先识别问题边界"
        self.assert_visual_failure(
            manifest,
            blocks=compact_blocks(),
            media_source={"kind": "audio", "url": None},
        )

    def test_compact_reader_rejects_frame_assets(self):
        visual_reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            frame = Path(temp_dir) / "frame.webp"
            frame.write_bytes(b"not-empty")
            with self.assertRaisesRegex(visual_reader.VisualStageError, "frame assets"):
                visual_reader.render_visual_brief(
                    calibrated_transcript_blocks=compact_blocks(),
                    validated_timeline_report="validated",
                    trusted_metadata={"title": "短版解读", "duration_seconds": 3660},
                    media_source={"kind": "remote-video", "url": None},
                    manifest=compact_manifest(),
                    output_destination=Path(temp_dir) / "compact.html",
                    frame_assets=[{
                        "chapter_id": "chapter-0",
                        "source_window": "00:00-01:00",
                        "path": frame,
                        "width": 100,
                        "height": 100,
                    }],
                )

    def test_invalid_window_mappings_fail_before_publication(self):
        cases = {}
        missing = valid_manifest()
        missing["chapters"][0]["source_windows"] = ["00:00-00:30"]
        cases["missing"] = (missing, TRANSCRIPT_BLOCKS)

        duplicated = valid_manifest()
        duplicated["chapters"][0]["source_windows"].append("00:30-01:00")
        cases["duplicated"] = (duplicated, TRANSCRIPT_BLOCKS)

        reordered = valid_manifest()
        reordered["chapters"][0]["source_windows"].reverse()
        cases["reordered"] = (reordered, TRANSCRIPT_BLOCKS)

        unsupported = valid_manifest()
        unsupported["chapters"][0]["source_windows"][1] = "01:00-01:30"
        cases["out of range"] = (unsupported, TRANSCRIPT_BLOCKS)

        three_blocks = TRANSCRIPT_BLOCKS + [
            {"window": "01:00-01:30", "text": "The final window closes the discussion."}
        ]
        non_adjacent = valid_manifest()
        first = non_adjacent["chapters"][0]
        first["source_windows"] = ["00:00-00:30", "01:00-01:30"]
        second = copy.deepcopy(first)
        second.update({"id": "middle", "title": "Middle", "source_windows": ["00:30-01:00"]})
        non_adjacent["chapters"].append(second)
        cases["non adjacent"] = (non_adjacent, three_blocks)

        overlapping = valid_manifest()
        second = copy.deepcopy(overlapping["chapters"][0])
        second.update({"id": "overlap", "title": "Overlap", "source_windows": ["00:30-01:00"]})
        overlapping["chapters"].append(second)
        cases["overlapping"] = (overlapping, TRANSCRIPT_BLOCKS)

        for label, (manifest, blocks) in cases.items():
            with self.subTest(label=label):
                self.assert_visual_failure(manifest, blocks=blocks)

    def test_inexact_quote_fails_before_publication(self):
        manifest = valid_manifest()
        manifest["chapters"][0]["visuals"][-1]["quote"] = "Onboarding was clearer."
        self.assert_visual_failure(manifest)

    def test_missing_unknown_and_unsupported_manifest_fields_fail(self):
        missing = valid_manifest()
        missing.pop("overview")
        unknown = valid_manifest()
        unknown["template"] = "model-selected"
        unsupported = valid_manifest()
        unsupported["chapters"][0]["visuals"][0]["type"] = "arbitrary-svg"
        for label, manifest in (
            ("missing", missing),
            ("unknown", unknown),
            ("unsupported", unsupported),
        ):
            with self.subTest(label=label):
                self.assert_visual_failure(manifest)

    def test_every_visible_claim_and_diagram_item_requires_source_windows(self):
        cases = {}
        overview = valid_manifest()
        overview["overview"].pop("source_windows")
        cases["overview"] = overview

        insight = valid_manifest()
        insight["core_insights"][0].pop("source_windows")
        cases["insight"] = insight

        chapter_summary = valid_manifest()
        chapter_summary["chapters"][0]["summary"].pop("source_windows")
        cases["chapter summary"] = chapter_summary

        process_item = valid_manifest()
        process_item["chapters"][0]["visuals"][0]["items"][0].pop("source_windows")
        cases["process item"] = process_item

        relationship_item = valid_manifest()
        relationship_item["chapters"][0]["visuals"][2]["items"][0].pop("source_windows")
        cases["relationship item"] = relationship_item

        for label, manifest in cases.items():
            with self.subTest(label=label):
                self.assert_visual_failure(manifest)

    def test_visible_claim_source_windows_must_belong_to_their_scope(self):
        manifest = valid_manifest()
        manifest["chapters"][0]["visuals"][0]["items"][0]["source_windows"] = [
            "01:00-01:30"
        ]
        self.assert_visual_failure(manifest)

    def test_numeric_item_requires_exact_source_sentence_and_valid_window(self):
        for mutation in ("missing_sentence", "wrong_sentence", "wrong_window"):
            manifest = valid_manifest()
            metric = manifest["chapters"][0]["visuals"][3]["items"][0]
            if mutation == "missing_sentence":
                metric.pop("source_sentence")
            elif mutation == "wrong_sentence":
                metric["source_sentence"] = "Revenue doubled."
            else:
                metric["source_window"] = "01:00-01:30"
            with self.subTest(mutation=mutation):
                self.assert_visual_failure(manifest)

    def test_untrusted_text_is_escaped_and_presentation_payloads_are_rejected(self):
        visual_reader = load_visual_reader()
        manifest = valid_manifest()
        manifest["overview"]["text"] = '<script>alert("overview")</script>'
        blocks = copy.deepcopy(TRANSCRIPT_BLOCKS)
        blocks[0]["text"] += ' <img src=x onerror="alert(1)">'
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "safe.html"
            visual_reader.render_visual_brief(
                calibrated_transcript_blocks=blocks,
                validated_timeline_report="validated",
                trusted_metadata={"title": '<b onclick="x">Title</b>'},
                media_source={"kind": "audio", "url": None},
                manifest=manifest,
                output_destination=destination,
            )
            page = destination.read_text(encoding="utf-8")
            self.assertNotIn('<img src=x onerror=', page)
            self.assertNotIn('<b onclick=', page)
            self.assertIn("&lt;script&gt;", page)

        for key in ("html", "javascript", "css", "svg"):
            manifest = valid_manifest()
            manifest["chapters"][0]["visuals"][0][key] = "<unsafe>"
            with self.subTest(key=key):
                self.assert_visual_failure(manifest)

    def test_unsafe_media_source_and_asset_paths_are_rejected(self):
        for source in (
            {"kind": "video", "url": "javascript:alert(1)"},
            {"kind": "video", "url": "file:///secret.mp4"},
        ):
            with self.subTest(source=source):
                self.assert_visual_failure(valid_manifest(), media_source=source)

        for asset_path in ("../escape.webp", "C:\\secret.webp", "/tmp/secret.webp"):
            manifest = valid_manifest()
            manifest["chapters"][0]["visuals"][0]["asset_path"] = asset_path
            with self.subTest(asset_path=asset_path):
                self.assert_visual_failure(manifest)

    def test_validation_failure_keeps_previous_reader_artifacts(self):
        manifest = valid_manifest()
        manifest["chapters"][0]["source_windows"] = []

        def setup(root, destination):
            destination.write_text("previous reader", encoding="utf-8")
            assets = root / "episode_visual_reader_assets"
            assets.mkdir()
            (assets / "marker.txt").write_text("previous assets", encoding="utf-8")

        visual_reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "episode_visual_reader.html"
            setup(root, destination)
            with self.assertRaises(visual_reader.VisualStageError):
                visual_reader.render_visual_brief(
                    calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                    validated_timeline_report="validated",
                    trusted_metadata={"title": "Launch review"},
                    media_source={"kind": "audio", "url": None},
                    manifest=manifest,
                    output_destination=destination,
                )
            self.assertEqual(destination.read_text(encoding="utf-8"), "previous reader")
            self.assertEqual(
                (root / "episode_visual_reader_assets" / "marker.txt").read_text(encoding="utf-8"),
                "previous assets",
            )

    def test_staging_failure_is_reported_as_visual_stage_failure(self):
        visual_reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "missing" / "reader.html"
            with self.assertRaises(visual_reader.VisualStageError) as caught:
                visual_reader.render_visual_brief(
                    calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                    validated_timeline_report="validated",
                    trusted_metadata={"title": "Launch review"},
                    media_source={"kind": "audio", "url": None},
                    manifest=valid_manifest(),
                    output_destination=destination,
                )
            self.assertIn("staging", str(caught.exception))

    def test_valid_render_atomically_replaces_previous_reader_artifacts(self):
        visual_reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "episode_visual_reader.html"
            assets = root / "episode_visual_reader_assets"
            destination.write_text("previous reader", encoding="utf-8")
            assets.mkdir()
            (assets / "marker.txt").write_text("previous assets", encoding="utf-8")

            visual_reader.render_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report="validated",
                trusted_metadata={"title": "Replacement reader"},
                media_source={"kind": "audio", "url": None},
                manifest=valid_manifest(),
                output_destination=destination,
            )

            self.assertIn("Replacement reader", destination.read_text(encoding="utf-8"))
            self.assertFalse((assets / "marker.txt").exists())
            self.assertTrue((assets / "frames").is_dir())

    def test_publication_failure_rolls_back_previous_reader_artifacts(self):
        visual_reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "episode_visual_reader.html"
            assets = root / "episode_visual_reader_assets"
            destination.write_text("previous reader", encoding="utf-8")
            assets.mkdir()
            (assets / "marker.txt").write_text("previous assets", encoding="utf-8")
            real_replace = visual_reader.os.replace
            publication_calls = 0
            failed_once = False

            def fail_when_publishing_html(source, target):
                nonlocal publication_calls, failed_once
                if Path(target) in {destination, assets}:
                    publication_calls += 1
                    if Path(target) == destination and not failed_once:
                        failed_once = True
                        raise OSError("simulated publication failure")
                return real_replace(source, target)

            with patch.object(visual_reader.os, "replace", side_effect=fail_when_publishing_html):
                with self.assertRaises(visual_reader.VisualStageError) as caught:
                    visual_reader.render_visual_brief(
                        calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                        validated_timeline_report="validated",
                        trusted_metadata={"title": "Replacement reader"},
                        media_source={"kind": "audio", "url": None},
                        manifest=valid_manifest(),
                        output_destination=destination,
                    )

            self.assertGreaterEqual(publication_calls, 2)
            self.assertIn("publication", str(caught.exception))
            self.assertEqual(destination.read_text(encoding="utf-8"), "previous reader")
            self.assertEqual((assets / "marker.txt").read_text(encoding="utf-8"), "previous assets")


if __name__ == "__main__":
    unittest.main()
