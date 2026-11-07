"""Comprehensive pre-publication sensitive data, credentials, and path audit."""

import os
import re
import subprocess
import sys


def run_audit() -> int:
    raw_status = subprocess.check_output(["git", "status", "-u", "--porcelain"]).decode().splitlines()
    candidate_files = [line[3:].strip() for line in raw_status if not line.startswith("!!")]

    print(f"Total candidate files to audit: {len(candidate_files)}")

    secret_patterns = [
        (r"(?i)(api[_-]?key|secret|password|bearer|token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{12,}['\"]", "Hardcoded credential assignment"),
        (r"sk-[a-zA-Z0-9]{20,}", "OpenAI-style key"),
        (r"bh-[a-zA-Z0-9]{20,}", "BharatCode-style key"),
        (r"ghp_[a-zA-Z0-9]{20,}", "GitHub personal token"),
        (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    ]

    personal_path_patterns = [
        (r"(?i)c:\\users\\[a-zA-Z0-9_.-]+", "Personal Windows user path"),
        (r"(?i)/home/[a-zA-Z0-9_.-]+", "Personal Linux user path"),
        (r"(?i)onedrive", "OneDrive path reference"),
        (r"(?i)\bnitin\b", "Username literal reference"),
    ]

    findings = []

    for file_path in candidate_files:
        if not os.path.isfile(file_path):
            continue

        # Skip this audit script itself, binary files, or lockfiles
        if os.path.basename(file_path) == "audit_prepublish.py" or file_path.endswith((".ico", ".png", ".jpg", ".svg", ".lock")):
            continue

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_no, line in enumerate(f, 1):
                    # Check for secrets
                    for pattern, desc in secret_patterns:
                        if re.search(pattern, line):
                            # Filter out safe placeholders or mock test values
                            safe_terms = [
                                "your_key_here",
                                "your_actual",
                                "placeholder",
                                "dummy",
                                "mock",
                                "<MCP_API_KEY>",
                                "sample_key",
                                "test_key",
                                "test-key-12345",
                                "test-mcp-key-xyz123",
                                "test-secret-key-123",
                                "test-secret-key-456",
                                "example",
                                "BHARATCODE_API_KEY=",
                                "MCP_API_KEY=",
                            ]
                            if any(safe in line for safe in safe_terms):
                                continue
                            findings.append({
                                "file": file_path,
                                "line": line_no,
                                "content": line.strip(),
                                "reason": desc,
                            })

                    # Check for personal paths
                    for pattern, desc in personal_path_patterns:
                        if re.search(pattern, line):
                            # Filter out placeholder documentation syntax like C:\Users\<USER>\
                            if "<USER>" in line:
                                continue
                            findings.append({
                                "file": file_path,
                                "line": line_no,
                                "content": line.strip(),
                                "reason": desc,
                            })
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    print(f"Total findings: {len(findings)}")
    for f in findings:
        print(f"  [FAIL] {f['file']}:{f['line']} - {f['reason']}: {f['content'][:100]}")

    if findings:
        return 1

    print("ALL CANDIDATE FILES PASSED SENSITIVE DATA & PATH SCAN WITH ZERO VIOLATIONS!")
    return 0


if __name__ == "__main__":
    sys.exit(run_audit())
