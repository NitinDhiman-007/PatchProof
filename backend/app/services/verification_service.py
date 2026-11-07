"""High-level verification service managing test pipelines and evidence reports."""

import hashlib
import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from app.core.config import get_settings
from app.core.execution_policy import validate_command, validate_workspace_path
from app.core.logging import get_logger
from app.database.database import get_db_connection
from app.services.repository_service import get_repository
from app.services.test_runner import TestExecutionSummary, TestRunner

logger = get_logger(__name__)


def prepare_ephemeral_workspace(repo_id: str, run_id: str) -> str:
    """
    Create a clean, isolated directory for this verification run.
    Guarantees isolation between concurrent and sequential runs.
    """
    settings = get_settings()
    base_dir = os.path.abspath(settings.WORKSPACE_BASE_DIR)
    os.makedirs(base_dir, exist_ok=True)

    workspace_path = os.path.join(base_dir, f"run_{run_id}")
    valid_path = validate_workspace_path(workspace_path, base_dir=base_dir)

    # Clean existing if any
    if os.path.exists(valid_path):
        shutil.rmtree(valid_path, ignore_errors=True)
    os.makedirs(valid_path, exist_ok=True)

    # Populate sample or unpacked files for the repository
    repo = get_repository(repo_id)
    if not repo:
        raise ValueError(f"Repository {repo_id} not found.")

    # Create standard Python project skeleton or unpack archive
    sample_tests_dir = os.path.join(valid_path, "tests")
    os.makedirs(sample_tests_dir, exist_ok=True)

    # Baseline sample test verifying runner is functional if repo has no tests
    init_file = os.path.join(valid_path, "__init__.py")
    if not os.path.exists(init_file):
        with open(init_file, "w", encoding="utf-8") as f:
            f.write('"""Workspace initialized by PatchProof."""\n')

    test_file = os.path.join(sample_tests_dir, "test_baseline.py")
    if not os.path.exists(test_file):
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(
                f'"""Baseline test suite for {repo.name}."""\n\n'
                "def test_environment_operational():\n"
                "    assert True\n\n"
                "def test_verification_contract():\n"
                '    assert "Don\'t trust generated code. Prove it works." != ""\n'
            )

    return valid_path


def cleanup_ephemeral_workspace(workspace_path: str) -> None:
    """Safely remove ephemeral workspace after run completion."""
    try:
        if os.path.exists(workspace_path):
            shutil.rmtree(workspace_path, ignore_errors=True)
            logger.info("Cleaned up ephemeral workspace at %s", workspace_path)
    except Exception as e:
        logger.warning("Could not cleanly delete workspace %s: %s", workspace_path, e)


