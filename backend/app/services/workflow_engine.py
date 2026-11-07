"""LangGraph multi-step agentic debugging and patch verification workflow engine."""

import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.core.execution_policy import validate_workspace_path
from app.core.logging import get_logger
from app.database.database import get_db_connection
from app.models.schemas import RepositoryResponse
from app.services.bharatcode_service import BharatCodeServiceError, get_bharatcode_service
from app.services.patch_service import PatchService, PatchValidationError
from app.services.repository_service import get_repository
from app.services.repository_understanding import CodeRetriever, RepositoryIndex
from app.services.test_runner import TestRunner

logger = get_logger(__name__)


class DebuggingState(TypedDict, total=False):
    """State schema for the LangGraph agent debugging workflow."""

    analysis_id: str
    repository_id: str
    repository_name: str
    bug_description: str
    issue_url: str | None
    stack_trace: str | None
    workspace_path: str
    patched_workspace_path: str
    repo_metadata: dict[str, Any]
    indexed_files: list[str]
    relevant_snippets: list[dict[str, Any]]
    root_cause: dict[str, Any] | None
    failing_test_code: str | None
    failing_test_path: str | None
    test_generation_attempts: int
    baseline_reproduced: bool
    baseline_summary: dict[str, Any] | None
    patch_diff: str | None
    patch_summary: str | None
    patch_rationale: str | None
    patch_validation: dict[str, Any] | None
    patch_attempts: int
    patched_regression_passed: bool
    patched_all_passed: bool
    patched_ruff_passed: bool
    patched_summary: dict[str, Any] | None
    verdict: str  # "VERIFIED", "FAILED", "INCONCLUSIVE", "ERROR"
    verdict_explanation: str
    evidence_report: dict[str, Any] | None
    error_message: str | None


