"""Automated unit and security tests for Docker sandbox and execution policy."""

from unittest.mock import MagicMock

import pytest

from app.core.execution_policy import (
    SecurityPolicyViolation,
    get_default_security_profile,
    validate_command,
    validate_workspace_path,
)
from app.services.docker_sandbox import DockerSandbox, sanitize_output
from app.services.test_runner import TestRunner, parse_pytest_metrics


def test_unauthorized_command_rejection():
    """Verify unauthorized binaries, shell chaining, and dangerous flags are rejected."""
    # Unauthorized binaries
    with pytest.raises(SecurityPolicyViolation):
        validate_command(["rm", "-rf", "/"])

    with pytest.raises(SecurityPolicyViolation):
        validate_command(["bash", "-c", "echo test"])

    with pytest.raises(SecurityPolicyViolation):
        validate_command(["curl", "http://example.com"])

    # Shell metacharacters and chaining
    with pytest.raises(SecurityPolicyViolation):
        validate_command("pytest; cat /etc/passwd")

    with pytest.raises(SecurityPolicyViolation):
        validate_command("pytest && rm -rf /")

    with pytest.raises(SecurityPolicyViolation):
        validate_command("pytest | grep error")

    with pytest.raises(SecurityPolicyViolation):
        validate_command("pytest `whoami`")

    # Unallowlisted pytest flags
    with pytest.raises(SecurityPolicyViolation):
        validate_command(["pytest", "--import-mode=importlib", "--override-ini=evil"])


def test_allowlisted_commands():
    """Verify strictly allowlisted commands and presets normalize properly."""
    assert validate_command("pytest") == ["pytest", "-v", "--tb=short"]
    assert validate_command("pytest_verbose") == ["pytest", "-vv", "--tb=short"]
    assert validate_command("pytest_quiet") == ["pytest", "-q"]
    assert validate_command("ruff") == ["ruff", "check", "."]
    assert validate_command(["pytest", "-v"]) == ["pytest", "-v"]


def test_workspace_path_validation(tmp_path):
    """Verify workspace path containment and directory traversal rejection."""
    allowed_base = str(tmp_path)

    # Valid subfolder
    sub_workspace = tmp_path / "run_123"
    sub_workspace.mkdir()
    valid = validate_workspace_path(str(sub_workspace), base_dir=allowed_base)
    assert valid == str(sub_workspace.resolve())

    # Path traversal attack
    with pytest.raises(SecurityPolicyViolation):
        validate_workspace_path(str(tmp_path / "../etc"), base_dir=allowed_base)

    # Empty path
    with pytest.raises(SecurityPolicyViolation):
        validate_workspace_path("", base_dir=allowed_base)


def test_security_profile_constraints():
    """Verify strict execution constraints and resource limits."""
    profile = get_default_security_profile()
    assert profile.network_mode == "none"
    assert profile.user == "1000:1000"
    assert profile.cap_drop == ["ALL"]
    assert profile.security_opt == ["no-new-privileges:true"]
    assert profile.read_only is True
    assert profile.mem_limit == "512m"
    assert profile.nano_cpus == 1_000_000_000
    assert profile.pids_limit == 64
    assert profile.timeout_seconds > 0
    assert "/tmp" in profile.tmpfs


def test_docker_unavailable_handling():
    """Verify graceful handling when Docker daemon is offline."""
    mock_client = MagicMock()
    mock_client.ping.side_effect = Exception("Docker daemon connection failed")

    sandbox = DockerSandbox(client=mock_client)
    available, msg = sandbox.is_available()
    assert available is False
    assert "unreachable" in msg.lower() or "failed" in msg.lower()

    # run_command with offline docker returns structured result, does not crash
    sandbox_no_client = DockerSandbox()
    sandbox_no_client._client = None
    sandbox_no_client.get_client = lambda: None

    result = sandbox_no_client.run_command("./workspaces/dummy", "pytest")
    assert result.exit_code is None
    assert "not available" in result.error_message.lower()


