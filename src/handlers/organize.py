"""
Organize Handlers - File organization FSM and callbacks.

Commands:
- /organize - Start interactive organization
- /organized - View organized files list
- /cancel - Cancel current organization

FSM Steps:
1. Select file from candidates
2. Choose category (movie/tv/anime)
3. Enter title
4. Enter year (movie) or season/episode (tv/anime)
5. Finalize (rename + record)
"""
import logging
from pathlib import Path
from datetime import datetime

import humanize
from telethon import events, Button
from guessit import guessit

from config import DOWNLOAD_DIR, OTHER_DIR, MOVIES_DIR, TV_DIR, ANIME_DIR, MEDIA_EXTENSIONS
from database import organized_tbl
from utils import admin_only
from organizer import InteractiveOrganizer

logger = logging.getLogger(__name__)

# These will be set during handler registration
client = None
organizer = None
organize_sessions = None  # SessionManager


def register(telegram_client, org, org_sessions, handle_media_callback=None):
    """Register organize handlers with the client."""
    global client, organizer, organize_sessions, _handle_media
    client = telegram_client
    organizer = org
    organize_sessions = org_sessions
    _handle_media = handle_media_callback
    
    # Register all handlers
    client.add_event_handler(organize_command, events.NewMessage(pattern='^/organize$'))
    client.add_event_handler(pick_file, events.CallbackQuery(pattern=r'org_file:(.+)'))
    client.add_event_handler(pick_category, events.CallbackQuery(pattern=r'org_cat:(\w+)'))
    client.add_event_handler(organize_flow, events.NewMessage)
    client.add_event_handler(organized_command, events.NewMessage(pattern=r'^/organized$'))
    client.add_event_handler(organized_page_callback, events.CallbackQuery(pattern=r'^org_page:(\d+)$'))
    client.add_event_handler(cancel_organize, events.NewMessage(pattern='/cancel'))


# Callback for media handler when not in organize session
_handle_media = None


def get_run_finalize():
    """Get the run_finalize function for use by admin handlers."""
    return run_finalize


@admin_only
async def organize_command(event):
    """Start interactive file organization."""
    user = event.sender_id
    organize_sessions.clear(user)

    # Scan for candidates using organizer
    candidates = organizer.scan_for_candidates()
    if not candidates:
        return await event.respond(
            "✅ No files needing categorization.\n\n"
            f"(I saw {len(list(Path(DOWNLOAD_DIR).rglob('*')))} files on disk — "
            "check your extensions filter.)"
        )

    # Create session with file mappings
    file_map = {}
    buttons = []
    for idx, path in enumerate(candidates):
        key = f"file_{idx}"
        file_map[key] = path
        buttons.append([Button.inline(path.name, f'org_file:{key}')])
    
    organize_sessions.create(user, "select_file", file_map)
    await event.respond("🗂️ Choose a file to categorize:", buttons=buttons)


async def pick_file(event):
    """Handle file selection callback."""
    user = event.sender_id
    file_id = event.data.decode().split(':', 1)[1]
    
    session = organize_sessions.get(user)
    if not session:
        return await event.respond("⚠️ Session expired. Use /organize to start again.")
    
    file_path = session.data.get(file_id)
    if not file_path:
        return await event.respond("⚠️ File not found or session expired.")

    # Detect resolution and update session
    res = organizer.detect_resolution(file_path)
    organize_sessions.create(user, "choose_category", {
        "file": file_path,
        "meta": {"resolution": res}
    })

    kb = [
        [Button.inline("Movie", "org_cat:movie"), Button.inline("TV", "org_cat:tv")],
        [Button.inline("Anime", "org_cat:anime"), Button.inline("Skip", "org_cat:skip")]
    ]
    await event.respond(f"🔍 Selected file: `{file_path.name}`\nDetected resolution: `{res}`", parse_mode="markdown")
    await event.edit(f"🗂️ File: {file_path.name}\nSelect category:", buttons=kb)


async def pick_category(event):
    """Handle category selection callback."""
    user = event.sender_id
    session = organize_sessions.get(user)
    if not session:
        return await event.respond("⚠️ Session expired.")
    
    choice = event.data.decode().split(':', 1)[1]

    if choice == 'skip':
        await event.edit(f"⏭️ Skipped `{session.data['file'].name}`.")
        organize_sessions.clear(user)
        return

    session.data['meta']['category'] = choice
    session.data['step'] = 'ask_title'
    session.refresh()

    guess = guessit(session.data['file'].name).get('title', '')
    await event.edit(
        f"✏️ Category: **{choice.title()}**\n"
        f"Reply with *Title* (suggestion: `{guess}`)"
    )