def record_workflow_event(
    analysis_id: str,
    step_name: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Record an audit trail event for the debugging run in SQLite."""
    event_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    details_json = json.dumps(details) if details else None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO workflow_events (id, analysis_id, step_name, status, message, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (event_id, analysis_id, step_name, status, message, details_json, now),
            )
            # Also update the updated_at timestamp on analysis_runs
            cursor.execute(
                "UPDATE analysis_runs SET updated_at = ? WHERE id = ?;",
                (now, analysis_id),
            )
        logger.info("[Workflow %s] [%s] %s: %s", analysis_id[:8], step_name, status.upper(), message)
    except Exception as exc:
        logger.error("Failed to record workflow event: %s", exc)


def prepare_analysis_workspace(repo: RepositoryResponse, analysis_id: str, suffix: str = "base") -> str:
    """Create and populate an isolated ephemeral workspace for analysis."""
    settings = get_settings()
    base_dir = os.path.abspath(settings.WORKSPACE_BASE_DIR)
    os.makedirs(base_dir, exist_ok=True)

    target_dir = os.path.join(base_dir, f"analysis_{analysis_id}_{suffix}")
    valid_path = validate_workspace_path(target_dir, base_dir=base_dir)

    if os.path.exists(valid_path):
        shutil.rmtree(valid_path, ignore_errors=True)
    os.makedirs(valid_path, exist_ok=True)

    # Check if repository has source directory registered in metadata
    source_dir = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT metadata_json FROM repositories WHERE id = ?;", (repo.id,))
            row = cursor.fetchone()
            if row and row["metadata_json"]:
                meta = json.loads(row["metadata_json"])
                source_dir = meta.get("source_directory")
    except Exception as exc:
        logger.debug("Could not read repository source_directory from metadata: %s", exc)

    if not source_dir and ("demo" in repo.name.lower() or "discount" in repo.name.lower()):
        demo_candidate = os.path.abspath("examples/demo_discount_repo")
        if os.path.isdir(demo_candidate):
            source_dir = demo_candidate

    if source_dir and os.path.isdir(source_dir):
        # Copy source repo contents into ephemeral workspace
        for item in os.listdir(source_dir):
            s = os.path.join(source_dir, item)
            d = os.path.join(valid_path, item)
            if os.path.isdir(s):
                if item not in [".git", ".venv", "__pycache__", ".pytest_cache"]:
                    shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
    else:
        # Default minimal scaffold
        tests_dir = os.path.join(valid_path, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        init_file = os.path.join(valid_path, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w", encoding="utf-8") as f:
                f.write(f'"""Workspace for {repo.name}."""\n')

        # Baseline dummy test if none exists
        dummy_test = os.path.join(tests_dir, "test_baseline.py")
        if not os.path.exists(dummy_test):
            with open(dummy_test, "w", encoding="utf-8") as f:
                f.write("def test_baseline_environment():\n    assert True\n")

    return valid_path


# ==============================================================================
# LangGraph Workflow Nodes
# ==============================================================================


def node_load_context(state: DebuggingState) -> dict[str, Any]:
    """Node 1: Initialize isolated workspace and index repository source tree."""
    analysis_id = state["analysis_id"]
    repo_id = state["repository_id"]

    repo = get_repository(repo_id)
    if not repo:
        raise ValueError(f"Repository '{repo_id}' not found.")

    record_workflow_event(analysis_id, "load_context", "running", "Creating isolated workspace and indexing repository...")

    workspace_path = prepare_analysis_workspace(repo, analysis_id, suffix="base")
    index = RepositoryIndex(workspace_path)
    index.build_index()

    record_workflow_event(
        analysis_id,
        "load_context",
        "completed",
        f"Indexed {len(index.files)} files across repository ({len(index.symbols_by_file)} Python files).",
        {"files_count": len(index.files), "symbols_count": len(index.all_symbols)},
    )

    return {
        "repository_name": repo.name,
        "workspace_path": workspace_path,
        "indexed_files": index.files,
        "repo_metadata": {
            "name": repo.name,
            "detected_language": repo.detected_language,
            "source_type": repo.source_type,
            "file_count": len(index.files),
        },
    }


def node_analyze_bug(state: DebuggingState) -> dict[str, Any]:
    """Node 2: Parse and structure the incoming bug report and traceback."""
    analysis_id = state["analysis_id"]
    record_workflow_event(analysis_id, "analyze_bug", "running", "Analyzing bug report and extracting defect indicators...")

    # Validate inputs
    bug_desc = state["bug_description"]
    stack_trace = state.get("stack_trace")

    record_workflow_event(
        analysis_id,
        "analyze_bug",
        "completed",
        f"Extracted defect indicators (description length: {len(bug_desc)} chars, stack trace present: {bool(stack_trace)}).",
    )
    return {}


def node_retrieve_code(state: DebuggingState) -> dict[str, Any]:
    """Node 3: Retrieve line-numbered code snippets grounded in the bug description."""
    analysis_id = state["analysis_id"]
    workspace_path = state["workspace_path"]
    record_workflow_event(analysis_id, "retrieve_code", "running", "Retrieving relevant source code snippets...")

    index = RepositoryIndex(workspace_path)
    index.build_index()
    retriever = CodeRetriever(index)

    snippets = retriever.retrieve_relevant_snippets(
        bug_description=state["bug_description"],
        stack_trace=state.get("stack_trace"),
        max_snippets=5,
    )

    file_summary = [s["file_path"] for s in snippets]
    record_workflow_event(
        analysis_id,
        "retrieve_code",
        "completed",
        f"Retrieved {len(snippets)} relevant code snippets: {', '.join(file_summary) if file_summary else 'None'}",
        {"retrieved_files": file_summary},
    )

    return {"relevant_snippets": snippets}


def node_root_cause(state: DebuggingState) -> dict[str, Any]:
    """Node 4: Analyze defect root cause using BharatCode model."""
    analysis_id = state["analysis_id"]
    record_workflow_event(analysis_id, "root_cause", "running", "Consulting BharatCode model for root cause analysis...")

    settings = get_settings()
    is_demo = settings.DEMO_MODE or (
        not settings.BHARATCODE_API_KEY.strip()
        and "discount" in state.get("bug_description", "").lower()
    )

    try:
        if is_demo:
            rca = {
                "problem_summary": "[DEMO MODE] Discount percentage treated as raw multiplier",
                "suspected_root_cause": (
                    "[DEMO MODE] Missing percentage normalization in calculator/discount.py: "
                    "calculate_discount expects decimal fractions (e.g. 0.20) but received integer percentage (e.g. 20)."
                ),
                "affected_files": [{"file_path": "calculator/discount.py", "line_numbers": [11]}],
                "explanation": (
                    "[DEMO MODE] When discount=20 is passed for 20% discount on price=1000, "
                    "price - (price * discount) evaluates to 1000 - 20000 = -19000 instead of 800.0."
                ),
                "confidence_score": 0.99,
                "confidence_explanation": "[DEMO MODE] Deterministic reproduction of arithmetic defect.",
                "proposed_correction_strategy": "Normalize discount: if discount > 1.0, discount = discount / 100.0.",
            }
        else:
            service = get_bharatcode_service()
            rca = service.generate_root_cause_analysis(
                bug_description=state["bug_description"],
                stack_trace=state.get("stack_trace"),
                code_snippets=state.get("relevant_snippets", []),
                repo_metadata=state.get("repo_metadata", {}),
            )

        conf = rca.get("confidence_score", 0.5)
        summary = rca.get("problem_summary", "Analysis completed.")
        record_workflow_event(
            analysis_id,
            "root_cause",
            "completed",
            f"Root cause identified: {summary} (Confidence: {int(conf * 100)}%)",
            rca,
        )

        # Update SQLite analysis_runs table with root cause
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE analysis_runs SET summary = ?, root_cause_json = ? WHERE id = ?;",
                (summary, json.dumps(rca), analysis_id),
            )

        return {"root_cause": rca}
    except BharatCodeServiceError as exc:
        record_workflow_event(analysis_id, "root_cause", "failed", f"BharatCode model call failed: {exc.message}")
        return {
            "root_cause": {
                "problem_summary": "Model analysis failed",
                "suspected_root_cause": exc.message,
                "affected_files": [],
                "confidence_score": 0.0,
                "confidence_explanation": exc.message,
                "proposed_correction_strategy": "Manual review required",
            },
            "error_message": exc.message,
        }


def node_generate_test(state: DebuggingState) -> dict[str, Any]:
    """Node 5: Generate an automated pytest regression test reproducing the defect."""
    analysis_id = state["analysis_id"]
    attempts = state.get("test_generation_attempts", 0) + 1
    record_workflow_event(
        analysis_id,
        "generate_test",
        "running",
        f"Generating regression reproduction test (Attempt #{attempts})...",
    )

    settings = get_settings()
    is_demo = settings.DEMO_MODE or (
        not settings.BHARATCODE_API_KEY.strip()
        and "discount" in state.get("bug_description", "").lower()
    )

    try:
        if is_demo:
            test_data = {
                "test_code": (
                    '"""Reproducible failing test for discount calculation bug [DEMO MODE]."""\n\n'
                    "from calculator.discount import calculate_discount\n\n\n"
                    "def test_reproduce_percentage_discount_bug():\n"
                    '    """Test passing 20 for 20% discount on 1000 produces 800.0."""\n'
                    "    assert calculate_discount(1000.0, 20.0) == 800.0\n"
                ),
                "test_file_path": "tests/test_reproduce_discount_bug.py",
                "test_explanation": "[DEMO MODE] Verifies that calculate_discount(1000, 20) yields 800.0.",
            }
        else:
            service = get_bharatcode_service()
            existing_tests = [f for f in state.get("indexed_files", []) if "test" in f]
            test_data = service.generate_reproduction_test(
                bug_description=state["bug_description"],
                stack_trace=state.get("stack_trace"),
                root_cause=state.get("root_cause") or {},
                code_snippets=state.get("relevant_snippets", []),
                existing_test_paths=existing_tests,
            )

        test_code = test_data.get("test_code", "")
        test_path = test_data.get("test_file_path", "tests/test_reproduce_patchproof.py")

        # Write generated test into workspace
        full_test_path = os.path.join(state["workspace_path"], test_path)
        os.makedirs(os.path.dirname(full_test_path), exist_ok=True)
        with open(full_test_path, "w", encoding="utf-8") as f:
            f.write(test_code)

        record_workflow_event(
            analysis_id,
            "generate_test",
            "completed",
            f"Generated test '{test_path}' ({len(test_code.splitlines())} lines).",
            {"test_path": test_path, "explanation": test_data.get("test_explanation")},
        )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE analysis_runs
                SET reproduction_test_code = ?, reproduction_test_path = ?
                WHERE id = ?;
                """,
                (test_code, test_path, analysis_id),
            )

        return {
            "failing_test_code": test_code,
            "failing_test_path": test_path,
            "test_generation_attempts": attempts,
        }
    except BharatCodeServiceError as exc:
        record_workflow_event(analysis_id, "generate_test", "failed", f"Failed to generate test: {exc.message}")
        return {
            "test_generation_attempts": attempts,
            "error_message": exc.message,
        }


