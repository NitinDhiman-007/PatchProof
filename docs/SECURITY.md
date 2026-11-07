# PatchProof Security Policies & Threat Model

## Security Principles

PatchProof operates on untrusted codebases submitted by arbitrary users. As such, the platform implements a **zero-trust, multi-layered security model**.

---

## 1. Non-Execution Policy on Host

### Invariant
> **Untrusted code from external repositories is NEVER executed directly on the host server.**

- Repository registration, Git URL parsing, and ZIP archive validation are strictly inspection-only operations.
- Python source code is parsed exclusively via **Tree-sitter AST**, which parses the grammar into concrete syntax trees without invoking Python's `eval()`, `exec()`, or module imports.
- Dynamic test execution is delegated exclusively to isolated, ephemeral, rootless Docker containers.

---

## 2. Docker Execution Sandbox Controls (Phase 2)

Every test execution is subject to strict container-level isolation constraints:

| Security Control | Implementation | Purpose |
|---|---|---|
| **Trusted Base Image** | Fixed `python:3.12-slim` | Prevents users or LLMs from selecting malicious or backdoored container images |
| **Network Air-Gap** | `network_mode="none"` | Severely restricts all inbound and outbound network access, eliminating data exfiltration risks |
| **Non-Root Execution** | `user="1000:1000"` | Containers execute without root privileges inside the container |
| **Capability Dropping** | `cap_drop=["ALL"]` | Drops all Linux capabilities (including `CAP_NET_RAW`, `CAP_SYS_ADMIN`, `CAP_SETUID`) |
| **No New Privileges** | `security_opt=["no-new-privileges:true"]` | Disallows `setuid`/`setgid` binaries from escalating privileges |
| **Read-Only Root Filesystem** | `read_only=True` | Root container filesystem is immutable; modifications to system binaries are prohibited |
| **Scoped Writable Paths** | `tmpfs={"/tmp": "rw,noexec,nosuid,size=64m", ...}` | Writable locations are mounted in-memory with `noexec` and `nosuid` flags |
| **Memory Limit** | `mem_limit="512m"` | Prevents memory exhaustion attacks |
| **CPU Quota** | `nano_cpus=1_000_000_000` | Limits CPU consumption to a single core quota |
| **Process Limit** | `pids_limit=64` | Mitigates fork bombs and runaway process creation |
| **Execution Timeout** | `timeout=30` seconds | Automatically kills runaway or hanging test suites |
| **Disposable Lifecycle** | `container.remove(force=True)` in `finally` | Containers and ephemeral workspaces are destroyed immediately after execution |

---

## 3. Command Allowlisting & Shell Injection Defense

PatchProof strictly rejects arbitrary shell commands:
1. **Allowlisted Binaries**: Only `pytest` and `ruff` are permitted.
2. **Prohibited Interpeters & Shells**: `sh`, `bash`, `cmd`, `powershell`, `python -c` are blocked.
3. **Prohibited Metacharacters**: Commands containing `;`, `&`, `|`, `` ` ``, `$`, `>`, `<`, `\n`, `\r`, `&&`, `||` are rejected before execution.
4. **Flag Allowlisting**: Only known, safe flags (e.g. `-v`, `-vv`, `-q`, `--tb=short`, `-k`) are accepted. Arbitrary flags (e.g. `--override-ini`, `--import-mode`) are denied.

---

## 4. Ingestion Defense & Archive Safety

### Git URL Injection Prevention
Git CLI commands and URL handlers can be vulnerable to argument injection (e.g. `--upload-pack`, `--config`) or shell metacharacter injection.

PatchProof enforces:
1. **Character Disallowance**: Rejects URLs containing `;`, `&`, `|`, `` ` ``, `$`, `<`, `>`, `\n`, `\r`.
2. **Flag Disallowance**: Rejects URLs starting with a hyphen `-`.
3. **Strict Regex Filtering**: Only standard HTTP and HTTPS repository URLs are allowed.

### ZIP Archive Safety (Anti-Zip Bomb & Anti-Traversal)
When processing user-uploaded `.zip` files:
1. **In-Memory Buffer Inspection**: Files are inspected in memory (`io.BytesIO`) rather than extracted to disk.
2. **Path Traversal Defense**: All archive entry paths are inspected. Any entry starting with `/`, containing `..`, or containing Windows drive letters (`C:`) is immediately rejected.
3. **Zip Bomb Mitigation**:
   - Per-file compression ratios are calculated. Entries with compression ratios exceeding `100:1` trigger immediate rejection.
   - Total uncompressed size is capped at `4 * MAX_ZIP_UPLOAD_BYTES` (200MB max uncompressed footprint).
   - Maximum archive upload size is strictly limited to 50MB.
   - Archive entry count is capped at 5,000 files.

---

## 5. Secret Management

1. **No Hardcoded Secrets**: Secrets such as `BHARATCODE_API_KEY` are read strictly from runtime environment variables.
2. **Source Control Safeguards**:
   - The root `.gitignore` explicitly excludes `.env`, `.env.local`, `.env.*.local`, `*.db`, and virtual environments.
   - Templates (`.env.example`) provide placeholder names without credentials.
