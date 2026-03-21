"""
LLM prompts for the technical-swing workflow.

Combines adapted frameworks from:
  - technical-analyst (OHLC trend + S/R analysis, 4-scenario framework)
  - vcp-screener (Minervini VCP methodology, RS scoring)
  - uptrend-analyzer (market breadth context)
  - position-sizer (multi-target scale-out, 1R/2R/3R)

Output schema enforced via JSON mode.
"""

from typing import Dict, Any, Optional


SYSTEM_PROMPT = """You are a professional swing trader and technical analyst specializing in Minervini's SEPA methodology.
You analyze stocks using the Stage 2 Trend Template, VCP methodology, multi-timeframe confluence, RS ranking, and market breadth data.
You produce rich, structured JSON trade plans: entry/stop/targets, multi-scenario sizing, a Synthesized Setup Score, and a Final Recommendation narrative.
You are precise, disciplined, and risk-aware. You never recommend trades that violate Stage 2 criteria.
All prices must be in the correct currency for the market (USD for US, ILS/NIS for TASE).
Your chain_of_thought field must be the FIRST field you write in the JSON. Reason carefully before committing to any number.
"""


def build_research_prompt(
    symbol: str,
    market: str,
    indicators: Dict[str, Any],
    pre_screen_result,  # PreScreenResult
    breadth: Dict[str, Any],
    portfolio_size: float,
    max_risk_pct: float,
    weekly_indicators: Optional[Dict[str, Any]] = None,
    rs_indicators: Optional[Dict[str, Any]] = None,
    period_candles: int = 252,
) -> str:
    """
    Build the combined research prompt for LLM analysis.

    Returns a prompt string that produces a rich JSON trade plan with:
    chain-of-thought, ATR-validated stop, multi-timeframe context, volume profile,
    RS strength, 4 scenarios, Synthesized Score, scale-out targets, and Final Recommendation.
    """
    currency = "ILS (NIS)" if market.upper() == "TASE" else "USD"
    currency_sym = "\u20aa" if market.upper() == "TASE" else "$"
    market_label = "Tel Aviv Stock Exchange (TASE)" if market.upper() == "TASE" else "US Stock Market (NYSE/Nasdaq)"
    exchange_note = (
        "Trading hours: 9:15\u201317:00 Israel Time (Sunday\u2013Thursday). Prices in NIS."
        if market.upper() == "TASE"
        else "Trading hours: 9:30\u201316:00 ET (Monday\u2013Friday). Prices in USD."
    )

    price = indicators.get("price", "N/A")
    ma20 = indicators.get("ma20", "N/A")
    ma50 = indicators.get("ma50", "N/A")
    ma150 = indicators.get("ma150", "N/A")
    ma200 = indicators.get("ma200", "N/A")
    atr14 = indicators.get("atr14", "N/A")
    rsi14 = indicators.get("rsi14", "N/A")
    high_52w = indicators.get("high_52w", "N/A")
    low_52w = indicators.get("low_52w", "N/A")
    avg_vol = indicators.get("avg_vol_50", "N/A")
    rvol = indicators.get("rvol", "N/A")
    ma200_trend = "Yes" if indicators.get("ma200_trending_up") else "No"

    # ATR-based minimum stop distance
    atr14_val = indicators.get("atr14")
    min_stop_distance = round(atr14_val * 0.8, 4) if atr14_val else "N/A"

    vcp = pre_screen_result.vcp
    vcp_section = f"""
VCP Detection:
  - Contractions found: {vcp.get('contraction_count', 0)}
  - Depths (%): {vcp.get('depths', [])}
  - VCP pattern confirmed: {vcp.get('is_vcp', False)}
  - Pivot buy point: {vcp.get('pivot_buy_point', 'N/A')}
""" if vcp else "VCP: insufficient data"

    stage2_checks = "\n".join(
        f"  - {k}: {'PASS' if v else 'FAIL'}"
        for k, v in pre_screen_result.checks.items()
    )
    stage2_pass_count = sum(1 for v in pre_screen_result.checks.values() if v)
    stage2_total = len(pre_screen_result.checks)

    breadth_section = _format_breadth(breadth, market)
    weekly_section = _format_weekly(weekly_indicators)
    volume_profile_section = _format_volume_profile(indicators)
    rs_section = _format_rs(rs_indicators, market)

    account_risk = round(portfolio_size * max_risk_pct / 100, 2)

    # Pre-computed axis scores for probability formula
    breadth_zone = breadth.get("zone", "Neutral")
    breadth_prob_score = {
        "Strong Bull": "1.0", "Bull": "0.8", "Bullish": "0.8",
        "Neutral": "0.5", "Cautious": "0.3",
        "Bearish": "0.2", "Bear": "0.1",
    }.get(breadth_zone, "0.5")

    vcp_is_confirmed = vcp.get("is_vcp", False) if vcp else False
    vcp_count = vcp.get("contraction_count", 0) if vcp else 0
    if vcp_is_confirmed and vcp_count >= 3:
        vcp_prob_hint = "1.0 (confirmed VCP, 3+ contractions)"
    elif vcp_is_confirmed:
        vcp_prob_hint = "0.75 (confirmed VCP)"
    elif vcp_count >= 1:
        vcp_prob_hint = "0.40 (partial contraction only)"
    else:
        vcp_prob_hint = "0.20 (no VCP pattern)"

    weekly_trend = (weekly_indicators or {}).get("weekly_trend", "unknown")
    weekly_trend_score = {
        "uptrend": "1.0", "sideways": "0.5", "downtrend": "0.0", "unknown": "0.5"
    }.get(weekly_trend, "0.5")

    # RS hint for synthesized score
    rs_composite = (rs_indicators or {}).get("rs_composite")
    rs_rank = (rs_indicators or {}).get("rs_rank_pct")
    if rs_rank is not None:
        if rs_rank >= 80:
            rs_score_hint = f"high (rank {rs_rank:.0f}/100, composite {rs_composite:+.1f}%)"
        elif rs_rank >= 50:
            rs_score_hint = f"medium (rank {rs_rank:.0f}/100, composite {rs_composite:+.1f}%)"
        else:
            rs_score_hint = f"low (rank {rs_rank:.0f}/100, composite {rs_composite:+.1f}%)"
    elif rs_composite is not None:
        rs_score_hint = f"composite {rs_composite:+.1f}% vs benchmark (no universe rank)"
    else:
        rs_score_hint = "RS data unavailable"

    return f"""Analyze {symbol} for a swing trade entry on the {market_label}.
{exchange_note}

Portfolio context:
  - Account size: {currency_sym}{portfolio_size:,.2f} {currency}
  - Max risk per trade: {max_risk_pct}% = {currency_sym}{account_risk:,.2f} {currency}

=== DAILY TECHNICAL INDICATORS (latest session) ===
  - Price:      {price}
  - MA20:       {ma20}
  - MA50:       {ma50}
  - MA150:      {ma150}
  - MA200:      {ma200}
  - MA200 Trending Up (22 sessions): {ma200_trend}
  - ATR-14:     {atr14}  ← minimum stop distance = 0.8 × ATR14 = {min_stop_distance}
  - RSI-14:     {rsi14}
  - RVOL (vs 50d avg): {rvol}
  - 52-week High: {high_52w}
  - 52-week Low:  {low_52w}
  - Avg Volume (50-day): {avg_vol}

{weekly_section}

{volume_profile_section}

{rs_section}

=== STAGE 2 TREND TEMPLATE ({stage2_pass_count}/{stage2_total} checks passing) ===
{stage2_checks}
Pre-screen result: {pre_screen_result.summary}

{vcp_section}

{breadth_section}

=== INSTRUCTIONS ===

STEP 1 — Write chain_of_thought (3-4 sentences) evaluating:
  a) Daily + weekly trend alignment (both timeframes bullish/bearish/mixed?)
  b) RS strength vs benchmark — is the stock outperforming or lagging the index?
  c) Key support and resistance levels from the indicator data above
  d) Overall conviction and pattern stage (pre-vcp / developing / entry-ready / extended)

STEP 2 — Compute the ATR-validated stop loss:
  The stop_loss MUST be at least {min_stop_distance} {currency} below entry_price.
  Formula: minimum_stop = entry_price - {min_stop_distance}
  If your preferred stop (based on S/R) is tighter, widen it to entry_price - {min_stop_distance}.

  ACCOUNT SIZE CONSTRAINT: The account is {currency_sym}{portfolio_size:,.2f}. A very tight stop forces
  a massive share count that may require margin. If you identify multiple valid technical support
  levels for the stop, PREFER the wider, more structural level (e.g. the base low or prior
  consolidation floor rather than the intraday low) when it still makes technical sense.
  A slightly wider stop with a position that fits within the account is always better than a
  theoretically perfect tight stop that requires buying on margin.

STEP 3 — Set 3 scale-out targets using R-multiples:
  T1 (1R): entry + 1 × (entry - stop) — take 40% of shares
  T2 (2R): entry + 2 × (entry - stop) — take 35% of shares
  T3 (3R): entry + 3 × (entry - stop) — take 25% of shares (align with prior resistance if possible)
  share_pct values must sum to exactly 100.

STEP 4 — Write 4 scenarios (probabilities must sum to exactly 1.0):
  Bull Case:  best-case outcome, trend accelerates to T3
  Base Case:  setup plays as planned, exits between T1 and T2
  Bear Case:  entry stalls or fades, exits at stop
  Breakdown:  gap below stop on bad news, emergency exit

STEP 5 — Synthesized Setup Score (score each dimension 0-10):
  trend_template:  MA stack quality + direction + ATH proximity
  vcp_pattern:     contraction count + depth + pivot proximity
  volume_profile:  accum/distrib ratio + dry-up compression
  rs_strength:     RS vs benchmark — {rs_score_hint}
    (9-10 = top-tier RS rank 80+, 7-8 = above average 60-80, 5-6 = average 40-60, <5 = below average)
  breadth_context: market zone + sector alignment
  weekly_alignment: weekly trend + weekly RSI position
  total = sum of all 6 dimension scores (max 60)
  Verdict: ≥42 → "Strong Buy", 34-41 → "Buy", 25-33 → "Watch", <25 → "Avoid"

STEP 6 — Compute bullish_probability using this weighted formula (do NOT default to 0.65):
  Stage2_score  = {stage2_pass_count}/{stage2_total} = {round(stage2_pass_count / stage2_total, 2) if stage2_total else 0.5}   (weight 0.30)
  Weekly_score  = {weekly_trend_score}   ({weekly_trend})  (weight 0.25)
  VCP_score     = {vcp_prob_hint}        (weight 0.20)
  Volume_score  = compute from accum/distrib above: accum > distrib+2 → 0.85, balanced → 0.50, distrib > accum+2 → 0.20  (weight 0.15)
  Breadth_score = {breadth_prob_score}   ({breadth_zone})  (weight 0.10)
  bullish_probability = (Stage2×0.30) + (Weekly×0.25) + (VCP×0.20) + (Volume×0.15) + (Breadth×0.10)
  Report the computed decimal. Do NOT round to 0.65 or 0.35.

STEP 7 — Final Recommendation:
  verdict: derive from synthesized_score.total (≥42 Strong Buy, 34-41 Buy, 25-33 Watch, <25 Avoid)
  Write a 2-3 sentence narrative connecting: RS rank, setup quality, market context, and the single most important prerequisite before entry.

STEP 8 — Output the JSON below (chain_of_thought MUST be the first field):

Required JSON output format (all prices in {currency}):
{{
  "chain_of_thought": "<3-4 sentences: trend alignment, RS vs benchmark, S/R levels, conviction + pattern stage>",

  "technical_analysis": {{
    "entry_price": <number>,
    "entry_type": "<current | breakout>",
    "stop_loss": <number>,
    "atr_stop_check": "<valid | violated>",
    "pivot_level": <number or null>,
    "key_support": [<number>, ...],
    "key_resistance": [<number>, ...],
    "pattern_stage": "<pre-vcp | developing | entry-ready | extended>"
  }},

  "scale_out_targets": [
    {{"label": "T1 (1R)", "price": <number>, "share_pct": 40}},
    {{"label": "T2 (2R)", "price": <number>, "share_pct": 35}},
    {{"label": "T3 (3R)", "price": <number>, "share_pct": 25}}
  ],

  "scenarios": [
    {{"name": "Bull Case",  "probability": <0.0-1.0>, "description": "<...>", "target": <number>, "invalidation": "<...>"}},
    {{"name": "Base Case",  "probability": <0.0-1.0>, "description": "<...>", "target": <number>, "invalidation": "<...>"}},
    {{"name": "Bear Case",  "probability": <0.0-1.0>, "description": "<...>", "target": <number>, "invalidation": "<...>"}},
    {{"name": "Breakdown",  "probability": <0.0-1.0>, "description": "<...>", "target": <number>, "invalidation": "<...>"}}
  ],

  "synthesized_score": {{
    "trend_template":   {{"score": <0-10>, "note": "<...>"}},
    "vcp_pattern":      {{"score": <0-10>, "note": "<...>"}},
    "volume_profile":   {{"score": <0-10>, "note": "<...>"}},
    "rs_strength":      {{"score": <0-10>, "note": "<...>"}},
    "breadth_context":  {{"score": <0-10>, "note": "<...>"}},
    "weekly_alignment": {{"score": <0-10>, "note": "<...>"}},
    "total": <sum of 6 scores>
  }},

  "execution_checklist": {{
    "prerequisites": ["<what must be true before entry>", ...],
    "entry_triggers": ["<specific trigger conditions>", ...],
    "invalidation_conditions": ["<conditions that cancel the setup>", ...]
  }},

  "final_recommendation": {{
    "verdict": "<Strong Buy | Buy | Watch | Avoid>",
    "action": "<specific action sentence>",
    "conviction": "<high | medium | low>",
    "narrative": "<2-3 sentence holistic story connecting RS rank, setup quality, and market context>"
  }},

  "entry_price": <mirrors technical_analysis.entry_price>,
  "entry_rationale": "<1-2 sentences>",
  "stop_loss": <mirrors technical_analysis.stop_loss>,
  "stop_rationale": "<1 sentence confirming ATR minimum of {min_stop_distance}>",
  "target": <mirrors scale_out_targets[1].price — base case T2>,
  "target_rationale": "<1 sentence>",
  "risk_reward_ratio": <target distance / stop distance>,
  "bullish_probability": <computed decimal 0.0-1.0 from Step 6>,
  "key_triggers": [<3-5 strings — what must happen for this trade to work>],
  "caveats": [<2-4 strings — key risks and invalidation conditions>],
  "setup_quality": "<A | B | C — A=high conviction VCP breakout, B=good Stage2, C=borderline>",
  "trend_context": "<daily + weekly trend alignment assessment>",
  "volume_context": "<accumulation/distribution day analysis + dry-up assessment>",
  "market_breadth_context": "<how market breadth affects this trade's probability>"
}}

Hard Rules:
1. entry_price must be above current price (buy stop / break above resistance)
2. stop_loss MUST respect ATR minimum: stop_loss <= entry_price - {min_stop_distance}
3. target (T2) must give risk:reward >= 2:1
4. scale_out_targets share_pct values must sum to exactly 100
5. scenarios probabilities must sum to exactly 1.0
6. synthesized_score.total must equal the sum of the 6 dimension scores
7. bullish_probability must be a computed decimal, not a rounded default
8. All monetary values must be in {currency}
9. No margin: the full position (shares × entry_price) must fit within {currency_sym}{portfolio_size:,.2f}.
   If a tight stop would require more capital than the account holds, widen the stop to a more
   structural support level so the position size is naturally reduced.
"""