def node_verify_baseline(state: DebuggingState) -> dict[str, Any]:
    """Node 6: Run the generated test in the Docker sandbox against the unmodified baseline."""
    analysis_id = state["analysis_id"]
    test_path = state.get("failing_test_path", "tests/test_reproduce_patchproof.py")
    record_workflow_event(
        analysis_id,
        "verify_baseline",
        "running",
        f"Executing baseline verification in Docker sandbox on '{test_path}'...",
    )

    runner = TestRunner()
    workspace_path = state["workspace_path"]

    summary = runner.run_test_suite(
        workspace_path,
        command_preset="pytest",
        run_ruff=False,
    )

    # Bug is successfully reproduced if the test fails (exit code != 0 or tests_failed > 0)
    reproduced = summary.exit_code != 0 or summary.tests_failed > 0

    if reproduced:
        msg = f"Bug successfully reproduced! Baseline test failed as expected (Exit code: {summary.exit_code}, Failures: {summary.tests_failed})."
        record_workflow_event(analysis_id, "verify_baseline", "completed", msg, {
            "exit_code": summary.exit_code,
            "tests_failed": summary.tests_failed,
            "tests_passed": summary.tests_passed,
            "stdout": summary.stdout[:500],
        })
    else:
        msg = f"Bug was NOT reproduced: test unexpectedly passed on unmodified baseline (Exit code: {summary.exit_code})."
        record_workflow_event(analysis_id, "verify_baseline", "warning", msg, {
            "exit_code": summary.exit_code,
            "tests_passed": summary.tests_passed,
        })

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE analysis_runs SET baseline_reproduced = ? WHERE id = ?;",
            (1 if reproduced else 0, analysis_id),
        )

    return {
        "baseline_reproduced": reproduced,
        "baseline_summary": {
            "status": summary.status,
            "exit_code": summary.exit_code,
            "tests_failed": summary.tests_failed,
            "tests_passed": summary.tests_passed,
            "duration_seconds": summary.duration_seconds,
            "stdout": summary.stdout,
            "stderr": summary.stderr,
        },
    }


