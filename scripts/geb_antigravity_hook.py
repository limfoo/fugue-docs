#!/usr/bin/env python3
"""
[INPUT]: 依赖 json, os, sys, geb_hook
[OUTPUT]: 提供 Antigravity 生命周期与工具事件适配,隔离会话并复用共享维护回环
[POS]: fugue-docs 工具层-Antigravity 原生 hook 协议适配(跨 Windows/macOS/Linux)
[PROTOCOL]: 变更时同步 evals/test_antigravity_hooks.py、scripts/FOLDER_INDEX.md、hooks.json 与 references/antigravity.md
"""

import os
import sys

if sys.version_info < (3, 9):
    os.execvp("python3", ["python3"] + sys.argv)

import json  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geb_hook as engine  # noqa: E402

FILE_WRITE_TOOLS = {
    "write_file",
    "edit_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
}
COMMAND_TOOLS = {"run_command"}
PATH_KEYS = ("Path", "TargetFile", "file_path", "path", "AbsolutePath")


def normalize_payload(raw):
    """将 Antigravity camelCase payload 归一化为 geb_hook 引擎格式。"""
    conv_id = raw.get("conversationId")
    if not isinstance(conv_id, str) or not conv_id.strip():
        return None

    workspaces = raw.get("workspacePaths")
    cwd = raw.get("cwd")
    if not cwd and isinstance(workspaces, list) and workspaces:
        cwd = workspaces[0]

    result = {
        "session_id": "antigravity-" + conv_id,
        "fugue_agent": "antigravity",
        "fugue_session_id": conv_id,
        "cwd": cwd,
        "workspace_paths": workspaces if isinstance(workspaces, list) else [],
        "transcript_path": raw.get("transcriptPath"),
        "stop_hook_active": bool(raw.get("continuationActive", False)),
        "termination_reason": raw.get("terminationReason", ""),
        "invocation_num": raw.get("invocationNum"),
        "tool_error": raw.get("error"),
    }

    tool_call = raw.get("toolCall")
    if isinstance(tool_call, dict):
        result["tool_use_id"] = tool_call.get("id")
        result["tool_name"] = tool_call.get("name")
        result["tool_input"] = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
    return result


def extract_file_path(tool_input):
    if not isinstance(tool_input, dict):
        return None
    for key in PATH_KEYS:
        val = tool_input.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def snapshot_path(session_id):
    return engine.session_file(session_id, ".agy-turn-snap.json")


def session_start(payload):
    """翻译 SessionStart 输出为 Antigravity injectSteps 契约。"""
    out = engine.session_start(payload)
    if not out:
        return {}
    hint = (out.get("hookSpecificOutput") or {}).get("additionalContext")
    if not hint:
        return {}
    return {
        "injectSteps": [
            {
                "systemMessage": {
                    "systemMessage": hint
                }
            }
        ]
    }


def pre_invocation(payload):
    """
    每次模型调用前执行:
    1) 在新回合首次调用时清理外部改动(替代 UserPromptSubmit);
    2) 记录工作区快照,供 PostToolUse 在零权限侵入的前提下归属改动。
    """
    session_id, root, state = engine.adopted(payload)
    if not session_id:
        return {}
    if payload.get("invocation_num") in (None, 1) and state is not None:
        engine.prompt(payload)
    snap = engine.bash_snapshot(root, session_id)
    engine.write_json(snapshot_path(session_id), {"root": root, "snapshot": snap})
    return {}


def infer_pre_record(root, rel, snap):
    """基于 PreInvocation 快照还原文件改前视图与存在状态。"""
    if snap and snap.get("kind") == "git":
        prev = (snap.get("dirty") or {}).get(rel)
        if prev is not None:
            return {k: prev.get(k) for k in ("sha", "exists", "exports", "output_line")}
        base = engine.tracked_view(root, snap.get("head"), rel)
        return {
            "sha": None,
            "exists": base is not None,
            "tracked_clean": base is not None,
            "exports": (base or {}).get("exports"),
            "output_line": (base or {}).get("output_line"),
        }
    if snap and snap.get("kind") == "mtime":
        existed = rel in set(snap.get("files") or ())
        return {"sha": None, "exists": existed}
    return {"sha": None, "exists": True}


def post_tool(payload):
    """零权限侵入的工具改动归属(PostToolUse 契约仅要求返回 {})。"""
    session_id, root, _state = engine.adopted(payload)
    if not session_id:
        return {}

    name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    snap_file = snapshot_path(session_id)
    saved = engine.read_json(snap_file) or {}
    snap = saved.get("snapshot") if saved.get("root") == root else None

    if name in FILE_WRITE_TOOLS:
        path = extract_file_path(tool_input)
        rel = engine.tool_rel(root, payload, path)
        if rel and engine.relevant_code(rel) and engine.inside(root, rel):
            pre = infer_pre_record(root, rel, snap)
            engine.append_log(session_id, [{"rel": rel, "pre": pre}], root)
    elif name in COMMAND_TOOLS:
        command = str(tool_input.get("CommandLine") or tool_input.get("command") or "")
        if snap and not engine.GIT_WORKTREE.search(command):
            records = engine.bash_records(session_id, root, snap)
            engine.append_log(session_id, records, root)

    new_snap = engine.bash_snapshot(root, session_id)
    engine.write_json(snap_file, {"root": root, "snapshot": new_snap})
    return {}


def stop(payload):
    """
    翻译 Stop 契约:
    - 仅在正常完成回合(NO_TOOL_CALL)时允许拦截并触发补写语义;
    - geb_hook 的 decision="block" 必须翻译为 Antigravity 的 decision="continue"。
    """
    reason_code = payload.get("termination_reason") or "NO_TOOL_CALL"
    if reason_code != "NO_TOOL_CALL":
        payload = dict(payload, stop_hook_active=True)

    out = engine.stop(payload)
    session_id = engine.safe_id(payload.get("session_id"))
    if session_id:
        try:
            os.remove(snapshot_path(session_id))
        except OSError:
            pass

    if not out:
        return {}
    if out.get("decision") == "block" and out.get("reason"):
        return {
            "decision": "continue",
            "reason": out["reason"],
        }
    return {}


HANDLERS = {
    "session-start": session_start,
    "pre-invocation": pre_invocation,
    "post-tool": post_tool,
    "stop": stop,
}


def read_stdin_json():
    """显式以 UTF-8 解码 stdin,避免 Windows 控制台默认 GBK 编码解析失败。"""
    raw_bytes = sys.stdin.buffer.read()
    if not raw_bytes or not raw_bytes.strip():
        return None
    return json.loads(raw_bytes.decode("utf-8", "replace"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    os.environ["FUGUE_HOOK_AGENT"] = "antigravity"
    if len(argv) != 1 or argv[0] not in HANDLERS:
        sys.stdout.write("{}")
        return 0
    event = argv[0]
    try:
        raw = read_stdin_json()
        payload = normalize_payload(raw) if isinstance(raw, dict) else None
        output = HANDLERS[event](payload) if payload is not None else {}
        sys.stdout.write(json.dumps(output or {}, ensure_ascii=True))
    except Exception as error:  # noqa: BLE001
        engine.log_error("antigravity:" + event, error)
        sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
