"""Tests for health and status endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_health_endpoint():
    """Test GET /health returns 200 OK and valid health schema."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


def test_api_v1_health_endpoint():
    """Test GET /api/v1/health returns 200 OK."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_api_v1_status_endpoint():
    """Test GET /api/v1/status returns system status and database operational info."""
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["operational", "degraded"]
    assert "version" in data
    assert "database" in data
    assert "bharatcode_configured" in data
    assert "repositories_count" in data
    assert isinstance(data["repositories_count"], int)