def _format_weekly(weekly: Optional[Dict[str, Any]]) -> str:
    if not weekly:
        return "=== WEEKLY TIMEFRAME ===\n  Weekly data unavailable."
    return f"""=== WEEKLY TIMEFRAME (multi-timeframe confluence) ===
  - Weekly Close:    {weekly.get('weekly_close', 'N/A')}
  - Weekly MA10 (10-week ≈ 50d): {weekly.get('weekly_ma10', 'N/A')}
  - Weekly MA20 (20-week ≈ 100d): {weekly.get('weekly_ma20', 'N/A')}
  - Weekly RSI-14:   {weekly.get('weekly_rsi14', 'N/A')}
  - Weekly ATR-14:   {weekly.get('weekly_atr14', 'N/A')}
  - Weekly Trend:    {weekly.get('weekly_trend', 'unknown').upper()}
    (uptrend = close > WMA10 > WMA20; downtrend = close < WMA10 < WMA20; sideways = mixed)"""


def _format_volume_profile(indicators: Dict[str, Any]) -> str:
    accum = indicators.get("accum_days_20")
    distrib = indicators.get("distrib_days_20")
    dry_up = indicators.get("vol_dry_up")
    dry_up_ratio = indicators.get("vol_dry_up_ratio")

    if accum is None:
        return "=== VOLUME ACCUMULATION/DISTRIBUTION ===\n  Volume profile data unavailable."

    if accum > (distrib or 0) + 2:
        bias = "ACCUMULATION BIAS (bullish)"
    elif (distrib or 0) > accum + 2:
        bias = "DISTRIBUTION BIAS (bearish)"
    else:
        bias = "BALANCED (no clear institutional direction)"

    dry_up_str = "YES — volume compression detected (potential breakout setup)" if dry_up else "No"
    ratio_str = f"{dry_up_ratio:.2f} (10d/50d avg)" if dry_up_ratio is not None else "N/A"

    return f"""=== VOLUME ACCUMULATION/DISTRIBUTION (last 20 sessions) ===
  - Accumulation days (up + above-avg vol): {accum}
  - Distribution days (down + above-avg vol): {distrib}
  - Net bias: {bias}
  - Volume dry-up ratio (10d vs 50d avg): {ratio_str}
  - Volume dry-up (last 3 sessions < 60% avg): {dry_up_str}"""


