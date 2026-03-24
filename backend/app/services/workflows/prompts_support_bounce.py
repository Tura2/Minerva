# backend/app/services/workflows/prompts_support_bounce.py
"""
LLM prompt builder for the support-bounce workflow.

Key difference from swing prompts: asks for a CONDITIONAL PLAYBOOK (executable
commands), not an analysis report. The LLM must:
  - Determine setup_status: READY / NOT_READY / BROKEN
  - Write entry_trigger as an exact executable condition
  - List abort_conditions as specific price/volume events
  - Provide expiry_range (the price range where analysis stays valid)
  - Flag hidden_risks the trader might miss
"""

from typing import Any, Dict, Optional

SYSTEM_PROMPT_SB = """You are a veteran swing trader and technical analyst specializing in TASE (Tel Aviv Stock Exchange) stocks.
Your job is NOT to write a research report. Your job is to write a CONDITIONAL EXECUTION PLAYBOOK.

Rules:
- entry_trigger must be a SPECIFIC, EXECUTABLE condition: "Close above X.XX on volume > Y.Yx average" — never vague
- stop_loss must be a specific price level, never a range
- abort_conditions must be specific events that invalidate the setup BEFORE it triggers
- If the setup is NOT ready, say so clearly and tell the trader EXACTLY what to wait for
- If support is already broken, say BROKEN immediately
- hidden_risks must catch things a trader might miss: upcoming earnings, sector weakness, overbought market, thin liquidity
- R:R ratio must be computed to the first target (target_1)
- synthesized_score dimensions: support_zone_quality / trend_integrity / momentum_setup / rr_quality / market_context / timing_readiness
- All prices in ILS for TASE stocks
- Respond ONLY with valid JSON. No markdown, no text outside the JSON object."""


def build_playbook_prompt(
    symbol: str,
    market: str,
    indicators: Dict[str, Any],
    sr_data: Dict[str, Any],
    breadth: Dict[str, Any],
    portfolio_size: float,
    max_risk_pct: float,
    rs_indicators: Optional[Dict[str, Any]] = None,
    weekly_indicators: Optional[Dict[str, Any]] = None,
) -> str:
    price = indicators.get("price", "N/A")
    ma50 = indicators.get("ma50", "N/A")
    ma200 = indicators.get("ma200", "N/A")
    rsi14 = indicators.get("rsi14", "N/A")
    vol_dry_up_ratio = indicators.get("vol_dry_up_ratio", "N/A")
    rvol = indicators.get("rvol", "N/A")
    atr14 = indicators.get("atr14", "N/A")
    atr_pct = indicators.get("atr_pct", "N/A")

    nearest_support = sr_data.get("nearest_support") or {}
    nearest_resistance = sr_data.get("nearest_resistance") or {}
    rr_ratio = sr_data.get("rr_ratio", "N/A")
    support_zones_count = len(sr_data.get("support_zones", []))
    resistance_zones_count = len(sr_data.get("resistance_zones", []))

    breadth_zone = breadth.get("zone", "Unknown")
    breadth_score = breadth.get("composite_score", "N/A")

    rs_composite = (rs_indicators or {}).get("rs_composite", "N/A")
    rs_rank = (rs_indicators or {}).get("rs_rank_pct", "N/A")
    weekly_trend = (weekly_indicators or {}).get("weekly_trend", "N/A")
    weekly_rsi = (weekly_indicators or {}).get("weekly_rsi14", "N/A")

    currency = "ILS" if market.upper() == "TASE" else "USD"

    return f"""
Analyze {symbol} ({market}) for a support-bounce trade setup.

=== MARKET DATA ===
Price: {price} {currency}
MA50: {ma50} | MA200: {ma200}
RSI-14: {rsi14} | Weekly RSI-14: {weekly_rsi}
ATR-14: {atr14} ({atr_pct}% of price)
Relative Volume: {rvol}x | Volume Compression (10d/50d): {vol_dry_up_ratio}
Weekly Trend: {weekly_trend}

=== SUPPORT/RESISTANCE ===
Nearest Support: {nearest_support.get('price', 'N/A')} {currency}
  ({nearest_support.get('distance_pct', 'N/A')}% below price, {nearest_support.get('touches', 'N/A')} touches, {nearest_support.get('strength', 'N/A')})
Nearest Resistance: {nearest_resistance.get('price', 'N/A')} {currency}
  ({nearest_resistance.get('distance_pct', 'N/A')}% above price)
Computed R:R to first target: {rr_ratio}
Total support zones detected: {support_zones_count}
Total resistance zones detected: {resistance_zones_count}

=== RELATIVE STRENGTH ===
RS Composite: {rs_composite} | RS Rank in Universe: {rs_rank}%

=== MARKET BREADTH ===
Zone: {breadth_zone} | Score: {breadth_score}

=== ACCOUNT PARAMETERS ===
Portfolio: {portfolio_size} {currency} | Max Risk: {max_risk_pct}%

=== YOUR TASK ===
Write a conditional execution playbook. Determine setup_status first.

Return ONLY this JSON structure:

{{
  "setup_status": "READY" | "NOT_READY" | "BROKEN",
  "entry_trigger": "<exact condition: e.g. Close above X.XX ILS on volume > Y.Yx average>",
  "entry_price": <numeric trigger level>,
  "stop_loss": <exact stop price>,
  "target_1": <first target price>,
  "target_2": <second target price, or null>,
  "rr_ratio": <R:R to target_1, numeric>,
  "abort_conditions": [
    "<specific price/volume event that kills the setup before it triggers>",
    ...
  ],
  "expiry_range": {{ "low": <price>, "high": <price> }},
  "not_ready_reason": "<null if READY, else explain what is missing>",
  "check_back_condition": "<null if READY, else exactly what the trader should wait for>",
  "support_zone": {{ "low": <price>, "high": <price>, "strength": "Strong|Moderate|Weak" }},
  "resistance_zone": {{ "low": <price>, "high": <price> }},
  "hidden_risks": ["<risk the trader might overlook>", ...],
  "synthesized_score": {{
    "support_zone_quality": {{ "score": <0-10>, "note": "<brief>" }},
    "trend_integrity":      {{ "score": <0-10>, "note": "<brief>" }},
    "momentum_setup":       {{ "score": <0-10>, "note": "<brief>" }},
    "rr_quality":           {{ "score": <0-10>, "note": "<brief>" }},
    "market_context":       {{ "score": <0-10>, "note": "<brief>" }},
    "timing_readiness":     {{ "score": <0-10>, "note": "<brief>" }},
    "total": <sum of 6 dimension scores>
  }},
  "final_recommendation": {{
    "verdict": "Strong Buy" | "Buy" | "Watch" | "Avoid",
    "action": "<what to do right now>",
    "conviction": "high" | "medium" | "low",
    "narrative": "<2-3 sentences max>"
  }},
  "bullish_probability": <0.0-1.0>,
  "key_triggers": ["<what must happen for setup to work>", ...],
  "caveats": ["<risk factor>", ...]
}}
""".strip()
