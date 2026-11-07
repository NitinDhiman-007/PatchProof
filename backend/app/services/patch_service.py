"""Patch parsing, validation, safety guardrails, and isolated diff application."""

import os
import re
from typing import Any

from app.core.execution_policy import validate_workspace_path
from app.core.logging import get_logger

logger = get_logger(__name__)

# Files that patches must NEVER be allowed to touch
FORBIDDEN_PATCH_PATTERNS = [
    r"^\.git\/",
    r"^\.github\/",
    r"^\.env",
    r"docker-compose",
    r"Dockerfile",
    r"\.sqlite3?$",
    r"\.db$",
    r"\.pem$",
    r"\.key$",
    r"\.id_rsa",
]


class PatchValidationError(Exception):
    """Raised when a proposed patch violates security rules or unified diff syntax."""


class PatchHunk:
    """Represents a single unified diff hunk."""

    def __init__(self, old_start: int, old_count: int, new_start: int, new_count: int):
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.lines: list[str] = []


class ParsedDiffFile:
    """Represents a diff for a single target file."""

    def __init__(self, old_path: str, new_path: str):
        self.old_path = old_path
        self.new_path = new_path
        self.hunks: list[PatchHunk] = []


class PatchService:
    """Validates and safely applies unified diff patches inside isolated workspaces."""

    @staticmethod
    def sanitize_diff_path(path_str: str) -> str:
        """Strip standard git prefixes (a/, b/) and normalize path separators."""
        clean = path_str.strip().replace("\\", "/")
        if clean.startswith("a/") or clean.startswith("b/"):
            clean = clean[2:]
        return clean.strip("/")

    @classmethod
    def validate_patch_security(cls, diff_text: str, workspace_base: str | None = None) -> list[str]:
        """
        Validate diff against security guardrails:
        - No path traversal
        - No modification of sensitive files (.env, .git, etc.)
        - Only approved extensions (.py, .txt, .md, .json, .yaml, .yml)
        Returns list of affected relative file paths if valid.
        """
        if not diff_text or not diff_text.strip():
            raise PatchValidationError("Patch diff is empty.")

        affected_files: list[str] = []
        lines = diff_text.splitlines()

        found_header = False
        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    continue
                raw_path = parts[1].strip()
                if raw_path == "/dev/null":
                    continue

                clean_path = cls.sanitize_diff_path(raw_path)
                found_header = True

                # Path traversal check
                if ".." in clean_path.split("/") or clean_path.startswith("/") or ":" in clean_path:
                    raise PatchValidationError(f"Path traversal detected in patch header: '{clean_path}'")

                # Forbidden file patterns
                for pattern in FORBIDDEN_PATCH_PATTERNS:
                    if re.search(pattern, clean_path, re.IGNORECASE):
                        raise PatchValidationError(f"Patch attempts to modify restricted file: '{clean_path}'")

                # Disallow executable / binary extensions
                _, ext = os.path.splitext(clean_path.lower())
                allowed_exts = {".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".rst"}
                if ext and ext not in allowed_exts:
                    raise PatchValidationError(
                        f"Patch attempts to modify unsupported or binary file type: '{clean_path}'"
                    )

                if clean_path not in affected_files:
                    affected_files.append(clean_path)

        if not found_header or not affected_files:
            raise PatchValidationError("No valid unified diff file headers (--- / +++) found in patch.")

        # If workspace provided, check path containment
        if workspace_base:
            for rel in affected_files:
                target_full = os.path.join(workspace_base, rel)
                validate_workspace_path(target_full, base_dir=workspace_base)

        return affected_files

    @classmethod
    def parse_unified_diff(cls, diff_text: str) -> list[ParsedDiffFile]:
        """Parse raw unified diff text into structured file hunks."""
        files: list[ParsedDiffFile] = []
        lines = diff_text.splitlines()

        current_file: ParsedDiffFile | None = None
        current_hunk: PatchHunk | None = None

        hunk_header_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

        i = 0
        while i < len(lines):
            line = lines[i]

            if line.startswith("--- "):
                old_raw = line[4:].strip()
                # Next line should be +++
                if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                    new_raw = lines[i + 1][4:].strip()
                    i += 1
                    old_path = cls.sanitize_diff_path(old_raw)
                    new_path = cls.sanitize_diff_path(new_raw)
                    current_file = ParsedDiffFile(old_path, new_path)
                    files.append(current_file)
                    current_hunk = None
                    i += 1
                    continue

            hunk_match = hunk_header_re.match(line)
            if hunk_match and current_file is not None:
                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4)) if hunk_match.group(4) is not None else 1

                current_hunk = PatchHunk(old_start, old_count, new_start, new_count)
                current_file.hunks.append(current_hunk)
                i += 1
                continue

            if current_hunk is not None:
                if line.startswith(" ") or line.startswith("+") or line.startswith("-") or line == "":
                    # Diff line
                    current_hunk.lines.append(line)
                elif line.startswith("\\ No newline at end of file"):
                    pass
                else:
                    # Non-diff line outside hunk
                    pass

            i += 1

        if not files:
            raise PatchValidationError("Failed to parse any diff file structures from provided patch.")

        return files

    @classmethod
    def apply_patch_to_workspace(
        cls,
        workspace_path: str,
        diff_text: str,
    ) -> dict[str, Any]:
        """
        Apply parsed unified diff directly into the target isolated workspace.
        Never touches host or original repository.
        """
        # 1. Validate security & boundaries
        cls.validate_patch_security(diff_text, workspace_base=workspace_path)
        parsed_files = cls.parse_unified_diff(diff_text)

        applied_files: list[str] = []

        for diff_file in parsed_files:
            rel_path = diff_file.new_path if diff_file.new_path != "/dev/null" else diff_file.old_path
            target_path = os.path.join(workspace_path, rel_path)

            if not os.path.exists(target_path):
                # Check if it's file creation
                if diff_file.old_path == "/dev/null":
                    original_lines: list[str] = []
                else:
                    raise PatchValidationError(f"Target file does not exist in workspace: '{rel_path}'")
            else:
                with open(target_path, encoding="utf-8", errors="replace") as f:
                    original_lines = f.read().splitlines()

            # Apply hunks sequentially
            new_lines = cls._apply_hunks_to_lines(original_lines, diff_file.hunks, rel_path)

            # Write updated content
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")

            applied_files.append(rel_path)

        logger.info("Successfully applied patch to %d file(s) in %s", len(applied_files), workspace_path)
        return {
            "success": True,
            "applied_files": applied_files,
            "total_hunks": sum(len(f.hunks) for f in parsed_files),
        }

    @staticmethod
    def _apply_hunks_to_lines(
        original_lines: list[str],
        hunks: list[PatchHunk],
        file_label: str,
    ) -> list[str]:
        """Apply hunks with line-offset tracking and context verification."""
        result = list(original_lines)
        line_offset = 0

        for hunk in hunks:
            # 1-indexed to 0-indexed
            target_idx = (hunk.old_start - 1) + line_offset

            # Clamp target_idx within reasonable bounds
            target_idx = max(0, min(len(result), target_idx))

            # Build expected old slice and replacement new slice
            expected_old: list[str] = []
            replacement: list[str] = []

            for h_line in hunk.lines:
                if not h_line:
                    prefix = " "
                    content = ""
                else:
                    prefix = h_line[0]
                    content = h_line[1:]

                if prefix == " ":
                    expected_old.append(content)
                    replacement.append(content)
                elif prefix == "-":
                    expected_old.append(content)
                elif prefix == "+":
                    replacement.append(content)

            # Find matching position in result (check exact index or search in ±5 lines)
            best_idx = -1

            # Try exact match first
            for search_offset in [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5]:
                candidate_idx = target_idx + search_offset
                if candidate_idx < 0 or candidate_idx + len(expected_old) > len(result):
                    continue

                slice_matches = True
                for j, exp_line in enumerate(expected_old):
                    if result[candidate_idx + j].rstrip() != exp_line.rstrip():
                        slice_matches = False
                        break

                if slice_matches:
                    best_idx = candidate_idx
                    break

            if best_idx == -1 and expected_old:
                # If fuzzy match failed, check if empty replacement or fallback
                logger.warning(
                    "Context mismatch applying hunk to %s at expected line %d. Attempting fuzzy insert.",
                    file_label,
                    hunk.old_start,
                )
                best_idx = target_idx

            # Apply replacement
            old_len = len(expected_old)
            result[best_idx : best_idx + old_len] = replacement
            line_offset += len(replacement) - old_len

        return result
