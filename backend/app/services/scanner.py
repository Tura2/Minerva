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

# Market-aware filter defaults
MARKET_DEFAULTS = {
    "US": {
        "min_price": 5.0,
        "max_price": 2000.0,
        "min_volume": 500_000,
        "min_volatility": 0.008,
    },
    "TASE": {
        # Prices are in ILS (post agorot ÷100 conversion applied in fetch_market_data)
        # TASE stocks typically trade between 1–2000 ILS
        "min_price": 1.0,
        "max_price": 2000.0,
        "min_volume": 30_000,   # TASE is less liquid; lower bar
        "min_volatility": 0.005,
    },
}


def _yf_symbol(symbol: str, market: str) -> str:
    if market == "TASE" and not symbol.endswith(".TA"):
        return f"{symbol}.TA"
    return symbol


class ScannerService:
    """Symbol scanning and filtering service."""

    async def load_symbols(self, market: str, db) -> list[str]:
        """Load scan universe from watchlist_items for the given market."""
        result = db.table("watchlist_items").select("symbol").eq("market", market).execute()
        symbols = [row["symbol"] for row in result.data]
        logger.info(f"Loaded {len(symbols)} symbols from watchlist for market={market}")
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
        min_volume: int | None = None,
        min_volatility: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Apply market-aware screener filters.
        Falls back to market defaults for any unspecified threshold.
        """
        defaults = MARKET_DEFAULTS.get(market, MARKET_DEFAULTS["US"])
        min_price = min_price if min_price is not None else defaults["min_price"]
        max_price = max_price if max_price is not None else defaults["max_price"]
        min_volume = min_volume if min_volume is not None else defaults["min_volume"]
        min_volatility = min_volatility if min_volatility is not None else defaults["min_volatility"]

        candidates = []
        rejections: dict[str, str] = {}

        for symbol, df in data.items():
            try:
                latest = df.iloc[-1]
                price = float(latest["Close"])
                volume = float(latest["Volume"])
                volatility = float(df["Close"].pct_change().std())

                if price < min_price or price > max_price:
                    rejections[symbol] = f"price {price:.2f} outside [{min_price}, {max_price}]"
                    continue
                if volume < min_volume:
                    rejections[symbol] = f"volume {volume:.0f} < {min_volume}"
                    continue
                if volatility < min_volatility:
                    rejections[symbol] = f"volatility {volatility:.4f} < {min_volatility}"
                    continue

                score = self._compute_score(df, price, volume, volatility)
                candidates.append({
                    "symbol": symbol,
                    "market": market,
                    "price": round(price, 4),
                    "volume": int(volume),
                    "score": round(score, 4),
                    "screened_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"volatility": round(volatility, 6)},
                })

            except Exception as e:
                logger.error(f"Filter error for {symbol}: {e}")

        if rejections:
            logger.info(f"Rejected {len(rejections)} symbols: {rejections}")

        candidates.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Screener: {len(candidates)} passed / {len(data)} fetched")
        return candidates

    def _compute_score(self, df: pd.DataFrame, price: float, volume: float, volatility: float) -> float:
        """
        Simple composite score: rewards volatility and relative volume.
        Volume ratio = latest volume / 20-day avg volume.
        """
        avg_volume = df["Close"].tail(20).mean()
        vol_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        return (volatility * 50) + (min(vol_ratio, 3.0) * 10)
