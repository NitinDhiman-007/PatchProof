"""Code intelligence and search service using Tree-sitter for AST analysis."""

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Lazy initialization of Tree-sitter parser
_parser: Any | None = None


def get_python_parser() -> Any | None:
    """Get or initialize the Tree-sitter Python parser safely."""
    global _parser
    if _parser is not None:
        return _parser

    try:
        import tree_sitter
        import tree_sitter_python

        language = tree_sitter.Language(tree_sitter_python.language())
        _parser = tree_sitter.Parser(language)
        logger.info("Tree-sitter Python parser initialized successfully.")
        return _parser
    except Exception as e:
        logger.warning("Could not initialize Tree-sitter parser: %s", e)
        return None


def parse_python_ast(source_code: str) -> dict[str, Any]:
    """
    Parse Python source code into AST summary without executing any code.
    Extracts functions, classes, and top-level definitions.
    """
    parser = get_python_parser()
    if not parser:
        return {
            "success": False,
            "error": "Tree-sitter parser unavailable",
            "functions": [],
            "classes": [],
        }

    try:
        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)
        root = tree.root_node

        functions: list[str] = []
        classes: list[str] = []

        def traverse(node):
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    functions.append(source_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8"))
            elif node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    classes.append(source_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8"))

            for child in node.children:
                traverse(child)

        traverse(root)

        return {
            "success": True,
            "root_type": root.type,
            "functions": functions,
            "classes": classes,
            "has_syntax_errors": root.has_error,
        }
    except Exception as e:
        logger.error("Error parsing Python code: %s", e)
        return {
            "success": False,
            "error": str(e),
            "functions": [],
            "classes": [],
        }
