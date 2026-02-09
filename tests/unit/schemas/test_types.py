"""Unit tests for custom Pydantic types (GP-001)."""

from decimal import Decimal

from pydantic import BaseModel

from squant.schemas.types import NumberDecimal


class _SampleModel(BaseModel):
    """Helper model for testing NumberDecimal serialization."""

    price: NumberDecimal
    amount: NumberDecimal


class TestNumberDecimal:
    """Tests for NumberDecimal type alias."""

    def test_accepts_decimal_input(self):
        """Test NumberDecimal accepts Decimal values."""
        m = _SampleModel(price=Decimal("42000.50"), amount=Decimal("1.5"))
        assert m.price == Decimal("42000.50")
        assert m.amount == Decimal("1.5")

    def test_accepts_string_input(self):
        """Test NumberDecimal accepts string coercion (Pydantic default)."""
        m = _SampleModel(price="100.25", amount="0.001")
        assert m.price == Decimal("100.25")
        assert m.amount == Decimal("0.001")

    def test_accepts_int_input(self):
        """Test NumberDecimal accepts int input."""
        m = _SampleModel(price=100, amount=2)
        assert m.price == Decimal("100")
        assert m.amount == Decimal("2")

    def test_accepts_float_input(self):
        """Test NumberDecimal accepts float input."""
        m = _SampleModel(price=99.99, amount=0.5)
        assert isinstance(m.price, Decimal)

    def test_json_serializes_as_float(self):
        """Test JSON output uses float (number), not string."""
        m = _SampleModel(price=Decimal("42000.50"), amount=Decimal("1.5"))
        data = m.model_dump(mode="json")
        assert isinstance(data["price"], float)
        assert isinstance(data["amount"], float)
        assert data["price"] == 42000.5
        assert data["amount"] == 1.5

    def test_python_dump_returns_float(self):
        """Test model_dump (python mode) also returns float due to PlainSerializer."""
        m = _SampleModel(price=Decimal("42000.50"), amount=Decimal("1.5"))
        data = m.model_dump()
        assert isinstance(data["price"], float)
        assert isinstance(data["amount"], float)

    def test_attribute_access_preserves_decimal(self):
        """Test direct attribute access preserves Decimal type."""
        m = _SampleModel(price=Decimal("42000.50"), amount=Decimal("1.5"))
        assert isinstance(m.price, Decimal)
        assert isinstance(m.amount, Decimal)

    def test_json_roundtrip_precision(self):
        """Test precision is preserved in JSON output for typical trading values."""
        m = _SampleModel(price=Decimal("0.00001234"), amount=Decimal("99999.99"))
        data = m.model_dump(mode="json")
        assert data["price"] == 1.234e-05
        assert data["amount"] == 99999.99

    def test_zero_value(self):
        """Test zero serializes correctly."""
        m = _SampleModel(price=Decimal("0"), amount=Decimal("0.0"))
        data = m.model_dump(mode="json")
        assert data["price"] == 0.0
        assert data["amount"] == 0.0

    def test_model_dump_json_string(self):
        """Test model_dump_json produces number, not quoted string."""
        m = _SampleModel(price=Decimal("42000.50"), amount=Decimal("1.5"))
        json_str = m.model_dump_json()
        # Should contain 42000.5 as a number, not "42000.5" as a string
        assert '"42000.5"' not in json_str
        assert "42000.5" in json_str
