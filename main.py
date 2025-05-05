import os
import random
import re
import signal
import time
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from tinydb import TinyDB, where
from dotenv import load_dotenv
import humanize
import aiohttp
import shutil
import magic
import mimetypes
from guessit import guessit
from difflib import SequenceMatcher
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
from cachetools import TTLCache, cached

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')
# Admin IDs: comma-separated in ENV
ADMIN_IDS = {
    int(x.strip().strip('"').strip("'"))
    for x in os.getenv('ADMIN_IDS', '').split(',')
    if x.strip().strip('"').strip("'")
}

# Base directory for downloads & DB
BASE_DIR = Path.home() / "jellyfin"
BASE_DIR.mkdir(parents=True, exist_ok=True)

# TinyDB setup (replaces JSON persistence)
DB_PATH = BASE_DIR / "db.json"
db = TinyDB(DB_PATH)
users_tbl = db.table("users")
stats_tbl = db.table("stats")

# Fuzzy‑matching thresholds
HIGH_CONFIDENCE = 0.8  # auto‑accept
LOW_CONFIDENCE  = 0.6  # auto‑reject

# Create a shared cache for TMDb searches: up to 500 entries, TTL 1 hour
tmdb_cache = TTLCache(maxsize=500, ttl=3600)

# Shared HTTP session
aiohttp_session: aiohttp.ClientSession 

# Helper functions

def load_active_users() -> set[int]:
    """Load active users from TinyDB."""
    return {row['id'] for row in users_tbl.all()}


def save_active_users(users: set[int]):
    """Persist any new users via TinyDB."""
    for uid in users:
        if not users_tbl.contains(where('id') == uid):
            users_tbl.insert({'id': uid})


def admin_only(func):
    """Decorator to restrict command to admins."""
    async def wrapper(event):
        if event.sender_id not in ADMIN_IDS:
            return await event.respond("⚠️ Permission denied.")
        return await func(event)
    return wrapper

