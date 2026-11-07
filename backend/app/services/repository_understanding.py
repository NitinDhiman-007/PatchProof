"""Repository understanding service: AST symbol extraction, file tree indexing, and code search."""

import ast
import os
import re
from typing import Any

from app.core.logging import get_logger
from app.services.code_search_service import get_python_parser

logger = get_logger(__name__)

# Standard ignore patterns during repository indexing
EXCLUDED_DIRECTORIES = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".next",
    "dist",
    "build",
    "eggs",
    ".eggs",
    "site-packages",
}

EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".zip",
    ".tar",
    ".gz",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".db",
    ".sqlite",
    ".sqlite3",
}

MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB limit for source inspection


class SymbolExtractor:
    """Extracts symbols, function signatures, classes, and imports from Python code."""

    @staticmethod
    def extract_symbols(source_code: str, file_path: str = "") -> dict[str, Any]:
        """
        Extract AST definitions safely without code execution.
        Uses Python's ast module with Tree-sitter fallback.
        """
        result: dict[str, Any] = {
            "file_path": file_path,
            "classes": [],
            "functions": [],
            "imports": [],
            "docstring": "",
            "line_count": len(source_code.splitlines()),
        }

        # Try standard library ast first for rich structured node representation
        try:
            tree = ast.parse(source_code)
            result["docstring"] = ast.get_docstring(tree) or ""

            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = {
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "docstring": ast.get_docstring(node) or "",
                        "methods": [
                            m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ],
                    }
                    result["classes"].append(class_info)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_info = {
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "args": [a.arg for a in node.args.args],
                        "docstring": ast.get_docstring(node) or "",
                    }
                    result["functions"].append(func_info)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        result["imports"].append(f"{module}.{alias.name}")

            return result

        except SyntaxError:
            # If standard AST fails (e.g. syntax variation), fall back to Tree-sitter
            parser = get_python_parser()
            if parser:
                try:
                    source_bytes = source_code.encode("utf-8")
                    tree = parser.parse(source_bytes)
                    root = tree.root_node

                    def traverse(n):
                        if n.type == "function_definition":
                            name_n = n.child_by_field_name("name")
                            if name_n:
                                name = source_bytes[name_n.start_byte : name_n.end_byte].decode("utf-8")
                                result["functions"].append({"name": name, "line": n.start_point[0] + 1})
                        elif n.type == "class_definition":
                            name_n = n.child_by_field_name("name")
                            if name_n:
                                name = source_bytes[name_n.start_byte : name_n.end_byte].decode("utf-8")
                                result["classes"].append({"name": name, "line": n.start_point[0] + 1})
                        for ch in n.children:
                            traverse(ch)

                    traverse(root)
                except Exception as exc:
                    logger.warning("Tree-sitter parse fallback error for %s: %s", file_path, exc)

            return result
        except Exception as exc:
            logger.warning("Symbol extraction error for %s: %s", file_path, exc)
            return result


