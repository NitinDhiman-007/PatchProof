"""Comprehensive unit and integration tests for PatchProof MCP Server.

Verifies:
1. Registration of all 9 required MCP tools with descriptions and schemas
2. list_repositories tool functionality and secret sanitization
3. search_code tool non-executing AST symbol search
4. read_file tool with strict path traversal, restricted file, and extension defenses
5. analyze_bug tool lifecycle execution and analysis record persistence
6. get_analysis_status tool timeline retrieval
7. get_root_cause tool structured diagnosis
8. get_proposed_patch tool unified diff and mandatory human approval notice
9. run_verification tool Docker sandbox integration and allowlist enforcement
10. get_verification_report tool evidence report retrieval
11. MCP authentication middleware enforcement (401 on missing/invalid token)
12. Deterministic DEMO MODE execution
"""

import json
import os
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from app.core.config import Settings
from app.database.database import get_db_connection, init_db
from app.mcp_server.auth import MCPAuthMiddleware
from app.mcp_server.server import create_mcp_server
from app.mcp_server.tools import (
    mcp_analyze_bug,
    mcp_get_analysis_status,
    mcp_get_proposed_patch,
    mcp_get_root_cause,
    mcp_get_verification_report,
    mcp_list_repositories,
    mcp_read_file,
    mcp_run_verification,
    mcp_search_code,
)
from app.services.repository_service import create_git_repository
from app.services.test_runner import TestExecutionSummary


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure database schema is ready before each test."""
    init_db()


@pytest.fixture
def demo_repository():
    """Create and return a repository configured for the demo discount code."""
    repo = create_git_repository("https://github.com/bharatcode-eval/demo-discount-repo")
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE repositories SET metadata_json = ? WHERE id = ?;",
            (json.dumps({"source_directory": demo_dir}), repo.id),
        )
    return repo


def test_mcp_server_registers_all_nine_tools():
    """Verify that the MCP server instance registers exactly the 9 required tools."""
    import asyncio

    server = create_mcp_server()
    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}

    expected_tools = {
        "list_repositories",
        "search_code",
        "read_file",
        "analyze_bug",
        "get_analysis_status",
        "get_root_cause",
        "get_proposed_patch",
        "run_verification",
        "get_verification_report",
    }

    assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    # Verify every tool has a non-empty description
    for tool in tools:
        if tool.name in expected_tools:
            assert tool.description, f"Tool '{tool.name}' must have a description."


def test_mcp_list_repositories():
    """Verify list_repositories returns structured list without sensitive internal host paths."""
    res = mcp_list_repositories(limit=10)
    assert "count" in res
    assert "repositories" in res
    assert isinstance(res["repositories"], list)
    if res["repositories"]:
        first = res["repositories"][0]
        assert "id" in first
        assert "name" in first
        assert "source_type" in first
        # Must not leak raw secrets or arbitrary host environment
        assert "api_key" not in first
        assert "token" not in first


def test_mcp_search_code_success(demo_repository):
    """Verify search_code finds symbols and snippets in the repository."""
    res = mcp_search_code(demo_repository.id, "calculate_discount percentage")
    assert "snippets" in res
    assert res.get("snippets_found", 0) > 0
    assert any("discount.py" in s["file_path"] for s in res["snippets"])


def test_mcp_search_code_invalid_repo():
    """Verify search_code returns structured error when repository does not exist."""
    res = mcp_search_code("nonexistent-repo-uuid", "discount")
    assert "error" in res
    assert "not exist" in res["error"].lower()


def test_mcp_read_file_success(demo_repository):
    """Verify read_file safely reads allowed code files."""
    res = mcp_read_file(demo_repository.id, "calculator/discount.py")
    assert "content" in res
    assert "def calculate_discount" in res["content"]
    assert res["relative_path"] == "calculator/discount.py"
    assert res["total_lines"] > 0
    assert res["truncated"] is False


def test_mcp_read_file_path_traversal_defense(demo_repository):
    """Verify read_file blocks directory traversal sequences."""
    traversal_paths = [
        "../../etc/passwd",
        "..\\..\\windows\\system.ini",
        "calculator/../../secret.txt",
        "/etc/shadow",
        "C:\\Windows\\System32\\cmd.exe",
    ]
    for bad_path in traversal_paths:
        res = mcp_read_file(demo_repository.id, bad_path)
        assert "error" in res
        assert ("traversal" in res["error"].lower() or "not permitted" in res["error"].lower() or "escapes" in res["error"].lower())


def test_mcp_read_file_restricted_files_defense(demo_repository):
    """Verify read_file refuses access to sensitive files like .env or keys."""
    restricted_paths = [
        ".env",
        ".env.local",
        ".git/config",
        "server.key",
        "database.db",
        "credentials.pem",
    ]
    for path in restricted_paths:
        res = mcp_read_file(demo_repository.id, path)
        assert "error" in res
        assert "forbidden" in res["error"].lower() or "not permitted" in res["error"].lower()


def test_mcp_read_file_unsupported_extension(demo_repository):
    """Verify read_file refuses arbitrary binary / executable files."""
    res = mcp_read_file(demo_repository.id, "malware.exe")
    assert "error" in res
    assert "extension" in res["error"].lower()


def test_mcp_analyze_bug_demo_mode(demo_repository, monkeypatch, tmp_path):
    """Verify analyze_bug executes deterministic demo mode and records state in SQLite."""
    mock_settings = Settings(
        WORKSPACE_BASE_DIR=str(tmp_path),
        DEMO_MODE=True,
    )
    monkeypatch.setattr("app.services.workflow_engine.get_settings", lambda: mock_settings)
    monkeypatch.setattr("app.core.execution_policy.get_settings", lambda: mock_settings)
    monkeypatch.setattr("app.services.verification_service.get_settings", lambda: mock_settings)

    # Mock runner so tests pass deterministically in test environment
    mock_runner = MagicMock()
    # Baseline test fails (proves reproduction)
    mock_runner.run_test_suite.side_effect = [
        TestExecutionSummary(
            status="failed",
            command="pytest tests/test_reproduce_discount_bug.py",
            exit_code=1,
            duration_seconds=0.45,
            tests_passed=1,
            tests_failed=1,
            stdout="FAILED tests/test_reproduce_discount_bug.py::test_reproduce_percentage_discount_bug",
        ),
        TestExecutionSummary(
            status="passed",
            command="pytest",
            exit_code=0,
            duration_seconds=0.55,
            tests_passed=2,
            tests_failed=0,
            stdout="2 passed in 0.55s",
        ),
    ]
    mock_runner.run_static_check.return_value = {
        "passed": True,
        "issues": [],
        "exit_code": 0,
        "raw_output": "All checks passed!",
    }
    monkeypatch.setattr("app.services.workflow_engine.TestRunner", lambda: mock_runner)

    res = mcp_analyze_bug(
        repository_id=demo_repository.id,
        bug_description="calculate_discount produces negative prices when whole percentage 20 is passed.",
    )

    assert "analysis_id" in res
    analysis_id = res["analysis_id"]
    assert res["status"] in ["completed", "running"]
    assert res["verdict"] in ["VERIFIED", "PENDING"]

    # Verify status tool
    status_res = mcp_get_analysis_status(analysis_id)
    assert status_res["analysis_id"] == analysis_id
    assert status_res["events_count"] > 0
    assert status_res["verdict"] in ["VERIFIED", "PENDING"]

    # Verify root cause tool
    rca_res = mcp_get_root_cause(analysis_id)
    assert rca_res["analysis_id"] == analysis_id
    assert rca_res["root_cause"] is not None
    assert "[DEMO MODE]" in str(rca_res["root_cause"])

    # Verify proposed patch tool
    patch_res = mcp_get_proposed_patch(analysis_id)
    assert patch_res["analysis_id"] == analysis_id
    assert patch_res["patch_available"] is True
    assert "calculator/discount.py" in patch_res["patch_diff"]
    assert patch_res["human_approval_required"] is True
    assert "human review and approval" in patch_res["human_review_notice"].lower()


def test_mcp_run_verification_rejects_unauthorized_commands(demo_repository):
    """Verify run_verification enforces strict command allowlist and rejects arbitrary shell commands."""
    forbidden_commands = [
        "cat /etc/passwd",
        "rm -rf /",
        "curl http://evil.com",
        "python -c 'import os; os.system(\"dir\")'",
        "pytest; ls -la",
        "ruff check . && echo pwned",
    ]
    for cmd in forbidden_commands:
        res = mcp_run_verification(demo_repository.id, command=cmd)
        assert "error" in res
        assert "security policy" in res["error"].lower() or "unauthorized" in res["error"].lower()


def test_mcp_run_verification_and_get_report(demo_repository, monkeypatch):
    """Verify run_verification triggers verification service and get_verification_report fetches evidence."""
    mock_runner = MagicMock()
    mock_runner.run_test_suite.return_value = TestExecutionSummary(
        status="passed",
        command="pytest -v --tb=short",
        exit_code=0,
        duration_seconds=0.42,
        tests_passed=1,
        tests_failed=0,
        stdout="1 passed in 0.42s",
    )
    mock_runner.run_static_check.return_value = {
        "passed": True,
        "issues": [],
        "exit_code": 0,
        "raw_output": "All checks passed!",
    }
    monkeypatch.setattr("app.services.verification_service.TestRunner", lambda: mock_runner)

    res = mcp_run_verification(demo_repository.id, command="pytest", run_ruff=True)
    assert "run_id" in res
    assert res["status"] == "passed"
    assert res["tests_passed"] == 1
    assert res["ruff_passed"] is True

    # Retrieve evidence report tool
    report_res = mcp_get_verification_report(res["run_id"])
    assert "evidence_report" in report_res
    ev = report_res["evidence_report"]
    assert ev["run_id"] == res["run_id"]
    assert ev["tests_passed"] == 1
    assert "Docker" in ev["execution_environment"]


def test_mcp_auth_middleware_blocks_unauthorized(monkeypatch):
    """Verify MCPAuthMiddleware enforces API key verification on network HTTP/SSE endpoints."""
    mock_settings = Settings(MCP_API_KEY="secret-test-token-12345")
    monkeypatch.setattr("app.mcp_server.auth.get_settings", lambda: mock_settings)

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse

    test_app = Starlette()
    test_app.add_middleware(MCPAuthMiddleware)
    test_app.add_route("/sse", lambda r: PlainTextResponse("sse-endpoint"))

    client = TestClient(test_app)

    # 1. Missing header -> 401 Unauthorized
    res = client.get("/sse")
    assert res.status_code == 401
    assert res.json()["error"] == "Unauthorized"

    # 2. Invalid token -> 401 Unauthorized
    res = client.get("/sse", headers={"Authorization": "Bearer wrong-token"})
    assert res.status_code == 401

    # 3. Valid X-API-Key header -> Accepted (200 OK)
    res = client.get("/sse", headers={"X-API-Key": "secret-test-token-12345"})
    assert res.status_code == 200

    # 4. Valid Authorization: Bearer token -> Accepted (200 OK)
    res = client.get("/sse", headers={"Authorization": "Bearer secret-test-token-12345"})
    assert res.status_code == 200


def test_mcp_auth_middleware_allows_when_no_key_configured(monkeypatch):
    """Verify MCPAuthMiddleware permits local requests when no MCP_API_KEY is configured."""
    mock_settings = Settings(MCP_API_KEY="")
    monkeypatch.setattr("app.mcp_server.auth.get_settings", lambda: mock_settings)

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse

    test_app = Starlette()
    test_app.add_middleware(MCPAuthMiddleware)
    test_app.add_route("/sse", lambda r: PlainTextResponse("sse-endpoint"))

    client = TestClient(test_app)

    res = client.get("/sse")
    assert res.status_code == 200
