"""
Scanner Service for Symbol Screening.

Fetches market data via yfinance and applies screening filters.
Supports US (S&P 500, Nasdaq) and TASE markets.
"""

import yfinance as yf
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ScannerService:
    """Symbol scanning and filtering service."""

    def __init__(self):
        self.us_symbols: Optional[List[str]] = None
        self.tase_symbols: Optional[List[str]] = None

    async def load_symbols(self, market: str) -> List[str]:
        """Load valid symbols for market."""
        if market == "US" and self.us_symbols is None:
            # TODO: Load from CSV or S&P 500 list
            self.us_symbols = []
        elif market == "TASE" and self.tase_symbols is None:
            # TODO: Load from CSV or TASE list
            self.tase_symbols = []

        return self.us_symbols if market == "US" else self.tase_symbols

    async def fetch_market_data(
        self,
        symbols: List[str],
        period: str = "3mo",
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLC and volume data for symbols via yfinance.

        Returns:
        - Dict mapping symbol to DataFrame with OHLC data
        """
        data = {}

        for i, symbol in enumerate(symbols):
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)

                if hist.empty:
                    logger.warning(f"No data found for symbol: {symbol}")
                    continue

                data[symbol] = hist
                logger.info(f"Fetched data for {symbol}")

                if progress_callback:
                    progress_callback((i + 1) / len(symbols))

            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                continue

        return data

    def apply_filters(
        self,
        data: Dict[str, pd.DataFrame],
        min_price: float = 5.0,
        max_price: float = 1000.0,
        min_volume: int = 100000,
        min_volatility: float = 0.01,
    ) -> List[Dict[str, Any]]:
        """
        Apply screening filters to symbol data.

        Filters:
        - Price range
        - Volume threshold
        - Volatility range

        Returns:
        - List of candidates with scores
        """
        candidates = []

        for symbol, df in data.items():
            try:
                latest = df.iloc[-1]
                price = latest["Close"]
                volume = latest["Volume"]
                volatility = df["Close"].pct_change().std()

                # Apply filters
                if price < min_price or price > max_price:
                    continue
                if volume < min_volume:
                    continue
                if volatility < min_volatility:
                    continue

                # Compute screening score
                score = self._compute_score(df, price, volume, volatility)

                candidates.append({
                    "symbol": symbol,
                    "price": float(price),
                    "volume": float(volume),
                    "volatility": float(volatility),
                    "screening_score": score,
                })

            except Exception as e:
                logger.error(f"Error filtering symbol {symbol}: {e}")
                continue

        # Sort by score
        candidates.sort(key=lambda x: x["screening_score"], reverse=True)
        return candidates

    def _compute_score(self, df: pd.DataFrame, price: float, volume: float, volatility: float) -> float:
        """Compute screening score for symbol (simple formula)."""
        # TODO: Implement sophisticated scoring
        return volatility * 100
