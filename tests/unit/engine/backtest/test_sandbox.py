"""Unit tests for strategy sandbox validation."""

from __future__ import annotations

import pytest

from squant.engine.sandbox import (
    DISALLOWED_BUILTINS,
    DISALLOWED_MODULES,
    SAFE_BUILTINS,
    CompiledStrategy,
    DangerousBuiltinsValidator,
    ImportValidator,
    StrategyStructureValidator,
    ValidationResult,
    _build_restricted_globals,
    _inplacevar_,
    compile_strategy,
    validate_strategy_code,
)


@pytest.fixture
def valid_strategy():
    """Valid strategy code."""
    return '''
class MyStrategy(Strategy):
    """A valid trading strategy."""

    def on_init(self):
        self.counter = 0

    def on_bar(self, bar):
        self.counter = self.counter + 1
        if bar.close > bar.open:
            self.ctx.buy(bar.symbol, Decimal("0.1"))

    def on_stop(self):
        pass
'''


@pytest.fixture
def minimal_strategy():
    """Minimal valid strategy."""
    return """
class MinimalStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_initial_state_valid(self):
        """Test result starts as valid."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_error_invalidates(self):
        """Test add_error sets valid to False."""
        result = ValidationResult(valid=True)
        result.add_error("Test error")

        assert result.valid is False
        assert "Test error" in result.errors

    def test_add_warning_keeps_valid(self):
        """Test add_warning doesn't change validity."""
        result = ValidationResult(valid=True)
        result.add_warning("Test warning")

        assert result.valid is True
        assert "Test warning" in result.warnings

    def test_multiple_errors(self):
        """Test multiple errors collected."""
        result = ValidationResult(valid=True)
        result.add_error("Error 1")
        result.add_error("Error 2")

        assert len(result.errors) == 2
        assert result.valid is False


class TestImportValidator:
    """Tests for ImportValidator."""

    def test_allowed_import_passes(self):
        """Test allowed imports don't cause errors."""
        result = ValidationResult(valid=True)
        validator = ImportValidator(result)

        # Parse code with allowed import
        import ast

        tree = ast.parse("from decimal import Decimal")
        validator.visit(tree)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_disallowed_import_fails(self):
        """Test disallowed imports cause errors."""
        result = ValidationResult(valid=True)
        validator = ImportValidator(result)

        import ast

        tree = ast.parse("import os")
        validator.visit(tree)

        assert result.valid is False
        assert any("os" in err for err in result.errors)

    def test_disallowed_from_import_fails(self):
        """Test disallowed from imports cause errors."""
        result = ValidationResult(valid=True)
        validator = ImportValidator(result)

        import ast

        tree = ast.parse("from subprocess import run")
        validator.visit(tree)

        assert result.valid is False
        assert any("subprocess" in err for err in result.errors)

    def test_multiple_disallowed_imports(self):
        """Test multiple disallowed imports all caught."""
        result = ValidationResult(valid=True)
        validator = ImportValidator(result)

        import ast

        tree = ast.parse("import os\nimport sys\nimport socket")
        validator.visit(tree)

        assert result.valid is False
        assert len(result.errors) == 3


class TestStrategyStructureValidator:
    """Tests for StrategyStructureValidator."""

    def test_valid_strategy_passes(self, valid_strategy):
        """Test valid strategy passes validation."""
        result = ValidationResult(valid=True)
        validator = StrategyStructureValidator(result)

        import ast

        tree = ast.parse(valid_strategy)
        validator.visit(tree)
        validator.finalize()

        assert result.valid is True

    def test_missing_strategy_class_fails(self):
        """Test code without Strategy class fails."""
        result = ValidationResult(valid=True)
        validator = StrategyStructureValidator(result)

        import ast

        tree = ast.parse("class SomeClass:\n    pass")
        validator.visit(tree)
        validator.finalize()

        assert result.valid is False
        assert any("Strategy" in err for err in result.errors)

    def test_missing_on_bar_fails(self):
        """Test strategy without on_bar fails."""
        result = ValidationResult(valid=True)
        validator = StrategyStructureValidator(result)

        import ast

        code = """
class MyStrategy(Strategy):
    def some_method(self):
        pass
"""
        tree = ast.parse(code)
        validator.visit(tree)
        validator.finalize()

        assert result.valid is False
        assert any("on_bar" in err for err in result.errors)


