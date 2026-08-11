import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "mimo-token-plan-asr-llm-pipeline"
SKILL_MD = SKILL_ROOT / "SKILL.md"


def skill_text():
    return SKILL_MD.read_text(encoding="utf-8")


def frontmatter(text):
    match = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        raise AssertionError("SKILL.md must start with YAML frontmatter")
    fields = {}
    for line in match.group(1).splitlines():
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


class SkillPackageTests(unittest.TestCase):
    def test_description_is_trigger_focused_and_discoverable(self):
        fields = frontmatter(skill_text())

        self.assertEqual(set(fields), {"name", "description"})
        self.assertTrue(fields["description"].startswith("Use when "))
        self.assertLessEqual(len(fields["description"]), 500)
        for keyword in ("播客", "Bilibili", "transcript", "ASR", "Fun-ASR-Flash", "DashScope", "HTML"):
            self.assertIn(keyword, fields["description"])

    def test_english_provider_reference_includes_funasr_flash(self):
        providers = (SKILL_ROOT / "references" / "providers.en.md").read_text(encoding="utf-8")
        for keyword in (
            "Alibaba Fun-ASR-Flash",
            "--asr-provider aliyun-funasr-flash",
            "fun-asr-flash-2026-06-15",
            "https://dashscope.aliyuncs.com/api/v1",
            "multimodal-generation",
            "5-minute limit",
        ):
            self.assertIn(keyword, providers)

    def test_bilingual_readmes_document_latest_bundle_and_funasr(self):
        chinese = (ROOT / "README.zh.md").read_text(encoding="utf-8")
        english = (ROOT / "README.en.md").read_text(encoding="utf-8")

        for text in (chinese, english):
            self.assertIn("aliyun-funasr-flash", text)
            self.assertIn("fun-asr-flash-2026-06-15", text)
            self.assertIn("multimodal-generation", text)
            self.assertIn("<base>_转写.txt", text)
            self.assertIn("<base>_逐窗口深度解读.md", text)
            self.assertIn("<base>_图文速览.html", text)
            self.assertIn("VisualBriefManifest v2", text)
            self.assertIn("17/17", text)

    def test_verification_commands_are_cross_platform(self):
        text = skill_text()

        self.assertIn("安装后的 skill 包必须运行以下安装态验证", text)
        self.assertIn("修改源码仓库时还必须从仓库根目录运行完整回归", text)
        self.assertIn("python -m compileall -q scripts", text)
        self.assertNotIn("python -m py_compile scripts/*.py", text)
        self.assertIn("PYTHONUTF8=1", text)

    def test_timeline_contract_requires_verified_window_quotes(self):
        text = skill_text()

        self.assertIn("金句必须逐字存在于对应校对窗口", text)
        self.assertIn("不得使用统一占位文案", text)
        self.assertIn("无有效语音", text)
        self.assertIn("绝不把正文首句、截断首句或正文同义复写当标题", text)

    def test_default_media_parse_requires_complete_three_artifact_bundle(self):
        text = skill_text()

        self.assertIn("默认三产物合同", text)
        self.assertIn("任何一个产物缺失都不得报整项完成", text)
        self.assertIn("只有用户明确要求“只转写/不要总结”", text)
        self.assertIn("<base>_转写.txt", text)
        self.assertIn("<base>_逐窗口深度解读.md", text)
        self.assertIn("<base>_图文速览.html", text)
        self.assertIn("Agent 开发学习路径", text)

    def test_every_routed_reference_exists(self):
        text = skill_text()
        routed = set(re.findall(r"`(references/[^`*]+(?:\.md)?)`", text))

        self.assertTrue(routed)
        for relative in routed:
            self.assertTrue((SKILL_ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
