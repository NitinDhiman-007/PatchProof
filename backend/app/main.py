"""FastAPI application entry point for PatchProof."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analysis, health, repositories, verification
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database.database import init_db
from app.mcp_server.server import get_mcp_server, get_mcp_starlette_app
from app.models.schemas import ErrorResponse, HealthResponse

# Initialize logging
setup_logging()
logger = get_logger("patchproof.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown routines."""
    logger.info("Starting PatchProof Backend Service (v%s)", settings.VERSION)
    # Initialize SQLite database schema
    init_db()
    # Initialize MCP Streamable HTTP session manager TaskGroup
    mcp_server = get_mcp_server()
    async with mcp_server.session_manager.run():
        yield
    logger.info("Shutting down PatchProof Backend Service.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for PatchProof - AI-powered bug reproduction and verification platform.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors with clear structured details."""
    logger.warning("Validation error on %s: %s", request.url.path, exc.errors())
    details = "; ".join([f"{'.'.join(str(l) for l in err['loc'])}: {err['msg']}" for err in exc.errors()])
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="Validation Error",
            detail=details,
            timestamp=datetime.now(UTC).isoformat(),
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle application HTTP exceptions."""
    logger.warning("HTTP error %d on %s: %s", exc.status_code, request.url.path, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="HTTP Exception",
            detail=str(exc.detail),
            timestamp=datetime.now(UTC).isoformat(),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unhandled server exceptions."""
    logger.error("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal Server Error",
            detail="An unexpected error occurred processing your request.",
            timestamp=datetime.now(UTC).isoformat(),
        ).model_dump(),
    )


# Root level /health endpoint
@app.get("/health", response_model=HealthResponse, tags=["Health"])
def root_health():
    """Root health check endpoint."""
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        timestamp=datetime.now(UTC),
    )


# API Version 1 Router
api_v1_router = APIRouter(prefix=settings.API_V1_STR)
api_v1_router.include_router(health.router)
api_v1_router.include_router(repositories.router)
api_v1_router.include_router(analysis.router)
api_v1_router.include_router(verification.router)

app.include_router(api_v1_router)

# Mount official Model Context Protocol (MCP) Streamable HTTP endpoint
app.mount("/mcp", get_mcp_starlette_app(transport="streamable-http", path="/"))

# Mount legacy MCP Server-Sent Events (SSE) endpoint for backward compatibility
app.mount("/sse", get_mcp_starlette_app(transport="sse"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
    )
