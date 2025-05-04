import os
import signal
import time
import asyncio
import logging
import json
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, DocumentAttributeAudio
import humanize
import aiohttp
import shutil
from guessit import guessit
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration (should be in a config file)
API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')

# Directory Configuration
BASE_DIR = os.path.expanduser("~/jellyfin")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "Downloads")
MOVIES_DIR = os.path.join(BASE_DIR, "Movies")
TV_DIR = os.path.join(BASE_DIR, "TV")
ANIME_DIR = os.path.join(BASE_DIR, "Anime") # Added Anime directory
MUSIC_DIR = os.path.join(BASE_DIR, "Music")
OTHER_DIR = os.path.join(BASE_DIR, "Other")

# Ensure directories exist
for directory in [DOWNLOAD_DIR, MOVIES_DIR, TV_DIR, ANIME_DIR, MUSIC_DIR, OTHER_DIR]:
    os.makedirs(directory, exist_ok=True)

# Movie‐year pattern: title + year between 1900–2099
MOVIE_YEAR_REGEX = r'(?P<title>.+?)[\.\s_\(\[]+(?P<year>(?:19|20)\d{2})(?=[\.\s_\)\[]|$)'

# Add global shutdown flags
shutdown_in_progress = False
force_shutdown = False
last_sigint_time = 0
FORCE_SHUTDOWN_TIMEOUT = 10  # seconds between consecutive Ctrl+C to force shutdown

# File paths
USERS_FILE = os.path.join(BASE_DIR, "active_users.json")
# Check if the users file exists, if not create it
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump([], f)  # Create an empty JSON array if it doesn't exist

# Log file
LOG_FILE = "bot.log"
# Check if the log file exists, if not create it
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w") as f:
        pass  # Create an empty log file if it doesn't exist
# Set up logging to file
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# Bot Stats
class BotStats:
    def __init__(self):
        self.start_time = datetime.now()
        self.files_handled = 0
        self.successful_downloads = 0
        self.failed_downloads = 0
        self.total_data = 0  # in bytes
        self.peak_concurrent = 0
        self.download_times = []  # list of seconds
        self.download_speeds = []  # list of bytes/second

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
        if not self.download_speeds:
            return 0
        return sum(self.download_speeds) / len(self.download_speeds)

    def get_average_time(self):
        if not self.download_times:
            return 0
        return sum(self.download_times) / len(self.download_times)
    
# Signal handlers for graceful shutdown
def signal_handler(sig, frame):
    global shutdown_in_progress, force_shutdown, last_sigint_time
    current_time = time.time()
    
    if sig == signal.SIGINT:
        if current_time - last_sigint_time < FORCE_SHUTDOWN_TIMEOUT:
            logger.warning("Second interrupt received within timeout. Forcing immediate shutdown!")
            force_shutdown = True
            os._exit(1)  # Force exit without cleanup
        else:
            last_sigint_time = current_time
            if not shutdown_in_progress:
                logger.info("Interrupt received, initiating graceful shutdown...")
                shutdown_in_progress = True
                asyncio.create_task(shutdown())
            else:
                logger.info("Shutdown already in progress. Press Ctrl+C again within 10 seconds for forced exit.")

