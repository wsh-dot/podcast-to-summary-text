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
SPEC = importlib.util.spec_from_file_location("mimo_podcast_tool_funasr_flash", SCRIPT_PATH)
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


class FakeJSONResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


class AliyunFunASRFlashProviderTests(unittest.TestCase):
    def test_posts_documented_mp3_payload_and_returns_output_text(self):
        requests = []

        def opener(request, *, timeout):
            requests.append((request, timeout))
            return FakeJSONResponse(
                {
                    "output": {
                        "sentence": {"text": "分句文本"},
                        "text": "完整转写文本",
                    },
                    "request_id": "request-1",
                }
            )

        provider = tool.AliyunFunASRFlashProvider(
            api_key="dashscope-secret",
            base_url="https://dashscope.aliyuncs.com/api/v1",
            model="fun-asr-flash-2026-06-15",
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
        self.assertEqual(
            request.full_url,
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/"
            "multimodal-generation/generation",
        )
        self.assertEqual(timeout, 45)
        self.assertEqual(request.get_header("Authorization"), "Bearer dashscope-secret")
        self.assertEqual(request.get_header("X-dashscope-sse"), "disable")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "fun-asr-flash-2026-06-15")
        self.assertEqual(payload["parameters"], {"format": "mp3"})
        self.assertEqual(
            payload["input"]["messages"][0]["content"][0]["input_audio"]["data"],
            "data:audio/mpeg;base64,dGVzdC1hdWRpbw==",
        )

    def test_accepts_full_generation_endpoint_without_appending_twice(self):
        endpoint = (
            "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/services/"
            "aigc/multimodal-generation/generation"
        )
        provider = tool.AliyunFunASRFlashProvider(
            api_key="secret",
            base_url=endpoint,
            model="fun-asr-flash-2026-06-15",
        )
        self.assertEqual(provider.endpoint, endpoint)

    def test_rejects_response_without_output_text(self):
        provider = tool.AliyunFunASRFlashProvider(
            api_key="secret",
            base_url="https://dashscope.aliyuncs.com/api/v1",
            model="fun-asr-flash-2026-06-15",
            opener=lambda _request, *, timeout: FakeJSONResponse(
                {"output": {"sentence": {}}, "request_id": "bad-response"}
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "chunk.mp3"
            audio_path.write_bytes(b"audio")
            with self.assertRaisesRegex(RuntimeError, "bad-response"):
                provider.transcribe_chunk(audio_path)


class AliyunFunASRFlashRoutingTests(unittest.TestCase):
    def test_factory_selects_funasr_flash_defaults(self):
        argv = [
            str(SCRIPT_PATH),
            "episode.mp3",
            "--asr-provider",
            "aliyun-funasr-flash",
            "--asr-api-key",
            "dashscope-secret",
        ]
        with patch.object(sys, "argv", argv):
            args = tool.parse_args()
        provider = tool.create_asr_provider(args)

        self.assertIsInstance(provider, tool.AliyunFunASRFlashProvider)
        self.assertEqual(provider.model, "fun-asr-flash-2026-06-15")
        self.assertEqual(provider.endpoint, "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")


if __name__ == "__main__":
    unittest.main()
