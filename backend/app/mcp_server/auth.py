"""Authentication middleware and validation for network-accessible MCP endpoints."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MCPAuthMiddleware:
    """
    Pure ASGI middleware ensuring that network-accessible MCP endpoints (Streamable HTTP & SSE)
    are protected by an API key when MCP_API_KEY is configured in settings.

    Uses pure ASGI protocol handling to safely support streaming responses (SSE and chunked streams)
    without buffering or body iterator conflicts.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        required_key = settings.MCP_API_KEY.strip()

        # If no key is configured in settings, permit local access
        if not required_key:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("latin1").strip()
        api_key_header = headers.get(b"x-api-key", b"").decode("latin1").strip()

        provided_key = None
        if auth_header.lower().startswith("bearer "):
            provided_key = auth_header[7:].strip()
        elif api_key_header:
            provided_key = api_key_header

        if not provided_key or provided_key != required_key:
            client_ip = scope.get("client", ("unknown", 0))[0]
            path = scope.get("path", "")
            logger.warning(
                "Unauthorized MCP request from %s on path %s",
                client_ip,
                path,
            )
            response = JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "Missing or invalid MCP API key. Provide via 'Authorization: Bearer <key>' or 'X-API-Key' header.",
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