async def shutdown():
    """Perform graceful shutdown of the bot"""
    global shutdown_in_progress, force_shutdown, all_users
    
    if force_shutdown:
        logger.warning("Forced shutdown initiated!")
        return
        
    logger.info("Starting graceful shutdown sequence...")
    
    try:
        # 1. Stop accepting new downloads
        download_manager.accepting_new_downloads = False
        
        # 2. Notify users about shutdown
        shutdown_message = "🔄 Bot is shutting down for maintenance. Currently queued downloads will be completed."
        current_active_users = set()
        for task in list(download_manager.active_downloads.values()):
            try:
                current_active_users.add(task.event.sender_id)
                await task.event.respond(shutdown_message)
            except Exception as e:
                logger.error(f"Failed to notify user about shutdown: {e}")
        
        # 3. Wait for active downloads to complete (with timeout)
        if download_manager.active_downloads:
            logger.info(f"Waiting for {len(download_manager.active_downloads)} active downloads to complete...")
            try:
                # Wait up to 5 minutes for downloads to complete
                for _ in range(30):  # 30 x 10 seconds = 5 minutes
                    if force_shutdown or not download_manager.active_downloads:
                        break
                    await asyncio.sleep(10)
                    logger.info(f"Still waiting for {len(download_manager.active_downloads)} downloads...")
            except Exception as e:
                logger.error(f"Error while waiting for downloads to complete: {e}")
        
        # 4. Cancel any remaining downloads
        remaining_downloads = list(download_manager.active_downloads.values())
        for task in remaining_downloads:
            try:
                logger.info(f"Cancelling download: {task.filename}")
                await task.cancel()
            except Exception as e:
                logger.error(f"Error cancelling download: {e}")

        # 5. Send final offline notification
        final_message = "🔴 Bot is now offline. Thank you for using our service!"
        try:
            # Send to all users who have ever interacted with the bot, not just current session
            for user_id in all_users:
                await client.send_message(user_id, final_message)

            # Save all users for next startup (using the global all_users set)
            save_active_users(all_users)
        except Exception as e:
            logger.error(f"Error sending final shutdown message: {e}")
        
        # 6. Final cleanup and disconnect
        logger.info("Disconnecting client...")
        await client.disconnect()
        logger.info("Shutdown complete")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        # Ensure the program exits
        os._exit(0)

# Save_active_users function to update the global all_users
def save_active_users(users):
    """Save active users to file"""
    global all_users
    
    # Ensure all_users is updated with any new users
    all_users.update(users)
    
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(list(all_users), f)
    except Exception as e:
        logger.error(f"Failed to save active users: {e}")

# Add a function to explicitly save the all_users set to file
def save_all_users_to_file():
    """Save the global all_users set to file"""
    global all_users
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(list(all_users), f)
        logger.info(f"Saved {len(all_users)} users to file")
    except Exception as e:
        logger.error(f"Failed to save all users to file: {e}")

# Add a periodic user save function
async def periodic_user_save():
    """Save the user list to file every hour"""
    while not shutdown_in_progress:
        try:
            # Save all users to file
            save_all_users_to_file()
            # Wait for an hour
            await asyncio.sleep(3600)  # 3600 seconds = 1 hour
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic user save: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying

# Load active users from file
def load_active_users():
    """Load active users from file"""
    try:
        with open(USERS_FILE, 'r') as f:
            return set(json.load(f))
    except Exception as e:
        logger.error(f"Failed to load active users: {e}")
        return set()
    
# Initialize the global set:
all_users = load_active_users()


