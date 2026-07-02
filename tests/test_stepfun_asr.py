import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
    / "mimo_podcast_tool.py"
)
SPEC = importlib.util.spec_from_file_location("mimo_podcast_tool_stepfun", SCRIPT_PATH)
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


class FakeSSEResponse(io.BytesIO):
    def __init__(self, events):
        payload = "".join(
            f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            for event in events
        ).encode("utf-8")
        super().__init__(payload)


class StepFunSSEProviderTests(unittest.TestCase):
    def test_posts_documented_mp3_payload_and_returns_done_text(self):
        requests = []
        events = [
            {
                "type": "transcript.text.delta",
                "meta": {"session_id": "sse_1", "timestamp": 1},
                "delta": "增量文本",
                "item_id": "item_1",
                "content_index": 0,
                "start_time": 0,
                "end_time": 500,
            },
            {
                "type": "transcript.text.done",
                "meta": {"session_id": "sse_1", "timestamp": 2},
                "text": "完整转写文本",
                "usage": {
                    "type": "realtime_asr",
                    "input_tokens": 100,
                    "input_token_details": {"text_tokens": 0, "audio_tokens": 100},
                    "output_tokens": 5,
                    "total_tokens": 105,
                },
            },
        ]

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeSSEResponse(events)

        provider = tool.StepFunSSEASRProvider(
            api_key="step-secret",
            base_url="https://api.stepfun.com/v1",
            model="stepaudio-2.5-asr",
            language="zh",
            timeout=45,
            opener=opener,
        )
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "chunk.mp3"
            audio_path.write_bytes(b"test-audio")
            result = provider.transcribe_chunk(audio_path)

        self.assertEqual(result, "完整转写文本")
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(request.full_url, "https://api.stepfun.com/v1/audio/asr/sse")
        self.assertEqual(timeout, 45)
        self.assertEqual(request.get_header("Authorization"), "Bearer step-secret")
        self.assertEqual(request.get_header("Accept"), "text/event-stream")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["audio"]["data"], "dGVzdC1hdWRpbw==")
        self.assertEqual(
            payload["audio"]["input"]["transcription"],
            {
                "model": "stepaudio-2.5-asr",
                "enable_itn": True,
                "language": "zh",
            },
        )
        self.assertEqual(payload["audio"]["input"]["format"], {"type": "mp3"})

    def test_uses_delta_text_when_done_event_has_no_text(self):
        events = [
            {"type": "transcript.text.delta", "delta": "第一段"},
            {"type": "transcript.text.delta", "delta": "第二段"},
            {"type": "transcript.text.done", "text": ""},
        ]
        provider = tool.StepFunSSEASRProvider(
            api_key="step-secret",
            base_url="https://api.stepfun.com/step_plan/v1",
            model="stepaudio-2.5-asr",
            opener=lambda _request, _timeout: FakeSSEResponse(events),
        )
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "chunk.mp3"
            audio_path.write_bytes(b"audio")
            result = provider.transcribe_chunk(audio_path)

        self.assertEqual(result, "第一段第二段")

    def test_raises_documented_sse_error_event(self):
        events = [
            {
                "type": "error",
                "meta": {"session_id": "sse_1", "timestamp": 3},
                "message": "quota exhausted",
            }
        ]
        provider = tool.StepFunSSEASRProvider(
            api_key="step-secret",
            base_url="https://api.stepfun.com/v1",
            model="stepaudio-2.5-asr",
            opener=lambda _request, _timeout: FakeSSEResponse(events),
        )
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "chunk.mp3"
            audio_path.write_bytes(b"audio")
            with self.assertRaisesRegex(RuntimeError, "quota exhausted"):
                provider.transcribe_chunk(audio_path)

    def test_rejects_stream_that_ends_before_done_event(self):
        events = [
            {"type": "transcript.text.delta", "delta": "可能不完整的文本"},
        ]
        provider = tool.StepFunSSEASRProvider(
            api_key="step-secret",
            base_url="https://api.stepfun.com/v1",
            model="stepaudio-2.5-asr",
            opener=lambda _request, _timeout: FakeSSEResponse(events),
        )
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "chunk.mp3"
            audio_path.write_bytes(b"audio")
            with self.assertRaisesRegex(RuntimeError, "transcript.text.done"):
                provider.transcribe_chunk(audio_path)


class StepFunRoutingTests(unittest.TestCase):
    def test_cli_selects_step_plan_without_changing_provider_name(self):
        argv = [
            str(SCRIPT_PATH),
            "episode.mp3",
            "--asr-provider",
            "stepfun",
            "--stepfun-plan",
            "--stepfun-language",
            "zh",
        ]
        with patch.object(sys, "argv", argv):
            args = tool.parse_args()

        self.assertEqual(args.asr_provider, "stepfun")
        self.assertTrue(args.stepfun_plan)
        self.assertEqual(args.stepfun_language, "zh")

    def test_factory_routes_step_plan_to_dedicated_prefix(self):
        argv = [
            str(SCRIPT_PATH),
            "episode.mp3",
            "--asr-provider",
            "stepfun",
            "--stepfun-plan",
            "--asr-api-key",
            "step-secret",
        ]
        with patch.object(sys, "argv", argv):
            args = tool.parse_args()
        provider = tool.create_asr_provider(args)

        self.assertIsInstance(provider, tool.StepFunSSEASRProvider)
        self.assertEqual(provider.base_url, "https://api.stepfun.com/step_plan/v1")
        self.assertEqual(provider.model, "stepaudio-2.5-asr")


if __name__ == "__main__":
    unittest.main()