def node_generate_patch(state: DebuggingState) -> dict[str, Any]:
    """Node 7: Generate minimal unified diff patch using BharatCode model."""
    analysis_id = state["analysis_id"]
    attempts = state.get("patch_attempts", 0) + 1
    record_workflow_event(
        analysis_id,
        "generate_patch",
        "running",
        f"Synthesizing candidate patch via BharatCode model (Attempt #{attempts})...",
    )

    settings = get_settings()
    is_demo = settings.DEMO_MODE or (
        not settings.BHARATCODE_API_KEY.strip()
        and "discount" in state.get("bug_description", "").lower()
    )

    try:
        if is_demo:
            diff = (
                "--- a/calculator/discount.py\n"
                "+++ b/calculator/discount.py\n"
                "@@ -8,4 +8,6 @@\n"
                "     Bug: Assumes discount is always a decimal (e.g. 0.20) rather than a percentage (e.g. 20).\n"
                "     When 20 is passed for a 20% discount, it returns a negative or incorrect price.\n"
                '     """\n'
                "+    if discount > 1.0:\n"
                "+        discount = discount / 100.0\n"
                "     return price - (price * discount)\n"
            )
            patch_data = {
                "patch_diff": diff,
                "summary": "[DEMO MODE] Normalize percentage discounts > 1.0 to decimal fractions",
                "rationale": "[DEMO MODE] Corrects negative price calculation when integer percentages are passed.",
                "affected_files": ["calculator/discount.py"],
            }
        else:
            service = get_bharatcode_service()
            baseline_out = state.get("baseline_summary", {}).get("stdout", "")
            patch_data = service.generate_patch(
                bug_description=state["bug_description"],
                root_cause=state.get("root_cause") or {},
                reproduction_test_code=state.get("failing_test_code", ""),
                code_snippets=state.get("relevant_snippets", []),
                baseline_failure_output=baseline_out,
            )

        diff = patch_data.get("patch_diff", "")
        summary = patch_data.get("summary", "Patch generated")
        rationale = patch_data.get("rationale", "")

        record_workflow_event(
            analysis_id,
            "generate_patch",
            "completed",
            f"Generated patch: {summary} ({len(diff.splitlines())} diff lines).",
            {"summary": summary, "rationale": rationale, "affected_files": patch_data.get("affected_files", [])},
        )

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE analysis_runs SET patch_diff = ?, patch_status = 'pending_approval' WHERE id = ?;",
                (diff, analysis_id),
            )

        return {
            "patch_diff": diff,
            "patch_summary": summary,
            "patch_rationale": rationale,
            "patch_attempts": attempts,
        }
    except BharatCodeServiceError as exc:
        record_workflow_event(analysis_id, "generate_patch", "failed", f"Failed to generate patch: {exc.message}")
        return {
            "patch_attempts": attempts,
            "error_message": exc.message,
        }