def save_all_users():
    """Save all users to a global variable"""
    global all_users
    all_users = load_active_users()

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
        # Check the mime type or other indicators to determine the extension
        if filename.endswith('.mp4'):
            return '.mp4'
        elif filename.endswith('.avi'):
            return '.avi'
        elif filename.endswith('.flv'):
            return '.flv'
        elif filename.endswith('.mov'):
            return '.mov'
        # Add more formats as needed
        return '.mkv'  # Default to .mkv

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
                stats.add_download(self.file_size, duration, success=True)

                # Send completion message
                await self.send_completion_message(duration)

                return True
            return False
        except Exception as e:
            logger.error(f"Download error for {self.filename}: {e}")
            await self.event.respond(f"⚠️ Download failed for {self.filename}: {str(e)}")
            stats.add_download(0, 0, success=False)
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
            processor = MediaProcessor(self.filename, TMDB_API_KEY)
            result = await processor.search_tmdb()
            logger.info("search_tmdb result → %s", result)

            # Step 2: Decide where to put it
            if result:
                # 2a) Anime goes under Anime/<Title>
                if result.get('is_anime'):
                    target_dir = os.path.join(ANIME_DIR, result['title'])
                    anime_series_dir = target_dir
                    os.makedirs(anime_series_dir, exist_ok=True)
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
                        target_dir = os.path.join(TV_DIR, folder_struct)
                    else:
                        target_dir = os.path.join(TV_DIR, show_name, f"Season {season_no:02d}")

                    os.makedirs(target_dir, exist_ok=True)
                    await self.update_processing_message(
                        f"✅ TV: {show_name} S{season_no:02d}E{episode_no:02d}"
                    )

                # 2c) Movies
                elif result['type'] == 'movie':
                    title    = result['title']
                    year     = result.get('year', '')
                    folder_name = f"{title} ({year})" if year else title

                    target_dir = os.path.join(MOVIES_DIR, folder_name)
                    os.makedirs(target_dir, exist_ok=True)
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

    def __init__(self, filename: str, tmdb_api_key: str):
        self.filename = filename
        self.tmdb_api_key = tmdb_api_key

    async def fetch_json(self, session: aiohttp.ClientSession, url: str, params: dict) -> dict:
        params["api_key"] = self.tmdb_api_key
        async with session.get(url, params=params) as resp:
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

    async def tmdb_search_movie(self, title: str, year: int = None) -> dict:
        search_url = f"{self.TMDB_URL}/search/movie"
        params = {"query": title, "api_key": self.tmdb_api_key}
        if year:
            params["year"] = year

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params=params) as resp:
                data = await resp.json()

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
            # ... other fields
        }

    async def tmdb_search_tv(self, title: str, season: int, episode: int) -> dict:
        # Existing TV search code
        search_url = f"{self.TMDB_URL}/search/tv"
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params={"query": title, "api_key": self.tmdb_api_key}) as resp:
                results = (await resp.json()).get("results", [])

        if not results:
            return {}

        show_id = results[0]["id"]
        is_anime = await self.check_anime_tag(show_id, "tv")

        # Existing episode data retrieval
        return {
            "type": "tv",
            "title": results[0].get("name", title),
            "season": season,
            "episode": episode,
            "is_anime": is_anime,
            "tmdb_id": show_id,
            # ... other fields
        }
    
    async def check_anime_tag(self, tmdb_id: int, media_type: str) -> bool:
        """Check if 'anime' exists in TMDb keywords"""
        endpoint = f"{self.TMDB_URL}/{media_type}/{tmdb_id}/keywords"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params={"api_key": self.tmdb_api_key}) as resp:
                    data = await resp.json()
                    # Handle both movie and TV keyword formats
                    keywords = data.get("keywords", []) if media_type == "movie" else data.get("results", [])
                    return any(k["name"].lower() == "anime" for k in keywords)
        except Exception as e:
            logger.error(f"TMDb keyword check failed: {e}")
            return False

# Initialize objects
stats = BotStats()
download_manager = DownloadManager()

# Initialize the client
client = TelegramClient('jellyfin_bot', API_ID, API_HASH)


# Add shutdown command handler
@client.on(events.NewMessage(pattern='/shutdown'))
async def shutdown_command(event):
    """Handler for /shutdown command - admin only"""
    # Simple admin check - you might want to replace this with your own logic
    ADMIN_IDS = [int(id) for id in os.environ.get('ADMIN_IDS', '').split(',') if id]
    
    if not ADMIN_IDS:
        await event.respond("⚠️ No admin IDs configured. Shutdown command disabled.")
        return
        
    if event.sender_id not in ADMIN_IDS:
        await event.respond("⚠️ You don't have permission to shut down the bot.")
        return
    
    global shutdown_in_progress
    if shutdown_in_progress:
        await event.respond("⚠️ Shutdown already in progress.")
        return
        
    await event.respond("🔄 Initiating graceful shutdown. Bot will complete current downloads before exiting.")
    shutdown_in_progress = True
    asyncio.create_task(shutdown())

