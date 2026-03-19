"""
Deterministic pre-screening gate for swing trade candidates.

Implements Minervini's 7-point Trend Template (Stage 2 check) plus
basic liquidity and VCP contraction detection.

No LLM calls. Returns PASS / FAIL with reasons.
If FAIL, LLM research is skipped — saving tokens on poor setups.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import logging

from app.services.indicators import detect_vcp_contractions

logger = logging.getLogger(__name__)

# Minervini Trend Template thresholds
STAGE2_ABOVE_52W_LOW_PCT = 25.0   # price >= 25% above 52-week low
STAGE2_NEAR_52W_HIGH_PCT = 25.0   # price within 25% of 52-week high

# Market-aware minimum average volume
MIN_AVG_VOLUME = {"US": 200_000, "TASE": 30_000}


@dataclass
class PreScreenResult:
    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    vcp: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""


def pre_screen(
    symbol: str,
    market: str,
    df,  # pd.DataFrame
    indicators: Dict[str, Any],
) -> PreScreenResult:
    """
    Run Stage 2 Trend Template checks + basic liquidity on a symbol.

    Args:
        symbol:     Ticker symbol (display name, no .TA suffix)
        market:     "US" or "TASE"
        df:         OHLC DataFrame (sorted ascending)
        indicators: Output from compute_indicators()

    Returns:
        PreScreenResult with passed=True if all checks pass.
    """
    checks: Dict[str, bool] = {}
    reasons: list = []

    price = indicators.get("price")
    ma50 = indicators.get("ma50")
    ma150 = indicators.get("ma150")
    ma200 = indicators.get("ma200")
    high_52w = indicators.get("high_52w")
    low_52w = indicators.get("low_52w")
    avg_vol_50 = indicators.get("avg_vol_50")
    ma200_trending_up = indicators.get("ma200_trending_up", False)

    if price is None:
        return PreScreenResult(
            passed=False,
            checks={},
            reasons=["No price data available"],
            summary="FAIL — no price data",
        )

    # ── Trend Template Checks ────────────────────────────────────────────────

    # 1. Price above MA150
    checks["price_above_ma150"] = price > ma150 if ma150 else False
    if not checks["price_above_ma150"]:
        reasons.append(f"Price {price:.2f} below MA150 {(ma150 or 0):.2f}")

    # 2. Price above MA200
    checks["price_above_ma200"] = price > ma200 if ma200 else False
    if not checks["price_above_ma200"]:
        reasons.append(f"Price {price:.2f} below MA200 {(ma200 or 0):.2f}")

    # 3. MA150 above MA200
    checks["ma150_above_ma200"] = (ma150 > ma200) if (ma150 and ma200) else False
    if not checks["ma150_above_ma200"]:
        reasons.append(f"MA150 {(ma150 or 0):.2f} not above MA200 {(ma200 or 0):.2f}")

    # 4. MA200 trending up (22+ sessions)
    checks["ma200_trending_up"] = ma200_trending_up
    if not checks["ma200_trending_up"]:
        reasons.append("MA200 not trending up over last 22 sessions")

    # 5. Price above MA50
    checks["price_above_ma50"] = price > ma50 if ma50 else False
    if not checks["price_above_ma50"]:
        reasons.append(f"Price {price:.2f} below MA50 {(ma50 or 0):.2f}")

    # 6. Price >= 25% above 52-week low
    if low_52w and low_52w > 0:
        above_low_pct = (price - low_52w) / low_52w * 100
        checks["above_52w_low"] = above_low_pct >= STAGE2_ABOVE_52W_LOW_PCT
        if not checks["above_52w_low"]:
            reasons.append(
                f"Price only {above_low_pct:.1f}% above 52w low (need ≥{STAGE2_ABOVE_52W_LOW_PCT}%)"
            )
    else:
        checks["above_52w_low"] = False
        reasons.append("52-week low unavailable")

    # 7. Price within 25% of 52-week high
    if high_52w and high_52w > 0:
        below_high_pct = (high_52w - price) / high_52w * 100
        checks["near_52w_high"] = below_high_pct <= STAGE2_NEAR_52W_HIGH_PCT
        if not checks["near_52w_high"]:
            reasons.append(
                f"Price {below_high_pct:.1f}% below 52w high (need within {STAGE2_NEAR_52W_HIGH_PCT}%)"
            )
    else:
        checks["near_52w_high"] = False
        reasons.append("52-week high unavailable")

    # ── Liquidity Check ──────────────────────────────────────────────────────
    min_vol = MIN_AVG_VOLUME.get(market.upper(), 200_000)
    if avg_vol_50 is not None:
        checks["min_volume"] = avg_vol_50 >= min_vol
        if not checks["min_volume"]:
            reasons.append(
                f"Avg 50-day volume {int(avg_vol_50):,} below minimum {min_vol:,}"
            )
    else:
        checks["min_volume"] = False
        reasons.append("Volume data unavailable")

    # ── VCP Detection (informational, non-blocking) ──────────────────────────
    vcp = detect_vcp_contractions(df, indicators)

    # Determine pass/fail
    critical_checks = [
        "price_above_ma150",
        "price_above_ma200",
        "ma150_above_ma200",
        "price_above_ma50",
        "above_52w_low",
        "near_52w_high",
        "min_volume",
    ]
    passed = all(checks.get(c, False) for c in critical_checks)

    if passed:
        vcp_note = f" | VCP detected ({vcp['contraction_count']} contractions)" if vcp["is_vcp"] else ""
        summary = f"PASS — Stage 2 confirmed{vcp_note}"
    else:
        summary = f"FAIL — {len(reasons)} check(s) failed: {'; '.join(reasons[:2])}"

    return PreScreenResult(
        passed=passed,
        checks=checks,
        reasons=reasons,
        vcp=vcp,
        summary=summary,
    )
