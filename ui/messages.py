"""
Message Templates
All user-facing messages in one place for easy customization.
"""

class Messages:
    """Message templates with simple fallback theme."""
    
    # === WELCOME & HELP ===
    WELCOME = "Welcome to Jellyfin Media Downloader Bot!"
    
    HELP_TEXT = """Welcome to the Jellyfin Media Downloader Bot!

Send me any media file and I will download it to your Jellyfin library.

Commands:
/start - Start the bot
/help - Show this help message
/stats - View download statistics
/queue - View download queue
/organize - Organize downloaded files (admin)
/history - View organization history (admin)
/test - Run system test (admin)
/users - View active users (admin)
/shutdown - Shutdown bot (admin)

Features:
- Automatic media detection
- Smart file organization
- Progress tracking
- Queue management"""
    
    # === STATS ===
    STATS_HEADER = "DOWNLOAD STATISTICS"
    STATS_USER_SECTION = "Your Stats:"
    STATS_GLOBAL_SECTION = "Global Stats:"
    STATS_DOWNLOADS = "Downloads"
    STATS_DATA = "Data"
    STATS_UPTIME = "Uptime"
    STATS_ACTIVE_USERS = "Active Users"
    
    # === QUEUE ===
    QUEUE_HEADER = "Download Queue (page {page})"
    QUEUE_NOW = "Now:"
    QUEUE_IDLE = "idle"
    QUEUE_UPCOMING = "Up next:"
    QUEUE_NO_MORE = "No more items in queue."
    
    # === DOWNLOAD ===
    DOWNLOAD_STARTED = "Download started: `{filename}`"
    DOWNLOAD_COMPLETE = "Download Complete!"
    DOWNLOAD_CANCELLED = "Download cancelled for {filename}"
    DOWNLOAD_REMOVED = "Removed from queue"
    DOWNLOAD_CANCELLATION_REQUESTED = "Cancellation requested for {filename}"
    
    DOWNLOAD_STATUS_LARGE = "STATUS UPDATE - LARGE FILE DOWNLOAD"
    DOWNLOAD_STATUS_REGULAR = "Download Progress"
    DOWNLOAD_FILE = "File"
    DOWNLOAD_RUNNING_FOR = "Running for"
    DOWNLOAD_PROGRESS = "Progress"
    DOWNLOAD_COMPLETE_PCT = "complete"
    DOWNLOAD_DOWNLOADED = "Downloaded"
    DOWNLOAD_SPEED = "Speed"
    DOWNLOAD_ETA = "ETA"
    DOWNLOAD_UNKNOWN = "Unknown"
    
    # === PROCESSING ===
    PROCESSING_STARTED = "Started processing: {filename}"
    PROCESSING_STAGE = "Stage"
    
    # === ORGANIZE ===
    ORGANIZE_NO_FILES = "No files needing categorization."
    ORGANIZE_CHOOSE_FILE = "Choose a file to categorize:"
    ORGANIZE_SELECTED = "Selected file: `{filename}`"
    ORGANIZE_DETECTED_RES = "Detected resolution: `{resolution}`"
    ORGANIZE_SELECT_CATEGORY = "File: {filename}\nSelect category:"
    ORGANIZE_SKIPPED = "Skipped `{filename}`."
    ORGANIZE_CATEGORY_SELECTED = "Category: **{category}**\nReply with *Title* (suggestion: `{guess}`)"
    ORGANIZE_ENTER_YEAR = "Reply with *Year* (e.g., 2024):"
    ORGANIZE_ENTER_SEASON = "Reply with *Season number* (e.g., 1):"
    ORGANIZE_ENTER_EPISODE = "Reply with *Episode number* (e.g., 1):"
    ORGANIZE_SUCCESS = "Successfully organized to: `{path}`"
    ORGANIZE_ERROR = "Error organizing file: {error}"
    
    # === HISTORY ===
    HISTORY_HEADER = "Organization History ({start}-{end} of {total}):"
    HISTORY_NO_ENTRIES = "No organized entries found."
    HISTORY_DETAIL_HEADER = "Entry Details"
    HISTORY_FILE = "File"
    HISTORY_TITLE = "Title"
    HISTORY_CATEGORY = "Category"
    HISTORY_YEAR = "Year"
    HISTORY_SEASON = "Season"
    HISTORY_EPISODE = "Episode"
    HISTORY_RESOLUTION = "Resolution"
    HISTORY_METHOD = "Method"
    HISTORY_ORGANIZED_BY = "Organized by"
    HISTORY_TIMESTAMP = "When"
    HISTORY_BACK = "Back to list"
    
    # === PROPAGATE ===
    PROPAGATE_NO_MANUAL = "No manual organizes to propagate from."
    PROPAGATE_NO_REMAINING = "No remaining episodes found for bulk propagation."
    PROPAGATE_STARTED = "Bulk propagation started: {current}/{total}"
    PROPAGATE_COMPLETE = "Bulk propagation complete!"
    PROPAGATE_PROCESSED = "Processed {count} files"
    
    # === ADMIN ===
    ADMIN_ONLY = "This command is admin-only."
    ADMIN_USERS_HEADER = "Active Users"
    ADMIN_USER_ENTRY = "User ID: {user_id}"
    
    # === TEST ===
    TEST_HEADER = "System Test Results"
    TEST_TELEGRAM = "Telegram Connection"
    TEST_TMDB = "TMDb API"
    TEST_DIRECTORIES = "Directories"
    TEST_DATABASE = "Database"
    TEST_PERMISSIONS = "Permissions"
    TEST_OK = "OK"
    TEST_FAILED = "FAILED"
    TEST_WARNING = "WARNING"
    
    # === SHUTDOWN ===
    SHUTDOWN_IN_PROGRESS = "Shutdown in progress."
    SHUTDOWN_INITIATED = "Graceful shutdown initiated."
    SHUTDOWN_WAITING = "Waiting for {count} active downloads to complete..."
    SHUTDOWN_TIMEOUT = "Force shutdown after timeout."
    SHUTDOWN_COMPLETE = "Shutdown complete."
    
    # === ERRORS ===
    ERROR_GENERIC = "An error occurred: {error}"
    ERROR_FILE_NOT_FOUND = "File not found or session expired."
    ERROR_ENTRY_NOT_FOUND = "Entry not found."
    ERROR_INVALID_INPUT = "Invalid input. Please try again."
    ERROR_TIMEOUT = "Operation timed out."
    ERROR_PERMISSION_DENIED = "Permission denied."
    
    # === PREVIEW ===
    PREVIEW_RENAME = "Preview rename:\n`{src}` → `{dest}`"
    PREVIEW_TIMEOUT = "Preview timed out; discarding."
    PREVIEW_BULK_ITEM = "{index}/{total}  `{src}` → `{dest}`\nReply `yes` to confirm, `no` to skip."
    
    # === MEDIA DETECTION ===
    MEDIA_CATEGORIZER_START = "Media categorizer will start shortly."
    MEDIA_LARGE_FILE = "Large file"
    MEDIA_REGULAR_FILE = "Regular file"
    MEDIA_SUGGESTED_FILENAME = "Suggested Filename"
    MEDIA_SIZE = "Size"
    MEDIA_TIME = "Time"
    MEDIA_AVG_SPEED = "Avg Speed"
    
    @staticmethod
    def format_stats(user_stats, global_stats, uptime):
        """Format statistics message."""
        msg = f"{Messages.STATS_HEADER}\n\n"
        msg += f"{Messages.STATS_USER_SECTION}\n"
        msg += f"  • {Messages.STATS_DOWNLOADS}: {user_stats.downloads}\n"
        msg += f"  • {Messages.STATS_DATA}: {user_stats.bytes_formatted}\n\n"
        msg += f"{Messages.STATS_GLOBAL_SECTION}\n"
        msg += f"  • {Messages.STATS_DOWNLOADS}: {global_stats.downloads}\n"
        msg += f"  • {Messages.STATS_DATA}: {global_stats.bytes_formatted}\n"
        msg += f"  • {Messages.STATS_UPTIME}: {uptime}\n"
        msg += f"  • {Messages.STATS_ACTIVE_USERS}: {global_stats.active_users}"
        return msg
    
    @staticmethod
    def format_queue_header(page):
        """Format queue header."""
        return Messages.QUEUE_HEADER.format(page=page)
    
    @staticmethod
    def format_download_started(filename):
        """Format download started message."""
        return Messages.DOWNLOAD_STARTED.format(filename=filename)
    
    @staticmethod
    def format_download_complete(filename, suggested_filename, is_large, size, duration, speed):
        """Format download completion message."""
        msg = f"{Messages.DOWNLOAD_COMPLETE}\n\n"
        msg += f"{Messages.DOWNLOAD_FILE}: {filename}\n"
        msg += f"{Messages.MEDIA_SUGGESTED_FILENAME}: {suggested_filename}\n"
        msg += f"{Messages.MEDIA_LARGE_FILE if is_large else Messages.MEDIA_REGULAR_FILE}\n"
        msg += f"{Messages.MEDIA_SIZE}: {size}\n"
        msg += f"{Messages.MEDIA_TIME}: {duration}\n"
        msg += f"{Messages.MEDIA_AVG_SPEED}: {speed}\n\n"
        msg += Messages.MEDIA_CATEGORIZER_START
        return msg
    
    @staticmethod
    def format_download_progress(filename, is_large, elapsed, progress, downloaded, speed, eta):
        """Format download progress message."""
        if is_large:
            msg = f"{Messages.DOWNLOAD_STATUS_LARGE}\n\n"
        else:
            msg = f"{Messages.DOWNLOAD_STATUS_REGULAR}\n\n"
        
        msg += f"{Messages.DOWNLOAD_FILE}: {filename}\n"
        msg += f"{Messages.DOWNLOAD_RUNNING_FOR}: {elapsed}\n"
        msg += f"{Messages.DOWNLOAD_PROGRESS}: {progress:.1f}% {Messages.DOWNLOAD_COMPLETE_PCT}\n"
        msg += f"{Messages.DOWNLOAD_DOWNLOADED}: {downloaded}\n"
        msg += f"{Messages.DOWNLOAD_SPEED}: {speed}\n"
        msg += f"{Messages.DOWNLOAD_ETA}: {eta}"
        return msg
    
    @staticmethod
    def format_processing_stage(filename, stage, is_final=False, is_error=False):
        """Format processing stage message."""
        if is_error:
            return f"{Messages.PROCESSING_STARTED.format(filename=filename)}\n\n{stage}"
        
        stage_symbol = "" if is_final else ""
        return f"{Messages.PROCESSING_STARTED.format(filename=filename)}\n\n{stage_symbol} {Messages.PROCESSING_STAGE}: {stage}"
    
    @staticmethod
    def format_organize_success(path):
        """Format successful organization message."""
        return Messages.ORGANIZE_SUCCESS.format(path=path)
    
    @staticmethod
    def format_organize_error(error):
        """Format organization error message."""
        return Messages.ORGANIZE_ERROR.format(error=error)
