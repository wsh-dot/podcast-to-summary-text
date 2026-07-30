import importlib.util
import os
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
SPEC = importlib.util.spec_from_file_location("mimo_podcast_tool_credentials", SCRIPT_PATH)
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


class FakeAuthError(Exception):
    status_code = 401


class ASRCredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "credentials.json"
        self.env = patch.dict(
            os.environ,
            {tool.CREDENTIAL_STORE_ENV: str(self.store_path)},
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp_dir.cleanup()

    def test_successful_provided_key_is_saved_and_reused(self):
        provider = tool.StepFunSSEASRProvider(
            api_key="step-secret",
            base_url=tool.STEPFUN_BASE_URL,
            model="stepaudio-2.5-asr",
        )
        tool._attach_asr_credential_state(
            provider,
            "stepfun",
            {"api_key": "step-secret"},
            used_cache=False,
        )

        self.assertFalse(self.store_path.exists())
        tool.persist_successful_asr_credentials(provider)
        self.assertEqual(
            tool.load_asr_credentials()["stepfun"]["api_key"],
            "step-secret",
        )

        argv = [
            str(SCRIPT_PATH),
            "episode.mp3",
            "--asr-provider",
            "stepfun",
        ]
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("ASR_API_KEY", "STEPFUN_API_KEY", "STEP_API_KEY")
        }
        with patch.dict(os.environ, clean_env, clear=True), patch.object(sys, "argv", argv):
            args = tool.parse_args()
            cached_provider = tool.create_asr_provider(args)

        self.assertEqual(cached_provider.api_key, "step-secret")
        self.assertEqual(cached_provider._credential_source, "cache")

    def test_cached_authentication_failure_forgets_only_that_provider(self):
        tool.save_asr_credentials("stepfun", {"api_key": "expired"})
        tool.save_asr_credentials("mimo", {"api_key": "tp-still-valid"})
        provider = tool.StepFunSSEASRProvider(
            api_key="expired",
            base_url=tool.STEPFUN_BASE_URL,
            model="stepaudio-2.5-asr",
        )
        tool._attach_asr_credential_state(
            provider,
            "stepfun",
            {"api_key": "expired"},
            used_cache=True,
        )

        handled = tool.handle_cached_asr_authentication_error(
            provider,
            FakeAuthError("unauthorized"),
        )

        self.assertTrue(handled)
        credentials = tool.load_asr_credentials()
        self.assertNotIn("stepfun", credentials)
        self.assertEqual(credentials["mimo"]["api_key"], "tp-still-valid")

    def test_non_authentication_failure_keeps_cached_key(self):
        tool.save_asr_credentials("stepfun", {"api_key": "step-secret"})
        provider = tool.StepFunSSEASRProvider(
            api_key="step-secret",
            base_url=tool.STEPFUN_BASE_URL,
            model="stepaudio-2.5-asr",
        )
        tool._attach_asr_credential_state(
            provider,
            "stepfun",
            {"api_key": "step-secret"},
            used_cache=True,
        )

        handled = tool.handle_cached_asr_authentication_error(
            provider,
            RuntimeError("rate limit"),
        )

        self.assertFalse(handled)
        self.assertEqual(
            tool.load_asr_credentials()["stepfun"]["api_key"],
            "step-secret",
        )

    def test_authentication_failure_is_not_retried(self):
        class RejectedProvider:
            def __init__(self):
                self.calls = 0

            def transcribe_chunk(self, _path):
                self.calls += 1
                raise FakeAuthError("unauthorized")

        provider = RejectedProvider()
        with patch.object(tool.time, "sleep") as sleep:
            with self.assertRaises(FakeAuthError):
                tool.transcribe_chunk_with_retry(
                    provider,
                    Path("unused.mp3"),
                    0,
                    1,
                    "00:00-00:03",
                )

        self.assertEqual(provider.calls, 1)
        sleep.assert_not_called()

    def test_forget_removes_last_store_file(self):
        tool.save_asr_credentials("aliyun-qwen", {"api_key": "dashscope-secret"})

        self.assertTrue(tool.forget_asr_credentials("aliyun-qwen"))
        self.assertFalse(self.store_path.exists())


if __name__ == "__main__":
    unittest.main()
