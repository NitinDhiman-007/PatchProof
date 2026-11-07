"""Unit tests for BharatCode OpenAI-compatible API client and error handling."""

from unittest.mock import MagicMock

import pytest
from openai import AuthenticationError

from app.core.config import Settings
from app.services.bharatcode_service import BharatCodeService, BharatCodeServiceError


def test_missing_api_key_raises_error(monkeypatch):
    """When BHARATCODE_API_KEY is empty, get_client() should raise a clear error."""
    mock_settings = Settings(BHARATCODE_API_KEY="")
    monkeypatch.setattr("app.services.bharatcode_service.get_settings", lambda: mock_settings)

    service = BharatCodeService()
    with pytest.raises(BharatCodeServiceError) as exc_info:
        service.get_client()

    assert exc_info.value.status_code == 401
    assert "not configured" in exc_info.value.message


def test_check_connectivity_when_unconfigured(monkeypatch):
    """When API key is empty, check_connectivity returns unconfigured status gracefully."""
    mock_settings = Settings(BHARATCODE_API_KEY="")
    monkeypatch.setattr("app.services.bharatcode_service.get_settings", lambda: mock_settings)

    service = BharatCodeService()
    status = service.check_connectivity()

    assert status["configured"] is False
    assert status["reachable"] is False
    assert "Set BHARATCODE_API_KEY" in status["message"]


def test_check_connectivity_authenticated(monkeypatch):
    """When API key is present and model responds, connectivity reports reachable."""
    mock_settings = Settings(BHARATCODE_API_KEY="test-mock-key")
    monkeypatch.setattr("app.services.bharatcode_service.get_settings", lambda: mock_settings)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "pong"
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    service = BharatCodeService(client=mock_client)
    status = service.check_connectivity()

    assert status["configured"] is True
    assert status["reachable"] is True
    assert "authenticated" in status["message"]


def test_check_connectivity_auth_failure(monkeypatch):
    """When authentication fails (401), connectivity reports reachable: False."""
    mock_settings = Settings(BHARATCODE_API_KEY="bad-key")
    monkeypatch.setattr("app.services.bharatcode_service.get_settings", lambda: mock_settings)

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = AuthenticationError(
        message="Invalid API Key",
        response=MagicMock(status_code=401),
        body={},
    )

    service = BharatCodeService(client=mock_client)
    status = service.check_connectivity()

    assert status["configured"] is True
    assert status["reachable"] is False
    assert "Authentication failed" in status["message"]


def test_extract_json_payload_clean():
    """Extract raw JSON successfully."""
    service = BharatCodeService()
    raw = '{"problem_summary": "Issue found", "confidence_score": 0.9}'
    parsed = service._extract_json_payload(raw)

    assert parsed["problem_summary"] == "Issue found"
    assert parsed["confidence_score"] == 0.9


def test_extract_json_payload_from_markdown_fence():
    """Extract JSON nested inside markdown code fences."""
    service = BharatCodeService()
    raw = """Here is the analysis:
```json
{
  "problem_summary": "Calculation error",
  "affected_files": [{"file_path": "discount.py"}]
}
```
Hope this helps."""
    parsed = service._extract_json_payload(raw)

    assert parsed["problem_summary"] == "Calculation error"
    assert parsed["affected_files"][0]["file_path"] == "discount.py"


def test_extract_json_payload_invalid_raises():
    """Malformed non-JSON output should raise BharatCodeServiceError."""
    service = BharatCodeService()
    with pytest.raises(BharatCodeServiceError) as exc_info:
        service._extract_json_payload("This is not valid JSON at all.")

    assert exc_info.value.status_code == 502
    assert "not valid JSON" in exc_info.value.message


def test_generate_root_cause_analysis():
    """Verify structured root cause analysis generation."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = """
    {
        "problem_summary": "Discount treated as ratio instead of percentage",
        "suspected_root_cause": "Function multiplies directly without dividing by 100",
        "affected_files": [{"file_path": "calculator/discount.py", "line_numbers": [10], "reason": "Missing divide by 100"}],
        "explanation": "When 20 is passed, it calculates price - price * 20",
        "confidence_score": 0.95,
        "confidence_explanation": "Direct mathematical analysis confirms bug",
        "proposed_correction_strategy": "Divide discount by 100 if > 1 or standardize input"
    }
    """
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    service = BharatCodeService(client=mock_client)
    res = service.generate_root_cause_analysis(
        bug_description="Percentage discount calculated wrong",
        stack_trace=None,
        code_snippets=[{"file_path": "calculator/discount.py", "start_line": 1, "end_line": 15, "code": "def calculate_discount(): ..."}],
        repo_metadata={"name": "demo"},
    )

    assert res["problem_summary"] == "Discount treated as ratio instead of percentage"
    assert res["confidence_score"] == 0.95
    assert len(res["affected_files"]) == 1


def test_generate_reproduction_test():
    """Verify reproduction test generation and path safety."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = """
    {
        "test_file_path": "../evil_path.py",
        "test_code": "def test_reproduce(): assert calculate_discount(1000, 20) == 800",
        "test_explanation": "Checks percentage discount"
    }
    """
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    service = BharatCodeService(client=mock_client)
    res = service.generate_reproduction_test(
        bug_description="Calculate discount fails",
        stack_trace=None,
        root_cause={"suspected_root_cause": "missing divide by 100"},
        code_snippets=[],
        existing_test_paths=[],
    )

    # Path must be forced to safe relative tests/ location
    assert res["test_file_path"] == "tests/test_reproduce_patchproof.py"
    assert "test_reproduce" in res["test_code"]
