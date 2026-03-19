"""
Position sizing service — deterministic fixed-fractional calculator.

Computes share quantity from entry price, stop price, account size, and risk %.
Ported from reference/claude-trading-skills/skills/position-sizer/.
"""

import math
from typing import Optional
import logging

logger = logging.getLogger(__name__)

CURRENCY_SYMBOL = {"US": "$", "TASE": "₪"}


def compute_position_size(
    entry_price: float,
    stop_price: float,
    account_size: float,
    risk_pct: float,
    market: str = "US",
    max_position_pct: Optional[float] = None,
) -> dict:
    """
    Fixed-fractional position sizing.

    Formula:
        risk_per_share  = entry_price - stop_price
        dollar_risk     = account_size * risk_pct / 100
        shares          = floor(dollar_risk / risk_per_share)

    Args:
        entry_price:       Planned entry price
        stop_price:        Hard stop-loss price (must be below entry)
        account_size:      Total account value in local currency
        risk_pct:          Max % of account to risk (e.g. 1.0 for 1%)
        market:            "US" or "TASE" (affects currency display)
        max_position_pct:  Optional max single position size as % of account

    Returns:
        {
          "shares": int,
          "position_value": float,
          "dollar_risk": float,
          "risk_pct_actual": float,
          "risk_per_share": float,
          "currency": str,
          "currency_symbol": str,
          "binding_constraint": str | None,
          "error": str | None,
        }
    """
    currency_sym = CURRENCY_SYMBOL.get(market.upper(), "$")
    currency = "ILS" if market.upper() == "TASE" else "USD"

    # Validate
    if entry_price <= 0:
        return _error("entry_price must be positive", currency, currency_sym)
    if stop_price >= entry_price:
        return _error("stop_price must be below entry_price", currency, currency_sym)
    if account_size <= 0:
        return _error("account_size must be positive", currency, currency_sym)
    if risk_pct <= 0 or risk_pct > 100:
        return _error("risk_pct must be between 0 and 100", currency, currency_sym)

    risk_per_share = entry_price - stop_price
    dollar_risk = account_size * risk_pct / 100
    shares = int(dollar_risk / risk_per_share)

    binding_constraint = None

    # Apply max position constraint
    if max_position_pct is not None and max_position_pct > 0:
        max_by_pos = int(account_size * max_position_pct / 100 / entry_price)
        if max_by_pos < shares:
            shares = max_by_pos
            binding_constraint = "max_position_pct"

    shares = max(0, shares)
    position_value = round(shares * entry_price, 2)
    actual_risk = round(shares * risk_per_share, 2)
    actual_risk_pct = round(actual_risk / account_size * 100, 2) if account_size > 0 else 0

    return {
        "shares": shares,
        "position_value": position_value,
        "dollar_risk": actual_risk,
        "risk_pct_actual": actual_risk_pct,
        "risk_per_share": round(risk_per_share, 4),
        "currency": currency,
        "currency_symbol": currency_sym,
        "binding_constraint": binding_constraint,
        "error": None,
    }


def _error(msg: str, currency: str, currency_sym: str) -> dict:
    logger.warning(f"Position sizing error: {msg}")
    return {
        "shares": 0,
        "position_value": 0.0,
        "dollar_risk": 0.0,
        "risk_pct_actual": 0.0,
        "risk_per_share": 0.0,
        "currency": currency,
        "currency_symbol": currency_sym,
        "binding_constraint": None,
        "error": msg,
    }