class TestDangerousBuiltinsValidator:
    """Tests for DangerousBuiltinsValidator."""

    def test_safe_builtins_allowed(self):
        """Test safe builtin calls are allowed."""
        result = ValidationResult(valid=True)
        validator = DangerousBuiltinsValidator(result)

        import ast

        tree = ast.parse("x = len([1, 2, 3])\ny = abs(-5)")
        validator.visit(tree)

        assert result.valid is True

    def test_dangerous_builtins_rejected(self):
        """Test dangerous builtin calls are rejected."""
        result = ValidationResult(valid=True)
        validator = DangerousBuiltinsValidator(result)

        import ast

        tree = ast.parse("eval('print(1)')")
        validator.visit(tree)

        assert result.valid is False
        assert any("eval" in err for err in result.errors)

    def test_exec_rejected(self):
        """Test exec is rejected."""
        result = ValidationResult(valid=True)
        validator = DangerousBuiltinsValidator(result)

        import ast

        tree = ast.parse("exec('x = 1')")
        validator.visit(tree)

        assert result.valid is False
        assert any("exec" in err for err in result.errors)

    def test_open_rejected(self):
        """Test open is rejected."""
        result = ValidationResult(valid=True)
        validator = DangerousBuiltinsValidator(result)

        import ast

        tree = ast.parse("f = open('file.txt')")
        validator.visit(tree)

        assert result.valid is False
        assert any("open" in err for err in result.errors)

    def test_method_call_not_rejected(self):
        """Test method calls with same name as builtins are not rejected."""
        result = ValidationResult(valid=True)
        validator = DangerousBuiltinsValidator(result)

        import ast

        # obj.open() should be allowed (method call, not builtin)
        tree = ast.parse("file.open()")
        validator.visit(tree)

        assert result.valid is True


class TestValidateStrategyCode:
    """Tests for validate_strategy_code function."""

    def test_valid_code_passes(self, valid_strategy):
        """Test valid strategy code passes."""
        result = validate_strategy_code(valid_strategy)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_empty_code_fails(self):
        """Test empty code fails."""
        result = validate_strategy_code("")
        assert result.valid is False
        assert any("empty" in err.lower() for err in result.errors)

    def test_whitespace_only_fails(self):
        """Test whitespace-only code fails."""
        result = validate_strategy_code("   \n\t  \n  ")
        assert result.valid is False

    def test_syntax_error_fails(self):
        """Test syntax error fails."""
        code = "class MyStrategy(Strategy)\n    def on_bar(self, bar): pass"
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("syntax" in err.lower() for err in result.errors)

    def test_dangerous_import_fails(self):
        """Test dangerous imports fail."""
        code = """
import os
class MyStrategy(Strategy):
    def on_bar(self, bar):
        os.system("ls")
"""
        result = validate_strategy_code(code)
        assert result.valid is False

    def test_minimal_strategy_passes(self, minimal_strategy):
        """Test minimal strategy passes."""
        result = validate_strategy_code(minimal_strategy)
        assert result.valid is True

    def test_strategy_info_populated_on_valid(self, valid_strategy):
        """Test strategy_info is populated when code is valid (ST-003)."""
        result = validate_strategy_code(valid_strategy)
        assert result.valid is True
        assert result.strategy_info is not None
        assert result.strategy_info["class_name"] == "MyStrategy"
        assert result.strategy_info["has_on_bar"] is True

    def test_strategy_info_none_on_invalid(self):
        """Test strategy_info is None when code is invalid (ST-003)."""
        result = validate_strategy_code("")
        assert result.valid is False
        assert result.strategy_info is None

    def test_strategy_info_has_init(self):
        """Test strategy_info detects __init__ method (ST-003)."""
        code = """
class TestStrat(Strategy):
    def __init__(self):
        self.x = 0
    def on_bar(self, bar):
        pass
"""
        result = validate_strategy_code(code)
        assert result.valid is True
        assert result.strategy_info["has_init"] is True

    def test_strategy_info_no_init(self, minimal_strategy):
        """Test strategy_info reports has_init=False when no __init__ (ST-003)."""
        result = validate_strategy_code(minimal_strategy)
        assert result.valid is True
        assert result.strategy_info["has_init"] is False
        assert result.strategy_info["class_name"] == "MinimalStrategy"


class TestCompileStrategy:
    """Tests for compile_strategy function."""

    def test_compile_valid_strategy(self, valid_strategy):
        """Test compiling valid strategy returns CompiledStrategy."""
        compiled = compile_strategy(valid_strategy)

        assert isinstance(compiled, CompiledStrategy)
        assert compiled.code_object is not None
        assert compiled.restricted_globals is not None

    def test_compile_minimal_strategy(self, minimal_strategy):
        """Test compiling minimal strategy."""
        compiled = compile_strategy(minimal_strategy)
        assert compiled.code_object is not None

    def test_compile_invalid_code_raises(self):
        """Test compiling invalid code raises ValueError."""
        code = "class BadStrategy(Strategy):\n    pass"
        with pytest.raises(ValueError) as exc_info:
            compile_strategy(code)
        assert "on_bar" in str(exc_info.value)

    def test_compile_syntax_error_raises(self):
        """Test compiling code with syntax error raises ValueError."""
        code = "class MyStrategy(Strategy)\n    def on_bar(): pass"
        with pytest.raises(ValueError) as exc_info:
            compile_strategy(code)
        assert (
            "syntax" in str(exc_info.value).lower() or "validation" in str(exc_info.value).lower()
        )


