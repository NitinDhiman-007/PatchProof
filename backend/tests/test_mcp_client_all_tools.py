"""Verify that an actual MCP ClientSession can list and invoke all 9 tools end-to-end."""

import asyncio
import json
import os
from unittest.mock import MagicMock

import pytest
from mcp import ClientSession
from mcp.server.mcpserver import MCPServer

from app.database.database import get_db_connection, init_db
from app.mcp_server.server import create_mcp_server
from app.services.repository_service import create_git_repository
from app.services.test_runner import TestExecutionSummary


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_all_nine_mcp_tools_invocable_via_session(monkeypatch, tmp_path):
    """Test that all 9 tools appear in tools/list and can be invoked via ClientSession."""
    repo = create_git_repository("https://github.com/bharatcode-eval/mcp-full-audit")
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    with get_db_connection() as conn:
        conn.cursor().execute(
            "UPDATE repositories SET metadata_json = ? WHERE id = ?;",
            (json.dumps({"source_directory": demo_dir}), repo.id),
        )

    # Mock settings
    from app.core.config import Settings
    mock_settings = Settings(WORKSPACE_BASE_DIR=str(tmp_path), DEMO_MODE=True)
    monkeypatch.setattr("app.services.workflow_engine.get_settings", lambda: mock_settings)
    monkeypatch.setattr("app.core.execution_policy.get_settings", lambda: mock_settings)
    monkeypatch.setattr("app.services.verification_service.get_settings", lambda: mock_settings)

    # Mock runner for deterministic sandbox execution
    mock_runner = MagicMock()
    mock_runner.run_test_suite.side_effect = [
        TestExecutionSummary(
            status="failed",
            command="pytest tests/test_reproduce_discount_bug.py",
            exit_code=1,
            duration_seconds=0.3,
            tests_passed=1,
            tests_failed=1,
            stdout="FAILED tests/test_reproduce_discount_bug.py",
        ),
        TestExecutionSummary(
            status="passed",
            command="pytest",
            exit_code=0,
            duration_seconds=0.4,
            tests_passed=2,
            tests_failed=0,
            stdout="2 passed",
        ),
        TestExecutionSummary(
            status="passed",
            command="pytest",
            exit_code=0,
            duration_seconds=0.2,
            tests_passed=1,
            tests_failed=0,
            stdout="1 passed",
        ),
    ]
    mock_runner.run_static_check.return_value = {
        "passed": True,
        "issues": [],
        "exit_code": 0,
        "raw_output": "Clean",
    }
    monkeypatch.setattr("app.services.workflow_engine.TestRunner", lambda: mock_runner)
    monkeypatch.setattr("app.services.verification_service.TestRunner", lambda: mock_runner)

    server: MCPServer = create_mcp_server()

    async def run_audit():
        # Connect in-memory streams
        from anyio import create_memory_object_stream

        client_to_server_send, client_to_server_recv = create_memory_object_stream()
        server_to_client_send, server_to_client_recv = create_memory_object_stream()

        async def run_server():
            await server._lowlevel_server.run(
                client_to_server_recv,
                server_to_client_send,
                server._lowlevel_server.create_initialization_options(),
            )

        server_task = asyncio.create_task(run_server())

        try:
            async with ClientSession(server_to_client_recv, client_to_server_send) as session:
                await session.initialize()

                # 1. tools/list verification
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]
                assert len(tool_names) == 9

                # Tool 1: list_repositories
                r1 = await session.call_tool("list_repositories", {"limit": 10})
                data1 = json.loads(r1.content[0].text)
                assert data1["count"] >= 1

                # Tool 2: search_code
                r2 = await session.call_tool("search_code", {"repository_id": repo.id, "query": "discount"})
                data2 = json.loads(r2.content[0].text)
                assert data2["snippets_found"] > 0

                # Tool 3: read_file
                r3 = await session.call_tool("read_file", {"repository_id": repo.id, "relative_path": "calculator/discount.py"})
                data3 = json.loads(r3.content[0].text)
                assert "calculate_discount" in data3["content"]

                # Tool 4: analyze_bug
                r4 = await session.call_tool("analyze_bug", {
                    "repository_id": repo.id,
                    "bug_description": "calculate_discount gives negative price for whole percentage discount 20",
                })
                data4 = json.loads(r4.content[0].text)
                assert "analysis_id" in data4
                analysis_id = data4["analysis_id"]

                # Tool 5: get_analysis_status
                r5 = await session.call_tool("get_analysis_status", {"analysis_id": analysis_id})
                data5 = json.loads(r5.content[0].text)
                assert data5["analysis_id"] == analysis_id

                # Tool 6: get_root_cause
                r6 = await session.call_tool("get_root_cause", {"analysis_id": analysis_id})
                data6 = json.loads(r6.content[0].text)
                assert "root_cause" in data6

                # Tool 7: get_proposed_patch
                r7 = await session.call_tool("get_proposed_patch", {"analysis_id": analysis_id})
                data7 = json.loads(r7.content[0].text)
                assert data7["human_approval_required"] is True

                # Tool 8: run_verification
                r8 = await session.call_tool("run_verification", {"repository_id": repo.id, "command": "pytest"})
                data8 = json.loads(r8.content[0].text)
                assert "run_id" in data8
                run_id = data8["run_id"]

                # Tool 9: get_verification_report
                r9 = await session.call_tool("get_verification_report", {"run_id": run_id})
                data9 = json.loads(r9.content[0].text)
                assert "evidence_report" in data9
                assert data9["run_id"] == run_id

                print("ALL 9 MCP TOOLS SUCCESSFULLY INVOCATED THROUGH MCP CLIENT!")
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    asyncio.run(run_audit())

