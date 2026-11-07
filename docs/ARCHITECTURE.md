# PatchProof System Architecture

## Vision & Guiding Principle

> **"Don't trust generated code. Prove it works."**

PatchProof is an automated defect reproduction, patch generation, and evidence-backed verification platform. Traditional AI code generators produce diffs that appear plausible but frequently introduce subtle runtime regressions or fail to fix edge-case bugs. 

PatchProof enforces an evidence-first contract: **a patch is never verified unless a reproducible failing test was run, turned green by the patch, and validated against the entire test suite in an isolated environment.**

---

## High-Level Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        PatchProof Architecture                         │
└────────────────────────────────────────────────────────────────────────┘

 [ Developer Dashboard ] (Next.js 16 App Router / TypeScript / Tailwind CSS)
             │
             │ HTTP / JSON API (NEXT_PUBLIC_API_BASE_URL)
             ▼
 [ FastAPI Application Gateway ] (Python 3.12 / Pydantic v2)
      ├── /health & /api/v1/status
      ├── /api/v1/repositories (Git URL & ZIP upload validation)
      ├── /api/v1/analysis (LangGraph agent workflow & approval gates)
       ├── /api/v1/verification (Isolated Docker execution engine)
       ├── /mcp (Official Model Context Protocol Streamable HTTP transport)
       └── /sse (Legacy SSE transport for backward compatibility)
             │
      ┌──────┴───────────────────────────────────────────────────────┐
      ▼                                                              ▼
 [ BharatCode Model API ]                                   [ SQLite Persistence ]
  - Base URL: https://bharatcode.ai/api/model/v1              - Repositories Table
  - Model: qwen-3.8-27b                                       - Analysis Runs Table
  - Root Cause Analysis & Structured JSON                     - Workflow Events Table
  - Failing Pytest Generator                                  - Verification Runs Table
  - Minimal Unified Diff Synthesizer                          - Evidence Reports
      │
      ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ LangGraph Agent State Machine                                     │
 │  load_context -> analyze_bug -> retrieve_code -> root_cause       │
 │  -> generate_test -> verify_baseline -> generate_patch            │
 │  -> validate_patch -> apply_patch -> verify_docker                │
 │  -> compare_regression -> compile_evidence                        │
 └───────────────────────────────────────────────────────────────────┘
      │
      ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │ [ Phase 2 ] Secure Disposable Docker Sandbox Engine               │
 │  ├── Base Image: python:3.12-slim (Fixed, Trusted)               │
 │  ├── Network: none (Air-gapped offline test execution)            │
 │  ├── User: 1000:1000 (Non-root unprivileged)                      │
 │  ├── Capabilities: cap_drop=["ALL"], no-new-privileges:true       │
 │  ├── Resources: 512MB RAM, 1.0 CPU, 64 PIDs, 30s timeout         │
 │  ├── Filesystem: Read-only root + scoped tmpfs cache mounts       │
 │  └── Lifecycle: Unconditional container deletion in finally block │
 └───────────────────────────────────────────────────────────────────┘
```

---

## Core System Layers

### 1. Presentation Layer (Frontend)
- **Framework**: Next.js 16 App Router using React 19.
- **Developer-Centric UX**:
  - Dark charcoal and navy canvas (`#020617`, `#0f172a`) with slate borders (`#1e293b`) and sky blue accents (`#38bdf8`).
  - High-density monospace telemetry displays.
  - Sidebar navigation for `Overview`, `Repositories`, `Bug Analysis`, `Verification Reports`, and `Settings`.
  - Bug Analysis console with live workflow progress stepper, tabbed resource inspection (Events, Root Cause, Reproduction Test, Unified Diff, Evidence), and mandatory human approval controls.
  - Real-time polling with zero mock responses.

### 2. Application API Layer (Backend)
- **FastAPI Framework**: High-performance asynchronous API engine with OpenAPI documentation.
- **Pydantic Validation**: Strict schema enforcement for all incoming and outgoing payloads.
- **Background Tasks**: Dispatches long-running LangGraph agent workflows asynchronously while persisting real-time audit events.
- **Error Handling**: Global exception interceptors converting unhandled runtime exceptions and validation errors into structured `ErrorResponse` envelopes.

### 3. BharatCode AI Integration Layer (Phase 3)
- **Model Endpoint**: `https://bharatcode.ai/api/model/v1` using official OpenAI-compatible SDK.
- **Model**: `qwen-3.8-27b`.
- **Security & Prompt Guardrails**:
  - Strictly delimiters untrusted user input and repository files inside `<user_bug_report>` and `<code_context>` tags.
  - Instructs model to ignore commands or prompt injections within untrusted data.
  - Requires valid JSON output with schema enforcement.
  - Never logs API keys or transmits credentials to frontend.
- **Fault-Tolerant Error Translation**:
  - Automatically catches and maps HTTP 401/403 (`AuthenticationError`), HTTP 429 (`RateLimitError`), HTTP 500/503 (`InternalServerError`), and request timeouts (`APITimeoutError`) to informative diagnostics.

### 4. Repository Understanding Engine
- **File Tree Indexer**: Safely crawls repository trees excluding `.git`, `.venv`, `node_modules`, binary files, and files exceeding 500KB. Never executes code on the host.
- **Symbol Extractor**: Extracts classes, functions, methods, parameters, docstrings, and imports using Python's `ast` module with Tree-sitter fallback.
- **Line-Numbered Code Retriever**: Extracts relevant source snippets centered around traceback lines or identifier token matches, strictly bounded to prevent context window explosion.

