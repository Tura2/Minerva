"""
LLM prompt builder for the mean-reversion-bounce workflow.

Philosophy: Hunt for oversold bounces within confirmed long-term uptrends.
NOT breakouts — FLOORS. The LLM identifies structural support confluence,
exhaustion signals, and sets a tight structural stop below that support.

Scale-out targets:
  T1 (40%) → MA20 (the primary mean-reversion target)
  T2 (35%) → prior resistance / gap fill
  T3 (25%) → full trend resumption area

Synthesized Score dimensions (6 × 0–10 = max 60):
  long_term_trend    — MA200 slope + price position vs MA150/MA200
  dip_depth_quality  — RSI depth + %B position + distance from MA20
  exhaustion_signals — Capitulation vol ratio + RSI divergence
  support_confluence — How many structural S/R layers converge near entry
  breadth_context    — Market breadth zone + sector alignment
  rs_quality         — RS rank + composite (leader temporarily weak vs laggard)
"""

from typing import Any, Dict, Optional

from app.services.pre_screen import PreScreenResult

MR_SYSTEM_PROMPT = (
    "You are a professional swing trader and quantitative analyst specializing in "
    "Mean Reversion and Oversold Bounce strategies within confirmed long-term uptrends. "
    "You identify high-probability bounce setups using exhaustion signals (capitulation volume, "
    "RSI divergence), structural support confluence, and RSI oversold conditions — "
    "exclusively in stocks that remain above their 200-day moving average. "
    "You produce rich, structured JSON trade plans: entry at the support floor, a tight "
    "structural stop below that floor, mean-reversion scale-out targets (T1=MA20, T2=resistance, "
    "T3=trend resumption), multi-scenario sizing, a Synthesized Setup Score, and a Final "
    "Recommendation narrative. "
    "Critical philosophy: You do NOT look for breakouts. You look for FLOORS — structural "
    "support levels where a controlled dip in a confirmed uptrend is likely to reverse. "
    "All prices must be in the correct currency for the market (USD for US stocks, ILS/NIS for TASE)."
)


