"""
Button Definitions - Minimal Play Theme
All inline keyboard buttons with emoji personality and consistent labeling.
"""

from telethon import Button

class Buttons:
    """Button builders with Minimal Play theme - emoji + clear text."""
    
    # === NAVIGATION ===
    @staticmethod
    def pagination(page: int, total_pages: int, callback_prefix: str):
        """Create pagination buttons with previous/next navigation."""
        buttons = []
        if page > 1:
            buttons.append(Button.inline("◀ Prev", f"{callback_prefix}:{page - 1}"))
        if page < total_pages:
            buttons.append(Button.inline("Next ▶", f"{callback_prefix}:{page + 1}"))
        return buttons if buttons else None
    
    # === DOWNLOAD ACTIONS ===
    @staticmethod
    def cancel_download(message_id: int):
        """Cancel download button."""
        return Button.inline("❌ Cancel Download", f"cancel:{message_id}")
    
    # === ORGANIZE CATEGORY ===
    @staticmethod
    def category_selection():
        """Category selection buttons for file organization."""
        return [
            [Button.inline("🎬 Movie", "org_cat:movie"),
             Button.inline("📺 TV Show", "org_cat:tv")],
            [Button.inline("🎌 Anime", "org_cat:anime"),
             Button.inline("↷ Skip", "org_cat:skip")]
        ]
    
    # === PREVIEW PANEL ===
    @staticmethod
    def preview_panel():
        """Preview confirmation buttons."""
        return [
            [Button.inline("✅ Confirm", b"confirm")],
            [Button.inline("✏️ Edit", b"amend")],
            [Button.inline("❌ Discard", b"discard")]
        ]
    
    # === YES/NO ===
    @staticmethod
    def yes_no():
        """Simple yes/no buttons for confirmations."""
        return [
            [Button.inline("✅ Yes", "bulk_ans:yes"),
             Button.inline("❌ No", "bulk_ans:no")]
        ]
    
    # === HISTORY ACTIONS ===
    @staticmethod
    def history_navigation(offset: int, total_entries: int, entries_per_page: int):
        """Navigation buttons for history pagination."""
        nav_row = []
        if offset > 0:
            nav_row.append(Button.inline("◀ Prev", f"hist_page:{max(0, offset - entries_per_page)}"))
        if offset + entries_per_page < total_entries:
            nav_row.append(Button.inline("Next ▶", f"hist_page:{offset + entries_per_page}"))
        return nav_row if nav_row else []
    
    @staticmethod
    def history_detail_actions(detail_eid: int, offset: int, entries_per_page: int):
        """Action buttons for history detail view."""
        return [
            [Button.inline("🔄 Re-organize", f"reorg:{detail_eid}"),
             Button.inline("🗑️ Delete Entry", f"delorg:{detail_eid}")],
            [Button.inline(f"◀ Back to History (Page {(offset // entries_per_page) + 1})", f"hist_page:{offset}")]
        ]
    
    # === FILE SELECTION ===
    @staticmethod
    def file_selection(files: list, offset: int = 0):
        """Create file selection buttons with pagination."""
        buttons = []
        page_size = 5
        page_files = files[offset:offset + page_size]
        
        for idx, file in enumerate(page_files):
            buttons.append([Button.inline(f"📄 {file.name}", f"pick:{offset + idx}")])
        
        # Add pagination if needed
        nav_row = []
        if offset > 0:
            nav_row.append(Button.inline("◀ Prev", f"files:{max(0, offset - page_size)}"))
        if offset + page_size < len(files):
            nav_row.append(Button.inline("Next ▶", f"files:{offset + page_size}"))
        
        if nav_row:
            buttons.append(nav_row)
        
        return buttons