def node_validate_patch(state: DebuggingState) -> dict[str, Any]:
    """Node 8: Validate proposed patch against unified diff syntax and security rules."""
    analysis_id = state["analysis_id"]
    diff = state.get("patch_diff", "")
    record_workflow_event(analysis_id, "validate_patch", "running", "Validating patch security, syntax, and boundaries...")

    try:
        affected = PatchService.validate_patch_security(diff)
        parsed = PatchService.parse_unified_diff(diff)
        hunk_count = sum(len(f.hunks) for f in parsed)

        record_workflow_event(
            analysis_id,
            "validate_patch",
            "completed",
            f"Patch syntax & security valid. Targets {len(affected)} file(s), {hunk_count} hunk(s).",
            {"affected_files": affected, "hunks": hunk_count},
        )

        return {
            "patch_validation": {
                "is_valid": True,
                "affected_files": affected,
                "hunk_count": hunk_count,
            }
        }
    except PatchValidationError as exc:
        record_workflow_event(analysis_id, "validate_patch", "failed", f"Patch validation rejected: {exc!s}")
        return {
            "patch_validation": {
                "is_valid": False,
                "error": str(exc),
                "affected_files": [],
            }
        }


def node_apply_isolated_patch(state: DebuggingState) -> dict[str, Any]:
    """Node 9: Clone baseline workspace to patched workspace and apply diff safely."""
    analysis_id = state["analysis_id"]
    base_ws = state["workspace_path"]
    diff = state.get("patch_diff", "")
    record_workflow_event(analysis_id, "apply_patch", "running", "Creating separate workspace and applying diff...")

    # Clone base workspace to patched workspace
    settings = get_settings()
    base_dir = os.path.abspath(settings.WORKSPACE_BASE_DIR)
    patched_ws = os.path.join(base_dir, f"analysis_{analysis_id}_patched")
    valid_patched = validate_workspace_path(patched_ws, base_dir=base_dir)

    if os.path.exists(valid_patched):
        shutil.rmtree(valid_patched, ignore_errors=True)
    shutil.copytree(base_ws, valid_patched, dirs_exist_ok=True)

    try:
        result = PatchService.apply_patch_to_workspace(valid_patched, diff)
        record_workflow_event(
            analysis_id,
            "apply_patch",
            "completed",
            f"Successfully applied diff to {len(result['applied_files'])} file(s) in isolated workspace.",
            result,
        )
        return {"patched_workspace_path": valid_patched}
    except Exception as exc:
        record_workflow_event(analysis_id, "apply_patch", "failed", f"Failed to apply patch: {exc!s}")
        return {"error_message": f"Patch application failed: {exc!s}"}


