#!/usr/bin/env python3
"""
[INPUT]: 依赖 json, os, shlex, sys, geb_hook, geb_codex_hook
[OUTPUT]: 提供 Devin 生命周期与工具事件适配,隔离会话并复用共享维护回环
[POS]: fugue-docs 工具层-Devin 原生 hook 协议适配
[PROTOCOL]: 修改时同步 evals/test_devin_hooks.py、scripts/FOLDER_INDEX.md 与 references/devin.md
"""

import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geb_hook as engine  # noqa: E402
from geb_codex_hook import patch_paths  # noqa: E402


def normalize_payload(payload):
    raw = payload.get("session_id")
    if not isinstance(raw, str) or not raw.strip():
        return None
    result = dict(payload)
    result.update(fugue_agent="devin", fugue_session_id=raw, session_id="devin-" + raw)
    return result


def tool_name(payload):
    name = payload.get("tool_name")
    return name[len("functions."):] if isinstance(name, str) and name.startswith("functions.") else name


def mapped_path(tool_input):
    if not isinstance(tool_input, dict):
        return None
    return next((tool_input.get(key) for key in ("file_path", "path", "target_file", "notebook_path", "file")
                 if isinstance(tool_input.get(key), str) and tool_input.get(key)), None)


def file_payload(payload, name):
    path = mapped_path(payload.get("tool_input"))
    if not path:
        return None
    return dict(payload, tool_name=name, tool_input={"file_path": path})


def exec_payload(payload):
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command", tool_input.get("cmd"))
    if isinstance(command, list) and all(isinstance(part, str) for part in command):
        command = shlex.join(command)
    if not isinstance(command, str):
        return None
    return dict(payload, tool_name="Bash", tool_input={"command": command})


def pre_tool(payload):
    name = tool_name(payload)
    if name in ("edit", "write", "notebook_edit"):
        mapped = file_payload(payload, {"edit": "Edit", "write": "Write", "notebook_edit": "NotebookEdit"}[name])
        if mapped:
            engine.pre_tool(mapped)
    elif name == "apply_patch":
        session_id, root, _state = engine.adopted(payload)
        if not session_id:
            return None
        records, seen = [], set()
        for path in patch_paths(payload.get("tool_input")):
            rel = engine.tool_rel(root, payload, path)
            if rel and rel not in seen and engine.relevant_code(rel) and engine.inside(root, rel):
                records.append(engine.pre_record(root, rel))
                seen.add(rel)
        engine.append_log(session_id, records, root)
    elif name == "exec":
        mapped = exec_payload(payload)
        if mapped:
            engine.pre_tool(mapped)
    return None


def post_tool(payload):
    if tool_name(payload) == "exec":
        mapped = exec_payload(payload)
        if mapped:
            engine.post_tool(mapped)
    return None


def session_start(payload):
    return engine.session_start(payload)


def prompt(payload):
    return engine.prompt(payload)


def stop(payload):
    return engine.stop(payload)


def session_end(payload):
    return engine.session_end(payload)


HANDLERS = {"session-start": session_start, "prompt": prompt, "pre-tool": pre_tool,
            "post-tool": post_tool, "stop": stop, "session-end": session_end}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in HANDLERS:
        return 0
    os.environ["FUGUE_HOOK_AGENT"] = "devin"
    event = argv[0]
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        payload = normalize_payload(payload)
        if payload is None:
            return 0
        output = HANDLERS[event](payload)
        if output:
            sys.stdout.write(json.dumps(output, ensure_ascii=True))
    except Exception as error:  # noqa: BLE001
        engine.log_error("devin:" + event, error)
    return 0


if __name__ == "__main__":
    sys.exit(main())
