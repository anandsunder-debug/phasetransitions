# Perl FEA Reliability Chain

This directory contains a 4-step Perl pipeline to:

1. Collect runtime telemetry inputs.
2. Build a bounded FEA-inspired reliability model with both functional and non-functional reliability.
3. Emit corrected payload templates for known failing request shapes.
4. Run all three steps end-to-end.

## Scripts

- `01_collect_inputs.pl`
  - Reads `report.json` (if present).
  - Fetches live data from:
    - `/api/healing/topology/schema`
    - `/api/metrics/real`
    - `/api/metrics/reliability`
    - `/api/healing/status`
- `02_build_bounded_fea_model.pl`
  - Produces bounded scores in `[0,1]` for:
    - per-node functional reliability
    - per-node non-functional reliability
    - per-node overall reliability
    - system composite reliability
- `03_correct_failing_payloads.pl`
  - Produces a JSON catalog of corrected payloads for common 400/422 payload mismatches.
  - Produces runnable curl examples.
- `04_run_chain.pl`
  - Orchestrates the full chain.

## Usage

```bash
perl scripts/perl-fea/04_run_chain.pl \
  --base-url http://localhost:8001 \
  --report report.json \
  --out-dir artifacts/perl-fea
```

## Outputs

- `artifacts/perl-fea/runtime-inputs.json`
- `artifacts/perl-fea/bounded-fea-model.json`
- `artifacts/perl-fea/corrected-payloads.json`
- `artifacts/perl-fea/corrected-curl-examples.sh`
