"""Bug analysis, LangGraph agent workflow, and patch verification endpoints."""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.core.logging import get_logger
from app.database.database import get_db_connection
from app.models.schemas import (
    BugAnalysisRequest,
    BugAnalysisResponse,
    ModelStatusResponse,
    PatchApprovalRequest,
    PatchApprovalResponse,
    ProposedPatchResponse,
    ReproductionTestResponse,
    RootCauseResponse,
    WorkflowEventResponse,
)
from app.services.bharatcode_service import get_bharatcode_service
from app.services.patch_service import PatchService, PatchValidationError
from app.services.repository_service import get_repository
from app.services.workflow_engine import record_workflow_event, run_debugging_workflow

logger = get_logger(__name__)
router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.get(
    "/model/status",
    response_model=ModelStatusResponse,
    summary="Check BharatCode model connectivity and authentication status",
)
def get_model_status() -> ModelStatusResponse:
    """Verify connectivity to BharatCode API without throwing runtime errors."""
    service = get_bharatcode_service()
    data = service.check_connectivity()
    return ModelStatusResponse(
        configured=data.get("configured", False),
        reachable=data.get("reachable", False),
        model=data.get("model", ""),
        base_url=data.get("base_url", ""),
        message=data.get("message", ""),
        response_sample=data.get("response_sample"),
    )


@router.post(
    "/start",
    response_model=BugAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start an automated AI debugging and patch verification workflow",
)
def start_bug_analysis(
    payload: BugAnalysisRequest,
    background_tasks: BackgroundTasks,
) -> BugAnalysisResponse:
    """
    Initialize and dispatch a full 12-node LangGraph debugging workflow.
    Executes asynchronously in background to provide real-time event streaming.
    """
    repo = get_repository(payload.repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{payload.repository_id}' does not exist.",
        )

    analysis_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    summary = f"Workflow initialized for {repo.name}. Preparing repository context..."

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO analysis_runs (
                id, repository_id, bug_description, issue_url, stack_trace,
                status, summary, verification_verdict, patch_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'analyzing', ?, 'PENDING', 'none', ?, ?);
            """,
            (
                analysis_id,
                payload.repository_id,
                payload.bug_description,
                payload.issue_url,
                payload.stack_trace,
                summary,
                now,
                now,
            ),
        )

    # Initial workflow event
    record_workflow_event(
        analysis_id,
        "init",
        "completed",
        f"Workflow queued for repository '{repo.name}'.",
        {"repository_id": repo.id, "language": repo.detected_language},
    )

    # Enqueue background task
    background_tasks.add_task(
        run_debugging_workflow,
        analysis_id=analysis_id,
        repository_id=payload.repository_id,
        bug_description=payload.bug_description,
        issue_url=payload.issue_url,
        stack_trace=payload.stack_trace,
    )

    logger.info("Dispatched background debugging workflow %s for %s", analysis_id, repo.name)
    return BugAnalysisResponse(
        id=analysis_id,
        repository_id=payload.repository_id,
        bug_description=payload.bug_description,
        issue_url=payload.issue_url,
        stack_trace=payload.stack_trace,
        status="analyzing",
        summary=summary,
        patch_status="none",
        verification_verdict="PENDING",
        created_at=now,
        updated_at=now,
    )


@router.get(
    "",
    response_model=list[BugAnalysisResponse],
    summary="List recent bug analysis runs",
)
def list_analysis_runs(limit: int = 20) -> list[BugAnalysisResponse]:
    """Retrieve recent bug analysis records."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM analysis_runs ORDER BY created_at DESC LIMIT ?;",
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            BugAnalysisResponse(
                id=row["id"],
                repository_id=row["repository_id"],
                bug_description=row["bug_description"],
                issue_url=row["issue_url"],
                stack_trace=row["stack_trace"] if "stack_trace" in row.keys() else None,
                status=row["status"],
                summary=row["summary"],
                root_cause_json=row["root_cause_json"] if "root_cause_json" in row.keys() else None,
                reproduction_test_code=row["reproduction_test_code"] if "reproduction_test_code" in row.keys() else None,
                reproduction_test_path=row["reproduction_test_path"] if "reproduction_test_path" in row.keys() else None,
                baseline_reproduced=bool(row["baseline_reproduced"]) if "baseline_reproduced" in row.keys() else False,
                patch_diff=row["patch_diff"] if "patch_diff" in row.keys() else None,
                patch_status=row["patch_status"] if "patch_status" in row.keys() else "none",
                verification_verdict=row["verification_verdict"] if "verification_verdict" in row.keys() else "PENDING",
                evidence_report_json=row["evidence_report_json"] if "evidence_report_json" in row.keys() else None,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]


