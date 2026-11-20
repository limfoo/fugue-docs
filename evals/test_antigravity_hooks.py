#!/usr/bin/env python3
"""
[INPUT]: 依赖 json, os, shutil, subprocess, sys, tempfile, unittest
[OUTPUT]: 验证 Antigravity 原生 hook 协议翻译、跨平台插件安装器与 GEMINI.md 规则适配
[POS]: fugue-docs 评测包-Antigravity 原生适配回归测试
[PROTOCOL]: 变更时同步 evals/FOLDER_INDEX.md 与 references/antigravity.md
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOOK = os.path.join(ROOT, "scripts", "geb_antigravity_hook.py")
INSTALLER = os.path.join(ROOT, "scripts", "geb_install_antigravity.py")
ADAPT = os.path.join(ROOT, "scripts", "geb_adapt.py")
GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Test",
    GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="Test",
    GIT_COMMITTER_EMAIL="test@example.com",
)


class AntigravityHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fugue-agy-test-")
        self.project = os.path.join(self.tmp, "proj")
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.project)
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True, env=GIT_ENV)
        with open(os.path.join(self.project, "PROJECT_INDEX.md"), "w", encoding="utf-8") as f:
            f.write(
                "# demo — 项目索引(L1)\n\n## 定位\n测试项目\n\n## 文件清单\n"
                "| 文件 | 职责 | 关键导出 |\n|------|------|----------|\n"
            )
        subprocess.run(["git", "add", "."], cwd=self.project, check=True, env=GIT_ENV)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.project, check=True, env=GIT_ENV)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, event, payload):
        env = dict(os.environ, FUGUE_DATA_DIR=self.data_dir)
        res = subprocess.run(
            [sys.executable, HOOK, event],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            env=env,
            timeout=30,
            check=True,
        )
        return json.loads(res.stdout.decode("utf-8"))

    def test_lifecycle_sync_and_continue_contract(self):
        conv_id = "conv-agy-001"
        start = self.run_hook(
            "session-start",
            {"conversationId": conv_id, "cwd": self.project, "workspacePaths": [self.project]},
        )
        hint = start["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("PROJECT_INDEX.md", hint)

        pre = self.run_hook("pre-invocation", {"conversationId": conv_id, "cwd": self.project, "invocationNum": 1})
        self.assertEqual(pre, {})

        app_py = os.path.join(self.project, "app.py")
        with open(app_py, "w", encoding="utf-8") as f:
            f.write("import json\n\ndef greet(name):\n    return json.dumps({'name': name})\n")

        post = self.run_hook(
            "post-tool",
            {
                "conversationId": conv_id,
                "cwd": self.project,
                "toolCall": {"id": "tc-1", "name": "write_file", "args": {"Path": app_py}},
            },
        )
        self.assertEqual(post, {})

        stop = self.run_hook(
            "stop",
            {
                "conversationId": conv_id,
                "cwd": self.project,
                "terminationReason": "NO_TOOL_CALL",
                "continuationActive": False,
            },
        )
        self.assertEqual(stop.get("decision"), "continue")
        self.assertIn("app.py", stop.get("reason", ""))
        with open(app_py, encoding="utf-8") as f:
            self.assertIn("[INPUT]", f.read())
        with open(os.path.join(self.project, "PROJECT_INDEX.md"), encoding="utf-8") as f:
            self.assertIn("app.py", f.read())

        cancel = self.run_hook(
            "stop",
            {
                "conversationId": conv_id,
                "cwd": self.project,
                "terminationReason": "USER_CANCELED",
                "continuationActive": False,
            },
        )
        self.assertEqual(cancel, {})

        metrics_files = os.listdir(os.path.join(self.data_dir, "metrics"))
        self.assertEqual(len(metrics_files), 1)
        with open(os.path.join(self.data_dir, "metrics", metrics_files[0]), encoding="utf-8") as f:
            metric = json.load(f)
        self.assertEqual(metric["agent"], "antigravity")
        self.assertEqual(metric["status"], "telemetry_unavailable")
        self.assertIsNone(metric["usage"])

    def test_unadopted_project_stays_silent(self):
        other = os.path.join(self.tmp, "plain")
        os.makedirs(other)
        out = self.run_hook("session-start", {"conversationId": "conv-plain", "cwd": other})
        self.assertEqual(out, {})

    def test_installer_and_adapt(self):
        target = os.path.join(self.tmp, "workspace")
        os.makedirs(target)
        res = subprocess.run(
            [sys.executable, INSTALLER, "--project", target, "--dry-run"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("dry-run: install:", res.stdout)
        self.assertFalse(os.path.exists(os.path.join(target, ".agents", "plugins", "fugue-docs-agy")))

        subprocess.run([sys.executable, INSTALLER, "--project", target], capture_output=True, text=True, check=True)
        plugin_dir = os.path.join(target, ".agents", "plugins", "fugue-docs-agy")
        self.assertTrue(os.path.isfile(os.path.join(plugin_dir, "plugin.json")))
        self.assertTrue(os.path.isfile(os.path.join(plugin_dir, "hooks.json")))
        self.assertTrue(os.path.isfile(os.path.join(plugin_dir, "skills", "fugue-docs", "SKILL.md")))
        with open(os.path.join(plugin_dir, "hooks.json"), encoding="utf-8") as f:
            hooks_data = json.load(f)
        cmd = hooks_data["fugue-docs-agy"]["Stop"][0]["command"]
        self.assertIn("python3", cmd)
        self.assertIn("python ", cmd)

        adapt_res = subprocess.run(
            [sys.executable, ADAPT, target, "--tool", "antigravity", "--dry-run"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("GEMINI.md", adapt_res.stdout)


if __name__ == "__main__":
    unittest.main()