async def organize_flow(event):
    """Handle FSM text input for title/year/season/episode."""
    user = event.sender_id
    session = organize_sessions.get(user)
    
    if not session or 'step' not in session.data:
        # Not in an organize session - pass through to media handler if it's media
        if event.message.media and _handle_media:
            return await _handle_media(event)
        return
        
    text = event.raw_text.strip()
    step = session.data.get('step')

    if step == 'ask_title':
        session.data['meta']['title'] = text
        session.data['step'] = 'ask_year_or_next'
        session.refresh()
        if session.data['meta']['category'] == 'movie':
            return await event.respond("✏️ Now reply with *Year* (e.g. 2023):")
        else:
            return await event.respond("✏️ Now reply with *Season number* (e.g. 1):")

    if step == 'ask_year_or_next':
        cat = session.data['meta']['category']
        if cat == 'movie':
            session.data['meta']['year'] = text
            await event.respond("✅ Got it! Moving the file…")
            await run_finalize(event, session.data)
            return
        else:
            session.data['meta']['season'] = int(text)
            session.data['step'] = 'ask_episode'
            session.refresh()
            return await event.respond("✏️ Reply with *Episode number* (e.g. 3):")

    if step == 'ask_episode':
        session.data['meta']['episode'] = int(text)
        await event.respond("✅ Got it! Moving the file…")
        await run_finalize(event, session.data)
        return


async def run_finalize(event, session_data):
    """Handles folder creation, safe rename, DB record, and user feedback."""
    fpath = session_data['file']
    m = session_data['meta']
    res = m.get('resolution', '').upper()

    # Determine base folder & filename
    if m['category'] == 'movie':
        folder = MOVIES_DIR / f"{m['title']} ({m['year']})"
        base = f"{m['title']} ({m['year']})"
    elif m['category'] == 'tv':
        folder = TV_DIR / m['title'] / f"Season {m['season']:02d}"
        ep = f"S{m['season']:02d}E{m['episode']:02d}"
        base = f"{m['title']} - {ep}"
    else:  # anime
        if 'episode' in m:
            folder = ANIME_DIR / m['title'] / f"Season {m['season']:02d}"
            ep = f"S{m['season']:02d}E{m['episode']:02d}"
            base = f"{m['title']} - {ep}"
        else:
            folder = ANIME_DIR / f"{m['title']} ({m.get('year', '')})"
            base = f"{m['title']} ({m.get('year', '')})"

    # Build destination path
    folder.mkdir(parents=True, exist_ok=True)
    ext = fpath.suffix
    new_name = f"{base} [{res}]{ext}" if res else f"{base}{ext}"
    dest = folder / new_name

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
    organize_sessions.clear(event.sender_id)
    await event.respond("🗂️ Send /organize to categorize another file, or /propagate to propagate.")


@admin_only
async def organized_command(event):
    """View organized files list."""
    await show_organized_page(event, offset=0)


async def organized_page_callback(event):
    """Handle organized list pagination."""
    offset = int(event.data.decode().split(":")[1])
    await show_organized_page(event, offset=offset)


async def show_organized_page(event, offset=0):
    """Show paginated list of organized files."""
    # Only manually organized entries
    manual = [e for e in organized_tbl.all() if e.get("method", "manual") == "manual"]
    manual_sorted = sorted(manual, key=lambda r: r.get("timestamp", ""), reverse=True)
    total = len(manual_sorted)
    page = manual_sorted[offset:offset+10]
    if not page:
        return await event.respond("📁 No organized entries found.")

    buttons = []
    for entry in page:
        label = f"{entry['title']} ({entry.get('year', '')})"
        ts = humanize.naturaltime(datetime.fromisoformat(entry['timestamp']))
        eid = entry.doc_id
        buttons.append([
            Button.inline(f"🔁 {label}", f"reorg:{eid}"),
            Button.inline(f"🕓 {ts}", f"noop:{eid}"),
            Button.inline("🗑️", f"delorg:{eid}")
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


async def cancel_organize(event):
    """Cancel current organization session."""
    user = event.sender_id
    if user in organize_sessions:
        organize_sessions.clear(user)
        return await event.respond("🚫 Categorization cancelled.")
