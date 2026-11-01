"""Offline command-line entry point; does not acquire GPU readings."""
import argparse
import json
import sys
from pathlib import Path

from .validator import GateError, evaluate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate an offline telemetry JSON fixture")
    parser.add_argument("path", type=Path, help="Synthetic or pre-normalized JSON input")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.path.read_text(encoding="utf-8"))
        verdict = evaluate(document)
    except (GateError, ValueError, OSError) as exc:
        print(json.dumps({"gate": "ERROR", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(verdict, sort_keys=True, separators=(",", ":")))
    return 0 if verdict["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