def build_mr_research_prompt(
    symbol: str,
    market: str,
    indicators: Dict[str, Any],
    mr_indicators: Dict[str, Any],
    pre_screen_result: Optional[PreScreenResult],
    breadth: Dict[str, Any],
    portfolio_size: float,
    max_risk_pct: float,
    weekly_indicators: Optional[Dict[str, Any]] = None,
    rs_indicators: Optional[Dict[str, Any]] = None,
) -> str:
    """Build the LLM research prompt for mean-reversion-bounce workflow."""

    currency = "ILS (NIS)" if market.upper() == "TASE" else "USD"
    currency_sym = "₪" if market.upper() == "TASE" else "$"
    hours_note = "TASE trading hours: Sun–Thu 09:15–17:00 IL" if market.upper() == "TASE" else "NYSE hours: Mon–Fri 09:30–16:00 ET"

    price = indicators.get("price", 0)
    ma20 = indicators.get("ma20")
    ma50 = indicators.get("ma50")
    ma150 = indicators.get("ma150")
    ma200 = indicators.get("ma200")
    atr14 = indicators.get("atr14")
    rsi14 = indicators.get("rsi14")
    high_52w = indicators.get("high_52w")
    low_52w = indicators.get("low_52w")
    avg_vol_50 = indicators.get("avg_vol_50")
    rvol = indicators.get("rvol")
    ma200_up = indicators.get("ma200_trending_up", False)
    accum_days = indicators.get("accum_days_20")
    distrib_days = indicators.get("distrib_days_20")
    vol_dry_up_ratio = indicators.get("vol_dry_up_ratio")

    # MR-specific indicators
    bb_upper = mr_indicators.get("bb_upper")
    bb_middle = mr_indicators.get("bb_middle")
    bb_lower = mr_indicators.get("bb_lower")
    bb_pct_b = mr_indicators.get("bb_pct_b")
    dist_bb = mr_indicators.get("distance_from_lower_bb_pct")
    cap_detected = mr_indicators.get("capitulation_detected", False)
    cap_vol_ratio = mr_indicators.get("capitulation_vol_ratio", 0.0)
    cap_days_ago = mr_indicators.get("capitulation_days_ago")
    rsi_divergence = mr_indicators.get("rsi_divergence", False)
    rsi_trough_1 = mr_indicators.get("rsi_trough_1")
    rsi_trough_2 = mr_indicators.get("rsi_trough_2")
    price_low_1 = mr_indicators.get("price_low_1")
    price_low_2 = mr_indicators.get("price_low_2")

    # Minimum stop distance (structural beats ATR, but ATR is the absolute floor)
    atr_stop_min = round(atr14 * 0.8, 4) if atr14 else None
    min_stop_price = round(price - atr_stop_min, 4) if (price and atr_stop_min) else None

    # Pre-screen summary
    screen_lines = ""
    if pre_screen_result:
        screen_lines = f"\nMean Reversion Pre-Screen: {pre_screen_result.summary}\n"
        for k, v in pre_screen_result.checks.items():
            check_label = k.replace("_", " ").title()
            screen_lines += f"  {'✓' if v else '✗'} {check_label}\n"
        if pre_screen_result.reasons:
            screen_lines += f"  Note: {'; '.join(pre_screen_result.reasons[:3])}\n"

    # MA distance helpers
    def _pct(a, b):
        return f"{round((a / b - 1) * 100, 1):+.1f}%" if (a and b and b != 0) else "n/a"

    # Breadth context
    breadth_zone = breadth.get("zone", "Neutral")
    breadth_ratio = breadth.get("overall_ratio")
    breadth_available = breadth.get("available", False)
    breadth_score_val = breadth.get("composite_score")
    breadth_prob_score = _breadth_to_prob(breadth_zone)

    # RS context
    rs_composite = (rs_indicators or {}).get("rs_composite")
    rs_rank_pct = (rs_indicators or {}).get("rs_rank_pct")
    rs_benchmark = (rs_indicators or {}).get("benchmark_used", "SPY")

    # Weekly indicators
    weekly_trend = (weekly_indicators or {}).get("weekly_trend", "unknown")
    weekly_rsi = (weekly_indicators or {}).get("weekly_rsi14")
    weekly_ma10 = (weekly_indicators or {}).get("weekly_ma10")
    weekly_ma20 = (weekly_indicators or {}).get("weekly_ma20")

    prompt = f"""You are analyzing {symbol} ({market} market) for a MEAN REVERSION BOUNCE setup.
Market: {market} | Currency: {currency} | {hours_note}
Portfolio: {currency_sym}{portfolio_size:,.0f} | Max risk per trade: {max_risk_pct}%

═══════════════════════════════════════════
CURRENT PRICE & KEY LEVELS
═══════════════════════════════════════════
Current Price : {currency_sym}{price:.4f}
MA20          : {currency_sym}{f'{ma20:.4f}' if ma20 else 'n/a'} ({_pct(price, ma20)} from mean)
MA50          : {currency_sym}{f'{ma50:.4f}' if ma50 else 'n/a'} ({_pct(price, ma50)})
MA150         : {currency_sym}{f'{ma150:.4f}' if ma150 else 'n/a'} ({_pct(price, ma150)})
MA200         : {currency_sym}{f'{ma200:.4f}' if ma200 else 'n/a'} ({_pct(price, ma200)}) {'↑ RISING' if ma200_up else '→ FLAT/FALLING'}
52w High      : {currency_sym}{f'{high_52w:.4f}' if high_52w else 'n/a'} ({_pct(price, high_52w)} from high)
52w Low       : {currency_sym}{f'{low_52w:.4f}' if low_52w else 'n/a'}

ATR-14        : {currency_sym}{f'{atr14:.4f}' if atr14 else 'n/a'}
RSI-14        : {f'{rsi14:.1f}' if rsi14 else 'n/a'} {'⚡ OVERSOLD' if (rsi14 and rsi14 < 35) else '(oversold range)' if (rsi14 and rsi14 < 40) else ''}
Min stop price: {currency_sym}{f'{min_stop_price:.4f}' if min_stop_price else 'n/a'} (entry − 0.8×ATR14 = absolute floor)

═══════════════════════════════════════════
MEAN REVERSION SIGNALS
═══════════════════════════════════════════
Bollinger Bands (20,2):
  Upper : {currency_sym}{f'{bb_upper:.4f}' if bb_upper else 'n/a'}
  Middle: {currency_sym}{f'{bb_middle:.4f}' if bb_middle else 'n/a'} (= MA20)
  Lower : {currency_sym}{f'{bb_lower:.4f}' if bb_lower else 'n/a'}
  %B    : {f'{bb_pct_b:.2f}' if bb_pct_b is not None else 'n/a'}  (0.0 = at lower band, 1.0 = at upper band; <0 = pierced below)
  Gap to Lower BB: {f'{dist_bb:+.1f}%' if dist_bb is not None else 'n/a'}

Capitulation Volume:
  Detected    : {'YES ⚡' if cap_detected else 'No'}
  Peak ratio  : {f'{cap_vol_ratio:.1f}× avg volume' if cap_detected else 'n/a'}
  Sessions ago: {cap_days_ago if cap_detected else 'n/a'}
  (Interpretation: volume spike on a down day = weak-hand exhaustion)

RSI Divergence (30-session lookback):
  Bullish Divergence: {'YES ✓ (price lower low, RSI higher low)' if rsi_divergence else 'Not detected'}
  RSI trough 1 → 2  : {f'{rsi_trough_1:.1f} → {rsi_trough_2:.1f}' if (rsi_trough_1 and rsi_trough_2) else 'n/a'}
  Price low 1 → 2   : {f'{currency_sym}{price_low_1:.4f} → {currency_sym}{price_low_2:.4f}' if (price_low_1 and price_low_2) else 'n/a'}

═══════════════════════════════════════════
VOLUME PROFILE (last 20 sessions)
═══════════════════════════════════════════
Accumulation days: {accum_days if accum_days is not None else 'n/a'}
Distribution days: {distrib_days if distrib_days is not None else 'n/a'}
Net bias         : {'ACCUMULATION' if ((accum_days or 0) > (distrib_days or 0)) else 'DISTRIBUTION' if ((distrib_days or 0) > (accum_days or 0)) else 'BALANCED'}
Vol 10d/50d ratio: {f'{vol_dry_up_ratio:.2f}' if vol_dry_up_ratio else 'n/a'}
Today RVOL       : {f'{rvol:.2f}×' if rvol else 'n/a'}
50d avg volume   : {f'{int(avg_vol_50):,}' if avg_vol_50 else 'n/a'}

═══════════════════════════════════════════
WEEKLY TIMEFRAME
═══════════════════════════════════════════
Weekly trend   : {weekly_trend.upper()}
Weekly MA10    : {f'{currency_sym}{weekly_ma10:.4f}' if weekly_ma10 else 'n/a'}
Weekly MA20    : {f'{currency_sym}{weekly_ma20:.4f}' if weekly_ma20 else 'n/a'}
Weekly RSI-14  : {f'{weekly_rsi:.1f}' if weekly_rsi else 'n/a'}

═══════════════════════════════════════════
RELATIVE STRENGTH
═══════════════════════════════════════════
RS vs {rs_benchmark}:
  Composite (40/35/25 weighted): {f'{rs_composite:+.2f}%' if rs_composite is not None else 'n/a'}
  Rank vs watchlist             : {f'{rs_rank_pct:.0f}/100' if rs_rank_pct is not None else 'n/a'}
  (High RS rank = leader temporarily weak, not a broken stock)

═══════════════════════════════════════════
MARKET BREADTH
═══════════════════════════════════════════
{_format_breadth_mr(breadth, market)}

═══════════════════════════════════════════
PRE-SCREEN RESULT
═══════════════════════════════════════════{screen_lines}

═══════════════════════════════════════════
PROBABILITY HINTS (use these in your formula)
═══════════════════════════════════════════
breadth_prob_score   : {breadth_prob_score:.2f}  (derived from breadth zone: {breadth_zone})
weekly_trend_score   : {_weekly_score_mr(weekly_trend):.2f}  (uptrend=0.9, sideways=0.6, downtrend=0.3)
capitulation_score   : {_cap_score(cap_detected, cap_vol_ratio):.2f}  (no cap=0.3, weak=0.5, strong=0.8, extreme=1.0)
divergence_score     : {0.85 if rsi_divergence else 0.4:.2f}  (divergence confirmed={rsi_divergence})
rs_quality_hint      : {_rs_hint_mr(rs_rank_pct)}

═══════════════════════════════════════════
ANALYSIS INSTRUCTIONS
═══════════════════════════════════════════

STEP 1 — Chain of Thought (3–4 sentences):
  Assess: Is the long-term uptrend structurally intact (MA200 rising, price well above MA200)?
  Evaluate: Is the dip deep and clean (RSI deeply oversold, %B near/below 0, significant gap below MA20)?
  Identify: Is there evidence of seller exhaustion (capitulation volume, RSI divergence, or both)?
  Locate: Where is the most credible structural floor (MA200, prior swing lows, gap fills, key S/R)?

STEP 2 — Support-Anchored Entry & Stop:
  Entry: Can be "current" (enter now at the support floor) or "buy_stop" (wait for first bullish
         confirmation candle — close above yesterday's high, or bounce off a specific price level).
  Stop : Place BELOW the nearest structural support (MA200, prior swing low, gap fill, or significant
         horizontal S/R). This is a structural stop, NOT an arbitrary ATR multiple.
         Minimum floor: stop >= entry − 0.8×ATR14 ({currency_sym}{f'{atr_stop_min:.4f}' if atr_stop_min else 'n/a'}).
         Prefer a stop that makes the trade invalid if broken (i.e., below MA200 or below a key swing low).
  Rule : entry_price − stop_loss >= 0.8 × ATR14 (absolute minimum; structural stops are usually wider).

STEP 3 — Mean Reversion Scale-Out Targets:
  T1 (40% of shares): MA20 = {currency_sym}{f'{ma20:.4f}' if ma20 else 'n/a'}. This IS the mean reversion — the primary profit target.
                       T1 must be within ±3% of MA20. Do not invent a different T1.
  T2 (35% of shares): Prior resistance, gap fill, or MA50 ({currency_sym}{f'{ma50:.4f}' if ma50 else 'n/a'}).
                       Target a 1.5R–2R gain from entry.
  T3 (25% of shares): Full trend resumption — near 52w high or measured move up to prior highs.
                       This captures the case where the bounce becomes a new leg up.
  share_pct values must sum to exactly 100.

STEP 4 — Four Scenarios (probabilities must sum exactly to 1.0):
  1. Bull Case    — strong bounce with high volume, closes above MA20 quickly.
  2. Base Case    — gradual mean reversion over 5–15 days, reaches T1 and consolidates.
  3. Bear Case    — bounce fades at MA50 or prior resistance, no follow-through.
  4. Breakdown    — price breaks below structural stop (MA200 or key swing low), thesis invalidated.

STEP 5 — Synthesized Setup Score (6 dimensions, 0–10 each, max total 60):
  long_term_trend  : How intact is the uptrend? MA200 rising? Price comfortably above MA200 (not just barely)?
                     MA150/MA200 stack orderly? 0=broken trend, 5=intact, 10=pristine uptrend.
  dip_depth_quality: How oversold and clean is the pullback? RSI deeply below 35? Price significantly below
                     MA20? %B near or below 0? 0=barely dipped, 5=moderate, 10=very deep clean dip.
  exhaustion_signals: Evidence of seller exhaustion. Capitulation volume (>2× avg) + RSI divergence = 10.
                     One signal = 5–7. Neither = 0–3.
  support_confluence: How many structural support layers converge at/near entry price?
                      MA200 + prior swing low + gap fill = multiple layers = higher score.
                      0=arbitrary, 5=1–2 layers, 10=3+ converging layers.
  breadth_context  : Is the broader market supportive for a bounce? Use breadth_prob_score as reference.
                     Bear zone = 0–3, Neutral = 4–6, Bull = 7–10.
  rs_quality       : Is this a strong leader temporarily weak (high RS rank)? Or a laggard in distress?
                     RS rank >75 = 8–10 (leader pullback). RS rank 50–75 = 5–7. <50 = 0–4.

  Verdict mapping (same as swing workflow):
    total >= 42 → Strong Buy | 34–41 → Buy | 25–33 → Watch | < 25 → Avoid

STEP 6 — Bullish Probability (MUST be a computed decimal, not a rounded guess):
  Compute using this weighted formula:
    LT_trend_score   = (MA200_rising × 0.5 + price_comfortably_above_MA200 × 0.5)   weight 0.25
    Dip_quality      = (RSI_depth_score + BB_pct_b_score) / 2                         weight 0.25
    Exhaustion_score = (capitulation_score + divergence_score) / 2                    weight 0.20
    Support_strength = confluence_layers_score (0–1)                                  weight 0.20
    Breadth_score    = breadth_prob_score = {breadth_prob_score:.2f}                  weight 0.10

  bullish_probability = LT×0.25 + Dip×0.25 + Exhaustion×0.20 + Support×0.20 + Breadth×0.10
  Return as a decimal between 0.0 and 1.0 (e.g., 0.71). Do not round to 0.65.

STEP 7 — Final Recommendation:
  verdict    : "Strong Buy" | "Buy" | "Watch" | "Avoid" (must match synthesized_score total)
  action     : 1 specific actionable sentence (e.g., "Enter at {currency_sym}X.XX with stop below MA200 at {currency_sym}Y.YY")
  conviction : "high" | "medium" | "low"
  narrative  : 2–3 sentences covering: RS quality (leader or laggard?), exhaustion evidence,
               support floor quality, key prerequisite for the trade to work.

STEP 8 — Output the following JSON (no markdown, no extra text, just the JSON object):

{{
  "chain_of_thought": "3–4 sentence assessment of uptrend quality, dip depth, exhaustion signals, and support floor",

  "technical_analysis": {{
    "entry_price": <number>,
    "entry_type": "<current|buy_stop>",
    "stop_loss": <number>,
    "atr_stop_check": "<valid|violated>",
    "pivot_level": <number or null>,
    "key_support": [<number>, ...],
    "key_resistance": [<number>, ...],
    "pattern_stage": "<approaching-support|at-support|capitulating|reversing>"
  }},

  "scale_out_targets": [
    {{"label": "T1 — MA20", "price": <MA20 ± 3%>, "share_pct": 40}},
    {{"label": "T2 — Resistance / Gap Fill", "price": <number>, "share_pct": 35}},
    {{"label": "T3 — Trend Resumption", "price": <number>, "share_pct": 25}}
  ],

  "scenarios": [
    {{"name": "Bull Case",  "probability": <0–1>, "description": "...", "target": <number>, "invalidation": "..."}},
    {{"name": "Base Case",  "probability": <0–1>, "description": "...", "target": <number>, "invalidation": "..."}},
    {{"name": "Bear Case",  "probability": <0–1>, "description": "...", "target": <number>, "invalidation": "..."}},
    {{"name": "Breakdown",  "probability": <0–1>, "description": "...", "target": <number>, "invalidation": "..."}}
  ],

  "synthesized_score": {{
    "long_term_trend":   {{"score": <0–10>, "note": "..."}},
    "dip_depth_quality": {{"score": <0–10>, "note": "..."}},
    "exhaustion_signals":{{"score": <0–10>, "note": "..."}},
    "support_confluence":{{"score": <0–10>, "note": "..."}},
    "breadth_context":   {{"score": <0–10>, "note": "..."}},
    "rs_quality":        {{"score": <0–10>, "note": "..."}},
    "total": <sum of 6 scores, max 60>
  }},

  "execution_checklist": {{
    "prerequisites": ["...", "..."],
    "entry_triggers": ["...", "..."],
    "invalidation_conditions": ["...", "..."]
  }},

  "final_recommendation": {{
    "verdict": "<Strong Buy|Buy|Watch|Avoid>",
    "action": "specific 1-sentence action",
    "conviction": "<high|medium|low>",
    "narrative": "2–3 sentence story covering RS quality, exhaustion evidence, support floor"
  }},

  "entry_price": <number>,
  "entry_rationale": "1–2 sentences: why this price is the optimal entry at the support floor",
  "stop_loss": <number>,
  "stop_rationale": "1 sentence confirming stop is below structural support AND ≥ 0.8×ATR14 floor",
  "target": <T2 price from scale_out_targets>,
  "target_rationale": "1 sentence: why T2 is the primary target (gap fill, resistance, MA50)",
  "risk_reward_ratio": <(target - entry) / (entry - stop), rounded to 2 decimal places>,
  "bullish_probability": <computed decimal 0.0–1.0>,
  "key_triggers": ["3–5 specific conditions that confirm the bounce thesis"],
  "caveats": ["2–4 risks: what invalidates this trade, sector weakness, macro headwinds"],
  "setup_quality": "<A|B|C>",
  "trend_context": "daily + weekly trend assessment",
  "volume_context": "capitulation + distribution/accumulation assessment",
  "market_breadth_context": "how market breadth affects the bounce probability"
}}

═══════════════════════════════════════════
HARD RULES (violations will be rejected):
═══════════════════════════════════════════
1. entry_price ≤ current price (this is a MEAN REVERSION trade — you buy the dip, not the breakout)
   Exception: entry_type="buy_stop" allows entry slightly above current price for confirmation
2. stop_loss < entry_price (always)
3. entry_price − stop_loss >= 0.8 × ATR14 = {currency_sym}{f'{atr_stop_min:.4f}' if atr_stop_min else 'n/a'}
4. target (T2) gives R:R >= 1.5:1
5. scale_out share_pct sum = 100
6. scenarios probabilities sum = 1.0
7. synthesized_score total = sum of 6 dimension scores (max 60)
8. bullish_probability is a computed decimal (do NOT use 0.65 as a default)
9. All prices in {currency}
10. No margin: position fits within {currency_sym}{portfolio_size:,.0f}
11. T1 price must be within ±3% of MA20 = {currency_sym}{f'{ma20:.4f}' if ma20 else 'n/a'}
"""
    return prompt.strip()


