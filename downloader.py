import asyncio
import time
import logging
import mimetypes
import shutil
import os
import re
from pathlib import Path
from datetime import timedelta

import humanize
from async_timeout import timeout
from telethon import Button
from guessit import guessit

from config import (
    DOWNLOAD_DIR, MAX_DOWNLOAD_DURATION, TMDB_API_KEY,
    LOW_CONFIDENCE, HIGH_CONFIDENCE,
    MOVIES_DIR, TV_DIR, ANIME_DIR, OTHER_DIR, BASE_DIR
)
from stats import BotStats
from media_processor import MediaProcessor
from organizer import InteractiveOrganizer
from utils import similarity
from ui.messages import Messages
from ui.buttons import Buttons
from ui.formatters import Formatters



logger = logging.getLogger(__name__)

def sanitize_path_component(name: str) -> str:
    """
    Sanitize a path component (file or directory name) for cross-platform compatibility.
    Handles both Windows and Linux/Unix systems.
    
    Windows invalid characters: < > : " / \ | ? *
    Linux/Unix: only / and null byte are invalid, but we sanitize more for consistency
    """
    import platform
    
    # Always replace forward slash (invalid on all systems when used in filename)
    name = name.replace('/', '_')
    
    # Replace colon with space-dash for readability (Windows restriction, but safe everywhere)
    name = name.replace(':', ' -')
    
    # Replace other potentially problematic characters
    # These are invalid on Windows and can cause issues on some filesystems
    invalid_chars = '<>"|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    
    # Backslash handling: invalid on Windows, but valid on Linux
    # Replace it for consistency across platforms
    name = name.replace('\\', '_')
    
    # Remove leading/trailing spaces and dots
    # Windows doesn't allow these, and they can be problematic on other systems too
    name = name.strip('. ')
    
    # Ensure the name is not empty after sanitization
    if not name:
        name = 'unnamed'
    
    return name

# Create a local organizer instance for auto-organization
organizer = InteractiveOrganizer()

class DownloadManager:
    def __init__(self, max_concurrent=3):
        self.active_downloads = {}  # message_id: DownloadTask
        self.queued_downloads = []  # list of DownloadTask
        self.max_concurrent = max_concurrent
        self.lock = asyncio.Lock()
        self.accepting_new_downloads = True

    async def add_download(self, task):
        # Check if accepting new downloads
        if not self.accepting_new_downloads:
            await task.event.respond(Messages.DOWNLOAD_NOT_ACCEPTING)
            logger.info("Not accepting new downloads at the moment.")
            return -1
        
        async with self.lock:
            if len(self.active_downloads) < self.max_concurrent:
                self.active_downloads[task.message_id] = task
                # Update peak concurrent stats (using global stats for now)
                BotStats.global_stats.update_peak_concurrent(len(self.active_downloads))
                asyncio.create_task(self._process_download(task))
                return 0  # Started immediately
            else:
                self.queued_downloads.append(task)
                return len(self.queued_downloads)  # Position in queue

    async def _process_download(self, task):
        # Notify if coming from queue
        if task.queue_position and task.queue_position > 0:
            await task.event.respond(Messages.QUEUE_STARTING)

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
                    BotStats.global_stats.update_peak_concurrent(len(self.active_downloads))
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
                    BotStats.global_stats.update_peak_concurrent(len(self.active_downloads))
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

