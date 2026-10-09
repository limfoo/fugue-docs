#!/usr/bin/env python3
"""
[INPUT]: 依赖 json, os, subprocess, sys, unittest, test_hooks, geb_codex_hook
[OUTPUT]: 提供 Codex 原生钩子协议、patch 归属、异步命令、Stop 回环与平台隔离的离线回归
[POS]: fugue-docs 评测包-Codex hook 适配验收,复用 Claude 工作区夹具且不调用模型
[PROTOCOL]: 修改 Codex 钩子协议时更新本测试、evals/FOLDER_INDEX.md 与 Codex 接入说明
"""

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

import test_hooks as legacy

sys.path.insert(0, str(legacy.ROOT / "scripts"))
import geb_codex_hook as codex_hook  # noqa: E402

HOOK = legacy.ROOT / "scripts" / "geb_codex_hook.py"
EVENTS = {"session-start": "SessionStart", "prompt": "UserPromptSubmit", "pre-tool": "PreToolUse",
          "post-tool": "PostToolUse", "stop": "Stop", "session-end": "SessionEnd", "interrupt": "Interrupt",
          "subagent-start": "SubagentStart", "subagent-stop": "SubagentStop"}


class CodexHookTests(legacy.HookCase):
    def hook(self, event, session="s1", **extra):
        payload = dict(session_id=session, transcript_path=str(self.transcript), cwd=str(self.root),
                       hook_event_name=EVENTS[event], model="gpt-test", permission_mode="default",
                       turn_id="turn-1")
        payload.update(extra)
        run = subprocess.run([sys.executable, "-B", str(HOOK), event], input=json.dumps(payload),
                             capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual("", run.stderr)
        log = self.data / "hook-errors.log"
        self.assertFalse(log.exists(), log.read_text() if log.exists() else "")
        run.stdout.encode("ascii")
        return json.loads(run.stdout) if run.stdout.strip() else None

    def patch(self, changes, action, session="s1", **extra):
        self.calls += 1
        tool = dict(tool_name="apply_patch", tool_use_id="patch-%d" % self.calls,
                    tool_input={"command": "*** Begin Patch\n" + changes + "\n*** End Patch"})
        tool.update(extra)
        self.hook("pre-tool", session=session, **tool)
        action()
        self.hook("post-tool", session=session, tool_response="Success. Updated the following files.", **tool)

    def edit(self, rel, text, session="s1"):
        verb = "Update" if (self.root / rel).exists() else "Add"
        self.patch("*** %s File: %s\n@@\n+content" % (verb, rel),
                   lambda: self.write(rel, text), session=session)

    def state(self, session="s1"):
        return json.loads((self.data / "sessions" / ("codex-" + session + ".json")).read_text())

    def test_start_injects_native_context_and_namespaces_state(self):
        self.make_project()
        result = self.hook("session-start", source="startup")
        self.assertEqual("SessionStart", result["hookSpecificOutput"]["hookEventName"])
        self.assertIn("PROJECT_INDEX.md", result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual("codex-s1", self.state()["session_id"])
        self.assertFalse((self.data / "sessions" / "s1.json").exists())
        self.env["FUGUE_HOOK_QUIET"] = "1"
        self.assertIsNone(self.hook("session-start", session="s2", source="startup"))

    def test_subagent_start_uses_its_event_name_and_no_invented_zero_baseline(self):
        self.make_project()
        self.transcript.write_text(json.dumps({"type": "session_meta", "payload": {
            "id": "child", "cwd": str(self.root)}}) + "\n")
        result = self.hook("subagent-start", session="child", agent_id="child", agent_type="worker")
        self.assertEqual("SubagentStart", result["hookSpecificOutput"]["hookEventName"])
        self.assertIn("PROJECT_INDEX.md", result["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.state("child")["codex_usage_start"])
        self.assertEqual("child", self.state("child")["fugue_session_id"])

    def test_subagent_stop_maintains_only_child_files_and_suppresses_active_loop(self):
        self.make_project()
        self.hook("session-start", session="parent", source="startup")
        self.hook("subagent-start", session="child", agent_id="child", agent_type="worker")
        self.edit("pkg/parent.py", "def parent():\n    return 1\n", session="parent")
        self.edit("pkg/child.py", "def child():\n    return 1\n", session="child")
        child = dict(session="child", agent_id="child", agent_type="worker", agent_transcript_path=None)
        reason = self.hook("subagent-stop", **child)["reason"]
        self.assertIn("pkg/child.py", reason)
        self.assertNotIn("pkg/parent.py", reason)
        self.assertIn("[INPUT]", self.read("pkg/child.py"))
        self.assertNotIn("[INPUT]", self.read("pkg/parent.py"))
        self.edit("pkg/continued.py", "def continued():\n    return 1\n", session="child")
        continued = self.hook("subagent-stop", stop_hook_active=True, **child)
        self.assertNotIn("decision", continued or {})
        self.assertIn("[INPUT]", self.read("pkg/continued.py"))
        parent_reason = self.hook("stop", session="parent")["reason"]
        self.assertIn("pkg/parent.py", parent_reason)
        self.assertNotIn("pkg/child.py", parent_reason)
        self.assertNotIn("pkg/continued.py", parent_reason)

    def test_subagent_metering_uses_child_rollout_even_when_parent_path_is_supplied(self):
        self.make_project()
        parent, child = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
        parent_log, child_log = self.root.parent / "parent.jsonl", self.root.parent / "child.jsonl"

        def rollout(path, session, total_input, output, timestamp):
            events = [{"type": "session_meta", "payload": {"id": session, "cwd": str(self.root)}},
                      {"type": "turn_context", "payload": {"model": "gpt-test", "effort": "high"}},
                      {"type": "event_msg", "timestamp": timestamp, "payload": {"type": "token_count",
                       "info": {"total_token_usage": {"input_tokens": total_input, "cached_input_tokens": 0,
                                "output_tokens": output, "total_tokens": total_input + output}}}}]
            path.write_text("".join(json.dumps(event) + "\n" for event in events))

        rollout(parent_log, parent, 1000, 100, "2026-10-09T01:00:00Z")
        rollout(child_log, child, 50, 5, "2026-10-09T01:00:00Z")
        self.hook("session-start", session=parent, source="resume", transcript_path=str(parent_log))
        self.hook("subagent-start", session=child, agent_id=child, agent_type="worker", transcript_path=str(child_log))
        rollout(parent_log, parent, 1400, 140, "2026-10-09T01:01:00Z")
        rollout(child_log, child, 150, 15, "2026-10-09T01:01:00Z")
        self.hook("subagent-stop", session=child, agent_id=child, agent_type="worker",
                  transcript_path=str(parent_log), agent_transcript_path=str(child_log))
        self.hook("stop", session=parent, transcript_path=str(parent_log))
        records = {record["session_id"]: record for record in
                   (json.loads(path.read_text()) for path in (self.data / "metrics").glob("*.json"))}
        self.assertEqual({parent, child}, set(records))
        self.assertEqual(110, records[child]["usage"]["total_tokens"])
        self.assertEqual(440, records[parent]["usage"]["total_tokens"])
        self.assertEqual(str(child_log), records[child]["end"]["source"])
        # A missing child path may reuse the previously verified child binding, never the parent path.
        rollout(child_log, child, 160, 16, "2026-10-09T01:02:00Z")
        self.hook("subagent-stop", session=child, agent_id=child, agent_type="worker",
                  transcript_path=str(parent_log), agent_transcript_path=None)
        child_record = next(json.loads(path.read_text()) for path in (self.data / "metrics").glob("*.json")
                            if json.loads(path.read_text())["session_id"] == child)
        self.assertEqual(121, child_record["usage"]["total_tokens"])

    def test_unadopted_project_is_untouched(self):
        self.root.mkdir()
        self.edit("main.py", "print(1)\n")
        self.assertIsNone(self.hook("session-start", source="startup"))
        self.assertIsNone(self.hook("stop"))
        self.assertEqual("print(1)\n", self.read("main.py"))
        self.assertFalse(self.data.exists())

    def test_new_patch_file_gets_header_index_and_one_semantic_prompt(self):
        self.make_project()
        self.hook("session-start", source="startup")
        self.edit("pkg/util.py", "def clamp(x):\n    return x\n")
        first = self.hook("stop")
        self.assertEqual("block", first["decision"])
        self.assertIn("pkg/util.py", first["reason"])
        self.assertIn("[OUTPUT]: 提供 clamp()", self.read("pkg/util.py"))
        self.assertIn("| pkg/util.py | TODO(语义):职责 | clamp() |", self.read("PROJECT_INDEX.md"))
        self.assertIsNone(self.hook("stop", stop_hook_active=True))
        self.assertIsNone(self.hook("stop"))
        self.edit("pkg/util.py", self.read("pkg/util.py").replace("TODO(语义):本文件在系统中的定位与职责", "数值工具"))
        self.write("PROJECT_INDEX.md", self.read("PROJECT_INDEX.md").replace("TODO(语义):职责", "数值工具"))
        self.assertIsNone(self.hook("stop"))
        code, report = self.check_clean()
        self.assertEqual(0, code, report)

    def test_body_change_is_silent_but_export_change_prompts(self):
        self.make_project()
        self.hook("session-start", source="startup")
        self.edit("pkg/core.py", legacy.CORE.replace("return a + b", "return b + a"))
        self.assertIsNone(self.hook("stop"))
        self.assertEqual(legacy.L1, self.read("PROJECT_INDEX.md"))
        self.edit("pkg/core.py", self.read("pkg/core.py") + "\n\ndef sub(a, b):\n    return a - b\n")
        self.assertIn("+sub()", self.hook("stop")["reason"])

    def test_patch_move_records_old_and_new_paths_and_preserves_duty(self):
        self.make_project()
        self.hook("session-start", source="startup")
        self.patch("*** Update File: pkg/core.py\n*** Move to: pkg/calc.py\n@@\n-return a + b\n+return b + a",
                   lambda: (self.root / "pkg/core.py").rename(self.root / "pkg/calc.py"))
        self.edit("app.py", legacy.APP.replace("pkg.core", "pkg.calc"))
        self.hook("stop")
        self.assertIn("| pkg/calc.py | 核心计算 |", self.read("PROJECT_INDEX.md"))
        self.assertNotIn("pkg/core.py", self.read("PROJECT_INDEX.md"))

    def test_multi_file_patch_deletion_and_addition(self):
        self.make_project()
        self.hook("session-start", source="startup")

        def changes():
            (self.root / "pkg/core.py").unlink()
            self.write("pkg/replacement.py", "def replacement():\n    return 1\n")

        self.patch("*** Delete File: pkg/core.py\n*** Add File: pkg/replacement.py\n+def replacement():", changes)
        self.hook("stop")
        self.assertNotIn("pkg/core.py", self.read("PROJECT_INDEX.md"))
        self.assertIn("pkg/replacement.py", self.read("PROJECT_INDEX.md"))

    def test_patch_parser_ignores_body_lookalikes_and_bad_envelopes(self):
        patch = ("*** Begin Patch\n*** Add File: pkg/with space.py\n+*** Delete File: user.py\n"
                 "*** Update File: old.py\n*** Move to: new.py\n*** End Patch")
        expected = ["pkg/with space.py", "old.py", "new.py"]
        for field in ("command", "input", "patch"):
            self.assertEqual(expected, codex_hook.patch_paths({field: patch}))
        self.assertEqual(expected, codex_hook.patch_paths(patch))
        for bad in (None, [], {"command": 5}, "*** Add File: bad.py", "not a patch"):
            self.assertEqual([], codex_hook.patch_paths(bad))

    def test_failed_patch_does_not_claim_preexisting_user_change(self):
        self.make_project()
        self.write("pkg/core.py", legacy.CORE.replace("return a + b", "return b + a"))
        self.hook("session-start", source="startup")
        self.patch("*** Update File: pkg/core.py\n@@\n-impossible", lambda: None)
        self.assertIsNone(self.hook("stop"))
        self.assertEqual(legacy.L1, self.read("PROJECT_INDEX.md"))

    def test_patch_outside_project_and_symlink_are_ignored(self):
        self.make_project()
        outside = self.root.parent / "outside.py"
        outside.write_text("def outside():\n    return 1\n")
        (self.root / "pkg/link.py").symlink_to(outside)
        self.hook("session-start", source="startup")
        self.patch("*** Update File: ../outside.py\n*** Update File: pkg/link.py",
                   lambda: outside.write_text("def changed():\n    return 2\n"))
        self.assertIsNone(self.hook("stop"))
        self.assertNotIn("[INPUT]", outside.read_text())
        self.assertEqual({}, self.state()["authored"])

    def test_user_and_other_session_changes_are_not_claimed(self):
        self.make_project()
        self.hook("session-start", session="a", source="startup")
        self.hook("session-start", session="b", source="startup")
        self.write("pkg/user.py", "def user():\n    return 1\n")
        self.edit("pkg/b.py", "def b():\n    return 1\n", session="b")
        self.edit("pkg/a.py", "def a():\n    return 1\n", session="a")
        reason = self.hook("stop", session="a")["reason"]
        self.assertIn("pkg/a.py", reason)
        self.assertNotIn("pkg/b.py", reason)
        self.assertNotIn("[INPUT]", self.read("pkg/user.py"))
        self.assertNotIn("[INPUT]", self.read("pkg/b.py"))
        self.assertIn("pkg/b.py", self.hook("stop", session="b")["reason"])

    def test_prompt_releases_files_edited_between_turns(self):
        self.make_project()
        self.hook("session-start", source="startup")
        self.edit("pkg/core.py", legacy.CORE.replace("return a + b", "return b + a"))
        self.hook("stop")
        self.write("pkg/core.py", legacy.CORE + "\n\ndef user_added():\n    return 3\n")
        self.hook("prompt", prompt="continue")
        self.assertIsNone(self.hook("stop"))
        self.assertEqual({}, self.state()["authored"])

    def test_native_async_bash_waits_for_original_completion_post(self):
        self.make_project()
        self.hook("session-start", source="startup")
        native = dict(tool_name="Bash", tool_input={"command": "python3 generator.py"}, tool_use_id="exec-1")
        self.hook("pre-tool", **native)
        self.write("pkg/early.py", "def early():\n    return 1\n")
        # Codex exec_command yields; write_stdin does not send another PreToolUse.
        self.write("pkg/late.py", "def late():\n    return 2\n")
        self.hook("post-tool", tool_response="Process exited with code 0", **native)
        reason = self.hook("stop")["reason"]
        self.assertIn("pkg/early.py", reason)
        self.assertIn("pkg/late.py", reason)

    def test_native_failed_command_is_flushed_at_stop(self):
        self.make_project()
        self.hook("session-start", source="startup")
        self.hook("pre-tool", tool_name="Bash", tool_input={"command": "python3 generator.py"}, tool_use_id="failed")
        self.write("pkg/partial.py", "def partial():\n    return 1\n")
        self.assertIn("pkg/partial.py", self.hook("stop")["reason"])

    def test_native_git_workspace_changes_are_excluded(self):
        self.make_project()
        self.hook("session-start", source="startup")
        native = dict(tool_name="Bash", tool_input={"command": "git stash pop"}, tool_use_id="git-1")
        self.hook("pre-tool", **native)
        self.write("pkg/restored.py", "def restored():\n    return 1\n")
        self.hook("post-tool", tool_response="finished", **native)
        self.assertIsNone(self.hook("stop"))
        self.assertNotIn("[INPUT]", self.read("pkg/restored.py"))

    def test_explicit_exec_and_poll_keep_idle_interval_and_original_exclusion(self):
        self.make_project()
        self.hook("session-start", source="startup")
        for process, command, rel in ((42, "python3 gen.py", "pkg/generated.py"),
                                      (43, "git stash pop", "pkg/restored.py")):
            invocation = dict(tool_name="exec_command", tool_input={"cmd": command}, tool_use_id="exec-%s" % process)
            self.hook("pre-tool", **invocation)
            self.hook("post-tool", tool_response={"session_id": process}, **invocation)
            self.write(rel, "def made():\n    return 1\n")
            self.hook("pre-tool", tool_name="write_stdin", tool_input={"session_id": process}, tool_use_id="poll-%s" % process)
            self.hook("post-tool", tool_name="write_stdin", tool_input={"session_id": process},
                      tool_use_id="poll-%s" % process, tool_response={"exit_code": 0})
        reason = self.hook("stop")["reason"]
        self.assertIn("pkg/generated.py", reason)
        self.assertNotIn("pkg/restored.py", reason)
        self.assertNotIn("[INPUT]", self.read("pkg/restored.py"))

    def test_explicit_running_poll_and_stop_preserve_git_exclusion(self):
        self.make_project()
        self.hook("session-start", source="startup")
        native = dict(tool_name="exec_command", tool_input={"cmd": "git stash pop"}, tool_use_id="long-git")
        self.hook("pre-tool", **native)
        self.hook("post-tool", tool_response={"session_id": 1}, **native)
        self.write("pkg/restored.py", "def restored():\n    return 1\n")
        self.hook("post-tool", tool_name="write_stdin", tool_input={"session_id": 1},
                  tool_use_id="poll-1", tool_response={"session_id": 1})
        self.assertIsNone(self.hook("stop"))
        self.write("pkg/later.py", "def later():\n    return 1\n")
        self.hook("post-tool", tool_name="write_stdin", tool_input={"session_id": 1},
                  tool_use_id="poll-2", tool_response={"exit_code": 0})
        self.assertIsNone(self.hook("stop"))
        self.assertNotIn("[INPUT]", self.read("pkg/later.py"))

    def test_unknown_process_and_readonly_tools_do_not_capture_user_files(self):
        self.make_project()
        self.hook("session-start", source="startup")
        for name, tool_input in (("write_stdin", {"session_id": 9}), ("read_file", {"path": "pkg/user.py"})):
            self.hook("pre-tool", tool_name=name, tool_input=tool_input, tool_use_id=name)
            self.write("pkg/user.py", "def user():\n    return 1\n")
            self.hook("post-tool", tool_name=name, tool_input=tool_input, tool_use_id=name, tool_response={"exit_code": 0})
        self.assertIsNone(self.hook("stop"))
        self.assertNotIn("[INPUT]", self.read("pkg/user.py"))

    def test_default_data_location_uses_codex_home_and_ignores_claude_project(self):
        self.make_project()
        codex_home = self.root.parent / "codex-home"
        original_get = os.environ.get

        def configured_value(name, default=None):
            if name == "FUGUE_HOOK_AGENT":
                return "codex"
            if name == "FUGUE_DATA_DIR":
                return None
            if name == "CODEX_HOME":
                return str(codex_home)
            return original_get(name, default)

        with mock.patch.object(os.environ, "get", side_effect=configured_value):
            self.assertEqual(str(codex_home / "fugue"), codex_hook.engine.data_dir())
        self.env["CLAUDE_PROJECT_DIR"] = str(self.root.parent / "unrelated")
        self.hook("session-start", source="startup")
        self.assertEqual(str(self.root), self.state()["root"])

    def test_interrupt_and_session_end_never_maintain_or_block(self):
        self.make_project()
        self.hook("session-start", source="startup")
        self.edit("pkg/unfinished.py", "def unfinished():\n    return 1\n")
        self.assertIsNone(self.hook("interrupt", reason="user_interrupt"))
        self.assertIsNone(self.hook("session-end", reason="other"))
        self.assertNotIn("[INPUT]", self.read("pkg/unfinished.py"))
        self.assertEqual(legacy.L1, self.read("PROJECT_INDEX.md"))

    def test_codex_metering_never_creates_claude_records(self):
        self.make_project()
        self.hook("session-start", source="startup")
        self.hook("stop")
        records = [json.loads(path.read_text()) for path in (self.data / "metrics").glob("*.json")]
        self.assertEqual(1, len(records))
        self.assertEqual("codex", records[0]["agent"])
        self.assertNotEqual("claude_transcript", records[0]["source"])
        self.assertIsNone(records[0]["usage"])

    def test_non_git_project_patch_maintenance(self):
        self.make_project(git=False)
        self.hook("session-start", source="startup")
        self.edit("pkg/new.py", "def added():\n    return 1\n")
        self.assertIn("pkg/new.py", self.hook("stop")["reason"])

    def test_bad_payload_is_fail_open(self):
        for payload in ("not json", "[]", "null", '{}', '{"session_id":false}'):
            run = subprocess.run([sys.executable, "-B", str(HOOK), "stop"], input=payload,
                                 capture_output=True, text=True, env=self.env)
            self.assertEqual(0, run.returncode)
            self.assertEqual("", run.stdout)
        run = subprocess.run([sys.executable, "-B", str(HOOK), "unknown"], input="{}",
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(0, run.returncode)
        self.assertEqual("", run.stdout)


if __name__ == "__main__":
    unittest.main()
