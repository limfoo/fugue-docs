#!/usr/bin/env python3
"""
[INPUT]: 依赖 pathlib, subprocess, sys, tempfile, unittest
[OUTPUT]: 提供 Devin AGENTS.md 规则注入、英文精简与 Codex/Devin 合并适配回归
[POS]: fugue-docs 评测包-Devin 规则适配器验收
[PROTOCOL]: 修改 Devin 适配器时同步本测试、evals/FOLDER_INDEX.md 与 adapters/DEVIN*.md
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
ADAPT = ROOT / "scripts" / "geb_adapt.py"


class DevinAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fugue-devin-adapt-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()

    def adapt(self, *args):
        return subprocess.run([sys.executable, "-B", str(ADAPT), str(self.root), *args],
                              capture_output=True, text=True)

    def test_devin_uses_agents_without_override_and_injects_short_guidance(self):
        (self.root / "AGENTS.override.md").write_text("# Keep untouched\n", encoding="utf-8")
        result = self.adapt("--tool", "devin")
        self.assertEqual(0, result.returncode, result.stderr)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Devin 执行约定", agents)
        self.assertIn(".devin/skills/fugue-docs/scripts/", agents)
        self.assertEqual("# Keep untouched\n", (self.root / "AGENTS.override.md").read_text())

    def test_codex_and_devin_share_one_combined_block_and_compact_is_respected(self):
        result = self.adapt("--tool", "codex", "devin", "--lang", "en", "--compact")
        self.assertEqual(0, result.returncode, result.stderr)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(1, agents.count("<!-- GEB-PROTOCOL BEGIN"))
        self.assertEqual(1, agents.count("<!-- GEB-PROTOCOL END"))
        self.assertIn("## Codex workflow", agents)
        self.assertIn("## Devin execution conventions", agents)
        self.assertIn("# GEB Documentation Protocol (compact)", agents)
        self.assertEqual(1, agents.count("## Codex workflow"))
        self.assertEqual(1, agents.count("## Devin execution conventions"))


if __name__ == "__main__":
    unittest.main()