class TestBuildRestrictedGlobals:
    """Tests for _build_restricted_globals function."""

    def test_contains_builtins(self):
        """Test restricted globals contains builtins."""
        globals_dict = _build_restricted_globals()
        assert "__builtins__" in globals_dict

    def test_contains_decimal(self):
        """Test restricted globals includes Decimal."""
        globals_dict = _build_restricted_globals()
        builtins = globals_dict["__builtins__"]
        assert "Decimal" in builtins

    def test_contains_strategy_types(self):
        """Test restricted globals includes Strategy types."""
        globals_dict = _build_restricted_globals()
        assert "Strategy" in globals_dict
        assert "Bar" in globals_dict
        assert "Position" in globals_dict
        assert "OrderSide" in globals_dict
        assert "OrderType" in globals_dict

    def test_contains_math(self):
        """Test restricted globals includes restricted math proxy."""
        globals_dict = _build_restricted_globals()
        builtins = globals_dict["__builtins__"]
        assert "math" in builtins
        # math is now a restricted proxy, not the full module (SBX-2)
        restricted_math = builtins["math"]
        assert hasattr(restricted_math, "sin")
        assert hasattr(restricted_math, "pi")
        assert hasattr(restricted_math, "sqrt")

    def test_contains_guards(self):
        """Test restricted globals includes security guards."""
        globals_dict = _build_restricted_globals()
        assert "_getattr_" in globals_dict
        assert "_getiter_" in globals_dict
        assert "_getitem_" in globals_dict

    def test_contains_inplacevar(self):
        """Test restricted globals includes inplace var handler."""
        globals_dict = _build_restricted_globals()
        assert "_inplacevar_" in globals_dict


class TestInplaceVar:
    """Tests for _inplacevar_ function."""

    def test_addition(self):
        """Test += operation."""
        assert _inplacevar_("+=", 5, 3) == 8

    def test_subtraction(self):
        """Test -= operation."""
        assert _inplacevar_("-=", 10, 3) == 7

    def test_multiplication(self):
        """Test *= operation."""
        assert _inplacevar_("*=", 4, 5) == 20

    def test_division(self):
        """Test /= operation."""
        assert _inplacevar_("/=", 10, 2) == 5.0

    def test_floor_division(self):
        """Test //= operation."""
        assert _inplacevar_("//=", 10, 3) == 3

    def test_modulo(self):
        """Test %= operation."""
        assert _inplacevar_("%=", 10, 3) == 1

    def test_power(self):
        """Test **= operation."""
        assert _inplacevar_("**=", 2, 3) == 8


class TestDisallowedModules:
    """Tests for DISALLOWED_MODULES constant."""

    def test_os_disallowed(self):
        """Test os module is disallowed."""
        assert "os" in DISALLOWED_MODULES

    def test_sys_disallowed(self):
        """Test sys module is disallowed."""
        assert "sys" in DISALLOWED_MODULES

    def test_subprocess_disallowed(self):
        """Test subprocess module is disallowed."""
        assert "subprocess" in DISALLOWED_MODULES

    def test_socket_disallowed(self):
        """Test socket module is disallowed."""
        assert "socket" in DISALLOWED_MODULES

    def test_pickle_disallowed(self):
        """Test pickle module is disallowed."""
        assert "pickle" in DISALLOWED_MODULES


class TestDisallowedBuiltins:
    """Tests for DISALLOWED_BUILTINS constant."""

    def test_eval_disallowed(self):
        """Test eval is disallowed."""
        assert "eval" in DISALLOWED_BUILTINS

    def test_exec_disallowed(self):
        """Test exec is disallowed."""
        assert "exec" in DISALLOWED_BUILTINS

    def test_open_disallowed(self):
        """Test open is disallowed."""
        assert "open" in DISALLOWED_BUILTINS

    def test_import_disallowed(self):
        """Test __import__ is disallowed."""
        assert "__import__" in DISALLOWED_BUILTINS


