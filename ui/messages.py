"""
Message Templates - Minimal Play Theme
All user-facing messages with emoji personality, clean spacing, and consistent voice.
"""

class Messages:
    """Message templates with Minimal Play theme - expressive yet tasteful."""
    
    # === WELCOME & HELP ===
    WELCOME = "👋 Welcome!"
    
    HELP_TEXT = """👋 Welcome!

I help organize your media for Jellyfin.
Send me a video file to get started! 🎬

📖 Commands
→ /start - Show this message
→ /help - Show this message  
→ /stats - View your stats 📊
→ /queue - Check download queue ⏳
→ /organize - Sort your files 📁

🎯 Admin Commands
→ /history - View organize history 📚
→ /propagate - Bulk-propagate episodes 📤
→ /test - Run system test 🔍
→ /users - View total users 👥
→ /shutdown - Shutdown bot 🔴"""
    
    # === STATS ===
    STATS_HEADER = "📊 Stats"
    STATS_USER_SECTION = "📊 Your Stats"
    STATS_GLOBAL_SECTION = "🌍 Global Stats"
    STATS_DOWNLOADS = "⬇️ Downloads"
    STATS_DATA = "💾 Data"
    STATS_UPTIME = "⏰ Uptime"
    STATS_ACTIVE_USERS = "👥 Active Users"
    
    # === QUEUE ===
    QUEUE_HEADER = "📥 Queue · Page {page}"
    QUEUE_NOW = "⬇️ Now downloading"
    QUEUE_IDLE = "💤 idle"
    QUEUE_UPCOMING = "⏳ Up next"
    QUEUE_NO_MORE = "✓ No more items in queue"
    
    # === DOWNLOAD ===
    DOWNLOAD_STARTED = "⬇️ Download started\n`{filename}`"
    DOWNLOAD_COMPLETE = "✅ Download complete!"
    DOWNLOAD_CANCELLED = "❌ Download cancelled\n{filename}"
    DOWNLOAD_REMOVED = "🗑️ Removed from queue"
    DOWNLOAD_CANCELLATION_REQUESTED = "⏹️ Cancellation requested\n{filename}"
    DOWNLOAD_NOT_ACCEPTING = "⚠️ Bot is shutting down\n\nNot accepting new downloads right now."
    QUEUE_STARTING = "✅ Ready to download!\n\nYour queue position is now 0."
    
    DOWNLOAD_INITIALIZING = """⬇️ Downloading
{filename}

{file_type}
📁 Destination: {dir}

→ Preparing...
ℹ️ Updates every {interval}"""
    
    DOWNLOAD_TIMEOUT = """⏱️ Download timed out

Took longer than {reason}.
Cancelling automatically."""
    
    DOWNLOAD_FAILED = """❌ Download failed
{filename}

Error: {error}"""
    
    DOWNLOAD_CANCELLED_FULL = """⏹️ Cancellation requested
{filename}

❌ Download cancelled
🗑️ Removed from queue"""
    
    DOWNLOAD_STATUS_LARGE = "⬇️ Downloading (Large File)"
    DOWNLOAD_STATUS_REGULAR = "⬇️ Downloading"
    DOWNLOAD_FILE = "📄 File"
    DOWNLOAD_RUNNING_FOR = "⏱️ Running for"
    DOWNLOAD_PROGRESS = "📊 Progress"
    DOWNLOAD_COMPLETE_PCT = "complete"
    DOWNLOAD_DOWNLOADED = "💾 Downloaded"
    DOWNLOAD_SPEED = "⚡ Speed"
    DOWNLOAD_ETA = "⏱️ ETA"
    DOWNLOAD_UNKNOWN = "Unknown"
    
    # Media indicators
    MEDIA_LARGE_FILE = "📦 Large file detected"
    MEDIA_REGULAR_FILE = "📄 Regular file"
    
    # === PROCESSING ===
    PROCESSING_STARTED = "📝 Processing\n{filename}"
    PROCESSING_STAGE = "Stage"
    STAGE_ANALYZING = "🔍 Analyzing"
    STAGE_MOVING = "📂 Moving to library"
    
    # === ORGANIZE ===
    ORGANIZE_NO_FILES = "📁 No files to organize\n\nAll files are already categorized!"
    ORGANIZE_CHOOSE_FILE = "📁 Choose a file to categorize"
    ORGANIZE_SELECTED = "✓ Selected\n`{filename}`"
    ORGANIZE_DETECTED_RES = "📺 Detected resolution\n`{resolution}`"
    ORGANIZE_SELECT_CATEGORY = "📁 Organize: {filename}\n\nSelect category:"
    ORGANIZE_SKIPPED = "↷ Skipped\n`{filename}`"
    ORGANIZE_CATEGORY_SELECTED = "✓ Category: **{category}**\n\nReply with title\nSuggestion: `{guess}`"
    
    # Interactive prompts
    ORGANIZE_ENTER_CATEGORY = "📁 What type of media is this?\n\nReply: `movie`, `tv`, or `anime`"
    ORGANIZE_INVALID_CATEGORY = "⚠️ Invalid category\n\nDefaulting to `movie`"
    ORGANIZE_ENTER_TITLE = "📝 Enter title"
    ORGANIZE_ENTER_YEAR = "📅 Enter year\n\nExample: 2024"
    ORGANIZE_ENTER_SEASON = "🔢 Enter season number\n\nExample: 1"
    ORGANIZE_ENTER_EPISODE = "🔢 Enter episode number\n\nExample: 1"
    
    ORGANIZE_SUCCESS = "✅ Organized!\n\n📂 Moved to:\n`{path}`"
    ORGANIZE_ERROR = "❌ Organization failed\n\nError: {error}"
    
    # === PREVIEW ===
    PREVIEW_RENAME = """👀 Preview

📄 From: {src}
✨ To:   {dest}"""
    
    PREVIEW_TIMEOUT = "⏰ Preview timed out\n\nDiscarding changes."
    
    PREVIEW_BULK_ITEM = """{current}/{total}

📄 {src}
✨ {dest}

Reply `yes` to confirm, `no` to skip"""
    
    # === HISTORY ===
    HISTORY_NO_HISTORY = "📚 No history yet\n\nOrganize some files to see them here!"
    HISTORY_PAGE_HEADER = "📚 History · Page {page} of {total_pages}\n\n{total_entries} total entries\n\n"
    HISTORY_ITEM = "**{index}.** `{name}`\n   🕐 {time} · `[{method}]`\n"
    
    ERROR_ENTRY_NOT_FOUND = "⚠️ Entry not found"
    HISTORY_DELETED= "✅ Record deleted"
    HISTORY_DELETED_TOAST = "🗑️ Deleted record"
    
    # === PROPAGATE ===
    PROPAGATE_NO_MANUAL = "📁 No manual entries\n\nYou haven't organized any files manually yet.\nTry /organize first!"
    PROPAGATE_NO_REMAINING = """✓ All caught up!

No more episodes found after:
📺 {title} - S{season:02d}E{episode:02d}"""
    
    PROPAGATE_STARTED = """📤 Bulk propagate

Found {count} remaining episodes:
📺 {title} - Season {season}

Propagate all using the first episode's metadata?"""
    
    PROPAGATE_MOVED = "✅ Organized\n📂 {dest}"
    PROPAGATE_ERROR = "❌ Error\n{filename}: {error}"
    PROPAGATE_SKIPPED = "↷ Skipped\n{filename}"
    PROPAGATE_COMPLETE = "✅ Bulk propagate complete!\n\n{success} organized · {skipped} skipped"
