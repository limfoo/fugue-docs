#!/usr/bin/env python3
"""
[INPUT]: 依赖 hashlib, json, os, pathlib, runpy, shlex, shutil, subprocess, sys, tempfile, unittest, unittest.mock
[OUTPUT]: Codex 原生 skill 安装回归:位置、预览、复制完整性、重复安装、安全更新、冲突与安装副本执行
[POS]: fugue-docs 评测层-Codex standalone skill 分发契约
[PROTOCOL]: 变更时更新此头部,然后检查上级 FOLDER_INDEX.md 与 geb_install_codex.py 的安装契约
"""

import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ".fugue-codex-install.json"
PAYLOAD = ("SKILL.md", "scripts", "references", "adapters", "agents", "LICENSE")
RUN_INSTALLER = """import os, runpy, sys
from pathlib import Path
from unittest.mock import patch
script, fake_home, fake_codex_home = sys.argv[1:4]
sys.argv = [script, *sys.argv[4:]]
sys.path.insert(0, str(Path(script).parent))
original_get = os.environ.get
def isolated_get(key, default=None):
    return (fake_codex_home or None) if key == "CODEX_HOME" else original_get(key, default)
with patch("pathlib.Path.home", return_value=Path(fake_home)), patch.object(os.environ, "get", side_effect=isolated_get):
    runpy.run_path(script, run_name="__main__")
"""


class CodexInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="fugue-codex-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.source = self.directory / "source 技能"
        self.source.mkdir()
        for name in PAYLOAD:
            path = ROOT / name
            if path.is_dir():
                shutil.copytree(path, self.source / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(path, self.source / name)
        self.script = self.source / "scripts" / "geb_install_codex.py"
        self.destination = self.directory / "custom 目录" / "fugue-docs"
        self.home = self.directory / "fake home"
        self.environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def run_installer(self, *args, script=None, codex_directory=""):
        return subprocess.run([sys.executable, "-c", RUN_INSTALLER, str(script or self.script),
                               str(self.home), str(codex_directory), *map(str, args)],
                              cwd=self.directory, env=self.environment,
                              capture_output=True, text=True, timeout=20)

    def succeed(self, *args, script=None, codex_directory=""):
        result = self.run_installer(*args, script=script, codex_directory=codex_directory)
        self.assertEqual(0, result.returncode, result.stderr)
        return result

    def snapshot(self, path):
        return {item.relative_to(path).as_posix(): item.read_bytes()
                for item in path.rglob("*") if item.is_file()}

    def first_install(self):
        self.succeed("--dest", self.destination)

    def installer_namespace(self):
        with patch.object(sys, "path", [str(self.script.parent), *sys.path]):
            return runpy.run_path(str(self.script))

    def test_requires_exactly_one_explicit_target(self):
        for arguments in ((), ("--user", "--project", str(self.directory)),
                          ("--user", "--dest", str(self.destination))):
            with self.subTest(arguments=arguments):
                result = self.run_installer(*arguments)
                self.assertEqual(2, result.returncode, result.stderr)
        self.assertFalse(self.home.exists())
        self.assertFalse(self.destination.exists())

    def test_dry_run_does_not_create_any_destination_ancestors(self):
        before = self.snapshot(self.directory)
        for arguments in (("--dest", self.destination), ("--user",),
                          ("--project", self.directory / "absent project")):
            with self.subTest(arguments=arguments):
                result = self.succeed(*arguments, "--dry-run")
                self.assertIn("dry-run: install:", result.stdout)
        self.assertEqual(before, self.snapshot(self.directory))
        self.assertFalse(self.destination.parent.exists())
        self.assertFalse(self.home.exists())
        self.assertFalse((self.directory / "absent project").exists())

    def test_project_target_with_spaces_and_unicode(self):
        project = self.directory / "项目 with spaces"
        self.succeed("--project", project)
        destination = project / ".agents" / "skills" / "fugue-docs"
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertTrue((destination / "agents" / "openai.yaml").is_file())
        self.assertFalse(self.home.exists())

    def test_user_target_uses_isolated_home(self):
        self.succeed("--user")
        self.assertTrue((self.home / ".agents" / "skills" / "fugue-docs" / "SKILL.md").is_file())

    def test_project_under_system_tmp_alias(self):
        # Keep /tmp unresolved: on macOS it points to /private/tmp.
        with tempfile.TemporaryDirectory(prefix="fugue-codex-alias-", dir="/tmp") as directory:
            project = Path(directory) / "project"
            self.succeed("--project", project)
            self.assertTrue((project / ".agents" / "skills" / "fugue-docs" / "SKILL.md").is_file())

    def test_only_exact_macos_system_aliases_are_normalized(self):
        absolute_path = self.installer_namespace()["absolute_path"]
        for alias, canonical in (("/tmp", "/private/tmp"), ("/var", "/private/var")):
            for target in (canonical, canonical.lstrip("/")):
                with self.subTest(alias=alias, target=target):
                    with patch.object(sys, "platform", "darwin"), \
                            patch.object(Path, "is_symlink", return_value=True), \
                            patch("os.readlink", return_value=target):
                        self.assertEqual(Path(canonical) / "project", absolute_path(alias + "/project"))
        with patch.object(sys, "platform", "darwin"), \
                patch.object(Path, "is_symlink", return_value=True), \
                patch("os.readlink", return_value="/unexpected-location"):
            self.assertEqual(Path("/tmp/project"), absolute_path("/tmp/project"))
        with patch.object(sys, "platform", "linux"), \
                patch.object(Path, "is_symlink", return_value=True), \
                patch("os.readlink", return_value="/private/tmp"):
            self.assertEqual(Path("/tmp/project"), absolute_path("/tmp/project"))

    def test_custom_target_is_exact_and_payload_is_complete(self):
        self.first_install()
        installed = self.snapshot(self.destination)
        source = self.snapshot(self.source)
        self.assertEqual(source, {name: data for name, data in installed.items() if name != MANIFEST})
        manifest = json.loads(installed[MANIFEST])
        self.assertEqual({name: hashlib.sha256(data).hexdigest() for name, data in source.items()},
                         manifest["files"])
        self.assertEqual(1, manifest["format"])
        self.assertFalse((self.destination / "fugue-docs").exists())

    def test_excludes_caches_plugin_metadata_and_evaluations(self):
        for name in (".git/config", ".claude-plugin/plugin.json", "hooks/hooks.json", "evals/test_fake.py",
                     "assets/logo.svg", "README.md", "scripts/__pycache__/ignored.py",
                     "scripts/ignored.pyc", "scripts/.git/config", "scripts/hooks/hooks.json"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not part of the Codex skill\n", encoding="utf-8")
        self.first_install()
        installed = self.snapshot(self.destination)
        self.assertNotIn("README.md", installed)
        self.assertFalse(any(part in {"__pycache__", ".git", ".claude-plugin", "hooks", "evals", "assets"}
                             for name in installed for part in Path(name).parts))
        self.assertFalse(any(name.endswith(".pyc") for name in installed))

    def test_repeat_is_noop_and_preserves_unrelated_files(self):
        self.first_install()
        extra = self.destination / "my-notes.txt"
        extra.write_text("keep me\n")
        before = self.snapshot(self.destination)
        times = {name: (self.destination / name).stat().st_mtime_ns for name in before}
        result = self.succeed("--dest", self.destination)
        self.assertIn("unchanged:", result.stdout)
        self.assertEqual(before, self.snapshot(self.destination))
        self.assertEqual(times, {name: (self.destination / name).stat().st_mtime_ns for name in before})

    def test_different_release_requires_update_then_updates_and_removes(self):
        self.first_install()
        before = self.snapshot(self.destination)
        skill = self.source / "SKILL.md"
        skill.write_text(skill.read_text() + "\nNew release.\n")
        removed = self.source / "references" / "templates.md"
        removed.unlink()
        added = self.source / "references" / "新增 文档.md"
        added.write_text("New reference.\n")
        result = self.run_installer("--dest", self.destination)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--update", result.stderr)
        self.assertEqual(before, self.snapshot(self.destination))
        self.succeed("--dest", self.destination, "--update", "--dry-run")
        self.assertEqual(before, self.snapshot(self.destination))
        extra = self.destination / "references" / "personal.txt"
        extra.write_text("keep me\n")
        self.succeed("--dest", self.destination, "--update")
        self.assertEqual(skill.read_bytes(), (self.destination / "SKILL.md").read_bytes())
        self.assertEqual(added.read_bytes(), (self.destination / "references" / added.name).read_bytes())
        self.assertFalse((self.destination / "references" / "templates.md").exists())
        self.assertEqual("keep me\n", extra.read_text())
        self.assertIn("unchanged:", self.succeed("--dest", self.destination).stdout)

    def test_local_changes_block_update_without_partial_writes(self):
        self.first_install()
        local = self.destination / "references" / "templates.md"
        local.write_text("my local changes\n")
        (self.source / "SKILL.md").write_text("new upstream content\n")
        before = self.snapshot(self.destination)
        for options in ((), ("--update",), ("--update", "--dry-run")):
            with self.subTest(options=options):
                result = self.run_installer("--dest", self.destination, *options)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("modified or removed", result.stderr)
                self.assertEqual(before, self.snapshot(self.destination))

    def test_missing_managed_file_is_a_conflict(self):
        self.first_install()
        (self.destination / "LICENSE").unlink()
        before = self.snapshot(self.destination)
        result = self.run_installer("--dest", self.destination, "--update")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("modified or removed", result.stderr)
        self.assertEqual(before, self.snapshot(self.destination))

    def test_unmanaged_existing_destination_is_never_adopted(self):
        self.destination.mkdir(parents=True)
        for options in ((), ("--update",), ("--dry-run",)):
            with self.subTest(options=options):
                result = self.run_installer("--dest", self.destination, *options)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("not managed", result.stderr)
                self.assertEqual([], list(self.destination.iterdir()))

    def test_new_payload_cannot_overwrite_unmanaged_file(self):
        self.first_install()
        (self.source / "references" / "new.md").write_text("upstream\n")
        (self.destination / "references" / "new.md").write_text("personal\n")
        before = self.snapshot(self.destination)
        result = self.run_installer("--dest", self.destination, "--update")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unmanaged path", result.stderr)
        self.assertEqual(before, self.snapshot(self.destination))

    def test_manifest_rejects_invalid_paths_and_format(self):
        self.first_install()
        path = self.destination / MANIFEST
        original = json.loads(path.read_text())
        outside = self.destination.parent / "outside.txt"
        outside.write_text("must stay untouched\n")
        for invalid in ("not JSON", {"format": 2, "skill": "fugue-docs", "files": {}},
                        dict(original, files={"../outside.txt": "0" * 64}),
                        dict(original, files=dict(original["files"], **{"scripts/../../outside.txt": "0" * 64})),
                        dict(original, files=dict(original["files"], **{"scripts//bad.py": "0" * 64}))):
            with self.subTest(invalid=invalid):
                path.write_text(invalid if isinstance(invalid, str) else json.dumps(invalid))
                before = self.snapshot(self.destination)
                result = self.run_installer("--dest", self.destination, "--update")
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, self.snapshot(self.destination))
                self.assertEqual("must stay untouched\n", outside.read_text())

    def test_rejects_source_equals_destination(self):
        before = self.snapshot(self.source)
        result = self.run_installer("--dest", self.source, "--update")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("different directories", result.stderr)
        self.assertEqual(before, self.snapshot(self.source))

    def test_rejects_destination_inside_source_payload(self):
        result = self.run_installer("--dest", self.source / "scripts" / "installed")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("inside the source payload", result.stderr)
        self.assertFalse((self.source / "scripts" / "installed").exists())

    def test_rejects_symlinked_target_or_ancestor(self):
        elsewhere = self.directory / "elsewhere"
        elsewhere.mkdir()
        linked = self.directory / "linked"
        linked.symlink_to(elsewhere, target_is_directory=True)
        for target in (linked, linked / "nested", self.directory / "dangling"):
            if target.name == "dangling":
                target.symlink_to(self.directory / "missing")
            result = self.run_installer("--dest", target)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("symbolic link", result.stderr)
        self.assertEqual([], list(elsewhere.iterdir()))

    def test_rejects_link_in_source_payload(self):
        secret = self.directory / "secret.txt"
        secret.write_text("must not be copied\n")
        (self.source / "references" / "linked.md").symlink_to(secret)
        result = self.run_installer("--dest", self.destination)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("symbolic link", result.stderr)
        self.assertFalse(self.destination.exists())

    def test_rejects_links_replacing_managed_files_and_manifest(self):
        self.first_install()
        for name in ("SKILL.md", MANIFEST):
            with self.subTest(name=name):
                path = self.destination / name
                original = path.read_bytes()
                external = self.directory / (name + ".external")
                external.write_bytes(original)
                path.unlink()
                path.symlink_to(external)
                result = self.run_installer("--dest", self.destination, "--update")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("symbolic link", result.stderr)
                self.assertEqual(original, external.read_bytes())
                path.unlink()
                path.write_bytes(original)

    def test_rejects_new_payload_parent_that_is_an_unmanaged_file(self):
        self.first_install()
        directory = self.source / "references" / "new-directory"
        directory.mkdir()
        (directory / "file.md").write_text("new\n")
        (self.destination / "references" / "new-directory").write_text("personal\n")
        before = self.snapshot(self.destination)
        result = self.run_installer("--dest", self.destination, "--update")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not a directory", result.stderr)
        self.assertEqual(before, self.snapshot(self.destination))

    def test_hooks_require_explicit_custom_scope(self):
        for arguments in (("--dest", self.destination, "--hooks"),
                          ("--project", self.directory, "--hooks-dir", self.directory / ".codex")):
            with self.subTest(arguments=arguments):
                result = self.run_installer(*arguments)
                self.assertEqual(2, result.returncode)
        self.assertFalse(self.destination.exists())

    def test_default_install_does_not_register_hooks(self):
        project = self.directory / "project"
        self.succeed("--project", project)
        self.assertFalse((project / ".codex").exists())
        self.assertFalse(self.home.exists())

    def test_project_hooks_merge_preserve_other_entries_and_repeat_without_writes(self):
        project = self.directory / "project"
        config_directory = project / ".codex"
        config_directory.mkdir(parents=True)
        config = config_directory / "config.toml"
        config.write_text('[features]\nhooks = true\nmodel = "example"\n')
        other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user-hook"}]}
        hooks_path = config_directory / "hooks.json"
        hooks_path.write_text(json.dumps({"description": "My hooks", "hooks": {"PreToolUse": [other]}}))
        self.succeed("--project", project, "--hooks")
        document = json.loads(hooks_path.read_text())
        self.assertEqual("My hooks", document["description"])
        self.assertEqual(other, document["hooks"]["PreToolUse"][0])
        self.assertEqual({"SessionStart", "SubagentStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop",
                          "SubagentStop", "SessionEnd", "Interrupt"}, set(document["hooks"]))
        for event in ("PreToolUse", "PostToolUse"):
            self.assertEqual("apply_patch|Bash|exec_command|shell|shell_command|local_shell|write_stdin",
                             document["hooks"][event][-1]["matcher"])
        self.assertEqual(3, document["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"])
        self.assertEqual(3, document["hooks"]["Interrupt"][0]["hooks"][0]["timeout"])
        for event, action, timeout in (("SubagentStart", "subagent-start", 30),
                                       ("SubagentStop", "subagent-stop", 60)):
            group = document["hooks"][event][0]
            self.assertNotIn("matcher", group)
            self.assertEqual(action, shlex.split(group["hooks"][0]["command"])[-1])
            self.assertEqual(timeout, group["hooks"][0]["timeout"])
        self.assertEqual('[features]\nhooks = true\nmodel = "example"\n', config.read_text())
        before = self.snapshot(project)
        times = {name: (project / name).stat().st_mtime_ns for name in before}
        result = self.succeed("--project", project, "--hooks")
        self.assertIn("unchanged:", result.stdout)
        self.assertIn("Hooks need review", result.stdout)
        self.assertEqual(before, self.snapshot(project))
        self.assertEqual(times, {name: (project / name).stat().st_mtime_ns for name in before})
        self.assertNotIn("trusted_hash", hooks_path.read_text())

    def test_user_hooks_use_codex_home_or_user_default_without_config_writes(self):
        self.succeed("--user", "--hooks")
        self.assertTrue((self.home / ".codex" / "hooks.json").is_file())
        self.assertFalse((self.home / ".codex" / "config.toml").exists())
        configured = self.directory / "configured codex"
        self.succeed("--user", "--hooks", codex_directory=configured)
        self.assertTrue((configured / "hooks.json").is_file())
        self.assertFalse((configured / "config.toml").exists())

    def test_hooks_directory_override_and_shell_quoted_skill_path(self):
        destination = self.directory / "skill '中文' path"
        config_directory = self.directory / "explicit codex"
        self.succeed("--dest", destination, "--hooks", "--hooks-dir", config_directory)
        document = json.loads((config_directory / "hooks.json").read_text())
        command = document["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        # A shell parser must receive the exact script path as one argument.
        self.assertEqual(["python3", str(destination / "scripts" / "geb_codex_hook.py"), "session-start"],
                         shlex.split(command))
        project = self.directory / "another project"
        override = self.directory / "project override"
        self.succeed("--project", project, "--hooks", "--hooks-dir", override)
        self.assertTrue((override / "hooks.json").is_file())
        self.assertFalse((project / ".codex").exists())

    def test_hooks_dry_run_and_invalid_json_do_not_partially_install(self):
        project = self.directory / "project"
        result = self.succeed("--project", project, "--hooks", "--dry-run")
        self.assertIn(str(project / ".codex" / "hooks.json"), result.stdout)
        self.assertFalse(project.exists())
        config_directory = project / ".codex"
        config_directory.mkdir(parents=True)
        hooks_path = config_directory / "hooks.json"
        for raw in ('{"hooks": ', '{"hooks": {}, "privateMarker": true}',
                    '{"hooks": {}, "hooks": {}}', '{"hooks": {"Stop": "wrong"}}', 'null',
                    '{"hooks":{"Stop":[{"hooks":[{"type":"not-a-hook"}]}]}}',
                    '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"x","timeout":true}]}]}}'):
            with self.subTest(raw=raw):
                hooks_path.write_text(raw)
                before = self.snapshot(project)
                result = self.run_installer("--project", project, "--hooks")
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, self.snapshot(project))
                self.assertFalse((project / ".agents").exists())

    def test_modified_managed_hook_blocks_all_skill_updates(self):
        project = self.directory / "project"
        self.succeed("--project", project, "--hooks")
        path = project / ".codex" / "hooks.json"
        document = json.loads(path.read_text())
        document["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 42
        path.write_text(json.dumps(document))
        (self.source / "SKILL.md").write_text("changed upstream skill\n")
        before = self.snapshot(project)
        result = self.run_installer("--project", project, "--hooks", "--update")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("modified, removed, or duplicated", result.stderr)
        self.assertEqual(before, self.snapshot(project))

    def test_modified_skill_blocks_new_hook_registration(self):
        self.first_install()
        (self.destination / "SKILL.md").write_text("local changes\n")
        config_directory = self.directory / "config"
        result = self.run_installer("--dest", self.destination, "--hooks", "--hooks-dir", config_directory, "--update")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(config_directory.exists())

    def test_hook_update_preserves_unmanaged_group_indices(self):
        config_directory = self.directory / "config"
        self.succeed("--dest", self.destination, "--hooks", "--hooks-dir", config_directory)
        hooks_path = config_directory / "hooks.json"
        document = json.loads(hooks_path.read_text())
        other = {"hooks": [{"type": "command", "command": "echo existing-user-hook"}]}
        document["hooks"]["Stop"].append(other)
        hooks_path.write_text(json.dumps(document))
        relocated = self.directory / "new skill location"
        result = self.run_installer("--dest", relocated, "--hooks", "--hooks-dir", config_directory)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--update", result.stderr)
        self.assertFalse(relocated.exists())
        self.succeed("--dest", relocated, "--hooks", "--hooks-dir", config_directory, "--update")
        changed = json.loads(hooks_path.read_text())
        self.assertEqual(other, changed["hooks"]["Stop"][1])
        self.assertIn(str(relocated), changed["hooks"]["Stop"][0]["hooks"][0]["command"])

    def test_seven_event_install_upgrades_subagent_hooks_without_shifting_entries(self):
        project = self.directory / "project"
        self.succeed("--project", project, "--hooks")
        directory = project / ".codex"
        hooks_path = directory / "hooks.json"
        marker_path = directory / ".fugue-codex-hooks.json"
        document = json.loads(hooks_path.read_text())
        marker = json.loads(marker_path.read_text())
        for event in ("SubagentStart", "SubagentStop"):
            del document["hooks"][event]
            del marker["entries"][event]
        other = {"hooks": [{"type": "command", "command": "echo existing-user-hook"}]}
        document["hooks"]["Stop"].append(other)
        document["hooks"]["SubagentStop"] = [other]
        hooks_path.write_text(json.dumps(document))
        marker_path.write_text(json.dumps(marker))
        before = self.snapshot(project)
        result = self.run_installer("--project", project, "--hooks")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--update", result.stderr)
        self.assertEqual(before, self.snapshot(project))
        self.succeed("--project", project, "--hooks", "--update", "--dry-run")
        self.assertEqual(before, self.snapshot(project))
        self.succeed("--project", project, "--hooks", "--update")
        upgraded = json.loads(hooks_path.read_text())
        for event in marker["entries"]:
            self.assertEqual(document["hooks"][event], upgraded["hooks"][event])
        self.assertEqual(other, upgraded["hooks"]["SubagentStop"][0])
        self.assertEqual(2, len(upgraded["hooks"]["SubagentStop"]))
        self.assertEqual(9, len(json.loads(marker_path.read_text())["entries"]))
        self.assertIn("unchanged:", self.succeed("--project", project, "--hooks").stdout)

    def test_hooks_reject_symlinks_and_duplicate_toml_registration(self):
        project = self.directory / "project"
        config_directory = project / ".codex"
        config_directory.mkdir(parents=True)
        external = self.directory / "external.json"
        external.write_text('{"hooks": {}}')
        hooks_path = config_directory / "hooks.json"
        hooks_path.symlink_to(external)
        result = self.run_installer("--project", project, "--hooks")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("symbolic link", result.stderr)
        self.assertFalse((project / ".agents").exists())
        hooks_path.unlink()
        config = config_directory / "config.toml"
        config.write_text('[[hooks.Stop]]\nhooks = [{type="command", command="python3 /skill/scripts/geb_codex_hook.py stop"}]\n')
        result = self.run_installer("--project", project, "--hooks")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("config.toml already references", result.stderr)
        self.assertFalse((project / ".agents").exists())

    def test_unmanaged_matching_hooks_are_not_duplicated(self):
        project = self.directory / "project"
        self.succeed("--project", project, "--hooks")
        marker = project / ".codex" / ".fugue-codex-hooks.json"
        marker.unlink()
        before = self.snapshot(project)
        result = self.run_installer("--project", project, "--hooks", "--update")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Unmanaged fugue-docs hook", result.stderr)
        self.assertEqual(before, self.snapshot(project))

    def test_hook_write_failure_rolls_back_skill_and_existing_hook_bytes(self):
        namespace = self.installer_namespace()
        config_directory = self.directory / "config"
        config_directory.mkdir()
        (config_directory / "hooks.json").write_text('{ "description": "mine", "hooks": {} }\n')
        before = self.snapshot(self.directory)
        real_write = namespace["write_file"]
        failed = []

        def fail_once(path, data, mode):
            if path.name == ".fugue-codex-hooks.json" and not failed:
                failed.append(path)
                raise OSError("simulated hook manifest write failure")
            return real_write(path, data, mode)

        with patch.dict(namespace["install"].__globals__, {"write_file": fail_once}):
            with self.assertRaisesRegex(OSError, "simulated"):
                namespace["install"](self.source, self.destination, hooks_directory=config_directory)
        self.assertEqual(before, self.snapshot(self.directory))
        self.assertFalse(self.destination.parent.exists())

    def test_linked_worktree_requires_explicit_hook_configuration_scope(self):
        primary = self.directory / "primary"
        primary.mkdir()
        def git(*arguments):
            result = subprocess.run(["git", "-C", str(primary), *arguments], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
        git("init", "-q")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "initial")
        worktree = self.directory / "linked worktree"
        git("worktree", "add", "--detach", str(worktree))
        result = self.run_installer("--project", worktree, "--hooks")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Linked worktree", result.stderr)
        self.assertFalse((worktree / ".agents").exists())
        self.succeed("--project", worktree, "--hooks", "--hooks-dir", primary / ".codex")
        self.assertTrue((primary / ".codex" / "hooks.json").exists())

    def test_installed_copy_can_install_and_run_tools_from_other_cwd(self):
        self.first_install()
        relocated = self.directory / "second installation"
        installed_script = self.destination / "scripts" / "geb_install_codex.py"
        self.succeed("--dest", relocated, script=installed_script)
        self.assertEqual(self.snapshot(self.destination), self.snapshot(relocated))
        project = self.directory / "sample project"
        project.mkdir()
        (project / "app.py").write_text("print('hello')\n")
        for command in (("geb_arch.py", str(project), "--json"),
                        ("geb_scaffold.py", str(project), "--dry-run"),
                        ("geb_check.py", str(project), "--if-adopted"),
                        ("geb_sync.py", "--help"), ("geb_metrics.py", "--help"),
                        ("geb_adapt.py", "--help"), ("geb_staged.py", "--help")):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(relocated / "scripts" / command[0]), *command[1:]],
                                        cwd=self.directory, env=self.environment, capture_output=True,
                                        text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((project / "PROJECT_INDEX.md").exists())
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
