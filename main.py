from itertools import islice
import os
import random
import re
import signal
import sys
import time
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import List

from tinydb import TinyDB, where
from dotenv import load_dotenv
import humanize
import aiohttp
import shutil
from tmdbv3api import TMDb, Movie, TV
import mimetypes
from guessit import guessit
from difflib import SequenceMatcher
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from async_timeout import timeout
from cachetools import TTLCache, cached

# Load environment variables
load_dotenv()

# Ensure required vars
for var in ("API_ID","API_HASH","BOT_TOKEN"):
    if not os.getenv(var):
        print(f"Error: {var} not set", file=sys.stderr)
        sys.exit(1)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

REQUIRED_ENV = {
    'API_ID': {'val': None, 'required': True},
    'API_HASH': {'val': None, 'required': True},
    'BOT_TOKEN': {'val': None, 'required': True},
    'TMDB_API_KEY': {'val': None, 'required': False},  # metadata optional
}

# Maximum download duration (seconds); default 2 hours
MAX_DOWNLOAD_DURATION = int(os.getenv("MAX_DOWNLOAD_DURATION", "7200"))

# load and validate env vars
print("Loading environment variables...")
for name, meta in REQUIRED_ENV.items():
    val = os.getenv(name)
    meta['val'] = val
    if val:
        status = 'OK'
    else:
        status = 'MISSING' if meta['required'] else 'DISABLED'
    print(f"  {name}: {status}")
    if status == 'MISSING':
        sys.exit(1)

# assign for backward compatibility
API_ID = REQUIRED_ENV['API_ID']['val']
API_HASH = REQUIRED_ENV['API_HASH']['val']
BOT_TOKEN = REQUIRED_ENV['BOT_TOKEN']['val']
TMDB_API_KEY = REQUIRED_ENV['TMDB_API_KEY']['val']
# Admin IDs: comma-separated in ENV
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x}

# Base directory for downloads & DB
BASE_DIR    = Path(os.getenv("BASE_DIR","/data/jellyfin")).expanduser()
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", BASE_DIR / "Downloads")).expanduser()
MOVIES_DIR   = Path(os.getenv("MOVIES_DIR", BASE_DIR / "Movies")).expanduser()
TV_DIR       = Path(os.getenv("TV_DIR", BASE_DIR / "TV")).expanduser()
ANIME_DIR    = Path(os.getenv("ANIME_DIR", BASE_DIR / "Anime")).expanduser()
MUSIC_DIR    = Path(os.getenv("MUSIC_DIR", BASE_DIR / "Music")).expanduser()
OTHER_DIR    = Path(os.getenv("OTHER_DIR", BASE_DIR / "Other")).expanduser()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def create_dir_safely(path: Path):
    if not path.exists():
        logger.info(f"Creating directory: {path}")
    path.mkdir(parents=True, exist_ok=True)

# Create essential directories with retry logic
for d in (BASE_DIR, DOWNLOAD_DIR, MOVIES_DIR, TV_DIR, ANIME_DIR, MUSIC_DIR, OTHER_DIR):
    create_dir_safely(d)

# STDOUT handler
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
# File handler
fh = logging.FileHandler(BASE_DIR / "bot.log")
fh.setFormatter(formatter)
logger.addHandler(sh)
logger.addHandler(fh)

# Filenames list file (used in /organize or similar handlers)
FILENAMES_FILE = Path(os.getenv("FILENAMES_FILE", BASE_DIR / "filenames.txt"))

# Initialize TinyDB
# Database file (TinyDB)
DB_PATH = BASE_DIR / os.getenv("DB_FILE", "db.json")
# Initialize TinyDB and tables
db          = TinyDB(DB_PATH)
users_tbl   = db.table("users")
stats_tbl   = db.table("stats")
organized_tbl = db.table("organized")
error_log_tbl = db.table("error_log")

# Fuzzy-matching thresholds (configurable via ENV, defaults 0.6/0.8)
LOW_CONFIDENCE  = float(os.getenv("LOW_CONFIDENCE", "0.6"))   # below this → OTHER
HIGH_CONFIDENCE = float(os.getenv("HIGH_CONFIDENCE", "0.8"))  # at or above this → auto-rename

# Create a shared cache for TMDb searches: up to 500 entries, TTL 1 hour
tmdb_cache = TTLCache(maxsize=500, ttl=3600)

# Shared HTTP session
aiohttp_session: aiohttp.ClientSession 

# Override incorrect MIME-to-extension mapping
mimetypes.init()
mimetypes.add_type('video/x-matroska', '.mkv', strict=False)

# Merge the two dicts so we see both “official” and “common” mappings
combined_map = {}
combined_map.update(mimetypes.types_map)
combined_map.update(mimetypes.common_types)

# Now pick video/* extensions
MEDIA_EXTENSIONS = {
    ext.lower()
    for ext, mime in combined_map.items()
    if mime and mime.startswith("video/")
}

