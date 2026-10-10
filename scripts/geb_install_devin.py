#!/usr/bin/env python3
"""
[INPUT]: 依赖 argparse, json, os, pathlib, sys, geb_install_codex
[OUTPUT]: 显式安装 Devin skill 与可选原生 hooks,支持无写入预览、安全更新与回滚
[POS]: fugue-docs 工具层-Devin skill 与 hooks 安装入口
[PROTOCOL]: 变更时更新 evals/test_devin_install.py、scripts/FOLDER_INDEX.md 与 references/devin.md
"""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geb_install_codex as shared  # noqa: E402

SKILL_NAME = "fugue-docs"
MANIFEST = ".fugue-devin-install.json"
HOOK_MARKER = "geb_devin_hook.py"
EVENTS = (
    ("SessionStart", "session-start", None, 30),
    ("UserPromptSubmit", "prompt", None, 30),
    ("PreToolUse", "pre-tool", "^(edit|write|notebook_edit|apply_patch|exec)$", 30),
    ("PostToolUse", "post-tool", "^exec$", 30),
    ("Stop", "stop", None, 60),
    ("SessionEnd", "session-end", None, 30),
)


def shell_quote(value):
    return "'" + str(value).replace("'", "'\\''") + "'"


def command_for(destination, event, project):
    if project:
        script = '"$DEVIN_PROJECT_DIR/.agents/skills/fugue-docs/scripts/geb_devin_hook.py"'
    else:
        script = shell_quote(destination / "scripts" / "geb_devin_hook.py")
    return "python3 %s %s" % (script, event)


def hook_entries(destination, project):
    result = {}
    for event, argument, matcher, timeout in EVENTS:
        hook = {"type": "command", "command": command_for(destination, argument, project),
                "timeout": timeout}
        entry = {"hooks": [hook]}
        if matcher is not None:
            entry["matcher"] = matcher
        result[event] = [entry]
    return result


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key: %s" % key)
        value[key] = item
    return value


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as error:
        raise shared.InstallError("Invalid Devin hooks JSON: %s (%s)" % (path, error)) from error


def validate_hooks(hooks, path):
    if not isinstance(hooks, dict):
        raise shared.InstallError("Invalid Devin hooks configuration (expected object): %s" % path)
    for event, groups in hooks.items():
        if event not in {name for name, *_ in EVENTS}:
            continue
        if not isinstance(groups, list):
            raise shared.InstallError("Invalid Devin hook event %s in %s" % (event, path))
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise shared.InstallError("Invalid Devin hook entry for %s in %s" % (event, path))
            if any(not isinstance(hook, dict) for hook in group["hooks"]):
                raise shared.InstallError("Invalid Devin hook command for %s in %s" % (event, path))


def managed_merge(current, desired, path):
    validate_hooks(current, path)
    merged = {}
    for event, groups in current.items():
        if event not in desired:
            merged[event] = groups
            continue
        retained = []
        for group in groups:
            kept_hooks = [hook for hook in group["hooks"]
                          if HOOK_MARKER not in str(hook.get("command", ""))]
            if kept_hooks:
                copied = dict(group)
                copied["hooks"] = kept_hooks
                retained.append(copied)
        if retained:
            merged[event] = retained
    for event, groups in desired.items():
        merged.setdefault(event, []).extend(groups)
    return merged


def hook_change(path, destination, project, user):
    shared.check_destination(path)
    desired = hook_entries(destination, project)
    if user:
        if path.exists():
            config = read_json(path)
            if not isinstance(config, dict):
                raise shared.InstallError("Invalid Devin user config (expected object): %s" % path)
        else:
            config = {}
        current = config.get("hooks", {})
        validate_hooks(current, path)
        config["hooks"] = managed_merge(current, desired, path)
        output = config
    else:
        current = read_json(path) if path.exists() else {}
        output = managed_merge(current, desired, path)
    data = (json.dumps(output, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return None
    return path, (data, 0o644)


def install(source, destination, update=False, dry_run=False, hooks_path=None, project=False, user=False):
    files = shared.source_files(source)
    for runtime in ("scripts/geb_devin_hook.py", "scripts/geb_codex_hook.py"):
        if runtime not in files:
            raise shared.InstallError("Source package is missing required Devin runtime: %s" % runtime)
    action, previous, expected = shared.installation_plan(
        source, destination, files, update, manifest_name=MANIFEST)
    manifest = (json.dumps({"format": 1, "skill": SKILL_NAME, "files": expected},
                           ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    changes = {}
    if action != "unchanged":
        for name, (data, mode) in files.items():
            if previous.get(name) != expected[name]:
                changes[destination / name] = (data, mode)
        for name in sorted(previous.keys() - expected.keys()):
            changes[destination / name] = None
        changes[destination / MANIFEST] = (manifest, 0o644)
    if hooks_path is not None:
        if hooks_path == destination or destination in hooks_path.parents:
            raise shared.InstallError("Devin hooks configuration must be outside the skill payload")
        change = hook_change(hooks_path, destination, project, user)
        if change is not None:
            changes[change[0]] = change[1]
    for path in changes:
        parent = shared.check_destination(path)
        if not os.access(parent, os.W_OK | os.X_OK):
            raise shared.InstallError("Target directory is not writable: %s" % parent)
    if not dry_run:
        shared.apply_transaction(changes)
    if action == "unchanged" and hooks_path is not None and changes:
        action = "configure-hooks"
    return action, len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install fugue-docs as a native Devin skill (Python 3.9+)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", metavar="ROOT", help="install into ROOT/.agents/skills/fugue-docs")
    target.add_argument("--user", action="store_true", help="install into ~/.config/devin/skills/fugue-docs")
    parser.add_argument("--dry-run", action="store_true", help="validate and preview without writing any files")
    parser.add_argument("--update", action="store_true", help="update managed files only when unmodified")
    parser.add_argument("--hooks", action="store_true", help="also register native Devin hooks")
    args = parser.parse_args(argv)
    source = Path(__file__).resolve().parent.parent
    project = args.project is not None
    if project:
        root = shared.absolute_path(args.project)
        destination = root / ".agents" / "skills" / SKILL_NAME
        hooks_path = root / ".devin" / "hooks.v1.json" if args.hooks else None
    else:
        destination = shared.absolute_path(Path.home()) / ".config" / "devin" / "skills" / SKILL_NAME
        hooks_path = shared.absolute_path(Path.home()) / ".config" / "devin" / "config.json" if args.hooks else None
    try:
        action, count = install(source, destination, update=args.update, dry_run=args.dry_run,
                                hooks_path=hooks_path, project=project, user=args.user)
    except (shared.InstallError, OSError, UnicodeError) as error:
        print("Devin skill installation failed: %s" % error, file=sys.stderr)
        return 1
    print("%s%s: %s (%d managed files)" % ("dry-run: " if args.dry_run else "", action, destination, count))
    if hooks_path is not None:
        print("hooks: %s" % hooks_path)
        print("Verify that hooks loaded with /hooks in Devin CLI; hooks may be unavailable in cloud sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