def node_verify_docker(state: DebuggingState) -> dict[str, Any]:
    """Node 10: Run isolated Docker verification on the patched workspace."""
    analysis_id = state["analysis_id"]
    patched_ws = state.get("patched_workspace_path")
    if not patched_ws or not os.path.isdir(patched_ws):
        record_workflow_event(analysis_id, "verify_docker", "failed", "Patched workspace missing or invalid.")
        return {"patched_regression_passed": False, "patched_all_passed": False}

    record_workflow_event(
        analysis_id,
        "verify_docker",
        "running",
        "Running regression test suite and Ruff static analysis inside Docker sandbox...",
    )

    runner = TestRunner()
    summary = runner.run_test_suite(
        patched_ws,
        command_preset="pytest",
        run_ruff=True,
    )

    # Verification criteria:
    # 1. Exit code == 0 (all tests passed)
    # 2. No test failures (tests_failed == 0)
    all_passed = summary.exit_code == 0 and summary.tests_failed == 0
    regression_passed = summary.tests_failed == 0

    record_workflow_event(
        analysis_id,
        "verify_docker",
        "completed",
        f"Docker verification finished: Passed={summary.tests_passed}, Failed={summary.tests_failed}, Ruff={summary.ruff_passed}.",
        {
            "exit_code": summary.exit_code,
            "tests_passed": summary.tests_passed,
            "tests_failed": summary.tests_failed,
            "ruff_passed": summary.ruff_passed,
            "duration": summary.duration_seconds,
        },
    )

    return {
        "patched_regression_passed": regression_passed,
        "patched_all_passed": all_passed,
        "patched_ruff_passed": summary.ruff_passed,
        "patched_summary": {
            "status": summary.status,
            "exit_code": summary.exit_code,
            "tests_passed": summary.tests_passed,
            "tests_failed": summary.tests_failed,
            "ruff_passed": summary.ruff_passed,
            "ruff_issues": summary.ruff_issues,
            "duration_seconds": summary.duration_seconds,
            "stdout": summary.stdout,
            "stderr": summary.stderr,
        },
    }


