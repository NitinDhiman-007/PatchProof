"""Execute complete happy-path verification for all 9 MCP tools over Streamable HTTP."""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath("backend"))

import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.core.config import get_settings
from app.database.database import get_db_connection, init_db
from app.mcp_server.server import get_mcp_starlette_app
from app.services.repository_service import create_git_repository

PORT = 8997
HOST = "127.0.0.1"
ENDPOINT = f"http://{HOST}:{PORT}/mcp"


async def main():
    print("=" * 80)
    print("MCP HAPPY-PATH VERIFICATION OVER STREAMABLE HTTP TRANSPORT")
    print("=" * 80)

    init_db()

    # Enable DEMO_MODE in settings
    settings = get_settings()
    settings.DEMO_MODE = True

    # Register demo repository
    repo = create_git_repository("https://github.com/patchproof-org/demo-discount-repo")
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    with get_db_connection() as conn:
        conn.cursor().execute(
            "UPDATE repositories SET metadata_json = ? WHERE id = ?;",
            (f'{{"source_directory": "{demo_dir.replace("\\", "\\\\")}"}}', repo.id),
        )

    # Start Starlette Streamable HTTP app
    app = get_mcp_starlette_app(transport="streamable-http", path="/mcp")
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait for server to bind
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.1)

    print(f"Uvicorn Streamable HTTP server started on {ENDPOINT}\n")

    try:
        print(f"Connecting to {ENDPOINT} using official streamable_http_client...")
        async with streamable_http_client(ENDPOINT) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_res = await session.initialize()
                print(f"Session Initialized successfully! Protocol: {init_res.protocol_version}\n")

                # List tools
                tools_res = await session.list_tools()
                tool_names = [t.name for t in tools_res.tools]
                print(f"Registered MCP Tools ({len(tool_names)}): {tool_names}\n")

                # ==============================================================
                # 1. list_repositories (Happy-Path)
                # ==============================================================
                print("--- [Tool 1/9] list_repositories ---")
                r1 = await session.call_tool("list_repositories", {"limit": 10})
                d1 = json.loads(r1.content[0].text)
                print(f"Count: {d1.get('count')}")
                assert d1["count"] >= 1, "list_repositories returned empty count"
                print("Found repos:", [r["name"] for r in d1["repositories"][:3]])
                print("Result: PASS\n")

                # ==============================================================
                # 2. search_code (Happy-Path)
                # ==============================================================
                print("--- [Tool 2/9] search_code ---")
                r2 = await session.call_tool("search_code", {"repository_id": repo.id, "query": "discount"})
                d2 = json.loads(r2.content[0].text)
                print(f"Query: 'discount', Snippets found: {d2.get('snippets_found')}")
                assert d2["snippets_found"] > 0, "search_code found 0 snippets"
                top_snippet = d2["snippets"][0]
                print(f"Top snippet file: {top_snippet['file_path']}, symbol: {top_snippet.get('symbol_name')}")
                print("Result: PASS\n")

                # ==============================================================
                # 3. read_file (Happy-Path)
                # ==============================================================
                print("--- [Tool 3/9] read_file ---")
                r3 = await session.call_tool("read_file", {
                    "repository_id": repo.id,
                    "relative_path": "calculator/discount.py"
                })
                d3 = json.loads(r3.content[0].text)
                print(f"Relative path: {d3.get('relative_path')}, Lines: {d3.get('total_lines')}")
                assert "calculate_discount" in d3["content"]
                print("Content preview:\n" + d3["content"][:150] + "...")
                print("Result: PASS\n")

                # ==============================================================
                # 4. analyze_bug in DEMO_MODE with Live Docker Execution
                # ==============================================================
                print("--- [Tool 4/9] analyze_bug (DEMO_MODE + Live Docker Sandbox) ---")
                r4 = await session.call_tool("analyze_bug", {
                    "repository_id": repo.id,
                    "bug_description": "calculate_discount produces negative price when percentage 20 is passed",
                })
                d4 = json.loads(r4.content[0].text)
                analysis_id = d4.get("analysis_id")
                print(f"Analysis ID: {analysis_id}")
                print(f"Verdict: {d4.get('verdict')}")
                print(f"Status: {d4.get('status')}")
                print(f"Baseline Reproduced: {d4.get('baseline_reproduced')}")
                print(f"Patch Status: {d4.get('patch_status')}")
                assert d4.get("verdict") == "VERIFIED", f"Expected VERIFIED, got {d4.get('verdict')}"
                assert d4.get("baseline_reproduced") is True
                assert d4.get("patch_status") == "pending_approval"
                print("Result: PASS\n")

                # ==============================================================
                # 5. get_analysis_status (Happy-Path)
                # ==============================================================
                print("--- [Tool 5/9] get_analysis_status ---")
                r5 = await session.call_tool("get_analysis_status", {"analysis_id": analysis_id})
                d5 = json.loads(r5.content[0].text)
                print(f"Analysis ID: {d5.get('analysis_id')}")
                print(f"Status: {d5.get('status')}")
                print(f"Verdict: {d5.get('verdict')}")
                print(f"Patch Status: {d5.get('patch_status')}")
                print(f"Audit events recorded: {len(d5.get('events', []))}")
                assert d5["status"] == "completed"
                assert d5["verdict"] == "VERIFIED"
                assert len(d5.get("events", [])) >= 10
                print("Result: PASS\n")

                # ==============================================================
                # 6. get_root_cause (Happy-Path)
                # ==============================================================
                print("--- [Tool 6/9] get_root_cause ---")
                r6 = await session.call_tool("get_root_cause", {"analysis_id": analysis_id})
                d6 = json.loads(r6.content[0].text)
                rc = d6.get("root_cause", {})
                print(f"Problem Summary: {rc.get('problem_summary')}")
                print(f"Suspected Root Cause: {rc.get('suspected_root_cause')}")
                print(f"Confidence: {rc.get('confidence_score')}")
                assert "discount" in rc.get("problem_summary", "").lower()
                print("Result: PASS\n")

                # ==============================================================
                # 7. get_proposed_patch (Happy-Path)
                # ==============================================================
                print("--- [Tool 7/9] get_proposed_patch ---")
                r7 = await session.call_tool("get_proposed_patch", {"analysis_id": analysis_id})
                d7 = json.loads(r7.content[0].text)
                print(f"Human Approval Required: {d7.get('human_approval_required')}")
                print(f"Patch Status: {d7.get('patch_status')}")
                print(f"Review Notice: {d7.get('review_notice')}")
                print(f"Diff:\n{d7.get('patch_diff')}")
                assert d7.get("human_approval_required") is True
                assert d7.get("patch_status") == "pending_approval"
                assert "discount / 100.0" in d7.get("patch_diff", "")
                print("Result: PASS\n")

                # ==============================================================
                # 8. run_verification with allowed preset in Real Docker Sandbox
                # ==============================================================
                print("--- [Tool 8/9] run_verification (pytest in Real Docker Sandbox) ---")
                r8 = await session.call_tool("run_verification", {
                    "repository_id": repo.id,
                    "command": "pytest",
                    "run_ruff": True,
                })
                d8 = json.loads(r8.content[0].text)
                run_id = d8.get("run_id")
                print(f"Verification Run ID: {run_id}")
                print(f"Status: {d8.get('status')}")
                print(f"Tests Passed: {d8.get('tests_passed')}")
                print(f"Tests Failed: {d8.get('tests_failed')}")
                print(f"Ruff Passed: {d8.get('ruff_passed')}")
                print(f"Duration: {d8.get('duration_seconds')}s")
                assert run_id is not None
                assert d8.get("status") == "passed"
                assert d8.get("tests_passed") >= 1
                assert d8.get("tests_failed") == 0
                print("Result: PASS\n")

                # ==============================================================
                # 9. get_verification_report (Happy-Path)
                # ==============================================================
                print("--- [Tool 9/9] get_verification_report ---")
                r9 = await session.call_tool("get_verification_report", {"run_id": run_id})
                d9 = json.loads(r9.content[0].text)
                ev = d9.get("evidence_report", {})
                print(f"Report Run ID: {d9.get('run_id')}")
                print(f"Status: {ev.get('status')}")
                print(f"Integrity Hash: {ev.get('integrity_hash')}")
                print(f"Execution Environment: {ev.get('environment')}")
                print(f"Sanitized Stdout snippet:\n{ev.get('sanitized_stdout', '')[:180]}...")
                assert ev.get("status") in ["passed", "completed"]
                assert ev.get("integrity_hash", "").startswith("sha256:")
                print("Result: PASS\n")

                print("=" * 80)
                print("ALL 9 MCP TOOLS SUCCESSFULLY VERIFIED ON MEANINGFUL HAPPY-PATH OPERATIONS!")
                print("=" * 80)

    finally:
        server.should_exit = True
        await server_task
        print("Uvicorn server shutdown cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
