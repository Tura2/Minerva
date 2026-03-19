"""
OpenRouter API Client for LLM Research Integration.

Handles:
- Request construction for adapted skill prompts
- Retry policy (429, 5xx, timeout)
- Exponential backoff
- Strict JSON response validation
"""

import httpx
import json
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """HTTP client for OpenRouter API with retry policy."""

    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = settings.research_model
        self.retry_count = settings.research_openrouter_retry_count
        self.backoff_seconds = settings.research_openrouter_backoff_seconds

    @retry(
        stop=stop_after_attempt(settings.research_openrouter_retry_count),
        wait=wait_exponential(multiplier=1, min=settings.research_openrouter_backoff_seconds),
    )
    async def research(
        self,
        prompt: str,
        system_context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        Execute research prompt via OpenRouter API.

        Returns:
        - Parsed JSON response
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_context or "You are a trading research assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=30.0,
                )
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # Validate and parse JSON response
                parsed = json.loads(content)
                logger.info(f"OpenRouter research completed for model: {self.model}")
                return parsed

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API error: {e.status_code} {e.response.text}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenRouter response as JSON: {e}")
            raise
        except Exception as e:
            logger.error(f"OpenRouter client error: {e}")
            raise


# Singleton instance
openrouter = OpenRouterClient()
