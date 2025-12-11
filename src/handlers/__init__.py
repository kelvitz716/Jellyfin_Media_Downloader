"""
Handlers Package - Centralized handler registration.

This module provides a unified way to register all handlers
with the Telegram client.
"""
from . import user, admin, organize, media


def register_all_handlers(
    client,
    download_manager,
    organizer,
    organize_sessions,
    bulk_sessions,
    all_users,
    aiohttp_session,
    get_shutdown_status,
    shutdown_callback
):
    """
    Register all handlers with the Telegram client.
    
    Args:
        client: TelegramClient instance
        download_manager: DownloadManager instance
        organizer: InteractiveOrganizer instance
        organize_sessions: SessionManager for organize flow
        bulk_sessions: SessionManager for bulk propagation
        all_users: Set of user IDs
        aiohttp_session: aiohttp ClientSession
        get_shutdown_status: Callable returning shutdown status
        shutdown_callback: Async function for graceful shutdown
    """
    # Register user handlers
    user.register(client, download_manager, aiohttp_session, all_users)
    
    # Register media handler
    media.register(client, download_manager, all_users, get_shutdown_status)
    
    # Register organize handlers
    organize.register(client, organizer, organize_sessions, media.handle_media)
    
    # Register admin handlers (needs _run_finalize from organize)
    admin.register(
        client,
        organizer,
        bulk_sessions,
        finalize_cb=organize.run_finalize,
        shutdown_cb=shutdown_callback
    )

