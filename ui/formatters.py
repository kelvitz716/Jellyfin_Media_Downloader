"""
Formatters
Data formatting utilities for presentation.
"""

import humanize
from datetime import timedelta
from pathlib import Path


class Formatters:
    """Data formatting utilities."""
    
    @staticmethod
    def progress_bar(progress, length=10):
        """Create a text progress bar."""
        filled = min(int(progress // 10), length)
        return "[" + "█" * filled + "─" * (length - filled) + f"] {progress:.0f}%"
    
    @staticmethod
    def file_size(bytes_count):
        """Format file size in human-readable format."""
        return humanize.naturalsize(bytes_count)
    
    @staticmethod
    def duration(seconds):
        """Format duration in human-readable format."""
        return humanize.precisedelta(timedelta(seconds=seconds))
    
    @staticmethod
    def speed(bytes_per_second):
        """Format speed in human-readable format."""
        return f"{humanize.naturalsize(bytes_per_second)}/s"
    
    @staticmethod
    def time_ago(dt):
        """Format datetime as 'time ago'."""
        return humanize.naturaltime(dt)
    
    @staticmethod
    def filename_display(filename, max_length=50):
        """Truncate filename for display."""
        if len(filename) <= max_length:
            return filename
        return filename[:max_length-3] + "..."
    
    @staticmethod
    def queue_item(index, filename, size=None):
        """Format a queue item."""
        if size:
            return f"{index}. `{filename}` ({Formatters.file_size(size)})"
        return f"{index}. `{filename}`"
    
    @staticmethod
    def active_download(index, filename, progress):
        """Format an active download item."""
        bar = Formatters.progress_bar(progress)
        return f"{index}. `{filename}`  {bar}"
    
    @staticmethod
    def format_test_result(test_name, status, details=None):
        """Format a test result line."""
        status_symbol = {
            'OK': '',
            'FAILED': '',
            'WARNING': ''
        }.get(status, '')
        
        line = f"{status_symbol} {test_name}: {status}"
        if details:
            line += f" - {details}"
        return line
    
    @staticmethod
    def format_history_entry(entry):
        """Format a history entry for display."""
        title = entry.get('title', 'Unknown')
        year = entry.get('year', '')
        category = entry.get('category', '')
        
        label = f"{title}"
        if year:
            label += f" ({year})"
        if category:
            label += f" [{category}]"
        
        return label
    
    @staticmethod
    def format_history_detail(entry):
        """Format detailed history entry information."""
        from .messages import Messages
        
        lines = [Messages.HISTORY_DETAIL_HEADER, ""]
        
        if 'path' in entry:
            lines.append(f"{Messages.HISTORY_FILE}: `{Path(entry['path']).name}`")
        if 'title' in entry:
            lines.append(f"{Messages.HISTORY_TITLE}: {entry['title']}")
        if 'category' in entry:
            lines.append(f"{Messages.HISTORY_CATEGORY}: {entry['category']}")
        if 'year' in entry:
            lines.append(f"{Messages.HISTORY_YEAR}: {entry.get('year', 'N/A')}")
        if 'season' in entry:
            lines.append(f"{Messages.HISTORY_SEASON}: {entry.get('season', 'N/A')}")
        if 'episode' in entry:
            lines.append(f"{Messages.HISTORY_EPISODE}: {entry.get('episode', 'N/A')}")
        if 'resolution' in entry:
            lines.append(f"{Messages.HISTORY_RESOLUTION}: {entry.get('resolution', 'N/A')}")
        if 'method' in entry:
            lines.append(f"{Messages.HISTORY_METHOD}: {entry.get('method', 'manual')}")
        if 'organized_by' in entry:
            lines.append(f"{Messages.HISTORY_ORGANIZED_BY}: {entry['organized_by']}")
        if 'timestamp' in entry:
            from datetime import datetime
            dt = datetime.fromisoformat(entry['timestamp'])
            lines.append(f"{Messages.HISTORY_TIMESTAMP}: {Formatters.time_ago(dt)}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_queue_message(active, queued, page, per_page):
        """Format complete queue message."""
        from .messages import Messages
        
        lines = [Messages.format_queue_header(page), ""]
        
        # Currently downloading
        if active:
            lines.append(f"{Messages.QUEUE_NOW}")
            for i, (_mid, fn, prog) in enumerate(active, 1):
                lines.append(Formatters.active_download(i, fn, prog))
            lines.append("")
        else:
            lines.append(f"{Messages.QUEUE_NOW} {Messages.QUEUE_IDLE}\n")
        
        # Upcoming (paginated)
        start = (page - 1) * per_page
        page_items = queued[start:start + per_page]
        
        if page_items:
            lines.append(f"{Messages.QUEUE_UPCOMING}")
            for idx, (_pos, _mid, fn, sz) in enumerate(page_items, start + 1):
                lines.append(Formatters.queue_item(idx, fn, sz))
        else:
            lines.append(Messages.QUEUE_NO_MORE)
        
        return "\n".join(lines)
