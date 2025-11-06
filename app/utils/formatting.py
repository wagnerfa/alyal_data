"""Formatting helpers shared across templates and view logic."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional


def _to_decimal(value: Optional[float], quantize: str) -> Decimal:
    """Convert arbitrary numeric input to a Decimal quantized accordingly."""
    reference = Decimal(quantize)
    if value is None:
        return Decimal('0').quantize(reference, rounding=ROUND_HALF_UP)
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        decimal_value = Decimal('0')
    return decimal_value.quantize(reference, rounding=ROUND_HALF_UP)


def format_currency_br(value: Optional[float]) -> str:
    """Format numbers as Brazilian Real currency (e.g. R$ 1.234,56)."""
    quantized = _to_decimal(value, '0.01')
    sign = '-' if quantized < 0 else ''
    absolute = abs(quantized)
    integer_part, fractional_part = f"{absolute:.2f}".split('.')
    grouped = f"{int(integer_part):,}".replace(',', '.')
    return f"{sign}R$ {grouped},{fractional_part}"


def format_decimal_br(value: Optional[float], decimals: int = 1) -> str:
    """Format decimal numbers using a comma as separator (e.g. 12,3)."""
    decimals = max(0, int(decimals))
    pattern = '0' if decimals == 0 else '0.' + ('0' * decimals)
    quantized = _to_decimal(value, pattern)
    if decimals == 0:
        sign = '-' if quantized < 0 else ''
        absolute = abs(int(quantized))
        return f"{sign}{absolute:,}".replace(',', '.')
    formatted = f"{quantized:.{decimals}f}"
    return formatted.replace('.', ',')