def node_compare_regression(state: DebuggingState) -> dict[str, Any]:
    """Node 11: Compare baseline reproduction vs patched execution to determine proof verdict."""
    analysis_id = state["analysis_id"]
    record_workflow_event(analysis_id, "compare_regression", "running", "Evaluating proof contract and comparing baseline vs patched runs...")

    baseline_reproduced = state.get("baseline_reproduced", False)
    patched_passed = state.get("patched_all_passed", False)
    patched_regression_passed = state.get("patched_regression_passed", False)
    ruff_passed = state.get("patched_ruff_passed", True)
    err = state.get("error_message")

    if err:
        verdict = "ERROR"
        explanation = f"Workflow encountered an unrecoverable error: {err}"
    elif not baseline_reproduced:
        verdict = "INCONCLUSIVE"
        explanation = "The generated regression test passed on the unmodified baseline repository. Bug reproduction was unproven."
    elif patched_regression_passed and patched_passed and ruff_passed:
        verdict = "VERIFIED"
        explanation = "Bug reproduced on baseline, fixed by patch, regression test turned green, and full test suite & static checks passed."
    elif not patched_regression_passed or not patched_passed:
        verdict = "FAILED"
        explanation = "Patch failed verification: the regression test or existing test suite failed inside the Docker sandbox."
    else:
        verdict = "INCONCLUSIVE"
        explanation = "Verification results were ambiguous or incomplete."

    record_workflow_event(
        analysis_id,
        "compare_regression",
        "completed",
        f"Verdict: {verdict}. {explanation}",
        {"verdict": verdict, "explanation": explanation},
    )

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE analysis_runs SET verification_verdict = ?, status = ? WHERE id = ?;",
            (verdict, "completed" if verdict != "ERROR" else "failed", analysis_id),
        )

    return {"verdict": verdict, "verdict_explanation": explanation}


def node_compile_evidence(state: DebuggingState) -> dict[str, Any]:
    """Node 12: Assemble final immutable evidence report and clean up ephemeral workspaces."""
    analysis_id = state["analysis_id"]
    now = datetime.now(UTC).isoformat()
    record_workflow_event(analysis_id, "compile_evidence", "running", "Compiling immutable verification evidence report...")

    settings = get_settings()
    evidence_report = {
        "analysis_id": analysis_id,
        "repository_id": state["repository_id"],
        "repository_name": state.get("repository_name", "Unknown"),
        "verdict": state.get("verdict", "INCONCLUSIVE"),
        "verdict_explanation": state.get("verdict_explanation", ""),
        "timestamp": now,
        "environment": f"Docker Sandbox ({settings.DOCKER_PYTHON_IMAGE}, network: none, user: 1000:1000)",
        "defect": {
            "description": state["bug_description"],
            "issue_url": state.get("issue_url"),
            "stack_trace": state.get("stack_trace"),
        },
        "root_cause_analysis": state.get("root_cause"),
        "reproduction_test": {
            "path": state.get("failing_test_path"),
            "code": state.get("failing_test_code"),
            "baseline_reproduced": state.get("baseline_reproduced", False),
            "baseline_results": state.get("baseline_summary"),
        },
        "proposed_patch": {
            "summary": state.get("patch_summary"),
            "rationale": state.get("patch_rationale"),
            "diff": state.get("patch_diff"),
            "validation": state.get("patch_validation"),
        },
        "patched_verification": state.get("patched_summary"),
    }

    # Deterministic SHA-256 cryptographic digest of agent debugging verification outcome
    import hashlib

    digest_payload = json.dumps(
        {
            "analysis_id": analysis_id,
            "repository_id": state["repository_id"],
            "verdict": state.get("verdict", "INCONCLUSIVE"),
            "baseline_reproduced": state.get("baseline_reproduced", False),
            "patch_diff": state.get("patch_diff"),
            "timestamp": now,
        },
        sort_keys=True,
    )
    evidence_report["integrity_hash"] = f"sha256:{hashlib.sha256(digest_payload.encode('utf-8')).hexdigest()}"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE analysis_runs SET evidence_report_json = ? WHERE id = ?;",
            (json.dumps(evidence_report), analysis_id),
        )

    # Clean up ephemeral workspaces
    for ws_key in ["workspace_path", "patched_workspace_path"]:
        p = state.get(ws_key)
        if p and os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True)

    record_workflow_event(
        analysis_id,
        "compile_evidence",
        "completed",
        "Evidence report compiled, persisted to SQLite, and ephemeral workspaces cleaned.",
    )

    return {"evidence_report": evidence_report}


# ==============================================================================
# Conditional Routing Functions
# ==============================================================================