# --- Organize sessions FSM ---
organize_sessions = defaultdict(dict)

# In-memory state for bulk propagation
bulk_sessions = defaultdict(lambda: {"items": [], "index": 0})

# Initialize tmdbv3api client (blocking under the hood)
tmdb = TMDb()
tmdb.api_key = TMDB_API_KEY
tmdb.language = 'en'

_movie = Movie()
_tv    = TV()

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

# Helper: paginate TinyDB results (returns page + total count)
def paginate_db(table, limit=10, offset=0):
    all_entries = sorted(table.all(), key=lambda r: r.get("timestamp", ""), reverse=True)
    total = len(all_entries)
    page = list(islice(all_entries, offset, offset + limit))
    return page, total

def find_remaining_episodes(folder: Path, title: str, season: int, last_ep: int) -> list:
    """
    Scan DOWNLOAD_DIR for unorganized episodes matching title+season,
    with episode > last_ep.
    Returns list of dicts: {src: Path, dest: Path, season, episode}.
    """
    results = []
    for p in DOWNLOAD_DIR.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        info = guessit(p.name)
        if info.get("type") != "episode":
            continue
        if info.get("season") != season:
            continue
        ep = info.get("episode")
        if not ep or ep <= last_ep:
            continue
        # fuzzy title match
        if similarity(info.get("title",""), title) < 0.8:
            continue
        # skip if already in DB
        if organizer.is_already_organized(p.name):
            continue
        # build destination path
        base = f"{title} - S{season:02d}E{ep:02d}"
        res  = organizer.detect_resolution(p)
        new_name = f"{base} [{res}]{p.suffix}"
        dest = folder / new_name
        results.append({"src": p, "dest": dest, "season": season, "episode": ep})
    # sort by episode number
    return sorted(results, key=lambda i: i["episode"])
# Global shutdown flags
shutdown_in_progress = False
force_shutdown = False
last_sigint_time = 0
FORCE_SHUTDOWN_TIMEOUT = 10  # seconds