def _format_rs(rs: Optional[Dict[str, Any]], market: str) -> str:
    if not rs or rs.get("error"):
        reason = (rs or {}).get("error", "not available")
        return f"=== RELATIVE STRENGTH vs BENCHMARK ===\n  RS data unavailable: {reason}"

    benchmark = rs.get("benchmark_used", "SPY")
    rs_63 = rs.get("rs_63")
    rs_126 = rs.get("rs_126")
    rs_189 = rs.get("rs_189")
    composite = rs.get("rs_composite")
    rank = rs.get("rs_rank_pct")

    def fmt(v: Optional[float]) -> str:
        return f"{v:+.1f}%" if v is not None else "N/A"

    rank_str = f"{rank:.0f}/100" if rank is not None else "not computed"

    return f"""=== RELATIVE STRENGTH vs BENCHMARK ({benchmark}) ===
  - RS 63-day  (3mo excess return vs {benchmark}): {fmt(rs_63)}
  - RS 126-day (6mo excess return vs {benchmark}): {fmt(rs_126)}
  - RS 189-day (9mo excess return vs {benchmark}): {fmt(rs_189)}
  - RS Composite (weighted: 40/35/25):            {fmt(composite)}
  - RS Rank (percentile vs watchlist universe):   {rank_str}
    (RS Rank 80+ = top-tier leadership; 50-80 = above average; <50 = lagging)"""


