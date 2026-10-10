#!/usr/bin/env python3
"""
[INPUT]: 依赖 json, os, pathlib, subprocess, sys, tempfile, unittest
[OUTPUT]: 提供 Devin 技能部署、用户/项目 hooks 合并、幂等、预演与 malformed JSON 离线回归
[POS]: fugue-docs 评测包-Devin 安装器与配置写入边界验收
[PROTOCOL]: 修改安装器或受管 hooks 合并时同步本测试、evals/FOLDER_INDEX.md 与 references/devin.md
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts" / "geb_install_devin.py"


class DevinInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fugue-devin-install-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home with spaces"
        self.project = self.base / "project with spaces"
        self.project.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")

    def run_installer(self, *args):
        return subprocess.run([sys.executable, "-B", str(INSTALLER), *map(str, args)],
                              cwd=self.base, env=self.env, capture_output=True, text=True, timeout=30)

    def succeed(self, *args):
        result = self.run_installer(*args)
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    @staticmethod
    def snapshot(path):
        return {item.relative_to(path).as_posix(): item.read_bytes()
                for item in path.rglob("*") if item.is_file()}

    def test_project_install_hooks_merge_and_rerun_are_idempotent(self):
        hooks_path = self.project / ".devin" / "hooks.v1.json"
        hooks_path.parent.mkdir()
        foreign = {"type": "command", "command": "echo foreign", "timeout": 3}
        hooks_path.write_text(json.dumps({
            "SessionStart": [{"matcher": "", "hooks": [foreign]}],
            "ForeignEvent": [{"matcher": "keep", "hooks": [{"type": "prompt", "prompt": "keep"}]}],
            "metadata": "preserve",
        }), encoding="utf-8")
        self.succeed("--project", self.project, "--hooks")
        destination = self.project / ".agents" / "skills" / "fugue-docs"
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertTrue((destination / "scripts" / "geb_devin_hook.py").is_file())
        self.assertTrue((destination / "scripts" / "geb_codex_hook.py").is_file())
        installed = json.loads(hooks_path.read_text())
        self.assertEqual("preserve", installed["metadata"])
        self.assertEqual(foreign, installed["SessionStart"][0]["hooks"][0])
        self.assertEqual("keep", installed["ForeignEvent"][0]["matcher"])
        all_commands = [hook["command"] for groups in installed.values() if isinstance(groups, list)
                        for group in groups for hook in group.get("hooks", []) if "command" in hook]
        project_command = next(command for command in all_commands if "geb_devin_hook.py" in command)
        self.assertIn('$DEVIN_PROJECT_DIR/.agents/skills/fugue-docs/scripts/geb_devin_hook.py', project_command)
        self.assertNotIn(str(self.base), project_command)
        self.assertIn("^exec$", next(group["matcher"] for group in installed["PostToolUse"]))
        managed_count = sum("geb_devin_hook.py" in command for command in all_commands)
        self.assertEqual(6, managed_count)
        before = self.snapshot(self.project)
        self.succeed("--project", self.project, "--hooks")
        self.assertEqual(before, self.snapshot(self.project))

    def test_user_install_uses_global_skills_and_preserves_config(self):
        config = self.home / ".config" / "devin" / "config.json"
        config.parent.mkdir(parents=True)
        foreign = [{"matcher": "foreign", "hooks": [{"type": "command", "command": "echo user"}]}]
        config.write_text(json.dumps({"theme": "dark", "hooks": {"UserPromptSubmit": foreign}}), encoding="utf-8")
        self.succeed("--user", "--hooks")
        destination = self.home / ".config" / "devin" / "skills" / "fugue-docs"
        self.assertTrue((destination / "SKILL.md").is_file())
        saved = json.loads(config.read_text())
        self.assertEqual("dark", saved["theme"])
        self.assertEqual(foreign, saved["hooks"]["UserPromptSubmit"][:1])
        commands = [hook["command"] for groups in saved["hooks"].values()
                    for group in groups for hook in group["hooks"] if "command" in hook]
        user_command = next(command for command in commands if "geb_devin_hook.py" in command)
        self.assertIn(str(destination / "scripts" / "geb_devin_hook.py"), user_command)
        self.assertIn("'", user_command)

    def test_dry_run_writes_nothing_for_project_and_user(self):
        before = self.snapshot(self.base)
        self.succeed("--project", self.project, "--hooks", "--dry-run")
        self.succeed("--user", "--hooks", "--dry-run")
        self.assertEqual(before, self.snapshot(self.base))
        self.assertFalse((self.project / ".agents").exists())
        self.assertFalse(self.home.exists())

    def test_malformed_project_or_user_json_is_refused_before_skill_write(self):
        project_hooks = self.project / ".devin" / "hooks.v1.json"
        project_hooks.parent.mkdir()
        project_hooks.write_text("{broken", encoding="utf-8")
        result = self.run_installer("--project", self.project, "--hooks")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Invalid Devin hooks JSON", result.stderr)
        self.assertFalse((self.project / ".agents").exists())
        project_hooks.unlink()
        user_config = self.home / ".config" / "devin" / "config.json"
        user_config.parent.mkdir(parents=True)
        user_config.write_text("{broken", encoding="utf-8")
        result = self.run_installer("--user", "--hooks")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Invalid Devin hooks JSON", result.stderr)
        self.assertFalse((self.home / ".config" / "devin" / "skills").exists())


if __name__ == "__main__":
    unittest.main()