class DownloadTask:
    def __init__(self, client, event, message_id, filename, file_size, download_manager, session=None):
        self.client = client
        self.event = event
        self.message_id = message_id
        
        # SECURITY: Sanitize filename to prevent path traversal attacks
        from utils import sanitize_filename, validate_path_within_base
        safe_filename = sanitize_filename(filename)
        
        # Log if filename was modified for security
        if safe_filename != filename:
            logger.warning(f"Filename sanitized: '{filename}' -> '{safe_filename}'")
        
        self.download_path = DOWNLOAD_DIR / safe_filename
        
        # SECURITY: Validate that resolved path is within DOWNLOAD_DIR
        if not validate_path_within_base(self.download_path, DOWNLOAD_DIR):
            error_msg = f"Security: Path traversal attempt blocked for file: {filename}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.ext = self.get_file_extension(safe_filename)
        self.filename = safe_filename if safe_filename.endswith(self.ext) else f"{safe_filename}{self.ext}"
        self.file_size = file_size
        self.start_time = None
        self.end_time = None
        self.progress = 0
        self.downloaded_bytes = 0
        self.current_speed = 0
        self.cancelled = False
        self.status_message = None
        self.process_message = None
        # Identify large files upfront
        self.large_file = file_size > 500 * 1024 * 1024  # > 500 MB
        self.max_duration = MAX_DOWNLOAD_DURATION
        self.download_manager = download_manager
        self.queue_position = None
        self.last_update_time = None
        self.last_progress = 0
        self.session = session # aiohttp session
        
        logger.info(f"File {safe_filename} size: {humanize.naturalsize(file_size)}, classified as {'large' if self.large_file else 'regular'} file")


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
            file_type_indicator = Messages.MEDIA_LARGE_FILE if self.large_file else Messages.MEDIA_REGULAR_FILE
            update_interval = "1 minute" if self.large_file else "15 seconds"
            
            await self.update_queue_message(
                Messages.DOWNLOAD_INITIALIZING.format(
                    filename=self.filename,
                    file_type=file_type_indicator,
                    dir=DOWNLOAD_DIR,
                    interval=update_interval
                )
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
                    Messages.DOWNLOAD_TIMEOUT.format(reason=reason)
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
            await self.event.respond(Messages.DOWNLOAD_FAILED.format(filename=self.filename, error=str(e)))
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

        # Build update message
        message = Formatters.format_download_progress(
            filename=self.filename,
            is_large=self.large_file,
            elapsed=humanize.precisedelta(timedelta(seconds=elapsed)),
            progress=self.progress,
            downloaded=f"{humanize.naturalsize(current)} of {humanize.naturalsize(total)}",
            speed=f"{humanize.naturalsize(self.current_speed)}/s",
            eta=eta
        )

        try:
            await self.status_message.edit(message,
                                            buttons=[
                                                [ Buttons.cancel_download(self.message_id) ]
                                            ])
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            # If edit fails, try sending a new message
            try:
                old_message = self.status_message
                self.status_message = await self.event.respond(message,
                                                                buttons=[
                                                                    [ Buttons.cancel_download(self.message_id) ]
                                                                ])
                try:
                    await old_message.delete()
                except:
                    pass
            except Exception as inner_e:
                logger.error(f"Failed to send new status message: {inner_e}")

    async def send_completion_message(self, duration):
        suggested_filename = f"{self.filename}{self.ext}"
        message = Formatters.format_download_complete(
            filename=self.filename,
            suggested_filename=suggested_filename,
            is_large=self.large_file,
            size=humanize.naturalsize(self.file_size),
            duration=humanize.precisedelta(timedelta(seconds=duration)),
            speed=f"{humanize.naturalsize(self.file_size / duration)}/s"
        )

        try:
            await self.status_message.edit(message,
                                            buttons=[
                                                [ Buttons.cancel_download(self.message_id) ]
                                            ])
        except Exception as e:
            logger.error(f"Failed to send completion message: {e}")
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

        await self.event.respond(
            Messages.DOWNLOAD_CANCELLED_FULL.format(filename=self.filename)
        )
        return True

    async def process_media(self):
        if self.cancelled:
            return

        self.process_message = await self.event.respond(
            Messages.PROCESSING_STARTED.format(filename=self.filename)
        )
        try:
            # Step 1: Analyze file using MediaProcessor
            await self.update_processing_message(Messages.STAGE_ANALYZING)
            processor = MediaProcessor(self.filename, TMDB_API_KEY, session=self.session)
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
                with open(BASE_DIR / 'low_confidence_log.csv', 'a') as lf:
                    lf.write(f"{self.filename},{parsed},{tmdb_title},{score:.2f}\n")
                return

            elif score < HIGH_CONFIDENCE:
                # Medium confidence → proceed but warn
                await self.update_processing_message(
                    f"⚠️ Medium confidence ({score:.2f}); proceeding with caution"
                )
            
            # Step 2: Decide where to put it
            if result:
                # 2a) Anime goes under Anime/<Title>
                if result.get('is_anime'):
                    if result['type'] == 'tv':
                        show  = sanitize_path_component(result['title'])
                        season = result['season']
                        target_dir = ANIME_DIR / show / f"Season {season:02d}"
                    elif result['type'] == 'movie':
                        title = sanitize_path_component(result['title'])
                        year  = result.get('year', '')
                        folder = f"{title} ({year})" if year else title
                        target_dir = ANIME_DIR / folder
                    else:
                        target_dir = ANIME_DIR / sanitize_path_component(result['title'])

                    target_dir.mkdir(parents=True, exist_ok=True)
                    await self.update_processing_message(
                        f"✅ Anime detected: {result['title']}\n"
                        f"Created directory: {target_dir}")
                # 2b) TV shows
                elif result['type'] == 'tv':
                    show_name   = sanitize_path_component(result['title'])
                    season_no   = result['season']
                    episode_no  = result['episode']
                    folder_struct = result.get('folder_structure')

                    if folder_struct:
                        target_dir = TV_DIR / folder_struct
                    else:
                        target_dir = TV_DIR / show_name / f"Season {season_no:02d}"

                    target_dir.mkdir(parents=True, exist_ok=True)
                    await self.update_processing_message(
                        f"✅ TV: {show_name} S{season_no:02d}E{episode_no:02d}"
                    )

                # 2c) Movies
                elif result['type'] == 'movie':
                    title    = sanitize_path_component(result['title'])
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
                # Build Jellyfin‑friendly base name
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
                    base = Path(self.filename).stem

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
            await self.update_processing_message(Messages.STAGE_MOVING)
            final_name = Path(self.download_path).name
            dest_path: Path = target_dir / final_name
            if dest_path.exists():
                base = dest_path.stem
                ext = dest_path.suffix
                dest_path = dest_path.parent / f"{base}_{int(time.time())}{ext}"
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

        message = Formatters.format_processing_stage(
            filename=self.filename,
            stage=stage,
            is_final=final,
            is_error=error
        )

        try:
            await self.process_message.edit(message)
        except Exception as e:
            logger.error(f"Failed to update processing message: {e}")

    async def update_queue_message(self, message):
        """Updates the queue message with the current status."""
        if not self.status_message:
            self.status_message = await self.event.respond(message)
            return
            
        try:
            await self.status_message.edit(message,
                                            buttons=[
                                                [ Button.inline("❌ Cancel download", f"cancel_{self.message_id}") ]
                                            ])
        except Exception as e:
            logger.error(f"Failed to update queue message: {e}")
            if "Content of the message was not modified" in str(e):
                pass
            else:
                try:
                    old_message = self.status_message
                    self.status_message = await self.event.respond(message)
                    try:
                        await old_message.delete()
                    except:
                        pass
                except Exception as inner_e:
                    logger.error(f"Failed to send new queue message: {inner_e}")
