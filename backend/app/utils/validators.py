"""Validation utilities for market data and business logic."""

import logging

logger = logging.getLogger(__name__)


def validate_symbol(symbol: str, market: str, valid_symbols: list) -> tuple[bool, str]:
    """
    Validate symbol exists in market.

    Returns:
    - (is_valid, reason)
    """
    if not symbol or not isinstance(symbol, str):
        return False, "Invalid symbol format"

    if symbol.upper() not in [s.upper() for s in valid_symbols]:
        return False, f"Symbol {symbol} not found in {market} market"

    return True, ""


def validate_price(price: float, min_price: float = 0.01) -> tuple[bool, str]:
    """Validate price is reasonable."""
    if price < min_price:
        return False, f"Price {price} below minimum {min_price}"

    if price > 1_000_000:
        return False, f"Price {price} exceeds maximum"

    return True, ""


def validate_position_size(quantity: int, max_quantity: int = 10_000) -> tuple[bool, str]:
    """Validate position size."""
    if quantity <= 0:
        return False, "Quantity must be positive"

    if quantity > max_quantity:
        return False, f"Quantity {quantity} exceeds maximum {max_quantity}"

    return True, ""


def validate_risk_amount(risk_amount: float, max_risk: float = 10_000) -> tuple[bool, str]:
    """Validate risk per trade."""
    if risk_amount < 0:
        return False, "Risk amount cannot be negative"

    if risk_amount > max_risk:
        return False, f"Risk amount ${risk_amount} exceeds maximum ${max_risk}"

    return True, ""


def get_currency_for_market(market: str) -> str:
    """Get default currency for market."""
    if market == "US":
        return "USD"
    elif market == "TASE":
        return "ILS"
    else:
        raise ValueError(f"Unknown market: {market}")


def get_trading_hours_for_market(market: str) -> dict:
    """Get trading hours for market."""
    if market == "US":
        return {"open": "09:30", "close": "16:00", "tz": "US/Eastern"}
    elif market == "TASE":
        return {"open": "09:15", "close": "17:00", "tz": "Asia/Jerusalem"}
    else:
        raise ValueError(f"Unknown market: {market}")
