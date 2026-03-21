"""
Market breadth analysis ported from uptrend-analyzer skill.

US markets: Downloads Monty's Uptrend Ratio Dashboard CSV data (no API key required).
TASE markets: Batch-fetches TA-35 components via yfinance and computes % above MA50.
"""

import csv
import io
import logging
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ── TASE breadth: TA-35 representative components ─────────────────────────────
# Used as a proxy for the TA-35 index. Missing/invalid symbols are silently skipped.
TA35_COMPONENTS = [
    # Banks & Insurance
    "HARL", "FIBI", "DSCT", "POLI", "LUMI", "MIZR",
    # Tech (most dual-listed on NASDAQ + TASE)
    "NICE", "CHKP", "NOVA", "CEVA", "INMD", "PERI", "MNDO", "MZTF",
    # Defense / Aerospace
    "ESLT",
    # Pharma
    "TEVA",
    # Energy / Infra
    "ENLT", "ORL",
    # Telecom / Real Estate
    "BEZQ", "AMOT", "ALHE", "IGLD", "KMNK",
    # Other large-caps
    "SPRX", "FNTS",
]
TASE_BREADTH_BULL = 0.60  # > 60% above MA50 → Bullish
TASE_BREADTH_BEAR = 0.40  # < 40% above MA50 → Bearish

TIMESERIES_URL = (
    "https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/"
    "main/data/uptrend_ratio_timeseries.csv"
)

OVERBOUGHT_THRESHOLD = 0.37
OVERSOLD_THRESHOLD = 0.097

SECTOR_DISPLAY = {
    "sec_basicmaterials": "Basic Materials",
    "sec_communicationservices": "Communication Services",
    "sec_consumercyclical": "Consumer Cyclical",
    "sec_consumerdefensive": "Consumer Defensive",
    "sec_energy": "Energy",
    "sec_financial": "Financial",
    "sec_healthcare": "Healthcare",
    "sec_industrials": "Industrials",
    "sec_realestate": "Real Estate",
    "sec_technology": "Technology",
    "sec_utilities": "Utilities",
}

# Scoring weights (matching uptrend-analyzer scorer.py)
COMPONENT_WEIGHTS = {
    "market_breadth": 0.30,
    "sector_participation": 0.25,
    "momentum": 0.20,
    "sector_rotation": 0.15,
    "historical_context": 0.10,
}


def get_market_breadth(market: str) -> dict:
    """
    Return market breadth summary for the given market.

    For US: fetches Monty's uptrend ratio data and computes a composite score.
    For TASE: returns a neutral stub (no equivalent free data source).

    Returns:
        {
          "available": bool,
          "market": str,
          "overall_ratio": float | None,
          "overall_trend": str,
          "composite_score": float | None,
          "zone": str,
          "sectors": [...],
          "note": str,
        }
    """
    if market.upper() == "TASE":
        return get_tase_breadth()

    try:
        rows = _fetch_timeseries()
    except Exception as e:
        logger.warning(f"Failed to fetch breadth data: {e}")
        return _neutral_us_stub(str(e))

    if not rows:
        return _neutral_us_stub("Empty timeseries response")

    # Overall breadth (worksheet == "all")
    all_rows = sorted(
        [r for r in rows if r["worksheet"] == "all"],
        key=lambda x: x["date"],
    )
    latest_all = all_rows[-1] if all_rows else None

    # Sector latest values
    sector_latest: dict[str, dict] = {}
    for row in rows:
        ws = row["worksheet"]
        if ws == "all":
            continue
        if ws not in sector_latest or row["date"] > sector_latest[ws]["date"]:
            sector_latest[ws] = row

    overall_ratio = latest_all["ratio"] if latest_all else None
    overall_trend = (latest_all.get("trend") or "").capitalize() if latest_all else "Unknown"

    # Build sector summary list
    sectors = []
    for ws, row in sector_latest.items():
        ratio = row.get("ratio")
        status = (
            "Overbought"
            if ratio is not None and ratio > OVERBOUGHT_THRESHOLD
            else "Oversold"
            if ratio is not None and ratio < OVERSOLD_THRESHOLD
            else "Normal"
        )
        sectors.append(
            {
                "sector": SECTOR_DISPLAY.get(ws, ws),
                "ratio": ratio,
                "ma10": row.get("ma_10"),
                "trend": (row.get("trend") or "").capitalize(),
                "status": status,
            }
        )
    sectors.sort(key=lambda s: s["ratio"] or 0, reverse=True)

    # Compute composite score
    composite = _compute_composite(overall_ratio, all_rows, sector_latest)
    zone = _score_to_zone(composite)

    return {
        "available": True,
        "market": "US",
        "overall_ratio": overall_ratio,
        "overall_trend": overall_trend,
        "composite_score": composite,
        "zone": zone,
        "sectors": sectors,
        "note": "",
    }


