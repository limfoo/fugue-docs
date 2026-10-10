#!/usr/bin/env python3
"""
[INPUT]: 依赖 argparse, geb_codex_config, hashlib, json, os, pathlib, stat, subprocess, sys, tempfile
[OUTPUT]: 显式安装 Codex skill 与可选原生 hooks;共享白名单、清单参数化、安全更新、预检与事务回滚供宿主安装器复用
[POS]: fugue-docs 工具层-Codex 原生 standalone skill 分发入口
[PROTOCOL]: 变更时更新此头部,检查 scripts/FOLDER_INDEX.md、Codex 安装文档与复用该事务的宿主安装说明
"""

import argparse
from geb_codex_config import HOOK_MANIFEST, RUNTIME, HookConfigError, plan_hooks
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile

SKILL_NAME = "fugue-docs"
MANIFEST = ".fugue-codex-install.json"
PAYLOAD = ("SKILL.md", "scripts", "references", "adapters", "agents", "LICENSE")
EXCLUDED = {"__pycache__", ".git", ".claude-plugin", "hooks", "evals"}
MACOS_SYSTEM_ALIASES = {"/tmp": "/private/tmp", "/var": "/private/var"}


class InstallError(Exception):
    """An unsafe or ambiguous installation that must not proceed."""


def absolute_path(value):
    # Do not resolve links here: validation must see a linked target or ancestor.
    path = Path(os.path.abspath(os.path.expanduser(str(value))))
    # macOS exposes its normal temporary directories through system symlinks.
    # Normalize only these exact aliases, never arbitrary user-controlled links.
    if sys.platform == "darwin":
        for alias, canonical in MACOS_SYSTEM_ALIASES.items():
            link = Path(alias)
            if (path == link or link in path.parents) and link.is_symlink():
                target = Path(os.path.abspath(str(link.parent / os.readlink(link))))
                if target == Path(canonical):
                    path = Path(canonical) / path.relative_to(link)
                    break
    return path


def reject_symlinks(path):
    for part in reversed((path,) + tuple(path.parents)):
        if part.is_symlink():
            raise InstallError("Refusing symbolic link: %s" % part)


def payload_path(name):
    path = PurePosixPath(name)
    return (bool(path.parts) and not path.is_absolute() and path.as_posix() == name
            and "\\" not in name and not any(part in (".", "..") for part in path.parts)
            and path.parts[0] in PAYLOAD and not any(part in EXCLUDED for part in path.parts)
            and path.suffix not in (".pyc", ".pyo")
            and (path.parts[0] not in ("SKILL.md", "LICENSE") or len(path.parts) == 1))


def source_files(source):
    """Snapshot only the distributable payload, rejecting links and special files."""
    files = {}

    def collect(path):
        if path.name in EXCLUDED or path.suffix in (".pyc", ".pyo"):
            return
        reject_symlinks(path)
        if path.is_dir():
            for child in sorted(path.iterdir()):
                collect(child)
        elif path.is_file():
            name = path.relative_to(source).as_posix()
            files[name] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        else:
            raise InstallError("Missing or non-regular payload file: %s" % path)

    for name in PAYLOAD:
        collect(source / name)
    return files


def hashes(files):
    return {name: hashlib.sha256(data).hexdigest() for name, (data, _) in files.items()}


