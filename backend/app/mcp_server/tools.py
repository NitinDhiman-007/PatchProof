"""Model Context Protocol (MCP) tool implementations for PatchProof.

Exposes 9 core tools that invoke the existing backend service layer directly:
1. list_repositories
2. search_code
3. read_file
4. analyze_bug
5. get_analysis_status
6. get_root_cause
7. get_proposed_patch
8. run_verification
9. get_verification_report

Strict non-execution guardrails, path traversal defenses, zero secret exposure,
and mandatory human approval constraints are enforced across all tools.
"""

import json
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.execution_policy import SecurityPolicyViolation, validate_command
from app.core.logging import get_logger
from app.database.database import get_db_connection
from app.services.patch_service import FORBIDDEN_PATCH_PATTERNS
from app.services.repository_service import get_repository
from app.services.repository_service import list_repositories as svc_list_repositories
from app.services.repository_understanding import CodeRetriever, RepositoryIndex
from app.services.verification_service import VerificationService
from app.services.workflow_engine import run_debugging_workflow

logger = get_logger(__name__)

SAFE_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".rst",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
}


def _resolve_repo_workspace(repository_id: str) -> tuple[str | None, str | None]:
    """
    Safely resolve the directory containing repository files.
    Returns (workspace_path, error_message).
    """
    repo = get_repository(repository_id)
    if not repo:
        return None, f"Repository '{repository_id}' does not exist."

    # 1. Check metadata for source_directory
    source_dir = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT metadata_json FROM repositories WHERE id = ?;", (repository_id,))
            row = cursor.fetchone()
            if row and row["metadata_json"]:
                meta = json.loads(row["metadata_json"])
                source_dir = meta.get("source_directory")
    except Exception as exc:
        logger.debug("Could not inspect repo metadata: %s", exc)

    if source_dir and os.path.isdir(source_dir):
        return os.path.abspath(source_dir), None

    # 2. Check workspace base directory
    settings = get_settings()
    base_dir = os.path.abspath(settings.WORKSPACE_BASE_DIR)
    repo_workspace = os.path.join(base_dir, f"repo_{repository_id}")
    if os.path.isdir(repo_workspace):
        return repo_workspace, None

    # 3. Check demo discount repository as deterministic fallback if repo name matches
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    if os.path.isdir(demo_dir) and ("demo" in repo.name.lower() or "discount" in repo.name.lower()):
        return demo_dir, None

    # 4. If directory doesn't exist yet, return demo directory or create scaffold
    if os.path.isdir(demo_dir):
        return demo_dir, None

    return None, f"Workspace files for repository '{repository_id}' are not yet populated on disk."


# ==============================================================================
# Tool 1: list_repositories
# ==============================================================================


