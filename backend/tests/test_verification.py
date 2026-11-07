"""Tests for verification API endpoints and workflow orchestration."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes import verification
from app.main import app
from app.services.repository_service import create_git_repository
from app.services.test_runner import TestExecutionSummary, TestRunner

client = TestClient(app)


def test_docker_status_endpoint():
    """Test GET /api/v1/verification/docker/status returns availability report."""
    response = client.get("/api/v1/verification/docker/status")
    assert response.status_code == 200
    data = response.json()
    assert "docker_available" in data
    assert "detail" in data
    assert isinstance(data["docker_available"], bool)


def test_start_verification_nonexistent_repository():
    """Test start verification rejects unknown repository with 404."""
    payload = {
        "repository_id": "non-existent-uuid",
        "command": "pytest",
    }
    response = client.post("/api/v1/verification/start", json=payload)
    assert response.status_code == 404


def test_start_verification_unauthorized_command():
    """Test start verification rejects non-allowlisted command with 400."""
    repo = create_git_repository("https://github.com/test/repo-security")
    payload = {
        "repository_id": repo.id,
        "command": "bash -c whoami",
    }
    response = client.post("/api/v1/verification/start", json=payload)
    assert response.status_code == 400
    assert "Security Policy Violation" in response.json()["detail"]


def test_verification_run_lifecycle_and_report(monkeypatch):
    """Test complete verification run, logs, and evidence report lifecycle."""
    repo = create_git_repository("https://github.com/psf/requests-verification-test")

    # Mock TestRunner to return deterministic evidence
    mock_runner = MagicMock(spec=TestRunner)
    mock_runner.run_test_suite.return_value = TestExecutionSummary(
        status="passed",
        command="pytest -v --tb=short",
        exit_code=0,
        duration_seconds=1.45,
        tests_passed=5,
        tests_failed=0,
        tests_skipped=0,
        ruff_passed=True,
        ruff_issues=[],
        stdout="5 passed in 1.45s",
        stderr="",
        timed_out=False,
    )

    monkeypatch.setattr(verification.verification_service, "runner", mock_runner)

    # 1. Trigger verification run
    payload = {
        "repository_id": repo.id,
        "command": "pytest",
        "run_ruff": True,
    }
    start_res = client.post("/api/v1/verification/start", json=payload)
    assert start_res.status_code == 201
    report_data = start_res.json()
    run_id = report_data["run_id"]

    assert report_data["repository_id"] == repo.id
    assert report_data["status"] == "passed"
    assert report_data["tests_passed"] == 5
    assert "Docker" in report_data["execution_environment"]

    # 2. Get status by ID
    status_res = client.get(f"/api/v1/verification/{run_id}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "passed"
    assert status_res.json()["tests_passed"] == 5

    # 3. Get execution logs
    logs_res = client.get(f"/api/v1/verification/{run_id}/logs")
    assert logs_res.status_code == 200
    assert "5 passed in 1.45s" in logs_res.json()["stdout"]

    # 4. Get evidence report
    full_report_res = client.get(f"/api/v1/verification/{run_id}/report")
    assert full_report_res.status_code == 200
    full_report = full_report_res.json()
    assert full_report["run_id"] == run_id
    assert full_report["verification_summary"] != ""
    assert full_report["ruff_passed"] is True

    # 5. List verification runs
    list_res = client.get("/api/v1/verification")
    assert list_res.status_code == 200
    runs = list_res.json()
    assert any(r["id"] == run_id for r in runs)
