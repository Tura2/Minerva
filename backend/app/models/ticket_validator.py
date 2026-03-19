"""
Pydantic validator for research ticket output.

Validates LLM + sizing output BEFORE writing to DB.
Raises ValidationError with field-level details on failure.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator


class TicketOutputValidator(BaseModel):
    """Strict validation of research ticket fields before DB persist."""

    entry_price: float = Field(..., gt=0, description="Entry price must be positive")
    stop_loss: float = Field(..., gt=0, description="Stop loss must be positive")
    target: float = Field(..., gt=0, description="Target must be positive")
    risk_reward_ratio: float = Field(..., ge=1.0, description="R/R must be >= 1.0")
    bullish_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Probability must be in [0.0, 1.0]"
    )
    position_size: int = Field(..., gt=0, description="Position size must be positive")
    key_triggers: List[str] = Field(..., min_length=1, description="Must have at least one trigger")

    @model_validator(mode="after")
    def validate_price_hierarchy(self) -> "TicketOutputValidator":
        """For long setups: stop_loss < entry_price < target."""
        if self.stop_loss >= self.entry_price:
            raise ValueError(
                f"stop_loss ({self.stop_loss}) must be less than entry_price ({self.entry_price})"
            )
        if self.target <= self.entry_price:
            raise ValueError(
                f"target ({self.target}) must be greater than entry_price ({self.entry_price})"
            )
        return self

    @field_validator("key_triggers")
    @classmethod
    def triggers_not_empty_strings(cls, v: List[str]) -> List[str]:
        filtered = [t.strip() for t in v if t.strip()]
        if not filtered:
            raise ValueError("key_triggers must contain at least one non-empty string")
        return filtered