class InteractiveOrganizer:
    def __init__(self):
        self.organized_tbl = organized_tbl
        self.error_log_tbl = error_log_tbl

    def is_already_organized(self, file_name: str) -> bool:
        """Check TinyDB to see if this filename was already handled."""
        return bool(self.organized_tbl.get(lambda r: r.get("path", "").endswith(file_name)))

    def scan_for_candidates(self) -> List[Path]:
        """Scan DOWNLOAD_DIR and OTHER_DIR for files not yet organized."""
        candidates = []
        for base in (DOWNLOAD_DIR, OTHER_DIR):
            for p in Path(base).rglob("*"):
                if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS:
                    if not self.is_already_organized(p.name):
                        candidates.append(p)
        return candidates

    async def prompt_for_category_and_metadata(self, session, file_path: Path) -> dict:
        """
        Interactive prompt: category, title, year, season/episode.
        Returns metadata dict.
        """
        client = session.client

        async def ask(question: str):
            await session.respond(question)
            ev = await client.wait_event(
                events.NewMessage(incoming=True, from_users=session.sender_id),
                timeout=60
            )
            return ev.text.strip()

        # 1) category
        cat = await ask("Enter category (`movie`, `tv`, or `anime`):")
        cat = cat.lower()
        if cat not in {"movie", "tv", "anime"}:
            await session.respond("Invalid category, defaulting to `movie`.")
            cat = "movie"

        # 2) title
        title = await ask("Enter title:")

        # 3) year
        year_text = await ask("Enter year (e.g. `2021`):")
        year = int(year_text) if year_text.isdigit() else None

        # 4) season/episode if needed
        season = episode = None
        if cat in {"tv", "anime"}:
            s = await ask("Enter season number:")
            e = await ask("Enter episode number:")
            season = int(s) if s.isdigit() else None
            episode = int(e) if e.isdigit() else None

        return {
            "path": str(file_path),
            "category": cat,
            "title": title,
            "year": year,
            "season": season,
            "episode": episode,
            "organized_by": session.sender_id,
        }

    def detect_resolution(self, path: Path) -> str:
        """Detect video resolution via filename (e.g. `1080p`) or default."""
        m = re.search(r"(\d{3,4}p)", path.name, re.IGNORECASE)
        return m.group(1) if m else "Unknown"

    async def show_preview_panel(self, session, src: Path, proposed_dest: Path) -> bool:
        """Show a preview with Confirm/Amend/Discard buttons."""
        kb = [
            [Button.inline("✅ Confirm", b"confirm")],
            [Button.inline("✏️ Amend",    b"amend")],
            [Button.inline("❌ Discard",  b"discard")],
        ]
        msg = await session.respond(
            f"Preview rename:\n`{src.name}` → `{proposed_dest.name}`",
            buttons=kb, parse_mode="markdown"
        )

        # wait for one callback
        @session.client.on(events.CallbackQuery)
        async def _(ev):
            if ev.query.user_id != session.sender_id:
                return
            await ev.answer()
            await msg.delete()
            session.data["preview_choice"] = ev.data  # store raw bytes
            raise asyncio.CancelledError  # break out of wait_event

        try:
            await session.client.wait_event(events.CallbackQuery, timeout=60)
        except asyncio.CancelledError:
            choice = session.data.pop("preview_choice", b"")
            return choice == b"confirm"
        except asyncio.TimeoutError:
            await session.respond("⏰ Preview timed out; discarding.")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10),
           retry=retry_if_exception_type(Exception))
    def safe_rename(self, src: Path, dest: Path):
        """Rename/move file with retries via tenacity."""
        src.rename(dest)

    def record_organized(self, metadata: dict):
        """Persist a successful organize operation into organized_tbl."""
        entry = {
            "path": metadata["path"],
            "title": metadata["title"],
            "category": metadata["category"],
            "year": metadata.get("year"),
            "season": metadata.get("season"),
            "episode": metadata.get("episode"),
            "resolution": self.detect_resolution(Path(metadata["path"])),
            "organized_by": metadata["organized_by"],
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "method": metadata.get("method", "manual"),
        }
        self.organized_tbl.insert(entry)

    async def show_bulk_preview_panel(self, session, items: List[dict]):
        """After first episode, show bulk items with Confirm/Amend/Skip."""
        for idx, item in enumerate(items, start=1):
            await asyncio.sleep(0)  # allow cancellation
            await session.respond(
                f"{idx}/{len(items)}  `{item['src'].name}` → `{item['dest'].name}`\n"
                "Reply `yes` to confirm, `no` to skip."
            )

    async def process_bulk_queue(self):
        """Iterate through pending bulk items and handle admin responses."""
        # Placeholder: implement per-item confirm/amend/skip flow in Sprint 7
        await asyncio.sleep(0)

    def record_error(self, context: dict):
        """Log error context into error_log_tbl."""
        self.error_log_tbl.insert({
            **context,
            "timestamp": __import__("datetime").datetime.now().isoformat()
        })

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
    def __init__(self, max_concurrent=3):
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
        # Notify if coming from queue
        if task.queue_position and task.queue_position > 0:
            await task.event.respond(
                f"✅ Your queue position is now 0 — download is starting!"
            )

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
            # 1) Active download cancellation
            if message_id in self.active_downloads:
                task = self.active_downloads.pop(message_id)
                await task.cancel()

                # Immediately start the next queued task, if any
                if self.queued_downloads:
                    next_task = self.queued_downloads.pop(0)
                    self.active_downloads[next_task.message_id] = next_task
                    stats.update_peak_concurrent(len(self.active_downloads))
                    asyncio.create_task(self._process_download(next_task))

                return True

            # 2) Remove from queue if pending
            for idx, task in enumerate(self.queued_downloads):
                if task.message_id == message_id:
                    self.queued_downloads.pop(idx)
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
        self.download_path = DOWNLOAD_DIR / filename
        self.ext = self.get_file_extension(filename)
        self.filename = filename if filename.endswith(self.ext) else f"{filename}{self.ext}"
        self.file_size = file_size
        self.start_time = None
        self.end_time = None
        self.progress = 0
        self.downloaded_bytes = 0
        self.current_speed = 0
        self.cancelled = False
        self.status_message = None
        self.process_message = None
        # Identify large files upfront and save as instance variable
        self.large_file = file_size > 500 * 1024 * 1024  # > 500 MB
        self.max_duration = MAX_DOWNLOAD_DURATION
        self.download_manager = download_manager
        self.queue_position = None
        self.last_update_time = None
        self.last_progress = 0
        
        # Log the file size classification for debugging
        logger.info(f"File {filename} size: {humanize.naturalsize(file_size)}, classified as {'large' if self.large_file else 'regular'} file")

    def get_file_extension(self, filename):
        """
        Determine a file extension:
         1) Prefer the filename's suffix
         2) Fallback to mimetypes.guess_extension
         3) Default to .bin
        """
        # 1) Prefer the original suffix if present
        suffix = Path(filename).suffix
        if suffix:
            return suffix

        # 2) Fallback to mimetypes
        guessed_mime, _ = mimetypes.guess_type(filename)
        if guessed_mime:
            ext = mimetypes.guess_extension(guessed_mime)
            if ext:
                return ext

        # 3) Ultimate fallback
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

            # Start the download, but enforce a max-duration
            try:
                async with timeout(self.max_duration):
                    await self.client.download_media(
                        self.event.message,
                        self.download_path,
                        progress_callback=self.progress_callback
                    )
            except asyncio.TimeoutError:
                # Auto-cancel on timeout
                reason = humanize.precisedelta(timedelta(seconds=self.max_duration))
                logger.warning(f"Download {self.filename} timed out after {reason}")
                await self.event.respond(
                    f"⚠️ Download timed out after {reason}. Cancelling automatically."
                )
                await self.cancel()
                BotStats.record_download(self.event.sender_id, 0, 0, success=False)
                return False

            if not self.cancelled:                
                # Record completion time & stats
                self.end_time = time.time()
                duration = self.end_time - self.start_time
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
        if Path(self.download_path).exists():
            try:
                Path(self.download_path).unlink()
            except Exception as e:
                logger.error(f"Failed to remove file during cancellation: {e}")

       # Send cancellation message (event.respond expects string paths)
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
                    # Treat anime like TV or Movie, but rooted under ANIME_DIR
                    if result['type'] == 'tv':
                        show  = result['title']
                        season = result['season']
                        # e.g. /data/.../Anime/My Anime/Season 01
                        target_dir = ANIME_DIR / show / f"Season {season:02d}"
                    elif result['type'] == 'movie':
                        title = result['title']
                        year  = result.get('year', '')
                        # e.g. /data/.../Anime/My Anime Movie (2023)
                        folder = f"{title} ({year})" if year else title
                        target_dir = ANIME_DIR / folder
                    else:
                        # Fallback for unknown
                        target_dir = ANIME_DIR / result['title']

                    target_dir.mkdir(parents=True, exist_ok=True)
                    await self.update_processing_message(
                        f"✅ Anime detected: {result['title']}\n"
                        f"Created directory: {target_dir}")
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
                # 1) Prepare ext & base name
                orig_name = Path(self.download_path).name
                ext       = Path(self.download_path).suffix
                # Build Jellyfin‑friendly base name (consistent with organization logic)
                if result.get('is_anime') and result.get('type') == 'tv':
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

                # --- Add resolution tag from filename ---
                resolution = guessit(orig_name).get('screen_size', '').lower()
                if resolution:
                    base = f"{base} [{resolution}]"

                # Sanitize file name
                safe_base   = re.sub(r'[\\/:"*?<>|]+', '', base)
                new_name_str = f"{safe_base}{ext}"
                new_path     = Path(self.download_path).with_name(new_name_str)
                logger.info(f"Renaming for TMDb → {self.download_path} → {new_path}")
                os.rename(self.download_path, new_path)
                self.download_path = str(new_path)

            # Step 3: Move file into its final library folder
            await self.update_processing_message("Moving to library")
            final_name = Path(self.download_path).name
            dest_path: Path = target_dir / final_name
            if dest_path.exists():
                base, ext = os.path.splitext(dest_path)
                dest_path = f"{base}_{int(time.time())}{ext}"
            logger.info(f"Moving final file → {self.download_path} → {dest_path}")
            shutil.move(self.download_path, str(dest_path))

            # Record automatic organization
            try:
                organizer.record_organized({
                    "path": str(dest_path),
                    "title": result.get("title", Path(dest_path).stem),
                    "category": result.get("type", "unknown"),
                    "year": result.get("year"),
                    "season": result.get("season"),
                    "episode": result.get("episode"),
                    "resolution": guessit(Path(dest_path).name).get("screen_size",""),
                    "organized_by": self.event.sender_id,
                    "method": "auto",
                })
            except Exception as e:
                logger.error(f"Failed to record auto-organize: {e}")

            processing_time = time.time() - self.end_time
            await self.update_processing_message(
                f"✅ Processed {final_name} in {processing_time:.1f}s\nMoved to: {dest_path}",
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

    async def search_tmdb(self) -> dict:
        """
        Use tmdbv3api to lookup movie or TV episode based on GuessIt.
        """
        info = guessit(self.filename)
        title = info.get('title')
        if not title:
            raise ValueError(f"Could not extract title from '{self.filename}'")

        loop = asyncio.get_running_loop()

        # TV episode
        if info.get('type') == 'episode':
            season  = info.get('season', 1)
            episode = info.get('episode', 1)
            # run blocking .search in thread
            results = await loop.run_in_executor(None, lambda: _tv.search(title))
            if not results:
                return {}
            show = results[0]
            # fetch specific episode details (blocking)
            try:
                ep_data = await loop.run_in_executor(
                    None,
                    lambda: _tv.tv_episode(show.id, season, episode)
                )
            except Exception:
                ep_data = {}
            return {
                "type":    "tv",
                "title":   show.name,
                "season":  season,
                "episode": episode,
                "is_anime": False,  # keyword lookup not in tmdbv3api
                "tmdb_id": show.id,
            }

        # Movie
        year = info.get('year') if info.get('type') == 'movie' else None
        results = await loop.run_in_executor(None, lambda: _movie.search(title))
        if not results:
            return {}
        m = results[0]
        return {
            "type":     "movie",
            "title":    m.title,
            "year":     m.release_date[:4] if getattr(m, 'release_date', None) else None,
            "is_anime": False,
            "tmdb_id":  m.id,
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

# Telegram client (dynamic session name)
SESSION_NAME = os.getenv("SESSION_NAME","bot_session")
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

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

# Create a single organizer instance (so it reuses the same TinyDB tables, etc.)
organizer = InteractiveOrganizer()

# Handlers
@client.on(events.NewMessage(pattern=r'^/propagate$'))
@admin_only
async def propagate_command(event):
    """
    Bulk-propagation: after a manual organize,
    find remaining episodes and ask yes/no per file.
    """
    # get last manual entry
    manual = [r for r in organized_tbl.all() if r.get("method","manual")=="manual"]
    entries = sorted(manual, key=lambda r: r["timestamp"], reverse=True)
    if not entries:
        return await event.respond("📁 No manual organizes to propagate from.")
    last = entries[0]
    folder = Path(last["path"]).parent
    title  = last["title"]
    season = last["season"]
    ep0    = last["episode"]
    items = find_remaining_episodes(folder, title, season, ep0)
    if not items:
        return await event.respond("✅ No remaining episodes found for bulk propagation.")
    
    # initialize session
    bulk_sessions[event.sender_id] = {"items": items, "index": 0}
    cur = items[0]
    # send first prompt with inline buttons
    await event.respond(
        f"📦 Bulk propagation started: 1/{len(items)}\n"
        f"`{cur['src'].name}` → `{cur['dest'].name}`",
        buttons=[
            [Button.inline("✅ Yes", f"bulk_ans:yes"),
             Button.inline("❌ No",  f"bulk_ans:no")]
        ]
    )

@client.on(events.CallbackQuery(pattern=r'^bulk_ans:(yes|no)$'))
async def bulk_answer(event):
    user = event.query.user_id
    if user not in bulk_sessions:
        return await event.answer(alert="No propagation in progress.")

    answer = event.data.decode().split(":",1)[1]
    state = bulk_sessions[user]
    items, idx = state["items"], state["index"]
    current = items[idx]

    # handle confirm/skip
    if answer == "yes":
        try:
            organizer.safe_rename(current["src"], current["dest"])
            # derive metadata
            dest_stem = Path(current["dest"]).stem
            title = dest_stem.split(" - ")[0]
            manual_entries = [r for r in organized_tbl.all() if r.get("method","manual")=="manual"]
            last_manual = sorted(manual_entries, key=lambda r: r["timestamp"], reverse=True)[0]
            category = last_manual["category"]
            organizer.record_organized({
                "path": str(current["dest"]),
                "title": title,
                "category": category,
                "year": None,
                "season": current["season"],
                "episode": current["episode"],
                "resolution": organizer.detect_resolution(current["src"]),
                "organized_by": user,
                "method": "auto",
            })
            await event.answer("Moved ✔️", alert=False)
        except Exception as e:
            await event.answer(f"Error: {e}", alert=True)
    else:
        await event.answer("Skipped ⏭️", alert=False)

    # advance
    state["index"] += 1
    if state["index"] < len(items):
        nxt = items[state["index"]]
        await event.edit(
            f"📦 Bulk propagation: {state['index']+1}/{len(items)}\n"
            f"`{nxt['src'].name}` → `{nxt['dest'].name}`",
            buttons=[
                [Button.inline("✅ Yes", f"bulk_ans:yes"),
                 Button.inline("❌ No",  f"bulk_ans:no")]
            ]
        )
    else:
        await event.edit("✅ Bulk propagation complete.", buttons=None)
        del bulk_sessions[user]

@client.on(events.NewMessage(pattern='^/organize$'))
@admin_only
async def organize_command(event):
    # ── DEBUG: dump raw contents of both directories ──
    raw_dl = list(Path(DOWNLOAD_DIR).iterdir())
    raw_oth = list(Path(OTHER_DIR).iterdir())
    await event.respond(
        f"DEBUG ▶ DOWNLOAD_DIR={DOWNLOAD_DIR}\n"
        f"  contains: {[p.name for p in raw_dl]}\n"
        f"DEBUG ▶ OTHER_DIR={OTHER_DIR}\n"
        f"  contains: {[p.name for p in raw_oth]}"
    )

    user = event.sender_id
    organize_sessions[user].clear()

    # use the organizer class to find candidates
    # debug: show what extensions we’re accepting
    await event.respond(f"DEBUG ▶ Accepting extensions: {sorted(MEDIA_EXTENSIONS)}")
    candidates = organizer.scan_for_candidates()
    if not candidates:
        return await event.respond(
            "✅ No files needing categorization.\n\n"
            f"(I saw {len(list(Path(DOWNLOAD_DIR).rglob('*')))} files on disk — "
            "check your extensions filter.)"
        )

    # build your button list
    buttons = []
    for idx, path in enumerate(candidates):
        key = f"file_{idx}"
        organize_sessions[user][key] = path
        buttons.append([Button.inline(path.name, f'org_file:{key}')])
    await event.respond("🗂️ Choose a file to categorize:", buttons=buttons)

@client.on(events.CallbackQuery(pattern=r'org_file:(.+)'))
async def pick_file(event):
    user = event.sender_id
    file_id = event.data.decode().split(':',1)[1]
    file_path = organize_sessions[user].get(file_id)
    if not file_path:
        return await event.respond("⚠️ File not found or session expired.")

    # use organizer to detect resolution
    res = organizer.detect_resolution(file_path)
    organize_sessions[user] = {
        "step": "choose_category",
        "file": file_path,
        "meta": {
            "resolution": res
        }
    }

    kb = [
      [ Button.inline("Movie","org_cat:movie"), Button.inline("TV","org_cat:tv") ],
      [ Button.inline("Anime","org_cat:anime"), Button.inline("Skip","org_cat:skip") ]
    ]
    # confirm selection
    await event.respond(f"🔍 Selected file: `{file_path.name}`\nDetected resolution: `{res}`", parse_mode="markdown")
    await event.edit(f"🗂️ File: {file_path.name}\nSelect category:", buttons=kb)  

@client.on(events.CallbackQuery(pattern=r'org_cat:(\w+)'))
async def pick_category(event):
    user = event.sender_id
    session = organize_sessions[user]
    choice  = event.data.decode().split(':',1)[1]

    if choice == 'skip':
        await event.edit(f"⏭️ Skipped `{session['file'].name}`.")
        organize_sessions.pop(user, None)
        return

    session['meta']['category'] = choice
    session['step'] = 'ask_title'

    guess = guessit(session['file'].name).get('title','')
    await event.edit(
        f"✏️ Category: **{choice.title()}**\n"
        f"Reply with *Title* (suggestion: `{guess}`)"
    )

@client.on(events.NewMessage)
async def organize_flow(event):
    user = event.sender_id
    if user not in organize_sessions:
        return

    session = organize_sessions.get(user)
    if 'step' not in session:
        return
    text = event.raw_text.strip()
    step = session['step']

    if step == 'ask_title':
        session['meta']['title'] = text
        session['step'] = 'ask_year_or_next'
        if session['meta']['category'] == 'movie':
            return await event.respond("✏️ Now reply with *Year* (e.g. 2023):")
        else:
            return await event.respond("✏️ Now reply with *Season number* (e.g. 1):")

    if step == 'ask_year_or_next':
        cat = session['meta']['category']
        if cat == 'movie':
            session['meta']['year'] = text
            await event.respond("✅ Got it! Moving the file…")
            await _run_finalize(event, session)
            return
        else:
            session['meta']['season'] = int(text)
            session['step'] = 'ask_episode'
            return await event.respond("✏️ Reply with *Episode number* (e.g. 3):")

    if step == 'ask_episode':
        session['meta']['episode'] = int(text)
        await event.respond("✅ Got it! Moving the file…")
        await _run_finalize(event, session)
        return

async def _run_finalize(event, session):
    """Handles folder creation, safe rename, DB record, and user feedback."""
    fpath = session['file']
    m     = session['meta']
    res   = m.get('resolution', '').upper()

    # Determine base folder & filename
    if m['category'] == 'movie':
        folder = MOVIES_DIR / f"{m['title']} ({m['year']})"
        base   = f"{m['title']} ({m['year']})"
    elif m['category'] == 'tv':
        folder = TV_DIR / m['title'] / f"Season {m['season']:02d}"
        ep     = f"S{m['season']:02d}E{m['episode']:02d}"
        base   = f"{m['title']} - {ep}"
    else:  # anime
        if 'episode' in m:
            folder = ANIME_DIR / m['title'] / f"Season {m['season']:02d}"
            ep     = f"S{m['season']:02d}E{m['episode']:02d}"
            base   = f"{m['title']} - {ep}"
        else:
            folder = ANIME_DIR / f"{m['title']} ({m.get('year','')})"
            base   = f"{m['title']} ({m.get('year','')})"

    # Build destination path
    folder.mkdir(parents=True, exist_ok=True)
    ext     = fpath.suffix
    new_name= f"{base} [{res}]{ext}" if res else f"{base}{ext}"
    dest    = folder / new_name

    logger.info(f"Organize: moving `{fpath}` → `{dest}`")
    try:
        organizer.safe_rename(fpath, dest)
        organizer.record_organized({
            "path": str(dest),
            "title": m["title"],
            "category": m["category"],
            "year": m.get("year"),
            "season": m.get("season"),
            "episode": m.get("episode"),
            "resolution": res,
            "organized_by": event.sender_id
        })
        await event.respond(f"✅ Moved to `{dest}`")
    except Exception as e:
        organizer.record_error({
            "error": str(e),
            "file": str(fpath),
            "stage": "finalize"
        })
        await event.respond(f"⚠️ Could not move file: {e}")

    # Clean up session
    organize_sessions.pop(event.sender_id, None)
    await event.respond("🗂️ Send /organize to categorize another file, or /propagate to propagate.")

# /organized command
@client.on(events.NewMessage(pattern=r'^/organized$'))
@admin_only
async def organized_command(event):
    await show_organized_page(event, offset=0)

@client.on(events.CallbackQuery(pattern=r'^org_page:(\d+)$'))
async def organized_page_callback(event):
    offset = int(event.data.decode().split(":")[1])
    await show_organized_page(event, offset=offset)

async def show_organized_page(event, offset=0):
    # Only manually organized entries
    manual = [e for e in organized_tbl.all() if e.get("method","manual") == "manual"]
    manual_sorted = sorted(manual, key=lambda r: r.get("timestamp",""), reverse=True)
    total = len(manual_sorted)
    page = manual_sorted[offset:offset+10]
    if not page:
        return await event.respond("📁 No organized entries found.")

    buttons = []
    for entry in page:
        label = f"{entry['title']} ({entry.get('year','')})"
        ts = humanize.naturaltime(datetime.fromisoformat(entry['timestamp']))
        eid = entry.doc_id
        buttons.append([
            Button.inline(f"🔁 {label}", f"reorg:{eid}"),
            Button.inline(f"🕓 {ts}", f"noop:{eid}"),
            Button.inline(f"🗑️", f"delorg:{eid}")
        ])

    nav = []
    if offset > 0:
        nav.append(Button.inline("◀️ Prev", f"org_page:{max(0, offset-10)}"))
    if offset + 10 < total:
        nav.append(Button.inline("▶️ Next", f"org_page:{offset+10}"))
    if nav:
        buttons.append(nav)

    text = f"📁 Recently organized files ({offset+1}–{offset+len(page)} of {total}):"
    await event.respond(text, buttons=buttons)

@client.on(events.NewMessage(pattern=r'^/history$'))
@admin_only
async def history_command(event):
    await show_history_page(event, offset=0, detail_eid=None)

@client.on(events.CallbackQuery(pattern=r'^hist_page:(\d+)$'))
async def history_page_callback(event):
    offset = int(event.pattern_match.group(1)) # Use pattern_match for safety
    # Call show_history_page to display the list view for the new offset
    await show_history_page(event, offset=offset, detail_eid=None)

# New callback for viewing item details
@client.on(events.CallbackQuery(pattern=r'^hist_detail:(\d+):(\d+)$')) # eid:offset
async def history_detail_callback(event):
    eid = int(event.pattern_match.group(1))
    offset = int(event.pattern_match.group(2)) # The offset of the list page we came from
    # Call show_history_page to display the detail view
    await show_history_page(event, offset=offset, detail_eid=eid)

async def show_history_page(event, offset=0, detail_eid=None):
    all_sorted = sorted(organized_tbl.all(), key=lambda r: r.get("timestamp", ""), reverse=True)
    total_entries = len(all_sorted)
    entries_per_page = 5

    # --- DETAIL VIEW ---
    if detail_eid:
        entry = organized_tbl.get(doc_id=detail_eid)
        if not entry:
            await event.answer("⚠️ Entry not found.", alert=True)
            # Fallback to list view at the current offset
            return await show_history_page(event, offset=offset, detail_eid=None)

        name = Path(entry['path']).name
        ts = humanize.naturaltime(datetime.fromisoformat(entry['timestamp']))
        method = entry.get("method", "manual").capitalize()
        category = entry.get("category", "N/A").capitalize()
        resolution = entry.get("resolution", "N/A")
        year = entry.get("year", "")
        season = entry.get("season")
        episode = entry.get("episode")

        title_display = entry.get('title', Path(name).stem)
        if year and category.lower() == 'movie':
            title_display += f" ({year})"
        elif season is not None and episode is not None and category.lower() != 'movie': # Check if category is not movie and season/ep exist
            title_display += f" - S{int(season):02d}E{int(episode):02d}"


        text = f"📜 **History Item Details**\n\n" \
               f"🎬 **Title:** `{title_display}`\n" \
               f"📄 **Original File:** `{name}`\n" \
               f"⚙️ **Method:** `{method}`\n" \
               f"🗂️ **Category:** `{category}`\n"
        if resolution and resolution != "N/A":
             text += f"📺 **Resolution:** `{resolution}`\n"
        text += f"🕓 **Time:** _{ts}_"

        buttons = [
            [Button.inline(f"🔁 Reorganize", f"reorg:{detail_eid}"),
             Button.inline(f"🗑️ Delete Entry", f"delorg:{detail_eid}")],
            [Button.inline(f"◀️ Back to History (Page {(offset // entries_per_page) + 1})", f"hist_page:{offset}")]
        ]
        
        try:
            # This view is typically reached via a CallbackQuery, so event.edit() is appropriate.
            await event.edit(text, buttons=buttons, parse_mode="markdown")
        except Exception as e:
            logger.error(f"Error editing history detail view: {e}")
            await event.answer("Error displaying details. Please try again.", alert=True)

    # --- LIST VIEW ---
    else:
        if offset >= total_entries and offset > 0:
            offset = max(0, total_entries - entries_per_page) 
            if offset < 0: offset = 0

        page_entries = all_sorted[offset : offset + entries_per_page]

        if not page_entries and total_entries > 0:
             offset = max(0, total_entries - entries_per_page)
             if offset < 0: offset = 0
             page_entries = all_sorted[offset : offset + entries_per_page]
        elif not page_entries and total_entries == 0:
             message_text = "📁 No history available."
             if isinstance(event, events.CallbackQuery.Event):
                try:
                    await event.edit(message_text, buttons=None)
                except Exception as e:
                    logger.error(f"Error editing to 'No history': {e}")
                    await event.answer("No history available.") # Answer callback
             elif isinstance(event, events.NewMessage.Event):
                await event.respond(message_text)
             return

        current_page_num = (offset // entries_per_page) + 1
        total_pages = (total_entries + entries_per_page - 1) // entries_per_page
        if total_pages == 0 and total_entries > 0 : total_pages = 1

        message_text = f"📜 **History - Page {current_page_num} of {total_pages}** ({total_entries} total entries)\n\n"
        action_buttons_rows = []

        for i, entry in enumerate(page_entries):
            name = Path(entry['path']).name
            ts = humanize.naturaltime(datetime.fromisoformat(entry['timestamp']))
            method = entry.get("method", "manual").capitalize()
            eid = entry.doc_id
            
            title = entry.get('title', Path(name).stem)
            display_name = title if len(title) < 35 else title[:32] + "..."

            message_text += f"**{offset + i + 1}.** `{display_name}`\n" \
                            f"   └─ _{ts}_ `[{method}]`\n"
            action_buttons_rows.append(
                [Button.inline(f"🔍 Details for #{offset + i + 1}", f"hist_detail:{eid}:{offset}")]
            )

        nav_row = []
        if offset > 0:
            nav_row.append(Button.inline("◀️ Prev", f"hist_page:{max(0, offset - entries_per_page)}"))
        if offset + entries_per_page < total_entries:
            nav_row.append(Button.inline("▶️ Next", f"hist_page:{offset + entries_per_page}"))
        
        if nav_row:
            action_buttons_rows.append(nav_row)

        # Send or Edit the message based on the event type
        if isinstance(event, events.CallbackQuery.Event):
            try:
                await event.edit(message_text, buttons=action_buttons_rows, parse_mode="markdown")
            except Exception as e:
                # Handle "message is not modified" error specifically if needed, or log others
                if "Message actual text is empty" in str(e) or "message to edit not found" in str(e): # Example specific error checks
                    logger.warning(f"Attempted to edit but failed (possibly deleted message or bad state): {e}")
                    # May need to send a new message if edit context is lost, but be careful.
                    # For now, just answer the callback.
                    await event.answer("Could not update view. Please try /history again.", alert=True)
                elif "message not modified" not in str(e).lower(): # Don't log "not modified" as an error
                    logger.error(f"Error editing history list view: {e}")
                    await event.answer("Error updating list.", alert=True)
                else:
                    await event.answer() # Acknowledge if not modified
        elif isinstance(event, events.NewMessage.Event):
            await event.respond(message_text, buttons=action_buttons_rows, parse_mode="markdown")
        else:
            logger.warning(f"show_history_page called with unexpected event type: {type(event)}")

@client.on(events.CallbackQuery(pattern=r'reorg:(\d+)'))
async def reorganize_entry(event):
    eid = int(event.data.decode().split(':')[1])
    entry = organized_tbl.get(doc_id=eid)
    if not entry:
        return await event.respond("⚠️ Entry not found.")
    fake_event = event  # reuse current event
    session = {
        "file": Path(entry['path']),
        "meta": {
            "title": entry['title'],
            "category": entry['category'],
            "year": entry.get('year'),
            "season": entry.get('season'),
            "episode": entry.get('episode'),
            "resolution": entry.get('resolution'),
        }
    }
    await _run_finalize(fake_event, session)

@client.on(events.CallbackQuery(pattern=r'delorg:(\d+)'))
async def delete_organized_record(event):
    eid = int(event.data.decode().split(':')[1])
    organized_tbl.remove(doc_ids=[eid])
    await event.answer("🗑️ Deleted record.", alert=False)
    await event.edit("✅ Record deleted.")

@client.on(events.NewMessage(pattern='/cancel'))
async def cancel_organize(event):
    user = event.sender_id
    if user in organize_sessions:
        organize_sessions.pop(user, None)
        return await event.respond("🚫 Categorization cancelled.")

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
        "/organize - 🗂️ Organize files into categories (admin only)\n"
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
        "tv_dir": TV_DIR, # Changed from music_dir to tv_dir
        "music_dir": MUSIC_DIR,
        "other_dir": OTHER_DIR
    }
    dir_checks = []
    for name, path in directories.items():
        if path.exists() and path.access(os.R_OK | os.W_OK):
            free = shutil.disk_usage(path).free
            dir_checks.append(f"✅ {name}: OK ({humanize.naturalsize(free)} free)") # Use humanize
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