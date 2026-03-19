"""Unit tests for TicketOutputValidator."""

import pytest
from pydantic import ValidationError

from app.models.ticket_validator import TicketOutputValidator

VALID = {
    "entry_price": 100.0,
    "stop_loss": 90.0,
    "target": 120.0,
    "risk_reward_ratio": 2.0,
    "bullish_probability": 0.72,
    "position_size": 50,
    "key_triggers": ["breakout above resistance", "volume surge"],
}


def test_valid_ticket_passes():
    v = TicketOutputValidator(**VALID)
    assert v.entry_price == 100.0
    assert v.position_size == 50


def test_stop_equals_entry_fails():
    with pytest.raises(ValidationError) as exc_info:
        TicketOutputValidator(**{**VALID, "stop_loss": 100.0})
    assert "stop_loss" in str(exc_info.value)


def test_stop_above_entry_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "stop_loss": 105.0})


def test_target_equals_entry_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "target": 100.0})


def test_target_below_entry_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "target": 95.0})


def test_negative_position_size_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "position_size": -5})


def test_zero_position_size_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "position_size": 0})


def test_probability_above_one_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "bullish_probability": 1.1})


def test_probability_below_zero_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "bullish_probability": -0.1})


def test_probability_boundary_values_pass():
    TicketOutputValidator(**{**VALID, "bullish_probability": 0.0})
    TicketOutputValidator(**{**VALID, "bullish_probability": 1.0})


def test_empty_key_triggers_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "key_triggers": []})


def test_whitespace_only_triggers_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "key_triggers": ["   ", ""]})


def test_rr_below_one_fails():
    with pytest.raises(ValidationError):
        TicketOutputValidator(**{**VALID, "risk_reward_ratio": 0.9})


def test_rr_exactly_one_passes():
    v = TicketOutputValidator(**{**VALID, "risk_reward_ratio": 1.0})
    assert v.risk_reward_ratio == 1.0