### 5. LangGraph Agent State Machine (Phase 3)
12-node state machine orchestrating the complete defect reproduction and verification loop:
1. `load_context`: Creates isolated ephemeral workspace and indexes repository.
2. `analyze_bug`: Extracts defect indicators, error messages, and traceback tokens.
3. `retrieve_code`: Retrieves line-numbered source snippets grounded in the defect.
4. `root_cause`: Synthesizes structured root cause analysis via BharatCode model.
5. `generate_test`: Generates an isolated pytest regression test (`tests/test_reproduce_patchproof.py`).
6. `verify_baseline`: Executes the regression test in Docker on unmodified baseline. **Must fail** to prove reproduction.
7. `generate_patch`: Synthesizes a minimal unified diff patch.
8. `validate_patch`: Validates unified diff syntax, hunk structure, and security constraints.
9. `apply_patch`: Creates an isolated patched workspace and applies the diff safely.
10. `verify_docker`: Runs the regression test and existing test suite in Docker on the patched workspace.
11. `compare_regression`: Compares baseline and patched results to assign a verdict (`VERIFIED`, `FAILED`, `INCONCLUSIVE`, `ERROR`).
12. `compile_evidence`: Compiles immutable evidence JSON report and cleans up ephemeral directories.

### 6. Execution Policy & Sandbox Layer (Phase 2)
- **Allowlisted Command Presets**: `pytest` and `ruff`.
- **Workspace Boundary Enforcement**: Strictly contained inside `./workspaces/` with path traversal defense.
- **Disposable Docker Containers**: Managed via Docker SDK for Python with network disabled, non-root user `1000:1000`, dropped Linux capabilities, and resource caps.

### 7. Persistence Layer
- **SQLite Database**: Thread-safe connection factory managing local SQLite storage (`patchproof.db`).
- Tables:
  - `repositories`: ID, name, source type (`git`/`zip`), branch, file counts, detected language, metadata.
  - `analysis_runs`: ID, repository foreign key, bug description, stack trace, root cause JSON, reproduction test code, patch diff, patch status, verification verdict, evidence report JSON.
  - `workflow_events`: Audit trail events with analysis ID, step name, status, message, details JSON, and timestamps.
  - `verification_runs`: Standalone verification records and evidence reports.

### 8. Model Context Protocol (MCP) Service Layer (Phase 4)
- **SDK**: Official Python MCP SDK (`mcp` 2.3.0).
- **Architecture**: Decoupled service wrapper invoking existing service layer without business logic duplication.
- **Transports**:
  - `stdio`: Process-to-process communication for local LLM tools (Claude Desktop, Cursor, local agents).
  - `sse`: Streamable HTTP server for remote agent networks and web integrations.
  - `FastAPI mount`: Mounted directly on `/mcp/sse` in the main application gateway.
- **Authentication**: `MCPAuthMiddleware` checking `Authorization: Bearer <token>` or `X-API-Key` headers when `MCP_API_KEY` is configured.
- **Tool Suite**:
  1. `list_repositories`: Enumerate registered repositories safely.
  2. `search_code`: Read-only AST symbol search bounded to repository.
  3. `read_file`: Safe file retrieval with path traversal defense.
  4. `analyze_bug`: Trigger LangGraph debugging loop.
  5. `get_analysis_status`: Retrieve run status & audit trail.
  6. `get_root_cause`: Fetch structured defect explanation.
  7. `get_proposed_patch`: Fetch candidate unified diff with mandatory human approval notice.
  8. `run_verification`: Execute air-gapped Docker container test run.
  9. `get_verification_report`: Fetch evidence report & execution metrics.

### 9. Deterministic Demo Mode (Phase 4)
- Provides offline non-LLM evaluation capabilities using `examples/demo_discount_repo`.
- Synthesizes deterministic root causes, reproduction tests, and unified diff patches clearly flagged as `[DEMO MODE]`.
- **Never bypasses Docker verification**: Tests are executed for real inside the container sandbox to prove the failing baseline and passing patch.

---

## Multi-Phase Roadmap

- [x] **Phase 1: Production Foundation & Scaffolding** (FastAPI, SQLite, Next.js 16 dashboard, Tree-sitter foundation, safe URL/ZIP inspection).
- [x] **Phase 2: Secure Docker Sandbox & Test Execution Engine** (Docker SDK, execution policy, allowlisted pytest/ruff runner, resource & network isolation, evidence reporting).
- [x] **Phase 3: BharatCode AI Integration & LangGraph Agentic Debugging Engine** (BharatCode API, repository understanding, failing test generator, baseline reproduction, minimal patch synthesis, Docker proof loop, human approval workflow).
- [x] **Phase 4: Model Context Protocol (MCP) Server & Hackathon Submission Readiness** (Official Python MCP SDK 2.3, stdio & SSE transports, 9 modular tools, token authentication, path traversal guardrails, 64 passing tests).
- [x] **Phase 5: Final QA, Security Audit, MCP Streamable HTTP & Hackathon Submission Readiness** (Official Streamable HTTP transport at /mcp, legacy SSE at /sse, stdio client verification across all 9 tools, SHA-256 evidence integrity hashing, zero-secret git tracking audit, 65 passing tests).