def mcp_list_repositories(limit: int = 50) -> dict[str, Any]:
    """
    List all registered repositories in PatchProof.

    Args:
        limit: Maximum number of repositories to return (default: 50, max: 100).

    Returns:
        Structured list of registered repositories and summary counts.
    """
    safe_limit = max(1, min(limit, 100))
    repos = svc_list_repositories(limit=safe_limit)
    return {
        "count": len(repos),
        "repositories": [
            {
                "id": r.id,
                "name": r.name,
                "source_type": r.source_type,
                "git_url": r.git_url,
                "default_branch": r.default_branch,
                "file_count": r.file_count,
                "detected_language": r.detected_language,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in repos
        ],
    }


# ==============================================================================
# Tool 2: search_code
# ==============================================================================


def mcp_search_code(repository_id: str, query: str, limit: int = 10) -> dict[str, Any]:
    """
    Search symbols and code within a repository using non-executing AST and lexical indexing.

    Args:
        repository_id: Unique UUID of the registered repository.
        query: Natural language bug description or code search query.
        limit: Maximum number of matching snippets to return (default: 10).

    Returns:
        Structured code snippets with file paths, line ranges, and relevance scores.
    """
    if not repository_id or not repository_id.strip():
        return {"error": "Missing repository_id", "snippets": []}
    if not query or not query.strip():
        return {"error": "Search query cannot be empty", "snippets": []}

    workspace_dir, err = _resolve_repo_workspace(repository_id.strip())
    if err or not workspace_dir:
        return {"error": err or "Repository workspace unavailable", "snippets": []}

    try:
        index = RepositoryIndex(workspace_dir)
        index.build_index()
        retriever = CodeRetriever(index)
        snippets = retriever.retrieve_relevant_snippets(query.strip(), max_snippets=max(1, min(limit, 20)))
        return {
            "repository_id": repository_id,
            "query": query,
            "total_files_indexed": len(index.files),
            "snippets_found": len(snippets),
            "snippets": snippets,
        }
    except Exception as exc:
        logger.error("Error searching code for repository %s: %s", repository_id, exc)
        return {"error": f"Search failed: {exc}", "snippets": []}


# ==============================================================================
# Tool 3: read_file
# ==============================================================================


def mcp_read_file(repository_id: str, relative_path: str, max_lines: int = 500) -> dict[str, Any]:
    """
    Safely read file contents from a repository workspace with strict path traversal defenses.

    Args:
        repository_id: Unique UUID of the registered repository.
        relative_path: Safe relative path to the file within the repository (e.g. 'calculator/discount.py').
        max_lines: Maximum number of lines to return to prevent buffer exhaustion (default: 500).

    Returns:
        File contents, line count, and metadata.
    """
    if not repository_id or not repository_id.strip():
        return {"error": "Missing repository_id"}
    if not relative_path or not relative_path.strip():
        return {"error": "relative_path cannot be empty"}

    clean_rel = relative_path.strip().replace("\\", "/")

    # Security check 1: Path traversal inspection
    if clean_rel.startswith("/") or ":" in clean_rel or ".." in clean_rel.split("/"):
        return {"error": f"Path traversal sequence detected in relative path: '{relative_path}'"}

    clean_rel = clean_rel.lstrip("/")

    # Security check 2: Restricted file patterns (.env, .git, keys, databases)
    for pattern in FORBIDDEN_PATCH_PATTERNS:
        if re.search(pattern, clean_rel, re.IGNORECASE):
            return {"error": f"Access to restricted file '{clean_rel}' is forbidden."}

    # Security check 3: Allowlisted file extensions
    _, ext = os.path.splitext(clean_rel.lower())
    if ext and ext not in SAFE_EXTENSIONS:
        return {"error": f"File extension '{ext}' is not permitted for reading."}

    workspace_dir, err = _resolve_repo_workspace(repository_id.strip())
    if err or not workspace_dir:
        return {"error": err or "Repository workspace unavailable"}

    full_path = os.path.abspath(os.path.join(workspace_dir, clean_rel))

    # Security check 4: Path containment check
    try:
        common = os.path.commonpath([full_path, workspace_dir])
        if os.path.abspath(common) != workspace_dir:
            return {"error": "Resolved file path escapes repository root."}
    except ValueError:
        return {"error": "Path traversal detected across filesystem boundaries."}

    if not os.path.isfile(full_path):
        return {"error": f"File '{clean_rel}' does not exist in repository workspace."}

    try:
        with open(full_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        truncated = total_lines > max_lines
        content_lines = lines[:max_lines]

        return {
            "repository_id": repository_id,
            "relative_path": clean_rel,
            "total_lines": total_lines,
            "lines_returned": len(content_lines),
            "truncated": truncated,
            "content": "".join(content_lines),
        }
    except Exception as exc:
        logger.error("Failed to read file %s: %s", full_path, exc)
        return {"error": f"Failed to read file: {exc}"}


# ==============================================================================
# Tool 4: analyze_bug
# ==============================================================================


def mcp_analyze_bug(
    repository_id: str,
    bug_description: str,
    issue_url: str | None = None,
    stack_trace: str | None = None,
) -> dict[str, Any]:
    """
    Initiate the LangGraph automated debugging, reproduction, and patch generation workflow.

    Args:
        repository_id: Unique UUID of the target repository.
        bug_description: Detailed description of the defect or failing behavior.
        issue_url: Optional link to issue tracker or bug report.
        stack_trace: Optional stack trace or raw failure logs.

    Returns:
        Structured analysis initiation response with analysis_id and initial status.
    """
    if not repository_id or not repository_id.strip():
        return {"error": "Missing repository_id"}
    if not bug_description or not bug_description.strip():
        return {"error": "bug_description cannot be empty"}

    repo = get_repository(repository_id.strip())
    if not repo:
        return {"error": f"Repository '{repository_id}' does not exist."}

    analysis_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO analysis_runs (
                id, repository_id, bug_description, issue_url, stack_trace,
                status, patch_status, verification_verdict, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'running', 'none', 'PENDING', ?, ?);
            """,
            (analysis_id, repo.id, bug_description.strip(), issue_url, stack_trace, now, now),
        )

    # Run workflow engine
    try:
        final_state = run_debugging_workflow(
            analysis_id=analysis_id,
            repository_id=repo.id,
            bug_description=bug_description.strip(),
            issue_url=issue_url,
            stack_trace=stack_trace,
        )
        verdict = final_state.get("verdict", "PENDING")
        return {
            "analysis_id": analysis_id,
            "repository_id": repo.id,
            "status": "completed" if verdict in ["VERIFIED", "FAILED", "INCONCLUSIVE"] else "running",
            "verdict": verdict,
            "message": f"Bug analysis completed with verdict: {verdict}",
            "patch_status": final_state.get("patch_status", "pending_approval"),
            "baseline_reproduced": final_state.get("baseline_reproduced", False),
        }
    except Exception as exc:
        logger.error("Error executing debugging workflow for %s: %s", analysis_id, exc)
        return {
            "analysis_id": analysis_id,
            "repository_id": repo.id,
            "status": "error",
            "error": str(exc),
        }


# ==============================================================================
# Tool 5: get_analysis_status
# ==============================================================================


def mcp_get_analysis_status(analysis_id: str) -> dict[str, Any]:
    """
    Retrieve real-time status and telemetry events for a bug analysis run.

    Args:
        analysis_id: Unique UUID of the analysis run.

    Returns:
        Current lifecycle state, verdict, patch status, and workflow event log.
    """
    if not analysis_id or not analysis_id.strip():
        return {"error": "Missing analysis_id"}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.*, r.name as repository_name
            FROM analysis_runs a
            LEFT JOIN repositories r ON a.repository_id = r.id
            WHERE a.id = ?;
            """,
            (analysis_id.strip(),),
        )
        run_row = cursor.fetchone()
        if not run_row:
            return {"error": f"Analysis run '{analysis_id}' not found."}

        cursor.execute(
            """
            SELECT step_name, status, message, details_json, created_at
            FROM workflow_events
            WHERE analysis_id = ?
            ORDER BY created_at ASC;
            """,
            (analysis_id.strip(),),
        )
        events = [
            {
                "step_name": ev["step_name"],
                "status": ev["status"],
                "message": ev["message"],
                "created_at": ev["created_at"],
            }
            for ev in cursor.fetchall()
        ]

    return {
        "analysis_id": run_row["id"],
        "repository_id": run_row["repository_id"],
        "repository_name": run_row["repository_name"],
        "status": run_row["status"],
        "verdict": run_row["verification_verdict"],
        "patch_status": run_row["patch_status"],
        "baseline_reproduced": bool(run_row["baseline_reproduced"]),
        "summary": run_row["summary"],
        "created_at": run_row["created_at"],
        "updated_at": run_row["updated_at"],
        "events_count": len(events),
        "events": events,
    }


# ==============================================================================
# Tool 6: get_root_cause
# ==============================================================================


def mcp_get_root_cause(analysis_id: str) -> dict[str, Any]:
    """
    Retrieve structured root cause analysis and defect explanation for an analysis run.

    Args:
        analysis_id: Unique UUID of the analysis run.

    Returns:
        Problem summary, suspected root cause, affected files, confidence score, and strategy.
    """
    if not analysis_id or not analysis_id.strip():
        return {"error": "Missing analysis_id"}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT root_cause_json, summary, status FROM analysis_runs WHERE id = ?;",
            (analysis_id.strip(),),
        )
        row = cursor.fetchone()
        if not row:
            return {"error": f"Analysis run '{analysis_id}' not found."}

    rca_json = row["root_cause_json"]
    if not rca_json:
        return {
            "analysis_id": analysis_id,
            "status": row["status"],
            "message": "Root cause analysis has not yet been produced for this run.",
            "root_cause": None,
        }

    try:
        rca_data = json.loads(rca_json)
        return {
            "analysis_id": analysis_id,
            "status": row["status"],
            "root_cause": rca_data,
        }
    except json.JSONDecodeError:
        return {
            "analysis_id": analysis_id,
            "status": row["status"],
            "root_cause": {"raw_summary": row["summary"]},
        }


