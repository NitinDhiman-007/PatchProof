"""Test and static analysis runner parsing output telemetry."""

import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.execution_policy import validate_command
from app.core.logging import get_logger
from app.services.docker_sandbox import DockerSandbox, ExecutionResult

logger = get_logger(__name__)


@dataclass
class TestExecutionSummary:
    """Consolidated results of test and static analysis execution."""

    __test__ = False

    status: str  # "passed" | "failed" | "timed_out" | "error"
    command: str
    exit_code: Optional[int]
    duration_seconds: float
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_errors: int = 0
    ruff_passed: bool = True
    ruff_issues: list[str] = field(default_factory=list)
    ruff_exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    error_message: Optional[str] = None


def parse_pytest_metrics(output: str) -> dict:
    """
    Parse standard pytest summary lines to extract test metrics.
    Example: '=== 2 failed, 5 passed, 1 skipped, 1 warning in 1.23s ==='
    """
    metrics = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }

    if not output:
        return metrics

    # Look for summary lines
    lines = output.split("\n")
    for line in reversed(lines):
        if "==" in line and ("passed" in line or "failed" in line or "error" in line or "skipped" in line):
            # Parse individual components
            passed_match = re.search(r"(\d+)\s+passed", line)
            if passed_match:
                metrics["passed"] = int(passed_match.group(1))

            failed_match = re.search(r"(\d+)\s+failed", line)
            if failed_match:
                metrics["failed"] = int(failed_match.group(1))

            skipped_match = re.search(r"(\d+)\s+skipped", line)
            if skipped_match:
                metrics["skipped"] = int(skipped_match.group(1))

            errors_match = re.search(r"(\d+)\s+error", line)
            if errors_match:
                metrics["errors"] = int(errors_match.group(1))

            break

    # If no summary line found but tests were collected/passed
    if metrics["passed"] == 0 and metrics["failed"] == 0:
        passed_dots = output.count(" PASSED")
        failed_dots = output.count(" FAILED")
        skipped_dots = output.count(" SKIPPED")
        if passed_dots or failed_dots or skipped_dots:
            metrics["passed"] = passed_dots
            metrics["failed"] = failed_dots
            metrics["skipped"] = skipped_dots

    return metrics


def parse_ruff_output(output: str, exit_code: Optional[int]) -> tuple[bool, list[str]]:
    """Parse Ruff output into structured findings list."""
    if exit_code == 0:
        return True, []

    issues: list[str] = []
    lines = output.split("\n")
    for line in lines:
        clean = line.strip()
        # Look for ruff diagnostic lines (e.g., path:line:col: CODE message)
        if clean and ":" in clean and any(rule in clean for rule in ["E", "F", "W", "I", "UP", "B", "S"]):
            issues.append(clean)
            if len(issues) >= 50:  # Cap findings list
                issues.append("... (more findings truncated)")
                break

    return False, issues


class TestRunner:
    """Executes tests and static analysis within the Docker sandbox."""

    __test__ = False

    def __init__(self, sandbox: Optional[DockerSandbox] = None):
        self.sandbox = sandbox or DockerSandbox()

    def run_test_suite(
        self,
        workspace_path: str,
        command_preset: str = "pytest",
        run_ruff: bool = True,
    ) -> TestExecutionSummary:
        """
        Execute allowlisted test suite followed by optional Ruff static analysis.
        Produces full metrics and sanitized output streams.
        """
        # Validate command
        cmd_parts = validate_command(command_preset)
        cmd_str = " ".join(cmd_parts)

        # 1. Run Pytest in Docker Sandbox
        test_exec: ExecutionResult = self.sandbox.run_command(workspace_path, cmd_parts)

        # Handle infrastructure / Docker availability error
        if test_exec.error_message and not test_exec.timed_out:
            logger.error("Sandbox execution failed: %s", test_exec.error_message)
            return TestExecutionSummary(
                status="error",
                command=cmd_str,
                exit_code=test_exec.exit_code,
                duration_seconds=test_exec.duration_seconds,
                stdout=test_exec.stdout,
                stderr=test_exec.stderr,
                timed_out=False,
                error_message=test_exec.error_message,
            )

        if test_exec.timed_out:
            return TestExecutionSummary(
                status="timed_out",
                command=cmd_str,
                exit_code=test_exec.exit_code,
                duration_seconds=test_exec.duration_seconds,
                stdout=test_exec.stdout,
                stderr=test_exec.stderr,
                timed_out=True,
                error_message="Test run exceeded timeout limit.",
            )

        # Parse test metrics
        combined_logs = f"{test_exec.stdout}\n{test_exec.stderr}"
        metrics = parse_pytest_metrics(combined_logs)

        # 2. Run Ruff Static Analysis (if requested and test run didn't fail on infrastructure)
        ruff_passed = True
        ruff_issues: list[str] = []
        ruff_exit = None

        if run_ruff:
            ruff_cmd = validate_command("ruff")
            ruff_exec = self.sandbox.run_command(workspace_path, ruff_cmd)
            ruff_exit = ruff_exec.exit_code
            ruff_passed, ruff_issues = parse_ruff_output(f"{ruff_exec.stdout}\n{ruff_exec.stderr}", ruff_exec.exit_code)

        # Determine overall execution status
        # Note: In bug reproduction, a failed test indicates the bug is reproduced!
        status = "passed" if test_exec.exit_code == 0 else "failed"

        return TestExecutionSummary(
            status=status,
            command=cmd_str,
            exit_code=test_exec.exit_code,
            duration_seconds=test_exec.duration_seconds,
            tests_passed=metrics["passed"],
            tests_failed=metrics["failed"],
            tests_skipped=metrics["skipped"],
            tests_errors=metrics["errors"],
            ruff_passed=ruff_passed,
            ruff_issues=ruff_issues,
            ruff_exit_code=ruff_exit,
            stdout=test_exec.stdout,
            stderr=test_exec.stderr,
            timed_out=False,
            error_message=None,
        )
