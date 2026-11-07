# PatchProof Dashboard Screenshots

This directory contains representative captures of the PatchProof dark developer dashboard and operational interfaces.

## Screenshots Reference

| File | View | Description |
|---|---|---|
| `01-dashboard-overview.png` | **Dashboard Overview** | Operational telemetry cards (Total Repositories, Analyses Run, Verified Patches, Sandbox Runs) and recent runs table. |
| `02-repository-registration.png` | **Repository Connect** | Safe Git URL registration and ZIP archive upload dropzone with anti-traversal inspection. |
| `03-bug-analysis-stepper.png` | **Bug Analysis Stepper** | 12-stage LangGraph agent state machine executing live defect reproduction and validation. |
| `04-root-cause-and-test.png` | **Defect Diagnosis & Pytest** | Structured root cause diagnosis, affected symbols, and synthesized failing reproduction test (`tests/test_reproduce_patchproof.py`). |
| `05-unified-diff-and-approval.png` | **Patch Review & Human Gate** | Syntax-highlighted minimal unified diff with mandatory human approval controls (`Approve Patch` / `Reject Patch`). |
| `06-verification-report.png` | **Evidence Verification Report** | Baseline vs. patched test delta, air-gapped Docker execution metrics, and SHA-256 cryptographic integrity hash. |

