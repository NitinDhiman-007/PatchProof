"""Integration and unit tests for Phase 3: Repository understanding, patch validation, and LangGraph workflow."""

import json
import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database.database import get_db_connection, init_db
from app.main import app
from app.services.patch_service import PatchService, PatchValidationError
from app.services.repository_service import create_git_repository
from app.services.repository_understanding import CodeRetriever, RepositoryIndex
from app.services.test_runner import TestExecutionSummary
from app.services.workflow_engine import run_debugging_workflow

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_repository_indexing_and_symbol_extraction():
    """Verify repository indexer extracts files and AST symbols without code execution."""
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    assert os.path.isdir(demo_dir), "Demo repository directory must exist"

    index = RepositoryIndex(demo_dir)
    index.build_index()

    # Must find calculator and test files
    assert any("discount.py" in f for f in index.files)
    assert any("test_discount.py" in f for f in index.files)

    # Must extract calculate_discount symbol
    assert "calculate_discount" in index.all_symbols


def test_code_retriever_locates_defect_function():
    """Verify retriever finds relevant code based on bug description keywords."""
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    index = RepositoryIndex(demo_dir)
    index.build_index()

    retriever = CodeRetriever(index)
    snippets = retriever.retrieve_relevant_snippets(
        bug_description="The function calculate_discount returns an incorrect result when discount is a percentage.",
        stack_trace=None,
    )

    assert len(snippets) > 0
    top = snippets[0]
    assert "discount.py" in top["file_path"]
    assert "calculate_discount" in top["code"]
    assert top["start_line"] >= 1


def test_patch_validation_success():
    """Valid unified diff passes security and syntax validation."""
    valid_diff = """--- a/calculator/discount.py
+++ b/calculator/discount.py
@@ -8,3 +8,6 @@
-    return price - (price * discount)
+    rate = discount / 100.0 if discount > 1.0 else discount
+    return price - (price * rate)
"""
    affected = PatchService.validate_patch_security(valid_diff)
    assert affected == ["calculator/discount.py"]


def test_patch_validation_rejects_path_traversal():
    """Rejects diffs attempting directory traversal."""
    traversal_diff = """--- a/../../etc/passwd
+++ b/../../etc/passwd
@@ -1,1 +1,1 @@
-root
+hacked
"""
    with pytest.raises(PatchValidationError) as exc_info:
        PatchService.validate_patch_security(traversal_diff)
    assert "traversal" in str(exc_info.value).lower()


def test_patch_validation_rejects_restricted_files():
    """Rejects diffs targeting sensitive configuration files."""
    env_diff = """--- a/.env
+++ b/.env
@@ -1,1 +1,1 @@
-SECRET=123
+SECRET=456
"""
    with pytest.raises(PatchValidationError) as exc_info:
        PatchService.validate_patch_security(env_diff)
    assert "restricted file" in str(exc_info.value).lower()


def test_patch_application_in_temp_workspace(tmp_path):
    """Verify diff applicator updates file content cleanly without host damage."""
    file_path = tmp_path / "calc.py"
    file_path.write_text("def discount(p, d):\n    return p - (p * d)\n", encoding="utf-8")

    diff = """--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,3 @@
 def discount(p, d):
-    return p - (p * d)
+    r = d / 100.0 if d > 1 else d
+    return p - (p * r)
"""
    result = PatchService.apply_patch_to_workspace(str(tmp_path), diff)
    assert result["success"] is True
    assert "calc.py" in result["applied_files"]

    updated_content = file_path.read_text(encoding="utf-8")
    assert "r = d / 100.0" in updated_content
    assert "return p - (p * r)" in updated_content


