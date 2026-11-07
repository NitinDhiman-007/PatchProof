"""Centralized environment and application configuration."""

import json
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory paths
_CURRENT_DIR = Path(__file__).resolve().parent  # app/core
_APP_DIR = _CURRENT_DIR.parent                  # app
_BACKEND_DIR = _APP_DIR.parent                  # backend
_ROOT_DIR = _BACKEND_DIR.parent                 # project root

# Search candidate .env locations in order: backend/.env, root .env, CWD .env
_CANDIDATE_ENV_PATHS = [
    _BACKEND_DIR / ".env",
    _ROOT_DIR / ".env",
    Path(".env").resolve(),
]

# Ensure candidate dotenv files are loaded into os.environ if present without overriding existing env vars
for _candidate in _CANDIDATE_ENV_PATHS:
    if _candidate.is_file():
        load_dotenv(dotenv_path=_candidate, override=False)

_ENV_FILES = tuple(str(p) for p in _CANDIDATE_ENV_PATHS if p.is_file()) or (".env",)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Project Information
    PROJECT_NAME: str = "PatchProof API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Server Binding
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Database Configuration
    DATABASE_URL: str = "sqlite:///./patchproof.db"

    # BharatCode Model Configuration (Do not commit real keys)
    BHARATCODE_API_KEY: str = ""
    BHARATCODE_BASE_URL: str = "https://bharatcode.ai/api/model/v1"
    BHARATCODE_MODEL: str = "qwen-3.8-27b"
    BHARATCODE_TIMEOUT_SECONDS: float = 60.0
    BHARATCODE_MAX_RETRIES: int = 2

    # Offline / Demo Mode Configuration
    DEMO_MODE: bool = False

    # MCP (Model Context Protocol) Server Configuration
    MCP_API_KEY: str = ""
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8001
    MCP_TRANSPORT: str = "sse"

    # CORS Configuration
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    # Security & Archive Limits (Non-execution guardrails)
    MAX_ZIP_UPLOAD_BYTES: int = 50 * 1024 * 1024  # 50 MB
    MAX_ZIP_FILE_COUNT: int = 5000
    MAX_UNCOMPRESSED_RATIO: float = 100.0

    # Docker Sandbox Execution Limits
    DOCKER_PYTHON_IMAGE: str = "python:3.12-slim"
    DOCKER_MEMORY_LIMIT: str = "512m"
    DOCKER_NANO_CPUS: int = 1_000_000_000  # 1.0 CPU
    DOCKER_PIDS_LIMIT: int = 64
    DOCKER_TIMEOUT_SECONDS: int = 30
    WORKSPACE_BASE_DIR: str = "./workspaces"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item) for item in parsed]
                except (json.JSONDecodeError, TypeError):
                    return [i.strip() for i in v.split(",") if i.strip()]
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
