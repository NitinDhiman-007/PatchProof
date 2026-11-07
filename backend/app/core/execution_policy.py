"""Execution policy, allowlisted commands, and container security profiles."""

import os
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings


class SecurityPolicyViolation(Exception):
    """Raised when an execution request violates security policy."""

    pass


# Strictly allowlisted commands and flags
ALLOWED_BINARIES = {"pytest", "ruff"}

ALLOWED_COMMAND_PRESETS = {
    "pytest": ["pytest", "-v", "--tb=short"],
    "pytest_verbose": ["pytest", "-vv", "--tb=short"],
    "pytest_quiet": ["pytest", "-q"],
    "ruff": ["ruff", "check", "."],
}


@dataclass(frozen=True)
class ContainerSecurityProfile:
    """Security constraints for disposable Docker execution containers."""

    image: str
    network_mode: str = "none"
    user: str = "1000:1000"
    cap_drop: list[str] = field(default_factory=lambda: ["ALL"])
    security_opt: list[str] = field(default_factory=lambda: ["no-new-privileges:true"])
    mem_limit: str = "512m"
    nano_cpus: int = 1_000_000_000  # 1.0 CPU
    pids_limit: int = 64
    timeout_seconds: int = 30
    read_only: bool = True
    tmpfs: dict[str, str] = field(
        default_factory=lambda: {
            "/tmp": "rw,noexec,nosuid,size=64m",  # nosec B108 - Container-internal tmpfs mount
        }
    )


def get_default_security_profile() -> ContainerSecurityProfile:
    """Instantiate container security profile from centralized settings."""
    settings = get_settings()
    return ContainerSecurityProfile(
        image=settings.DOCKER_PYTHON_IMAGE,
        mem_limit=settings.DOCKER_MEMORY_LIMIT,
        nano_cpus=settings.DOCKER_NANO_CPUS,
        pids_limit=settings.DOCKER_PIDS_LIMIT,
        timeout_seconds=settings.DOCKER_TIMEOUT_SECONDS,
    )


def validate_command(command: str | list[str]) -> list[str]:
    """
    Validate and sanitize execution commands against strict allowlist.
    Prevents arbitrary command execution, shell injection, and unauthorized binaries.
    """
    if isinstance(command, str):
        # Match against preset names or exact strings
        clean_key = command.strip().lower()
        if clean_key in ALLOWED_COMMAND_PRESETS:
            return list(ALLOWED_COMMAND_PRESETS[clean_key])

        # Reject any shell metacharacters in raw string
        for forbidden in [";", "&", "|", "`", "$", ">", "<", "\n", "\r", "&&", "||"]:
            if forbidden in command:
                raise SecurityPolicyViolation(f"Forbidden shell metacharacter '{forbidden}' in command: {command}")

        parts = command.strip().split()
    elif isinstance(command, list):
        parts = [str(p).strip() for p in command if str(p).strip()]
    else:
        raise SecurityPolicyViolation("Command must be a non-empty string or list of arguments.")

    if not parts:
        raise SecurityPolicyViolation("Command cannot be empty.")

    binary = parts[0]
    if binary not in ALLOWED_BINARIES:
        raise SecurityPolicyViolation(
            f"Unauthorized binary '{binary}'. Only {sorted(ALLOWED_BINARIES)} are permitted."
        )

    # Validate arguments for pytest
    if binary == "pytest":
        valid_pytest_flags = {
            "-v",
            "-vv",
            "-q",
            "--tb=short",
            "--tb=auto",
            "--tb=no",
            "--tb=line",
            "--tb",
            "--capture=no",
            "-s",
            "--disable-warnings",
            "-k",
        }
        i = 1
        while i < len(parts):
            arg = parts[i]
            if arg.startswith("-"):
                flag_name = arg.split("=")[0]
                if arg not in valid_pytest_flags and flag_name not in valid_pytest_flags:
                    raise SecurityPolicyViolation(f"Unallowlisted flag '{arg}' for pytest execution.")
                if flag_name == "-k" and "=" not in arg:
                    # Skip next arg as it's the filter expression
                    i += 1
                elif flag_name == "--tb" and "=" not in arg:
                    i += 1
            else:
                # Path argument: must not contain path traversal
                if ".." in arg or arg.startswith("/") or (len(arg) > 1 and arg[1] == ":"):
                    raise SecurityPolicyViolation(f"Path traversal detected in command argument: {arg}")
            i += 1

    # Validate arguments for ruff
    elif binary == "ruff":
        valid_ruff_flags = {"check", ".", "--isolated", "--no-fix", "-q"}
        for arg in parts[1:]:
            if arg not in valid_ruff_flags:
                raise SecurityPolicyViolation(f"Unallowlisted argument '{arg}' for ruff execution.")

    return parts


def validate_workspace_path(path: str, base_dir: Optional[str] = None) -> str:
    """
    Validate that the repository workspace path is safe and contained within allowed directory.
    Prevents mounting host root, system directories, or path traversals.
    """
    settings = get_settings()
    allowed_base = os.path.abspath(base_dir or settings.WORKSPACE_BASE_DIR)

    if not path or not path.strip():
        raise SecurityPolicyViolation("Workspace path cannot be empty.")

    clean_path = os.path.abspath(path.strip())

    # Path traversal check
    if ".." in path.replace("\\", "/").split("/"):
        raise SecurityPolicyViolation(f"Path traversal sequence detected in workspace path: {path}")

    # Check prefix containment
    try:
        common = os.path.commonpath([clean_path, allowed_base])
        if os.path.abspath(common) != allowed_base:
            raise SecurityPolicyViolation(f"Workspace path '{clean_path}' escapes allowed root '{allowed_base}'.")
    except ValueError as e:
        raise SecurityPolicyViolation(f"Invalid path comparison across drives: {e}")

    return clean_path
