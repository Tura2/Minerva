"""Supabase client singleton."""

from supabase import create_client, Client
from app.config import settings
import logging

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client initialized")
    return _client
