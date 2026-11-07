"""Tests for repository registration and safe validation."""

import io
import zipfile

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_valid_git_url():
    """Test registering a valid GitHub repository URL."""
    payload = {
        "git_url": "https://github.com/psf/requests",
        "default_branch": "main",
    }
    response = client.post("/api/v1/repositories/register-url", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "psf/requests"
    assert data["source_type"] == "git"
    assert data["git_url"] == payload["git_url"]
    assert "id" in data


def test_register_invalid_git_url():
    """Test malformed URL formats are rejected."""
    payload = {"git_url": "not-a-valid-url"}
    response = client.post("/api/v1/repositories/register-url", json=payload)
    assert response.status_code == 422


def test_register_injection_git_url():
    """Test Git URL with command injection payload is rejected by validation."""
    payload = {"git_url": "https://github.com/test/repo;cat /etc/passwd"}
    response = client.post("/api/v1/repositories/register-url", json=payload)
    assert response.status_code == 422


def test_register_flag_injection_git_url():
    """Test Git URL starting with hyphen flag is rejected."""
    payload = {"git_url": "--upload-pack=evil"}
    response = client.post("/api/v1/repositories/register-url", json=payload)
    assert response.status_code == 422


def test_upload_valid_zip_archive():
    """Test uploading a safe in-memory ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("src/main.py", "def main(): print('hello world')\n")
        zf.writestr("tests/test_main.py", "def test_main(): assert True\n")
        zf.writestr("README.md", "# Test Project\n")
    buf.seek(0)

    files = {"file": ("test_project.zip", buf.getvalue(), "application/zip")}
    response = client.post("/api/v1/repositories/upload-zip", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["total_files"] == 3
    assert data["detected_language"] == "python"
    assert data["repository"] is not None
    assert data["repository"]["source_type"] == "zip"


def test_upload_zip_with_path_traversal():
    """Test ZIP with directory traversal is rejected safely without extracting."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../evil.sh", "echo bad")
    buf.seek(0)

    files = {"file": ("malicious.zip", buf.getvalue(), "application/zip")}
    response = client.post("/api/v1/repositories/upload-zip", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert any("path traversal" in err.lower() for err in data["errors"])
    assert data["repository"] is None


def test_list_repositories():
    """Test GET /api/v1/repositories returns registered repositories."""
    response = client.get("/api/v1/repositories")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
