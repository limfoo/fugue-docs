#!/usr/bin/env python3
"""
[INPUT]: 依赖 hashlib, json, pathlib, shlex, stat
[OUTPUT]: 生成 Codex hooks.json 的受管安装计划,保留其他 hooks 并拒绝本地修改冲突
[POS]: fugue-docs 工具层-Codex 原生 hook 配置合并器,不写信任或执行命令
[PROTOCOL]: 变更时更新此头部,然后检查上级 FOLDER_INDEX.md 与 Codex 安装文档
"""

import hashlib
import json
from pathlib import Path
import shlex
import stat

HOOK_MANIFEST = ".fugue-codex-hooks.json"
RUNTIME = "geb_codex_hook.py"
TOOL_MATCHER = "apply_patch|Bash|exec_command|shell|shell_command|local_shell|write_stdin"
HOOK_EVENTS = {
    "SessionStart": ("session-start", 30),
    "SubagentStart": ("subagent-start", 30),
    "UserPromptSubmit": ("prompt", 30),
    "PreToolUse": ("pre-tool", 30),
    "PostToolUse": ("post-tool", 30),
    "Stop": ("stop", 60),
    "SubagentStop": ("subagent-stop", 60),
    "SessionEnd": ("session-end", 3),
    "Interrupt": ("interrupt", 3),
}


class HookConfigError(Exception):
    """Hook configuration cannot safely be merged."""


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise HookConfigError("Duplicate JSON key: %s" % key)
        result[key] = value
    return result


def invalid_constant(value):
    raise HookConfigError("Non-JSON numeric constant: %s" % value)


def read_json(path):
    if not path.exists():
        return None, None
    if not path.is_file():
        raise HookConfigError("Hook configuration is not a regular file: %s" % path)
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=invalid_constant), raw
    except (ValueError, UnicodeError) as error:
        raise HookConfigError("Invalid JSON in %s: %s" % (path, error)) from error


def validate_hooks(document):
    # HooksFile rejects unknown root keys. Preserve other handlers and their
    # optional fields; the installed Codex version performs full schema checks.
    if (not isinstance(document, dict) or set(document) - {"description", "hooks"}
            or (document.get("description") is not None and not isinstance(document["description"], str))
            or not isinstance(document.get("hooks", {}), dict)):
        raise HookConfigError("Invalid hooks.json root; expected {description?, hooks: {...}}")
    for event, groups in document.get("hooks", {}).items():
        if not isinstance(groups, list):
            raise HookConfigError("Hook event must contain a list of matcher groups: %s" % event)
        for group in groups:
            if (not isinstance(group, dict) or not isinstance(group.get("hooks", []), list)
                    or (group.get("matcher") is not None and not isinstance(group["matcher"], str))):
                raise HookConfigError("Invalid matcher group in %s" % event)
            for hook in group.get("hooks", []):
                if not isinstance(hook, dict) or hook.get("type") not in ("command", "mcp_tool", "prompt", "agent"):
                    raise HookConfigError("Invalid hook handler in %s" % event)
                if hook["type"] == "command" and not isinstance(hook.get("command"), str):
                    raise HookConfigError("Command hook is missing its command in %s" % event)
                for key in ("timeout", "additionalContextLimit"):
                    value = hook.get(key)
                    if value is not None and (type(value) is not int or value < 0 or value > 2 ** 64 - 1):
                        raise HookConfigError("Invalid %s in %s" % (key, event))
                for key in ("commandWindows", "command_windows", "statusMessage"):
                    if hook.get(key) is not None and not isinstance(hook[key], str):
                        raise HookConfigError("Invalid %s in %s" % (key, event))
                if "async" in hook and not isinstance(hook["async"], bool):
                    raise HookConfigError("Invalid async flag in %s" % event)
                if hook["type"] == "mcp_tool" and (not isinstance(hook.get("server"), str)
                                                    or not isinstance(hook.get("tool"), str)
                                                    or not isinstance(hook.get("input", {}), dict)):
                    raise HookConfigError("Invalid MCP hook in %s" % event)


