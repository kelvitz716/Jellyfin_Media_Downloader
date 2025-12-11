"""
User Handlers - Commands accessible to all users.

Commands:
- /start, /help - Welcome message
- /stats, /status - Download statistics
- /queue - View download queue
- /test - System diagnostics (admin)
"""
import os
import re
import shutil
import time
import random
from datetime import timedelta

import humanize
from telethon import events, Button

from config import (
    ADMIN_IDS, TMDB_API_KEY,
    DOWNLOAD_DIR, MOVIES_DIR, TV_DIR, MUSIC_DIR, OTHER_DIR
)
from database import load_active_users, save_active_users
from stats import BotStats, stats
from media_processor import MediaProcessor
from downloader import DownloadManager
from src.services.rate_limiter import rate_limited, command_limiter

# These will be set during handler registration
client = None
download_manager = None
aiohttp_session = None
all_users = set()


def register(telegram_client, dm, session, users):
    """Register handlers with the client."""
    global client, download_manager, aiohttp_session, all_users
    client = telegram_client
    download_manager = dm
    aiohttp_session = session
    all_users = users
    
    # Register all handlers
    client.add_event_handler(start_command, events.NewMessage(pattern='/start|/help'))
    client.add_event_handler(stats_command, events.NewMessage(pattern='/stats|/status'))
    client.add_event_handler(queue_command, events.NewMessage(pattern=r'^/queue(?:\s+(\d+))?$'))
    client.add_event_handler(queue_pagination, events.CallbackQuery(data=re.compile(r'^queue:(\d+)$')))
    client.add_event_handler(test_command, events.NewMessage(pattern='/test'))


def build_queue_message(page: int = 1, per_page: int = 10):
    """
    Returns (text, buttons) for the /queue response.
    """
    status = download_manager.get_queue_status()
    active = status["active"]    # list of (msg_id, filename, progress)
    queued = status["queued"]    # list of (pos, msg_id, filename, size)

    lines = [f"🗒️ **Download Queue (page {page})**\n"]

    # Currently downloading
    if active:
        lines.append("▶️ **Now:**")
        for i, (_mid, fn, prog) in enumerate(active, 1):
            filled = min(int(prog // 10), 10)
            bar = "[" + "█"*filled + "─"*(10-filled) + f"] {prog:.0f}%"
            lines.append(f"{i}. `{fn}`  {bar}")
        lines.append("")
    else:
        lines.append("▶️ **Now:** _idle_\n")

    # Upcoming (paginated)
    start = (page-1)*per_page
    page_items = queued[start : start+per_page]
    if page_items:
        lines.append("⬇️ **Up next:**")
        for idx, (_pos, _mid, fn, sz) in enumerate(page_items, start+1):
            lines.append(f"{idx}. `{fn}` ({humanize.naturalsize(sz)})")
    else:
        lines.append("✅ No more items in queue.")

    # Build inline buttons: cancel + "More →"
    buttons = []
    # Cancel buttons for active + queued
    for mid, fn, _ in [(mid, fn, _) for mid, fn, _ in active] \
                   + [(mid, fn, _) for _, mid, fn, _ in page_items]:
        disp = fn if len(fn) <= 20 else fn[:17] + "..."
        buttons.append([Button.inline(f"❌ Cancel: {disp}", f"cancel_{mid}")])

    # "More" button if further pages exist
    total_queued = len(queued)
    if total_queued > start + per_page:
        next_page = page + 1
        buttons.append([
            Button.inline(f"More (page {next_page})", data=f"queue:{next_page}")
        ])

    return "\n".join(lines), buttons


@rate_limited(command_limiter)
async def start_command(event):
    """Handle /start and /help commands."""
    global all_users
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users(all_users)

    await event.respond(
        "👋 Welcome to the Jellyfin Media Downloader Bot!\n\n"
        "Send me any media file and I will download it to your Jellyfin library.\n\n"
        "📂 COMMANDS:\n"
        "/start      - Show this welcome message\n"
        "/help       - Show usage help\n"
        "/stats      - 📊 Show download statistics\n"
        "/status     - 📊 Alias for /stats\n"
        "/queue      - 📋 View current download queue\n"
        "/test       - 🔍 Run system test\n"
        "\n"
        "🚀 Admin commands:\n"
        "/organize   - 🗂️ Organize files into categories\n"
        "/history    - 📜 View organize history\n"
        "/propagate  - 📦 Bulk-propagate episodes\n"
        "/users      - 👥 View total unique users\n"
        "/shutdown   - 🔌 Gracefully shut down the bot\n"
        "\n"
        "📱 SUPPORTED FORMATS:\n"
        "• 🎬 Videos: MP4, MKV, AVI, etc.\n"
        "• 🎵 Audio: MP3, FLAC, WAV, etc.\n"
        "• 📄 Documents: PDF, ZIP, etc."
    )


@rate_limited(command_limiter)
async def stats_command(event):
    """Handle /stats and /status commands."""
    global all_users
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})
    
    # Admin gets detailed per-user stats
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

    # Non-admin: show runtime stats
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


@rate_limited(command_limiter)
async def queue_command(event):
    """Handle /queue command."""
    global all_users
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})
    # parse optional page argument
    page_arg = event.pattern_match.group(1)
    page = int(page_arg) if page_arg and page_arg.isdigit() else 1

    text, buttons = build_queue_message(page=page)
    await event.respond(text,
                        buttons=buttons or None,
                        parse_mode='md')


async def queue_pagination(event):
    """Handle queue pagination callbacks."""
    page = int(event.data_match.group(1))
    text, buttons = build_queue_message(page=page)
    await event.edit(text,
                     buttons=buttons or None,
                     parse_mode='md')


@rate_limited(command_limiter)
async def test_command(event):
    """Handle /test command - run system diagnostics."""
    global all_users
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

    # 5) Random-filename TMDb lookup
    filenames_env = os.getenv('FILENAMES', '')
    if not filenames_env:
        filename_section = "⚠️ No FILENAMES set in environment."
    else:
        lines_list = [
            name.strip().strip('"')
            for name in filenames_env.split(',')
            if name.strip()
        ]
        if not lines_list:
            filename_section = "⚠️ FILENAMES is empty."
        else:
            test_file = random.choice(lines_list)
            processor = MediaProcessor(test_file, tmdb_api_key=TMDB_API_KEY, session=aiohttp_session)
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
    msg.append("")
    msg.append("🎲 Metadata Test")
    msg.append(filename_section)
    msg.append("")
    msg.append(f"⚡ Network Speed: {net_speed}")

    await event.respond("\n".join(msg))