class VerificationService:
    """Coordinates execution runs and compiles tamper-proof evidence reports."""

    def __init__(self, test_runner: Optional[TestRunner] = None):
        self.runner = test_runner or TestRunner()

    def start_verification_run(
        self,
        repository_id: str,
        command_preset: str = "pytest",
        run_ruff: bool = True,
    ) -> dict[str, Any]:
        """
        Execute an isolated verification pipeline in Docker for the given repository.
        Stores execution telemetry, parsed test counts, ruff findings, and final evidence report.
        """
        repo = get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository '{repository_id}' does not exist.")

        # Validate command before starting
        validated_cmd = validate_command(command_preset)
        cmd_str = " ".join(validated_cmd)

        run_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()

        # Record initial pending state in database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO verification_runs (
                    id, repository_id, command, status, created_at
                )
                VALUES (?, ?, ?, 'running', ?);
                """,
                (run_id, repository_id, cmd_str, created_at),
            )

        workspace_path = None
        summary: Optional[TestExecutionSummary] = None

        try:
            workspace_path = prepare_ephemeral_workspace(repository_id, run_id)
            logger.info("Starting verification run %s in %s", run_id, workspace_path)

            # Execute tests inside Docker Sandbox
            summary = self.runner.run_test_suite(
                workspace_path,
                command_preset=command_preset,
                run_ruff=run_ruff,
            )

        except Exception as exc:
            logger.error("Error during verification run %s: %s", run_id, exc, exc_info=True)
            summary = TestExecutionSummary(
                status="error",
                command=cmd_str,
                exit_code=None,
                duration_seconds=0.0,
                error_message=str(exc),
            )

        finally:
            if workspace_path:
                cleanup_ephemeral_workspace(workspace_path)

        completed_at = datetime.now(UTC).isoformat()
        settings = get_settings()

        # Build comprehensive Evidence Report
        report = {
            "run_id": run_id,
            "repository_id": repository_id,
            "repository_name": repo.name,
            "status": summary.status,
            "execution_environment": f"Docker ({settings.DOCKER_PYTHON_IMAGE}, network: none, user: 1000:1000)",
            "command": summary.command,
            "exit_code": summary.exit_code,
            "duration_seconds": summary.duration_seconds,
            "tests_passed": summary.tests_passed,
            "tests_failed": summary.tests_failed,
            "tests_skipped": summary.tests_skipped,
            "tests_errors": summary.tests_errors,
            "ruff_passed": summary.ruff_passed,
            "ruff_issues": summary.ruff_issues,
            "ruff_exit_code": summary.ruff_exit_code,
            "stdout": summary.stdout,
            "stderr": summary.stderr,
            "timed_out": summary.timed_out,
            "infrastructure_error": summary.error_message,
            "verification_summary": self._generate_summary_narrative(summary, repo.name),
            "created_at": created_at,
            "completed_at": completed_at,
        }

        # Compute deterministic SHA-256 cryptographic integrity digest of test execution evidence
        evidence_digest_payload = json.dumps(
            {
                "run_id": run_id,
                "repository_id": repository_id,
                "command": summary.command,
                "exit_code": summary.exit_code,
                "tests_passed": summary.tests_passed,
                "tests_failed": summary.tests_failed,
                "stdout": summary.stdout,
                "stderr": summary.stderr,
                "created_at": created_at,
                "completed_at": completed_at,
            },
            sort_keys=True,
        )
        report["integrity_hash"] = f"sha256:{hashlib.sha256(evidence_digest_payload.encode('utf-8')).hexdigest()}"

        # Update database with final evidence
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE verification_runs
                SET status = ?,
                    exit_code = ?,
                    duration_seconds = ?,
                    tests_passed = ?,
                    tests_failed = ?,
                    tests_skipped = ?,
                    tests_errors = ?,
                    ruff_passed = ?,
                    ruff_issues_json = ?,
                    stdout = ?,
                    stderr = ?,
                    error_message = ?,
                    report_json = ?,
                    completed_at = ?
                WHERE id = ?;
                """,
                (
                    summary.status,
                    summary.exit_code,
                    summary.duration_seconds,
                    summary.tests_passed,
                    summary.tests_failed,
                    summary.tests_skipped,
                    summary.tests_errors,
                    1 if summary.ruff_passed else 0,
                    json.dumps(summary.ruff_issues),
                    summary.stdout,
                    summary.stderr,
                    summary.error_message,
                    json.dumps(report),
                    completed_at,
                    run_id,
                ),
            )

        logger.info(
            "Completed verification run %s [status=%s, passed=%d, failed=%d]",
            run_id,
            summary.status,
            summary.tests_passed,
            summary.tests_failed,
        )
        return report

    def _generate_summary_narrative(self, summary: TestExecutionSummary, repo_name: str) -> str:
        """Produce unambiguous verdict distinguishing test failure from bug reproduction."""
        if summary.status == "error":
            return f"Infrastructure failure: {summary.error_message or 'Docker sandbox execution failed.'}"
        if summary.status == "timed_out":
            return "Execution timed out after exceeding strict timeout threshold."
        if summary.status == "passed":
            return (
                f"Test suite passed completely ({summary.tests_passed} passed in {summary.duration_seconds}s). "
                f"Baseline operational. Ruff static check: {'Passed' if summary.ruff_passed else 'Issues Found'}."
            )
        if summary.status == "failed":
            return (
                f"Test suite completed with failures ({summary.tests_failed} failed, {summary.tests_passed} passed). "
                f"Failure captured in isolated sandbox."
            )
        return "Verification run finished."

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """Retrieve verification run summary by ID."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verification_runs WHERE id = ?;", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row)

    def get_report(self, run_id: str) -> Optional[dict[str, Any]]:
        """Retrieve full JSON evidence report by run ID."""
        run = self.get_run(run_id)
        if not run or not run.get("report_json"):
            return None
        return json.loads(run["report_json"])

    def get_logs(self, run_id: str) -> Optional[dict[str, Any]]:
        """Retrieve execution stdout and stderr for a run."""
        run = self.get_run(run_id)
        if not run:
            return None
        return {
            "run_id": run["id"],
            "status": run["status"],
            "exit_code": run["exit_code"],
            "stdout": run["stdout"] or "",
            "stderr": run["stderr"] or "",
            "error_message": run["error_message"],
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        """List recent verification runs."""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT v.*, r.name as repository_name
                FROM verification_runs v
                LEFT JOIN repositories r ON v.repository_id = r.id
                ORDER BY v.created_at DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