class TestSafeBuiltins:
    """Tests for SAFE_BUILTINS constant."""

    def test_math_functions_allowed(self):
        """Test math functions are allowed."""
        assert "abs" in SAFE_BUILTINS
        assert "round" in SAFE_BUILTINS
        assert "pow" in SAFE_BUILTINS

    def test_type_conversion_allowed(self):
        """Test type conversion allowed."""
        assert "int" in SAFE_BUILTINS
        assert "float" in SAFE_BUILTINS
        assert "str" in SAFE_BUILTINS
        assert "bool" in SAFE_BUILTINS

    def test_collections_allowed(self):
        """Test collection functions allowed."""
        assert "len" in SAFE_BUILTINS
        assert "list" in SAFE_BUILTINS
        assert "dict" in SAFE_BUILTINS
        assert "set" in SAFE_BUILTINS
        assert "tuple" in SAFE_BUILTINS

    def test_iteration_allowed(self):
        """Test iteration functions allowed."""
        assert "range" in SAFE_BUILTINS
        assert "enumerate" in SAFE_BUILTINS
        assert "zip" in SAFE_BUILTINS
        assert "map" in SAFE_BUILTINS
        assert "filter" in SAFE_BUILTINS

    def test_print_allowed(self):
        """Test print is allowed for debugging."""
        assert "print" in SAFE_BUILTINS


class TestCompiledStrategyExecution:
    """Tests for executing compiled strategy code."""

    def test_execute_compiled_strategy(self, minimal_strategy):
        """Test executing compiled strategy."""
        compiled = compile_strategy(minimal_strategy)

        # Execute the compiled code
        local_namespace: dict = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        # Check strategy class was defined
        assert "MinimalStrategy" in local_namespace

    def test_strategy_inherits_from_base(self, minimal_strategy):
        """Test compiled strategy inherits from Strategy."""
        compiled = compile_strategy(minimal_strategy)

        local_namespace: dict = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        strategy_class = local_namespace["MinimalStrategy"]
        from squant.engine.backtest.strategy_base import Strategy

        assert issubclass(strategy_class, Strategy)

    def test_strategy_can_use_decimal(self):
        """Test strategy can use Decimal in code."""
        code = """
class DecimalStrategy(Strategy):
    def on_bar(self, bar):
        amount = Decimal("0.1")
        total = amount * Decimal("100")
"""
        compiled = compile_strategy(code)

        local_namespace: dict = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        assert "DecimalStrategy" in local_namespace

    def test_strategy_can_use_math_module(self):
        """Test strategy can use math functions (sqrt, log, exp)."""
        code = """
class MathStrategy(Strategy):
    def on_bar(self, bar):
        volatility = math.sqrt(0.04)
        log_return = math.log(bar.close / bar.open)
        weight = math.exp(-0.5)
"""
        compiled = compile_strategy(code)

        local_namespace: dict = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        assert "MathStrategy" in local_namespace

    def test_strategy_can_use_inplace_operators(self):
        """Test strategy can use += and other inplace operators on local variables."""
        code = """
class InplaceStrategy(Strategy):
    def on_bar(self, bar):
        counter = 0
        counter += 1
        total = counter * 10
"""
        compiled = compile_strategy(code)

        local_namespace: dict = {}
        exec(compiled.code_object, compiled.restricted_globals, local_namespace)

        assert "InplaceStrategy" in local_namespace


# =============================================================================
# Parameterized Tests - Best Practice Examples
# =============================================================================


class TestNewlyDisallowedModules:
    """Tests for newly added disallowed modules (STR-012).

    These modules were added to DISALLOWED_MODULES to prevent:
    - asyncio: Async network operations and execution bypass
    - ssl: Encrypted network connections
    - pdb/bdb/cmd: Debugger access for environment exploration
    """

    @pytest.mark.parametrize("module", ["asyncio", "ssl", "pdb", "bdb", "cmd"])
    def test_new_critical_module_in_disallowed_list(self, module: str) -> None:
        """Test that new critical modules are in DISALLOWED_MODULES."""
        assert module in DISALLOWED_MODULES, f"Module '{module}' should be disallowed"

    @pytest.mark.parametrize("module", ["asyncio", "ssl", "pdb", "bdb", "cmd"])
    def test_new_critical_module_import_blocked(self, module: str) -> None:
        """Test that importing new critical modules is blocked."""
        code = f"""
import {module}

class TestStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
        result = validate_strategy_code(code)
        assert result.valid is False, f"Import of '{module}' should be blocked"
        assert any(module in err for err in result.errors), f"Error should mention '{module}'"

    @pytest.mark.parametrize("module", ["asyncio", "ssl", "pdb"])
    def test_new_critical_module_from_import_blocked(self, module: str) -> None:
        """Test that from-import of new critical modules is blocked."""
        code = f"""
from {module} import *

class TestStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
        result = validate_strategy_code(code)
        assert result.valid is False, f"From-import of '{module}' should be blocked"

    def test_asyncio_event_loop_blocked(self) -> None:
        """Test asyncio event loop creation is blocked."""
        code = """
import asyncio

class TestStrategy(Strategy):
    def on_bar(self, bar):
        loop = asyncio.get_event_loop()
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("asyncio" in err for err in result.errors)

    def test_asyncio_run_blocked(self) -> None:
        """Test asyncio.run is blocked."""
        code = """
import asyncio

