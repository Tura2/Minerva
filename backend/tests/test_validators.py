"""Tests for validation utilities."""

import pytest
from app.utils.validators import (
    validate_symbol,
    validate_price,
    validate_position_size,
    get_currency_for_market,
)


def test_validate_price():
    """Test price validation."""
    assert validate_price(100.0)[0] is True
    assert validate_price(0.01)[0] is True
    assert validate_price(0.001)[0] is False
    assert validate_price(1_000_001)[0] is False


def test_validate_position_size():
    """Test position size validation."""
    assert validate_position_size(100)[0] is True
    assert validate_position_size(1)[0] is True
    assert validate_position_size(0)[0] is False
    assert validate_position_size(10_001)[0] is False


def test_get_currency_for_market():
    """Test currency mapping."""
    assert get_currency_for_market("US") == "USD"
    assert get_currency_for_market("TASE") == "ILS"


def test_get_currency_for_invalid_market():
    """Test invalid market raises error."""
    with pytest.raises(ValueError):
        get_currency_for_market("INVALID")
