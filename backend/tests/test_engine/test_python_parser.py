"""
Tests for the Python AST parser module.
"""

import pytest
from pathlib import Path
import textwrap

from app.engine.parser.python_parser import (
    PythonASTParser,
    file_path_to_module_name,
)


@pytest.fixture
def parser():
    return PythonASTParser()


@pytest.fixture
def sample_file(tmp_path):
    """Create a sample Python file for parsing."""
    code = textwrap.dedent('''\
        """Module docstring."""

        import os
        import sys
        from pathlib import Path
        from collections import OrderedDict
        from typing import List, Optional

        CONSTANT = 42


        def standalone_function(x: int, y: int) -> int:
            """Add two numbers."""
            result = x + y
            print(result)
            return result


        def another_function():
            """Calls standalone_function."""
            val = standalone_function(1, 2)
            os.path.join("a", "b")
            return val


        class MyBaseClass:
            """A base class."""

            def base_method(self):
                pass


        class MyClass(MyBaseClass):
            """A sample class."""

            def __init__(self, value):
                self.value = value

            def compute(self, factor: float) -> float:
                """Compute something."""
                return self.value * factor

            async def async_method(self):
                """An async method."""
                pass

            @staticmethod
            def static_helper():
                """A static method."""
                standalone_function(1, 1)
    ''')
    file_path = tmp_path / "sample_module.py"
    file_path.write_text(code)
    return file_path


class TestPythonASTParser:
    def test_parse_imports(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        # Check regular imports
        regular_imports = [i for i in result.imports if not i.is_from_import]
        assert any(i.module == "os" for i in regular_imports)
        assert any(i.module == "sys" for i in regular_imports)

        # Check from imports
        from_imports = [i for i in result.imports if i.is_from_import]
        assert any(i.module == "pathlib" and i.name == "Path" for i in from_imports)
        assert any(
            i.module == "collections" and i.name == "OrderedDict"
            for i in from_imports
        )

    def test_parse_functions(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        func_names = {f.name for f in result.functions}
        assert "standalone_function" in func_names
        assert "another_function" in func_names

    def test_function_qualified_name(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for func in result.functions:
            if func.name == "standalone_function":
                assert func.qualified_name == "sample_module.standalone_function"

    def test_function_docstring(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for func in result.functions:
            if func.name == "standalone_function":
                assert func.docstring == "Add two numbers."

    def test_function_args(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for func in result.functions:
            if func.name == "standalone_function":
                assert "x" in func.args
                assert "y" in func.args

    def test_function_calls_detected(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for func in result.functions:
            if func.name == "another_function":
                assert "standalone_function" in func.calls
                assert "os.path.join" in func.calls

    def test_parse_classes(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        class_names = {c.name for c in result.classes}
        assert "MyClass" in class_names
        assert "MyBaseClass" in class_names

    def test_class_bases(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for cls in result.classes:
            if cls.name == "MyClass":
                assert "MyBaseClass" in cls.bases

    def test_class_methods(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for cls in result.classes:
            if cls.name == "MyClass":
                method_names = {m.name for m in cls.methods}
                assert "__init__" in method_names
                assert "compute" in method_names
                assert "async_method" in method_names
                assert "static_helper" in method_names

    def test_method_is_method_flag(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for cls in result.classes:
            for method in cls.methods:
                assert method.is_method is True

    def test_async_method_detected(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for cls in result.classes:
            if cls.name == "MyClass":
                for method in cls.methods:
                    if method.name == "async_method":
                        assert method.is_async is True

    def test_static_decorator_detected(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for cls in result.classes:
            if cls.name == "MyClass":
                for method in cls.methods:
                    if method.name == "static_helper":
                        assert "staticmethod" in method.decorators

    def test_line_numbers(self, parser, sample_file):
        result = parser.parse_file(sample_file, "sample_module")

        for func in result.functions:
            assert func.line_start > 0
            assert func.line_end >= func.line_start

        for cls in result.classes:
            assert cls.line_start > 0
            assert cls.line_end >= cls.line_start

    def test_syntax_error_handled(self, parser, tmp_path):
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(\n")

        result = parser.parse_file(bad_file, "bad")
        assert len(result.parse_errors) > 0
        assert len(result.functions) == 0
        assert len(result.classes) == 0

    def test_empty_file(self, parser, tmp_path):
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        result = parser.parse_file(empty_file, "empty")
        assert len(result.functions) == 0
        assert len(result.classes) == 0
        assert len(result.imports) == 0
        assert len(result.parse_errors) == 0

    def test_nonexistent_file(self, parser):
        result = parser.parse_file(Path("/nonexistent/file.py"), "missing")
        assert len(result.parse_errors) > 0


class TestFilePathToModuleName:
    def test_simple_file(self):
        assert file_path_to_module_name("main.py", "/repo") == "main"

    def test_nested_file(self):
        assert (
            file_path_to_module_name("utils/helpers.py", "/repo")
            == "utils.helpers"
        )

    def test_init_file(self):
        assert file_path_to_module_name("__init__.py", "/repo") == ""

    def test_package_init(self):
        assert (
            file_path_to_module_name("package/__init__.py", "/repo")
            == "package"
        )

    def test_deeply_nested(self):
        assert (
            file_path_to_module_name("a/b/c/module.py", "/repo")
            == "a.b.c.module"
        )