def test_mocked_successful_test_execution(tmp_path, monkeypatch):
    """Verify successful test execution and metric extraction with container cleanup."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "WORKSPACE_BASE_DIR", str(tmp_path))

    mock_container = MagicMock()
    mock_container.id = "mock_container_12345"
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = lambda stdout=True, stderr=False: (
        b"test_mod.py::test_ok PASSED\n=== 3 passed in 0.12s ===" if stdout else b""
    )

    mock_docker = MagicMock()
    mock_docker.containers.create.return_value = mock_container

    sandbox = DockerSandbox(client=mock_docker)
    runner = TestRunner(sandbox=sandbox)

    sub_dir = tmp_path / "valid_run"
    sub_dir.mkdir()

    summary = runner.run_test_suite(str(sub_dir), command_preset="pytest", run_ruff=False)

    assert summary.status == "passed"
    assert summary.exit_code == 0
    assert summary.tests_passed == 3
    assert summary.tests_failed == 0

    # Verify container removal was executed
    mock_container.remove.assert_called_once_with(force=True)


def test_mocked_failing_test_execution(tmp_path, monkeypatch):
    """Verify failing test metrics are captured and container is cleaned up."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "WORKSPACE_BASE_DIR", str(tmp_path))

    mock_container = MagicMock()
    mock_container.id = "mock_fail_123"
    mock_container.wait.return_value = {"StatusCode": 1}
    mock_container.logs.side_effect = lambda stdout=True, stderr=False: (
        b"test_bug.py::test_fail FAILED\n=== 2 failed, 1 passed in 0.35s ===" if stdout else b"AssertionError: failed"
    )

    mock_docker = MagicMock()
    mock_docker.containers.create.return_value = mock_container

    sandbox = DockerSandbox(client=mock_docker)
    runner = TestRunner(sandbox=sandbox)

    sub_dir = tmp_path / "valid_fail_run"
    sub_dir.mkdir()

    summary = runner.run_test_suite(str(sub_dir), command_preset="pytest", run_ruff=False)

    assert summary.status == "failed"
    assert summary.exit_code == 1
    assert summary.tests_failed == 2
    assert summary.tests_passed == 1
    mock_container.remove.assert_called_once_with(force=True)


def test_mocked_timeout_handling(tmp_path, monkeypatch):
    """Verify timeout triggers container kill, marks timed_out, and removes container."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "WORKSPACE_BASE_DIR", str(tmp_path))

    mock_container = MagicMock()
    mock_container.id = "mock_timeout_123"
    # Simulate read timeout during wait
    mock_container.wait.side_effect = Exception("Read timed out while waiting for container")
    mock_container.logs.return_value = b"Running long test..."

    mock_docker = MagicMock()
    mock_docker.containers.create.return_value = mock_container

    sandbox = DockerSandbox(client=mock_docker)
    runner = TestRunner(sandbox=sandbox)

    sub_dir = tmp_path / "timeout_run"
    sub_dir.mkdir()

    summary = runner.run_test_suite(str(sub_dir), command_preset="pytest", run_ruff=False)

    assert summary.status == "timed_out"
    assert summary.timed_out is True
    # Verify container kill and cleanup were called
    mock_container.kill.assert_called_once()
    mock_container.remove.assert_called_once_with(force=True)


def test_container_cleanup_on_start_exception(tmp_path, monkeypatch):
    """Verify container is deleted even if container.start() throws an unexpected error."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "WORKSPACE_BASE_DIR", str(tmp_path))

    mock_container = MagicMock()
    mock_container.id = "mock_crash_123"
    mock_container.start.side_effect = RuntimeError("Fatal container launch error")

    mock_docker = MagicMock()
    mock_docker.containers.create.return_value = mock_container

    sandbox = DockerSandbox(client=mock_docker)
    sub_dir = tmp_path / "crash_run"
    sub_dir.mkdir()

    result = sandbox.run_command(str(sub_dir), "pytest")

    assert result.exit_code is None
    assert "Fatal container launch error" in result.error_message
    mock_container.remove.assert_called_once_with(force=True)


def test_network_isolation_enforcement(tmp_path, monkeypatch):
    """Verify network_mode='none' is strictly passed to docker containers.create."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "WORKSPACE_BASE_DIR", str(tmp_path))

    mock_container = MagicMock()
    mock_container.id = "mock_net_123"
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b""

    mock_docker = MagicMock()
    mock_docker.containers.create.return_value = mock_container

    sandbox = DockerSandbox(client=mock_docker)
    sub_dir = tmp_path / "net_run"
    sub_dir.mkdir()

    sandbox.run_command(str(sub_dir), "pytest")

    # Assert network_mode='none' in kwargs
    call_kwargs = mock_docker.containers.create.call_args.kwargs
    assert call_kwargs.get("network_mode") == "none"
    assert call_kwargs.get("user") == "1000:1000"
    assert call_kwargs.get("cap_drop") == ["ALL"]
    assert call_kwargs.get("security_opt") == ["no-new-privileges:true"]


def test_parse_pytest_metrics():
    """Verify parser extracts numbers accurately across various pytest output formats."""
    sample_output = """
test_one.py::test_alpha PASSED
test_one.py::test_beta FAILED
test_one.py::test_gamma SKIPPED
================= 1 failed, 1 passed, 1 skipped in 0.15s =================
"""
    metrics = parse_pytest_metrics(sample_output)
    assert metrics["passed"] == 1
    assert metrics["failed"] == 1
    assert metrics["skipped"] == 1


def test_sanitize_output():
    """Verify ANSI escape codes are stripped."""
    colored = "\x1b[32mPASSED\x1b[0m \x1b[31mFAILED\x1b[0m\r\n"
    clean = sanitize_output(colored)
    assert clean == "PASSED FAILED"
