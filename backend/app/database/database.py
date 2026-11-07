"""SQLite database persistence layer."""

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_db_path() -> str:
    """Extract SQLite database file path from DATABASE_URL."""
    settings = get_settings()
    url = settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "")
        return path
    elif url == "sqlite:///:memory:":
        return ":memory:"
    return "patchproof.db"


_initialized = False


def ensure_db_initialized() -> None:
    """Ensure database tables are created once per process."""
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True


def _create_raw_connection() -> sqlite3.Connection:
    """Create a raw SQLite connection with Row factory."""
    db_path = get_db_path()
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables if they do not exist."""
    conn = _create_raw_connection()
    try:
        cursor = conn.cursor()

        # Repositories table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS repositories (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                git_url TEXT,
                default_branch TEXT,
                file_count INTEGER DEFAULT 0,
                detected_language TEXT DEFAULT 'unknown',
                status TEXT NOT NULL DEFAULT 'active',
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        # Bug Analysis runs table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                repository_id TEXT NOT NULL,
                bug_description TEXT NOT NULL,
                issue_url TEXT,
                stack_trace TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                summary TEXT,
                root_cause_json TEXT,
                reproduction_test_code TEXT,
                reproduction_test_path TEXT,
                baseline_reproduced INTEGER DEFAULT 0,
                patch_diff TEXT,
                patch_status TEXT DEFAULT 'none',
                verification_verdict TEXT DEFAULT 'PENDING',
                evidence_report_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (repository_id) REFERENCES repositories(id)
            );
            """
        )

        # Migration: Add columns to existing analysis_runs if table existed from Phase 1/2
        cursor.execute("PRAGMA table_info(analysis_runs);")
        existing_cols = {col["name"] for col in cursor.fetchall()}
        new_cols = [
            ("stack_trace", "TEXT"),
            ("root_cause_json", "TEXT"),
            ("reproduction_test_code", "TEXT"),
            ("reproduction_test_path", "TEXT"),
            ("baseline_reproduced", "INTEGER DEFAULT 0"),
            ("patch_diff", "TEXT"),
            ("patch_status", "TEXT DEFAULT 'none'"),
            ("verification_verdict", "TEXT DEFAULT 'PENDING'"),
            ("evidence_report_json", "TEXT"),
        ]
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE analysis_runs ADD COLUMN {col_name} {col_type};")

        # Workflow Events table for real-time LangGraph agent telemetry
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_events (
                id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analysis_runs(id)
            );
            """
        )

        # Verification Runs and Evidence Reports table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS verification_runs (
                id TEXT PRIMARY KEY,
                repository_id TEXT NOT NULL,
                command TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                exit_code INTEGER,
                duration_seconds REAL DEFAULT 0.0,
                tests_passed INTEGER DEFAULT 0,
                tests_failed INTEGER DEFAULT 0,
                tests_skipped INTEGER DEFAULT 0,
                tests_errors INTEGER DEFAULT 0,
                ruff_passed INTEGER DEFAULT 1,
                ruff_issues_json TEXT,
                stdout TEXT,
                stderr TEXT,
                error_message TEXT,
                report_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (repository_id) REFERENCES repositories(id)
            );
            """
        )
        conn.commit()
        logger.info("Database initialized successfully at %s", get_db_path())
    finally:
        conn.close()


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yield a database connection with Row factory and automatic commit/rollback."""
    ensure_db_initialized()
    conn = _create_raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_db_health() -> bool:
    """Verify SQLite connection is operational."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()
            return result is not None and result[0] == 1
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return False
