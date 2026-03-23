"""JSON-backed cache for raw LLM results. Keyed by symbol + signal_date + workflow."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_FILE = Path(__file__).parent / "cache" / "llm_cache.json"


class LLMCache:
    def __init__(
        self,
        cache_file: Path = DEFAULT_CACHE_FILE,
        no_cache: bool = False,
    ) -> None:
        self._file = Path(cache_file)
        self._no_cache = no_cache
        self._data: Dict[str, Any] = {}
        if not self._no_cache and self._file.exists():
            try:
                self._data = json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("LLM cache load failed (%s) — starting fresh", exc)

    @staticmethod
    def _key(symbol: str, signal_date: date, workflow: str) -> str:
        return f"{symbol}_{signal_date.strftime('%Y-%m-%d')}_{workflow}"

    def get(self, symbol: str, signal_date: date, workflow: str) -> Optional[Dict[str, Any]]:
        if self._no_cache:
            return None
        return self._data.get(self._key(symbol, signal_date, workflow))

    def store(self, symbol: str, signal_date: date, workflow: str, data: Dict[str, Any]) -> None:
        key = self._key(symbol, signal_date, workflow)
        self._data[key] = data
        if not self._no_cache:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(self._data, indent=2, default=str),
                encoding="utf-8",
            )
