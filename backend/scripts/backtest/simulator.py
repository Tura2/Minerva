"""Day-by-day simulation loop — signal detection, entry resolution, exit processing."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from app.services.pre_screen import pre_screen, pre_screen_mean_reversion

logger = logging.getLogger(__name__)


# ── Entry resolution ──────────────────────────────────────────────────────────

def resolve_entry(
    entry_type: str,
    entry_price: float,
    d1_open: float,
    d1_high: float,
) -> Optional[float]:
    """Return fill price or None if entry not triggered.

    current  → always fills at D+1 open
    breakout → fills only if D+1 high >= entry_price; fill = entry_price
    """
    if entry_type == "current":
        return d1_open
    if entry_type == "breakout":
        return entry_price if d1_high >= entry_price else None
    logger.warning("Unknown entry_type=%s, treating as current", entry_type)
    return d1_open


# ── Signal detection ──────────────────────────────────────────────────────────

def detect_signals(
    symbol: str,
    market: str,
    df_slice,       # pd.DataFrame — point-in-time slice
    indicators: Dict[str, Any],
    mr_indicators: Dict[str, Any],
    open_symbols: Set[str],
) -> List[Dict[str, Any]]:
    """Run both pre-screen gates. Return passing workflow(s).

    If both pass, only technical-swing is returned (preferred workflow).
    If symbol is already in an open position, returns [].
    """
    if symbol in open_symbols:
        return []

    swing_result = pre_screen(symbol, market, df_slice, indicators)
    mr_result = pre_screen_mean_reversion(symbol, market, df_slice, mr_indicators)

    if swing_result.passed:
        return [{"workflow": "technical-swing", "pre_screen_result": swing_result}]
    if mr_result.passed:
        return [{"workflow": "mean-reversion-bounce", "pre_screen_result": mr_result}]
    return []
