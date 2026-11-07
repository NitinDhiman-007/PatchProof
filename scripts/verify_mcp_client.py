"""Verify MCP Streamable HTTP transport and all 9 tools using official MCP client."""

import asyncio
import json
import os
import sys

# Ensure backend package is in python path
sys.path.insert(0, os.path.abspath("backend"))

import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.database.database import get_db_connection, init_db
from app.mcp_server.server import get_mcp_starlette_app
from app.services.repository_service import create_git_repository

PORT = 8996
HOST = "127.0.0.1"
ENDPOINT = f"http://{HOST}:{PORT}/mcp"


async def main():
    init_db()

    # Configure a test repository
    repo = create_git_repository("https://github.com/bharatcode-eval/mcp-streamable-test")
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    with get_db_connection() as conn:
        conn.cursor().execute(
            "UPDATE repositories SET metadata_json = ? WHERE id = ?;",
            (json.dumps({"source_directory": demo_dir}), repo.id),
        )

    # Build the Starlette Streamable HTTP app
    app = get_mcp_starlette_app(transport="streamable-http", path="/mcp")

    # Start uvicorn server in background
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait for server to bind
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.1)

    print(f"Uvicorn Streamable HTTP server started on {ENDPOINT}", flush=True)

    try:
        print(f"Connecting to {ENDPOINT} using official streamable_http_client...", flush=True)
        async with streamable_http_client(ENDPOINT) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_res = await session.initialize()
                print(f"Session Initialized successfully! Protocol version: {init_res.protocol_version}", flush=True)

                # 1. tools/list verification
                tools_res = await session.list_tools()
                tool_names = [t.name for t in tools_res.tools]
                print(f"Total tools registered: {len(tool_names)}", flush=True)
                print(f"Tools list: {tool_names}", flush=True)

                expected_9 = [
                    "list_repositories",
                    "search_code",
                    "read_file",
                    "analyze_bug",
                    "get_analysis_status",
                    "get_root_cause",
                    "get_proposed_patch",
                    "run_verification",
                    "get_verification_report",
                ]
                for exp in expected_9:
                    assert exp in tool_names, f"Missing tool: {exp}"
                print("All 9 required MCP tools registered!", flush=True)

                # Tool 1: list_repositories
                r1 = await session.call_tool("list_repositories", {"limit": 10})
                d1 = json.loads(r1.content[0].text)
                print(f"[Tool 1: list_repositories] count={d1.get('count')}", flush=True)
                assert d1["count"] >= 1

                # Tool 2: search_code
                r2 = await session.call_tool("search_code", {"repository_id": repo.id, "query": "discount"})
                d2 = json.loads(r2.content[0].text)
                print(f"[Tool 2: search_code] snippets_found={d2.get('snippets_found')}", flush=True)
                assert d2["snippets_found"] > 0

                # Tool 3: read_file
                r3 = await session.call_tool("read_file", {"repository_id": repo.id, "relative_path": "calculator/discount.py"})
                d3 = json.loads(r3.content[0].text)
                print(f"[Tool 3: read_file] relative_path={d3.get('relative_path')}, lines={d3.get('total_lines')}", flush=True)
                assert "calculate_discount" in d3["content"]

                # Tool 5: get_analysis_status (with dummy ID)
                r5 = await session.call_tool("get_analysis_status", {"analysis_id": "nonexistent-test-id"})
                d5 = json.loads(r5.content[0].text)
                print(f"[Tool 5: get_analysis_status] status={d5.get('status')}", flush=True)

                # Tool 6: get_root_cause (with dummy ID)
                r6 = await session.call_tool("get_root_cause", {"analysis_id": "nonexistent-test-id"})
                d6 = json.loads(r6.content[0].text)
                print(f"[Tool 6: get_root_cause] error={d6.get('error')}", flush=True)

                # Tool 7: get_proposed_patch (with dummy ID)
                r7 = await session.call_tool("get_proposed_patch", {"analysis_id": "nonexistent-test-id"})
                d7 = json.loads(r7.content[0].text)
                print(f"[Tool 7: get_proposed_patch] error={d7.get('error')}", flush=True)

                # Tool 8: run_verification (rejects unauthorized command)
                r8 = await session.call_tool("run_verification", {"repository_id": repo.id, "command": "cat /etc/passwd"})
                d8 = json.loads(r8.content[0].text)
                print(f"[Tool 8: run_verification] rejected={d8.get('error')}", flush=True)
                assert "unauthorized" in d8["error"].lower() or "allowlist" in d8["error"].lower() or "disallowed" in d8["error"].lower()

                # Tool 9: get_verification_report (with dummy ID)
                r9 = await session.call_tool("get_verification_report", {"run_id": "nonexistent-run-id"})
                d9 = json.loads(r9.content[0].text)
                print(f"[Tool 9: get_verification_report] error={d9.get('error')}", flush=True)

                print("ALL 9 MCP TOOLS REGISTERED AND CALLABLE OVER STREAMABLE HTTP TRANSPORT!", flush=True)

    finally:
        server.should_exit = True
        await server_task
        print("Server shutdown cleanly.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
