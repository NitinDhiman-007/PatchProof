# PatchProof Local Development Guide

## Prerequisites

- **Python**: Version 3.12+ (Installed and accessible in PATH)
- **Node.js**: Version 20+ and `npm`
- **Git**: Version 2.40+
- **Docker**: Docker Desktop or Docker Engine (Required for live containerized test execution)

---

## 1. Environment Setup

### Backend Setup
1. Navigate to `backend/`:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

### Frontend Setup
1. Navigate to `frontend/`:
   ```bash
   cd frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Copy the environment template:
   ```bash
   cp .env.example .env.local
   ```

---

## 2. Running Services

### Start Backend Service
From the workspace root or `backend/` directory:
```bash
# Windows
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --app-dir backend

# Linux / macOS
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --app-dir backend
```
- Swagger UI Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)
- Verification API: [http://localhost:8000/api/v1/verification](http://localhost:8000/api/v1/verification)

### Start Frontend Development Server
From the `frontend/` directory:
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 3. Testing and Code Quality

### Backend Quality Suite

#### Run Unit & Sandbox Tests (Pytest)
```bash
# Run all tests with verbose output
backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

#### Code Formatting & Linting (Ruff)
```bash
# Check formatting and lint rules
backend\.venv\Scripts\ruff.exe check backend

# Auto-fix lintable issues
backend\.venv\Scripts\ruff.exe check backend --fix

# Code formatting
backend\.venv\Scripts\ruff.exe format backend
```

#### Security Analysis (Bandit)
```bash
# Run AST security scanner
backend\.venv\Scripts\python.exe -m bandit -r backend/app
```

### Frontend Quality Suite

From the `frontend/` directory:
```bash
# TypeScript strict typechecking
npm run typecheck

# ESLint code inspection
npm run lint

# Production bundle compilation
npm run build
```

---

## 4. Docker Sandbox Execution

1. Ensure **Docker Desktop** is started and running.
2. The verification engine uses the official `python:3.12-slim` image by default. You can pull it in advance:
   ```bash
   docker pull python:3.12-slim
   ```
3. Verify connectivity via endpoint:
   ```bash
   curl http://localhost:8000/api/v1/verification/docker/status
   ```

---

## 5. Demonstration Scenario: Discount Calculator Defect

A deterministic Python demonstration repository is provided in `examples/demo_discount_repo/`.

### Bug Overview
- File: `calculator/discount.py`
- Bug: `calculate_discount(price, discount)` returns `-19000` instead of `800` when a 20% discount is passed as `20`.
- Baseline test (`tests/test_discount.py`) only tests decimal discounts (`0.10`), passing erroneously.

### Executing the Demonstration Workflow
1. Register the demo repository in the dashboard or via API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/repositories/register-url \
     -H "Content-Type: application/json" \
     -d '{"git_url": "https://github.com/patchproof-org/demo-discount-repo"}'
   ```
2. Start the automated debugging workflow:
   ```bash
   curl -X POST http://localhost:8000/api/v1/analysis/start \
     -H "Content-Type: application/json" \
     -d '{
       "repository_id": "<REPO_ID>",
       "bug_description": "The calculate_discount function returns an incorrect result when the discount is supplied as a percentage. Expected calculate_discount(1000, 20) == 800."
     }'
   ```
3. Watch real-time LangGraph agent progression:
   ```bash
   curl http://localhost:8000/api/v1/analysis/<ANALYSIS_ID>/events
   ```
4. Review the generated root cause and minimal unified diff in the dashboard.
5. Explicitly approve or reject the patch before export:
   ```bash
   curl -X POST http://localhost:8000/api/v1/analysis/<ANALYSIS_ID>/patch/approve \
     -H "Content-Type: application/json" \
     -d '{"status": "approved", "comment": "Verified discount calculation."}'
   ```

---

## 6. BharatCode API Configuration & Status

1. Add your key to `backend/.env`:
   ```ini
   BHARATCODE_API_KEY=your_actual_key
   BHARATCODE_BASE_URL=https://bharatcode.ai/api/model/v1
   BHARATCODE_MODEL=qwen-3.8-27b
   ```
2. Verify live connectivity:
   ```bash
   curl http://localhost:8000/api/v1/analysis/model/status
   ```

---

## 7. Model Context Protocol (MCP) Server (Phase 4 & 5)

### Running via Stdio (Claude Desktop / Cursor)
```bash
# From repository root:
backend\.venv\Scripts\python.exe backend/mcp_server.py --transport stdio
```

### Running Standalone Streamable HTTP Server
```bash
# From repository root:
backend\.venv\Scripts\python.exe backend/mcp_server.py --transport streamable-http --port 8001
```

### Running Standalone SSE Server (Legacy)
```bash
# From repository root:
backend\.venv\Scripts\python.exe backend/mcp_server.py --transport sse --port 8001
```

### Unified Gateway Endpoints
When the FastAPI backend is running, the MCP endpoints are accessible at:
- **Official Streamable HTTP**: `http://127.0.0.1:8000/mcp`
- **Legacy SSE**: `http://127.0.0.1:8000/sse`

### Testing MCP Tools via Script
```bash
# Execute unit, security, and ClientSession tests for all 9 MCP tools:
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_mcp_server.py backend/tests/test_mcp_client_all_tools.py -v
```

### Standalone End-to-End Verification Scripts
For automated judge verification and end-to-end regression validation:
```bash
# 1. Real Docker container baseline failure & patched verification:
backend\.venv\Scripts\python.exe scripts/verify_docker_e2e.py

# 2. Live Docker container isolation & security controls audit:
backend\.venv\Scripts\python.exe scripts/verify_isolation.py

# 3. MCP Streamable HTTP 9-tool happy-path audit:
backend\.venv\Scripts\python.exe scripts/verify_mcp_happypath.py
```

---

## 8. Offline Evaluation / Demo Mode

If you are evaluating PatchProof without paid API credits or wish to run an offline deterministic demonstration:
1. In `backend/.env`, set:
   ```ini
   DEMO_MODE=true
   ```
2. Run the bug analysis workflow for `examples/demo_discount_repo`:
   ```bash
   curl -X POST http://localhost:8000/api/v1/analysis/start \
     -H "Content-Type: application/json" \
     -d '{
       "repository_id": "<REPO_ID>",
       "bug_description": "calculate_discount produces negative prices when whole percentage 20 is passed."
     }'
   ```
3. The workflow executes deterministically:
   - Root cause and reproduction test are generated and clearly tagged `[DEMO MODE]`.
   - **Docker verification runs for real**: the failing test is proven in the sandbox on unpatched code.
   - The verified patch is applied and tested for real inside the Docker container, turning green.
   - Evidence report is generated and stored in SQLite.