def route_after_baseline(state: DebuggingState) -> str:
    """Route: If baseline did not reproduce bug and attempts < 2, retry test generation.
    If bug cannot be reproduced after retry limit, terminate with INCONCLUSIVE."""
    if not state.get("baseline_reproduced"):
        if state.get("test_generation_attempts", 0) < 2:
            return "generate_test"
        return "compare_regression"
    return "generate_patch"


def route_after_patch_validation(state: DebuggingState) -> str:
    """Route: If patch is invalid and attempts < 2, retry patch generation."""
    validation = state.get("patch_validation") or {}
    if not validation.get("is_valid", False):
        if state.get("patch_attempts", 0) < 2:
            return "generate_patch"
        return "compare_regression"
    return "apply_patch"


# ==============================================================================
# Graph Construction & Workflow Runner
# ==============================================================================


def build_debugging_graph() -> Any:
    """Build and compile the LangGraph agent state graph."""
    builder = StateGraph(DebuggingState)

    # Add all 12 nodes
    builder.add_node("load_context", node_load_context)
    builder.add_node("analyze_bug", node_analyze_bug)
    builder.add_node("retrieve_code", node_retrieve_code)
    builder.add_node("root_cause", node_root_cause)
    builder.add_node("generate_test", node_generate_test)
    builder.add_node("verify_baseline", node_verify_baseline)
    builder.add_node("generate_patch", node_generate_patch)
    builder.add_node("validate_patch", node_validate_patch)
    builder.add_node("apply_patch", node_apply_isolated_patch)
    builder.add_node("verify_docker", node_verify_docker)
    builder.add_node("compare_regression", node_compare_regression)
    builder.add_node("compile_evidence", node_compile_evidence)

    # Edges
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "analyze_bug")
    builder.add_edge("analyze_bug", "retrieve_code")
    builder.add_edge("retrieve_code", "root_cause")
    builder.add_edge("root_cause", "generate_test")
    builder.add_edge("generate_test", "verify_baseline")

    builder.add_conditional_edges(
        "verify_baseline",
        route_after_baseline,
        {
            "generate_test": "generate_test",
            "generate_patch": "generate_patch",
            "compare_regression": "compare_regression",
        },
    )

    builder.add_edge("generate_patch", "validate_patch")

    builder.add_conditional_edges(
        "validate_patch",
        route_after_patch_validation,
        {
            "generate_patch": "generate_patch",
            "apply_patch": "apply_patch",
            "compare_regression": "compare_regression",
        },
    )

    builder.add_edge("apply_patch", "verify_docker")
    builder.add_edge("verify_docker", "compare_regression")
    builder.add_edge("compare_regression", "compile_evidence")
    builder.add_edge("compile_evidence", END)

    return builder.compile()


# Singleton compiled graph
_compiled_workflow = None


def get_debugging_workflow():
    """Return singleton compiled LangGraph workflow instance."""
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = build_debugging_graph()
    return _compiled_workflow


def run_debugging_workflow(
    analysis_id: str,
    repository_id: str,
    bug_description: str,
    issue_url: str | None = None,
    stack_trace: str | None = None,
) -> dict[str, Any]:
    """Execute the full agentic debugging workflow synchronously or in background."""
    workflow = get_debugging_workflow()
    initial_state: DebuggingState = {
        "analysis_id": analysis_id,
        "repository_id": repository_id,
        "bug_description": bug_description,
        "issue_url": issue_url,
        "stack_trace": stack_trace,
        "test_generation_attempts": 0,
        "patch_attempts": 0,
    }

    try:
        final_state = workflow.invoke(initial_state)
        return final_state
    except Exception as exc:
        logger.error("Workflow failed with unhandled exception: %s", exc, exc_info=True)
        record_workflow_event(analysis_id, "workflow", "failed", f"Workflow execution error: {exc!s}")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE analysis_runs SET status = 'failed', verification_verdict = 'ERROR' WHERE id = ?;",
                (analysis_id,),
            )
        return {
            "analysis_id": analysis_id,
            "verdict": "ERROR",
            "error_message": str(exc),
        }
