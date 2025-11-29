import asyncio
import logging
import os
import signal
import sys
import time
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta

import aiohttp
import humanize
from telethon import TelegramClient, events, Button
from guessit import guessit

# Import from modular files
from config import (
    API_ID, API_HASH, BOT_TOKEN, TMDB_API_KEY,
    BASE_DIR, DOWNLOAD_DIR, MOVIES_DIR, TV_DIR, ANIME_DIR, MUSIC_DIR, OTHER_DIR,
    LOG_DIR, SESSION_NAME, DB_PATH, MEDIA_EXTENSIONS
)
from database import (
    load_active_users, save_active_users, paginate_db,

    users_tbl, stats_tbl, organized_tbl, error_log_tbl
)
from utils import similarity, create_dir_safely, admin_only
from stats import BotStats, stats
from media_processor import MediaProcessor
from organizer import InteractiveOrganizer
from downloader import DownloadManager, DownloadTask

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# STDOUT handler
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)

organizer = InteractiveOrganizer()
download_manager = DownloadManager()

# Load active users
all_users = load_active_users()

# Telegram client
client = TelegramClient(str(SESSION_NAME), API_ID, API_HASH)

# --- Organize sessions FSM ---
organize_sessions = defaultdict(dict)
# In-memory state for bulk propagation
bulk_sessions = defaultdict(lambda: {"items": [], "index": 0})

# Global shutdown flags
shutdown_in_progress = False
force_shutdown = False
last_sigint_time = 0
FORCE_SHUTDOWN_TIMEOUT = 10  # seconds

# --- Helper Functions ---

def build_queue_message(page: int = 1, per_page: int = 10):
    """
    Returns (text, buttons) for the /queue response.
    """
    status   = download_manager.get_queue_status()
    active   = status["active"]    # list of (msg_id, filename, progress)
    queued   = status["queued"]    # list of (pos, msg_id, filename, size)

    lines = [f"🗒️ **Download Queue (page {page})**\n"]

    # Currently downloading
    if active:
        lines.append("▶️ **Now:**")
        for i, (_mid, fn, prog) in enumerate(active, 1):
            filled = min(int(prog // 10), 10)
            bar    = "[" + "█"*filled + "─"*(10-filled) + f"] {prog:.0f}%"
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

    # Build inline buttons: cancel + “More →”
    buttons = []
    # Cancel buttons for active + queued
    for mid, fn, _ in [(mid, fn, _) for mid,fn,_ in active] \
                   + [(mid, fn, _) for _,mid,fn,_ in page_items]:
        disp = fn if len(fn) <= 20 else fn[:17] + "..."
        buttons.append([ Button.inline(f"❌ Cancel: {disp}", f"cancel_{mid}") ])

    # “More” button if further pages exist
    total_queued = len(queued)
    if total_queued > start + per_page:
        next_page = page + 1
        buttons.append([
            Button.inline(f"More (page {next_page})", data=f"queue:{next_page}")
        ])

    return "\n".join(lines), buttons

# --- Handlers ---

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
    
    # Use organizer method
    items = organizer.find_remaining_episodes(folder, title, season, ep0)
    
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
    # This handler might conflict with handle_media if not careful.
    # handle_media checks for event.message.media.
    # organize_flow checks if user is in session.
    
    user = event.sender_id
    if user not in organize_sessions:
        # Pass through to handle_media if it's media
        if event.message.media:
            return await handle_media(event)
        return

    session = organize_sessions.get(user)
    if 'step' not in session:
        # Same here
        if event.message.media:
            return await handle_media(event)
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
    offset = int(event.pattern_match.group(1))
    await show_history_page(event, offset=offset, detail_eid=None)

@client.on(events.CallbackQuery(pattern=r'^hist_detail:(\d+):(\d+)$'))
async def history_detail_callback(event):
    eid = int(event.pattern_match.group(1))
    offset = int(event.pattern_match.group(2))
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
        elif season is not None and episode is not None and category.lower() != 'movie':
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
                    await event.answer("No history available.")
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

        if isinstance(event, events.CallbackQuery.Event):
            try:
                await event.edit(message_text, buttons=action_buttons_rows, parse_mode="markdown")
            except Exception as e:
                if "Message actual text is empty" in str(e) or "message to edit not found" in str(e):
                    logger.warning(f"Attempted to edit but failed: {e}")
                    await event.answer("Could not update view. Please try /history again.", alert=True)
                elif "message not modified" not in str(e).lower():
                    logger.error(f"Error editing history list view: {e}")
                    await event.answer("Error updating list.", alert=True)
                else:
                    await event.answer()
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

@client.on(events.NewMessage(pattern='/stats|/status'))
async def stats_command(event):
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})
    
    # Check if admin using utils.ADMIN_IDS (but admin_only decorator handles it, here we check manually for content)
    # We need to import ADMIN_IDS from config
    from config import ADMIN_IDS
    
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

