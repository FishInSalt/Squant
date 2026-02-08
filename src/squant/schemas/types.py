"""Custom Pydantic types for schema serialization.

GP-001: Decimal fields serialize as JSON number (float) instead of string.
Keeps Decimal precision internally, only affects JSON output.
"""

from decimal import Decimal
from typing import Annotated

from pydantic.functional_serializers import PlainSerializer

# Use this in response schemas to serialize Decimal → float in JSON output.
# Internal Python value remains Decimal for precision.
# JSON output: 100.50 (number) instead of "100.50" (string)
NumberDecimal = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float)]