def test_human_approval_api_workflow():
    """Verify explicit human approval endpoint transitions and persists patch status."""
    repo = create_git_repository("https://github.com/org/test-approval-repo")

    # Start analysis
    start_res = client.post(
        "/api/v1/analysis/start",
        json={
            "repository_id": repo.id,
            "bug_description": "Observed arithmetic calculation issue in parser",
        },
    )
    assert start_res.status_code == 201
    analysis_id = start_res.json()["id"]

    # Manually store a proposed patch diff in database
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE analysis_runs SET patch_diff = '--- a/f.py\\n+++ b/f.py\\n@@ -1,1 +1,1 @@\\n-1\\n+2', patch_status = 'pending_approval' WHERE id = ?;",
            (analysis_id,),
        )

    # Approve patch
    approve_res = client.post(
        f"/api/v1/analysis/{analysis_id}/patch/approve",
        json={"status": "approved", "comment": "Reviewed by Senior Engineer. Verified math."},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["patch_status"] == "approved"

    # Check status endpoint
    get_res = client.get(f"/api/v1/analysis/{analysis_id}")
    assert get_res.json()["patch_status"] == "approved"


def test_model_status_endpoint():
    """Verify model status endpoint returns structured diagnostic response."""
    response = client.get("/api/v1/analysis/model/status")
    assert response.status_code == 200
    data = response.json()
    assert "configured" in data
    assert "reachable" in data
    assert "model" in data
    assert "base_url" in data


def test_langgraph_workflow_state_transitions(monkeypatch, tmp_path):
    """
    Test end-to-end LangGraph state transitions:
    1. Baseline test fails -> Bug reproduced
    2. Patch generated and validated
    3. Patch applied to isolated workspace
    4. Patched test passes -> Verdict VERIFIED
    """
    from app.core.config import Settings
    mock_settings = Settings(WORKSPACE_BASE_DIR=str(tmp_path))
    monkeypatch.setattr("app.services.workflow_engine.get_settings", lambda: mock_settings)
    monkeypatch.setattr("app.core.execution_policy.get_settings", lambda: mock_settings)

    repo = create_git_repository("https://github.com/org/test-full-pipeline")
    import json
    with get_db_connection() as conn:
        conn.cursor().execute(
            "UPDATE repositories SET metadata_json = ? WHERE id = ?;",
            (json.dumps({"source_directory": os.path.abspath("examples/demo_discount_repo")}), repo.id),
        )

    # Mock BharatCode service methods
    mock_bcs = MagicMock()
    mock_bcs.generate_root_cause_analysis.return_value = {
        "problem_summary": "Discount percentage treated as raw multiplier",
        "suspected_root_cause": "Missing division by 100",
        "affected_files": [{"file_path": "calculator/discount.py", "line_numbers": [10]}],
        "explanation": "Calculates negative price",
        "confidence_score": 0.95,
        "confidence_explanation": "Deterministic calculation bug",
        "proposed_correction_strategy": "Divide by 100",
    }
    mock_bcs.generate_reproduction_test.return_value = {
        "test_file_path": "tests/test_reproduce_patchproof.py",
        "test_code": "def test_reproduce():\n    assert False, 'Bug reproduced: expected 800 but got -19000'\n",
        "test_explanation": "Reproduces bug by asserting expected discount result",
    }
    mock_bcs.generate_patch.return_value = {
        "summary": "Divide discount by 100 when supplied as percentage",
        "rationale": "Prevents negative price",
        "affected_files": ["calculator/discount.py"],
        "patch_diff": """--- a/calculator/discount.py
+++ b/calculator/discount.py
@@ -1,2 +1,3 @@
 def calculate_discount(price, discount):
-    return price - (price * discount)
+    rate = discount / 100.0 if discount > 1.0 else discount
+    return price - (price * rate)
""",
    }
    monkeypatch.setattr("app.services.workflow_engine.get_bharatcode_service", lambda: mock_bcs)

    # Mock TestRunner:
    # First call (baseline): fails
    # Second call (patched): passes
    mock_runner = MagicMock()
    baseline_summary = TestExecutionSummary(
        status="failed",
        command="pytest",
        exit_code=1,
        duration_seconds=0.45,
        tests_passed=1,
        tests_failed=1,
        stdout="FAILED tests/test_reproduce_patchproof.py::test_reproduce - AssertionError: Bug reproduced",
    )
    patched_summary = TestExecutionSummary(
        status="passed",
        command="pytest",
        exit_code=0,
        duration_seconds=0.52,
        tests_passed=2,
        tests_failed=0,
        ruff_passed=True,
        stdout="2 passed in 0.52s",
    )
    mock_runner.run_test_suite.side_effect = [baseline_summary, patched_summary]
    monkeypatch.setattr("app.services.workflow_engine.TestRunner", lambda: mock_runner)

    # Run workflow
    final_state = run_debugging_workflow(
        analysis_id="test-run-12345",
        repository_id=repo.id,
        bug_description="Percentage discount returns negative result",
    )

    assert final_state["verdict"] == "VERIFIED"
    assert final_state["baseline_reproduced"] is True
    assert final_state["patched_all_passed"] is True
    assert final_state["evidence_report"] is not None

    # Verify audit events recorded in database
    events_res = client.get(f"/api/v1/analysis/{final_state['analysis_id']}/events")
    assert events_res.status_code == 200
    events = events_res.json()
    assert len(events) >= 10
    step_names = [e["step_name"] for e in events]
    assert "load_context" in step_names
    assert "root_cause" in step_names
    assert "generate_test" in step_names
    assert "verify_baseline" in step_names
    assert "generate_patch" in step_names
    assert "verify_docker" in step_names
    assert "compare_regression" in step_names
    assert "compile_evidence" in step_names


def test_langgraph_workflow_inconclusive_when_test_passes(monkeypatch, tmp_path):
    """
    Test proof contract: If generated test unexpectedly passes on baseline,
    the bug was not reproduced, and the verdict MUST be INCONCLUSIVE.
    """
    from app.core.config import Settings
    mock_settings = Settings(WORKSPACE_BASE_DIR=str(tmp_path))
    monkeypatch.setattr("app.services.workflow_engine.get_settings", lambda: mock_settings)
    monkeypatch.setattr("app.core.execution_policy.get_settings", lambda: mock_settings)

    repo = create_git_repository("https://github.com/org/test-inconclusive")
    with get_db_connection() as conn:
        conn.cursor().execute(
            "UPDATE repositories SET metadata_json = ? WHERE id = ?;",
            (json.dumps({"source_directory": os.path.abspath("examples/demo_discount_repo")}), repo.id),
        )

    mock_bcs = MagicMock()
    mock_bcs.generate_root_cause_analysis.return_value = {
        "problem_summary": "Ambiguous issue",
        "suspected_root_cause": "Unknown",
        "affected_files": [],
        "explanation": "No clear fault",
        "confidence_score": 0.3,
        "confidence_explanation": "Low confidence",
        "proposed_correction_strategy": "None",
    }
    mock_bcs.generate_reproduction_test.return_value = {
        "test_file_path": "tests/test_reproduce_patchproof.py",
        "test_code": "def test_reproduce(): assert True\n",
        "test_explanation": "Test that inadvertently passes",
    }
    mock_bcs.generate_patch.return_value = {
        "summary": "No-op patch",
        "rationale": "None",
        "affected_files": ["calculator/discount.py"],
        "patch_diff": """--- a/calculator/discount.py
+++ b/calculator/discount.py
@@ -1,1 +1,1 @@
-def f(): pass
+def f(): pass
""",
    }
    monkeypatch.setattr("app.services.workflow_engine.get_bharatcode_service", lambda: mock_bcs)

    # Runner always returns passing exit_code=0
    mock_runner = MagicMock()
    passing_summary = TestExecutionSummary(
        status="passed",
        command="pytest",
        exit_code=0,
        duration_seconds=0.3,
        tests_passed=1,
        tests_failed=0,
        stdout="1 passed",
    )
    mock_runner.run_test_suite.return_value = passing_summary
    monkeypatch.setattr("app.services.workflow_engine.TestRunner", lambda: mock_runner)

    final_state = run_debugging_workflow(
        analysis_id="test-run-inconclusive",
        repository_id=repo.id,
        bug_description="Bug that is not reproduced by the test",
    )

    # Verification must NOT be VERIFIED
    assert final_state["verdict"] == "INCONCLUSIVE"
    assert final_state["baseline_reproduced"] is False
    assert "unproven" in final_state["verdict_explanation"].lower()

