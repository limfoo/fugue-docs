#!/usr/bin/env python3
"""
[INPUT]: 依赖 json, pathlib, sys, tempfile, unittest, uuid, geb_codex_metering, geb_metrics
[OUTPUT]: 提供 Codex hook 计量回归:真实区间、身份绑定、未知遥测、恢复会话和防重复累计
[POS]: fugue-docs 评测包-Codex 自动回环账本的可信度验证
[PROTOCOL]: 变更时同步 evals/FOLDER_INDEX.md 并运行 unittest discovery
"""

import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import geb_codex_metering as metering
import geb_metrics


class CodexMeteringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fugue-codex-metering-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.transcript = self.root / "session.jsonl"
        self.session = str(uuid.uuid4())
        self.payload = {"fugue_agent": "codex", "fugue_session_id": self.session,
                        "session_id": "codex-" + self.session, "cwd": str(self.root),
                        "transcript_path": str(self.transcript), "model": "test-model",
                        "source": "startup"}
        self.state = {"root": str(self.root), "fugue_agent": "codex",
                      "fugue_session_id": self.session, "session_id": "codex-" + self.session,
                      "transcript_path": str(self.transcript), "started_at": geb_metrics.now(),
                      "coverage_start": "session_start", "stops": 1, "blocks": 0}

    def append(self, event):
        with self.transcript.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")

    def metadata(self, session=None):
        self.append({"type": "session_meta", "payload": {"id": session or self.session,
                                                          "cwd": str(self.root)}})
        self.append({"type": "turn_context", "payload": {"model": "test-model", "effort": "medium"}})

    def usage(self, inputs, outputs, cached=0, stamp="end", model=None):
        if model:
            self.append({"type": "turn_context", "payload": {"model": model, "effort": "medium"}})
        self.append({"type": "event_msg", "timestamp": stamp,
                     "payload": {"type": "token_count", "info": {"total_token_usage": {
                         "input_tokens": inputs, "cached_input_tokens": cached,
                         "output_tokens": outputs, "total_tokens": inputs + outputs}}}})

    def record(self, event="stop"):
        metering.record_metering(self.state, self.payload, event, str(self.root))
        paths = list((self.root / "metrics").glob("*.json"))
        self.assertEqual(1, len(paths))
        return json.loads(paths[0].read_text())

    def test_verified_startup_counts_first_turn_and_repeated_hooks_do_not_double_count(self):
        self.metadata()
        metering.initialize_metering(self.state, self.payload)
        self.usage(100, 20, cached=30)
        record = self.record()
        self.assertEqual("measured_interval", record["status"])
        self.assertEqual(120, record["usage"]["total_tokens"])
        self.assertEqual(90, record["usage"]["uncached_plus_output"])
        self.assertEqual("codex", record["agent"])
        self.assertEqual(self.session, record["session_id"])
        self.assertIsNone(record["saved_tokens"])
        self.assertEqual(record["usage"], self.record("session_end")["usage"])
        summary = geb_metrics.summarize(self.root / "metrics")
        self.assertEqual(1, summary["runs"])
        self.assertEqual(120, summary["actual_total_tokens"])

    def test_resumed_session_records_only_the_observed_interval(self):
        self.metadata()
        self.usage(1000, 200, cached=100, stamp="before")
        self.payload["source"] = "resume"
        metering.initialize_metering(self.state, self.payload)
        self.usage(1200, 230, cached=150)
        record = self.record()
        self.assertEqual(230, record["usage"]["total_tokens"])

    def test_missing_transcript_is_unknown_and_does_not_create_zero_baseline(self):
        metering.initialize_metering(self.state, self.payload)
        self.assertIsNone(self.state["codex_usage_start"])
        record = self.record()
        self.assertEqual("explicit_source_unavailable", record["status"])
        self.assertIsNone(record["usage"])
        self.metadata()
        self.usage(100, 20, stamp="first")
        record = self.record()
        self.assertEqual("awaiting_next_measurement", record["status"])
        self.assertIsNone(record["usage"])
        self.usage(140, 30, stamp="second")
        record = self.record()
        self.assertEqual(50, record["usage"]["total_tokens"])
        self.assertEqual("first_available_measurement", record["coverage_start"])

    def test_explicit_transcript_of_other_session_is_rejected(self):
        self.metadata(session=str(uuid.uuid4()))
        self.usage(100, 20)
        metering.initialize_metering(self.state, self.payload)
        record = self.record()
        self.assertEqual("session_mismatch", record["status"])
        self.assertIsNone(record["usage"])
        self.assertIsNone(record["start"])

    def test_no_new_events_are_unknown_not_zero(self):
        self.metadata()
        self.usage(100, 20)
        metering.initialize_metering(self.state, self.payload)
        record = self.record()
        self.assertEqual("no_new_telemetry", record["status"])
        self.assertIsNone(record["usage"])

    def test_counter_reset_and_model_change_do_not_produce_false_savings(self):
        for reset in (True, False):
            with self.subTest(reset=reset):
                self.transcript.write_text("")
                self.metadata()
                self.usage(100, 20, stamp="before")
                metering.initialize_metering(self.state, self.payload)
                self.usage(10 if reset else 150, 3 if reset else 30,
                           model=None if reset else "another-model")
                record = self.record()
                self.assertIsNone(record["usage"])
                self.assertIn(record["status"], ("counter_reset", "model_changed_or_unknown"))
                self.assertIsNone(record["saved_tokens"])

    def test_source_rotation_keeps_interval_unknown(self):
        self.metadata()
        self.usage(100, 20, stamp="before")
        metering.initialize_metering(self.state, self.payload)
        first = self.transcript
        self.transcript = self.root / "session-next-page.jsonl"
        self.metadata()
        self.usage(140, 30)
        self.payload["transcript_path"] = str(self.transcript)
        self.assertTrue(first.exists())
        record = self.record()
        self.assertEqual("source_rotated_unverified", record["status"])
        self.assertIsNone(record["usage"])

    def test_missing_session_id_never_falls_back_to_environment_thread(self):
        self.state["fugue_session_id"] = None
        self.payload["fugue_session_id"] = None
        self.metadata()
        self.usage(100, 20)
        binding, snapshot = metering.observation(self.state, self.payload)
        self.assertEqual("missing_session_id", binding["status"])
        self.assertIsNone(snapshot)


if __name__ == "__main__":
    unittest.main()