@router.get(
    "/{analysis_id}",
    response_model=BugAnalysisResponse,
    summary="Get analysis run details by ID",
)
def get_analysis_run(analysis_id: str) -> BugAnalysisResponse:
    """Retrieve details of a specific bug analysis run."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analysis_runs WHERE id = ?;", (analysis_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis run '{analysis_id}' not found.",
            )
        return BugAnalysisResponse(
            id=row["id"],
            repository_id=row["repository_id"],
            bug_description=row["bug_description"],
            issue_url=row["issue_url"],
            stack_trace=row["stack_trace"] if "stack_trace" in row.keys() else None,
            status=row["status"],
            summary=row["summary"],
            root_cause_json=row["root_cause_json"] if "root_cause_json" in row.keys() else None,
            reproduction_test_code=row["reproduction_test_code"] if "reproduction_test_code" in row.keys() else None,
            reproduction_test_path=row["reproduction_test_path"] if "reproduction_test_path" in row.keys() else None,
            baseline_reproduced=bool(row["baseline_reproduced"]) if "baseline_reproduced" in row.keys() else False,
            patch_diff=row["patch_diff"] if "patch_diff" in row.keys() else None,
            patch_status=row["patch_status"] if "patch_status" in row.keys() else "none",
            verification_verdict=row["verification_verdict"] if "verification_verdict" in row.keys() else "PENDING",
            evidence_report_json=row["evidence_report_json"] if "evidence_report_json" in row.keys() else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@router.get(
    "/{analysis_id}/events",
    response_model=list[WorkflowEventResponse],
    summary="Retrieve audit trail events for an analysis run",
)
def get_analysis_events(analysis_id: str) -> list[WorkflowEventResponse]:
    """Retrieve chronological event stream from LangGraph execution."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM workflow_events WHERE analysis_id = ? ORDER BY created_at ASC;",
            (analysis_id,),
        )
        rows = cursor.fetchall()
        return [
            WorkflowEventResponse(
                id=row["id"],
                analysis_id=row["analysis_id"],
                step_name=row["step_name"],
                status=row["status"],
                message=row["message"],
                details_json=row["details_json"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.get(
    "/{analysis_id}/root-cause",
    response_model=RootCauseResponse,
    summary="Retrieve structured root cause analysis",
)
def get_root_cause_analysis(analysis_id: str) -> RootCauseResponse:
    """Retrieve structured defect analysis generated by BharatCode model."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT root_cause_json FROM analysis_runs WHERE id = ?;", (analysis_id,))
        row = cursor.fetchone()
        if not row or not row["root_cause_json"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Root cause analysis not yet available or failed.",
            )

        data = json.loads(row["root_cause_json"])
        return RootCauseResponse(
            analysis_id=analysis_id,
            problem_summary=data.get("problem_summary", "Analysis completed"),
            suspected_root_cause=data.get("suspected_root_cause", ""),
            affected_files=data.get("affected_files", []),
            explanation=data.get("explanation", ""),
            confidence_score=float(data.get("confidence_score", 0.5)),
            confidence_explanation=data.get("confidence_explanation", ""),
            proposed_correction_strategy=data.get("proposed_correction_strategy", ""),
        )


@router.get(
    "/{analysis_id}/test",
    response_model=ReproductionTestResponse,
    summary="Retrieve generated regression test and baseline reproduction results",
)
def get_reproduction_test(analysis_id: str) -> ReproductionTestResponse:
    """Retrieve generated pytest reproduction test details."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT reproduction_test_code, reproduction_test_path, baseline_reproduced, evidence_report_json
            FROM analysis_runs WHERE id = ?;
            """,
            (analysis_id,),
        )
        row = cursor.fetchone()
        if not row or not row["reproduction_test_code"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reproduction test not yet generated.",
            )

        baseline_summary = None
        if row["evidence_report_json"]:
            try:
                rep = json.loads(row["evidence_report_json"])
                baseline_summary = rep.get("reproduction_test", {}).get("baseline_results")
            except Exception as exc:
                logger.debug("Could not parse baseline summary from evidence report: %s", exc)

        return ReproductionTestResponse(
            analysis_id=analysis_id,
            test_path=row["reproduction_test_path"] or "tests/test_reproduce_patchproof.py",
            test_code=row["reproduction_test_code"],
            baseline_reproduced=bool(row["baseline_reproduced"]),
            baseline_summary=baseline_summary,
        )


@router.get(
    "/{analysis_id}/patch",
    response_model=ProposedPatchResponse,
    summary="Retrieve proposed patch unified diff and audit metadata",
)
def get_proposed_patch(analysis_id: str) -> ProposedPatchResponse:
    """Retrieve proposed minimal unified diff patch."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT patch_diff, patch_status, evidence_report_json FROM analysis_runs WHERE id = ?;",
            (analysis_id,),
        )
        row = cursor.fetchone()
        if not row or not row["patch_diff"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proposed patch not yet available.",
            )

        diff = row["patch_diff"]
        patch_status_val = row["patch_status"] or "none"

        is_valid = True
        validation_err = None
        affected_files = []
        try:
            affected_files = PatchService.validate_patch_security(diff)
        except PatchValidationError as exc:
            is_valid = False
            validation_err = str(exc)

        summary = None
        rationale = None
        if row["evidence_report_json"]:
            try:
                rep = json.loads(row["evidence_report_json"])
                p = rep.get("proposed_patch", {})
                summary = p.get("summary")
                rationale = p.get("rationale")
            except Exception as exc:
                logger.debug("Could not parse patch summary from evidence report: %s", exc)

        return ProposedPatchResponse(
            analysis_id=analysis_id,
            patch_diff=diff,
            patch_status=patch_status_val,
            summary=summary,
            rationale=rationale,
            affected_files=affected_files,
            is_valid=is_valid,
            validation_error=validation_err,
        )


@router.post(
    "/{analysis_id}/patch/approve",
    response_model=PatchApprovalResponse,
    summary="Explicit human approval or rejection of proposed patch",
)
def approve_or_reject_patch(
    analysis_id: str,
    payload: PatchApprovalRequest,
) -> PatchApprovalResponse:
    """
    Enforce explicit human sign-off before patch export or finalization.
    Patches are never automatically committed.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, patch_diff FROM analysis_runs WHERE id = ?;", (analysis_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis run '{analysis_id}' not found.",
            )

        if not row["patch_diff"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot review patch: no patch has been generated for this run.",
            )

        new_status = payload.status
        now = datetime.now(UTC).isoformat()
        cursor.execute(
            "UPDATE analysis_runs SET patch_status = ?, updated_at = ? WHERE id = ?;",
            (new_status, now, analysis_id),
        )

    # Record event in audit trail
    record_workflow_event(
        analysis_id,
        "human_approval",
        "completed",
        f"Patch {new_status.upper()} by human operator. Comment: {payload.comment or 'None'}",
        {"status": new_status, "comment": payload.comment},
    )

    return PatchApprovalResponse(
        analysis_id=analysis_id,
        patch_status=new_status,
        message=f"Patch marked as '{new_status}' by operator.",
        updated_at=now,
    )


@router.get(
    "/{analysis_id}/evidence",
    summary="Retrieve final verification evidence report JSON",
)
def get_evidence_report(analysis_id: str) -> dict:
    """Retrieve full immutable evidence report comparing baseline and patched execution."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT evidence_report_json FROM analysis_runs WHERE id = ?;", (analysis_id,))
        row = cursor.fetchone()
        if not row or not row["evidence_report_json"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evidence report not yet compiled or workflow did not complete.",
            )
        return json.loads(row["evidence_report_json"])
