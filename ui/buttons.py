"""
Button Builders
All inline keyboard buttons in one place.
"""

from telethon import Button


class Buttons:
    """Button builders for inline keyboards."""
    
    # === BUTTON LABELS ===
    CANCEL = "Cancel"
    CANCEL_DOWNLOAD = "Cancel download"
    CONFIRM = "Confirm"
    AMEND = "Amend"
    DISCARD = "Discard"
    YES = "Yes"
    NO = "No"
    SKIP = "Skip"
    MORE = "More (page {page})"
    PREV = "Prev"
    NEXT = "Next"
    BACK = "Back"
    DELETE = "Delete"
    REORGANIZE = "Reorganize"
    
    # === CATEGORY BUTTONS ===
    CATEGORY_MOVIE = "Movie"
    CATEGORY_TV = "TV"
    CATEGORY_ANIME = "Anime"
    CATEGORY_SKIP = "Skip"
    
    @staticmethod
    def cancel_download(message_id, filename=None):
        """Create cancel download button."""
        if filename:
            display = filename if len(filename) <= 20 else filename[:17] + "..."
            label = f"{Buttons.CANCEL}: {display}"
        else:
            label = Buttons.CANCEL_DOWNLOAD
        
        return Button.inline(label, f"cancel_{message_id}")
    
    @staticmethod
    def queue_more(page):
        """Create 'More' button for queue pagination."""
        return Button.inline(Buttons.MORE.format(page=page), data=f"queue:{page}")
    
    @staticmethod
    def queue_navigation(page, has_prev, has_next):
        """Create navigation buttons for queue."""
        buttons = []
        if has_prev:
            buttons.append(Button.inline(Buttons.PREV, f"queue:{page-1}"))
        if has_next:
            buttons.append(Button.inline(Buttons.NEXT, f"queue:{page+1}"))
        return buttons if buttons else None
    
    @staticmethod
    def preview_panel():
        """Create preview panel buttons (Confirm/Amend/Discard)."""
        return [
            [Button.inline(Buttons.CONFIRM, b"confirm")],
            [Button.inline(Buttons.AMEND, b"amend")],
            [Button.inline(Buttons.DISCARD, b"discard")],
        ]
    
    @staticmethod
    def yes_no():
        """Create Yes/No buttons."""
        return [
            [Button.inline(Buttons.YES, f"bulk_ans:yes"),
             Button.inline(Buttons.NO, f"bulk_ans:no")]
        ]
    
    @staticmethod
    def category_selection():
        """Create category selection buttons."""
        return [
            [Button.inline(Buttons.CATEGORY_MOVIE, "org_cat:movie"),
             Button.inline(Buttons.CATEGORY_TV, "org_cat:tv")],
            [Button.inline(Buttons.CATEGORY_ANIME, "org_cat:anime"),
             Button.inline(Buttons.CATEGORY_SKIP, "org_cat:skip")]
        ]
    
    @staticmethod
    def organize_file_list(files_dict):
        """Create buttons for file selection in organize command."""
        buttons = []
        for key, path in files_dict.items():
            buttons.append([Button.inline(path.name, f'org_file:{key}')])
        return buttons
    
    @staticmethod
    def history_navigation(offset, entries_per_page, total, has_prev, has_next):
        """Create navigation buttons for history."""
        nav = []
        if has_prev:
            nav.append(Button.inline(Buttons.PREV, f"hist_page:{max(0, offset - entries_per_page)}"))
        if has_next:
            nav.append(Button.inline(Buttons.NEXT, f"hist_page:{offset + entries_per_page}"))
        return nav if nav else None
    
    @staticmethod
    def history_entry_actions(entry_id, timestamp_display):
        """Create action buttons for history entry."""
        return [
            Button.inline(f"{Buttons.REORGANIZE} {timestamp_display}", f"reorg:{entry_id}"),
            Button.inline(timestamp_display, f"noop:{entry_id}"),
            Button.inline(Buttons.DELETE, f"delorg:{entry_id}")
        ]
    
    @staticmethod
    def history_detail_back(offset):
        """Create back button for history detail view."""
        return Button.inline(Buttons.BACK, f"hist_page:{offset}")
    
    @staticmethod
    def organized_page_navigation(offset, has_prev, has_next):
        """Create navigation for organized files page."""
        nav = []
        if has_prev:
            nav.append(Button.inline(Buttons.PREV, f"org_page:{max(0, offset-10)}"))
        if has_next:
            nav.append(Button.inline(Buttons.NEXT, f"org_page:{offset+10}"))
        return nav if nav else None
