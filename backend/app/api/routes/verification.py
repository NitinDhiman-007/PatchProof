"""Verification execution and evidence report API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.execution_policy import SecurityPolicyViolation
from app.core.logging import get_logger
from app.models.schemas import (
    VerificationLogsResponse,
    VerificationReportResponse,
    VerificationRunRequest,
    VerificationRunResponse,
)
from app.services.docker_sandbox import DockerSandbox
from app.services.verification_service import VerificationService

logger = get_logger(__name__)
router = APIRouter(prefix="/verification", tags=["Verification"])

verification_service = VerificationService()


@router.post(
    "/start",
    response_model=VerificationReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger an isolated verification run in Docker sandbox",
)
def start_verification(payload: VerificationRunRequest) -> VerificationReportResponse:
    """
    Start an isolated test execution pipeline inside a disposable Docker container.
    Enforces allowlisted commands, non-root user, network disabled, and strict resource quotas.
    Returns full evidence report.
    """
    try:
        report = verification_service.start_verification_run(
            repository_id=payload.repository_id,
            command_preset=payload.command,
            run_ruff=payload.run_ruff,
        )
        return VerificationReportResponse(**report)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except SecurityPolicyViolation as sec_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security Policy Violation: {str(sec_err)}",
        )
    except Exception as exc:
        logger.error("Failed to start verification run: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute verification: {str(exc)}",
        )


@router.get(
    "/docker/status",
    summary="Check Docker engine availability",
)
def check_docker_status() -> dict[str, Any]:
    """Check whether local Docker daemon is reachable for isolated execution."""
    sandbox = DockerSandbox()
    available, message = sandbox.is_available()
    return {
        "docker_available": available,
        "detail": message,
    }


@router.get(
    "",
    response_model=list[VerificationRunResponse],
    summary="List recent verification runs",
)
def list_verifications(limit: int = 50) -> list[VerificationRunResponse]:
    """Retrieve history of verification runs."""
    runs = verification_service.list_runs(limit=limit)
    return [
        VerificationRunResponse(
            id=run["id"],
            repository_id=run["repository_id"],
            repository_name=run.get("repository_name"),
            command=run["command"],
            status=run["status"],
            exit_code=run["exit_code"],
            duration_seconds=run["duration_seconds"] or 0.0,
            tests_passed=run["tests_passed"] or 0,
            tests_failed=run["tests_failed"] or 0,
            tests_skipped=run["tests_skipped"] or 0,
            tests_errors=run["tests_errors"] or 0,
            ruff_passed=bool(run["ruff_passed"]),
            error_message=run["error_message"],
            created_at=run["created_at"],
            completed_at=run["completed_at"],
        )
        for run in runs
    ]


@router.get(
    "/{run_id}",
    response_model=VerificationRunResponse,
    summary="Get verification run status",
)
def get_verification_status(run_id: str) -> VerificationRunResponse:
    """Retrieve summary status for a specific verification run."""
    run = verification_service.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification run '{run_id}' not found.",
        )
    return VerificationRunResponse(
        id=run["id"],
        repository_id=run["repository_id"],
        repository_name=run.get("repository_name"),
        command=run["command"],
        status=run["status"],
        exit_code=run["exit_code"],
        duration_seconds=run["duration_seconds"] or 0.0,
        tests_passed=run["tests_passed"] or 0,
        tests_failed=run["tests_failed"] or 0,
        tests_skipped=run["tests_skipped"] or 0,
        tests_errors=run["tests_errors"] or 0,
        ruff_passed=bool(run["ruff_passed"]),
        error_message=run["error_message"],
        created_at=run["created_at"],
        completed_at=run["completed_at"],
    )


@router.get(
    "/{run_id}/logs",
    response_model=VerificationLogsResponse,
    summary="Get stdout and stderr logs for a verification run",
)
def get_verification_logs(run_id: str) -> VerificationLogsResponse:
    """Retrieve raw execution output logs."""
    logs = verification_service.get_logs(run_id)
    if not logs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Logs for run '{run_id}' not found.",
        )
    return VerificationLogsResponse(**logs)


@router.get(
    "/{run_id}/report",
    response_model=VerificationReportResponse,
    summary="Get full evidence verification report",
)
def get_verification_report(run_id: str) -> VerificationReportResponse:
    """Retrieve the immutable evidence-backed verification report."""
    report = verification_service.get_report(run_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Verification report for run '{run_id}' not found.",
        )
    return VerificationReportResponse(**report)