# Add an admin command to view user count
@client.on(events.NewMessage(pattern='/users'))
async def users_command(event):
    """Handler for /users command - admin only"""
    # Simple admin check - you might want to replace this with your own logic
    ADMIN_IDS = [int(id) for id in os.environ.get('ADMIN_IDS', '').split(',') if id]
    
    if not ADMIN_IDS:
        await event.respond("⚠️ No admin IDs configured. Users command disabled.")
        return
        
    if event.sender_id not in ADMIN_IDS:
        await event.respond("⚠️ You don't have permission to view user statistics.")
        return
    
    global all_users
    
    # Force save current users
    save_all_users_to_file()
    
    await event.respond(
        f"👥 User Statistics\n\n"
        f"Total unique users: {len(all_users)}\n"
        f"User IDs are saved in: {USERS_FILE}"
    )

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
    """Handler for /stats command"""

    global all_users
    # Check if the user is already in the active users list
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users(all_users)

    # Get the current stats
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
    """Handler for /queue command"""

    global all_users
    # Check if the user is already in the active users list
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users(all_users)

    # Get the queue status
    queue_status = download_manager.get_queue_status()
    active_downloads = queue_status["active"]
    queued_downloads = queue_status["queued"]

    # Build the response message
    message = "📋 DOWNLOAD QUEUE STATUS\n\n"
    message += f"⏳ Active downloads: {len(active_downloads)}/{download_manager.max_concurrent}\n"
    message += f"🔄 Queued files: {len(queued_downloads)}\n\n"

    # Add active downloads
    if active_downloads:
        message += "🔽 CURRENTLY DOWNLOADING:\n"
        for i, (msg_id, filename, progress) in enumerate(active_downloads, 1):
            message += f"{i}️⃣ {filename} ({progress:.0f}% complete)\n"
        message += "\n"

    # Add queued downloads
    if queued_downloads:
        message += "⏭️ NEXT IN QUEUE:\n"
        for i, (pos, msg_id, filename, size) in enumerate(queued_downloads, 1):
            message += f"{i}. {filename} ({humanize.naturalsize(size)})\n"

    message += "\n🛑 To cancel a download: press ❌ next to the file"

    # Create cancel buttons for active downloads
    buttons = []
    for msg_id, filename, _ in active_downloads:
        # Truncate filename if too long
        display_name = filename[:20] + "..." if len(filename) > 20 else filename
        buttons.append([Button.inline(f"❌ Cancel: {display_name}", f"cancel_{msg_id}")])

    # Add buttons for queued downloads too
    for _, msg_id, filename, _ in queued_downloads:
        display_name = filename[:20] + "..." if len(filename) > 20 else filename
        buttons.append([Button.inline(f"❌ Cancel: {display_name}", f"cancel_{msg_id}")])

    if buttons:
        await event.respond(message, buttons=buttons)
    else:
        await event.respond(message)

