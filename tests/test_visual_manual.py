import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_visual_generation import TRANSCRIPT_BLOCKS, batch_response
from tests.test_visual_reader import compact_blocks, compact_manifest, valid_manifest


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
)
MODULE_PATH = SCRIPTS_DIR / "visual_manual.py"


def load_visual_manual():
    spec = importlib.util.spec_from_file_location("visual_manual", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


def load_podcast_tool():
    path = SCRIPTS_DIR / "mimo_podcast_tool.py"
    spec = importlib.util.spec_from_file_location("visual_manual_podcast_tool", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


REPORT = (
    "# Timeline\n\n## Core overview\n\nValidated overview.\n\n"
    "## 00:00-00:30 First\n\nFirst detail.\n\n"
    "## 00:30-01:00 Second\n\nSecond detail."
)


def calibrated_transcript_payload(prompt):
    start_marker = "CALIBRATED_TRANSCRIPT_JSON:\n"
    end_marker = "\nVALIDATED_VISUAL_BATCHES_JSON:"
    start = prompt.index(start_marker) + len(start_marker)
    end = prompt.index(end_marker, start)
    return json.loads(prompt[start:end])


class ManualVisualWorkflowTests(unittest.TestCase):
    def test_compact_manual_route_never_calls_frame_provider(self):
        visual_manual = load_visual_manual()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "manifest.json").write_text(
                json.dumps(compact_manifest(), ensure_ascii=False),
                encoding="utf-8",
            )

            frame_calls = []

            def forbidden_frame_provider(*args):
                frame_calls.append(args)
                return []

            result = visual_manual.render_manual_visual_brief(
                calibrated_transcript_blocks=compact_blocks(),
                validated_timeline_report="validated",
                trusted_metadata={"title": "短版解读", "duration_seconds": 3660},
                media_source={"kind": "remote-video", "url": "https://example.com/video"},
                prompt_root=root,
                output_destination=root / "compact.html",
                frame_provider=forbidden_frame_provider,
            )
            self.assertIsNone(result.assets_dir)
            self.assertEqual(frame_calls, [])
    def test_export_validate_synthesize_and_render_without_llm(self):
        visual_manual = load_visual_manual()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prompt_root = visual_manual.export_visual_prompts(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report=REPORT,
                trusted_metadata={"title": "Launch review", "duration_seconds": 60},
                output_dir=root,
                base_name="episode",
                batch_size=1,
            )

            prompt_files = sorted((prompt_root / "batch_prompts").glob("*.md"))
            self.assertEqual([path.name for path in prompt_files], ["001.md", "002.md"])
            self.assertTrue((prompt_root / "batch_results").is_dir())
            first_prompt = prompt_files[0].read_text(encoding="utf-8")
            self.assertIn("00:00-00:30", first_prompt)
            self.assertIn("001.json", first_prompt)
            self.assertIn("JSON only", first_prompt)
            for forbidden in ("HTML", "CSS", "JavaScript", "SVG"):
                self.assertIn(forbidden, first_prompt)

            (prompt_root / "batch_results" / "001.json").write_text(
                batch_response(TRANSCRIPT_BLOCKS[:1]), encoding="utf-8"
            )
            (prompt_root / "batch_results" / "002.json").write_text(
                batch_response(TRANSCRIPT_BLOCKS[1:]), encoding="utf-8"
            )
            synthesis_path = visual_manual.prepare_visual_synthesis(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report=REPORT,
                trusted_metadata={"title": "Launch review", "duration_seconds": 60},
                media_source={"kind": "remote-video", "url": "https://example.com/episode"},
                prompt_root=prompt_root,
                batch_size=1,
            )
            synthesis_prompt = synthesis_path.read_text(encoding="utf-8")
            self.assertIn("VALIDATED_VISUAL_BATCHES_JSON", synthesis_prompt)
            self.assertIn("001.json", synthesis_prompt)
            self.assertIn("Source kind: remote-video.", synthesis_prompt)
            self.assertEqual(calibrated_transcript_payload(synthesis_prompt), TRANSCRIPT_BLOCKS)
            self.assertNotIn("First detail.", synthesis_prompt)

            (prompt_root / "manifest.json").write_text(
                json.dumps(valid_manifest()), encoding="utf-8"
            )
            result = visual_manual.render_manual_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report=REPORT,
                trusted_metadata={"title": "Launch review", "duration_seconds": 60},
                media_source={"kind": "transcript", "url": None},
                prompt_root=prompt_root,
                output_destination=root / "episode.html",
            )
            page = result.html_path.read_text(encoding="utf-8")
            self.assertIn("Launch effects", page)
            self.assertTrue((result.assets_dir / "frames").is_dir())

    def test_missing_extra_and_malformed_batch_results_are_actionable(self):
        visual_manual = load_visual_manual()
        mutations = ("missing", "extra", "malformed")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                prompt_root = visual_manual.export_visual_prompts(
                    calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                    validated_timeline_report=REPORT,
                    trusted_metadata={"title": "Launch review"},
                    output_dir=root,
                    base_name="episode",
                    batch_size=1,
                )
                results = prompt_root / "batch_results"
                if mutation != "missing":
                    (results / "001.json").write_text(
                        batch_response(TRANSCRIPT_BLOCKS[:1]), encoding="utf-8"
                    )
                (results / "002.json").write_text(
                    batch_response(TRANSCRIPT_BLOCKS[1:]), encoding="utf-8"
                )
                if mutation == "extra":
                    (results / "003.json").write_text("{}", encoding="utf-8")
                if mutation == "malformed":
                    (results / "001.json").write_text("not json", encoding="utf-8")

                with self.assertRaises(visual_manual.VisualStageError) as caught:
                    visual_manual.prepare_visual_synthesis(
                        calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                        validated_timeline_report=REPORT,
                        trusted_metadata={"title": "Launch review"},
                        media_source={"kind": "remote-video", "url": "https://example.com/episode"},
                        prompt_root=prompt_root,
                        batch_size=1,
                    )
                self.assertIn(mutation if mutation != "malformed" else "invalid", str(caught.exception))

    def test_cli_accepts_three_stage_manual_visual_options(self):
        tool = load_podcast_tool()
        argv = [
            str(SCRIPTS_DIR / "mimo_podcast_tool.py"),
            "--transcript-input",
            "episode_calibrated.txt",
            "--visual-report-input",
            "episode_timeline.md",
            "--prepare-visual-synthesis",
            "--visual-prompts-dir",
            "episode_visual_prompts",
        ]
        with patch.object(sys, "argv", argv):
            args = tool.parse_args()
        self.assertTrue(args.prepare_visual_synthesis)
        self.assertEqual(args.visual_report_input, "episode_timeline.md")
        self.assertEqual(args.visual_prompts_dir, "episode_visual_prompts")


if __name__ == "__main__":
    unittest.main()