class TestStrategy(Strategy):
    def on_bar(self, bar):
        asyncio.run(self.async_method())
"""
        result = validate_strategy_code(code)
        assert result.valid is False

    def test_ssl_context_blocked(self) -> None:
        """Test SSL context creation is blocked."""
        code = """
import ssl

class TestStrategy(Strategy):
    def on_bar(self, bar):
        ctx = ssl.create_default_context()
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("ssl" in err for err in result.errors)

    def test_pdb_set_trace_blocked(self) -> None:
        """Test pdb.set_trace() is blocked."""
        code = """
import pdb

class TestStrategy(Strategy):
    def on_bar(self, bar):
        pdb.set_trace()
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("pdb" in err for err in result.errors)

    def test_bdb_debugger_blocked(self) -> None:
        """Test bdb debugger is blocked."""
        code = """
import bdb

class TestStrategy(Strategy):
    def on_bar(self, bar):
        debugger = bdb.Bdb()
"""
        result = validate_strategy_code(code)
        assert result.valid is False

    def test_cmd_module_blocked(self) -> None:
        """Test cmd module is blocked."""
        code = """
import cmd

class TestStrategy(Strategy):
    def on_bar(self, bar):
        shell = cmd.Cmd()
"""
        result = validate_strategy_code(code)
        assert result.valid is False


class TestDisallowedModulesParameterized:
    """Parameterized tests for all disallowed modules.

    This demonstrates the recommended pattern for testing similar behaviors
    across multiple inputs, reducing code duplication significantly.
    """

    # Key security-critical modules that must be blocked
    CRITICAL_MODULES = [
        "os",
        "sys",
        "subprocess",
        "socket",
        "pickle",
        "shutil",
        "pathlib",
        "ctypes",
        "multiprocessing",
        "threading",
        # STR-012: New modules
        "asyncio",
        "ssl",
        "pdb",
    ]

    @pytest.mark.parametrize("module", CRITICAL_MODULES)
    def test_critical_module_import_blocked(self, module: str) -> None:
        """Test that critical security modules are blocked via import statement."""
        code = f"""
import {module}

class TestStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
        result = validate_strategy_code(code)
        assert result.valid is False, f"Module '{module}' should be blocked"
        assert any(module in err for err in result.errors), f"Error should mention '{module}'"

    @pytest.mark.parametrize("module", CRITICAL_MODULES)
    def test_critical_module_from_import_blocked(self, module: str) -> None:
        """Test that critical modules are blocked via from-import statement."""
        code = f"""
from {module} import *

class TestStrategy(Strategy):
    def on_bar(self, bar):
        pass
"""
        result = validate_strategy_code(code)
        assert result.valid is False, f"Module '{module}' should be blocked via from-import"


class TestDisallowedBuiltinsParameterized:
    """Parameterized tests for dangerous builtin functions."""

    DANGEROUS_BUILTINS = [
        ("eval", "eval('1+1')"),
        ("exec", "exec('x=1')"),
        ("open", "open('file.txt')"),
        ("compile", "compile('x=1', '', 'exec')"),
        ("__import__", "__import__('os')"),
    ]

    @pytest.mark.parametrize("builtin_name,code_snippet", DANGEROUS_BUILTINS)
    def test_dangerous_builtin_blocked(self, builtin_name: str, code_snippet: str) -> None:
        """Test that dangerous builtin functions are blocked."""
        code = f"""
class TestStrategy(Strategy):
    def on_bar(self, bar):
        {code_snippet}
"""
        result = validate_strategy_code(code)
        assert result.valid is False, f"Builtin '{builtin_name}' should be blocked"
        assert any(builtin_name in err for err in result.errors), (
            f"Error should mention '{builtin_name}'"
        )


class TestInplaceOperatorsParameterized:
    """Parameterized tests for inplace operators."""

    OPERATORS = [
        ("+=", 5, 3, 8),
        ("-=", 10, 3, 7),
        ("*=", 4, 5, 20),
        ("/=", 10, 2, 5.0),
        ("//=", 10, 3, 3),
        ("%=", 10, 3, 1),
        ("**=", 2, 3, 8),
    ]

    @pytest.mark.parametrize("operator,left,right,expected", OPERATORS)
    def test_inplace_operator(self, operator: str, left: int, right: int, expected: float) -> None:
        """Test inplace operator produces correct result."""
        result = _inplacevar_(operator, left, right)
        assert result == expected, f"{left} {operator} {right} should equal {expected}"