def get_tase_breadth() -> dict:
    """
    Compute TASE market breadth using TA-35 representative components.

    Batch-fetches 3 months of daily OHLC for each component via yfinance,
    then calculates the percentage of stocks currently trading above their MA50.

    Returns same schema as get_market_breadth() for US.
    """
    symbols = [f"{s}.TA" for s in TA35_COMPONENTS]
    logger.info(f"[tase_breadth] Fetching {len(symbols)} TA-35 components")

    try:
        raw = yf.download(
            symbols,
            period="3mo",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        logger.warning(f"[tase_breadth] yfinance batch fetch failed: {e}")
        return _neutral_tase_stub(str(e))

    if raw.empty:
        return _neutral_tase_stub("No data returned from yfinance")

    above_ma50 = 0
    valid = 0

    for sym in symbols:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw["Close"][sym].dropna()
            else:
                # Single ticker fallback (shouldn't happen with a list, but safe)
                close = raw["Close"].dropna()

            if len(close) < 50:
                continue

            ma50_val = close.rolling(50).mean().iloc[-1]
            current = float(close.iloc[-1])
            if pd.isna(ma50_val) or pd.isna(current):
                continue

            valid += 1
            if current > float(ma50_val):
                above_ma50 += 1

        except (KeyError, TypeError, IndexError):
            continue

    if valid == 0:
        return _neutral_tase_stub("Insufficient data for TA-35 components")

    ratio = above_ma50 / valid
    if ratio > TASE_BREADTH_BULL:
        zone = "Bullish"
    elif ratio < TASE_BREADTH_BEAR:
        zone = "Bearish"
    else:
        zone = "Neutral"

    logger.info(
        f"[tase_breadth] {above_ma50}/{valid} components above MA50 "
        f"({ratio:.1%}) → {zone}"
    )

    return {
        "available": True,
        "market": "TASE",
        "overall_ratio": round(ratio, 3),
        "overall_trend": zone,
        "composite_score": round(ratio * 100, 1),
        "zone": zone,
        "sectors": [],
        "note": f"{above_ma50}/{valid} TA-35 components above MA50",
        "components_checked": valid,
        "components_above_ma50": above_ma50,
    }


def _neutral_tase_stub(note: str) -> dict:
    return {
        "available": False,
        "market": "TASE",
        "overall_ratio": None,
        "overall_trend": "Unknown",
        "composite_score": None,
        "zone": "Neutral",
        "sectors": [],
        "note": f"TASE breadth unavailable: {note}. Proceeding with neutral assumption.",
    }


# ── private helpers ────────────────────────────────────────────────────────────


def _fetch_timeseries() -> list:
    resp = requests.get(TIMESERIES_URL, timeout=30)
    resp.raise_for_status()
    rows = []
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        try:
            parsed = {
                "worksheet": row.get("worksheet", "").strip(),
                "date": row.get("date", "").strip(),
                "ratio": _safe_float(row.get("ratio")),
                "ma_10": _safe_float(row.get("ma_10")),
                "slope": _safe_float(row.get("slope")),
                "trend": row.get("trend", "").strip(),
                "count": _safe_int(row.get("count")),
                "total": _safe_int(row.get("total")),
            }
            if parsed["worksheet"] and parsed["date"]:
                rows.append(parsed)
        except Exception:
            continue
    return rows


def _compute_composite(
    overall_ratio: Optional[float],
    all_rows: list,
    sector_latest: dict,
) -> Optional[float]:
    """Simplified composite score (0-100) derived from breadth data."""
    if overall_ratio is None:
        return None

    # Market breadth score (0-100): ratio → score
    breadth_score = min(100, max(0, overall_ratio * 200))

    # Momentum: is ratio above MA10?
    momentum_score = 50.0
    if all_rows:
        latest = all_rows[-1]
        if latest.get("ma_10") is not None and latest.get("ratio") is not None:
            if latest["ratio"] > latest["ma_10"]:
                momentum_score = 75.0
            elif latest["ratio"] < latest["ma_10"]:
                momentum_score = 25.0

    # Sector participation: % of sectors with ratio > 0.20
    participation_score = 50.0
    if sector_latest:
        above = sum(1 for r in sector_latest.values() if (r.get("ratio") or 0) > 0.20)
        participation_score = above / len(sector_latest) * 100

    # Sector rotation: % of sectors trending up
    rotation_score = 50.0
    if sector_latest:
        up = sum(
            1 for r in sector_latest.values() if (r.get("trend") or "").lower() == "up"
        )
        rotation_score = up / len(sector_latest) * 100

    # Historical context: fixed neutral since we don't track long history
    history_score = 50.0

    composite = (
        breadth_score * COMPONENT_WEIGHTS["market_breadth"]
        + participation_score * COMPONENT_WEIGHTS["sector_participation"]
        + momentum_score * COMPONENT_WEIGHTS["momentum"]
        + rotation_score * COMPONENT_WEIGHTS["sector_rotation"]
        + history_score * COMPONENT_WEIGHTS["historical_context"]
    )
    return round(composite, 1)


def _score_to_zone(score: Optional[float]) -> str:
    if score is None:
        return "Neutral"
    if score >= 80:
        return "Strong Bull"
    if score >= 60:
        return "Bull"
    if score >= 40:
        return "Neutral"
    if score >= 20:
        return "Cautious"
    return "Bear"


def _neutral_us_stub(note: str) -> dict:
    return {
        "available": False,
        "market": "US",
        "overall_ratio": None,
        "overall_trend": "Unknown",
        "composite_score": None,
        "zone": "Neutral",
        "sectors": [],
        "note": f"Breadth data unavailable: {note}. Proceeding with neutral assumption.",
    }


def _safe_float(value) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> Optional[int]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None
