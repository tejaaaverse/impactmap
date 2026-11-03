"""
Python AST Parser Module.

Uses Python's ast module to extract structured information from source files:
- Functions and their signatures
- Classes and their methods
- Import statements (both `import` and `from ... import`)
- Decorators
- Docstrings
- Function calls (for dependency edges)

This is a static analysis tool — it cannot resolve dynamic imports,
runtime-generated names, or other dynamic Python constructs.
"""

import ast
from pathlib import Path
from dataclasses import dataclass, field

from app.core.logging import logger


@dataclass
class ImportInfo:
    """Represents a single import statement."""

    module: str  # The module being imported (e.g., "os.path")
    name: str | None = None  # The specific name imported (e.g., "join")
    alias: str | None = None  # Import alias (e.g., "import numpy as np" -> alias="np")
    is_from_import: bool = False  # True for "from X import Y"
    level: int = 0  # Relative import level (0 = absolute)
    line_number: int = 0


@dataclass
class FunctionInfo:
    """Represents a discovered function or method."""

    name: str
    qualified_name: str  # Full dotted path within the module
    line_start: int
    line_end: int
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None
    args: list[str] = field(default_factory=list)
    is_method: bool = False
    is_async: bool = False
    calls: list[str] = field(default_factory=list)  # Names of functions called within


