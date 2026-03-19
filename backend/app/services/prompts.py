"""
LLM prompts for the technical-swing workflow.

Combines adapted frameworks from:
  - technical-analyst (OHLC trend + S/R analysis)
  - vcp-screener (Minervani VCP methodology)
  - uptrend-analyzer (market breadth context)
  - position-sizer (entry/exit discipline)

Output schema enforced via JSON mode.
"""

from typing import Dict, Any, Optional


SYSTEM_PROMPT = """You are a professional swing trader and technical analyst.
You analyze stocks using Minervini's Trend Template (Stage 2), VCP methodology, and market breadth data.
You output structured JSON trade plans with explicit entry, stop-loss, and target levels.
You are precise, disciplined, and risk-aware. You never recommend trades that violate Stage 2 criteria.
All prices must be in the correct currency for the market (USD for US, ILS/NIS for TASE).
"""


def build_research_prompt(
    symbol: str,
    market: str,
    indicators: Dict[str, Any],
    pre_screen_result,  # PreScreenResult
    breadth: Dict[str, Any],
    portfolio_size: float,
    max_risk_pct: float,
    period_candles: int = 252,
) -> str:
    """
    Build the combined research prompt for LLM analysis.

    Returns a prompt string that produces a JSON trade plan.
    """
    currency = "ILS (NIS)" if market.upper() == "TASE" else "USD"
    currency_sym = "₪" if market.upper() == "TASE" else "$"
    market_label = "Tel Aviv Stock Exchange (TASE)" if market.upper() == "TASE" else "US Stock Market (NYSE/Nasdaq)"
    exchange_note = (
        "Trading hours: 9:15–17:00 Israel Time (Sunday–Thursday). Prices in NIS."
        if market.upper() == "TASE"
        else "Trading hours: 9:30–16:00 ET (Monday–Friday). Prices in USD."
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
    ma200_trend = "Yes" if indicators.get("ma200_trending_up") else "No"

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

    breadth_section = _format_breadth(breadth, market)

    account_risk = round(portfolio_size * max_risk_pct / 100, 2)

    return f"""Analyze {symbol} for a swing trade entry on the {market_label}.
{exchange_note}

Portfolio context:
  - Account size: {currency_sym}{portfolio_size:,.2f} {currency}
  - Max risk per trade: {max_risk_pct}% = {currency_sym}{account_risk:,.2f} {currency}

Technical Indicators (latest session):
  - Price:      {price}
  - MA20:       {ma20}
  - MA50:       {ma50}
  - MA150:      {ma150}
  - MA200:      {ma200}
  - MA200 Trending Up (22 sessions): {ma200_trend}
  - ATR-14:     {atr14}
  - RSI-14:     {rsi14}
  - 52-week High: {high_52w}
  - 52-week Low:  {low_52w}
  - Avg Volume (50-day): {avg_vol}

Minervini Stage 2 Trend Template Checks:
{stage2_checks}
Pre-screen result: {pre_screen_result.summary}

{vcp_section}

{breadth_section}

Based on this data, produce a complete swing trade plan in JSON.

Required JSON output format (all prices in {currency}):
{{
  "entry_price": <number — specific level to enter, e.g. break above pivot or key MA>,
  "entry_rationale": "<1-2 sentences explaining WHY this entry level>,
  "stop_loss": <number — hard stop below key support>,
  "stop_rationale": "<1 sentence — why this is the stop level>",
  "target": <number — primary price target based on resistance/prior highs>,
  "target_rationale": "<1 sentence>",
  "risk_reward_ratio": <number — target distance / stop distance>,
  "bullish_probability": <number 0.0–1.0 — your confidence in this setup>,
  "key_triggers": [<list of 3–5 strings — what must happen for this trade to work>],
  "caveats": [<list of 2–4 strings — key risks and invalidation conditions>],
  "setup_quality": "<A/B/C — A=high conviction VCP breakout, B=good Stage2, C=borderline>",
  "trend_context": "<brief assessment of the trend structure and momentum>",
  "volume_context": "<brief assessment of volume patterns>",
  "market_breadth_context": "<how market breadth affects this trade's probability>"
}}

Rules:
1. Entry must be above current price (buy stop / break above resistance)
2. Stop must be below key support (do not risk more than {max_risk_pct}% of account)
3. Target must give risk:reward >= 2:1
4. If Stage 2 checks are mostly failing, set bullish_probability < 0.40
5. All monetary values must be in {currency}
"""


def _format_breadth(breadth: Dict[str, Any], market: str) -> str:
    if not breadth.get("available"):
        return f"Market Breadth:\n  {breadth.get('note', 'Not available')}"

    sector_lines = ""
    for s in (breadth.get("sectors") or [])[:5]:
        sector_lines += (
            f"  - {s['sector']}: ratio={s.get('ratio', 'N/A')}, "
            f"trend={s.get('trend', '?')}, status={s.get('status', '?')}\n"
        )

    return f"""Market Breadth (Monty's Uptrend Dashboard):
  - Overall uptrend ratio: {breadth.get('overall_ratio', 'N/A')}
  - Trend: {breadth.get('overall_trend', 'N/A')}
  - Composite score: {breadth.get('composite_score', 'N/A')} / 100
  - Zone: {breadth.get('zone', 'N/A')}
  Top sectors by uptrend ratio:
{sector_lines}"""
