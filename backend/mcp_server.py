"""Convenience entry point for starting the PatchProof MCP Server.

Usage:
    # Stdio transport (default, for Claude Desktop, Cursor, local agents):
    python mcp_server.py --transport stdio

    # Modern Streamable HTTP transport (official MCP over HTTP spec):
    python mcp_server.py --transport streamable-http --host 127.0.0.1 --port 8001

    # Legacy SSE transport (for backward compatibility):
    python mcp_server.py --transport sse --host 127.0.0.1 --port 8001
"""

import os
import sys

# Ensure backend root is on Python sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.mcp_server.server import main  # noqa: E402

if __name__ == "__main__":
    main()
