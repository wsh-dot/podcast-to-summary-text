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
        for keyword in ("播客", "Bilibili", "transcript", "ASR", "HTML"):
            self.assertIn(keyword, fields["description"])

    def test_verification_commands_are_cross_platform(self):
        text = skill_text()

        self.assertIn("python -m compileall -q scripts", text)
        self.assertNotIn("python -m py_compile scripts/*.py", text)
        self.assertIn("PYTHONUTF8=1", text)

    def test_timeline_contract_requires_verified_window_quotes(self):
        text = skill_text()

        self.assertIn("金句必须逐字存在于对应校对窗口", text)
        self.assertIn("不得使用统一占位文案", text)
        self.assertIn("无有效语音", text)

    def test_every_routed_reference_exists(self):
        text = skill_text()
        routed = set(re.findall(r"`(references/[^`*]+(?:\.md)?)`", text))

        self.assertTrue(routed)
        for relative in routed:
            self.assertTrue((SKILL_ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
