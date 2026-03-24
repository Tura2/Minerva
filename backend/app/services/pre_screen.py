"""
Deterministic pre-screening gates.

Two gates available:
  - pre_screen()                  Minervini 7-point Stage 2 Trend Template (technical-swing)
  - pre_screen_mean_reversion()   Oversold bounce gate (mean-reversion-bounce)

No LLM calls. Returns PASS / FAIL with reasons.
If FAIL, LLM research is skipped — saving tokens on poor setups.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import logging

from app.services.indicators import detect_vcp_contractions

logger = logging.getLogger(__name__)

# Market-aware Stage 2 thresholds.
# TASE is more volatile and has fewer trading days (Sun–Thu + Israeli holidays),
# so some Minervini criteria are relaxed to avoid filtering all TASE stocks.
STAGE2_THRESHOLDS = {
    "US": {
        "above_52w_low_pct": 25.0,    # price >= 25% above 52w low
        "near_52w_high_pct": 25.0,    # price within 25% of 52w high
        "ma200_trend_sessions": 22,   # MA200 slope window
    },
    "TASE": {
        "above_52w_low_pct": 20.0,    # relaxed — TASE stocks recover from deeper drawdowns
        "near_52w_high_pct": 30.0,    # relaxed — allow wider distance from highs
        "ma200_trend_sessions": 15,   # fewer sessions — holidays create gaps in TASE data
    },
}

# Minimum Relative Volume for the liquidity gate.
# RVOL = today's volume / stock's own 50d average — market-agnostic by design.
# A floor of 0.5 means "trading at least half its own normal pace."
MIN_RVOL = {"US": 0.5, "TASE": 0.3}

# Absolute fallback floor — only used when RVOL cannot be computed (insufficient history).
MIN_AVG_VOLUME_FALLBACK = {"US": 200_000, "TASE": 30_000}


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

    # Pull market-specific thresholds
    t = STAGE2_THRESHOLDS.get(market.upper(), STAGE2_THRESHOLDS["US"])
    above_52w_low_pct = t["above_52w_low_pct"]
    near_52w_high_pct = t["near_52w_high_pct"]
    ma200_trend_sessions = t["ma200_trend_sessions"]

    price = indicators.get("price")
    ma50 = indicators.get("ma50")
    ma150 = indicators.get("ma150")
    ma200 = indicators.get("ma200")
    high_52w = indicators.get("high_52w")
    low_52w = indicators.get("low_52w")
    avg_vol_50 = indicators.get("avg_vol_50")
    rvol = indicators.get("rvol")

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

    # 4. MA200 trending up (market-specific session window)
    ma200_series = df["close"].rolling(200).mean().dropna()
    if len(ma200_series) >= ma200_trend_sessions:
        ma200_trending_up = bool(ma200_series.iloc[-1] > ma200_series.iloc[-ma200_trend_sessions])
    else:
        ma200_trending_up = False
    checks["ma200_trending_up"] = ma200_trending_up
    if not checks["ma200_trending_up"]:
        reasons.append(f"MA200 not trending up over last {ma200_trend_sessions} sessions")

    # 5. Price above MA50
    checks["price_above_ma50"] = price > ma50 if ma50 else False
    if not checks["price_above_ma50"]:
        reasons.append(f"Price {price:.2f} below MA50 {(ma50 or 0):.2f}")

    # 6. Price >= N% above 52-week low (market-specific threshold)
    if low_52w and low_52w > 0:
        above_low_pct = (price - low_52w) / low_52w * 100
        checks["above_52w_low"] = above_low_pct >= above_52w_low_pct
        if not checks["above_52w_low"]:
            reasons.append(
                f"Price only {above_low_pct:.1f}% above 52w low (need ≥{above_52w_low_pct}%)"
            )
    else:
        checks["above_52w_low"] = False
        reasons.append("52-week low unavailable")

    # 7. Price within N% of 52-week high (market-specific threshold)
    if high_52w and high_52w > 0:
        below_high_pct = (high_52w - price) / high_52w * 100
        checks["near_52w_high"] = below_high_pct <= near_52w_high_pct
        if not checks["near_52w_high"]:
            reasons.append(
                f"Price {below_high_pct:.1f}% below 52w high (need within {near_52w_high_pct}%)"
            )
    else:
        checks["near_52w_high"] = False
        reasons.append("52-week high unavailable")

    # ── Liquidity Check (RVOL-based) ─────────────────────────────────────────
    # Primary: RVOL — compares today's activity to the stock's own baseline.
    # Fallback: absolute avg volume when RVOL cannot be computed.
    min_rvol = MIN_RVOL.get(market.upper(), 0.5)
    if rvol is not None:
        checks["min_volume"] = rvol >= min_rvol
        if not checks["min_volume"]:
            reasons.append(
                f"RVOL {rvol:.2f} < {min_rvol} (below own average trading pace)"
            )
    elif avg_vol_50 is not None:
        fallback_min = MIN_AVG_VOLUME_FALLBACK.get(market.upper(), 200_000)
        checks["min_volume"] = avg_vol_50 >= fallback_min
        if not checks["min_volume"]:
            reasons.append(
                f"Avg 50-day volume {int(avg_vol_50):,} below minimum {fallback_min:,}"
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


# ── Mean Reversion Gate ────────────────────────────────────────────────────────

# Thresholds tuned per market for the mean-reversion-bounce workflow.
MR_THRESHOLDS = {
    "US": {
        "rsi_oversold": 45.0,          # RSI < 45 — mild oversold in an uptrend; RSI 38 was too extreme
        "freefall_buffer_pct": 15.0,   # price must be > MA200 × 0.85 (not a breakdown)
        "max_below_52w_high_pct": 45.0, # not more than 45% below 52w high
        "ma200_trend_sessions": 22,
    },
    "TASE": {
        "rsi_oversold": 48.0,          # relaxed — TASE is more volatile, dips are shallower
        "freefall_buffer_pct": 18.0,
        "max_below_52w_high_pct": 50.0, # wider for TASE drawdown patterns
        "ma200_trend_sessions": 15,
    },
}


def pre_screen_mean_reversion(
    symbol: str,
    market: str,
    df,  # pd.DataFrame
    indicators: Dict[str, Any],
) -> PreScreenResult:
    """
    Run Mean Reversion pre-screen gate — 7 deterministic checks.

    Checks (all must pass):
      1. long_term_trend_intact — price > MA200 (uptrend worth fading into)
      2. ma200_rising           — MA200 slope positive (structural foundation)
      3. price_below_mean       — price < MA20 (dip from short-term mean confirmed)
      4. rsi_oversold           — RSI-14 < threshold (quantified oversold)
      5. not_in_freefall        — price > MA200 × (1 - buffer) (dip, not breakdown)
      6. not_extended_down      — price < X% below 52w high (avoids structural damage)
      7. min_volume             — RVOL or absolute volume floor (liquidity gate)

    VCP detection is informational only (non-blocking for MR).
    """
    checks: Dict[str, bool] = {}
    reasons: list = []

    t = MR_THRESHOLDS.get(market.upper(), MR_THRESHOLDS["US"])
    rsi_threshold = t["rsi_oversold"]
    freefall_buffer = t["freefall_buffer_pct"] / 100.0
    max_below_high = t["max_below_52w_high_pct"]
    ma200_trend_sessions = t["ma200_trend_sessions"]

    price = indicators.get("price")
    ma20 = indicators.get("ma20")
    ma200 = indicators.get("ma200")
    rsi14 = indicators.get("rsi14")
    high_52w = indicators.get("high_52w")
    avg_vol_50 = indicators.get("avg_vol_50")
    rvol = indicators.get("rvol")

    if price is None:
        return PreScreenResult(
            passed=False,
            checks={},
            reasons=["No price data available"],
            summary="FAIL — no price data",
        )

    # 1. Long-term trend intact: price above MA200
    checks["long_term_trend_intact"] = bool(price > ma200) if ma200 else False
    if not checks["long_term_trend_intact"]:
        reasons.append(f"Price {price:.2f} below MA200 {(ma200 or 0):.2f} — trend broken")

    # 2. MA200 rising (market-specific window)
    ma200_series = df["close"].rolling(200).mean().dropna()
    if len(ma200_series) >= ma200_trend_sessions:
        ma200_rising = bool(ma200_series.iloc[-1] > ma200_series.iloc[-ma200_trend_sessions])
    else:
        ma200_rising = False
    checks["ma200_rising"] = ma200_rising
    if not checks["ma200_rising"]:
        reasons.append(f"MA200 not rising over last {ma200_trend_sessions} sessions")

    # 3. Price below MA20 (short-term dip confirmed)
    checks["price_below_mean"] = bool(price < ma20) if ma20 else False
    if not checks["price_below_mean"]:
        reasons.append(f"Price {price:.2f} not below MA20 {(ma20 or 0):.2f} — no dip yet")

    # 4. RSI oversold
    if rsi14 is not None:
        checks["rsi_oversold"] = rsi14 < rsi_threshold
        if not checks["rsi_oversold"]:
            reasons.append(f"RSI {rsi14:.1f} not oversold (need < {rsi_threshold})")
    else:
        checks["rsi_oversold"] = False
        reasons.append("RSI data unavailable")

    # 5. Not in freefall: price still reasonably close to MA200
    if ma200:
        freefall_floor = ma200 * (1.0 - freefall_buffer)
        checks["not_in_freefall"] = price > freefall_floor
        if not checks["not_in_freefall"]:
            reasons.append(
                f"Price {price:.2f} more than {t['freefall_buffer_pct']:.0f}% below MA200 "
                f"(floor {freefall_floor:.2f}) — potential structural breakdown"
            )
    else:
        checks["not_in_freefall"] = False
        reasons.append("MA200 unavailable for freefall check")

    # 6. Not structurally broken: price not too far below 52w high
    if high_52w and high_52w > 0:
        pct_below_high = (high_52w - price) / high_52w * 100
        checks["not_extended_down"] = pct_below_high < max_below_high
        if not checks["not_extended_down"]:
            reasons.append(
                f"Price {pct_below_high:.1f}% below 52w high "
                f"(max allowed {max_below_high:.0f}%) — structural damage"
            )
    else:
        checks["not_extended_down"] = False
        reasons.append("52-week high unavailable")

    # 7. Liquidity gate (reuses same logic as Stage 2)
    min_rvol = MIN_RVOL.get(market.upper(), 0.5)
    if rvol is not None:
        checks["min_volume"] = rvol >= min_rvol
        if not checks["min_volume"]:
            reasons.append(f"RVOL {rvol:.2f} < {min_rvol} (below own average trading pace)")
    elif avg_vol_50 is not None:
        fallback_min = MIN_AVG_VOLUME_FALLBACK.get(market.upper(), 200_000)
        checks["min_volume"] = avg_vol_50 >= fallback_min
        if not checks["min_volume"]:
            reasons.append(
                f"Avg 50-day volume {int(avg_vol_50):,} below minimum {fallback_min:,}"
            )
    else:
        checks["min_volume"] = False
        reasons.append("Volume data unavailable")

    # VCP detection — informational only (MR setups rarely have VCPs)
    vcp = detect_vcp_contractions(df, indicators)

    critical_checks = [
        "long_term_trend_intact",
        "ma200_rising",
        "price_below_mean",
        "rsi_oversold",
        "not_in_freefall",
        "not_extended_down",
        "min_volume",
    ]
    passed = all(checks.get(c, False) for c in critical_checks)

    rsi_str = f"RSI {rsi14:.0f}" if rsi14 is not None else "RSI n/a"
    if passed:
        summary = f"PASS — MR bounce setup: {rsi_str} oversold, price below MA20, trend intact"
    else:
        summary = f"FAIL — {len(reasons)} check(s) failed: {'; '.join(reasons[:2])}"

    return PreScreenResult(
        passed=passed,
        checks=checks,
        reasons=reasons,
        vcp=vcp,
        summary=summary,
    )


# ── Support-Bounce Gate ────────────────────────────────────────────────────────

# Support-proximity threshold: price must be within this % of nearest support
SUPPORT_PROXIMITY_PCT = {"US": 4.0, "TASE": 5.0}   # TASE more volatile
MIN_RR_RATIO = 2.0
RSI_MAX_SB = 65.0    # Not overbought
RSI_MIN_SB = 20.0    # Not in freefall
VOL_DRY_UP_THRESHOLD = 0.90  # 10d avg / 50d avg < 90%


def pre_screen_support_bounce(
    symbol: str,
    market: str,
    df,  # pd.DataFrame
    indicators: Dict[str, Any],
    sr_data: Dict[str, Any],
) -> PreScreenResult:
    """
    Deterministic gate for support-bounce setups. Seven checks:
      1. trend_intact       — price above MA200
      2. near_support       — nearest support within SUPPORT_PROXIMITY_PCT
      3. not_broken         — price has not closed below support zone low
      4. rsi_pullback       — RSI between RSI_MIN_SB and RSI_MAX_SB
      5. volume_compression — vol_dry_up_ratio < VOL_DRY_UP_THRESHOLD (if available)
      6. clear_target       — nearest resistance exists above price
      7. rr_adequate        — R:R ratio >= MIN_RR_RATIO

    Args:
        symbol:     Ticker (without .TA)
        market:     "US" or "TASE"
        df:         Daily OHLC DataFrame
        indicators: Output of compute_indicators()
        sr_data:    Output of detect_support_resistance_zones()
    """
    checks: Dict[str, bool] = {}
    reasons: List[str] = []

    price = float(indicators.get("price") or 0)
    ma200 = indicators.get("ma200")
    rsi14 = indicators.get("rsi14")
    vol_dry_up_ratio = indicators.get("vol_dry_up_ratio")
    nearest_support = sr_data.get("nearest_support")
    nearest_resistance = sr_data.get("nearest_resistance")
    rr_ratio = sr_data.get("rr_ratio")
    proximity_threshold = SUPPORT_PROXIMITY_PCT.get(market.upper(), 5.0)

    # 1. Trend intact: price > MA200
    checks["trend_intact"] = bool(ma200 and price > float(ma200))
    if not checks["trend_intact"]:
        ma200_str = f"{ma200:.2f}" if ma200 else "N/A"
        reasons.append(f"Price {price:.2f} below MA200 {ma200_str} — uptrend not intact")

    # 2. Near support
    if not nearest_support:
        checks["near_support"] = False
        reasons.append("No key support level detected below current price")
    else:
        distance_pct = nearest_support.get("distance_pct", 999)
        checks["near_support"] = distance_pct <= proximity_threshold
        if not checks["near_support"]:
            reasons.append(
                f"Nearest support {nearest_support['price']:.2f} is {distance_pct:.1f}% away "
                f"(max {proximity_threshold}%)"
            )

    # 3. Not broken: price still above support zone low
    if nearest_support:
        support_low = float(nearest_support.get("low", nearest_support["price"]) or nearest_support["price"])
        last_close = float(df["close"].iloc[-1]) if df is not None and not df.empty else price
        checks["not_broken"] = last_close > support_low
        if not checks["not_broken"]:
            reasons.append(
                f"Price {last_close:.2f} has closed below support zone low {support_low:.2f} — support broken"
            )
    else:
        checks["not_broken"] = False

    # 4. RSI pullback
    if rsi14 is None:
        checks["rsi_pullback"] = True  # non-blocking if unavailable
    else:
        rsi_val = float(rsi14)
        checks["rsi_pullback"] = RSI_MIN_SB <= rsi_val <= RSI_MAX_SB
        if not checks["rsi_pullback"]:
            if rsi_val > RSI_MAX_SB:
                reasons.append(f"RSI {rsi_val:.1f} is overbought (>{RSI_MAX_SB}) — not a pullback setup")
            else:
                reasons.append(f"RSI {rsi_val:.1f} is in freefall (<{RSI_MIN_SB}) — wait for stabilization")

    # 5. Volume compression (non-blocking — not all stocks show clear dry-up)
    if vol_dry_up_ratio is not None:
        checks["volume_compression"] = float(vol_dry_up_ratio) < VOL_DRY_UP_THRESHOLD
        if not checks["volume_compression"]:
            reasons.append(
                f"Volume not compressing: 10d/50d ratio {vol_dry_up_ratio:.2f} >= {VOL_DRY_UP_THRESHOLD} "
                f"(selling pressure still present)"
            )
    else:
        checks["volume_compression"] = True  # can't compute — allow through

    # 6. Clear target
    checks["clear_target"] = nearest_resistance is not None
    if not checks["clear_target"]:
        reasons.append("No clear resistance level found above price — cannot define target")

    # 7. R:R ratio
    if rr_ratio is None:
        checks["rr_adequate"] = False
        reasons.append("Cannot compute R:R — missing support or resistance level")
    else:
        checks["rr_adequate"] = float(rr_ratio) >= MIN_RR_RATIO
        if not checks["rr_adequate"]:
            reasons.append(
                f"R:R ratio {rr_ratio:.2f} below minimum {MIN_RR_RATIO:.1f} — risk not justified"
            )

    passed = all(checks.values())
    check_count = sum(checks.values())
    summary = (
        f"Support-bounce gate: {'PASS' if passed else 'FAIL'} "
        f"({check_count}/{len(checks)} checks passed)"
    )
    logger.info(f"[pre_screen_sb] {symbol}/{market}: {summary}")

    return PreScreenResult(
        passed=passed,
        checks=checks,
        reasons=reasons,
        vcp={},  # not applicable for support-bounce
        summary=summary,
    )
