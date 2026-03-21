"""
Scanner Service — fetches OHLC via yfinance, applies screener filters.
Symbol universe comes from the watchlist_items table (not CSV files).
"""

import yfinance as yf
import pandas as pd
from typing import Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Market-aware filter defaults.
# All thresholds are RELATIVE to the stock's own history — no absolute volume/volatility.
MARKET_DEFAULTS = {
    "US": {
        "min_price": 5.0,      # loose safety rail: filter sub-penny stocks
        "max_price": 2000.0,   # loose upper rail
        "min_rvol": 0.5,       # today's vol >= 50% of own 20d avg (actively trading)
        "min_atr_pct": 0.5,    # ATR-14 >= 0.5% of price (avoids flat/dead stocks)
    },
    "TASE": {
        "min_price": 1.0,
        "max_price": 2000.0,
        "min_rvol": 0.3,       # TASE lower baseline liquidity — more relaxed
        "min_atr_pct": 0.3,    # TASE smaller ATR% threshold
    },
}


def _yf_symbol(symbol: str, market: str) -> str:
    if market == "TASE" and not symbol.endswith(".TA"):
        return f"{symbol}.TA"
    return symbol


class ScannerService:
    """Symbol scanning and filtering service."""

    async def load_symbols(
        self, market: str, db, watchlist_id: str | None = None
    ) -> list[str]:
        """
        Load scan universe from watchlist_items for the given market.
        If watchlist_id is provided, only symbols from that list are returned.
        """
        query = db.table("watchlist_items").select("symbol").eq("market", market)
        if watchlist_id:
            query = query.eq("watchlist_id", watchlist_id)
        result = query.execute()
        symbols = [row["symbol"] for row in result.data]
        scope = f"watchlist={watchlist_id}" if watchlist_id else "all watchlists"
        logger.info(f"Loaded {len(symbols)} symbols for market={market} ({scope})")
        return symbols

    async def fetch_market_data(
        self,
        symbols: list[str],
        market: str,
        period: str = "1mo",
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch OHLC + volume for a list of symbols via yfinance.
        Applies .TA suffix for TASE symbols automatically.
        TASE prices from yfinance are in agorot (1/100 ILS) — converted here.
        """
        data: dict[str, pd.DataFrame] = {}
        is_tase = market.upper() == "TASE"

        for symbol in symbols:
            yf_sym = _yf_symbol(symbol, market)
            try:
                ticker = yf.Ticker(yf_sym)
                hist = ticker.history(period=period, auto_adjust=True)

                if hist.empty:
                    logger.warning(f"No data for {yf_sym} — skipping")
                    continue

                # Convert agorot → ILS for TASE
                if is_tase:
                    for col in ("Open", "High", "Low", "Close"):
                        if col in hist.columns:
                            hist[col] = hist[col] / 100.0

                data[symbol] = hist
            except Exception as e:
                logger.error(f"yfinance error for {yf_sym}: {e}")

        logger.info(f"Fetched data for {len(data)}/{len(symbols)} symbols")
        return data

    def apply_filters(
        self,
        data: dict[str, pd.DataFrame],
        market: str,
        min_price: float | None = None,
        max_price: float | None = None,
        min_rvol: float | None = None,
        min_atr_pct: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Apply market-aware screener filters using RELATIVE metrics.

        All thresholds compare a stock against its own history:
        - RVOL (Relative Volume): today vs its own 20d average — no cross-stock bias
        - ATR% (ATR-14 as % of price): volatility normalised to price level
        Price range is kept as a loose safety rail only (filters sub-penny/extreme instruments).
        """
        defaults = MARKET_DEFAULTS.get(market, MARKET_DEFAULTS["US"])
        min_price = min_price if min_price is not None else defaults["min_price"]
        max_price = max_price if max_price is not None else defaults["max_price"]
        min_rvol = min_rvol if min_rvol is not None else defaults["min_rvol"]
        min_atr_pct = min_atr_pct if min_atr_pct is not None else defaults["min_atr_pct"]

        candidates = []
        rejections: dict[str, str] = {}

        for symbol, df in data.items():
            try:
                latest = df.iloc[-1]
                price = float(latest["Close"])
                volume = float(latest["Volume"])

                # ── Safety rails (price only) ────────────────────────────────────
                if price < min_price or price > max_price:
                    rejections[symbol] = f"price {price:.2f} outside [{min_price}, {max_price}]"
                    continue

                # ── Relative Volume ───────────────────────────────────────────────
                avg_vol_20 = float(df["Volume"].tail(20).mean())
                rvol = volume / avg_vol_20 if avg_vol_20 > 0 else 0.0
                if rvol < min_rvol:
                    rejections[symbol] = (
                        f"RVOL {rvol:.2f} < {min_rvol} (trading below own avg volume)"
                    )
                    continue

                # ── ATR as % of price ─────────────────────────────────────────────
                atr_pct = self._compute_atr_pct(df, price)
                if atr_pct < min_atr_pct:
                    rejections[symbol] = (
                        f"ATR% {atr_pct:.3f}% < {min_atr_pct}% (price range too flat)"
                    )
                    continue

                score = self._compute_score(rvol, atr_pct)
                candidates.append({
                    "symbol": symbol,
                    "market": market,
                    "price": round(price, 4),
                    "volume": int(volume),
                    "score": round(score, 4),
                    "screened_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {
                        "rvol": round(rvol, 2),
                        "atr_pct": round(atr_pct, 3),
                    },
                })

            except Exception as e:
                logger.error(f"Filter error for {symbol}: {e}")

        if rejections:
            logger.info(f"Rejected {len(rejections)} symbols: {rejections}")

        candidates.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Screener: {len(candidates)} passed / {len(data)} fetched")
        return candidates

    def _compute_atr_pct(self, df: pd.DataFrame, price: float) -> float:
        """Compute ATR-14 as % of current price (volatility normalised to price level)."""
        if len(df) < 15:
            return 0.0
        high = df["High"]
        low = df["Low"]
        prev_close = df["Close"].shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = float(tr.ewm(span=14, min_periods=14, adjust=False).mean().iloc[-1])
        return (atr / price * 100) if price > 0 else 0.0

    def _compute_score(self, rvol: float, atr_pct: float) -> float:
        """
        Composite relative score — both inputs are already normalised to the
        stock's own history, so this score is market-agnostic.

        RVOL capped at 3× to avoid overnight gaps dominating the score.
        ATR% weighted equally with RVOL.
        """
        return (min(rvol, 3.0) * 10) + (atr_pct * 10)
