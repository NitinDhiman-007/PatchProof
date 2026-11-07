"""Test suite for calculator module."""

from calculator.discount import calculate_discount


def test_calculate_discount_decimal():
    """Baseline test that passes when decimal is used."""
    assert calculate_discount(100.0, 0.10) == 90.0

