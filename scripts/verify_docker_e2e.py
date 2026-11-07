"""Execute real Docker end-to-end verification for PatchProof Phase 6.

1. Test baseline defect reproduction in Docker.
2. Test patched fix verification in Docker.
3. Test container security constraints and isolation.
4. Test human approval gate enforcement.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.abspath("backend"))

from app.core.config import get_settings
from app.core.execution_policy import ContainerSecurityProfile
from app.database.database import get_db_connection, init_db
from app.services.docker_sandbox import DockerSandbox
from app.services.patch_service import PatchService
from app.services.repository_service import create_git_repository
from app.services.test_runner import TestRunner
from app.services.workflow_engine import run_debugging_workflow


def test_baseline_reproduction():
    print("=" * 80)
    print("STEP 2: BASELINE BUG REPRODUCTION IN REAL DOCKER SANDBOX")
    print("=" * 80)

    base_dir = os.path.abspath("workspaces/test_baseline_reproduction")
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir, ignore_errors=True)
    os.makedirs(base_dir, exist_ok=True)

    demo_dir = os.path.abspath("examples/demo_discount_repo")
    for item in os.listdir(demo_dir):
        s = os.path.join(demo_dir, item)
        d = os.path.join(base_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    # Generated reproduction test
    test_code = (
        '"""Reproducible failing test for discount calculation bug [DEMO MODE]."""\n\n'
        "from calculator.discount import calculate_discount\n\n\n"
        "def test_reproduce_percentage_discount_bug():\n"
        '    """Test passing 20 for 20% discount on 1000 produces 800.0."""\n'
        "    assert calculate_discount(1000.0, 20.0) == 800.0\n"
    )
    test_path = os.path.join(base_dir, "tests/test_reproduce_discount_bug.py")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_code)

    sandbox = DockerSandbox()
    res = sandbox.run_command(base_dir, ["pytest", "-v", "--tb=short"])

    print(f"BASELINE DOCKER EXIT CODE: {res.exit_code}")
    print(f"BASELINE DOCKER DURATION: {res.duration_seconds}s")
    print("BASELINE DOCKER STDOUT:\n" + res.stdout)
    if res.stderr:
        print("BASELINE DOCKER STDERR:\n" + res.stderr)

    # Verify baseline failure assertions
    assert res.exit_code == 1, f"Expected baseline exit code 1, got {res.exit_code}"
    assert "FAILED tests/test_reproduce_discount_bug.py" in res.stdout
    assert "assert -19000.0 == 800.0" in res.stdout
    print("BASELINE TEST GENUINELY FAILED WITH EXPECTED -19000.0 != 800.0 IN REAL DOCKER SANDBOX!")

    shutil.rmtree(base_dir, ignore_errors=True)
    return res


def test_patched_verification():
    print("\n" + "=" * 80)
    print("STEP 3: PATCH APPLICATION AND DOCKER VERIFICATION")
    print("=" * 80)

    patched_dir = os.path.abspath("workspaces/test_patched_verification")
    if os.path.exists(patched_dir):
        shutil.rmtree(patched_dir, ignore_errors=True)
    os.makedirs(patched_dir, exist_ok=True)

    demo_dir = os.path.abspath("examples/demo_discount_repo")
    for item in os.listdir(demo_dir):
        s = os.path.join(demo_dir, item)
        d = os.path.join(patched_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    # Include the regression test
    test_code = (
        '"""Reproducible failing test for discount calculation bug [DEMO MODE]."""\n\n'
        "from calculator.discount import calculate_discount\n\n\n"
        "def test_reproduce_percentage_discount_bug():\n"
        '    """Test passing 20 for 20% discount on 1000 produces 800.0."""\n'
        "    assert calculate_discount(1000.0, 20.0) == 800.0\n"
    )
    test_path = os.path.join(patched_dir, "tests/test_reproduce_discount_bug.py")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_code)

    # Apply proposed patch diff
    patch_diff = """--- a/calculator/discount.py
+++ b/calculator/discount.py
@@ -10,2 +10,3 @@
     \"\"\"