class TestSafeBuiltinsParameterized:
    """Parameterized tests for allowed safe builtins."""

    MATH_FUNCTIONS = ["abs", "round", "pow", "min", "max", "sum", "divmod"]
    TYPE_CONVERSIONS = ["int", "float", "str", "bool"]
    COLLECTION_FUNCTIONS = ["len", "list", "dict", "set", "tuple", "frozenset"]
    ITERATION_FUNCTIONS = ["range", "enumerate", "zip", "map", "filter", "sorted", "reversed"]

    @pytest.mark.parametrize("func", MATH_FUNCTIONS)
    def test_math_function_allowed(self, func: str) -> None:
        """Test math functions are in SAFE_BUILTINS."""
        assert func in SAFE_BUILTINS, f"Math function '{func}' should be allowed"

    @pytest.mark.parametrize("func", TYPE_CONVERSIONS)
    def test_type_conversion_allowed(self, func: str) -> None:
        """Test type conversion functions are in SAFE_BUILTINS."""
        assert func in SAFE_BUILTINS, f"Type conversion '{func}' should be allowed"

    @pytest.mark.parametrize("func", COLLECTION_FUNCTIONS)
    def test_collection_function_allowed(self, func: str) -> None:
        """Test collection functions are in SAFE_BUILTINS."""
        assert func in SAFE_BUILTINS, f"Collection function '{func}' should be allowed"

    @pytest.mark.parametrize("func", ITERATION_FUNCTIONS)
    def test_iteration_function_allowed(self, func: str) -> None:
        """Test iteration functions are in SAFE_BUILTINS."""
        assert func in SAFE_BUILTINS, f"Iteration function '{func}' should be allowed"


class TestStrategyValidationParameterized:
    """Parameterized tests for strategy validation scenarios."""

    INVALID_STRATEGY_CASES = [
        (
            "empty_code",
            "",
            "empty",
        ),
        (
            "whitespace_only",
            "   \n\t  ",
            "empty",
        ),
        (
            "no_strategy_class",
            "class NotStrategy:\n    pass",
            "Strategy",
        ),
        (
            "no_on_bar_method",
            "class MyStrategy(Strategy):\n    pass",
            "on_bar",
        ),
        (
            "syntax_error",
            "class MyStrategy(Strategy)\n    def on_bar(self): pass",
            "syntax",
        ),
    ]

    @pytest.mark.parametrize("case_name,code,expected_error", INVALID_STRATEGY_CASES)
    def test_invalid_strategy_rejected(
        self, case_name: str, code: str, expected_error: str
    ) -> None:
        """Test that invalid strategy code is rejected with appropriate error."""
        result = validate_strategy_code(code)
        assert result.valid is False, f"Case '{case_name}' should fail validation"
        assert any(expected_error.lower() in err.lower() for err in result.errors), (
            f"Case '{case_name}' error should mention '{expected_error}'"
        )


# =============================================================================
# Security Attack Tests - Issue 004 & 005
# =============================================================================


class TestAttributeAccessBypass:
    """Security tests for attribute access bypass attempts (Issue 004).

    These tests verify that RestrictedPython blocks access to dangerous
    dunder attributes that could be used to escape the sandbox.

    RestrictedPython provides two layers of protection:
    1. Compile-time: Syntax validation blocks attributes starting with "_"
    2. Runtime: safer_getattr blocks dangerous attribute access

    Both mechanisms are valid security measures - we test that at least
    one blocks the attack.
    """

    @pytest.fixture
    def try_attack(self):
        """Helper to attempt an attack and verify it's blocked.

        Returns True if attack was blocked (either at compile time or runtime).
        """

        def _try_attack(attack_code: str) -> bool:
            """Try to compile and execute attack code. Returns True if blocked."""
            code = f"""
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        {attack_code}
"""
            try:
                compiled = compile_strategy(code)
                local_namespace: dict = {}
                exec(compiled.code_object, compiled.restricted_globals, local_namespace)

                # Try to instantiate and run
                from unittest.mock import MagicMock

                strategy_class = local_namespace["AttackStrategy"]
                instance = strategy_class.__new__(strategy_class)
                instance.ctx = MagicMock()

                bar = MagicMock()
                bar.close = 100
                bar.open = 99
                bar.symbol = "BTC/USDT"

                instance.on_bar(bar)
                # If we get here without exception, attack succeeded
                return False
            except (ValueError, AttributeError, TypeError, NameError, KeyError):
                # Blocked at compile time (ValueError) or runtime (others)
                return True
            except Exception:
                # Any other exception also counts as blocked
                return True

        return _try_attack

    def test_class_attribute_blocked(self, try_attack):
        """Test that __class__ access is blocked."""
        assert try_attack("x = self.__class__"), "__class__ access should be blocked"

    def test_bases_attribute_blocked(self, try_attack):
        """Test that __bases__ access is blocked."""
        assert try_attack("x = self.__class__.__bases__"), "__bases__ access should be blocked"

    def test_mro_attribute_blocked(self, try_attack):
        """Test that __mro__ access is blocked."""
        assert try_attack("x = self.__class__.__mro__"), "__mro__ access should be blocked"

    def test_subclasses_method_blocked(self, try_attack):
        """Test that __subclasses__() access is blocked."""
        assert try_attack("x = object.__subclasses__()"), "__subclasses__() should be blocked"

    def test_globals_attribute_blocked(self, try_attack):
        """Test that __globals__ access is blocked."""
        assert try_attack("x = self.on_bar.__globals__"), "__globals__ access should be blocked"

    def test_code_attribute_blocked(self, try_attack):
        """Test that __code__ access is blocked."""
        assert try_attack("x = self.on_bar.__code__"), "__code__ access should be blocked"

    def test_dict_attribute_on_class_blocked(self, try_attack):
        """Test that __dict__ access on classes is blocked."""
        assert try_attack("x = self.__class__.__dict__"), "__dict__ on class should be blocked"

    def test_builtins_access_blocked(self, try_attack):
        """Test that accessing __builtins__ is blocked."""
        assert try_attack("x = __builtins__"), "__builtins__ access should be blocked"

    # Parameterized test for common escape patterns
    ESCAPE_PATTERNS = [
        ("class_bases_chain", "self.__class__.__bases__[0].__subclasses__()"),
        ("mro_escape", "self.__class__.__mro__[1]"),
        ("func_globals", "(lambda: None).__globals__"),
        ("func_code", "(lambda: None).__code__"),
    ]

    @pytest.mark.parametrize("pattern_name,attack_code", ESCAPE_PATTERNS)
    def test_escape_pattern_blocked(self, try_attack, pattern_name: str, attack_code: str) -> None:
        """Test that known sandbox escape patterns are blocked."""
        assert try_attack(f"x = {attack_code}"), (
            f"Escape pattern '{pattern_name}' should be blocked"
        )


