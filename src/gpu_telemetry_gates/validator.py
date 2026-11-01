"""Pure offline, deterministic evaluation of *synthetic or normalized* telemetry.

This module never acquires readings, spawns processes, or imports a GPU package.
An upstream producer must establish the trustworthiness of process classifications.
"""
from __future__ import annotations

import math
from typing import Any

SCHEMA = "gpu-telemetry-gates/v1"
VERDICT_SCHEMA = "gpu-telemetry-gates/verdict-v1"
MAX_GAP_MS = 300
BASELINE_COUNT = 20
PROCESS_CLASSES = frozenset({
    "UNKNOWN", "IDENTIFIED_WORKLOAD_UNPROVEN",
    "KNOWN_NONSTUDY_COMPUTE", "STUDY",
})
SAMPLE_FIELDS = frozenset({
    "started_ms", "exit_code", "temperature_c", "utilization_pct",
    "used_mib", "free_mib", "sm_clock_mhz",
})


class GateError(ValueError):
    """Input does not conform to the public fixture schema; fail closed."""


def _exact_keys(value: Any, required: set[str], where: str) -> dict:
    if not isinstance(value, dict) or set(value) != required:
        raise GateError(f"{where}: expected fields {sorted(required)}")
    return value


def _numeric(value: Any, where: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise GateError(f"{where}: finite number required")
    return float(value)


def _samples(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        raise GateError("samples: expected array")
    samples = []
    for i, item in enumerate(raw):
        s = _exact_keys(item, set(SAMPLE_FIELDS), f"samples[{i}]")
        for field in SAMPLE_FIELDS - {"exit_code"}:
            _numeric(s[field], f"samples[{i}].{field}")
        if type(s["exit_code"]) is not int:
            raise GateError(f"samples[{i}].exit_code: integer required")
        samples.append(s)
    return samples


def _inventory(value: Any) -> list[str]:
    inv = _exact_keys(value, {"capture_ok", "entries"}, "process_inventory")
    if type(inv["capture_ok"]) is not bool or not inv["capture_ok"]:
        raise GateError("process_inventory.capture_ok: true required")
    if not isinstance(inv["entries"], list):
        raise GateError("process_inventory.entries: array required")
    states = []
    for i, item in enumerate(inv["entries"]):
        row = _exact_keys(item, {"classification"}, f"process_inventory.entries[{i}]")
        if type(row["classification"]) is not str or row["classification"] not in PROCESS_CLASSES:
            raise GateError(f"process_inventory.entries[{i}]: unsupported classification")
        states.append(row["classification"])
    return states


def evaluate(document: Any) -> dict:
    """Return deterministic PASS/FAIL; raise GateError on malformed input.

    PASS is a telemetry-policy result, NOT scientific/executive authorization,
    evidence that physical readings are authentic, or proof of GPU isolation.
    """
    if not isinstance(document, dict):
        raise GateError("root: object required")
    kind = document.get("kind")
    if kind not in ("baseline", "session"):
        raise GateError("kind: expected baseline or session")
    keys = {"schema", "kind", "samples", "process_inventory"} if kind == "baseline" else {
        "schema", "kind", "samples"
    }
    _exact_keys(document, keys, "root")
    if document["schema"] != SCHEMA:
        raise GateError("schema: unsupported")
    samples = _samples(document["samples"])
    states = _inventory(document["process_inventory"]) if kind == "baseline" else []
    errors: set[str] = set()
    if kind == "baseline" and len(samples) != BASELINE_COUNT:
        errors.add("BASELINE_SAMPLE_COUNT")
    if kind == "session" and len(samples) < 2:
        errors.add("SESSION_SAMPLE_COUNT")
    if "KNOWN_NONSTUDY_COMPUTE" in states:
        errors.add("KNOWN_EXTERNAL_COMPUTE")
    if kind == "baseline" and samples:
        memory = [float(s["used_mib"]) for s in samples]
        if max(memory) - min(memory) > 256:
            errors.add("BASELINE_MEMORY_RANGE")
    previous = None
    for s in samples:
        start = float(s["started_ms"])
        if previous is not None and not 0 < start - previous <= MAX_GAP_MS:
            errors.add("SAMPLE_GAP")
        previous = start
        if s["exit_code"] != 0:
            errors.add("SENSOR_QUERY_FAILED")
        if not 0 <= s["utilization_pct"] <= 100:
            errors.add("SENSOR_UTILIZATION_RANGE")
        if s["used_mib"] < 0:
            errors.add("SENSOR_USED_MEMORY_NEGATIVE")
        if s["temperature_c"] < -273.15:
            errors.add("SENSOR_TEMPERATURE_RANGE")
        if kind == "baseline":
            if s["temperature_c"] > 65:
                errors.add("BASELINE_TEMPERATURE")
            if not 0 <= s["utilization_pct"] <= 10:
                errors.add("BASELINE_UTILIZATION")
            if not 0 <= s["used_mib"] <= 2048:
                errors.add("BASELINE_USED_MEMORY")
            if s["free_mib"] < 8192:
                errors.add("BASELINE_FREE_MEMORY")
        else:
            if s["temperature_c"] > 80:
                errors.add("SESSION_TEMPERATURE")
            if s["free_mib"] < 0:
                errors.add("SESSION_FREE_MEMORY")
        if not 200 <= s["sm_clock_mhz"] <= 2100:
            errors.add("SM_CLOCK")
    return {
        "schema": VERDICT_SCHEMA,
        "kind": kind,
        "gate": "FAIL" if errors else "PASS",
        "checked_samples": len(samples),
        "reasons": sorted(errors),
    }
