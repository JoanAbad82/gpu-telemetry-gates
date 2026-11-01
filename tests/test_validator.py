"""Exclusively synthetic tests. Nothing accesses a GPU or physical sensor."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gpu_telemetry_gates import GateError, evaluate
from generate_fixtures import expected_files, fixture


class PolicyTests(unittest.TestCase):
    def test_baseline_pass_unknown_pid_not_an_absence_claim(self):
        result = evaluate(fixture("baseline"))
        self.assertEqual(result["gate"], "PASS")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["checked_samples"], 20)

    def test_session_pass(self):
        self.assertEqual(evaluate(fixture("session"))["gate"], "PASS")

    def test_baseline_excess_utilization_fails(self):
        self.assertEqual(evaluate(fixture("baseline", fail=True))["reasons"], ["BASELINE_UTILIZATION"])

    def test_session_overheat_fails(self):
        self.assertEqual(evaluate(fixture("session", fail=True))["reasons"], ["SESSION_TEMPERATURE"])

    def test_known_nonstudy_compute_fails(self):
        doc = fixture("baseline")
        doc["process_inventory"]["entries"] = [{"classification": "KNOWN_NONSTUDY_COMPUTE"}]
        self.assertEqual(evaluate(doc)["reasons"], ["KNOWN_EXTERNAL_COMPUTE"])

    def test_unproven_workload_not_falsely_classified_as_compute(self):
        doc = fixture("baseline")
        doc["process_inventory"]["entries"] = [{"classification": "IDENTIFIED_WORKLOAD_UNPROVEN"}]
        self.assertEqual(evaluate(doc)["gate"], "PASS")

    def test_failed_or_missing_inventory_fails_closed(self):
        for replacement in (None, False):
            doc = fixture("baseline")
            doc["process_inventory"]["capture_ok"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(GateError):
                evaluate(doc)

    def test_bad_process_state_fails_closed(self):
        doc = fixture("baseline")
        doc["process_inventory"]["entries"][0]["classification"] = "NO_EXTERNAL_JOBS_PROVEN"
        with self.assertRaises(GateError):
            evaluate(doc)

    def test_short_baseline_fails(self):
        doc = fixture("baseline")
        doc["samples"].pop()
        self.assertIn("BASELINE_SAMPLE_COUNT", evaluate(doc)["reasons"])

    def test_timing_gap_fails(self):
        doc = fixture("session")
        doc["samples"][2]["started_ms"] = 551
        self.assertIn("SAMPLE_GAP", evaluate(doc)["reasons"])

    def test_nonincreasing_timestamps_fail(self):
        doc = fixture("baseline")
        doc["samples"][3]["started_ms"] = doc["samples"][2]["started_ms"]
        self.assertIn("SAMPLE_GAP", evaluate(doc)["reasons"])

    def test_query_failure_fails(self):
        doc = fixture("session")
        doc["samples"][1]["exit_code"] = 1
        self.assertIn("SENSOR_QUERY_FAILED", evaluate(doc)["reasons"])

    def test_memory_range_fails(self):
        doc = fixture("baseline")
        doc["samples"][5]["used_mib"] = 700
        self.assertIn("BASELINE_MEMORY_RANGE", evaluate(doc)["reasons"])

    def test_baseline_limits_all_samples(self):
        doc = fixture("baseline")
        doc["samples"][19]["temperature_c"] = 66
        doc["samples"][19]["free_mib"] = 8100
        self.assertEqual(evaluate(doc)["reasons"], ["BASELINE_FREE_MEMORY", "BASELINE_TEMPERATURE"])

    def test_runtime_memory_and_clock(self):
        doc = fixture("session")
        doc["samples"][1]["free_mib"] = -1
        doc["samples"][1]["sm_clock_mhz"] = 199
        self.assertEqual(evaluate(doc)["reasons"], ["SESSION_FREE_MEMORY", "SM_CLOCK"])

    def test_runtime_utilization_not_external_load(self):
        doc = fixture("session")
        doc["samples"][1]["utilization_pct"] = 100
        self.assertEqual(evaluate(doc)["gate"], "PASS")

    def test_impossible_sensor_values_fail(self):
        doc = fixture("session")
        doc["samples"][1]["utilization_pct"] = -5
        doc["samples"][1]["used_mib"] = -1
        doc["samples"][1]["temperature_c"] = -300
        self.assertEqual(evaluate(doc)["reasons"], [
            "SENSOR_TEMPERATURE_RANGE", "SENSOR_USED_MEMORY_NEGATIVE",
            "SENSOR_UTILIZATION_RANGE",
        ])

    def test_json_nan_and_boolean_are_rejected(self):
        for value in (float("nan"), True, "42"):
            doc = fixture("session")
            doc["samples"][0]["used_mib"] = value
            with self.subTest(value=value), self.assertRaises(GateError):
                evaluate(doc)

    def test_unknown_fields_rejected(self):
        doc = fixture("baseline")
        doc["host_name"] = "untrusted"
        with self.assertRaises(GateError):
            evaluate(doc)

    def test_order_of_reasons_deterministic(self):
        doc = fixture("baseline", fail=True)
        doc["samples"][0]["exit_code"] = 1
        self.assertEqual(evaluate(doc), evaluate(copy.deepcopy(doc)))
        self.assertEqual(evaluate(doc)["reasons"], ["BASELINE_UTILIZATION", "SENSOR_QUERY_FAILED"])

    def test_byte_exact_fixture_reproduction(self):
        for name, expected in expected_files().items():
            with self.subTest(name=name):
                self.assertEqual((ROOT / "fixtures" / name).read_bytes(), expected)
                actual = json.loads(expected)
                self.assertEqual(evaluate(actual)["gate"], "FAIL" if "-fail" in name else "PASS")

    def test_cli_pass_fail_and_bad_input_exit_codes(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
        for filename, code in (
            ("baseline-pass.json", 0),
            ("baseline-fail.json", 1),
            ("session-pass.json", 0),
            ("session-fail.json", 1),
        ):
            with self.subTest(file=filename):
                p = subprocess.run(
                    [sys.executable, "-m", "gpu_telemetry_gates", str(ROOT / "fixtures" / filename)],
                    env=env, text=True, capture_output=True, check=False, timeout=10,
                )
                self.assertEqual(p.returncode, code, p.stderr)
                self.assertEqual(json.loads(p.stdout)["gate"], "PASS" if code == 0 else "FAIL")
        p = subprocess.run(
            [sys.executable, "-m", "gpu_telemetry_gates", str(ROOT / "fixtures" / "missing.json")],
            env=env, text=True, capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stderr)["gate"], "ERROR")


if __name__ == "__main__":
    unittest.main()