@client.on(events.NewMessage(pattern=r'^/queue(?:\s+(\d+))?$'))
async def queue_command(event):
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

@client.on(events.CallbackQuery(data=re.compile(r'^queue:(\d+)$')))
async def queue_pagination(event):
    page = int(event.data_match.group(1))
    text, buttons = build_queue_message(page=page)
    await event.edit(text,
                     buttons=buttons or None,
                     parse_mode='md')
    
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
        lines = [
            name.strip().strip('"')
            for name in filenames_env.split(',')
            if name.strip()
        ]
        if not lines:
            filename_section = "⚠️ FILENAMES is empty."
        else:
            test_file = random.choice(lines)
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

async def handle_media(event):
    """
    Main handler for incoming media files.
    """
    if event.sender_id not in all_users:
        all_users.add(event.sender_id)
        save_active_users({event.sender_id})

    # Check if we are shutting down
    if shutdown_in_progress:
        await event.respond("⚠️ Bot is shutting down. Cannot accept new files.")
        return

    # Get media attributes
    media = event.message.media
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
        # For now, ignore or handle differently
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

async def shutdown():
    """Graceful shutdown sequence."""
    global force_shutdown
    logger.info("Shutdown initiated...")
    
    # 1. Stop accepting new downloads (handled in DownloadManager.add_download)
    download_manager.accepting_new_downloads = False
    
    # 2. Wait for active downloads to finish (with timeout)
    start_wait = time.time()
    while download_manager.active_downloads:
        if time.time() - start_wait > FORCE_SHUTDOWN_TIMEOUT:
            logger.warning("Shutdown timeout reached. Forcing exit.")
            force_shutdown = True
            break
        await asyncio.sleep(1)
        
    # 3. Cancel any queued downloads
    for task in download_manager.queued_downloads:
        await task.event.respond("⚠️ Bot shutting down. Download cancelled.")
    
    # 4. Close resources
    if aiohttp_session:
        await aiohttp_session.close()
    
    await client.disconnect()
    logger.info("Bot disconnected. Exiting.")
    sys.exit(0)

def signal_handler(sig, frame):
    global last_sigint_time, shutdown_in_progress
    current_time = time.time()
    
    if current_time - last_sigint_time < 2:
        logger.info("Force killing...")
        sys.exit(1)
    
    last_sigint_time = current_time
    if not shutdown_in_progress:
        logger.info("Interrupt received. Starting graceful shutdown... (Press Ctrl+C again to force)")
        shutdown_in_progress = True
        asyncio.create_task(shutdown())

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def main():
    global aiohttp_session
    
    # Initialize aiohttp session
    aiohttp_session = aiohttp.ClientSession()
    
    # Start client
    await client.start(bot_token=BOT_TOKEN)
    
    # Get bot info
    me = await client.get_me()
    logger.info(f"Bot started as @{me.username} (ID: {me.id})")
    
    # Register event handlers
    # (Handlers are already registered via decorators above)
    
    # FIX: Do NOT manually register handle_media - it's already called by organize_flow
    # This was causing duplicate downloads (same file downloaded twice in parallel)
    # client.add_event_handler(handle_media, events.NewMessage)
    
    # Run until disconnected
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)