class TestFormatStringAttacks:
    """Security tests for format string attacks (Issue 005).

    These tests verify that format string attacks that try to access
    dangerous attributes through string formatting are blocked.

    Format string attacks can bypass attribute guards if not properly handled.
    RestrictedPython should block these at compile time or runtime.
    """

    @pytest.fixture
    def try_format_attack(self):
        """Helper to attempt a format string attack and verify it's blocked."""

        def _try_attack(format_code: str) -> bool:
            """Try to compile and execute format attack. Returns True if blocked."""
            code = f"""
class FormatAttackStrategy(Strategy):
    def on_bar(self, bar):
        obj = self
        {format_code}
"""
            try:
                compiled = compile_strategy(code)
                local_namespace: dict = {}
                exec(compiled.code_object, compiled.restricted_globals, local_namespace)

                from unittest.mock import MagicMock

                strategy_class = local_namespace["FormatAttackStrategy"]
                instance = strategy_class.__new__(strategy_class)
                instance.ctx = MagicMock()

                bar = MagicMock()
                bar.close = 100
                bar.open = 99
                bar.symbol = "BTC/USDT"

                instance.on_bar(bar)
                return False  # Attack succeeded
            except Exception:
                return True  # Attack blocked

        return _try_attack

    def test_format_class_access_blocked(self, try_format_attack):
        """Test that format string __class__ access is blocked."""
        assert try_format_attack('result = "{0.__class__}".format(obj)'), (
            "Format string __class__ access should be blocked"
        )

    def test_format_bases_access_blocked(self, try_format_attack):
        """Test that format string __bases__ access is blocked."""
        assert try_format_attack('result = "{0.__class__.__bases__}".format(obj)'), (
            "Format string __bases__ access should be blocked"
        )

    def test_format_init_globals_blocked(self, try_format_attack):
        """Test that format string __init__.__globals__ access is blocked."""
        assert try_format_attack('result = "{0.__init__.__globals__}".format(obj)'), (
            "Format string __init__.__globals__ access should be blocked"
        )

    def test_fstring_class_access_blocked(self, try_format_attack):
        """Test that f-string __class__ access is blocked."""
        assert try_format_attack('result = f"{obj.__class__}"'), (
            "F-string __class__ access should be blocked"
        )

    def test_fstring_nested_access_blocked(self, try_format_attack):
        """Test that f-string nested attribute access is blocked."""
        assert try_format_attack('result = f"{obj.__class__.__bases__}"'), (
            "F-string nested attribute access should be blocked"
        )

    # Common format string attack patterns
    FORMAT_ATTACK_PATTERNS = [
        ("format_class", '"{0.__class__}".format(obj)'),
        ("format_subclasses", '"{0.__class__.__subclasses__}".format(obj)'),
        ("format_mro", '"{0.__class__.__mro__}".format(obj)'),
        ("fstring_class", 'f"{obj.__class__}"'),
        ("fstring_dict", 'f"{obj.__dict__}"'),
    ]

    @pytest.mark.parametrize("attack_name,attack_code", FORMAT_ATTACK_PATTERNS)
    def test_format_attack_pattern_blocked(
        self, try_format_attack, attack_name: str, attack_code: str
    ) -> None:
        """Test that format string attack patterns are blocked."""
        assert try_format_attack(f"result = {attack_code}"), (
            f"Format attack '{attack_name}' should be blocked"
        )


