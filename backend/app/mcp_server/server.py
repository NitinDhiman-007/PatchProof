"""Standalone Model Context Protocol (MCP) server for PatchProof.

Reuses the existing backend service layer and exposes 9 standard tools over
Streamable HTTP/SSE and stdio transports:
1. list_repositories
2. search_code
3. read_file
4. analyze_bug
5. get_analysis_status
6. get_root_cause
7. get_proposed_patch
8. run_verification
9. get_verification_report
"""

import argparse
import asyncio
from typing import Any

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette

from app.core.logging import get_logger
from app.database.database import ensure_db_initialized
from app.mcp_server.auth import MCPAuthMiddleware
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

logger = get_logger(__name__)

_mcp_server_instance: MCPServer | None = None


def create_mcp_server() -> MCPServer:
    """Create and configure the PatchProof MCP Server with all 9 tools."""
    ensure_db_initialized()

    server = MCPServer(
        name="PatchProof",
        instructions=(
            "PatchProof MCP Server provides evidence-backed bug reproduction and patch verification tools. "
            "Don't trust generated code. Prove it works."
        ),
        version="0.1.0",
    )

    # 1. list_repositories
    @server.tool(
        name="list_repositories",
        description="List all registered repositories in PatchProof with language and status metadata.",
    )
    def list_repositories(limit: int = 50) -> dict[str, Any]:
        """List registered repositories."""
        return mcp_list_repositories(limit=limit)

    # 2. search_code
    @server.tool(
        name="search_code",
        description="Search repository symbols and source code using non-executing AST and lexical indexing.",
    )
    def search_code(repository_id: str, query: str, limit: int = 10) -> dict[str, Any]:
        """Search code within a repository."""
        return mcp_search_code(repository_id=repository_id, query=query, limit=limit)

    # 3. read_file
    @server.tool(
        name="read_file",
        description="Safely read file contents within a repository workspace with strict path traversal defenses.",
    )
    def read_file(repository_id: str, relative_path: str, max_lines: int = 500) -> dict[str, Any]:
        """Read a file safely from repository workspace."""
        return mcp_read_file(repository_id=repository_id, relative_path=relative_path, max_lines=max_lines)

    # 4. analyze_bug
    @server.tool(
        name="analyze_bug",
        description=(
            "Initiate multi-step LangGraph debugging, baseline reproduction, and patch generation workflow. "
            "Never merges or commits code automatically."
        ),
    )
    def analyze_bug(
        repository_id: str,
        bug_description: str,
        issue_url: str | None = None,
        stack_trace: str | None = None,
    ) -> dict[str, Any]:
        """Run or initiate automated bug analysis."""
        return mcp_analyze_bug(
            repository_id=repository_id,
            bug_description=bug_description,
            issue_url=issue_url,
            stack_trace=stack_trace,
        )

    # 5. get_analysis_status
    @server.tool(
        name="get_analysis_status",
        description="Retrieve real-time status, verdict, patch status, and workflow events for an analysis run.",
    )
    def get_analysis_status(analysis_id: str) -> dict[str, Any]:
        """Get status and timeline for an analysis run."""
        return mcp_get_analysis_status(analysis_id=analysis_id)

    # 6. get_root_cause
    @server.tool(
        name="get_root_cause",
        description="Retrieve structured root cause analysis, affected files, line numbers, and confidence score.",
    )
    def get_root_cause(analysis_id: str) -> dict[str, Any]:
        """Get root cause diagnosis."""
        return mcp_get_root_cause(analysis_id=analysis_id)

    # 7. get_proposed_patch
    @server.tool(
        name="get_proposed_patch",
        description=(
            "Retrieve proposed candidate patch diff. "
            "Notice: Human review and explicit developer approval is strictly required before application."
        ),
    )
    def get_proposed_patch(analysis_id: str) -> dict[str, Any]:
        """Get proposed patch unified diff."""
        return mcp_get_proposed_patch(analysis_id=analysis_id)

    # 8. run_verification
    @server.tool(
        name="run_verification",
        description=(
            "Execute test suite and Ruff static checks inside an isolated, non-root Docker sandbox container. "
            "Only allowlisted test commands are permitted."
        ),
    )
    def run_verification(
        repository_id: str,
        command: str = "pytest",
        run_ruff: bool = True,
    ) -> dict[str, Any]:
        """Run tests inside Docker sandbox."""
        return mcp_run_verification(
            repository_id=repository_id,
            command=command,
            run_ruff=run_ruff,
        )

    # 9. get_verification_report
    @server.tool(
        name="get_verification_report",
        description="Retrieve full evidence-backed verification report with test metrics, exit codes, and sanitized logs.",
    )
    def get_verification_report(run_id: str) -> dict[str, Any]:
        """Get verification evidence report."""
        return mcp_get_verification_report(run_id=run_id)

    return server


def get_mcp_server() -> MCPServer:
    """Return singleton or cached MCP server instance."""
    global _mcp_server_instance
    if _mcp_server_instance is None:
        _mcp_server_instance = create_mcp_server()
    return _mcp_server_instance


def get_mcp_starlette_app(transport: str = "streamable-http", path: str = "/") -> Starlette:
    """
    Return Starlette application for Streamable HTTP or legacy SSE transport,
    configured with authentication middleware.

    Args:
        transport: 'streamable-http' (modern official MCP HTTP transport) or 'sse' (legacy SSE transport).
        path: Route path within the Starlette app (default: '/' when mounted under a prefix like '/mcp').
    """
    server = get_mcp_server()
    if transport == "streamable-http":
        inner_app = server.streamable_http_app(streamable_http_path=path)
    elif transport == "sse":
        inner_app = server.sse_app()
    else:
        inner_app = server.streamable_http_app(streamable_http_path=path)

    # Wrap with authentication middleware
    inner_app.add_middleware(MCPAuthMiddleware)
    return inner_app


def run_stdio():
    """Run MCP server in standard input/output (stdio) mode."""
    logger.info("Starting PatchProof MCP Server in stdio mode...")
    server = get_mcp_server()
    asyncio.run(server.run_stdio_async())


def run_streamable_http(host: str = "127.0.0.1", port: int = 8001, path: str = "/mcp"):
    """Run modern standalone Streamable HTTP server on specified host, port, and endpoint path."""
    logger.info("Starting PatchProof MCP Server in Streamable HTTP mode on http://%s:%d%s ...", host, port, path)
    app = get_mcp_starlette_app(transport="streamable-http", path=path)
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_sse(host: str = "127.0.0.1", port: int = 8001):
    """Run legacy standalone SSE server on specified host and port (for backward compatibility)."""
    logger.info("Starting PatchProof MCP Server in legacy SSE mode on http://%s:%d/sse ...", host, port)
    app = get_mcp_starlette_app(transport="sse")
    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    """CLI entrypoint for running the MCP server."""
    parser = argparse.ArgumentParser(description="PatchProof Model Context Protocol (MCP) Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="MCP transport protocol (default: stdio; modern HTTP: streamable-http; legacy HTTP: sse)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host binding for HTTP servers (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="Port for HTTP servers (default: 8001)")
    parser.add_argument("--path", default="/mcp", help="Endpoint path for Streamable HTTP (default: /mcp)")

    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    elif args.transport == "streamable-http":
        run_streamable_http(host=args.host, port=args.port, path=args.path)
    elif args.transport == "sse":
        run_sse(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
