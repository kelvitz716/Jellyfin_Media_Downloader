"""
Admin Handlers - Commands restricted to admin users.

Commands:
- /propagate - Bulk-propagate episodes
- /history - View organize history
- /shutdown - Graceful shutdown  
- /users - View user count
"""
import asyncio
import logging
import re
from pathlib import Path
from datetime import datetime

import humanize
from telethon import events, Button

from config import DB_PATH
from database import organized_tbl, users_tbl
from utils import admin_only
from organizer import InteractiveOrganizer

logger = logging.getLogger(__name__)

# These will be set during handler registration
client = None
organizer = None
bulk_sessions = None  # SessionManager
_run_finalize_callback = None  # Will be set from organize handlers
shutdown_callback = None


def register(telegram_client, org, bulk_sess, finalize_cb=None, shutdown_cb=None):
    """Register admin handlers with the client."""
    global client, organizer, bulk_sessions, _run_finalize_callback, shutdown_callback
    client = telegram_client
    organizer = org
    bulk_sessions = bulk_sess
    _run_finalize_callback = finalize_cb
    shutdown_callback = shutdown_cb
    
    # Register all handlers
    client.add_event_handler(propagate_command, events.NewMessage(pattern=r'^/propagate$'))
    client.add_event_handler(bulk_answer, events.CallbackQuery(pattern=r'^bulk_ans:(yes|no)$'))
    client.add_event_handler(history_command, events.NewMessage(pattern=r'^/history$'))
    client.add_event_handler(history_page_callback, events.CallbackQuery(pattern=r'^hist_page:(\d+)$'))
    client.add_event_handler(history_detail_callback, events.CallbackQuery(pattern=r'^hist_detail:(\d+):(\d+)$'))
    client.add_event_handler(reorganize_entry, events.CallbackQuery(pattern=r'reorg:(\d+)'))
    client.add_event_handler(delete_organized_record, events.CallbackQuery(pattern=r'delorg:(\d+)'))
    client.add_event_handler(shutdown_command, events.NewMessage(pattern='/shutdown'))
    client.add_event_handler(users_command, events.NewMessage(pattern='/users'))


@admin_only
async def propagate_command(event):
    """
    Bulk-propagation: after a manual organize,
    find remaining episodes and ask yes/no per file.
    """
    # Get last manual entry
    manual = [r for r in organized_tbl.all() if r.get("method", "manual") == "manual"]
    entries = sorted(manual, key=lambda r: r["timestamp"], reverse=True)
    if not entries:
        return await event.respond("📁 No manual organizes to propagate from.")
    last = entries[0]
    folder = Path(last["path"]).parent
    title = last["title"]
    season = last["season"]
    ep0 = last["episode"]
    
    # Use organizer method
    items = organizer.find_remaining_episodes(folder, title, season, ep0)
    
    if not items:
        return await event.respond("✅ No remaining episodes found for bulk propagation.")
    
    # Initialize session
    bulk_sessions.create(event.sender_id, "propagating", {"items": items, "index": 0})
    cur = items[0]
    # Send first prompt with inline buttons
    await event.respond(
        f"📦 Bulk propagation started: 1/{len(items)}\n"
        f"`{cur['src'].name}` → `{cur['dest'].name}`",
        buttons=[
            [Button.inline("✅ Yes", f"bulk_ans:yes"),
             Button.inline("❌ No", f"bulk_ans:no")]
        ]
    )


async def bulk_answer(event):
    """Handle bulk propagation yes/no callbacks."""
    user = event.query.user_id
    if user not in bulk_sessions:
        return await event.answer(alert="No propagation in progress.")

    answer = event.data.decode().split(":", 1)[1]
    session = bulk_sessions.get(user)
    if not session:
        return await event.answer(alert="Session expired.")
    
    items = session.data.get("items", [])
    idx = session.data.get("index", 0)
    current = items[idx]

    # Handle confirm/skip
    if answer == "yes":
        try:
            organizer.safe_rename(current["src"], current["dest"])
            # Derive metadata
            dest_stem = Path(current["dest"]).stem
            title = dest_stem.split(" - ")[0]
            manual_entries = [r for r in organized_tbl.all() if r.get("method", "manual") == "manual"]
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

    # Advance
    session.data["index"] += 1
    if session.data["index"] < len(items):
        nxt = items[session.data["index"]]
        await event.edit(
            f"📦 Bulk propagation: {session.data['index']+1}/{len(items)}\n"
            f"`{nxt['src'].name}` → `{nxt['dest'].name}`",
            buttons=[
                [Button.inline("✅ Yes", f"bulk_ans:yes"),
                 Button.inline("❌ No", f"bulk_ans:no")]
            ]
        )
    else:
        await event.edit("✅ Bulk propagation complete.", buttons=None)
        bulk_sessions.clear(user)


@admin_only
async def history_command(event):
    """Handle /history command."""
    await show_history_page(event, offset=0, detail_eid=None)


async def history_page_callback(event):
    """Handle history pagination callbacks."""
    offset = int(event.pattern_match.group(1))
    await show_history_page(event, offset=offset, detail_eid=None)


async def history_detail_callback(event):
    """Handle history detail view callbacks."""
    eid = int(event.pattern_match.group(1))
    offset = int(event.pattern_match.group(2))
    await show_history_page(event, offset=offset, detail_eid=eid)


async def show_history_page(event, offset=0, detail_eid=None):
    """Show history page (list view or detail view)."""
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
            [Button.inline("🔁 Reorganize", f"reorg:{detail_eid}"),
             Button.inline("🗑️ Delete Entry", f"delorg:{detail_eid}")],
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
            if offset < 0:
                offset = 0

        page_entries = all_sorted[offset : offset + entries_per_page]

        if not page_entries and total_entries > 0:
            offset = max(0, total_entries - entries_per_page)
            if offset < 0:
                offset = 0
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
        if total_pages == 0 and total_entries > 0:
            total_pages = 1

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


async def reorganize_entry(event):
    """Handle reorganize button from history detail."""
    eid = int(event.data.decode().split(':')[1])
    entry = organized_tbl.get(doc_id=eid)
    if not entry:
        return await event.respond("⚠️ Entry not found.")
    
    if _run_finalize_callback:
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
        await _run_finalize_callback(event, session)
    else:
        await event.answer("Reorganize not available.", alert=True)


async def delete_organized_record(event):
    """Handle delete button from history detail."""
    eid = int(event.data.decode().split(':')[1])
    organized_tbl.remove(doc_ids=[eid])
    await event.answer("🗑️ Deleted record.", alert=False)
    await event.edit("✅ Record deleted.")


@admin_only
async def shutdown_command(event):
    """Admin shutdown command."""
    if shutdown_callback:
        await event.respond("🔄 Graceful shutdown initiated.")
        asyncio.create_task(shutdown_callback())
    else:
        await event.respond("⚠️ Shutdown not configured.")


@admin_only
async def users_command(event):
    """Show total unique users."""
    total = len(users_tbl.all())
    await event.respond(f"👥 Total users: {total}\nDB: {DB_PATH}")