3. **Frontend Isolation**:
   - The Next.js frontend only consumes public environment variables prefixed with `NEXT_PUBLIC_` (e.g. `NEXT_PUBLIC_API_BASE_URL`).
   - Backend API keys are never exposed to the frontend browser bundle.

---

## 6. AI Threat Model & Prompt Injection Defense (Phase 3)

The BharatCode AI integration treats all repository contents, issues, and bug reports as **untrusted user input**:

1. **Tag-Delimited Prompt Encapsulation**:
   - User bug reports and retrieved source snippets are strictly enclosed within `<user_bug_report>` and `<code_context>` XML tags.
   - System prompts instruct the LLM to treat content inside these tags as pure data, never executing embedded instructions or modifying prompt objectives.
2. **Untrusted Model Output Handling**:
   - Model completions are validated via strict JSON parsing and schema checks.
   - Model output is never evaluated as code on the host, executed as shell commands, or used to configure container privileges.
3. **No Dynamic Container Selection**:
   - The LLM cannot specify base images, docker flags, or container parameters. The sandbox configuration is hardcoded and immutable.

---

## 7. Patch Validation & Ephemeral Workspace Boundaries (Phase 3)

Proposed patches are audited before being applied:

1. **Unified Diff Syntax Verification**: Diff headers (`--- a/...`, `+++ b/...`) and hunk headers (`@@ -l,s +l,s @@`) are validated.
2. **Path Traversal Rejection**: Target paths containing `..`, absolute paths, or Windows drive prefixes are rejected.
3. **Restricted File Defense**: Patches targeting sensitive configuration files (`.env`, `.git/`, `.github/`, `Dockerfile`, database files, certificates) are blocked.
4. **Binary & Executable Rejection**: Only approved source extensions (`.py`, `.txt`, `.md`, `.json`, `.yaml`, etc.) are permitted.
5. **Immutable Baseline**: Diffs are applied exclusively to separate, ephemeral workspace directories (`workspaces/analysis_{id}_patched`). The user's original repository is never modified directly.

---

## 8. Mandatory Human Approval Gate (Phase 3)

Automated commits and pushes to Git remotes are strictly prohibited:
- Every proposed patch begins in `pending_approval` status.
- Verification verdict (`VERIFIED`) confirms technical efficacy only.
- Acceptance requires explicit operator sign-off via `POST /api/v1/analysis/{id}/patch/approve` before any patch can be exported or integrated.
- All approval/rejection actions and comments are recorded in the immutable SQLite audit trail.

---

## 9. Model Context Protocol (MCP) Security Controls (Phase 4)

The MCP server adheres to strict non-execution and defense-in-depth principles:

1. **Path Traversal & Boundary Enforcement**:
   - The `read_file` tool validates all relative paths against directory traversal attacks (`..`, leading slashes, Windows colons).
   - Reading sensitive configuration files (`.env`, `.git/`, `.key`, `.db`, credentials) is blocked.
   - Only allowlisted source code extensions (`.py`, `.md`, `.json`, `.yaml`, etc.) can be read.
   - Filesystem reads are strictly bounded within the repository workspace via `os.path.commonpath`.
2. **No Arbitrary Shell Execution**:
   - The `run_verification` MCP tool strictly validates commands against `validate_command`. Only `pytest` and `ruff` allowlisted presets are accepted. Arbitrary shell arguments, chaining operators, or interpreters are blocked.
3. **Container Sandbox Preservation**:
   - Test execution requested via MCP is executed exclusively inside the air-gapped Docker sandbox with non-root user `1000:1000` and dropped capabilities.
4. **Network Authentication**:
   - Network-accessible HTTP/SSE endpoints are protected by `MCPAuthMiddleware`. When `MCP_API_KEY` is configured, requests without a valid token receive `HTTP 401 Unauthorized`.
   - Host header validation prevents DNS rebinding attacks on local SSE listeners.
5. **Human Approval Invariant**:
   - The MCP tool `get_proposed_patch` returns candidate diffs but enforces that patches are never automatically approved or applied. Human review remains mandatory.
6. **Zero Credential Exposure**:
   - No MCP tool output ever includes backend API keys, secrets, database credentials, or internal server paths.

---

## 10. Cryptographic Evidence Integrity (Phase 5)

Rather than claiming unbacked "tamper-proof" guarantees, PatchProof implements deterministic cryptographic verification for all generated evidence reports:

1. **Deterministic Canonical Serialization**:
   - Verification reports are compiled into canonical JSON representation (recursively sorted keys, standard separators `, `, `: `).
   - Dynamic non-evidence fields (such as timestamps or temporary workspace paths) are excluded from the hash payload.
2. **SHA-256 Digest**:
   - A deterministic SHA-256 digest is computed over the UTF-8 encoded canonical JSON payload.
   - The resulting hash is prefixed with `sha256:` and persisted directly on the report as `integrity_hash`.
3. **Tamper Detection**:
   - Consumers can recalculate the SHA-256 digest over the canonical payload and compare against `integrity_hash` to mathematically detect any unauthorized modifications to test verdicts, pass/fail counts, or failure outputs.



