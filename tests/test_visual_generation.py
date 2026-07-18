import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_visual_reader import (
    TRANSCRIPT_BLOCKS,
    compact_blocks,
    compact_manifest,
    valid_manifest,
)


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
)
MODULE_PATH = SCRIPTS_DIR / "visual_generation.py"


def load_visual_generation():
    spec = importlib.util.spec_from_file_location("visual_generation", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


def load_podcast_tool():
    path = SCRIPTS_DIR / "mimo_podcast_tool.py"
    spec = importlib.util.spec_from_file_location("visual_generation_podcast_tool", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


def batch_response(blocks):
    return json.dumps(
        {
            "version": 1,
            "windows": [block["window"] for block in blocks],
            "records": [
                {
                    "window": block["window"],
                    "claim": f"Claim for {block['window']}",
                    "evidence": block["text"],
                    "candidate_visual": None,
                    "quote": None,
                    "numbers": [],
                    "grouping_signal": "continue",
                }
                for block in blocks
            ],
        }
    )


def api_manifest():
    manifest = valid_manifest()
    manifest["chapters"][0]["visuals"] = manifest["chapters"][0]["visuals"][:5]
    return manifest


def serial_parallel_map(worker, items, max_workers):
    return [worker(item) for item in items]


def calibrated_transcript_payload(prompt):
    start_marker = "CALIBRATED_TRANSCRIPT_JSON:\n"
    end_marker = "\nVALIDATED_VISUAL_BATCHES_JSON:"
    start = prompt.index(start_marker) + len(start_marker)
    end = prompt.index(end_marker, start)
    return json.loads(prompt[start:end])


class APILLMVisualBriefTests(unittest.TestCase):
    def run_generation(self, complete, destination, duration_seconds=60, batch_size=2):
        visual_generation = load_visual_generation()
        return visual_generation.generate_api_visual_brief(
            calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
            validated_timeline_report="# Overview\n\nValidated overview.",
            trusted_metadata={"title": "Launch review", "duration_seconds": duration_seconds},
            media_source={"kind": "audio", "url": None},
            output_destination=destination,
            complete=complete,
            parallel_map=serial_parallel_map,
            batch_size=batch_size,
            concurrency=1,
        )

    def test_short_audio_batches_synthesizes_and_renders_offline_reader(self):
        visual_generation = load_visual_generation()
        prompts = []

        def complete(messages, max_tokens, label):
            prompt = messages[-1]["content"]
            prompts.append((label, prompt, max_tokens))
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            if "VISUAL_SYNTHESIS_REQUEST" in prompt:
                return json.dumps(api_manifest())
            raise AssertionError(f"unexpected prompt: {label}")

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "episode_visual.html"
            result = visual_generation.generate_api_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report=(
                    "# Timeline\n\n## Core overview\n\nValidated overview.\n\n"
                    "## 00:00-00:30 First\n\nBody detail that synthesis must not receive."
                ),
                trusted_metadata={"title": "Launch review", "duration_seconds": 60},
                media_source={"kind": "audio", "url": None},
                output_destination=destination,
                complete=complete,
                parallel_map=serial_parallel_map,
                batch_size=2,
                concurrency=1,
            )

            self.assertEqual(result.html_path, destination)
            self.assertTrue(result.html_path.exists())
            self.assertTrue((result.assets_dir / "frames").is_dir())

        self.assertEqual([label for label, _, _ in prompts], ["visual batch 1/1", "visual synthesis"])
        batch_prompt = prompts[0][1]
        for expected in (
            "00:00-00:30",
            "00:30-01:00",
            "claim",
            "evidence",
            "candidate_visual",
            "quote",
            "numbers",
            "grouping_signal",
            "HTML",
            "JavaScript",
            "CSS",
            "SVG",
        ):
            self.assertIn(expected, batch_prompt)
        synthesis_prompt = prompts[1][1]
        self.assertIn("5-10", synthesis_prompt)
        self.assertIn("Validated overview.", synthesis_prompt)
        self.assertNotIn("Body detail that synthesis must not receive.", synthesis_prompt)
        self.assertEqual(calibrated_transcript_payload(synthesis_prompt), TRANSCRIPT_BLOCKS)

    def test_synthesis_prompt_includes_exact_ordered_calibrated_transcript(self):
        visual_generation = load_visual_generation()

        prompt = visual_generation.build_visual_synthesis_prompt(
            [json.loads(batch_response(TRANSCRIPT_BLOCKS))],
            "# Overview\n\nValidated overview.",
            {"title": "Launch review", "duration_seconds": 60},
            60,
            calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
            media_source={"kind": "audio", "url": None},
        )

        self.assertIn(
            "Read the complete calibrated transcript before global interpretation.",
            prompt,
        )
        self.assertEqual(calibrated_transcript_payload(prompt), TRANSCRIPT_BLOCKS)

    def test_only_invalid_batch_is_repaired_before_synthesis(self):
        visual_generation = load_visual_generation()
        calls = []
        second_attempts = 0

        def complete(messages, max_tokens, label):
            nonlocal second_attempts
            prompt = messages[-1]["content"]
            calls.append((label, prompt))
            if "VISUAL_SYNTHESIS_REQUEST" in prompt:
                return json.dumps(api_manifest())
            if "00:00-00:30" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS[:1])
            if "00:30-01:00" in prompt:
                second_attempts += 1
                if second_attempts == 1:
                    invalid = json.loads(batch_response(TRANSCRIPT_BLOCKS[1:]))
                    invalid["records"][0]["evidence"] = "invented evidence"
                    return json.dumps(invalid)
                self.assertIn("Validation error", prompt)
                return batch_response(TRANSCRIPT_BLOCKS[1:])
            raise AssertionError(f"unexpected prompt: {label}")

        with tempfile.TemporaryDirectory() as temp_dir:
            result = visual_generation.generate_api_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report="# Overview\n\nValidated.",
                trusted_metadata={"title": "Launch review", "duration_seconds": 60},
                media_source={"kind": "audio", "url": None},
                output_destination=Path(temp_dir) / "episode.html",
                complete=complete,
                parallel_map=serial_parallel_map,
                batch_size=1,
                concurrency=1,
            )
            self.assertTrue(result.html_path.exists())

        labels = [label for label, _ in calls]
        self.assertEqual(labels.count("visual batch 1/2"), 1)
        self.assertEqual(labels.count("visual batch 2/2"), 1)
        self.assertEqual(labels.count("visual batch 2/2 repair"), 1)
        self.assertEqual(labels.count("visual synthesis"), 1)

    def test_permanently_invalid_batch_stops_before_synthesis_or_publication(self):
        visual_generation = load_visual_generation()
        labels = []

        def complete(messages, max_tokens, label):
            labels.append(label)
            invalid = json.loads(batch_response(TRANSCRIPT_BLOCKS))
            invalid["records"][0]["evidence"] = "invented evidence"
            return json.dumps(invalid)

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "episode.html"
            with self.assertRaises(visual_generation.VisualStageError):
                self.run_generation(complete, destination)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name("episode_assets").exists())

        self.assertEqual(labels, ["visual batch 1/1", "visual batch 1/1 repair"])

    def test_api_retry_exhaustion_becomes_visual_stage_failure(self):
        visual_generation = load_visual_generation()

        def complete(messages, max_tokens, label):
            raise RuntimeError("provider retries exhausted")

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "episode.html"
            with self.assertRaises(visual_generation.VisualStageError) as caught:
                self.run_generation(complete, destination)
            self.assertIn("provider retries exhausted", str(caught.exception))
            self.assertFalse(destination.exists())

    def test_video_frame_provider_failure_degrades_to_text_reader(self):
        visual_generation = load_visual_generation()

        def complete(messages, max_tokens, label):
            prompt = messages[-1]["content"]
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            manifest = api_manifest()
            manifest["chapters"][0]["frame_priority"] = 80
            return json.dumps(manifest)

        def fail_frames(blocks, manifest, duration_seconds):
            raise RuntimeError("ffmpeg unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "video.html"
            result = visual_generation.generate_api_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report="# Overview\n\nValidated.",
                trusted_metadata={"title": "Video", "duration_seconds": 60},
                media_source={"kind": "local-video", "url": None},
                output_destination=destination,
                complete=complete,
                parallel_map=serial_parallel_map,
                batch_size=2,
                concurrency=1,
                frame_provider=fail_frames,
            )
            self.assertTrue(result.html_path.exists())
            self.assertNotIn("<img", result.html_path.read_text(encoding="utf-8"))

    def test_compact_chinese_route_never_calls_frame_provider(self):
        visual_generation = load_visual_generation()
        blocks = compact_blocks()

        def complete(messages, max_tokens, label):
            if "VISUAL_BATCH_REQUEST" in messages[-1]["content"]:
                return batch_response(blocks)
            return json.dumps(compact_manifest(), ensure_ascii=False)

        frame_calls = []

        def forbidden_frame_provider(*args):
            frame_calls.append(args)
            return []

        expected = SimpleNamespace(html_path=Path("compact.html"), assets_dir=None)
        with tempfile.TemporaryDirectory() as temp_dir, (
            patch.object(visual_generation, "_validate_density")
        ), patch.object(visual_generation, "render_visual_brief", return_value=expected):
            result = visual_generation.generate_api_visual_brief(
                calibrated_transcript_blocks=blocks,
                validated_timeline_report="validated",
                trusted_metadata={"title": "短版解读", "duration_seconds": 3660},
                media_source={"kind": "remote-video", "url": "https://example.com/video"},
                output_destination=Path(temp_dir) / "compact.html",
                complete=complete,
                parallel_map=serial_parallel_map,
                batch_size=5,
                concurrency=1,
                frame_provider=forbidden_frame_provider,
            )
        self.assertIs(result, expected)
        self.assertEqual(frame_calls, [])

    def test_long_content_uses_fifteen_to_twenty_minute_density(self):
        prompts = []

        def complete(messages, max_tokens, label):
            prompt = messages[-1]["content"]
            prompts.append(prompt)
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            return json.dumps(api_manifest())

        with tempfile.TemporaryDirectory() as temp_dir:
            self.run_generation(
                complete,
                Path(temp_dir) / "episode.html",
                duration_seconds=3601,
            )
        self.assertIn("15-20", prompts[-1])
        self.assertNotIn("5-10", prompts[-1])

    def test_long_chinese_content_uses_compact_editorial_density(self):
        visual_generation = load_visual_generation()
        blocks = [
            {"window": "00:00-30:00", "text": "火箭回收推动航天运输规模化。"},
            {"window": "30:00-61:00", "text": "组织、工程和商业平台形成长期飞轮。"},
        ]

        prompt = visual_generation.build_visual_synthesis_prompt(
            [],
            "# Overview\n\nValidated overview.",
            {"title": "航天访谈", "duration_seconds": 3660},
            3660,
            calibrated_transcript_blocks=blocks,
            media_source={"kind": "remote-video", "url": "https://example.com/video"},
        )

        self.assertIn("5-7 minute", prompt)
        self.assertIn("exactly 4 core insights", prompt)
        self.assertIn("exactly 5 chapters", prompt)
        self.assertIn("1800-2500 visible CJK characters", prompt)
        self.assertIn("Do not emit quote visuals or frame_priority", prompt)
        self.assertNotIn("15-20", prompt)

    def test_compact_chinese_density_enforces_exact_structure_and_cjk_range(self):
        visual_generation = load_visual_generation()
        blocks = [{"window": "00:00-61:00", "text": "中文内容" * 200}]

        def compact_manifest(overview_length=1786, insight_count=4, chapter_count=5):
            return {
                "version": 1,
                "overview": {"text": "中" * overview_length, "source_windows": ["00:00-61:00"]},
                "core_insights": [
                    {"text": "中", "source_windows": ["00:00-61:00"]}
                    for _ in range(insight_count)
                ],
                "chapters": [
                    {
                        "id": f"chapter-{index}",
                        "title": {"text": "中", "source_windows": ["00:00-61:00"]},
                        "summary": {"text": "中", "source_windows": ["00:00-61:00"]},
                        "source_windows": ["00:00-61:00"],
                        "evidence": [],
                        "visuals": [],
                    }
                    for index in range(chapter_count)
                ],
            }

        visual_generation._validate_density(compact_manifest(), 3660, blocks)

        for invalid in (
            compact_manifest(overview_length=1785),
            compact_manifest(insight_count=3),
            compact_manifest(chapter_count=6),
        ):
            with self.assertRaisesRegex(ValueError, "compact density"):
                visual_generation._validate_density(invalid, 3660, blocks)

    def test_short_content_rejects_synthesis_above_density_limit(self):
        visual_generation = load_visual_generation()

        def complete(messages, max_tokens, label):
            prompt = messages[-1]["content"]
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            manifest = api_manifest()
            manifest["core_insights"] = [f"Insight {index}" for index in range(7)]
            return json.dumps(manifest)

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "episode.html"
            with self.assertRaises(visual_generation.VisualStageError) as caught:
                self.run_generation(complete, destination)
            self.assertIn("density", str(caught.exception))
            self.assertFalse(destination.exists())

    def test_short_content_rejects_sixth_visual(self):
        visual_generation = load_visual_generation()

        def complete(messages, max_tokens, label):
            prompt = messages[-1]["content"]
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            manifest = api_manifest()
            manifest["chapters"][0]["visuals"].append(
                manifest["chapters"][0]["visuals"][0]
            )
            return json.dumps(manifest)

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(visual_generation.VisualStageError) as caught:
                self.run_generation(complete, Path(temp_dir) / "episode.html")
            self.assertIn("density", str(caught.exception))

    def test_long_content_rejects_ninth_visual(self):
        visual_generation = load_visual_generation()

        def complete(messages, max_tokens, label):
            prompt = messages[-1]["content"]
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            manifest = api_manifest()
            manifest["chapters"][0]["visuals"].extend(
                manifest["chapters"][0]["visuals"][:4]
            )
            return json.dumps(manifest)

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(visual_generation.VisualStageError) as caught:
                self.run_generation(
                    complete,
                    Path(temp_dir) / "episode.html",
                    duration_seconds=3601,
                )
            self.assertIn("density", str(caught.exception))

    def test_no_supported_visual_renders_editorial_insight_presentation(self):
        def complete(messages, max_tokens, label):
            prompt = messages[-1]["content"]
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            manifest = api_manifest()
            manifest["chapters"][0]["visuals"] = []
            return json.dumps(manifest)

        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_generation(complete, Path(temp_dir) / "episode.html")
            page = result.html_path.read_text(encoding="utf-8")
            self.assertIn("editorial-insight", page)
            self.assertNotIn("<img", page)

    def test_invalid_global_synthesis_publishes_no_reader(self):
        visual_generation = load_visual_generation()
        labels = []

        def complete(messages, max_tokens, label):
            labels.append(label)
            prompt = messages[-1]["content"]
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            manifest = api_manifest()
            manifest["chapters"][0]["source_windows"] = ["00:00-00:30"]
            return json.dumps(manifest)

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "episode.html"
            with self.assertRaises(visual_generation.VisualStageError):
                self.run_generation(complete, destination)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name("episode_assets").exists())
        self.assertEqual(labels, ["visual batch 1/1", "visual synthesis", "visual synthesis repair"])

    def test_invalid_global_synthesis_is_repaired_once(self):
        visual_generation = load_visual_generation()
        labels = []
        synthesis_prompts = []

        def complete(messages, max_tokens, label):
            labels.append(label)
            prompt = messages[-1]["content"]
            if "VISUAL_BATCH_REQUEST" in prompt:
                return batch_response(TRANSCRIPT_BLOCKS)
            synthesis_prompts.append(prompt)
            if label == "visual synthesis":
                manifest = api_manifest()
                manifest["chapters"][0]["source_windows"] = ["00:00-00:30"]
                return json.dumps(manifest)
            self.assertIn("Validation error", prompt)
            return json.dumps(api_manifest())

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "episode.html"
            result = self.run_generation(complete, destination)
            self.assertTrue(result.html_path.exists())
        self.assertEqual(labels, ["visual batch 1/1", "visual synthesis", "visual synthesis repair"])
        self.assertEqual(
            [calibrated_transcript_payload(prompt) for prompt in synthesis_prompts],
            [TRANSCRIPT_BLOCKS, TRANSCRIPT_BLOCKS],
        )


