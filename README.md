# gpu-telemetry-gates

Deterministic, offline validation of *normalized* GPU telemetry records.

**Status:** isolated publication candidate; not released. The source and fixture
files contain no real GPU measurements. This library **does not** query
`nvidia-smi`, access devices, run CUDA, execute FFTs, or benchmark anything.

## What it does

- Validates a strict, versioned JSON input schema and rejects malformed data.
- Checks 20 baseline samples, each 300 ms or less apart, against explicit
  utilization, temperature, memory, and SM-clock constraints.
- Checks session telemetry gaps, failed queries, temperature, SM clock, and free
  memory; it does **not** mistake a busy experimental GPU for external load.
- Preserves the `UNKNOWN` process-classification state without claiming that
  no external GPU jobs exist; rejects a supplied `KNOWN_NONSTUDY_COMPUTE`.
- Returns stable machine-readable `PASS`/`FAIL` verdicts and sorted reason codes.

**Trust boundary:** the process inventory is a *pre-normalized assertion* supplied
by a trusted producer. The evaluator cannot establish process identity, prove
authenticity of samples, guarantee physical isolation or detect all short spikes.
A telemetry `PASS` is not a scientific session `PASS`, approval to experiment,
or evidence of any CPU-versus-GPU speedup.

## Offline quickstart (Python 3.11+; standard library only)

PowerShell:

```powershell
$env:PYTHONPATH="src"
py -3.11 -m gpu_telemetry_gates fixtures/baseline-pass.json
py -3.11 -m unittest discover -s tests -v
py -3.11 scripts/generate_fixtures.py --check
```

Linux/macOS:

```bash
PYTHONPATH=src python3 -m gpu_telemetry_gates fixtures/baseline-pass.json
python3 -m unittest discover -s tests -v
python3 scripts/generate_fixtures.py --check
```

CLI exit statuses: `0` = telemetry-policy PASS, `1` = telemetry-policy FAIL,
`2` = malformed input or file error. Error reasons are JSON on stderr.

## Input schema (v1)

The JSON root is exactly `{"schema":"gpu-telemetry-gates/v1",
"kind":"baseline"|"session","samples":[...]}` with one extra
`process_inventory` field required **only** for `baseline`.

Each sample must contain exactly these numeric fields:
`started_ms`, `exit_code` (integer), `temperature_c`,
`utilization_pct`, `used_mib`, `free_mib`, `sm_clock_mhz`.

`started_ms` represents monotonic acquisition-start milliseconds from an
arbitrary origin. Every consecutive pair must satisfy `0 < gap <= 300`.
A baseline has exactly 20 samples. A session has at least two samples.

Baseline inventory example:

```json
{"capture_ok":true,"entries":[{"classification":"UNKNOWN"}]}
```

Other supported classifications: `STUDY`,
`IDENTIFIED_WORKLOAD_UNPROVEN`, `KNOWN_NONSTUDY_COMPUTE`.
The evaluator does not infer these classifications from filenames or PIDs.

Main policy limits (engineering rules, **not hardware safety guarantees**):

| Parameter | Baseline | Session |
|---|---:|---:|
| Temperature | <=65 C | <=80 C |
| Utilization | 0..10% | Not an external-load criterion |
| Used memory | 0..2048 MiB | Recorded, not used to infer interference |
| Free memory | >=8192 MiB | >=0 MiB |
| Used-memory range | <=256 MiB | Not a gate |
| SM clock | 200..2100 MHz | 200..2100 MHz |
| Start-to-start gap | 0 < gap <=300 ms | 0 < gap <=300 ms |
| Sensor exit code | 0 in every sample | 0 in every sample |

This tool does not validate an FFT, enforce a GPU memory allocation budget,
verify session completeness, or reproduce the parent project's scientific
protocol. It intentionally implements only the narrow telemetry-policy layer.

## Reproducibility

`fixtures/*.json` are synthetic, deterministic test vectors. Regenerate their
exact bytes using `python3 scripts/generate_fixtures.py --write` or check
committed bytes without writing using `--check`.
`python3 -m unittest discover -s tests -v` tests positive and negative paths.
GitHub Actions runs these checks on Ubuntu and Windows. Consult the public
Actions runs for hosted results; local validation alone is not cross-platform proof.

## Privacy and licensing

No real telemetry, workstation identities, PIDs, personal paths or historical
experimental files are distributed. This repository was initialized from a
separate curated package, not from the private laboratory's Git history.

Licensed under the [MIT License](LICENSE); copyright (c) 2026 JoanAbad82.
