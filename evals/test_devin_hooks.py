#!/usr/bin/env python3
"""
[INPUT]: 依赖 io, json, os, pathlib, subprocess, sys, unittest, uuid, test_hooks, geb_devin_hook
[OUTPUT]: 提供 Devin payload 归一化、工具归属、Stop 回环、遥测未知与异常放行回归
[POS]: fugue-docs 评测包-Devin 原生 hook 离线协议验收
[PROTOCOL]: 修改 Devin hook 行为时同步本测试、evals/FOLDER_INDEX.md 与 references/devin.md
"""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import uuid

import test_hooks as legacy

sys.path.insert(0, str(legacy.ROOT / "scripts"))
import geb_devin_hook as devin_hook  # noqa: E402

HOOK = legacy.ROOT / "scripts" / "geb_devin_hook.py"
EVENTS = {"session-start": "SessionStart", "prompt": "UserPromptSubmit", "pre-tool": "PreToolUse",
          "post-tool": "PostToolUse", "stop": "Stop", "session-end": "SessionEnd"}


class DevinHookTests(legacy.HookCase):
    def hook(self, event, session="s1", **extra):
        payload = dict(session_id=session, cwd=str(self.root), hook_event_name=EVENTS[event],
                       prompt_id="prompt-1")
        payload.update(extra)
        env = dict(self.env, DEVIN_PROJECT_DIR=str(self.root))
        run = subprocess.run([sys.executable, "-B", str(HOOK), event], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual("", run.stderr)
        log = self.data / "hook-errors.log"
        self.assertFalse(log.exists(), log.read_text() if log.exists() else "")
        run.stdout.encode("ascii")
        return json.loads(run.stdout) if run.stdout.strip() else None

    def state(self, session="s1"):
        return json.loads((self.data / "sessions" / ("devin-" + session + ".json")).read_text())

    def test_payload_requires_session_and_namespaces_state(self):
        self.assertIsNone(devin_hook.normalize_payload({"session_id": "  "}))
        normalized = devin_hook.normalize_payload({"session_id": "session-a"})
        self.assertEqual("devin", normalized["fugue_agent"])
        self.assertEqual("session-a", normalized["fugue_session_id"])
        self.assertEqual("devin-session-a", normalized["session_id"])

    def test_edit_write_and_notebook_field_variants_are_attributed(self):
        self.make_project()
        self.hook("session-start")
        fields = ("file_path", "path", "target_file", "notebook_path", "file")
        for tool in ("edit", "write", "notebook_edit"):
            expected = []
            for field in fields:
                rel = "pkg/%s_%s.py" % (tool, field)
                self.hook("pre-tool", tool_name=tool, tool_input={field: str(self.root / rel)})
                self.write(rel, "def value():\n    return 1\n")
                expected.append("%s_%s.py" % (tool, field))
            result = self.hook("stop")
            self.assertEqual("block", result["decision"])
            for name in expected:
                self.assertIn(name, result["reason"])
        self.assertEqual("devin-s1", self.state()["session_id"])
        self.assertEqual("s1", self.state()["fugue_session_id"])

    def test_apply_patch_and_exec_pre_post_attribute_changes(self):
        self.make_project()
        self.hook("session-start")
        patch = "*** Begin Patch\n*** Add File: pkg/patched.py\n+def patched():\n+    return 1\n*** End Patch"
        self.hook("pre-tool", tool_name="apply_patch", tool_input={"patch": patch})
        self.write("pkg/patched.py", "def patched():\n    return 1\n")
        self.hook("pre-tool", tool_name="exec", tool_input={"command": ["python3", "make.py"]})
        self.write("pkg/executed.py", "def executed():\n    return 1\n")
        self.hook("post-tool", tool_name="exec", tool_input={"command": ["python3", "make.py"]},
                  tool_response={"success": True, "output": "done", "error": None})
        result = self.hook("stop")
        self.assertEqual("block", result["decision"])
        self.assertIn("pkg/patched.py", result["reason"])
        self.assertIn("pkg/executed.py", result["reason"])

    def test_stop_blocks_semantic_gap_and_suppresses_active_loop(self):
        self.make_project()
        self.hook("session-start")
        self.hook("pre-tool", tool_name="write", tool_input={"file_path": str(self.root / "pkg" / "new.py")})
        self.write("pkg/new.py", "def new():\n    return 1\n")
        result = self.hook("stop")
        self.assertEqual("block", result["decision"])
        self.assertIn("pkg/new.py", result["reason"])
        self.hook("pre-tool", tool_name="write", tool_input={"file_path": str(self.root / "pkg" / "continued.py")})
        self.write("pkg/continued.py", "def continued():\n    return 2\n")
        continued = self.hook("stop", stop_hook_active=True)
        self.assertNotIn("decision", continued or {})
        self.assertIn("[INPUT]", self.read("pkg/continued.py"))

    def test_unadopted_project_is_silent_and_creates_no_files(self):
        bare = self.root / "unadopted"
        bare.mkdir(parents=True)
        env = dict(self.env, DEVIN_PROJECT_DIR=str(bare))
        run = subprocess.run([sys.executable, "-B", str(HOOK), "session-start"],
                             input=json.dumps({"session_id": "bare", "cwd": str(self.root)}),
                             capture_output=True, text=True, env=env, timeout=20)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual("", run.stdout)
        self.assertFalse(self.data.exists())

    def test_devin_project_dir_overrides_payload_cwd(self):
        self.make_project()
        payload = {"session_id": "root-check", "cwd": str(self.root.parent)}
        normalized = devin_hook.normalize_payload(payload)
        with mock.patch.dict(os.environ, {"DEVIN_PROJECT_DIR": str(self.root), "FUGUE_HOOK_AGENT": "devin"}):
            self.assertEqual(str(self.root), devin_hook.engine.project_root(normalized))
        self.hook("session-start", session="root-check", cwd=str(self.root.parent))
        self.assertEqual(str(self.root), self.state("root-check")["root"])

    def test_ledger_records_unknown_usage_and_devins_data_directory(self):
        self.make_project()
        self.hook("session-start")
        self.hook("stop")
        records = list((self.data / "metrics").glob("*.json"))
        expected = str(uuid.uuid5(uuid.NAMESPACE_URL, "fugue-devin-session:s1"))
        self.assertEqual([expected + ".json"], [path.name for path in records])
        record = json.loads(records[0].read_text())
        self.assertEqual("devin", record["agent"])
        self.assertEqual("devin-session", record["task"])
        self.assertIsNone(record["usage"])
        self.assertEqual("telemetry_unavailable", record["status"])
        self.assertIsNone(record["source"])
        self.assertEqual("no_comparable_baseline", record["saving_status"])

    def test_malformed_stdin_and_handler_exception_exit_zero(self):
        malformed = subprocess.run([sys.executable, "-B", str(HOOK), "stop"], input="{",
                                   capture_output=True, text=True, env=dict(self.env, DEVIN_PROJECT_DIR=str(self.root)))
        self.assertEqual(0, malformed.returncode)
        with mock.patch.object(devin_hook, "HANDLERS", {"stop": lambda _payload: 1 / 0}), \
                mock.patch.object(devin_hook.sys, "stdin", io.StringIO('{"session_id":"boom"}')), \
                mock.patch.object(devin_hook.engine, "log_error") as log_error:
            self.assertEqual(0, devin_hook.main(["stop"]))
        log_error.assert_called_once()
        self.assertEqual("devin:stop", log_error.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