def read_manifest(destination, manifest_name=MANIFEST):
    path = destination / manifest_name
    reject_symlinks(path)
    if not path.is_file():
        raise InstallError("Existing destination is not managed by this installer: %s" % destination)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise InstallError("Invalid installation manifest: %s" % path) from error
    if (not isinstance(value, dict) or value.get("format") != 1
            or value.get("skill") != SKILL_NAME or not isinstance(value.get("files"), dict)):
        raise InstallError("Invalid installation manifest: %s" % path)
    files = value["files"]
    if "SKILL.md" not in files:
        raise InstallError("Installation manifest does not track SKILL.md: %s" % path)
    for name, digest in files.items():
        if (not payload_path(name) or not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise InstallError("Invalid managed path or hash in manifest: %r" % name)
    return files


def installation_plan(source, destination, files, update, manifest_name=MANIFEST):
    """Check every potential conflict before making any filesystem changes."""
    reject_symlinks(destination)
    if destination == source:
        raise InstallError("Source and destination must be different directories")
    for directory in (source / name for name in PAYLOAD if (source / name).is_dir()):
        if directory == destination or directory in destination.parents:
            raise InstallError("Destination cannot be inside the source payload: %s" % destination)
    expected = hashes(files)
    if not destination.exists():
        for parent in destination.parents:
            if parent.exists() and not parent.is_dir():
                raise InstallError("Destination ancestor is not a directory: %s" % parent)
        return "install", {}, expected
    if not destination.is_dir():
        raise InstallError("Destination is not a directory: %s" % destination)
    previous = read_manifest(destination, manifest_name)
    for name, digest in previous.items():
        path = destination / name
        reject_symlinks(path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise InstallError("Managed file was modified or removed; preserve your changes first: %s" % path)
    for name in expected:
        path = destination / name
        reject_symlinks(path)
        if name not in previous and path.exists():
            raise InstallError("New payload would overwrite an unmanaged path: %s" % path)
        for parent in path.parents:
            if parent == destination:
                break
            if parent.exists() and not parent.is_dir():
                raise InstallError("Payload parent is not a directory: %s" % parent)
    if previous == expected:
        return "unchanged", previous, expected
    if not update:
        raise InstallError("Installed payload differs; rerun with --update after reviewing the changes")
    return "update", previous, expected


def write_file(path, data, mode):
    """Replace a file atomically after its parent and links have been checked."""
    reject_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".fugue-install-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_destination(path):
    reject_symlinks(path)
    if path.exists() and not path.is_file():
        raise InstallError("Target is not a regular file: %s" % path)
    for parent in path.parents:
        if parent.exists():
            if not parent.is_dir():
                raise InstallError("Target ancestor is not a directory: %s" % parent)
            return parent
    raise InstallError("Target has no existing parent: %s" % path)


def apply_transaction(changes):
    """Preflight all paths, then restore prior bytes/modes on a write failure."""
    originals = {}
    created_directories = set()
    for path in changes:
        parent = check_destination(path)
        if not os.access(parent, os.W_OK | os.X_OK):
            raise InstallError("Target directory is not writable: %s" % parent)
        originals[path] = ((path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                           if path.exists() else None)
        for directory in path.parents:
            if directory.exists():
                break
            created_directories.add(directory)
    touched = []
    try:
        for path, content in changes.items():
            touched.append(path)
            if content is None:
                path.unlink()
            else:
                write_file(path, *content)
    except BaseException as error:
        failures = []
        for path in reversed(touched):
            try:
                if originals[path] is None:
                    if path.exists():
                        path.unlink()
                else:
                    write_file(path, *originals[path])
            except (OSError, InstallError) as rollback_error:
                failures.append("%s: %s" % (path, rollback_error))
        for directory in sorted(created_directories, key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        if failures:
            raise InstallError("Installation failed (%s); rollback also failed: %s" %
                               (error, "; ".join(failures))) from error
        raise


def project_hooks_directory(project):
    """Linked worktrees may load hooks from the primary checkout, not locally."""
    if project.exists():
        try:
            result = subprocess.run(["git", "-C", str(project), "rev-parse", "--git-dir", "--git-common-dir"],
                                    capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            paths = result.stdout.splitlines()
            if len(paths) == 2:
                git_dir, common_dir = (absolute_path(project / path) for path in paths)
                if git_dir != common_dir:
                    raise InstallError("Linked worktree hooks may be loaded from the primary checkout; "
                                       "use --hooks-dir to explicitly select its actual Codex configuration directory")
    return project / ".codex"


def install(source, destination, update=False, dry_run=False, hooks_directory=None, manifest_name=MANIFEST):
    files = source_files(source)
    action, previous, expected = installation_plan(source, destination, files, update, manifest_name)
    hook_changes = {}
    if hooks_directory is not None:
        if "scripts/" + RUNTIME not in files:
            raise InstallError("Source package is missing its Codex hook runtime: %s" % RUNTIME)
        source_directories = [source / name for name in PAYLOAD if (source / name).is_dir()]
        if (hooks_directory == destination or destination in hooks_directory.parents
                or hooks_directory == source
                or any(path == hooks_directory or path in hooks_directory.parents for path in source_directories)):
            raise InstallError("Hooks configuration must be outside the skill payload")
        for name in ("hooks.json", HOOK_MANIFEST, "config.toml"):
            check_destination(hooks_directory / name)
        config = hooks_directory / "config.toml"
        if config.exists() and RUNTIME in config.read_text(encoding="utf-8"):
            raise InstallError("config.toml already references %s; reconcile TOML hooks before installing hooks.json" % RUNTIME)
        hook_changes = plan_hooks(hooks_directory, destination, update=update)
    manifest = (json.dumps({"format": 1, "skill": SKILL_NAME, "files": expected},
                           ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    changes = {}
    if action != "unchanged":
        for name, (data, mode) in files.items():
            if previous.get(name) != expected[name]:
                changes[destination / name] = (data, mode)
        for name in sorted(previous.keys() - expected.keys()):
            changes[destination / name] = None
        changes[destination / manifest_name] = (manifest, 0o644)
    changes.update(hook_changes)
    # Dry runs perform the same filesystem/permission checks without mkdir or writes.
    for path in changes:
        parent = check_destination(path)
        if not os.access(parent, os.W_OK | os.X_OK):
            raise InstallError("Target directory is not writable: %s" % parent)
    if not dry_run:
        apply_transaction(changes)
    if action == "unchanged" and hook_changes:
        action = "configure-hooks"
    return action, len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install fugue-docs as a native Codex skill (Python 3.9+)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", metavar="ROOT", help="install into ROOT/.agents/skills/fugue-docs")
    target.add_argument("--user", action="store_true", help="install into ~/.agents/skills/fugue-docs")
    target.add_argument("--dest", metavar="PATH", help="use PATH as the complete skill destination")
    parser.add_argument("--dry-run", action="store_true", help="validate and preview without writing any files")
    parser.add_argument("--update", action="store_true", help="update a managed install only if its files are unmodified")
    parser.add_argument("--hooks", action="store_true", help="also register native Codex hooks; native trust review is still required")
    parser.add_argument("--hooks-dir", metavar="DIR", help="explicit Codex configuration directory for --hooks (required with --dest)")
    args = parser.parse_args(argv)
    if args.hooks_dir and not args.hooks:
        parser.error("--hooks-dir requires --hooks")
    if args.hooks and args.dest is not None and not args.hooks_dir:
        parser.error("--dest --hooks requires --hooks-dir to select a configuration scope")
    if args.project is not None:
        destination = absolute_path(args.project) / ".agents" / "skills" / SKILL_NAME
    elif args.user:
        destination = absolute_path(Path.home()) / ".agents" / "skills" / SKILL_NAME
    else:
        destination = absolute_path(args.dest)
    source = Path(__file__).resolve().parent.parent
    hooks_directory = None
    try:
        if args.hooks:
            if args.hooks_dir:
                hooks_directory = absolute_path(args.hooks_dir)
            elif args.project is not None:
                hooks_directory = project_hooks_directory(absolute_path(args.project))
            else:
                hooks_directory = absolute_path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        action, count = install(source, destination, update=args.update, dry_run=args.dry_run,
                                hooks_directory=hooks_directory)
    except (InstallError, HookConfigError, OSError, UnicodeError) as error:
        print("Codex skill installation failed: %s" % error, file=sys.stderr)
        return 1
    print("%s%s: %s (%d managed files)" % ("dry-run: " if args.dry_run else "", action, destination, count))
    if hooks_directory is not None:
        print("hooks: %s" % (hooks_directory / "hooks.json"))
        print("Restart Codex and review these hooks in its native 'Hooks need review' dialog. "
              "Project hooks also require a trusted project. This installer does not grant trust or change config.toml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
