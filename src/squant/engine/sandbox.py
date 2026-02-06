"""Strategy code sandbox validation using RestrictedPython.

This module provides secure code validation and compilation for user-defined
trading strategies. It uses RestrictedPython to restrict dangerous operations
while allowing safe Python constructs.
"""

import ast
from dataclasses import dataclass, field
from typing import Any

from RestrictedPython import compile_restricted, safe_builtins
from RestrictedPython.Eval import default_guarded_getiter
from RestrictedPython.Guards import (
    guarded_iter_unpack_sequence,
    safer_getattr,
)

# Modules that are explicitly forbidden
DISALLOWED_MODULES = frozenset(
    {
        # System access
        "os",
        "sys",
        "subprocess",
        "shutil",
        "pathlib",
        # Network access
        "socket",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        # Async network (STR-012)
        "asyncio",
        "ssl",
        # Debugger (STR-012)
        "pdb",
        "bdb",
        "cmd",
        # Serialization (can be exploited)
        "pickle",
        "marshal",
        "shelve",
        # Low-level access
        "ctypes",
        "cffi",
        # Process/thread management
        "multiprocessing",
        "threading",
        "concurrent",
        # Import system manipulation
        "importlib",
        "builtins",
        "__builtins__",
        # Code execution
        "code",
        "codeop",
        "compileall",
        # File system
        "io",
        "tempfile",
        "glob",
    }
)

# Built-in functions that are explicitly forbidden
DISALLOWED_BUILTINS = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "file",
        "__import__",
        "input",
        "globals",
        "locals",
        "getattr",
        "setattr",
        "delattr",
        "dir",
        "vars",
        "type",
        "object",
        "classmethod",
        "staticmethod",
        "property",
        "super",
        "memoryview",
        "bytearray",
        "breakpoint",
        "help",
        "license",
        "credits",
        "copyright",
    }
)

# Safe built-in functions allowed in strategy code
SAFE_BUILTINS = {
    # Math and type conversion
    "abs",
    "round",
    "pow",
    "divmod",
    "int",
    "float",
    "bool",
    "str",
    # Collections
    "len",
    "list",
    "dict",
    "set",
    "tuple",
    "frozenset",
    "range",
    "enumerate",
    "zip",
    "reversed",
    "sorted",
    # Iteration
    "map",
    "filter",
    "all",
    "any",
    "sum",
    "min",
    "max",
    # Type checking
    "isinstance",
    "issubclass",
    "callable",
    "hasattr",
    # String formatting
    "format",
    "repr",
    "ascii",
    "chr",
    "ord",
    "bin",
    "hex",
    "oct",
    # Other safe functions
    "slice",
    "iter",
    "next",
    "hash",
    "id",
    # Constants
    "True",
    "False",
    "None",
    # Printing (useful for debugging in backtest)
    "print",
}