def _format_breadth(breadth: Dict[str, Any], market: str) -> str:
    if not breadth.get("available"):
        return f"=== MARKET BREADTH ===\n  {breadth.get('note', 'Not available')}"

    if market.upper() == "TASE":
        components_note = breadth.get("note", "")
        return f"""=== MARKET BREADTH (TA-35 Components above MA50) ===
  - Components checked: {breadth.get('components_checked', 'N/A')}
  - Above MA50: {breadth.get('components_above_ma50', 'N/A')} ({components_note})
  - Overall ratio: {breadth.get('overall_ratio', 'N/A')}
  - Zone: {breadth.get('zone', 'N/A')}
    (Bullish >60%, Neutral 40-60%, Bearish <40%)"""

    sector_lines = ""
    for s in (breadth.get("sectors") or [])[:5]:
        sector_lines += (
            f"  - {s['sector']}: ratio={s.get('ratio', 'N/A')}, "
            f"trend={s.get('trend', '?')}, status={s.get('status', '?')}\n"
        )

    return f"""=== MARKET BREADTH (Monty's Uptrend Dashboard) ===
  - Overall uptrend ratio: {breadth.get('overall_ratio', 'N/A')}
  - Trend: {breadth.get('overall_trend', 'N/A')}
  - Composite score: {breadth.get('composite_score', 'N/A')} / 100
  - Zone: {breadth.get('zone', 'N/A')}
  Top sectors by uptrend ratio:
{sector_lines}"""
