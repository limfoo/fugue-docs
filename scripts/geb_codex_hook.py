#!/usr/bin/env python3
"""
[INPUT]: 依赖 hashlib, json, os, re, shlex, sys, geb_hook
[OUTPUT]: 提供 Codex 原生主/子会话、工具、Stop 与中断钩子,精确登记 apply_patch 并复用共享维护回环
[POS]: fugue-docs 工具层-Codex hook 协议适配,隔离会话身份并承接异步 shell 生命周期
[PROTOCOL]: 修改时同步 evals/test_codex_hooks.py、scripts/FOLDER_INDEX.md 与 references/codex.md

Codex 原生 shell 工具序列化为 Bash;exec_command 尚在运行时不发 PostToolUse,
write_stdin 使原进程结束后才以原 tool_use_id 发送 PostToolUse。因此原生异步
命令直接复用共享引擎的 Pre/完成 Post 快照,失败或中断的命令在 Stop 补记。
原生 apply_patch 使用 {"command": "*** Begin Patch..."},Write/Edit 只是 matcher
别名。额外接受显式 exec_command/shell/write_stdin 名称,用于直接转发工具事件的宿主。
任何异常都放行,Interrupt/SessionEnd 只补记计量,不触发文件维护或阻止中断。
"""

import hashlib
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geb_hook as engine  # noqa: E402

SHELL_TOOLS = ("Bash", "exec_command", "shell", "shell_command", "local_shell")
PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$")


def normalize_payload(payload):
    """保留 Codex thread ID 作计量身份;只给维护状态添加平台命名空间。"""
    raw = payload.get("session_id")
    if not isinstance(raw, str) or not raw.strip():
        return None
    result = dict(payload)
    result.update(fugue_agent="codex", fugue_session_id=raw, session_id="codex-" + raw)
    return result


def tool_name(payload):
    name = payload.get("tool_name")
    if isinstance(name, str) and name.startswith("functions."):
        return name[len("functions."):]
    return name


def patch_paths(tool_input):
    """只解析 patch 的结构行,不从新增/删除代码正文猜路径。"""
    if isinstance(tool_input, str):
        patch = tool_input
    elif isinstance(tool_input, dict):
        patch = next((tool_input[k] for k in ("command", "patch", "input")
                      if isinstance(tool_input.get(k), str)), "")
    else:
        return []
    lines = patch.strip().splitlines()
    if not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        return []
    paths = []
    for line in lines[1:-1]:
        match = PATCH_PATH.match(line)
        if match and match.group(1) not in paths:
            paths.append(match.group(1))
    return paths


def shell_payload(payload):
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command", tool_input.get("cmd"))
    if isinstance(command, list) and all(isinstance(part, str) for part in command):
        command = shlex.join(command)
    if not isinstance(command, str):
        return None
    return dict(payload, tool_name="Bash", tool_input={"command": command})


def process_id(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value):
        return None
    return str(value)


def process_path(session_id, process):
    digest = hashlib.sha256(process.encode("utf-8")).hexdigest()[:24]
    return engine.session_file(session_id, ".codex-process-" + digest + ".json")


def response_object(payload):
    response = payload.get("tool_response")
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return {}
    return response if isinstance(response, dict) else {}


def running_process(payload):
    response = response_object(payload)
    if response.get("exit_code") is not None:
        return None
    return process_id(response.get("process_id", response.get("session_id")))


def pre_tool(payload):
    name = tool_name(payload)
    if name == "apply_patch":
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
    elif name in SHELL_TOOLS:
        mapped = shell_payload(payload)
        if mapped:
            engine.pre_tool(mapped)
    # 原生 write_stdin 无独立 Pre;兼容事件继续沿用 exec_command 的原快照。
    return None


def post_tool(payload):
    name = tool_name(payload)
    if name in SHELL_TOOLS:
        mapped = shell_payload(payload)
        if not mapped:
            return None
        session_id, root, _state = engine.adopted(mapped)
        if not session_id:
            return None
        process = running_process(payload)
        snapshot_path = engine.bash_key(session_id, mapped)
        if process is not None and os.path.isfile(snapshot_path):
            # 显式 exec_command 兼容事件可在进程结束前发 Post;不要过早清掉快照。
            engine.write_json(process_path(session_id, process),
                              {"root": root, "bash_path": snapshot_path,
                               "excluded": not (engine.read_json(snapshot_path) or {}).get("snapshot")})
        else:
            engine.post_tool(mapped)
    elif name == "write_stdin":
        session_id, root, _state = engine.adopted(payload)
        tool_input = payload.get("tool_input") or {}
        process = process_id(tool_input.get("session_id")) if isinstance(tool_input, dict) else None
        if not session_id or process is None:
            return None
        path = process_path(session_id, process)
        saved = engine.read_json(path)
        if not saved or saved.get("root") != root or running_process(payload) is not None:
            return None
        engine.flush_bash(session_id, root, saved["bash_path"])
        os.remove(path)
    return None


def process_records(session_id, root):
    directory = os.path.dirname(engine.session_file(session_id, ".json"))
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    records = []
    for name in names:
        if name.startswith(session_id + ".codex-process-") and name.endswith(".json"):
            saved = engine.read_json(os.path.join(directory, name))
            if saved and saved.get("root") == root:
                records.append(saved)
    return records


def stop(payload):
    session_id, root, _state = engine.adopted(payload)
    if not session_id:
        return None
    active = process_records(session_id, root)
    # 先由共享引擎补记未完成工具,再同步、去重缺口并记录用量。
    output = engine.stop(payload)
    for saved in active:
        # 显式进程事件有稳定句柄,允许下一轮继续跟踪后台进程;刷新点在自动维护之后。
        previous = engine.read_json(saved["bash_path"])
        if previous is None:
            snapshot = None if saved.get("excluded") else engine.bash_snapshot(root, session_id)
            engine.write_json(saved["bash_path"], {"snapshot": snapshot})
    return output


def subagent_start(payload):
    """子线程可能继承历史;公开事件不区分新建和 fork,不假定零用量。"""
    output = engine.session_start(dict(payload, source="fork"))
    if output:
        output["hookSpecificOutput"]["hookEventName"] = "SubagentStart"
    return output


def subagent_stop(payload):
    """官方 transcript_path 在此事件指向父线程;计量只能使用子线程日志。"""
    return stop(dict(payload, transcript_path=payload.get("agent_transcript_path")))


HANDLERS = {"session-start": engine.session_start, "prompt": engine.prompt, "pre-tool": pre_tool,
            "post-tool": post_tool, "stop": stop, "session-end": engine.session_end,
            "interrupt": engine.session_end, "subagent-start": subagent_start, "subagent-stop": subagent_stop}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    os.environ["FUGUE_HOOK_AGENT"] = "codex"
    if len(argv) != 1 or argv[0] not in HANDLERS:
        return 0
    try:
        payload = json.load(sys.stdin)
        payload = normalize_payload(payload) if isinstance(payload, dict) else None
        if payload is not None:
            output = HANDLERS[argv[0]](payload)
            if output:
                sys.stdout.write(json.dumps(output, ensure_ascii=True))
    except Exception as error:  # noqa: BLE001
        engine.log_error("codex:" + argv[0], error)
    return 0


if __name__ == "__main__":
    sys.exit(main())