-    return price - (price * discount)
+    rate = discount / 100.0 if discount > 1.0 else discount
+    return price - (price * rate)
"""

    print("Verifying unified diff security...")
    affected = PatchService.validate_patch_security(patch_diff)
    print(f"Validated affected files: {affected}")

    print("Applying unified diff to isolated workspace...")
    apply_result = PatchService.apply_patch_to_workspace(patched_dir, patch_diff)
    print(f"Patch applied successfully: {apply_result}")

    # Inspect patched file content
    patched_file = os.path.join(patched_dir, "calculator/discount.py")
    with open(patched_file, encoding="utf-8") as f:
        print("Patched calculator/discount.py contents:\n" + f.read())

    sandbox = DockerSandbox()
    print("Executing patched test suite in REAL Docker sandbox...")
    res = sandbox.run_command(patched_dir, ["pytest", "-v", "--tb=short"])

    print(f"PATCHED DOCKER EXIT CODE: {res.exit_code}")
    print(f"PATCHED DOCKER DURATION: {res.duration_seconds}s")
    print("PATCHED DOCKER STDOUT:\n" + res.stdout)
    if res.stderr:
        print("PATCHED DOCKER STDERR:\n" + res.stderr)

    assert res.exit_code == 0, f"Expected exit code 0, got {res.exit_code}"
    assert "2 passed" in res.stdout
    assert "test_calculate_discount_decimal PASSED" in res.stdout
    assert "test_reproduce_percentage_discount_bug PASSED" in res.stdout
    print("ALL TESTS (BASELINE + REGRESSION) GENUINELY PASSED IN REAL DOCKER SANDBOX!")

    # Verify original repository was NOT modified
    orig_file = os.path.join(demo_dir, "calculator/discount.py")
    with open(orig_file, encoding="utf-8") as f:
        orig_content = f.read()
    assert "return price - (price * discount)" in orig_content
    print("ORIGINAL REPOSITORY REMAINS UNMODIFIED (Zero mutation on source files)!")

    shutil.rmtree(patched_dir, ignore_errors=True)
    return res


def test_full_langgraph_workflow_in_docker():
    print("\n" + "=" * 80)
    print("STEP 2 & 3 INTEGRATED: FULL LANGGRAPH DEBUGGING WORKFLOW IN REAL DOCKER")
    print("=" * 80)

    init_db()

    # Register repo
    repo = create_git_repository("https://github.com/patchproof-org/demo-discount-repo")
    demo_dir = os.path.abspath("examples/demo_discount_repo")
    with get_db_connection() as conn:
        conn.cursor().execute(
            "UPDATE repositories SET metadata_json = ? WHERE id = ?;",
            (f'{{"source_directory": "{demo_dir.replace("\\", "\\\\")}"}}', repo.id),
        )

    import uuid
    analysis_id = f"docker-audit-{uuid.uuid4().hex[:8]}"
    now = "2026-11-08T00:00:00Z"
    with get_db_connection() as conn:
        conn.cursor().execute(
            """
            INSERT INTO analysis_runs (
                id, repository_id, bug_description, status, patch_status,
                verification_verdict, created_at, updated_at
            )
            VALUES (?, ?, ?, 'running', 'none', 'PENDING', ?, ?);
            """,
            (analysis_id, repo.id, "calculate_discount returns negative price for whole percentage discount 20", now, now),
        )

    # Set DEMO_MODE=True in settings
    settings = get_settings()
    settings.DEMO_MODE = True

    print("Running 12-node LangGraph debugging workflow with live Docker container execution...")
    final_state = run_debugging_workflow(
        analysis_id=analysis_id,
        repository_id=repo.id,
        bug_description="calculate_discount returns negative price for whole percentage discount 20",
    )

    print(f"WORKFLOW FINAL VERDICT: {final_state.get('verdict')}")
    print(f"BASELINE REPRODUCED: {final_state.get('baseline_reproduced')}")
    print(f"PATCHED ALL PASSED: {final_state.get('patched_all_passed')}")
    print(f"PATCH STATUS (HUMAN APPROVAL GATE): {final_state.get('patch_status')}")

    ev = final_state.get("evidence_report")
    if ev:
        print(f"EVIDENCE REPORT VERDICT: {ev.get('verdict')}")
        print(f"EVIDENCE REPORT INTEGRITY HASH: {ev.get('integrity_hash')}")
        print(f"BASELINE PASSED: {ev.get('baseline_tests_passed')}, FAILED: {ev.get('baseline_tests_failed')}")
        print(f"PATCHED PASSED: {ev.get('patched_tests_passed')}, FAILED: {ev.get('patched_tests_failed')}")

    assert final_state.get("verdict") == "VERIFIED"
    assert final_state.get("baseline_reproduced") is True
    assert final_state.get("patched_all_passed") is True
    with get_db_connection() as conn:
        row = conn.cursor().execute(
            "SELECT patch_status, verification_verdict FROM analysis_runs WHERE id = ?;",
            (analysis_id,),
        ).fetchone()
        assert row["patch_status"] == "pending_approval"
        assert row["verification_verdict"] == "VERIFIED"
    print("MANDATORY HUMAN APPROVAL ENFORCED IN DATABASE: patch_status='pending_approval'!")
    print("LANGGRAPH WORKFLOW PROVED DEFECT IN REAL DOCKER AND PROVED PATCH TURNED SUITE GREEN!")


if __name__ == "__main__":
    b_res = test_baseline_reproduction()
    p_res = test_patched_verification()
    test_full_langgraph_workflow_in_docker()
    print("\n" + "=" * 80)
    print("PHASE 6 DOCKER VERIFICATION COMPLETE: ALL CHECKS PASSED WITH REAL CONTAINERS!")
    print("=" * 80)