@client.on(events.NewMessage(pattern='/test'))
async def test_command(event):
    """Handler for /test command"""

    global all_users
    # Check if the user is already in the active users list
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users(all_users)

    # Testing directory access
    directories = {
        "telegram_download_dir": DOWNLOAD_DIR,
        "movies_dir": MOVIES_DIR,
        "tv_dir": TV_DIR,
        "music_dir": MUSIC_DIR,
        "other_dir": OTHER_DIR
    }

    dir_checks = []
    for name, path in directories.items():
        if os.path.exists(path) and os.access(path, os.R_OK | os.W_OK):
            free_space = shutil.disk_usage(path).free
            dir_checks.append(f"✅ {name}: OK ({humanize.naturalsize(free_space)} free)")
        else:
            dir_checks.append(f"❌ {name}: NOT ACCESSIBLE")

    # Test internet connection
    internet_check = "✅ Internet connection: OK"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.google.com", timeout=5) as response:
                if response.status != 200:
                    internet_check = "❌ Internet connection: Failed (HTTP error)"
    except Exception:
        internet_check = "❌ Internet connection: Failed (connection error)"

    # Test Telethon client
    telethon_check = "✅ Telethon client: Connected" if client.is_connected() else "❌ Telethon client: Disconnected"

    # Test TMDb API if configured
    tmdb_check = "✅ TMDb API: Connected"
    if TMDB_API_KEY:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.themoviedb.org/3/configuration?api_key={TMDB_API_KEY}",
                    timeout=5
                ) as response:
                    if response.status != 200:
                        tmdb_check = "❌ TMDb API: Failed (HTTP error)"
        except Exception:
            tmdb_check = "❌ TMDb API: Failed (connection error)"
    else:
        tmdb_check = "⚠️ TMDb API: Not configured"

    # Test TMDb API with a title containing special characters
    test_title = "What the #$*! Do We (K)now!?"
    test_year = 2014  # Adjust year as needed
    tmdb_check = await download_manager.tmdb_search_movie(test_title, test_year)

    if tmdb_check:
        tmdb_result_message = f"✅ TMDb verification successful for: {test_title}"
    else:
        tmdb_result_message = f"❌ TMDb verification failed for: {test_title}"

    # Test network speed
    start_time = time.time()
    file_size = 0
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png") as response:
                if response.status == 200:
                    data = await response.read()
                    file_size = len(data)
    except Exception:
        pass

    duration = time.time() - start_time
    network_speed = file_size / duration if duration > 0 else 0

    # Format the message
    message = "🔍 SYSTEM TEST RESULTS\n\n"

    message += "📁 Directory Checks\n"
    message += "\n".join(dir_checks)
    message += "\n\n"

    message += "🔧 System Checks\n"
    message += f"{internet_check}\n"
    message += f"{telethon_check}\n"
    message += "\n"

    message += "🌐 API Connections\n"
    message += "✅ Telegram Bot API: Connected\n"
    message += f"{tmdb_check}\n"
    message += f"{tmdb_result_message}\n"
    message += "\n"

    message += "⚡ Performance\n"
    message += f"⚡ Network speed: {humanize.naturalsize(network_speed)}/s\n"
    message += f"⏱️ API response time: {int(duration * 1000)} ms\n"
    message += "\n"

    # Overall status
    if "❌" in message:
        message += "📊 Overall Status: Some issues detected"
    else:
        message += "📊 Overall Status: All systems operational"

    await event.respond(message)

@client.on(events.CallbackQuery(pattern=r'cancel_(\d+)'))
async def cancel_download_callback(event):
    """Handle cancellation button clicks"""
    message_id = int(event.data.decode('utf-8').split('_')[1])
    success = await download_manager.cancel_download(message_id)

    if success:
        await event.answer("Download cancelled successfully")
    else:
        await event.answer("Could not find the download task")

    # Update the queue message
    await queue_command(event)

@client.on(events.NewMessage)
async def handle_media(event):
    """Handle incoming media messages"""
    # Check if this is a media message
    if not event.message.media:
        return
    
    global all_users
    # Check if the user is already in the active users list
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users(all_users)

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
    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, 
            lambda s=sig: asyncio.create_task(
                handle_signal(s)
            )
        )

    # Start the client
    await client.start(bot_token=BOT_TOKEN)

    # Log startup
    logger.info("Bot started")

    # Start periodic user save task
    user_save_task = asyncio.create_task(periodic_user_save())

    # Notify previous users about bot restart
    previous_users = load_active_users()
    if previous_users:
        startup_message = (
            "🟢 Bot is back online and ready!\n\n"
            "Send me any media file and I will download it to your Jellyfin library.\n"
            "Use /help to see available commands."
        )
        for user_id in previous_users:
            try:
                await client.send_message(user_id, startup_message)
            except Exception as e:
                logger.error(f"Failed to send startup message to user {user_id}: {e}")


    # Run the client until disconnected
    try:
        await client.run_until_disconnected()
    finally:
        # Cancel the periodic save task when disconnected
        user_save_task.cancel()

async def handle_signal(sig):
    """Async signal handler that calls the main signal handler"""
    signal_handler(sig, None)

if __name__ == '__main__':
    # Run the bot
    asyncio.run(main())