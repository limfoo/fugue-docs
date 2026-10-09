#!/usr/bin/env python3
"""
[INPUT]: 依赖 pathlib, subprocess, sys, tempfile, unittest
[OUTPUT]: 提供 Codex 规则适配回归:覆盖优先级、规则保留、预演、工具独立运行与路径保护
[POS]: fugue-docs 评测包-Codex AGENTS 适配与可移植工具验收
[PROTOCOL]: 修改测试时同步 evals/FOLDER_INDEX.md 并运行 unittest discovery
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
ADAPT = ROOT / "scripts" / "geb_adapt.py"


class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fugue-codex-adapt-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "用户 project"
        self.root.mkdir()

    def adapt(self, *args, root=None, expect=0):
        result = subprocess.run(
            [sys.executable, "-B", str(ADAPT), str(root or self.root), *args],
            capture_output=True, text=True)
        self.assertEqual(expect, result.returncode, result.stdout + result.stderr)
        return result

    def test_existing_rules_and_crlf_survive_repeat_and_language_update(self):
        target = self.root / "AGENTS.md"
        target.write_bytes(b"# Team rules\r\n\r\nKeep our tests.\r\n")
        self.adapt("--tool", "codex", "--compact")
        first = target.read_bytes()
        self.assertTrue(first.startswith(b"# Team rules\r\n\r\nKeep our tests.\r\n"))
        self.assertNotIn(b"\n", first.replace(b"\r\n", b""))
        self.adapt("--tool", "codex", "--compact")
        self.assertEqual(first, target.read_bytes())
        self.adapt("--tool", "codex", "--lang", "en")
        updated = target.read_text()
        self.assertIn("Keep our tests.", updated)
        self.assertIn("## Codex workflow", updated)
        self.assertNotIn("## Codex 执行约定", updated)
        self.assertEqual(1, updated.count("<!-- GEB-PROTOCOL BEGIN"))

    def test_override_gets_effective_rules_and_base_is_untouched(self):
        base = self.root / "AGENTS.md"
        override = self.root / "AGENTS.override.md"
        nested = self.root / "src" / "AGENTS.md"
        base.write_text("# Base instructions\n", encoding="utf-8")
        override.write_text("# Local override\n", encoding="utf-8")
        nested.parent.mkdir()
        nested.write_text("# Module instructions\n", encoding="utf-8")
        result = self.adapt("--tool", "codex")
        self.assertIn("AGENTS.override.md", result.stdout)
        self.assertIn("# Local override", override.read_text())
        self.assertIn("## Codex 执行约定", override.read_text())
        self.assertEqual("# Base instructions\n", base.read_text())
        self.assertEqual("# Module instructions\n", nested.read_text())

    def test_empty_or_whitespace_override_still_shadows_base_instructions(self):
        base = self.root / "AGENTS.md"
        base.write_text("# Base rules\n", encoding="utf-8")
        override = self.root / "AGENTS.override.md"
        for content in ("", " \n\n"):
            with self.subTest(content=content):
                override.write_text(content, encoding="utf-8")
                self.adapt("--tool", "codex")
                self.assertIn("## Codex 执行约定", override.read_text())
                self.assertEqual("# Base rules\n", base.read_text())

    def test_dry_run_reports_override_without_writing_tools_or_rules(self):
        override = self.root / "AGENTS.override.md"
        override.write_text("# Preserve me\n", encoding="utf-8")
        result = self.adapt("--tool", "codex", "--copy-tools", "--dry-run")
        self.assertIn("AGENTS.override.md", result.stdout)
        self.assertEqual("# Preserve me\n", override.read_text())
        self.assertEqual([override], list(self.root.iterdir()))

    def test_codex_addendum_does_not_leak_into_other_adapters(self):
        self.adapt("--tool", "codex", "cursor", "--lang", "en", "--compact")
        self.assertIn("## Codex workflow", (self.root / "AGENTS.md").read_text())
        self.assertNotIn("## Codex workflow", (self.root / ".cursorrules").read_text())

    def test_copied_tools_run_from_an_unrelated_working_directory(self):
        self.adapt("--tool", "codex", "--copy-tools")
        source = self.root / "app.py"
        source.write_text("import json\n\ndef main():\n    return json.dumps({})\n", encoding="utf-8")
        tool_dir = self.root / "scripts" / "geb"
        for tool, options in (("geb_arch.py", []), ("geb_scaffold.py", ["--dry-run"]),
                              ("geb_sync.py", ["--changed", "--dry-run"]),
                              ("geb_check.py", ["--if-adopted"])):
            with self.subTest(tool=tool):
                result = subprocess.run(
                    [sys.executable, "-B", str(tool_dir / tool), str(self.root), *options],
                    cwd=self.temp.name, capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((self.root / "PROJECT_INDEX.md").exists())
        self.assertEqual("import json\n\ndef main():\n    return json.dumps({})\n", source.read_text())

    def test_symlinked_rule_is_not_overwritten(self):
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        (self.root / "AGENTS.md").symlink_to(outside)
        self.adapt("--tool", "codex", expect=2)
        self.assertEqual("# Outside\n", outside.read_text())

    def test_project_can_be_reached_through_a_symlink(self):
        alias = Path(self.temp.name) / "linked-project"
        alias.symlink_to(self.root, target_is_directory=True)
        self.adapt("--tool", "codex", root=alias)
        self.assertIn("## Codex 执行约定", (self.root / "AGENTS.md").read_text())


if __name__ == "__main__":
    unittest.main()