class RepositoryIndex:
    """Indexes files and extracted symbols across a repository workspace."""

    def __init__(self, workspace_path: str):
        self.workspace_path = os.path.abspath(workspace_path)
        self.files: list[str] = []
        self.symbols_by_file: dict[str, dict[str, Any]] = {}
        self.all_symbols: set[str] = set()

    def build_index(self) -> None:
        """Walk workspace and index Python and text source files safely."""
        self.files.clear()
        self.symbols_by_file.clear()
        self.all_symbols.clear()

        if not os.path.isdir(self.workspace_path):
            logger.warning("Workspace path %s is not a directory", self.workspace_path)
            return

        for root, dirs, filenames in os.walk(self.workspace_path):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRECTORIES and not d.startswith(".")]

            for filename in filenames:
                _, ext = os.path.splitext(filename.lower())
                if ext in EXCLUDED_EXTENSIONS:
                    continue

                full_path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(full_path)
                    if size > MAX_FILE_SIZE_BYTES:
                        continue
                except OSError:
                    continue

                rel_path = os.path.relpath(full_path, self.workspace_path).replace("\\", "/")
                self.files.append(rel_path)

                # For Python files, extract AST symbols
                if ext == ".py":
                    try:
                        with open(full_path, encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        extracted = SymbolExtractor.extract_symbols(content, rel_path)
                        self.symbols_by_file[rel_path] = extracted

                        for fn in extracted.get("functions", []):
                            self.all_symbols.add(fn["name"])
                        for cls in extracted.get("classes", []):
                            self.all_symbols.add(cls["name"])
                    except Exception as e:
                        logger.warning("Could not index %s: %s", rel_path, e)

        logger.info(
            "Indexed repository %s: %d files, %d Python files with symbols",
            self.workspace_path,
            len(self.files),
            len(self.symbols_by_file),
        )


class CodeRetriever:
    """Retrieves relevant code snippets grounded on bug descriptions and stack traces."""

    def __init__(self, index: RepositoryIndex):
        self.index = index

    def retrieve_relevant_snippets(
        self,
        bug_description: str,
        stack_trace: str | None = None,
        max_snippets: int = 5,
        context_radius: int = 25,
    ) -> list[dict[str, Any]]:
        """
        Rank repository files and extract line-numbered snippets relevant to the reported defect.
        """
        candidates: dict[str, float] = {}
        target_lines_by_file: dict[str, list[int]] = {}
        tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", bug_description))

        # 1. Parse stack trace for exact file and line mentions
        trace_text = (stack_trace or "") + "\n" + bug_description
        # Match Python tracebacks like: File "path/to/file.py", line 42, in func_name
        traceback_pattern = re.compile(
            r'File\s+["\']?([^"\'>\n]+)["\']?,\s+line\s+(\d+)(?:,\s+in\s+([A-Za-z0-9_]+))?',
            re.IGNORECASE,
        )
        for match in traceback_pattern.finditer(trace_text):
            raw_path = match.group(1).replace("\\", "/")
            line_no = int(match.group(2))
            func_name = match.group(3)
            if func_name:
                tokens.add(func_name)

            # Match against indexed files
            matched_rel_path = None
            for indexed in self.index.files:
                if indexed == raw_path or raw_path.endswith(indexed) or indexed.endswith(raw_path):
                    matched_rel_path = indexed
                    break

            if matched_rel_path:
                candidates[matched_rel_path] = candidates.get(matched_rel_path, 0.0) + 100.0
                target_lines_by_file.setdefault(matched_rel_path, []).append(line_no)

        # 2. Check symbol matches
        for rel_path, symbols in self.index.symbols_by_file.items():
            score = candidates.get(rel_path, 0.0)
            target_lines = target_lines_by_file.setdefault(rel_path, [])

            for fn in symbols.get("functions", []):
                if fn["name"] in tokens:
                    score += 25.0
                    target_lines.append(fn.get("line", 1))

            for cls in symbols.get("classes", []):
                if cls["name"] in tokens:
                    score += 20.0
                    target_lines.append(cls.get("line", 1))
                for method in cls.get("methods", []):
                    if method in tokens:
                        score += 15.0
                        target_lines.append(cls.get("line", 1))

            # Match in file path name
            path_tokens = set(re.findall(r"[A-Za-z0-9_]+", rel_path.lower()))
            for t in tokens:
                if t.lower() in path_tokens:
                    score += 10.0

            if score > 0:
                candidates[rel_path] = score

        # 3. If no high-confidence candidates found, scan file contents for token overlap
        if len(candidates) < max_snippets:
            for rel_path in self.index.files:
                if not rel_path.endswith(".py"):
                    continue
                if rel_path in candidates:
                    continue

                full_path = os.path.join(self.index.workspace_path, rel_path)
                try:
                    with open(full_path, encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    content_tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", content))
                    common = tokens.intersection(content_tokens)
                    if common:
                        # Find line of first match
                        for idx, line in enumerate(content.splitlines(), start=1):
                            if any(token in line for token in common):
                                candidates[rel_path] = len(common) * 2.0
                                target_lines_by_file.setdefault(rel_path, []).append(idx)
                                break
                except Exception as exc:
                    logger.debug("Skipping unreadable file %s: %s", rel_path, exc)
                    continue

        # Sort candidates by score descending
        sorted_files = sorted(candidates.keys(), key=lambda p: candidates[p], reverse=True)[:max_snippets]

        # Extract line-number-aware snippets
        snippets: list[dict[str, Any]] = []
        for rel_path in sorted_files:
            full_path = os.path.join(self.index.workspace_path, rel_path)
            try:
                with open(full_path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception as exc:
                logger.debug("Skipping unreadable lines in %s: %s", rel_path, exc)
                continue

            total_lines = len(lines)
            if total_lines == 0:
                continue

            target_lines = target_lines_by_file.get(rel_path, [1])
            primary_line = target_lines[0] if target_lines else 1

            start_line = max(1, primary_line - context_radius)
            end_line = min(total_lines, primary_line + context_radius)

            # Format line-numbered snippet
            snippet_lines = []
            for i in range(start_line - 1, end_line):
                line_no = i + 1
                prefix = "-> " if line_no in target_lines else "   "
                snippet_lines.append(f"{prefix}{line_no:4d} | {lines[i].rstrip()}")

            code_text = "\n".join(snippet_lines)
            symbols = [
                fn["name"]
                for fn in self.index.symbols_by_file.get(rel_path, {}).get("functions", [])
            ]

            snippets.append({
                "file_path": rel_path,
                "start_line": start_line,
                "end_line": end_line,
                "target_line": primary_line,
                "symbols": symbols,
                "code": code_text,
                "raw_code": "".join(lines[start_line - 1 : end_line]),
            })

        return snippets
