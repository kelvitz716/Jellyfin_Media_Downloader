"""
Media Handlers - Incoming file download handling.

Handles:
- Incoming media messages
- Creating download tasks
- Queue management callbacks
"""
import mimetypes
from pathlib import Path

from telethon import events

from config import MEDIA_EXTENSIONS
from database import save_active_users
from downloader import DownloadTask

# These will be set during handler registration
client = None
download_manager = None
all_users = set()
shutdown_in_progress = False


def register(telegram_client, dm, users, get_shutdown_status):
    """Register media handlers with the client."""
    global client, download_manager, all_users, _get_shutdown_status
    client = telegram_client
    download_manager = dm
    all_users = users
    _get_shutdown_status = get_shutdown_status


_get_shutdown_status = lambda: False


async def handle_media(event):
    """
    Main handler for incoming media files.
    """
    global all_users
    
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})

    # Check if we are shutting down
    if _get_shutdown_status():
        await event.respond("⚠️ Bot is shutting down. Cannot accept new files.")
        return

    # Get media attributes
    media = event.message.media
    if not media:
        return
        
    filename = None
    file_size = 0

    if hasattr(media, 'document'):
        # It's a document/video file
        for attr in media.document.attributes:
            if hasattr(attr, 'file_name'):
                filename = attr.file_name
                break
        file_size = media.document.size
        # Fallback if no filename
        if not filename:
            mime_type = media.document.mime_type
            ext = mimetypes.guess_extension(mime_type) or ".bin"
            filename = f"unknown_{event.message.id}{ext}"
    else:
        # It might be a photo or something else we don't handle as "media download"
        return

    # Check extension
    ext = Path(filename).suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        await event.respond(f"⚠️ Ignoring file with unsupported extension: `{ext}`")
        return

    # Create download task
    task = DownloadTask(client, event, event.message.id, filename, file_size, download_manager)
    
    # Add to manager
    position = await download_manager.add_download(task)
    
    if position == -1:
        # Shutdown prevented download
        return
    elif position == 0:
        await event.respond(f"⬇️ Starting download: `{filename}`")
    else:
        await event.respond(f"⏳ Added to queue (position {position}): `{filename}`")