# ==============================================================================
# Tool 7: get_proposed_patch
# ==============================================================================


def mcp_get_proposed_patch(analysis_id: str) -> dict[str, Any]:
    """
    Retrieve candidate code patch diff and validation status.

    IMPORTANT SAFETY NOTICE:
    Proposed patches are NEVER automatically merged or pushed. Explicit human review
    and approval is strictly required before applying changes to production code.

    Args:
        analysis_id: Unique UUID of the analysis run.

    Returns:
        Unified diff patch, patch status, and human review guidelines.
    """
    if not analysis_id or not analysis_id.strip():
        return {"error": "Missing analysis_id"}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT patch_diff, patch_status, verification_verdict FROM analysis_runs WHERE id = ?;",
            (analysis_id.strip(),),
        )
        row = cursor.fetchone()
        if not row:
            return {"error": f"Analysis run '{analysis_id}' not found."}

    diff = row["patch_diff"]
    patch_status = row["patch_status"] or "none"

    return {
        "analysis_id": analysis_id,
        "patch_available": bool(diff),
        "patch_status": patch_status,
        "verification_verdict": row["verification_verdict"],
        "patch_diff": diff,
        "human_approval_required": True,
        "human_review_notice": (
            "SAFETY POLICY ENFORCED: AI-generated code patches require explicit human review and approval. "
            "PatchProof will never automatically commit, merge, or push code without developer sign-off."
        ),
    }