def similarity(a: str, b: str) -> float:
    """Return a ratio [0.0–1.0] of how similar two strings are."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# Directory Configuration
dirs = ["Downloads", "Movies", "TV", "Anime", "Music", "Other"]
for sub in dirs:
    d = BASE_DIR / sub
    d.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = BASE_DIR / "Downloads"
MOVIES_DIR = BASE_DIR / "Movies"
TV_DIR = BASE_DIR / "TV"
ANIME_DIR = BASE_DIR / "Anime"
MUSIC_DIR = BASE_DIR / "Music"
OTHER_DIR = BASE_DIR / "Other"

# Global shutdown flags
shutdown_in_progress = False
force_shutdown = False
last_sigint_time = 0
FORCE_SHUTDOWN_TIMEOUT = 10  # seconds

# BotStats class with TinyDB persistence
class BotStats:
    def __init__(self):
        self.start_time = datetime.now()
        self.files_handled = 0
        self.successful_downloads = 0
        self.failed_downloads = 0
        self.total_data = 0
        self.peak_concurrent = 0
        self.download_times = []
        self.download_speeds = []

    global_stats = None
    user_stats = {}

    @classmethod
    def load_all(cls):
        """Load stats from TinyDB into memory."""
        # Global
        gs = stats_tbl.get(where('type') == 'global')
        if gs:
            for k, v in gs.items():
                if k != 'type': setattr(cls.global_stats, k, v)
        # Per-user
        for row in stats_tbl.search(where('type').matches(r'^user_\d+$')):
            uid = int(row['type'].split('_',1)[1])
            bs = BotStats()
            for k, v in row.items():
                if k not in ('type',): setattr(bs, k, v)
            cls.user_stats[uid] = bs

    @classmethod
    def save_all(cls):
        """Persist stats from memory to TinyDB."""
        # Global
        gs = vars(cls.global_stats).copy()
        gs['type'] = 'global'
        gs.pop('start_time', None)
        stats_tbl.upsert(gs, where('type') == 'global')
        # Per-user
        for uid, bs in cls.user_stats.items():
            doc = vars(bs).copy()
            doc['type'] = f'user_{uid}'
            doc.pop('start_time', None)
            stats_tbl.upsert(doc, where('type') == f'user_{uid}')

    @classmethod
    def record_download(cls, user_id, size, duration, success=True):
        """Update in-memory and persist."""
        cls.global_stats.add_download(size, duration, success)
        if user_id not in cls.user_stats:
            cls.user_stats[user_id] = BotStats()
        cls.user_stats[user_id].add_download(size, duration, success)
        cls.save_all()

    def add_download(self, size, duration, success=True):
        self.files_handled += 1
        if success:
            self.successful_downloads += 1
            self.total_data += size
            self.download_times.append(duration)
            self.download_speeds.append(size / duration if duration > 0 else 0)
        else:
            self.failed_downloads += 1

    def update_peak_concurrent(self, current):
        if current > self.peak_concurrent:
            self.peak_concurrent = current

    def get_uptime(self):
        return datetime.now() - self.start_time

    def get_average_speed(self):
        return (sum(self.download_speeds) / len(self.download_speeds)) if self.download_speeds else 0

    def get_average_time(self):
        return (sum(self.download_times) / len(self.download_times)) if self.download_times else 0

# Signal handlers
def signal_handler(sig, frame):
    global shutdown_in_progress, force_shutdown, last_sigint_time
    now = time.time()
    if sig == signal.SIGINT:
        if now - last_sigint_time < FORCE_SHUTDOWN_TIMEOUT:
            force_shutdown = True; os._exit(1)
        last_sigint_time = now
        if not shutdown_in_progress:
            shutdown_in_progress = True
            asyncio.create_task(shutdown())

async def shutdown():
    """Graceful shutdown."""
    global shutdown_in_progress, force_shutdown
    if force_shutdown: return
    download_manager.accepting_new_downloads = False
    # Notify active downloads
    msg = "🔄 Bot is shutting down. Queued tasks will complete."
    for task in list(download_manager.active_downloads.values()):
        try: await task.event.respond(msg)
        except: pass
    # Wait up to 5m
    for _ in range(30):
        if force_shutdown or not download_manager.active_downloads: break
        await asyncio.sleep(10)
    # Cancel rest
    for task in list(download_manager.active_downloads.values()):
        await task.cancel()
    # Final offline notice
    final = "🔴 Bot is now offline. Thank you!"
    for uid in all_users:
        try: await client.send_message(uid, final)
        except: pass
    await client.disconnect(); os._exit(0)

# Download Manager
class DownloadManager:
    def __init__(self, max_concurrent=8):
        self.active_downloads = {}  # message_id: DownloadTask
        self.queued_downloads = []  # list of DownloadTask
        self.max_concurrent = max_concurrent
        self.lock = asyncio.Lock()
        self.accepting_new_downloads = True  # New flag to control accepting new downloads

    async def add_download(self, task):
        # Check if accepting new downloads
        if not self.accepting_new_downloads:
            await task.event.respond("⚠️ Bot is currently shutting down and not accepting new downloads.")
            logger.info("Not accepting new downloads at the moment.")
            return -1
        
        async with self.lock:
            if len(self.active_downloads) < self.max_concurrent:
                self.active_downloads[task.message_id] = task
                stats.update_peak_concurrent(len(self.active_downloads))
                asyncio.create_task(self._process_download(task))
                return 0  # Started immediately
            else:
                self.queued_downloads.append(task)
                return len(self.queued_downloads)  # Position in queue

    async def _process_download(self, task):
        try:
            await task.start_download()
            # Process the downloaded file
            await task.process_media()
        except Exception as e:
            logger.error(f"Error processing download: {e}")
        finally:
            # Remove from active downloads and process next in queue
            async with self.lock:
                if task.message_id in self.active_downloads:
                    del self.active_downloads[task.message_id]

                if self.queued_downloads:
                    next_task = self.queued_downloads.pop(0)
                    self.active_downloads[next_task.message_id] = next_task
                    stats.update_peak_concurrent(len(self.active_downloads))
                    asyncio.create_task(self._process_download(next_task))

    async def cancel_download(self, message_id):
        async with self.lock:
            # Check if it's in active downloads
            if message_id in self.active_downloads:
                task = self.active_downloads[message_id]
                await task.cancel()
                del self.active_downloads[message_id]
                return True

            # Check if it's in the queue
            for i, task in enumerate(self.queued_downloads):
                if task.message_id == message_id:
                    self.queued_downloads.pop(i)
                    await task.cancel()
                    return True

            return False

    def get_queue_status(self):
        return {
            "active": [(task.message_id, task.filename, task.progress)
                      for task in self.active_downloads.values()],
            "queued": [(i+1, task.message_id, task.filename, task.file_size)
                      for i, task in enumerate(self.queued_downloads)]
        }

# Download Task
class DownloadTask:
    def __init__(self, client, event, message_id, filename, file_size, download_manager):
        self.client = client
        self.event = event
        self.message_id = message_id
        self.download_path = os.path.join(DOWNLOAD_DIR, filename)
        self.ext = self.get_file_extension(filename)
        self.filename = filename if filename.endswith(self.ext) else f"{filename}{self.ext}"
        self.file_size = file_size
        self.start_time = None
        self.end_time = None
        self.download_path = os.path.join(DOWNLOAD_DIR, filename)
        self.progress = 0
        self.downloaded_bytes = 0
        self.current_speed = 0
        self.cancelled = False
        self.status_message = None
        self.process_message = None
        # Identify large files upfront and save as instance variable
        self.large_file = file_size > 500 * 1024 * 1024  # > 500 MB
        self.download_manager = download_manager
        self.queue_position = None
        self.last_update_time = None
        self.last_progress = 0
        
        # Log the file size classification for debugging
        logger.info(f"File {filename} size: {humanize.naturalsize(file_size)}, classified as {'large' if self.large_file else 'regular'} file")

    def get_file_extension(self, filename):
        """
        Determine a file extension:
        1) If the file already exists on disk, try python-magic.
        2) If the original filename has a suffix, use that.
        3) Else try mimetypes.guess_extension.
        4) Default to .bin.
        """
        dp = getattr(self, "download_path", None)
        # 1) Use python-magic if the file exists
        try:
            if dp and Path(dp).exists():
                mime = magic.from_file(str(dp), mime=True)
                ext = mimetypes.guess_extension(mime)
                if ext:
                    return ext
        except Exception as e:
            logger.warning(f"Magic sniff failed for {dp}: {e}")

        # 2) Prefer the original suffix if there is one
        suffix = Path(filename).suffix
        if suffix:
            return suffix

        # 3) Fallback to mimetypes
        guessed_mime, _ = mimetypes.guess_type(filename)
        if guessed_mime:
            ext = mimetypes.guess_extension(guessed_mime)
            if ext:
                return ext

        # 4) Ultimate fallback
        return '.bin'

    async def start_download(self):
        self.start_time = time.time()

        try:
            # Update the message to indicate download is starting
            # Include large file notification if applicable
            file_type_indicator = "📦 LARGE FILE" if self.large_file else "📄 Document"
            update_interval = "1 minute" if self.large_file else "15 seconds"
            
            await self.update_queue_message(
                f"📂 File detected: {self.filename}\n"
                f"{file_type_indicator}\n"
                f"📁 Will be downloaded in: {DOWNLOAD_DIR}\n"
                f"⏳ Download is starting now.....\n"
                f"ℹ️ Status updates every {update_interval}"
            )

            # Start the download
            await self.client.download_media(
                self.event.message,
                self.download_path,
                progress_callback=self.progress_callback
            )

            if not self.cancelled:
                self.end_time = time.time()
                duration = self.end_time - self.start_time

                # Update stats
                BotStats.record_download(self.event.sender_id, self.file_size, duration, success=True)

                # Send completion message
                await self.send_completion_message(duration)

                return True
            return False
        except Exception as e:
            logger.error(f"Download error for {self.filename}: {e}")
            await self.event.respond(f"⚠️ Download failed for {self.filename}: {str(e)}")
            BotStats.record_download(self.event.sender_id, 0, 0, success=False)
            return False

    async def progress_callback(self, current, total):
        if self.cancelled:
            raise asyncio.CancelledError("Download was cancelled")

        self.downloaded_bytes = current
        self.progress = (current / total) * 100

        # Calculate current speed
        current_time = time.time()
        elapsed = current_time - self.start_time
        self.current_speed = current / elapsed if elapsed > 0 else 0

        # For the first progress update, always send a message
        if not hasattr(self, 'first_progress_sent') or not self.first_progress_sent:
            self.first_progress_sent = True
            await self.send_progress_update(current, total, elapsed)
            self.last_update_time = current_time
            return

        # Determine if we should send a progress update
        should_update = False

        if self.large_file:
            # For large files, update every 1 minute
            if not self.last_update_time or current_time - self.last_update_time >= 60:  # 1 minute
                should_update = True
                self.last_update_time = current_time
        else:
            # For regular files, update every 15 seconds
            if not self.last_update_time or current_time - self.last_update_time >= 15:  # 15 seconds
                should_update = True
                self.last_update_time = current_time

        if should_update:
            await self.send_progress_update(current, total, elapsed)

    async def send_progress_update(self, current, total, elapsed):
        # Calculate ETA
        if self.current_speed > 0:
            eta_seconds = (total - current) / self.current_speed
            eta = str(timedelta(seconds=int(eta_seconds)))
        else:
            eta = "Unknown"

        # Build update message with clear large file indicator
        if self.large_file:
            message = (
                f"📦 STATUS UPDATE - LARGE FILE DOWNLOAD\n\n"
                f"📂 File: {self.filename}\n"
                f"⏱️ Running for: {humanize.precisedelta(timedelta(seconds=elapsed))}\n"
                f"✅ Progress: {self.progress:.1f}% complete\n"
                f"💾 Downloaded: {humanize.naturalsize(current)} of {humanize.naturalsize(total)}\n"
                f"⚡ Current speed: {humanize.naturalsize(self.current_speed)}/s\n"
                f"🕒 ETA: {eta} remaining\n\n"
                f"ℹ️ Large file: Updates every minute"
            )
        else:
            message = (
                f"📄 STATUS UPDATE - Regular Download\n\n"
                f"📂 File: {self.filename}\n"
                f"⏱️ Running for: {humanize.precisedelta(timedelta(seconds=elapsed))}\n"
                f"✅ Progress: {self.progress:.1f}% complete\n"
                f"💾 Downloaded: {humanize.naturalsize(current)} of {humanize.naturalsize(total)}\n"
                f"⚡ Current speed: {humanize.naturalsize(self.current_speed)}/s\n"
                f"🕒 ETA: {eta} remaining"
            )

        try:
            await self.status_message.edit(message,
                                            buttons=[
                                                [ Button.inline("❌ Cancel download", f"cancel_{self.message_id}") ]
                                            ])
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            # If edit fails, try sending a new message
            try:
                old_message = self.status_message
                self.status_message = await self.event.respond(message,
                                                                buttons=[
                                                                    [ Button.inline("❌ Cancel download", f"cancel_{self.message_id}") ]
                                                                ])
                try:
                    # Try to delete the old message to avoid clutter
                    await old_message.delete()
                except:
                    pass
            except Exception as inner_e:
                logger.error(f"Failed to send new status message: {inner_e}")

    async def send_completion_message(self, duration):
        suggested_filename = f"{self.filename}{self.ext}"  # Use the determined extension
        message = (
            f"✅ Download Complete!\n\n"
            f"📂 File: {self.filename}\n"
            f"📄 Suggested Filename: {suggested_filename}\n"
            f"{'📦 Large file' if self.large_file else '📄 Regular file'}\n"
            f"📊 Size: {humanize.naturalsize(self.file_size)}\n"
            f"⏱️ Time: {humanize.precisedelta(timedelta(seconds=duration))}\n"
            f"🚀 Avg Speed: {humanize.naturalsize(self.file_size / duration)}/s\n\n"
            f"Media categorizer will start shortly."
        )

        try:
            await self.status_message.edit(message,
                                            buttons=[
                                                [ Button.inline("❌ Cancel download", f"cancel_{self.message_id}") ]
                                            ])
        except Exception as e:
            logger.error(f"Failed to send completion message: {e}")
            # If edit fails, try sending a new message
            try:
                self.status_message = await self.event.respond(message)
            except:
                pass

    async def cancel(self):
        self.cancelled = True

        # Delete the partially downloaded file if it exists
        if os.path.exists(self.download_path):
            try:
                os.remove(self.download_path)
            except Exception as e:
                logger.error(f"Failed to remove file during cancellation: {e}")

        # Send cancellation message
        await self.event.respond(
            f"⚠️ Cancellation requested for {self.filename}\n"
            f"❌ Download cancelled for {self.filename}\n"
            f"🗑️ Removed from queue"
        )

        return True

    async def process_media(self):
        if self.cancelled:
            return

        self.process_message = await self.event.respond(f"ℹ️ 📝 Started processing: {self.filename}")
        try:
            # Step 1: Analyze file using MediaProcessor
            await self.update_processing_message("Analyzing")
            processor = MediaProcessor(self.filename, TMDB_API_KEY, session=aiohttp_session)
            result = await processor.search_tmdb()
            logger.info("search_tmdb result → %s", result)

            # ─── Fuzzy‑match check ────────────────────────────────────────────────
            parsed     = guessit(self.filename).get('title', '')
            tmdb_title = result.get('title', '')
            score      = similarity(parsed, tmdb_title)
            logger.info("Fuzzy match '%s' vs. '%s' → %.2f", parsed, tmdb_title, score)

            if score < LOW_CONFIDENCE:
                # Low confidence → fallback to Other
                target_dir = OTHER_DIR
                await self.update_processing_message(
                    f"⚠️ Low confidence match ({score:.2f}); defaulting to OTHER"
                )
                # Move without renaming
                dest = target_dir / Path(self.download_path).name
                shutil.move(self.download_path, str(dest))
                # Log low‑confidence cases
                with open(os.path.join(BASE_DIR, 'low_confidence_log.csv'), 'a') as lf:
                    lf.write(f"{self.filename},{parsed},{tmdb_title},{score:.2f}\n")
                return

            elif score < HIGH_CONFIDENCE:
                # Medium confidence → proceed but warn
                await self.update_processing_message(
                    f"⚠️ Medium confidence ({score:.2f}); proceeding with caution"
                )
            # ───────────────────────────────────────────────────────────────────────
            
            # Step 2: Decide where to put it
            if result:
                # 2a) Anime goes under Anime/<Title>
                if result.get('is_anime'):
                    target_dir = ANIME_DIR
                    anime_series_dir = target_dir / result['title']
                    Path(anime_series_dir).mkdir(parents=True, exist_ok=True)
                    await self.update_processing_message(
                        f"✅ Anime detected: {result['title']}\n"
                        f"Created directory: {anime_series_dir}")
                # 2b) TV shows
                elif result['type'] == 'tv':
                    show_name   = result['title']
                    season_no   = result['season']
                    episode_no  = result['episode']
                    folder_struct = result.get('folder_structure')

                    if folder_struct:
                        # user provided e.g. "My Show/Season 01/"
                        target_dir = TV_DIR / folder_struct
                    else:
                        target_dir = TV_DIR / show_name / f"Season {season_no:02d}"

                    target_dir.mkdir(parents=True, exist_ok=True)
                    await self.update_processing_message(
                        f"✅ TV: {show_name} S{season_no:02d}E{episode_no:02d}"
                    )

                # 2c) Movies
                elif result['type'] == 'movie':
                    title    = result['title']
                    year     = result.get('year', '')
                    folder_name = f"{title} ({year})" if year else title

                    target_dir = MOVIES_DIR / folder_name
                    target_dir.mkdir(parents=True, exist_ok=True)
                    await self.update_processing_message(
                        f"✅ Movie: {title} {f'({year})' if year else ''}"
                    )

                # 2d) Fallback
                else:
                    target_dir = OTHER_DIR
                    await self.update_processing_message(
                        "⚠️ Could not identify media type; defaulting to OTHER"
                    )
            else:
                target_dir = OTHER_DIR
                await self.update_processing_message(
                    "⚠️ No TMDb match found; defaulting to OTHER"
                )


            # ─── Rename for high‑confidence matches ───────────────────────────────
            if score >= HIGH_CONFIDENCE:
                ext = os.path.splitext(self.download_path)[1]
                # Build Jellyfin‑friendly base name
                if result.get('is_anime'):
                    base = f"{result['title']} - Episode {result.get('episode', '')}"
                elif result.get('type') == 'tv':
                    season  = result.get('season', 0)
                    episode = result.get('episode', 0)
                    base = f"{result['title']} - S{season:02d}E{episode:02d}"
                elif result.get('type') == 'movie':
                    year = result.get('year', '')
                    base = f"{result['title']} ({year})"
                else:
                    base = os.path.splitext(self.filename)[0]
                # Sanitize file name
                safe_base = re.sub(r'[\\/:"*?<>|]+', '', base)
                new_name = f"{safe_base}{ext}"
                # Rename on disk and update path
                new_path = os.path.join(os.path.dirname(self.download_path), new_name)
                os.rename(self.download_path, new_path)
                self.download_path = new_path
            # ────────────────────────────────────────────────────────────────────────


            # Step 3: Move file into place
            await self.update_processing_message("Moving to library")
            safe_name = os.path.basename(self.download_path)
            dest_path = os.path.join(target_dir, safe_name)
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(dest_path)
                dest_path = f"{base}_{int(time.time())}{ext}"
            shutil.move(self.download_path, dest_path)

            processing_time = time.time() - self.end_time
            await self.update_processing_message(
                f"✅ Processed {safe_name} in {processing_time:.1f}s\nMoved to: {dest_path}",
                final=True
            )

        except Exception as e:
            logger.error(f"Error processing media: {e}")
            await self.update_processing_message(
                f"❌ Error: {e}\nThe file remains in the download directory.",
                error=True
            )

    async def update_processing_message(self, stage, final=False, error=False):
        """Updates the processing message with the current stage."""
        if not self.process_message:
            return

        if error:
            message = f"ℹ️ 📝 Started processing: {self.filename}\n\n⚠️ {stage}"
        else:
            stage_symbol = "✅" if final else "🔄"
            message = f"ℹ️ 📝 Started processing: {self.filename}\n\n{stage_symbol} Stage: {stage}"

        try:
            await self.process_message.edit(message)
        except Exception as e:
            logger.error(f"Failed to update processing message: {e}")

    async def update_queue_message(self, message):
        """Updates the queue message with the current status."""
        if not self.status_message:
            # If no status message exists yet, create one
            self.status_message = await self.event.respond(message)
            return
            
        try:
            await self.status_message.edit(message,
                                            buttons=[
                                                [ Button.inline("❌ Cancel download", f"cancel_{self.message_id}") ]
                                            ])
        except Exception as e:
            logger.error(f"Failed to update queue message: {e}")
            # If edit fails due to "Content not modified" error, don't try again
            if "Content of the message was not modified" in str(e):
                pass
            else:
                # For other errors, try sending a new message
                try:
                    old_message = self.status_message
                    self.status_message = await self.event.respond(message)
                    try:
                        # Try to delete the old message to avoid clutter
                        await old_message.delete()
                    except:
                        pass
                except Exception as inner_e:
                    logger.error(f"Failed to send new queue message: {inner_e}")

class MediaProcessor:
    """
    Parses media filenames using GuessIt and queries TMDb for movies or TV episodes.
    Replace the old regex-based extractor and remove TV_REGEX_PATTERNS, MOVIE_YEAR_REGEX,
    extract_tv_info, extract_movie_info, extract_base_title, sanitize_filename methods.
    """
    TMDB_URL = "https://api.themoviedb.org/3"

    def __init__(self, filename: str, tmdb_api_key: str, session: aiohttp.ClientSession = None):
        """Initializes the MediaProcessor with filename, TMDb API key, and optional session."""
        self.filename = filename
        self.tmdb_api_key = tmdb_api_key
        # Always reuse the global session if none provided
        self.session = session or aiohttp_session

    async def fetch_json(self, url: str, params: dict) -> dict:
        params["api_key"] = self.tmdb_api_key
        async with self.session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def search_tmdb(self) -> dict:
        """
        Parse filename with GuessIt and query TMDb for movie or TV episode.
        """
        info       = guessit(self.filename)
        media_type = info.get('type')
        title      = info.get('title')
        if not title:
            raise ValueError(f"Could not extract title from '{self.filename}'")

        # TV episode lookup
        if media_type == 'episode':
            season  = info.get('season', 1)
            episode = info.get('episode', 1)
            logger.info("Detected TV: %s S%02dE%02d", title, season, episode)
            return await self.tmdb_search_tv(title, season, episode)

        # Movie lookup (or fallback)
        year = info.get('year') if media_type == 'movie' else None
        logger.info("Detected Movie: %s (%s)", title, year)
        return await self.tmdb_search_movie(title, year)

    @cached(cache=tmdb_cache, key=lambda self, title, year=None: f"movie:{title}:{year}")
    async def tmdb_search_movie(self, title: str, year: int = None) -> dict:
        """Cached movie lookup (now sends API key correctly)."""
        search_url = f"{self.TMDB_URL}/search/movie"
        params = {"query": title}
        if year:
            params["year"] = year

        try:
            # fetch_json will inject the api_key param
            data = await self.fetch_json(search_url, params)
        except Exception as e:
            logger.error(f"TMDb movie search error: {e}")
            return {}

        if not data.get("results"):
            return {}
        result = data["results"][0]
        is_anime = await self.check_anime_tag(result["id"], "movie")
        return {
            "type": "movie",
            "title": result.get("title", title),
            "year": result.get("release_date", "")[:4],
            "tmdb_id": result["id"],
            "is_anime": is_anime,
        }

    @cached(cache=tmdb_cache, key=lambda self, title, season, episode: f"tv:{title}:{season}:{episode}")
    async def tmdb_search_tv(self, title: str, season: int, episode: int) -> dict:
        """Cached TV lookup."""
        search_url = f"{self.TMDB_URL}/search/tv"
        try:
            data = await self.fetch_json(search_url, {"query": title})
            results = data.get("results", [])
        except Exception as e:
            logger.error(f"TMDb TV search error: {e}")
            return {}
        except aiohttp.ClientError as e:
            logger.error(f"TMDb TV search network error: {e}")
            return {}

        if not results:
            return {}
        show_id = results[0]["id"]
        is_anime = await self.check_anime_tag(show_id, "tv")
        return {
            "type": "tv",
            "title": results[0].get("name", title),
            "season": season,
            "episode": episode,
            "is_anime": is_anime,
            "tmdb_id": show_id,
        }
    
    async def check_anime_tag(self, tmdb_id: int, media_type: str) -> bool:
        """Check if 'anime' exists in TMDb keywords"""
        endpoint = f"{self.TMDB_URL}/{media_type}/{tmdb_id}/keywords"
        try:
            # fetch_json will add api_key for us
            data = await self.fetch_json(endpoint, {})
            # Handle both movie and TV keyword formats
            keywords = data.get("keywords", []) if media_type == "movie" else data.get("results", [])
            return any(k["name"].lower() == "anime" for k in keywords)
        except Exception as e:
            logger.error(f"TMDb keyword check failed: {e}")
            return False

# Initialize in-memory state & objects
all_users = load_active_users()
stats = BotStats()
BotStats.global_stats = stats
BotStats.load_all()
download_manager = DownloadManager()

# Initialize Telegram client
client = TelegramClient('jellyfin_bot', API_ID, API_HASH)

def build_queue_message():
    """
    Returns (text, buttons) for the current download queue,
    so both /queue and the cancel callback can share it.
    """
    status = download_manager.get_queue_status()
    active = status["active"]
    queued = status["queued"]

    # Build text
    lines = [
        "📋 DOWNLOAD QUEUE STATUS\n",
        f"⏳ Active downloads: {len(active)}/{download_manager.max_concurrent}",
        f"🔄 Queued files: {len(queued)}\n",
    ]
    if active:
        lines.append("🔽 CURRENTLY DOWNLOADING:")
        for i, (_, fn, prog) in enumerate(active, 1):
            lines.append(f"{i}️⃣ {fn} ({prog:.0f}% complete)")
        lines.append("")
    if queued:
        lines.append("⏭️ NEXT IN QUEUE:")
        for i, (_, _, fn, sz) in enumerate(queued, 1):
            lines.append(f"{i}. {fn} ({humanize.naturalsize(sz)})")
    lines.append("\n🛑 To cancel: press ❌ next to the file")
    text = "\n".join(lines)

    # Build buttons
    buttons = []
    for msg_id, fn, _ in active:
        disp = (fn[:20] + "...") if len(fn) > 20 else fn
        buttons.append([Button.inline(f"❌ Cancel: {disp}", f"cancel_{msg_id}")])
    for _, msg_id, fn, _ in queued:
        disp = (fn[:20] + "...") if len(fn) > 20 else fn
        buttons.append([Button.inline(f"❌ Cancel: {disp}", f"cancel_{msg_id}")])

    return text, buttons

# Handlers
@client.on(events.NewMessage(pattern='/shutdown'))
@admin_only
async def shutdown_command(event):
    """Admin shutdown."""
    global shutdown_in_progress
    if shutdown_in_progress:
        return await event.respond("⚠️ Shutdown in progress.")
    await event.respond("🔄 Graceful shutdown initiated.")
    shutdown_in_progress = True
    asyncio.create_task(shutdown())

@client.on(events.NewMessage(pattern='/users'))
@admin_only
async def users_command(event):
    total = len(users_tbl.all())
    await event.respond(f"👥 Total users: {total}\nDB: {DB_PATH}")

@client.on(events.NewMessage(pattern='/start|/help'))
async def start_command(event):
    """Handler for /start and /help commands"""
    
    global all_users
    # Check if the user is already in the active users list
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users(all_users)

    await event.respond(
        "👋 Welcome to the Jellyfin Media Downloader Bot!\n\n"
        "Send me any media file and I will download it to your Jellyfin library.\n\n"
        "📂 COMMANDS:\n"
        "/start - Show this welcome message\n"
        "/stats - 📊 Show download statistics\n"
        "/queue - 📋 View current download queue\n"
        "/test - 🔍 Run system test\n"
        "/help - ❓ Show usage help\n\n"
        "/users - 👥 View total unique users (admin only)\n"
        "/shutdown - 🔌 Gracefully shut down the bot (admin only)\n\n"
        "📱 SUPPORTED FORMATS:\n"
        "🎬 Videos - MP4, MKV, AVI, etc.\n"
        "🎵 Audio - MP3, FLAC, WAV, etc.\n"
        "📄 Documents - PDF, ZIP, etc."
    )

@client.on(events.NewMessage(pattern='/stats|/status'))
async def stats_command(event):
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})
    if event.sender_id in ADMIN_IDS:
        lines = ["📊 Persistent Download Statistics", ""]
        lines.append("Per‑user stats:")
        for uid, st in BotStats.user_stats.items():
            lines.append(
                f"• User {uid}: handled {st.files_handled}, "
                f"success {st.successful_downloads}, failed {st.failed_downloads}"
            )
        lines.append("")  # spacer
        gs = BotStats.global_stats
        success_pct = (gs.successful_downloads / gs.files_handled * 100) if gs.files_handled else 0
        lines.append("Global stats:")
        lines.append(
            f"• Total handled: {gs.files_handled}, "
            f"success {gs.successful_downloads} ({success_pct:.1f}%), "
            f"failed {gs.failed_downloads} ({100-success_pct:.1f}%)"
        )
        await event.respond("\n".join(lines))
        return

    # Non-admin: show the existing runtime stats
    uptime = stats.get_uptime()

    # Calculate success percentage
    if stats.files_handled > 0:
        success_percent = (stats.successful_downloads / stats.files_handled) * 100
    else:
        success_percent = 0

    # Get average speed in MB/s
    avg_speed = stats.get_average_speed()
    avg_speed_str = humanize.naturalsize(avg_speed) + "/s" if avg_speed > 0 else "N/A"

    # Get average time per file
    avg_time = stats.get_average_time()
    avg_time_str = humanize.precisedelta(timedelta(seconds=avg_time)) if avg_time > 0 else "N/A"

    # Get queue info
    queue_status = download_manager.get_queue_status()
    active_count = len(queue_status["active"])
    queued_count = len(queue_status["queued"])

    await event.respond(
        "📊 DOWNLOAD STATISTICS\n\n"
        f"📆 Bot uptime: {humanize.precisedelta(uptime)}\n"
        f"📥 Files handled: {stats.files_handled}\n\n"
        f"DOWNLOADS:\n"
        f"✅ Successful: {stats.successful_downloads} ({success_percent:.1f}%)\n"
        f"❌ Failed: {stats.failed_downloads} ({100-success_percent:.1f}%)\n"
        f"💾 Total data: {humanize.naturalsize(stats.total_data)}\n\n"
        f"PERFORMANCE:\n"
        f"⚡ Average speed: {avg_speed_str}\n"
        f"⏱️ Avg time per file: {avg_time_str}\n"
        f"📊 Peak concurrent downloads: {stats.peak_concurrent}/{download_manager.max_concurrent}\n\n"
        f"⏳ Current status: {active_count} active, {queued_count} queued"
    )

@client.on(events.NewMessage(pattern='/queue'))
async def queue_command(event):
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})

    text, buttons = build_queue_message()
    # If there are buttons, send with them; else without
    await event.respond(text, buttons=buttons if buttons else None)

@client.on(events.NewMessage(pattern='/test'))
async def test_command(event):
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})

    # 1) Directory checks
    directories = {
        "telegram_download_dir": DOWNLOAD_DIR,
        "movies_dir": MOVIES_DIR,
        "tv_dir": TV_DIR,
        "music_dir": MUSIC_DIR,
        "other_dir": OTHER_DIR
    }
    dir_checks = []
    for name, path in directories.items():
        if path.exists() and os.access(path, os.R_OK | os.W_OK):
            free = shutil.disk_usage(path).free
            dir_checks.append(f"✅ {name}: OK ({humanize.naturalsize(free)} free)")
        else:
            dir_checks.append(f"❌ {name}: NOT ACCESSIBLE")

    # 2) Internet check
    internet_check = "✅ Internet connection: OK"
    try:
        async with aiohttp_session.get("https://www.google.com", timeout=5) as resp:
            if resp.status != 200:
                internet_check = "❌ Internet connection: Failed (HTTP error)"
    except:
        internet_check = "❌ Internet connection: Failed (connection error)"

    # 3) Telethon connection
    telethon_check = (
        "✅ Telethon client: Connected"
        if client.is_connected()
        else "❌ Telethon client: Disconnected"
    )

    # 4) TMDb API configuration
    if TMDB_API_KEY:
        tmdb_config_check = "✅ TMDb API: Configured"
        try:
            async with aiohttp_session.get(
                f"https://api.themoviedb.org/3/configuration?api_key={TMDB_API_KEY}",
                timeout=5
            ) as resp:
                if resp.status != 200:
                    tmdb_config_check = "❌ TMDb API: Config fetch failed"
        except Exception as e:
            tmdb_config_check = f"❌ TMDb API: Connection error: {e}"
    else:
        tmdb_config_check = "⚠️ TMDb API: Not configured"

    # 5) Random‑filename TMDb lookup
    filenames_env = os.getenv('FILENAMES', '')
    if not filenames_env:
        filename_section = "⚠️ No FILENAMES set in environment."
    else:
        # split on commas, strip whitespace and surrounding quotes
        lines = [
            name.strip().strip('"')
            for name in filenames_env.split(',')
            if name.strip()
        ]
        if not lines:
            filename_section = "⚠️ FILENAMES is empty."
        else:
            test_file = random.choice(lines)
            processor = MediaProcessor(test_file, tmdb_api_key=TMDB_API_KEY)
            try:
                lookup = await processor.search_tmdb()
                filename_section = (
                    f"🎲 Filename test: `{test_file}`\n"
                    "```json\n"
                    f"{lookup}\n"
                    "```"
                )
            except Exception as e:
                filename_section = f"❌ Error processing `{test_file}`:\n```\n{e}\n```"

    # 6) Network speed test
    start = time.time()
    size = 0
    try:
        async with aiohttp_session.get(
            "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",
            timeout=5
        ) as resp:
            data = await resp.read() if resp.status == 200 else b''
            size = len(data)
    except:
        pass
    duration = time.time() - start
    net_speed = humanize.naturalsize(size / duration) + "/s" if duration > 0 else "N/A"

    # Build the response
    msg = ["🔍 SYSTEM TEST RESULTS", ""]
    msg.append("📁 Directory Checks")
    msg += dir_checks
    msg.append("")
    msg.append("🔧 System Checks")
    msg.append(internet_check)
    msg.append(telethon_check)
    msg.append("")
    msg.append("🌐 API Connections")
    msg.append(tmdb_config_check)
    msg.append(filename_section)
    msg.append("")
    msg.append("⚡ Performance")
    msg.append(f"⚡ Network speed: {net_speed}")
    msg.append("")

    # Overall summary
    if any(line.startswith("❌") for line in msg):
        msg.append("📊 Overall Status: Some issues detected")
    else:
        msg.append("📊 Overall Status: All systems operational")

    await event.respond("\n".join(msg))

@client.on(events.CallbackQuery(pattern=r'cancel_(\d+)'))
async def cancel_download_callback(event):
    mid = int(event.data.decode().split('_')[1])
    success = await download_manager.cancel_download(mid)
    # Acknowledge the button press
    await event.answer("✅ Cancelled" if success else "❌ Not found", alert=False)

    # Rebuild and edit the same message that had the queue
    text, buttons = build_queue_message()
    try:
        # For CallbackQuery, event.edit() updates the original message
        await event.edit(text, buttons=buttons if buttons else None)
    except Exception:
        # Fallback: send a fresh message
        await event.respond(text, buttons=buttons if buttons else None)

@client.on(events.NewMessage)
async def handle_media(event):
    if not event.message.media: return
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})

    # Get file info
    filename = None
    file_size = 0

    # Handle different media types
    if hasattr(event.message.media, 'document'):
        document = event.message.media.document
        file_size = document.size
        
        # Log the file size for debugging
        logger.info(f"Received document with size: {humanize.naturalsize(file_size)}")

        # Try to get the filename from attributes
        for attr in document.attributes:
            if hasattr(attr, 'file_name') and attr.file_name:
                filename = attr.file_name
                break

    # If we couldn't get the filename, generate one
    if not filename:
        # Generate a name based on the media type and current timestamp
        ext = ".unknown"

        # Try to determine a better extension based on mime type
        if hasattr(event.message.media, 'document'):
            mime_type = event.message.media.document.mime_type
            if mime_type:
                if mime_type.startswith('video/'):
                    ext = ".mp4"
                elif mime_type.startswith('audio/'):
                    ext = ".mp3"
                elif mime_type.startswith('image/'):
                    ext = ".jpg"

        filename = f"telegram_download_{int(time.time())}{ext}"

    # Create a download task
    task = DownloadTask(
        client=client,
        event=event,
        message_id=event.message.id,
        filename=filename,
        file_size=file_size,
        download_manager=download_manager
    )

    # Determine file type for initial message
    file_type_indicator = "📦 LARGE FILE" if task.large_file else "📄 Document"
    update_interval = "1 minute" if task.large_file else "15 seconds"

    # Initial message with size classification
    initial_message = (
        f"📂 File detected: {filename}\n"
        f"{file_type_indicator} ({humanize.naturalsize(file_size)})\n"
        f"📁 Will be downloaded in: {DOWNLOAD_DIR}\n" 
        f"⏳ The file is being added to the queue.\n"
        f"ℹ️ Status updates will be sent every {update_interval}"
    )

    # Send the initial message and store it
    task.status_message = await event.respond(
        initial_message,
        buttons=[[ Button.inline("❌ Cancel download", f"cancel_{task.message_id}") ]]
    )

    # Add to download manager
    queue_position = await download_manager.add_download(task)
    task.queue_position = queue_position

    # Update the queue message based on queue position
    if queue_position == 0:
        await task.update_queue_message(
            f"📂 File detected: {filename}\n"
            f"{file_type_indicator} ({humanize.naturalsize(file_size)})\n"
            f"📁 Will be downloaded in: {DOWNLOAD_DIR}\n"
            f"⏳ Download is starting now.....\n"
            f"ℹ️ Status updates will be sent every {update_interval}"
        )
    else:
        total_files_in_queue = len(download_manager.queued_downloads) + len(download_manager.active_downloads)
        await task.update_queue_message(
            f"📂 File detected: {filename}\n"
            f"{file_type_indicator} ({humanize.naturalsize(file_size)})\n"
            f"📁 Will be downloaded in: {DOWNLOAD_DIR}\n"
            f"⏳ The file is queue number {queue_position}/{total_files_in_queue}\n"
            f"ℹ️ Status updates will be sent every {update_interval} once download starts"
        )

async def main():
    global aiohttp_session
    aiohttp_session = aiohttp.ClientSession()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s, None))
    await client.start(bot_token=BOT_TOKEN)
    logger.info("Bot started")
    # Optional: notify previous users
    for uid in load_active_users():
        try: await client.send_message(uid, "🟢 Bot is back online!")
        except: pass
    try:
        await client.run_until_disconnected()
    finally:
        # ensure we always close the session
        await aiohttp_session.close()

async def handle_signal(sig):
    """Async signal handler that calls the main signal handler"""
    signal_handler(sig, None)

if __name__ == '__main__':
    # Run the bot
    asyncio.run(main())