class APILLMVisualIntegrationTests(unittest.TestCase):
    def test_transcript_input_uses_transcript_media_description(self):
        tool = load_podcast_tool()
        transcript_args = SimpleNamespace(transcript_input="episode_calibrated.txt", input=None)
        remote_audio_args = SimpleNamespace(
            transcript_input=None,
            input="https://example.com/episode.mp3",
        )
        self.assertEqual(
            tool.visual_media_source(transcript_args),
            {"kind": "transcript", "url": None},
        )
        self.assertEqual(
            tool.visual_media_source(remote_audio_args),
            {"kind": "audio", "url": "https://example.com/episode.mp3"},
        )

    def test_visual_failure_after_markdown_publication_preserves_report(self):
        tool = load_podcast_tool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "episode_timeline.md"
            report_path.write_text("published Markdown", encoding="utf-8")

            def fail_visual(**kwargs):
                self.assertTrue(report_path.exists())
                self.assertEqual(report_path.read_text(encoding="utf-8"), "published Markdown")
                raise tool.VisualStageError("invalid global synthesis")

            with patch.object(tool, "generate_api_visual_brief", side_effect=fail_visual):
                with patch("builtins.print") as output:
                    result = tool.attempt_api_visual_brief(
                        llm_provider=object(),
                        transcript_blocks=TRANSCRIPT_BLOCKS,
                        report="validated report",
                        report_path=report_path,
                        metadata={"title": "Episode"},
                        media_source={"kind": "audio", "url": None},
                        output_destination=root / "episode.html",
                        batch_size=2,
                        concurrency=1,
                    )

            self.assertIsNone(result)
            self.assertEqual(report_path.read_text(encoding="utf-8"), "published Markdown")
            warning = " ".join(str(arg) for call in output.call_args_list for arg in call.args)
            self.assertIn("visual", warning.lower())
            self.assertIn(str(report_path), warning)

    def test_manual_timeline_merge_automatically_starts_visual_prompt_stage(self):
        tool = load_podcast_tool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript_path = root / "episode_calibrated.txt"
            transcript_path.write_text(
                "\n\n".join(
                    f'[{block["window"]}]\n{block["text"]}'
                    for block in TRANSCRIPT_BLOCKS
                ),
                encoding="utf-8",
            )
            sections = root / "sections"
            sections.mkdir()
            (sections / "batch_001.md").write_text(
                "## 00:00-00:30 Growth\n\nEvidence-backed growth section.\n\n"
                "## 00:30-01:00 Retention\n\nEvidence-backed retention section.\n",
                encoding="utf-8",
            )
            output_dir = root / "output"
            argv = [
                str(SCRIPTS_DIR / "mimo_podcast_tool.py"),
                "--transcript-input",
                str(transcript_path),
                "--manual-sections-dir",
                str(sections),
                "--output-dir",
                str(output_dir),
                "--title",
                "Launch review",
            ]
            with patch.object(sys, "argv", argv):
                tool.main()

            self.assertTrue((output_dir / "Launch_review_逐窗口深度解读.md").is_file())
            prompt_root = output_dir / "Launch_review_visual_prompts"
            self.assertTrue((prompt_root / "workflow.json").is_file())
            self.assertTrue((prompt_root / "batch_prompts" / "001.md").is_file())
            self.assertFalse((output_dir / "Launch_review_图文速览.html").exists())

    def test_manual_visual_prompt_failure_preserves_published_markdown(self):
        tool = load_podcast_tool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcript_path = root / "episode_calibrated.txt"
            transcript_path.write_text(
                "\n\n".join(
                    f'[{block["window"]}]\n{block["text"]}'
                    for block in TRANSCRIPT_BLOCKS
                ),
                encoding="utf-8",
            )
            sections = root / "sections"
            sections.mkdir()
            (sections / "batch_001.md").write_text(
                "## 00:00-00:30 Growth\n\nEvidence-backed growth section.\n\n"
                "## 00:30-01:00 Retention\n\nEvidence-backed retention section.\n",
                encoding="utf-8",
            )
            output_dir = root / "output"
            argv = [
                str(SCRIPTS_DIR / "mimo_podcast_tool.py"),
                "--transcript-input",
                str(transcript_path),
                "--manual-sections-dir",
                str(sections),
                "--output-dir",
                str(output_dir),
                "--title",
                "Launch review",
            ]
            with patch.object(sys, "argv", argv), patch.object(
                tool,
                "export_visual_prompts",
                side_effect=OSError("disk full"),
            ), patch("builtins.print") as output:
                tool.main()

            report_path = output_dir / "Launch_review_逐窗口深度解读.md"
            self.assertTrue(report_path.is_file())
            warning = " ".join(str(arg) for call in output.call_args_list for arg in call.args)
            self.assertIn("visual", warning.lower())
            self.assertIn(str(report_path), warning)


if __name__ == "__main__":
    unittest.main()
