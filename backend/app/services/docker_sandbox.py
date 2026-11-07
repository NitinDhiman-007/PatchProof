"""Docker execution sandbox engine enforcing isolation and resource boundaries."""

import re
import time
from dataclasses import dataclass
from typing import Optional

from app.core.execution_policy import (
    ContainerSecurityProfile,
    get_default_security_profile,
    validate_command,
    validate_workspace_path,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Telemetry and outcome of a containerized execution."""

    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    error_message: Optional[str] = None
    container_id: Optional[str] = None


def sanitize_output(text: str) -> str:
    """Remove terminal ANSI escape codes and normalize whitespace."""
    if not text:
        return ""
    # Strip ANSI escape sequences
    ansi_regex = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    cleaned = ansi_regex.sub("", text)
    return cleaned.replace("\r\n", "\n").strip()


class DockerSandbox:
    """Manages isolated test execution in disposable Docker containers."""

    def __init__(self, client=None):
        self._client = client

    def get_client(self):
        """Lazy-initialize Docker client from environment."""
        if self._client is not None:
            return self._client

        try:
            import docker

            self._client = docker.from_env()
            return self._client
        except Exception as e:
            logger.warning("Could not initialize Docker client: %s", e)
            return None

    def is_available(self) -> tuple[bool, str]:
        """Verify connectivity to local Docker daemon."""
        client = self.get_client()
        if client is None:
            return False, "Docker SDK could not initialize a client from environment."

        try:
            ping_ok = client.ping()
            if ping_ok:
                version_info = client.version().get("Version", "unknown")
                return True, f"Docker daemon operational (version {version_info})."
            return False, "Docker ping returned false."
        except Exception as e:
            return False, f"Docker daemon unreachable: {str(e)}"

    def run_command(
        self,
        workspace_path: str,
        command: list[str] | str,
        profile: Optional[ContainerSecurityProfile] = None,
    ) -> ExecutionResult:
        """
        Execute an allowlisted command in a disposable, unprivileged Docker container.
        Enforces:
        - Network isolation (network_mode='none')
        - Non-root user (1000:1000)
        - Dropped capabilities (cap_drop=['ALL'])
        - Strict memory, CPU, PID, and execution-time limits
        - Read-only root filesystem with scoped tmpfs
        - Unconditional container removal upon exit, error, or timeout
        """
        start_time = time.time()
        sec_profile = profile or get_default_security_profile()

        # 1. Validate command allowlist
        cmd_parts = validate_command(command)

        # 2. Validate workspace filesystem containment
        valid_workspace = validate_workspace_path(workspace_path)

        # 3. Verify Docker availability
        client = self.get_client()
        if client is None:
            duration = round(time.time() - start_time, 3)
            return ExecutionResult(
                exit_code=None,
                stdout="",
                stderr="",
                duration_seconds=duration,
                timed_out=False,
                error_message="Docker engine is not available or daemon is not running.",
            )

        container = None
        timed_out = False
        raw_stdout = b""
        raw_stderr = b""
        exit_code = None

        try:
            logger.info(
                "Creating disposable sandbox container [%s] in %s",
                " ".join(cmd_parts),
                valid_workspace,
            )

            # Mount workspace into /workspace (read-only root + tmpfs cache)
            volumes = {
                valid_workspace: {"bind": "/workspace", "mode": "ro"},
            }

            environment = {
                "PYTHONPYCACHEPREFIX": "/tmp/pycache",  # nosec B108 - Container-scoped path
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "PYTEST_ADDOPTS": "-o cache_dir=/tmp/pytest_cache",
                "RUFF_CACHE_DIR": "/tmp/ruff_cache",
            }

            container = client.containers.create(
                image=sec_profile.image,
                command=cmd_parts,
                working_dir="/workspace",
                volumes=volumes,
                environment=environment,
                network_mode=sec_profile.network_mode,
                user=sec_profile.user,
                cap_drop=sec_profile.cap_drop,
                security_opt=sec_profile.security_opt,
                mem_limit=sec_profile.mem_limit,
                nano_cpus=sec_profile.nano_cpus,
                pids_limit=sec_profile.pids_limit,
                read_only=sec_profile.read_only,
                tmpfs=sec_profile.tmpfs,
                detach=True,
            )

            container.start()

            # Wait with execution timeout
            timeout = sec_profile.timeout_seconds
            try:
                wait_res = container.wait(timeout=timeout)
                exit_code = wait_res.get("StatusCode", 1)
            except Exception as wait_exc:
                # Timeout or wait failure
                if "read timed out" in str(wait_exc).lower() or "timeout" in str(wait_exc).lower():
                    logger.warning("Execution timed out after %ds. Killing container.", timeout)
                    timed_out = True
                    try:
                        container.kill()
                    except Exception as kill_exc:
                        logger.debug("Container kill suppressed: %s", kill_exc)
                else:
                    raise wait_exc

            # Capture output streams safely
            try:
                raw_stdout = container.logs(stdout=True, stderr=False) or b""
                raw_stderr = container.logs(stdout=False, stderr=True) or b""
            except Exception as log_exc:
                logger.warning("Could not read logs from container: %s", log_exc)

            duration = round(time.time() - start_time, 3)

            return ExecutionResult(
                exit_code=exit_code if not timed_out else -1,
                stdout=sanitize_output(raw_stdout.decode("utf-8", errors="replace")),
                stderr=sanitize_output(raw_stderr.decode("utf-8", errors="replace")),
                duration_seconds=duration,
                timed_out=timed_out,
                error_message="Execution exceeded timeout limit." if timed_out else None,
                container_id=container.id[:12] if container else None,
            )

        except Exception as e:
            duration = round(time.time() - start_time, 3)
            logger.error("Container execution error: %s", e)
            return ExecutionResult(
                exit_code=None,
                stdout=sanitize_output(raw_stdout.decode("utf-8", errors="replace")),
                stderr=sanitize_output(raw_stderr.decode("utf-8", errors="replace")),
                duration_seconds=duration,
                timed_out=timed_out,
                error_message=f"Infrastructure error during container execution: {str(e)}",
                container_id=container.id[:12] if container else None,
            )

        finally:
            # Unconditional cleanup of disposable container
            if container:
                try:
                    container.remove(force=True)
                    logger.debug("Removed sandbox container %s", container.id[:12])
                except Exception as cleanup_err:
                    logger.warning("Error during container cleanup: %s", cleanup_err)