def managed_groups(skill_directory):
    command = "python3 " + shlex.quote(str(skill_directory / "scripts" / RUNTIME))
    groups = {event: {"hooks": [{"type": "command", "command": command + " " + action,
                                "timeout": timeout}]}
              for event, (action, timeout) in HOOK_EVENTS.items()}
    for event in ("PreToolUse", "PostToolUse"):
        groups[event]["matcher"] = TOOL_MATCHER
    return groups


def group_hash(group):
    return hashlib.sha256(json_bytes(group)).hexdigest()


def managed_entries(manifest):
    if manifest is None:
        return {}
    if (not isinstance(manifest, dict) or manifest.get("format") != 1
            or manifest.get("skill") != "fugue-docs" or not isinstance(manifest.get("entries"), dict)):
        raise HookConfigError("Invalid fugue-docs hook installation manifest")
    result = {}
    for event, entry in manifest["entries"].items():
        if (event not in HOOK_EVENTS or not isinstance(entry, dict)
                or not isinstance(entry.get("group"), dict)
                or entry.get("sha256") != group_hash(entry["group"])):
            raise HookConfigError("Invalid managed hook entry: %s" % event)
        group = entry["group"]
        validate_hooks({"hooks": {event: [group]}})
        handlers = group.get("hooks", [])
        if len(handlers) != 1 or handlers[0].get("type") != "command":
            raise HookConfigError("Invalid managed hook handler: %s" % event)
        try:
            arguments = shlex.split(handlers[0]["command"])
        except ValueError as error:
            raise HookConfigError("Invalid managed hook command: %s" % event) from error
        if (len(arguments) != 3 or arguments[0] != "python3"
                or Path(arguments[1]).name != RUNTIME or arguments[2] != HOOK_EVENTS[event][0]):
            raise HookConfigError("Manifest does not describe a fugue-docs hook: %s" % event)
        result[event] = group
    if not result:
        raise HookConfigError("Empty fugue-docs hook installation manifest")
    return result


def plan_hooks(directory, skill_directory, update=False):
    """Return only file changes; caller validates paths and commits transactionally."""
    hooks_path = directory / "hooks.json"
    manifest_path = directory / HOOK_MANIFEST
    document, previous_bytes = read_json(hooks_path)
    manifest, previous_manifest_bytes = read_json(manifest_path)
    if document is None and previous_bytes is not None:
        raise HookConfigError("hooks.json must be an object, not null")
    if manifest is None and previous_manifest_bytes is not None:
        raise HookConfigError("Hook installation manifest must be an object, not null")
    if document is None:
        document = {"hooks": {}}
    validate_hooks(document)
    previous = managed_entries(manifest)
    desired = managed_groups(skill_directory)
    if previous and previous != desired and not update:
        raise HookConfigError("Managed hooks differ; rerun with --update after reviewing the changes")
    events = document.setdefault("hooks", {})
    owned = {}
    for event, group in previous.items():
        matches = [index for index, candidate in enumerate(events.get(event, [])) if candidate == group]
        if len(matches) != 1:
            raise HookConfigError("Managed hook was modified, removed, or duplicated: %s" % event)
        owned[event] = matches[0]
    for event, groups in events.items():
        for index, group in enumerate(groups):
            if owned.get(event) == index:
                continue
            if any(hook.get("type") == "command" and RUNTIME in hook.get("command", "")
                   for hook in group.get("hooks", [])):
                raise HookConfigError("Unmanaged fugue-docs hook already exists in %s; reconcile it before installing" % event)
    original = json_bytes(document)
    for event, group in desired.items():
        groups = events.setdefault(event, [])
        if event in owned:
            # Keep the group index stable: Codex trust keys include list indices.
            groups[owned[event]] = group
        else:
            groups.append(group)
    changes = {}
    current = json_bytes(document)
    if previous_bytes is None or current != original:
        mode = stat.S_IMODE(hooks_path.stat().st_mode) if hooks_path.exists() else 0o644
        changes[hooks_path] = (current, mode)
    generated_manifest = {"format": 1, "skill": "fugue-docs",
                          "entries": {event: {"group": group, "sha256": group_hash(group)}
                                      for event, group in desired.items()}}
    if manifest != generated_manifest:
        mode = stat.S_IMODE(manifest_path.stat().st_mode) if manifest_path.exists() else 0o600
        changes[manifest_path] = (json_bytes(generated_manifest), mode)
    return changes
