"""Generate or verify deterministic synthetic fixtures. No GPU/sensors/FFT."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def sample(index: int, *, session: bool = False) -> dict:
    return {
        "started_ms": 250 * index,
        "exit_code": 0,
        "temperature_c": 48 if session else 45,
        "utilization_pct": 75 if session else 0,
        "used_mib": 850 if session else 400,
        "free_mib": 11250 if session else 11700,
        "sm_clock_mhz": 1200 if session else 210,
    }


def fixture(kind: str, *, fail: bool = False) -> dict:
    samples = [sample(i, session=(kind == "session")) for i in range(4 if kind == "session" else 20)]
    payload = {"schema": "gpu-telemetry-gates/v1", "kind": kind, "samples": samples}
    if kind == "baseline":
        payload["process_inventory"] = {
            "capture_ok": True,
            "entries": [{"classification": "UNKNOWN"}],
        }
        if fail:
            samples[5]["utilization_pct"] = 11
    elif fail:
        samples[2]["temperature_c"] = 81
    return payload


def expected_files() -> dict[str, bytes]:
    items = {
        "baseline-pass.json": fixture("baseline"),
        "baseline-fail.json": fixture("baseline", fail=True),
        "session-pass.json": fixture("session"),
        "session-fail.json": fixture("session", fail=True),
    }
    return {
        name: (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        for name, doc in items.items()
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Byte-for-byte verify existing fixtures")
    group.add_argument("--write", action="store_true", help="Write only the four known fixtures")
    args = parser.parse_args(argv)
    for name, data in expected_files().items():
        path = FIXTURES / name
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                print(f"MISMATCH: {name}")
                return 1
        else:
            path.write_bytes(data)
    print("FOUR_SYNTHETIC_FIXTURES_VERIFIED" if args.check else "FOUR_SYNTHETIC_FIXTURES_WRITTEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
