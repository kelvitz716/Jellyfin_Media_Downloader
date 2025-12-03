import asyncio
import re
import logging
from pathlib import Path
from typing import List
from datetime import datetime

from telethon import Button, events
from guessit import guessit
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import DOWNLOAD_DIR, OTHER_DIR, MEDIA_EXTENSIONS
from database import organized_tbl, error_log_tbl
from utils import similarity

# UI Layer
from ui.messages import Messages
from ui.buttons import Buttons


logger = logging.getLogger(__name__)

class InteractiveOrganizer:
    def __init__(self):
        self.organized_tbl = organized_tbl
        self.error_log_tbl = error_log_tbl

    def is_already_organized(self, file_name: str) -> bool:
        """Check TinyDB to see if this filename was already handled."""
        # Note: TinyDB query might be slow if table is large.
        # Using a lambda here as in original code.
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
        cat = await ask(Messages.ORGANIZE_ENTER_CATEGORY)
        cat = cat.lower()
        if cat not in {"movie", "tv", "anime"}:
            await session.respond(Messages.ORGANIZE_INVALID_CATEGORY)
            cat = "movie"

        # 2) title
        title = await ask(Messages.ORGANIZE_ENTER_TITLE)

        # 3) year
        year_text = await ask(Messages.ORGANIZE_ENTER_YEAR)
        year = int(year_text) if year_text.isdigit() else None

        # 4) season/episode if needed
        season = episode = None
        if cat in {"tv", "anime"}:
            s = await ask(Messages.ORGANIZE_ENTER_SEASON)
            e = await ask(Messages.ORGANIZE_ENTER_EPISODE)
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
        kb = Buttons.preview_panel()
        msg = await session.respond(
            Messages.PREVIEW_RENAME.format(src=src.name, dest=proposed_dest.name),
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
            await session.respond(Messages.PREVIEW_TIMEOUT)
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
            "timestamp": datetime.now().isoformat(),
            "method": metadata.get("method", "manual"),
        }
        self.organized_tbl.insert(entry)

    async def show_bulk_preview_panel(self, session, items: List[dict]):
        """After first episode, show bulk items with Confirm/Amend/Skip."""
        for idx, item in enumerate(items, start=1):
            await asyncio.sleep(0)  # allow cancellation
            await session.respond(
                Messages.PREVIEW_BULK_ITEM.format(
                    current=idx,
                    total=len(items),
                    src=item['src'].name,
                    dest=item['dest'].name
                )
            )

    async def process_bulk_queue(self):
        """Iterate through pending bulk items and handle admin responses."""
        # Placeholder: implement per-item confirm/amend/skip flow in Sprint 7
        await asyncio.sleep(0)

    def record_error(self, context: dict):
        """Log error context into error_log_tbl."""
        self.error_log_tbl.insert({
            **context,
            "timestamp": datetime.now().isoformat()
        })

    def find_remaining_episodes(self, folder: Path, title: str, season: int, last_ep: int) -> list:
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
            if self.is_already_organized(p.name):
                continue
            # build destination path
            base = f"{title} - S{season:02d}E{ep:02d}"
            res  = self.detect_resolution(p)
            new_name = f"{base} [{res}]{p.suffix}"
            dest = folder / new_name
            results.append({"src": p, "dest": dest, "season": season, "episode": ep})
        # sort by episode number
        return sorted(results, key=lambda i: i["episode"])