class TestAdditionalSecurityChecks:
    """Additional security tests for edge cases."""

    def test_getattr_builtin_blocked_in_validation(self):
        """Test that getattr builtin is blocked at validation time."""
        code = """
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        x = getattr(self, '__class__')
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("getattr" in err for err in result.errors)

    def test_setattr_builtin_blocked_in_validation(self):
        """Test that setattr builtin is blocked at validation time."""
        code = """
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        setattr(self, 'evil', True)
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("setattr" in err for err in result.errors)

    def test_delattr_builtin_blocked_in_validation(self):
        """Test that delattr builtin is blocked at validation time."""
        code = """
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        delattr(self, 'ctx')
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("delattr" in err for err in result.errors)

    def test_vars_builtin_blocked_in_validation(self):
        """Test that vars builtin is blocked at validation time."""
        code = """
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        x = vars(self)
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("vars" in err for err in result.errors)

    def test_dir_builtin_blocked_in_validation(self):
        """Test that dir builtin is blocked at validation time."""
        code = """
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        x = dir(self)
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("dir" in err for err in result.errors)

    def test_type_builtin_blocked_in_validation(self):
        """Test that type builtin is blocked at validation time."""
        code = """
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        x = type(self)
"""
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("type" in err for err in result.errors)

    def test_restricted_math_safe_functions_accessible(self):
        """Test restricted math allows safe functions (SBX-2)."""
        globals_dict = _build_restricted_globals()
        builtins = globals_dict["__builtins__"]
        restricted_math = builtins["math"]

        import math

        # Verify safe functions work correctly
        assert restricted_math.sin(0) == math.sin(0)
        assert restricted_math.sqrt(4) == math.sqrt(4)
        assert restricted_math.pi == math.pi
        assert restricted_math.log(1) == math.log(1)
        assert restricted_math.ceil(1.5) == math.ceil(1.5)
        assert restricted_math.isnan(float("nan")) is True

    def test_restricted_math_blocks_dangerous_functions(self):
        """Test restricted math blocks DoS-capable functions (SBX-2)."""
        globals_dict = _build_restricted_globals()
        builtins = globals_dict["__builtins__"]
        restricted_math = builtins["math"]

        # These combinatorial functions could be used for DoS
        assert not hasattr(restricted_math, "factorial")
        assert not hasattr(restricted_math, "comb")
        assert not hasattr(restricted_math, "perm")
        assert not hasattr(restricted_math, "prod")
        assert not hasattr(restricted_math, "gcd")
        assert not hasattr(restricted_math, "lcm")

    def test_restricted_statistics_safe_functions_accessible(self):
        """Test restricted statistics allows safe functions (IMP-P2-8)."""
        globals_dict = _build_restricted_globals()
        builtins = globals_dict["__builtins__"]
        restricted_stats = builtins["statistics"]

        import statistics

        # Verify safe functions work correctly
        data = [1, 2, 3, 4, 5]
        assert restricted_stats.mean(data) == statistics.mean(data)
        assert restricted_stats.median(data) == statistics.median(data)
        assert restricted_stats.stdev(data) == statistics.stdev(data)
        assert restricted_stats.pstdev(data) == statistics.pstdev(data)
        assert restricted_stats.variance(data) == statistics.variance(data)
        assert restricted_stats.pvariance(data) == statistics.pvariance(data)

    def test_statistics_usable_in_strategy_sandbox(self):
        """Test that statistics module works end-to-end in strategy code (IMP-P2-8)."""
        code = """
class StatsStrategy(Strategy):
    def on_bar(self, bar):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        avg = statistics.mean(data)
        med = statistics.median(data)
        sd = statistics.stdev(data)
        self.ctx.log(f"mean={avg} median={med} stdev={sd:.2f}")
"""
        compiled = compile_strategy(code)
        assert compiled.code_object is not None

    def test_object_subclasses_blocked_by_attribute_guard(self):
        """Test that object.__subclasses__() is blocked by RestrictedPython.

        Note: 'object' itself may pass validation, but RestrictedPython
        blocks access to __subclasses__ (dunder attribute) at compile time.
        """
        code = """
class AttackStrategy(Strategy):
    def on_bar(self, bar):
        x = object.__subclasses__()
"""
        result = validate_strategy_code(code)
        # Blocked at compile time due to __subclasses__ attribute access
        assert result.valid is False
        # Error message mentions the invalid attribute pattern
        assert any(
            "__subclasses__" in err or "invalid attribute" in err.lower() for err in result.errors
        )
