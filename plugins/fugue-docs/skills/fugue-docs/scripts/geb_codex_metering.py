#!/usr/bin/env python3
"""
[INPUT]: 依赖 os, uuid, geb_metrics, geb_telemetry
[OUTPUT]: 提供 Codex hook 自动计量:校验会话身份、记录实际遥测区间、缺失与轮换保留未知
[POS]: fugue-docs 工具层-Codex 自动回环的会话账本桥接,不读取 Claude 用量
[PROTOCOL]: 变更时更新上级 FOLDER_INDEX.md、Codex hook 计量测试与计量说明
"""

import os
import uuid

from geb_metrics import now, save_json, usage_delta
from geb_telemetry import COUNTERS, observe


def observation(state, payload):
    """Only bind the thread that emitted this hook; never use a neighbouring session."""
    expected = state.get("fugue_session_id") or payload.get("fugue_session_id")
    if not expected:
        return {"status": "missing_session_id"}, None
    path = payload.get("transcript_path") or state.get("transcript_path")
    binding, snapshot = observe(session=path, session_id=expected)
    identity = (snapshot or {}).get("session_id") or binding.get("session_id")
    if identity and identity != expected:
        return {"status": "session_mismatch", "session_id": expected}, None
    return binding, snapshot


def initialize_metering(state, payload):
    binding, snapshot = observation(state, payload)
    # A verified, new startup transcript without any token event represents the
    # pre-model boundary. Missing/unreadable logs and resumes are not zero usage.
    if (snapshot is None and binding.get("status") == "no_token_events"
            and state.get("coverage_start") == "session_start"
            and payload.get("source") == "startup" and payload.get("model")):
        snapshot = {"session_id": state["fugue_session_id"], "source": binding["path"],
                    "model": payload["model"], "model_epoch": 0, "settings_epoch": 0,
                    "counter_epoch": 0, "timestamp": now(),
                    "usage": {key: 0 for key in COUNTERS}}
    state["codex_usage_start"] = snapshot
    state["codex_start_binding"] = binding
    state["codex_coverage"] = "session_start" if snapshot else "awaiting_first_measurement"


def record_metering(state, payload, event, directory):
    """Rewrite one cumulative session record: repeated Stop/SessionEnd never double-count."""
    binding, end = observation(state, payload)
    start = state.get("codex_usage_start")
    usage, status = usage_delta(start, end)
    if end is None:
        status = binding.get("status", "missing_measurements")
    elif start is None:
        # Start a bounded interval when telemetry becomes available mid-session.
        # The earlier portion stays explicitly excluded rather than guessed.
        state["codex_usage_start"] = end
        state["codex_coverage"] = "first_available_measurement"
        status = "awaiting_next_measurement"
    if usage is not None:
        if usage["total_tokens"] == 0:
            usage, status = None, "no_new_telemetry"
        else:
            usage["uncached_plus_output"] = usage["uncached_input_tokens"] + usage["output_tokens"]
    raw_id = state.get("fugue_session_id")
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "fugue-codex-session:" + str(raw_id)))
    record = {"schema": "geb.metrics.v2", "run_id": run_id, "agent": "codex",
              "task": "codex-session", "condition": "fugue", "root": state["root"],
              "session_id": raw_id, "started_at": state["started_at"], "updated_at": now(),
              "git": state.get("git_state"), "last_event": event, "status": status,
              "start": state.get("codex_usage_start"), "end": end, "binding": binding,
              "measurement_ready": end is not None, "usage": usage,
              "saved_tokens": None, "saving_status": "no_comparable_baseline",
              "source": "codex_local_telemetry", "coverage_start": state.get("codex_coverage"),
              "coverage": "Bound local token-count interval; excludes later messages and separate subagent sessions; missing or rotated telemetry is unknown",
              "maintenance": {key: state.get(key, 0) for key in
                              ("stops", "blocks", "block_chars", "auto_writes", "skipped_turns")}}
    save_json(os.path.join(directory, "metrics", run_id + ".json"), record)