@dataclass
class ValidationResult:
    """Result of strategy code validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


@dataclass
class CompiledStrategy:
    """Compiled strategy code ready for execution."""

    code_object: Any
    restricted_globals: dict[str, Any]


class ImportValidator(ast.NodeVisitor):
    """AST visitor to validate import statements."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result

    def visit_Import(self, node: ast.Import) -> None:
        """Check regular import statements."""
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            if module_name in DISALLOWED_MODULES:
                self.result.add_error(
                    f"Line {node.lineno}: Import of '{alias.name}' is not allowed"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from ... import statements."""
        if node.module:
            module_name = node.module.split(".")[0]
            if module_name in DISALLOWED_MODULES:
                self.result.add_error(
                    f"Line {node.lineno}: Import from '{node.module}' is not allowed"
                )
        self.generic_visit(node)


class StrategyStructureValidator(ast.NodeVisitor):
    """AST visitor to validate strategy class structure."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        self.found_strategy_class = False
        self.has_on_bar = False
        self.current_class: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Check class definitions for Strategy base class."""
        # Check if any base class is exactly named 'Strategy'
        for base in node.bases:
            base_name = ""
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr

            if base_name == "Strategy":
                self.found_strategy_class = True
                self.current_class = node.name
                # Visit children to find methods
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        if child.name == "on_bar":
                            self.has_on_bar = True

        self.generic_visit(node)

    def finalize(self) -> None:
        """Check final validation results."""
        if not self.found_strategy_class:
            self.result.add_error("Strategy code must define a class that inherits from Strategy")
        elif not self.has_on_bar:
            self.result.add_error("Strategy class must implement the 'on_bar' method")


class DangerousBuiltinsValidator(ast.NodeVisitor):
    """AST visitor to check for dangerous built-in function calls."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls for dangerous builtins.

        Only checks direct function calls (ast.Name), not method calls on objects
        (ast.Attribute) to avoid false positives like obj.open() or file.eval().
        """
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in DISALLOWED_BUILTINS:
                self.result.add_error(f"Line {node.lineno}: Call to '{func_name}' is not allowed")

        self.generic_visit(node)


# Dunder attributes that should never be accessed in strategy code
_DANGEROUS_DUNDER_ATTRS = frozenset(
    {
        "__builtins__",
        "__globals__",
        "__locals__",
        "__import__",
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__code__",
        "__func__",
    }
)


class DangerousAttributeValidator(ast.NodeVisitor):
    """AST visitor to check for dangerous dunder attribute access."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute access for dangerous dunder attributes."""
        if node.attr in _DANGEROUS_DUNDER_ATTRS:
            self.result.add_error(
                f"Line {node.lineno}: Access to '{node.attr}' is not allowed"
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Check subscript access for dangerous dunder attributes.

        Catches patterns like:
        - obj["__builtins__"] — string literal in slice
        - __builtins__["eval"] — dangerous name as the subscript target
        """
        # Check string literal in slice: obj["__builtins__"]
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            if node.slice.value in _DANGEROUS_DUNDER_ATTRS:
                self.result.add_error(
                    f"Line {node.lineno}: Access to '{node.slice.value}' "
                    f"via subscript is not allowed"
                )
        # Check dangerous name as subscript target: __builtins__["eval"]
        if isinstance(node.value, ast.Name) and node.value.id in _DANGEROUS_DUNDER_ATTRS:
            self.result.add_error(
                f"Line {node.lineno}: Access to '{node.value.id}' is not allowed"
            )
        self.generic_visit(node)


def _inplacevar_(op: str, x: Any, y: Any) -> Any:
    """Handle in-place variable operations for RestrictedPython."""
    ops = {
        "+=": lambda a, b: a + b,
        "-=": lambda a, b: a - b,
        "*=": lambda a, b: a * b,
        "/=": lambda a, b: a / b,
        "//=": lambda a, b: a // b,
        "%=": lambda a, b: a % b,
        "**=": lambda a, b: a**b,
        "&=": lambda a, b: a & b,
        "|=": lambda a, b: a | b,
        "^=": lambda a, b: a ^ b,
        ">>=": lambda a, b: a >> b,
        "<<=": lambda a, b: a << b,
    }
    return ops[op](x, y)


def _build_restricted_globals() -> dict[str, Any]:
    """Build the restricted globals dictionary for code execution."""
    # Start with safe_builtins from RestrictedPython
    restricted_builtins = dict(safe_builtins)

    # Add our explicitly allowed builtins
    import builtins

    for name in SAFE_BUILTINS:
        if hasattr(builtins, name):
            restricted_builtins[name] = getattr(builtins, name)

    # Add Decimal for precise financial calculations
    from decimal import Decimal

    restricted_builtins["Decimal"] = Decimal

    # Add math module for technical analysis (sqrt, log, exp, etc.)
    # math is a pure computation module with no IO, network, or filesystem access.
    import math

    restricted_builtins["math"] = math

    # Build globals with guards
    restricted_globals = {
        "__builtins__": restricted_builtins,
        "_getattr_": safer_getattr,
        "_getiter_": default_guarded_getiter,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        # Allow print for debugging
        "_print_": print,
        "_getitem_": lambda obj, key: obj[key],
        "_write_": lambda x: x,
        # Required for class definitions in RestrictedPython
        "__metaclass__": type,
        "__name__": "__strategy__",
        # Required for in-place operations (+=, -=, etc.)
        "_inplacevar_": _inplacevar_,
    }

    # Inject Strategy base class and related types for backtest
    from squant.engine.backtest.strategy_base import Strategy
    from squant.engine.backtest.types import Bar, OrderSide, OrderType, Position

    restricted_globals["Strategy"] = Strategy
    restricted_globals["Bar"] = Bar
    restricted_globals["Position"] = Position
    restricted_globals["OrderSide"] = OrderSide
    restricted_globals["OrderType"] = OrderType

    return restricted_globals


def validate_strategy_code(code: str) -> ValidationResult:
    """Validate strategy code for security and structure.

    Args:
        code: Python source code string.

    Returns:
        ValidationResult with validation status and any errors/warnings.
    """
    result = ValidationResult(valid=True)

    if not code or not code.strip():
        result.add_error("Strategy code cannot be empty")
        return result

    # Step 1: Parse the code to AST
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        result.add_error(f"Syntax error at line {e.lineno}: {e.msg}")
        return result

    # Step 2: Validate imports
    import_validator = ImportValidator(result)
    import_validator.visit(tree)

    # Step 3: Validate for dangerous builtins
    builtins_validator = DangerousBuiltinsValidator(result)
    builtins_validator.visit(tree)

    # Step 3b: Validate for dangerous dunder attribute access
    attr_validator = DangerousAttributeValidator(result)
    attr_validator.visit(tree)

    # Step 4: Validate strategy structure
    structure_validator = StrategyStructureValidator(result)
    structure_validator.visit(tree)
    structure_validator.finalize()

    # Step 5: Try to compile with RestrictedPython
    # RestrictedPython 8.x returns the code object directly (or raises on error)
    if result.valid:
        try:
            compile_restricted(
                code,
                filename="<strategy>",
                mode="exec",
            )
        except SyntaxError as e:
            result.add_error(f"Restricted Python syntax error: {e}")
        except Exception as e:
            result.add_error(f"Compilation error: {e}")

    return result


def compile_strategy(code: str) -> CompiledStrategy:
    """Compile strategy code for execution.

    Args:
        code: Validated Python source code string.

    Returns:
        CompiledStrategy with compiled code object and restricted globals.

    Raises:
        ValueError: If the code fails validation or compilation.
    """
    # First validate
    validation = validate_strategy_code(code)
    if not validation.valid:
        raise ValueError(f"Code validation failed: {'; '.join(validation.errors)}")

    # Compile with RestrictedPython (v8.x returns code object directly)
    try:
        code_object = compile_restricted(
            code,
            filename="<strategy>",
            mode="exec",
        )
    except SyntaxError as e:
        raise ValueError(f"Compilation failed: {e}") from e
    except Exception as e:
        raise ValueError(f"Compilation failed: {e}") from e

    # Build restricted globals
    restricted_globals = _build_restricted_globals()

    return CompiledStrategy(
        code_object=code_object,
        restricted_globals=restricted_globals,
    )