# ── Private helpers ────────────────────────────────────────────────────────────


def _breadth_to_prob(zone: str) -> float:
    """Map breadth zone to a probability score 0.0–1.0."""
    mapping = {
        "Strong Bull": 0.95,
        "Bull": 0.80,
        "Neutral": 0.55,
        "Cautious": 0.35,
        "Bear": 0.15,
    }
    return mapping.get(zone, 0.55)


def _weekly_score_mr(weekly_trend: str) -> float:
    """Weekly trend score for MR — sideways is acceptable (stock digesting gains)."""
    if weekly_trend == "uptrend":
        return 0.9
    if weekly_trend == "sideways":
        return 0.6
    if weekly_trend == "downtrend":
        return 0.3
    return 0.5


def _cap_score(cap_detected: bool, cap_vol_ratio: float) -> float:
    """Capitulation score based on volume spike magnitude."""
    if not cap_detected:
        return 0.3
    if cap_vol_ratio >= 4.0:
        return 1.0
    if cap_vol_ratio >= 3.0:
        return 0.85
    if cap_vol_ratio >= 2.0:
        return 0.65
    return 0.5


def _rs_hint_mr(rs_rank_pct: Optional[float]) -> str:
    if rs_rank_pct is None:
        return "n/a — RS rank unavailable"
    if rs_rank_pct >= 80:
        return f"{rs_rank_pct:.0f}/100 — TOP TIER leader, pullback is a gift"
    if rs_rank_pct >= 60:
        return f"{rs_rank_pct:.0f}/100 — strong stock, quality dip candidate"
    if rs_rank_pct >= 40:
        return f"{rs_rank_pct:.0f}/100 — average relative strength, lower conviction"
    return f"{rs_rank_pct:.0f}/100 — weak RS, prefer high-RS stocks for MR bounces"


def _format_breadth_mr(breadth: Dict[str, Any], market: str) -> str:
    if not breadth.get("available"):
        note = breadth.get("note", "Breadth data unavailable")
        return f"Status : {note}\nZone   : Neutral (default)\n"

    zone = breadth.get("zone", "Neutral")
    ratio = breadth.get("overall_ratio")
    score = breadth.get("composite_score")
    lines = [
        f"Zone   : {zone}",
        f"Ratio  : {ratio:.1f}%" if ratio else "Ratio  : n/a",
        f"Score  : {score:.1f}/100" if score else "Score  : n/a",
    ]

    # Sector breakdown if available (list of {"name": str, "ratio": float})
    sectors = breadth.get("sectors") or []
    if sectors:
        lines.append("Sectors:")
        for s in sectors[:5]:
            name = s.get("name", "?")
            val = s.get("ratio")
            lines.append(f"  {name}: {val:.0f}%" if val is not None else f"  {name}: n/a")

    return "\n".join(lines)