# ==============================================================================
# Tool 8: run_verification
# ==============================================================================


def mcp_run_verification(
    repository_id: str,
    command: str = "pytest",
    run_ruff: bool = True,
) -> dict[str, Any]:
    """
    Execute tests and static analysis inside a secure, network-isolated Docker container sandbox.

    Args:
        repository_id: Unique UUID of the target repository.
        command: Allowlisted test command ('pytest', 'pytest_verbose', 'pytest_quiet').
        run_ruff: Whether to execute Ruff static analysis step (default: True).

    Returns:
        Structured execution result including test pass/fail counts, exit code, and duration.
    """
    if not repository_id or not repository_id.strip():
        return {"error": "Missing repository_id"}

    try:
        validate_command(command)
    except SecurityPolicyViolation as exc:
        return {"error": f"Command rejected by security policy: {exc}"}

    svc = VerificationService()
    try:
        report = svc.start_verification_run(
            repository_id=repository_id.strip(),
            command_preset=command,
            run_ruff=run_ruff,
        )
        return {
            "run_id": report.get("run_id"),
            "repository_id": repository_id,
            "status": report.get("status"),
            "exit_code": report.get("exit_code"),
            "duration_seconds": report.get("duration_seconds"),
            "tests_passed": report.get("tests_passed"),
            "tests_failed": report.get("tests_failed"),
            "tests_skipped": report.get("tests_skipped"),
            "ruff_passed": report.get("ruff_passed"),
            "verification_summary": report.get("verification_summary"),
        }
    except Exception as exc:
        logger.error("Verification run failed for %s: %s", repository_id, exc)
        return {"error": f"Verification run failed: {exc}"}


# ==============================================================================
# Tool 9: get_verification_report
# ==============================================================================


def mcp_get_verification_report(run_id: str) -> dict[str, Any]:
    """
    Retrieve the complete evidence-backed verification report by run ID.

    Args:
        run_id: Unique UUID of the verification run.

    Returns:
        Full JSON evidence report with test results, static analysis issues, sanitized stdout/stderr.
    """
    if not run_id or not run_id.strip():
        return {"error": "Missing run_id"}

    svc = VerificationService()
    report = svc.get_report(run_id.strip())
    if not report:
        return {"error": f"Verification report '{run_id}' not found."}

    return {
        "run_id": run_id,
        "evidence_report": report,
    }
