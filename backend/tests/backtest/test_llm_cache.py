from datetime import date
from pathlib import Path
import pytest
from scripts.backtest.llm_cache import LLMCache


SIGNAL_DATE = date(2025, 6, 15)
WORKFLOW = "technical-swing"
SYMBOL = "OPCE"

SAMPLE_TICKET = {
    "entry_price": 412.0,
    "entry_type": "breakout",
    "stop_loss": 385.0,
    "t1": 445.0,
    "t2": 480.0,
    "t3": 520.0,
    "verdict": "Strong Buy",
    "setup_score": 42,
    "entry_rationale": "Tight VCP above MA200",
}


def test_cache_miss_returns_none(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    assert cache.get(SYMBOL, SIGNAL_DATE, WORKFLOW) is None


def test_store_and_retrieve(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    result = cache.get(SYMBOL, SIGNAL_DATE, WORKFLOW)
    assert result == SAMPLE_TICKET


def test_cache_persists_across_instances(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache1 = LLMCache(cache_file=cache_file)
    cache1.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    cache2 = LLMCache(cache_file=cache_file)
    assert cache2.get(SYMBOL, SIGNAL_DATE, WORKFLOW) == SAMPLE_TICKET


def test_cache_key_format(tmp_path):
    """Key must be {symbol}_{YYYY-MM-DD}_{workflow}."""
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    import json
    data = json.loads((tmp_path / "cache.json").read_text())
    expected_key = "OPCE_2025-06-15_technical-swing"
    assert expected_key in data


def test_different_workflows_different_keys(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store(SYMBOL, SIGNAL_DATE, "technical-swing", {"entry_price": 412.0})
    cache.store(SYMBOL, SIGNAL_DATE, "mean-reversion-bounce", {"entry_price": 400.0})
    swing = cache.get(SYMBOL, SIGNAL_DATE, "technical-swing")
    mr = cache.get(SYMBOL, SIGNAL_DATE, "mean-reversion-bounce")
    assert swing["entry_price"] == 412.0
    assert mr["entry_price"] == 400.0


def test_no_cache_flag_always_returns_none(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json", no_cache=True)
    cache.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    assert cache.get(SYMBOL, SIGNAL_DATE, WORKFLOW) is None
