#!/usr/bin/env python3
"""
[INPUT]: 依赖 argparse, hashlib, json, os, pathlib, stat, sys, geb_install_codex
[OUTPUT]: 显式安装 Antigravity 原生插件(plugin.json + hooks.json + skills/fugue-docs/SKILL.md + 核心脚本),支持预检、无写入预览与安全更新
[POS]: fugue-docs 工具层-Antigravity 原生插件分发与安装入口
[PROTOCOL]: 变更时同步 evals/test_antigravity_hooks.py、scripts/FOLDER_INDEX.md 与 references/antigravity.md
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geb_install_codex as shared  # noqa: E402

DEFAULT_PLUGIN_NAME = "fugue-docs-agy"
MANIFEST = ".fugue-antigravity-install.json"

CORE_SCRIPTS = (
    "geb_adapt.py",
    "geb_antigravity_hook.py",
    "geb_arch.py",
    "geb_check.py",
    "geb_facts.py",
    "geb_hook.py",
    "geb_metrics.py",
    "geb_scaffold.py",
    "geb_staged.py",
    "geb_sync.py",
    "geb_telemetry.py",
    "git-pre-commit-hook.sh",
)
CORE_REFS = ("antigravity.md", "manual-workflow.md", "templates.md", "token-accounting.md")
CORE_ADAPTERS = (
    "ANTIGRAVITY.md",
    "ANTIGRAVITY_EN.md",
    "PROTOCOL.md",
    "PROTOCOL_EN.md",
    "PROTOCOL_COMPACT.md",
    "PROTOCOL_COMPACT_EN.md",
)


def hook_command(event):
    return (
        "python scripts/geb_antigravity_hook.py %s"
        " || python3 scripts/geb_antigravity_hook.py %s"
        " || py -3 scripts/geb_antigravity_hook.py %s"
    ) % (event, event, event)


def build_plugin_json(plugin_name, source):
    base_path = source / "plugin.json"
    if base_path.is_file():
        data = json.loads(base_path.read_text(encoding="utf-8"))
    else:
        data = {
            "displayName": "Fugue Docs (赋格文档)",
            "version": "2.7.0",
            "description": "GEB fractal documentation protocol for Antigravity.",
            "logo": "assets/logo.png",
        }
    data["name"] = plugin_name
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_hooks_json(plugin_name):
    payload = {
        plugin_name: {
            "SessionStart": [
                {"type": "command", "command": hook_command("session-start"), "timeout": 30}
            ],
            "PreInvocation": [
                {"type": "command", "command": hook_command("pre-invocation"), "timeout": 30}
            ],
            "PostToolUse": [
                {
                    "matcher": "write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content|run_command",
                    "hooks": [
                        {"type": "command", "command": hook_command("post-tool"), "timeout": 30}
                    ],
                }
            ],
            "Stop": [
                {"type": "command", "command": hook_command("stop"), "timeout": 60}
            ],
        }
    }
    return (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def collect_plugin_files(source, plugin_name, include_hooks=True):
    files = {}

    def add_copy(rel):
        path = source / rel
        shared.reject_symlinks(path)
        if not path.is_file():
            raise shared.InstallError("Missing required Antigravity payload file: %s" % path)
        files[rel] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))

    for name in CORE_SCRIPTS:
        add_copy("scripts/" + name)
    for name in CORE_REFS:
        add_copy("references/" + name)
    for name in CORE_ADAPTERS:
        add_copy("adapters/" + name)
    add_copy("skills/fugue-docs/SKILL.md")
    add_copy("assets/logo.png")
    add_copy("LICENSE")
    if (source / "README.md").is_file():
        add_copy("README.md")

    files["plugin.json"] = (build_plugin_json(plugin_name, source), 0o644)
    if include_hooks:
        files["hooks.json"] = (build_hooks_json(plugin_name), 0o644)
    return files


def read_manifest(destination, plugin_name):
    path = destination / MANIFEST
    shared.reject_symlinks(path)
    if not path.is_file():
        raise shared.InstallError("Existing destination is not managed by this installer: %s" % destination)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise shared.InstallError("Invalid installation manifest: %s" % path) from error
    if (
        not isinstance(value, dict)
        or value.get("format") != 1
        or value.get("plugin") != plugin_name
        or not isinstance(value.get("files"), dict)
    ):
        raise shared.InstallError("Invalid installation manifest: %s" % path)
    return value["files"]


def plan_install(source, destination, files, plugin_name, update=False):
    shared.reject_symlinks(destination)
    if destination == source:
        raise shared.InstallError("Source and destination must be different directories")
    expected = {name: hashlib.sha256(data).hexdigest() for name, (data, _) in files.items()}
    if not destination.exists():
        return "install", {}, expected
    if not destination.is_dir():
        raise shared.InstallError("Destination is not a directory: %s" % destination)
    previous = read_manifest(destination, plugin_name)
    for name, digest in previous.items():
        path = destination / name
        shared.reject_symlinks(path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise shared.InstallError("Managed file was modified or removed; preserve your changes first: %s" % path)
    for name in expected:
        path = destination / name
        shared.reject_symlinks(path)
        if name not in previous and path.exists():
            raise shared.InstallError("New payload would overwrite an unmanaged path: %s" % path)
    if previous == expected:
        return "unchanged", previous, expected
    if not update:
        raise shared.InstallError("Installed plugin differs; rerun with --update after reviewing changes")
    return "update", previous, expected


def install(source, destination, plugin_name=DEFAULT_PLUGIN_NAME, include_hooks=True, update=False, dry_run=False):
    files = collect_plugin_files(source, plugin_name, include_hooks=include_hooks)
    action, previous, expected = plan_install(source, destination, files, plugin_name, update=update)
    manifest = (
        json.dumps({"format": 1, "plugin": plugin_name, "files": expected}, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    changes = {}
    if action != "unchanged":
        for name, (data, mode) in files.items():
            if previous.get(name) != expected[name]:
                changes[destination / name] = (data, mode)
        for name in sorted(set(previous.keys()) - set(expected.keys())):
            changes[destination / name] = None
        changes[destination / MANIFEST] = (manifest, 0o644)
    for path in changes:
        parent = shared.check_destination(path)
        if not os.access(parent, os.W_OK | os.X_OK):
            raise shared.InstallError("Target directory is not writable: %s" % parent)
    if not dry_run and changes:
        shared.apply_transaction(changes)
    return action, len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install fugue-docs as a native Antigravity plugin (Python 3.9+)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--user", action="store_true", help="install into ~/.gemini/config/plugins/<name>")
    target.add_argument("--project", metavar="ROOT", help="install into ROOT/.agents/plugins/<name>")
    parser.add_argument("--name", default=DEFAULT_PLUGIN_NAME, help="plugin name and directory (default: fugue-docs-agy)")
    parser.add_argument("--no-hooks", action="store_true", help="install skill and tools without hooks.json")
    parser.add_argument("--dry-run", action="store_true", help="validate and preview without writing any files")
    parser.add_argument("--update", action="store_true", help="update managed files only when unmodified")
    args = parser.parse_args(argv)

    source = Path(__file__).resolve().parent.parent
    if args.user:
        destination = shared.absolute_path(Path.home()) / ".gemini" / "config" / "plugins" / args.name
    else:
        destination = shared.absolute_path(args.project) / ".agents" / "plugins" / args.name
    try:
        action, count = install(
            source,
            destination,
            plugin_name=args.name,
            include_hooks=not args.no_hooks,
            update=args.update,
            dry_run=args.dry_run,
        )
    except (shared.InstallError, OSError, UnicodeError) as error:
        print("Antigravity plugin installation failed: %s" % error, file=sys.stderr)
        return 1
    print("%s%s: %s (%d managed files)" % ("dry-run: " if args.dry_run else "", action, destination, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
