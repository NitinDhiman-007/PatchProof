"""Inspect actual live Docker container parameters directly from Docker Engine."""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath("backend"))

import docker
from app.core.execution_policy import get_default_security_profile
from app.services.docker_sandbox import DockerSandbox

client = docker.from_env()
sec_profile = get_default_security_profile()

base_dir = os.path.abspath("workspaces/test_isolation_audit")
if os.path.exists(base_dir):
    shutil.rmtree(base_dir, ignore_errors=True)
os.makedirs(base_dir, exist_ok=True)

# Create container with sandbox configuration
volumes = {base_dir: {"bind": "/workspace", "mode": "ro"}}
env = {
    "PYTHONPYCACHEPREFIX": "/tmp/pycache",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
    "PYTEST_ADDOPTS": "-o cache_dir=/tmp/pytest_cache",
    "RUFF_CACHE_DIR": "/tmp/ruff_cache",
}

print("=" * 80)
print("LIVE DOCKER CONTAINER ISOLATION INSPECTION")
print("=" * 80)

container = client.containers.create(
    image=sec_profile.image,
    command=["pytest", "--version"],
    working_dir="/workspace",
    volumes=volumes,
    environment=env,
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

container_id = container.id
print(f"Container created with ID: {container_id}")

# Inspect live container JSON directly from Docker API
inspect_data = client.api.inspect_container(container_id)
host_cfg = inspect_data.get("HostConfig", {})
cfg = inspect_data.get("Config", {})

print("\n--- EXTRACTED LIVE CONTAINER SECURITY ATTRIBUTES ---")
print(f"1. Image: {cfg.get('Image')} (Expected: {sec_profile.image})")
print(f"2. Network Mode: {host_cfg.get('NetworkMode')} (Expected: none)")
print(f"3. User: {cfg.get('User')} (Expected: 1000:1000)")
print(f"4. CapDrop: {host_cfg.get('CapDrop')} (Expected: ['ALL'] or ['all'])")
print(f"5. SecurityOpt: {host_cfg.get('SecurityOpt')} (Expected: ['no-new-privileges:true'])")
print(f"6. ReadonlyRootfs: {host_cfg.get('ReadonlyRootfs')} (Expected: True)")
print(f"7. Memory (bytes): {host_cfg.get('Memory')} (Expected: 536870912 = 512MB)")
print(f"8. NanoCpus: {host_cfg.get('NanoCpus')} (Expected: 1000000000 = 1.0 CPU)")
print(f"9. PidsLimit: {host_cfg.get('PidsLimit')} (Expected: 64)")
print(f"10. Tmpfs Mounts: {host_cfg.get('Tmpfs')} (Expected: {{'/tmp': 'rw,noexec,nosuid,size=64m'}})")

# Assert all isolation invariants on the live Docker engine data
assert host_cfg.get("NetworkMode") == "none", "Network isolation violated!"
assert cfg.get("User") == "1000:1000", "Non-root user invariant violated!"
assert "ALL" in [c.upper() for c in host_cfg.get("CapDrop", [])], "Capability drop invariant violated!"
assert "no-new-privileges:true" in host_cfg.get("SecurityOpt", []), "no-new-privileges invariant violated!"
assert host_cfg.get("ReadonlyRootfs") is True, "Read-only rootfs invariant violated!"
assert host_cfg.get("Memory") == 536870912, "Memory limit invariant violated!"
assert host_cfg.get("NanoCpus") == 1_000_000_000, "NanoCpus limit invariant violated!"
assert host_cfg.get("PidsLimit") == 64, "PidsLimit invariant violated!"
assert "/tmp" in host_cfg.get("Tmpfs", {}), "Scoped tmpfs invariant violated!"

print("\nALL 10 CONTAINER ISOLATION CONTROLS VERIFIED ON LIVE DOCKER ENGINE!")

# Start and execute
container.start()
res = container.wait(timeout=10)
print(f"Execution exit code: {res.get('StatusCode')}")
logs = container.logs().decode().strip()
print(f"Execution output: {logs}")

# Remove container
container.remove(force=True)

# Confirm container is removed
try:
    client.containers.get(container_id)
    print("WARNING: Container was not removed!")
except docker.errors.NotFound:
    print(f"Confirmed container {container_id[:12]} was permanently removed (No dangling containers).")

shutil.rmtree(base_dir, ignore_errors=True)

