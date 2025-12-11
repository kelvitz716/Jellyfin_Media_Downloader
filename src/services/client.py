"""
Telegram Client Setup - Centralized client initialization.

This module provides the shared Telegram client instance
that all handlers use.
"""
from telethon import TelegramClient

from config import API_ID, API_HASH, SESSION_NAME


# Shared Telegram client instance
client = TelegramClient(str(SESSION_NAME), API_ID, API_HASH)

# aiohttp session (initialized in main)
aiohttp_session = None


def get_client() -> TelegramClient:
    """Get the Telegram client instance."""
    return client


def get_aiohttp_session():
    """Get the shared aiohttp session."""
    return aiohttp_session


def set_aiohttp_session(session):
    """Set the shared aiohttp session."""
    global aiohttp_session
    aiohttp_session = session
