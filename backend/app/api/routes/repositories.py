"""Repository management and validation endpoints."""

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.logging import get_logger
from app.models.schemas import (
    GitUrlRegistrationRequest,
    RepositoryResponse,
    ZipMetadataRequest,
    ZipValidationResponse,
)
from app.services.repository_service import (
    create_git_repository,
    create_zip_repository,
    get_repository,
    inspect_zip_archive_safety,
    list_repositories,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.post(
    "/register-url",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register repository via Git URL",
)
def register_git_url(payload: GitUrlRegistrationRequest) -> RepositoryResponse:
    """
    Validate Git URL format and register repository metadata.
    Enforces URL sanitation to prevent command injection.
    Does NOT clone or execute code on the host.
    """
    try:
        repo = create_git_repository(
            git_url=payload.git_url,
            default_branch=payload.default_branch or "main",
        )
        return repo
    except Exception as e:
        logger.error("Failed to register Git repository: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register repository: {e!s}",
        )


@router.post(
    "/upload-zip",
    response_model=ZipValidationResponse,
    summary="Safely inspect and register an uploaded ZIP repository",
)
async def upload_zip_repository(
    file: UploadFile = File(..., description="ZIP archive of the codebase"),
) -> ZipValidationResponse:
    """
    Safely inspect an uploaded ZIP archive in memory.
    Guarantees:
    - No execution of repository code.
    - Path traversal defense.
    - Zip bomb detection and threshold limits.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only valid .zip files are accepted.",
        )

    try:
        content = await file.read()
    except Exception as e:
        logger.error("Failed to read uploaded file: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read uploaded archive payload.",
        )

    is_safe, errors, metadata = inspect_zip_archive_safety(content, file.filename)

    if not is_safe:
        return ZipValidationResponse(
            is_valid=False,
            message="Archive validation failed security or size checks.",
            repository=None,
            filename=file.filename,
            file_size_bytes=len(content),
            total_files=metadata.get("total_files", 0),
            top_level_directories=metadata.get("top_level_directories", []),
            detected_language="unknown",
            errors=errors,
        )

    # Register validated ZIP repository in SQLite
    repo = create_zip_repository(
        filename=file.filename,
        file_count=metadata.get("total_files", 0),
        detected_language=metadata.get("detected_language", "unknown"),
        metadata=metadata,
    )

    return ZipValidationResponse(
        is_valid=True,
        message="ZIP archive verified safely and registered successfully.",
        repository=repo,
        filename=file.filename,
        file_size_bytes=len(content),
        total_files=metadata.get("total_files", 0),
        top_level_directories=metadata.get("top_level_directories", []),
        detected_language=metadata.get("detected_language", "unknown"),
        errors=[],
    )


@router.post(
    "/validate-metadata",
    response_model=ZipValidationResponse,
    summary="Validate pre-parsed ZIP metadata",
)
def validate_zip_metadata(payload: ZipMetadataRequest) -> ZipValidationResponse:
    """Validate ZIP metadata without receiving binary content."""
    errors: list[str] = []

    if not payload.filename.lower().endswith(".zip"):
        errors.append("Filename must end with .zip")

    if payload.file_size_bytes > 50 * 1024 * 1024:
        errors.append("File size exceeds 50MB maximum threshold.")

    for dir_name in payload.top_level_directories:
        if ".." in dir_name or "/" in dir_name or "\\" in dir_name:
            errors.append(f"Invalid directory name detected: {dir_name}")

    is_valid = len(errors) == 0
    return ZipValidationResponse(
        is_valid=is_valid,
        message="Metadata check passed" if is_valid else "Metadata validation failed",
        repository=None,
        filename=payload.filename,
        file_size_bytes=payload.file_size_bytes,
        total_files=payload.file_count,
        top_level_directories=payload.top_level_directories,
        detected_language="unknown",
        errors=errors,
    )


@router.get(
    "",
    response_model=list[RepositoryResponse],
    summary="List registered repositories",
)
def get_repositories() -> list[RepositoryResponse]:
    """Retrieve all registered repositories."""
    return list_repositories()


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get repository details by ID",
)
def get_repository_by_id(repository_id: str) -> RepositoryResponse:
    """Retrieve a single repository by its unique identifier."""
    repo = get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repository_id}' not found.",
        )
    return repo
