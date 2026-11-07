"""Tests for configuration settings and code parser utilities."""

from app.core.config import Settings
from app.services.code_search_service import parse_python_ast


def test_settings_defaults():
    """Test default values for application configuration."""
    settings = Settings()
    assert settings.PROJECT_NAME == "PatchProof API"
    assert settings.VERSION == "0.1.0"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.DATABASE_URL.startswith("sqlite:///")
    assert isinstance(settings.CORS_ORIGINS, list)
    assert "http://localhost:3000" in settings.CORS_ORIGINS


def test_settings_cors_origins_parsing():
    """Test parsing CORS origins from comma separated strings and JSON arrays."""
    custom1 = Settings(CORS_ORIGINS="http://localhost:3000,http://app.local")
    assert "http://app.local" in custom1.CORS_ORIGINS

    custom2 = Settings(CORS_ORIGINS='["http://sub.domain.com"]')
    assert "http://sub.domain.com" in custom2.CORS_ORIGINS


def test_tree_sitter_python_parser():
    """Test safe AST parsing of Python source code."""
    sample_code = """
class Calculator:
    def add(self, a, b):
        return a + b

def standalone_helper():
    pass
"""
    result = parse_python_ast(sample_code)
    assert result["success"] is True
    assert "Calculator" in result["classes"]
    assert "add" in result["functions"]
    assert "standalone_helper" in result["functions"]


def test_settings_bharatcode_key_detected_when_configured():
    """Verify BHARATCODE_API_KEY is detected as configured when set."""
    custom = Settings(BHARATCODE_API_KEY="test-sample-key")
    assert bool(custom.BHARATCODE_API_KEY.strip()) is True
    assert custom.BHARATCODE_BASE_URL == "https://bharatcode.ai/api/model/v1"
    assert custom.BHARATCODE_MODEL == "qwen-3.8-27b"


def test_settings_bharatcode_key_reported_missing_when_absent():
    """Verify BHARATCODE_API_KEY is detected as absent when empty."""
    custom = Settings(BHARATCODE_API_KEY="")
    assert bool(custom.BHARATCODE_API_KEY.strip()) is False


def test_settings_loads_from_specified_dotenv(monkeypatch, tmp_path):
    """Verify Settings loads BHARATCODE_API_KEY correctly from dotenv files."""
    monkeypatch.delenv("BHARATCODE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("BHARATCODE_API_KEY=mock-detected-from-file\n", encoding="utf-8")

    class CustomSettings(Settings):
        model_config = {
            "env_file": str(env_file),
            "extra": "ignore",
        }

    loaded = CustomSettings()
    assert bool(loaded.BHARATCODE_API_KEY) is True
    assert loaded.BHARATCODE_API_KEY == "mock-detected-from-file"