@dataclass
class ClassInfo:
    """Represents a discovered class."""

    name: str
    qualified_name: str
    line_start: int
    line_end: int
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None
    bases: list[str] = field(default_factory=list)  # Base class names
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass
class ModuleParseResult:
    """Result of parsing a single Python module."""

    file_path: str
    module_name: str  # Dotted module name derived from file path
    imports: list[ImportInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    line_count: int = 0


class PythonASTParser:
    """
    Parses Python source files using the ast module to extract
    structured code information.

    Limitations:
    - Cannot resolve dynamic imports (importlib, __import__)
    - Cannot trace function calls through variables or higher-order functions
    - Does not evaluate decorators or metaclasses
    - Star imports (from X import *) are noted but not expanded
    """

    def parse_file(self, file_path: Path, module_name: str = "") -> ModuleParseResult:
        """
        Parse a Python file and extract its structure.

        Args:
            file_path: Absolute path to the Python file.
            module_name: Dotted module name (e.g., "package.module").

        Returns:
            ModuleParseResult with extracted information.
        """
        result = ModuleParseResult(
            file_path=str(file_path),
            module_name=module_name,
        )

        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            result.line_count = source.count("\n") + 1
        except (OSError, IOError) as e:
            result.parse_errors.append(f"Cannot read file: {e}")
            logger.warning(f"Cannot read {file_path}: {e}")
            return result

        return self.parse_source(source, str(file_path), module_name, result)

    def parse_source(
        self,
        source: str,
        file_path: str,
        module_name: str = "",
        result: ModuleParseResult | None = None,
    ) -> ModuleParseResult:
        """Parse Python source text.

        This is used both for files on disk and for historical Git revisions,
        where no working-tree file exists.
        """
        result = result or ModuleParseResult(file_path=file_path, module_name=module_name)
        result.line_count = source.count("\n") + 1

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            result.parse_errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            logger.warning(f"Syntax error in {file_path}: {e}")
            return result

        # Extract definitions recursively so nested functions/classes are
        # represented instead of being silently dropped.
        result.imports = self._extract_imports(tree)
        result.functions = []
        result.classes = []
        self._extract_definitions(
            tree.body, prefix=module_name, functions=result.functions, classes=result.classes
        )

        return result

    def _extract_imports(self, tree: ast.Module) -> list[ImportInfo]:
        """Extract all import statements from an AST."""
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportInfo(
                            module=alias.name,
                            alias=alias.asname,
                            is_from_import=False,
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(
                        ImportInfo(
                            module=module,
                            name=alias.name,
                            alias=alias.asname,
                            is_from_import=True,
                            level=node.level,
                            line_number=node.lineno,
                        )
                    )

        return imports

    def _extract_functions(
        self, tree: ast.Module, prefix: str = ""
    ) -> list[FunctionInfo]:
        """Extract top-level function definitions from an AST."""
        functions = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = self._parse_function(node, prefix)
                functions.append(func)

        return functions

    def _extract_classes(
        self, tree: ast.Module, prefix: str = ""
    ) -> list[ClassInfo]:
        """Extract class definitions from an AST."""
        classes = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                cls = self._parse_class(node, prefix)
                classes.append(cls)

        return classes

    def _extract_definitions(
        self,
        body: list[ast.stmt],
        prefix: str,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
    ) -> None:
        """Recursively collect definitions from a statement list.

        Nested functions, nested classes, methods defined inside functions,
        and definitions inside compound statements (``if``/``try``/``with``/
        loops/``match``) are all represented. Definitions are appended to the
        caller-owned ``functions``/``classes`` lists so the public
        ``ModuleParseResult`` shape is unchanged.
        """
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = self._parse_function(node, prefix)
                functions.append(func)
                self._extract_definitions(
                    node.body, func.qualified_name, functions, classes
                )
            elif isinstance(node, ast.ClassDef):
                cls = self._parse_class(node, prefix)
                classes.append(cls)
                self._extract_class_body_definitions(
                    node, cls.qualified_name, functions, classes
                )
            else:
                self._recurse_compound_statement(
                    node, prefix, functions, classes
                )

    def _extract_class_body_definitions(
        self,
        node: ast.ClassDef,
        class_prefix: str,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
    ) -> None:
        """Collect nested classes and function-local definitions in a class.

        Direct methods are already parsed by :meth:`_parse_class`; this only
        descends further so nested symbols are not silently dropped.
        """
        for child in node.body:
            if isinstance(child, ast.ClassDef):
                nested = self._parse_class(child, class_prefix)
                classes.append(nested)
                self._extract_class_body_definitions(
                    child, nested.qualified_name, functions, classes
                )
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_definitions(
                    child.body,
                    f"{class_prefix}.{child.name}",
                    functions,
                    classes,
                )
            else:
                self._recurse_compound_statement(
                    child, class_prefix, functions, classes
                )

    def _recurse_compound_statement(
        self,
        node: ast.stmt,
        prefix: str,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
    ) -> None:
        """Descend into branch/loop/try bodies that may define symbols."""
        if not isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.With,
                ast.AsyncWith,
                ast.Try,
            ),
        ) and not type(node).__name__ == "TryStar":
            return

        for attr in ("body", "orelse", "finalbody"):
            block = getattr(node, attr, None)
            if isinstance(block, list):
                self._extract_definitions(block, prefix, functions, classes)

        for handler in getattr(node, "handlers", []) or []:
            self._extract_definitions(handler.body, prefix, functions, classes)

        cases = getattr(node, "cases", None) or []
        for case in cases:
            self._extract_definitions(case.body, prefix, functions, classes)

    def _parse_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str = ""
    ) -> FunctionInfo:
        """Parse a function definition node into FunctionInfo."""
        qualified = f"{prefix}.{node.name}" if prefix else node.name

        func = FunctionInfo(
            name=node.name,
            qualified_name=qualified,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            decorators=self._extract_decorator_names(node.decorator_list),
            docstring=ast.get_docstring(node),
            args=self._extract_arg_names(node.args),
            is_method=False,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            calls=self._extract_calls(node),
        )

        return func

    def _parse_class(self, node: ast.ClassDef, prefix: str = "") -> ClassInfo:
        """Parse a class definition node into ClassInfo."""
        qualified = f"{prefix}.{node.name}" if prefix else node.name

        cls = ClassInfo(
            name=node.name,
            qualified_name=qualified,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            decorators=self._extract_decorator_names(node.decorator_list),
            docstring=ast.get_docstring(node),
            bases=self._extract_base_names(node.bases),
            methods=[],
        )

        # Extract methods
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = self._parse_function(child, prefix=qualified)
                method.is_method = True
                cls.methods.append(method)

        return cls

    def _extract_decorator_names(self, decorators: list[ast.expr]) -> list[str]:
        """Extract decorator names as strings."""
        names = []
        for dec in decorators:
            if isinstance(dec, ast.Name):
                names.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                names.append(self._attribute_to_str(dec))
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    names.append(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    names.append(self._attribute_to_str(dec.func))
        return names

    def _extract_arg_names(self, args: ast.arguments) -> list[str]:
        """Extract argument names from a function signature."""
        names = []
        for arg in args.args:
            names.append(arg.arg)
        for arg in args.posonlyargs:
            names.append(arg.arg)
        for arg in args.kwonlyargs:
            names.append(arg.arg)
        if args.vararg:
            names.append(f"*{args.vararg.arg}")
        if args.kwarg:
            names.append(f"**{args.kwarg.arg}")
        return names

    def _extract_base_names(self, bases: list[ast.expr]) -> list[str]:
        """Extract base class names."""
        names = []
        for base in bases:
            if isinstance(base, ast.Name):
                names.append(base.id)
            elif isinstance(base, ast.Attribute):
                names.append(self._attribute_to_str(base))
        return names

    def _extract_calls(self, node: ast.AST) -> list[str]:
        """
        Extract function/method call names within a function body.

        Note: This is a best-effort static extraction. It captures direct
        name-based calls but cannot resolve calls through variables,
        higher-order functions, or dynamic dispatch.
        """
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._resolve_call_name(child.func)
                if call_name:
                    calls.append(call_name)
        return list(set(calls))  # Deduplicate

    def _resolve_call_name(self, node: ast.expr) -> str | None:
        """Resolve a call expression to a string name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._attribute_to_str(node)
        return None

    def _attribute_to_str(self, node: ast.Attribute) -> str:
        """Convert an Attribute node to a dotted string (e.g., 'os.path.join')."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))


def file_path_to_module_name(file_path: str, repo_root: str) -> str:
    """
    Convert a file path relative to repo root into a dotted module name.

    Examples:
        "utils/helpers.py" -> "utils.helpers"
        "main.py" -> "main"
        "__init__.py" -> ""
        "package/__init__.py" -> "package"
    """
    rel = Path(file_path)
    parts = list(rel.parts)

    # Remove .py extension from last part
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]

    # Handle __init__ files
    if parts and parts[-1] == "__init__":
        parts.pop()

    return ".".join(parts)
