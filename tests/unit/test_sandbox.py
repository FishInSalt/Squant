"""Unit tests for strategy code sandbox validation."""

import pytest

from squant.engine.sandbox import (
    DISALLOWED_MODULES,
    ValidationResult,
    compile_strategy,
    validate_strategy_code,
)


class TestValidateStrategyCode:
    """Tests for validate_strategy_code function."""

    def test_valid_strategy_code(self) -> None:
        """Test that valid strategy code passes validation."""
        code = '''
from decimal import Decimal

class MyStrategy(Strategy):
    """A simple test strategy."""

    def on_bar(self, bar):
        if bar.close > bar.open:
            self.buy(size=Decimal("0.1"))
'''
        result = validate_strategy_code(code)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_empty_code(self) -> None:
        """Test that empty code fails validation."""
        result = validate_strategy_code("")
        assert result.valid is False
        assert "cannot be empty" in result.errors[0]

    def test_whitespace_only_code(self) -> None:
        """Test that whitespace-only code fails validation."""
        result = validate_strategy_code("   \n\t  ")
        assert result.valid is False
        assert "cannot be empty" in result.errors[0]

    def test_syntax_error(self) -> None:
        """Test that syntax errors are caught."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self
'''
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("Syntax error" in e for e in result.errors)

    def test_missing_strategy_class(self) -> None:
        """Test that missing Strategy class fails validation."""
        code = '''
class NotAStrategy:
    def on_bar(self, bar):
        pass
'''
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("inherits from Strategy" in e for e in result.errors)

    def test_missing_on_bar_method(self) -> None:
        """Test that missing on_bar method fails validation."""
        code = '''
class MyStrategy(Strategy):
    def do_something(self):
        pass
'''
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any("on_bar" in e for e in result.errors)


class TestDisallowedImports:
    """Tests for forbidden module imports."""

    @pytest.mark.parametrize("module", [
        "os", "sys", "subprocess", "socket", "pickle",
    ])
    def test_disallowed_import(self, module: str) -> None:
        """Test that disallowed imports are rejected."""
        code = f'''
import {module}

class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any(f"'{module}'" in e for e in result.errors)

    @pytest.mark.parametrize("module", [
        "os", "sys", "subprocess", "shutil",
    ])
    def test_disallowed_from_import(self, module: str) -> None:
        """Test that 'from X import Y' is also rejected for disallowed modules."""
        code = f'''
from {module} import path

class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        result = validate_strategy_code(code)
        assert result.valid is False
        assert any(f"'{module}'" in e for e in result.errors)

    def test_disallowed_modules_set(self) -> None:
        """Test that DISALLOWED_MODULES contains expected modules."""
        expected = {"os", "sys", "subprocess", "socket", "pickle", "marshal"}
        assert expected.issubset(DISALLOWED_MODULES)


class TestAllowedCode:
    """Tests for allowed operations in strategy code."""

    def test_allowed_builtins(self) -> None:
        """Test that safe built-in functions are allowed."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        prices = [1, 2, 3, 4, 5]
        avg = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        sorted_prices = sorted(prices)
        print(f"Average: {avg}")
'''
        result = validate_strategy_code(code)
        assert result.valid is True

    def test_decimal_allowed(self) -> None:
        """Test that Decimal is allowed for precise calculations."""
        code = '''
from decimal import Decimal

class MyStrategy(Strategy):
    def on_bar(self, bar):
        price = Decimal("42000.50")
        size = Decimal("0.001")
        total = price * size
'''
        result = validate_strategy_code(code)
        assert result.valid is True

    def test_list_comprehension(self) -> None:
        """Test that list comprehensions are allowed."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        prices = [x * 2 for x in range(10)]
        filtered = [p for p in prices if p > 5]
'''
        result = validate_strategy_code(code)
        assert result.valid is True

    def test_dict_operations(self) -> None:
        """Test that dictionary operations are allowed."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        data = {"open": 100, "close": 110}
        keys = list(data.keys())
        values = list(data.values())
'''
        result = validate_strategy_code(code)
        assert result.valid is True


class TestDangerousCode:
    """Tests for dangerous code patterns that should be rejected."""

    def test_eval_rejected(self) -> None:
        """Test that eval is rejected."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        eval("print('dangerous')")
'''
        result = validate_strategy_code(code)
        # eval may be rejected at RestrictedPython level
        # The validation should fail
        assert result.valid is False or "eval" in str(result.errors)

    def test_exec_rejected(self) -> None:
        """Test that exec is rejected."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        exec("import os")
'''
        result = validate_strategy_code(code)
        assert result.valid is False or "exec" in str(result.errors)

    def test_open_rejected(self) -> None:
        """Test that open() is rejected."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        f = open("/etc/passwd", "r")
'''
        result = validate_strategy_code(code)
        assert result.valid is False or "open" in str(result.errors)

    def test_dunder_import_rejected(self) -> None:
        """Test that __import__ is rejected."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        os = __import__("os")
'''
        result = validate_strategy_code(code)
        # __import__ should be rejected at RestrictedPython level
        assert result.valid is False


class TestCompileStrategy:
    """Tests for compile_strategy function."""

    def test_compile_valid_strategy(self) -> None:
        """Test that valid strategy code compiles successfully."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        compiled = compile_strategy(code)
        assert compiled.code_object is not None
        assert compiled.restricted_globals is not None
        assert "__builtins__" in compiled.restricted_globals

    def test_compile_invalid_strategy_raises(self) -> None:
        """Test that invalid strategy code raises ValueError."""
        code = '''
import os

class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        with pytest.raises(ValueError) as exc_info:
            compile_strategy(code)
        assert "validation failed" in str(exc_info.value).lower()

    def test_compiled_has_safe_builtins(self) -> None:
        """Test that compiled strategy has safe built-ins."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        compiled = compile_strategy(code)
        builtins = compiled.restricted_globals["__builtins__"]

        # Check safe builtins are present
        assert "len" in builtins
        assert "sum" in builtins
        assert "print" in builtins
        assert "Decimal" in builtins

    def test_compiled_has_guards(self) -> None:
        """Test that compiled strategy has RestrictedPython guards."""
        code = '''
class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        compiled = compile_strategy(code)

        assert "_getattr_" in compiled.restricted_globals
        assert "_getiter_" in compiled.restricted_globals


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_valid(self) -> None:
        """Test that default result is valid."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_error(self) -> None:
        """Test adding an error."""
        result = ValidationResult(valid=True)
        result.add_error("Test error")

        assert result.valid is False
        assert "Test error" in result.errors

    def test_add_warning(self) -> None:
        """Test adding a warning."""
        result = ValidationResult(valid=True)
        result.add_warning("Test warning")

        assert result.valid is True  # Warnings don't invalidate
        assert "Test warning" in result.warnings
