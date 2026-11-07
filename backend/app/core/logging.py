"""Structured logging configuration for PatchProof."""

import logging
import sys

from app.core.config import get_settings


def setup_logging(level: str | None = None) -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    log_level = level or settings.LOG_LEVEL

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    log_format = "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s"

    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    # Adjust external noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger with app configuration."""
    return logging.getLogger(name)
