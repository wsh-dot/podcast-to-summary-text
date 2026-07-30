import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
    / "mimo_podcast_tool.py"
)


def load_tool():
    spec = importlib.util.spec_from_file_location("asr_resilience_tool", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT_PATH.parent))
    return module


class ASRResilienceTests(unittest.TestCase):
    def test_download_audio_configures_network_retries(self):
        tool = load_tool()

        class Completed:
            returncode = 0
            stderr = ""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "downloaded.mp3").write_bytes(b"audio")
            with patch.object(tool.subprocess, "run", return_value=Completed()) as run:
                result = tool.download_audio("https://example.com/episode", root)

        command = run.call_args.args[0]
        self.assertEqual(result.name, "downloaded.mp3")
        self.assertIn("--retries", command)
        self.assertIn("--fragment-retries", command)
        self.assertIn("--socket-timeout", command)

    def test_rate_limit_uses_retry_after_and_more_than_generic_retry_budget(self):
        tool = load_tool()
        calls = 0
        delays = []

        class Provider:
            def transcribe_chunk(self, path):
                nonlocal calls
                calls += 1
                if calls <= tool.MAX_RETRIES:
                    raise HTTPError(
                        "https://api.stepfun.com/v1/audio/transcriptions",
                        429,
                        "Too Many Requests",
                        {"Retry-After": "3"},
                        None,
                    )
                return "recovered"

        result = tool.transcribe_chunk_with_retry(
            Provider(),
            Path("chunk.mp3"),
            0,
            1,
            "00:00-00:03",
            sleep_fn=delays.append,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(calls, tool.MAX_RETRIES + 1)
        self.assertEqual(delays, [3, 3, 3])

    def test_rate_limit_budget_covers_interleaved_risk_block(self):
        tool = load_tool()
        failures = [
            HTTPError("https://api.stepfun.com", 429, "Too Many Requests", {}, None),
            HTTPError("https://api.stepfun.com", 429, "Too Many Requests", {}, None),
            RuntimeError("risk blocked"),
        ]
        delays = []

        class Provider:
            def transcribe_chunk(self, path):
                if failures:
                    raise failures.pop(0)
                return "recovered"

        result = tool.transcribe_chunk_with_retry(
            Provider(),
            Path("chunk.mp3"),
            0,
            1,
            "00:00-00:03",
            sleep_fn=delays.append,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(delays, [15, 30, 2])

    def test_persistent_risk_block_splits_inside_original_window(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            main_chunk = root / "chunk_000.mp3"
            subchunks = [root / f"sub_{index}.mp3" for index in range(3)]
            for path in [main_chunk, *subchunks]:
                path.write_bytes(b"audio")

            class Provider:
                def __init__(self):
                    self.calls = []

                def transcribe_chunk(self, path):
                    name = Path(path).name
                    self.calls.append(name)
                    if name == main_chunk.name:
                        raise RuntimeError("risk blocked")
                    return f"text-{Path(path).stem}"

            provider = Provider()
            with patch.object(
                tool,
                "chunk_audio",
                side_effect=[[main_chunk], subchunks],
            ):
                transcript = tool.transcribe_audio(
                    provider,
                    root / "episode.m4a",
                    root,
                    segment_minutes=3,
                    duration_seconds=180,
                    retry_sleep=lambda delay: None,
                )

            blocks = tool.parse_transcript_blocks(transcript)
            self.assertEqual([block["window"] for block in blocks], ["00:00-00:03"])
            self.assertEqual(blocks[0]["text"], "text-sub_0\ntext-sub_1\ntext-sub_2")
            self.assertEqual(provider.calls.count(main_chunk.name), 3)

    def test_persistent_transport_failure_splits_inside_original_window(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            main_chunk = root / "chunk_000.mp3"
            subchunks = [root / f"sub_{index}.mp3" for index in range(3)]
            for path in [main_chunk, *subchunks]:
                path.write_bytes(b"audio")

            class Provider:
                def __init__(self):
                    self.calls = []

                def transcribe_chunk(self, path):
                    name = Path(path).name
                    self.calls.append(name)
                    if name == main_chunk.name:
                        raise URLError("The write operation timed out")
                    return f"text-{Path(path).stem}"

            provider = Provider()
            with patch.object(
                tool,
                "chunk_audio",
                side_effect=[[main_chunk], subchunks],
            ):
                transcript = tool.transcribe_audio(
                    provider,
                    root / "episode.m4a",
                    root,
                    segment_minutes=3,
                    duration_seconds=180,
                    retry_sleep=lambda _delay: None,
                )

            blocks = tool.parse_transcript_blocks(transcript)
            self.assertEqual([block["window"] for block in blocks], ["00:00-00:03"])
            self.assertEqual(blocks[0]["text"], "text-sub_0\ntext-sub_1\ntext-sub_2")
            self.assertEqual(provider.calls.count(main_chunk.name), 3)

    def test_transcription_checkpoints_each_window_and_resumes_prefix(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chunks = [root / f"chunk_{index:03d}.mp3" for index in range(3)]
            for chunk in chunks:
                chunk.write_bytes(b"audio")
            checkpoint = root / "episode_asr_checkpoint.json"

            class InterruptedProvider:
                def __init__(self):
                    self.calls = []

                def transcribe_chunk(self, path):
                    self.calls.append(Path(path).name)
                    if len(self.calls) == 2:
                        raise KeyboardInterrupt()
                    return f"text for {Path(path).stem}"

            first = InterruptedProvider()
            with patch.object(tool, "chunk_audio", return_value=chunks):
                with self.assertRaises(KeyboardInterrupt):
                    tool.transcribe_audio(
                        first,
                        root / "episode.m4a",
                        root,
                        segment_minutes=3,
                        duration_seconds=540,
                        checkpoint_path=checkpoint,
                        retry_sleep=lambda delay: None,
                    )

            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual([block["window"] for block in saved["blocks"]], ["00:00-00:03"])

            class ResumeProvider:
                def __init__(self):
                    self.calls = []

                def transcribe_chunk(self, path):
                    self.calls.append(Path(path).name)
                    return f"text for {Path(path).stem}"

            resumed = ResumeProvider()
            with patch.object(tool, "chunk_audio", return_value=chunks):
                transcript = tool.transcribe_audio(
                    resumed,
                    root / "episode.m4a",
                    root,
                    segment_minutes=3,
                    duration_seconds=540,
                    checkpoint_path=checkpoint,
                    retry_sleep=lambda delay: None,
                )

            self.assertEqual(resumed.calls, ["chunk_001.mp3", "chunk_002.mp3"])
            self.assertEqual(
                [block["window"] for block in tool.parse_transcript_blocks(transcript)],
                ["00:00-00:03", "00:03-00:06", "00:06-00:09"],
            )

    def test_chunk_audio_replaces_undecodable_ffmpeg_output(self):
        tool = load_tool()

        class Completed:
            returncode = 1
            stderr = "replacement-safe"

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            tool.subprocess,
            "run",
            return_value=Completed(),
        ) as run:
            with self.assertRaisesRegex(RuntimeError, "replacement-safe"):
                tool.chunk_audio(Path(temp_dir) / "episode.m4a", Path(temp_dir))

        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs.get("encoding"), "utf-8")
            self.assertEqual(call.kwargs.get("errors"), "replace")

    def test_cli_uses_stable_checkpoint_and_removes_it_after_transcript_publish(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "episode.m4a"
            audio.write_bytes(b"audio")
            output_dir = root / "output"
            observed = {}

            def fake_transcribe(*args, **kwargs):
                observed.update(kwargs)
                checkpoint = Path(kwargs["checkpoint_path"])
                checkpoint.write_text("checkpoint", encoding="utf-8")
                return "[00:00-00:01]\nRecovered transcript."

            argv = [
                str(SCRIPT_PATH),
                str(audio),
                "--transcribe-only",
                "--asr-provider",
                "stepfun",
                "--asr-api-key",
                "fixture-key",
                "--output-dir",
                str(output_dir),
                "--title",
                "Resume fixture",
            ]
            with patch.object(sys, "argv", argv), patch.object(
                tool, "check_ffmpeg", return_value=True
            ), patch.object(
                tool, "create_asr_provider", return_value=object()
            ), patch.object(
                tool, "resolve_input_audio", return_value=audio
            ), patch.object(
                tool, "get_audio_duration", return_value=60
            ), patch.object(
                tool, "transcribe_audio", side_effect=fake_transcribe
            ):
                tool.main()

            expected_checkpoint = output_dir / "Resume_fixture_asr_checkpoint.json"
            self.assertEqual(Path(observed["checkpoint_path"]), expected_checkpoint)
            self.assertEqual(observed["checkpoint_id"], str(audio))
            self.assertFalse(expected_checkpoint.exists())
            self.assertTrue((output_dir / "Resume_fixture_转写.txt").is_file())


if __name__ == "__main__":
    unittest.main()
