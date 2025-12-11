#!/usr/bin/env python3
"""
Jellyfin Media Downloader Bot - Entry Point

A Telegram bot that downloads media files and organizes them
into Jellyfin library folders using GuessIt and TMDb metadata.

This is a slim entry point. All handlers are in src/handlers/.
"""
import asyncio
import logging
import signal
import sys
import time

import aiohttp
from telethon import TelegramClient

# Core configuration and services
from config import API_ID, API_HASH, BOT_TOKEN, SESSION_NAME
from database import load_active_users, save_active_users
from organizer import InteractiveOrganizer
from downloader import DownloadManager

# Session management (replaces defaultdict)
from src.services.session_manager import SessionManager

# Handler registration
from src.handlers import register_all_handlers

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
logger.addHandler(sh)

# --- Global State ---
organizer = InteractiveOrganizer()
download_manager = DownloadManager()
all_users = load_active_users()

# Telegram client
client = TelegramClient(str(SESSION_NAME), API_ID, API_HASH)

# Session managers (replaces defaultdict)
organize_sessions = SessionManager(ttl_minutes=30)
bulk_sessions = SessionManager(ttl_minutes=30)

# Global aiohttp session
aiohttp_session = None

# Shutdown flags
shutdown_in_progress = False
force_shutdown = False
last_sigint_time = 0
FORCE_SHUTDOWN_TIMEOUT = 10  # seconds


def get_shutdown_status():
    """Get current shutdown status."""
    return shutdown_in_progress


async def shutdown():
    """Graceful shutdown sequence."""
    global shutdown_in_progress
    shutdown_in_progress = True
    
    logger.info("Starting graceful shutdown...")
    
    # Stop accepting new downloads
    download_manager.accepting_new_downloads = False
    
    # Wait for active downloads to complete (with timeout)
    max_wait = 60  # seconds
    start = time.time()
    while download_manager.active_downloads and (time.time() - start) < max_wait:
        active_count = len(download_manager.active_downloads)
        logger.info(f"Waiting for {active_count} active download(s) to complete...")
        await asyncio.sleep(2)
    
    if download_manager.active_downloads:
        logger.warning(f"Timeout reached. {len(download_manager.active_downloads)} downloads still active.")
    
    # Save stats
    from stats import BotStats
    BotStats.save_all()
    
    # Save active users
    save_active_users(all_users)
    
    # Close aiohttp session
    if aiohttp_session:
        await aiohttp_session.close()
    
    # Disconnect client
    await client.disconnect()
    
    logger.info("Shutdown complete.")


def signal_handler(sig, frame):
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    global shutdown_in_progress, force_shutdown, last_sigint_time
    
    current_time = time.time()
    
    if shutdown_in_progress:
        if current_time - last_sigint_time < FORCE_SHUTDOWN_TIMEOUT:
            logger.warning("Force shutdown requested. Exiting immediately.")
            sys.exit(1)
        last_sigint_time = current_time
        logger.info("Shutdown in progress. Press Ctrl+C again within 10s to force quit.")
    else:
        last_sigint_time = current_time
        asyncio.create_task(shutdown())


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Main entry point."""
    global aiohttp_session
    
    # Initialize aiohttp session
    aiohttp_session = aiohttp.ClientSession()
    
    # Register all handlers
    register_all_handlers(
        client=client,
        download_manager=download_manager,
        organizer=organizer,
        organize_sessions=organize_sessions,
        bulk_sessions=bulk_sessions,
        all_users=all_users,
        aiohttp_session=aiohttp_session,
        get_shutdown_status=get_shutdown_status,
        shutdown_callback=shutdown
    )
    
    # Start client
    await client.start(bot_token=BOT_TOKEN)
    
    # Get bot info
    me = await client.get_me()
    logger.info(f"Bot started as @{me.username} (ID: {me.id})")
    
    # Run until disconnected
    await client.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
