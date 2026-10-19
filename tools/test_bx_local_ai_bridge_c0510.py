#!/usr/bin/env python3
"""C0510 llama.cpp bridge tests with synthetic, never real, model execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from bx_local_ai_bridge_c0510 import (
    make_prompt, parse_model_json, run_local_ai, verify_local_assets,
)


class TestC0510OfflineBridge(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.exe = root / "llama-cli"
        self.exe.write_text("synthetic executable for unit tests only", encoding="utf-8")
        self.exe.chmod(0o755)
        self.model = root / "sample.gguf"
        self.model.write_bytes(b"GGUF" + b"\0" * 32)
        self.sha = hashlib.sha256(self.model.read_bytes()).hexdigest()
        self.badlog = "Permission denied on /workspace/output"
        self.proposal = json.dumps({
            "category": "permission", "line": 1,
            "action_id": "inspect_permissions",
            "summary_ko": "쓰기 권한을 확인하세요."
        }, ensure_ascii=False)

    def test_assets_sha_magic_exec(self):
        meta = verify_local_assets(self.exe, self.model, self.sha)
        self.assertEqual(meta["gguf_sha256"], self.sha)

    def test_assets_bad_sha_rejected(self):
        with self.assertRaises(ValueError):
            verify_local_assets(self.exe, self.model, "0" * 64)

    def test_assets_bad_magic_rejected(self):
        self.model.write_bytes(b"FAKE" * 10)
        with self.assertRaises(ValueError):
            verify_local_assets(self.exe, self.model, hashlib.sha256(self.model.read_bytes()).hexdigest())

    def test_assets_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            verify_local_assets(Path("llama-cli"), self.model, self.sha)

    def test_assets_symlink_executable_rejected(self):
        alias = self.exe.with_name("alias")
        alias.symlink_to(self.exe)
        with self.assertRaises(ValueError):
            verify_local_assets(alias, self.model, self.sha)

    def test_assets_exe_without_execution_permission_rejected(self):
        self.exe.chmod(0o644)
        with self.assertRaises(ValueError):
            verify_local_assets(self.exe, self.model, self.sha)

    def test_no_optin_means_no_model_run(self):
        calls = []
        def impossible(*a, **kw):
            calls.append((a, kw))
            raise AssertionError("model must never start")
        r = run_local_ai(self.badlog, 1, self.exe, self.model, self.sha,
                         run_model=False, runner=impossible)
        self.assertFalse(calls)
        self.assertEqual(r["ai"]["state"], "not_run")

    def test_no_grounded_diagnostic_skips_model(self):
        r = run_local_ai("Compiling 1/2", None, self.exe, self.model, "not-a-sha",
                         run_model=True, runner=lambda *a, **k: self.fail("should skip"))
        self.assertEqual(r["ai"]["state"], "skipped_no_grounded_diagnostic")

    def test_valid_ai_inference_is_only_suggestion(self):
        observed = {}
        def fake(cmd, **kwargs):
            observed["args"] = cmd
            observed["kwargs"] = kwargs
            return SimpleNamespace(returncode=0, stdout=self.proposal)
        r = run_local_ai(self.badlog, 1, self.exe, self.model, self.sha,
                         run_model=True, runner=fake)
        self.assertEqual(r["ai"]["state"], "evidence_matched_untrusted_suggestion")
        self.assertFalse(r["gate"]["release_approved"])
        self.assertFalse(r["gate"]["stage1_pass"])
        self.assertFalse(observed["kwargs"]["shell"])
        self.assertEqual(observed["args"][0], str(self.exe))
        self.assertEqual(observed["kwargs"]["timeout"], 120)
        self.assertNotIn("bash -c", str(observed["args"]))

    def test_hallucination_is_rejected(self):
        bad = json.dumps({"category": "undefined_symbol", "line": 120,
                          "action_id": "inspect_link_inputs", "summary_ko": "가짜 오류"})
        r = run_local_ai(self.badlog, 1, self.exe, self.model, self.sha,
                         run_model=True, runner=lambda *a, **kw: SimpleNamespace(returncode=0, stdout=bad))
        self.assertEqual(r["ai"]["state"], "rejected")

    def test_nonzero_model_keeps_rule_baseline(self):
        r = run_local_ai(self.badlog, 1, self.exe, self.model, self.sha,
                         run_model=True, runner=lambda *a, **kw: SimpleNamespace(returncode=1, stdout=""))
        self.assertEqual(r["ai"]["state"], "failed_safe")
        self.assertEqual(r["evidence"][0]["category"], "permission")

    def test_timeout_keeps_rule_baseline(self):
        def timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="llama-cli", timeout=10)
        r = run_local_ai(self.badlog, 1, self.exe, self.model, self.sha,
                         run_model=True, runner=timeout)
        self.assertEqual(r["ai"]["state"], "failed_safe")
        self.assertFalse(r["gate"]["release_approved"])

    def test_invalid_json_rejected(self):
        r = run_local_ai(self.badlog, 1, self.exe, self.model, self.sha,
                         run_model=True, runner=lambda *a, **kw: SimpleNamespace(returncode=0, stdout="no json"))
        self.assertEqual(r["ai"]["state"], "rejected")

    def test_model_json_embedded_text(self):
        self.assertEqual(parse_model_json("Here is JSON:\n" + self.proposal)["category"], "permission")

    def test_model_json_rejects_commands(self):
        s = '{"category":"permission","line":1,"action_id":"inspect_permissions","summary_ko":"okay","cmd":"rm -rf /"}'
        self.assertIsNone(parse_model_json(s))

    def test_overlong_model_response_rejected(self):
        self.assertIsNone(parse_model_json("x" * 40000))

    def test_reject_unbounded_inference_timeout(self):
        with self.assertRaises(ValueError):
            run_local_ai(self.badlog, 1, self.exe, self.model, self.sha,
                         run_model=True, timeout_seconds=9999)

    def test_prompt_uses_only_sanitized_evidence(self):
        from bx_ai_log_triage_c0510 import parse_log
        secret = "ghp_" + "Q" * 35
        r = parse_log("private non-error line " + secret +
                      "\nPermission denied; access token=" + secret, exit_code=1)
        prompt = make_prompt(r)
        self.assertNotIn(secret, prompt)
        self.assertNotIn("private non-error", prompt)
        self.assertIn("[REDACTED]", prompt)
        self.assertIn("신뢰할 수 없는 데이터", prompt)


if __name__ == "__main__":
    unittest.main()
