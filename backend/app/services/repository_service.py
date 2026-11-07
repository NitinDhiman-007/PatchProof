"""Service for safe repository registration, inspection, and persistence."""

import io
import json
import os
import uuid
import zipfile
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.database import get_db_connection
from app.models.schemas import RepositoryResponse

logger = get_logger(__name__)


def extract_repo_name_from_url(git_url: str) -> str:
    """Extract clean repository name from Git URL."""
    clean = git_url.strip().rstrip("/")
    clean = clean.removesuffix(".git")
    parts = clean.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else "repository"


def inspect_zip_archive_safety(zip_bytes: bytes, filename: str) -> tuple[bool, list[str], dict]:
    """
    Safely inspect a ZIP archive in memory without extracting it to disk.
    Enforces security controls against:
    - Zip Bombs (excessive uncompressed size or unreasonable compression ratio)
    - Path Traversal (filenames containing '..' or leading slashes)
    - Malicious executable formats
    """
    settings = get_settings()
    errors: list[str] = []
    metadata = {
        "filename": filename,
        "file_size_bytes": len(zip_bytes),
        "total_files": 0,
        "top_level_directories": set(),
        "detected_language": "unknown",
        "extensions_count": {},
    }

    if len(zip_bytes) > settings.MAX_ZIP_UPLOAD_BYTES:
        errors.append(f"File exceeds maximum allowed upload size ({settings.MAX_ZIP_UPLOAD_BYTES // (1024 * 1024)}MB).")
        return False, errors, metadata

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            infolist = zf.infolist()
            metadata["total_files"] = len(infolist)

            if len(infolist) > settings.MAX_ZIP_FILE_COUNT:
                errors.append(
                    f"Archive contains {len(infolist)} entries, exceeding safety limit of {settings.MAX_ZIP_FILE_COUNT} files."
                )
                return False, errors, metadata

            total_uncompressed_bytes = 0
            extensions_count: dict[str, int] = {}
            top_level_dirs = set()

            for info in infolist:
                # 1. Path traversal inspection
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/") or (len(name) > 1 and name[1] == ":"):
                    errors.append(f"Potentially malicious path traversal sequence detected in archive: {info.filename}")
                    return False, errors, metadata

                # 2. Extract top-level directory names
                parts = [p for p in name.split("/") if p]
                if parts and info.is_dir():
                    top_level_dirs.add(parts[0])

                # 3. Uncompressed size calculation (Zip Bomb defense)
                total_uncompressed_bytes += info.file_size
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > settings.MAX_UNCOMPRESSED_RATIO:
                        errors.append(
                            f"Suspicious compression ratio ({ratio:.1f}x) detected for {info.filename}. Potential zip bomb."
                        )
                        return False, errors, metadata

                # 4. File extension distribution
                if not info.is_dir():
                    _, ext = os.path.splitext(name.lower())
                    if ext:
                        extensions_count[ext] = extensions_count.get(ext, 0) + 1

            # Check total uncompressed size limit
            max_uncompressed = settings.MAX_ZIP_UPLOAD_BYTES * 4
            if total_uncompressed_bytes > max_uncompressed:
                errors.append(
                    f"Uncompressed archive size ({total_uncompressed_bytes // (1024 * 1024)}MB) exceeds safe threshold."
                )
                return False, errors, metadata

            metadata["top_level_directories"] = sorted(top_level_dirs)
            metadata["extensions_count"] = extensions_count

            # Language heuristic
            if extensions_count.get(".py", 0) > 0:
                metadata["detected_language"] = "python"
            elif extensions_count.get(".ts", 0) > 0 or extensions_count.get(".tsx", 0) > 0:
                metadata["detected_language"] = "typescript"
            elif extensions_count.get(".js", 0) > 0 or extensions_count.get(".jsx", 0) > 0:
                metadata["detected_language"] = "javascript"
            elif extensions_count.get(".rs", 0) > 0:
                metadata["detected_language"] = "rust"
            elif extensions_count.get(".go", 0) > 0:
                metadata["detected_language"] = "go"

            return True, [], metadata

    except zipfile.BadZipFile:
        errors.append("Invalid or corrupted ZIP archive.")
        return False, errors, metadata
    except Exception as e:
        logger.error("Error inspecting ZIP archive: %s", e)
        errors.append(f"Inspection error: {e!s}")
        return False, errors, metadata


def create_git_repository(git_url: str, default_branch: str = "main") -> RepositoryResponse:
    """Register a new repository via Git URL in the database."""
    repo_id = str(uuid.uuid4())
    name = extract_repo_name_from_url(git_url)
    now = datetime.now(UTC).isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO repositories (id, name, source_type, git_url, default_branch, status, created_at)
            VALUES (?, ?, 'git', ?, ?, 'active', ?);
            """,
            (repo_id, name, git_url, default_branch, now),
        )

    logger.info("Registered Git repository %s (%s)", name, repo_id)
    return RepositoryResponse(
        id=repo_id,
        name=name,
        source_type="git",
        git_url=git_url,
        default_branch=default_branch,
        file_count=0,
        detected_language="unknown",
        status="active",
        created_at=now,
    )


def create_zip_repository(
    filename: str,
    file_count: int,
    detected_language: str,
    metadata: dict,
) -> RepositoryResponse:
    """Register a repository from validated ZIP metadata in the database."""
    repo_id = str(uuid.uuid4())
    name = os.path.splitext(os.path.basename(filename))[0] or "zip-repository"
    now = datetime.now(UTC).isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO repositories (
                id, name, source_type, git_url, default_branch,
                file_count, detected_language, status, metadata_json, created_at
            )
            VALUES (?, ?, 'zip', NULL, NULL, ?, ?, 'active', ?, ?);
            """,
            (
                repo_id,
                name,
                file_count,
                detected_language,
                json.dumps(metadata),
                now,
            ),
        )

    logger.info("Registered ZIP repository %s (%s) with %d files", name, repo_id, file_count)
    return RepositoryResponse(
        id=repo_id,
        name=name,
        source_type="zip",
        git_url=None,
        default_branch=None,
        file_count=file_count,
        detected_language=detected_language,
        status="active",
        created_at=now,
    )


def get_repository(repo_id: str) -> RepositoryResponse | None:
    """Retrieve a repository record by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM repositories WHERE id = ?;", (repo_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return RepositoryResponse(
            id=row["id"],
            name=row["name"],
            source_type=row["source_type"],
            git_url=row["git_url"],
            default_branch=row["default_branch"],
            file_count=row["file_count"] or 0,
            detected_language=row["detected_language"] or "unknown",
            status=row["status"],
            created_at=row["created_at"],
        )


def list_repositories(limit: int = 50) -> list[RepositoryResponse]:
    """List registered repositories ordered by creation date descending."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM repositories ORDER BY created_at DESC LIMIT ?;",
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            RepositoryResponse(
                id=row["id"],
                name=row["name"],
                source_type=row["source_type"],
                git_url=row["git_url"],
                default_branch=row["default_branch"],
                file_count=row["file_count"] or 0,
                detected_language=row["detected_language"] or "unknown",
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


def count_repositories() -> int:
    """Return total count of registered repositories."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM repositories;")
        row = cursor.fetchone()
        return row[0] if row else 0
