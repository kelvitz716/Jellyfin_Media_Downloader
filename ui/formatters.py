"""
Formatters - Minimal Play Theme
Data formatting utilities with clean progress bars and humanized numbers.
"""

import humanize
from datetime import timedelta
from pathlib import Path


class Formatters:
    """Data formatting utilities with Minimal Play aesthetic."""
    
    @staticmethod
    def progress_bar(progress, length=10):
        """Create a clean text progress bar using blocks.
        
        Uses ▓ (filled) and ░ (empty) for a clean, modern look.
        """
        filled = min(int(progress / 10), length)
        empty = length - filled
        return "▓" * filled + "░" * empty + f" {progress:.0f}%"
    
    @staticmethod
    def file_size(bytes_count):
        """Format file size in human-readable format (e.g., 2.1 GB)."""
        return humanize.naturalsize(bytes_count, binary=True)
    
    @staticmethod
    def duration(seconds):
        """Format duration in human-readable format (e.g., 4m 20s)."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            m = int(seconds / 60)
            s = int(seconds % 60)
            return f"{m}m {s}s" if s > 0 else f"{m}m"
        else:
            # For longer durations, use humanize
            return humanize.precisedelta(timedelta(seconds=seconds))
    
    @staticmethod
    def speed(bytes_per_second):
        """Format speed in human-readable format (e.g., 4.5 MB/s)."""
        return f"{humanize.naturalsize(bytes_per_second, binary=True)}/s"
    
    @staticmethod
    def time_ago(dt):
        """Format datetime as 'time ago' (e.g., 12 minutes ago)."""
        return humanize.naturaltime(dt)
    
    @staticmethod
    def filename_display(filename, max_length=50):
        """Truncate filename for display."""
        if len(filename) <= max_length:
            return filename
        return filename[:max_length-3] + "..."
    
    # === DOWNLOAD FORMATTERS ===
    
    @staticmethod
    def format_download_progress(filename, is_large, elapsed, progress, downloaded, speed, eta):
        """Format the download progress message with clean spacing."""
        status_type = "⬇️ Downloading (Large File)" if is_large else "⬇️ Downloading"
        
        return f"""{status_type}
{filename}

{Formatters.progress_bar(progress)}

💾 {downloaded}
⚡ {speed} · ⏱️ {eta} left

Running for: {elapsed}"""
    
    @staticmethod
    def format_download_complete(filename, suggested_filename, is_large, size, duration, speed):
        """Format the download completion message."""
        file_type = "📦 Large file" if is_large else "📄 File"
        
        return f"""✅ Download complete!
{filename}

{file_type} · {size}
⏱️ Downloaded in {duration}
⚡ Average {speed}

Suggested name: `{suggested_filename}`"""
    
    # === HISTORY FORMATTERS ===
    
    @staticmethod
    def format_history_detail(title, original_file, method, category, resolution, time):
        """Format detailed history entry information with emojis."""
        
        # Category emoji mapping
        category_emoji = {
            'movie': '🎬',
            'tv': '📺',
            'anime': '🎌'
        }.get(category.lower(), '📄')
        
        text = f"""{category_emoji} {title}

📄 Original: {original_file}
🏷️ Category: {category}"""
        
        if resolution and resolution != "N/A":
            text += f"\n📺 Quality: {resolution}"
        
        text += f"\n🕐 Organized {time} · `[{method}]`"
        
        return text
    
    # === QUEUE FORMATTERS ===
    
    @staticmethod
    def queue_item(index, filename, size=None):
        """Format a queue item with consistent styling."""
        # Detect media type by extension
        ext = Path(filename).suffix.lower()
        emoji = {
            '.mp4': '🎬', '.mkv': '🎬', '.avi': '🎬',
            '.mp3': '🎵', '.flac': '🎵', '.wav': '🎵',
            '.pdf': '📄', '.zip': '📦'
        }.get(ext, '📄')
        
        if size:
            return f"{emoji} [{index}] {filename} ({Formatters.file_size(size)})"
        return f"{emoji} [{index}] {filename}"
    
    @staticmethod
    def active_download(index, filename, progress):
        """Format an active download item with progress bar."""
        # Detect media type
        ext = Path(filename).suffix.lower()
        emoji = {
            '.mp4': '🎬', '.mkv': '🎬', '.avi': '🎬',
            '.mp3': '🎵', '.flac': '🎵', '.wav': '🎵',
        }.get(ext, '📄')
        
        bar = Formatters.progress_bar(progress)
        return f"{emoji} [{index}] {filename} {bar}"
    
    # === STATS FORMATTERS ===
    
    @staticmethod
    def format_stats(uptime, files_handled, successful, failed, total_data, avg_speed, avg_time, peak_concurrent, max_concurrent, active_count, queued_count):
        """Format complete stats message with Minimal Play styling."""
        success_rate = (successful / files_handled * 100) if files_handled > 0 else 0
        
        return f"""📊 Stats

⏰ Uptime: {uptime}
📁 Files: {files_handled} total · ✅ {successful} successful

⚡ Download Performance
→ 💾 {total_data} transferred
→ 🚀 {avg_speed} average speed
→ ⏱️ {avg_time} per file
→ 📊 {success_rate:.1f}% success rate

📈 Activity
→ Peak: {peak_concurrent}/{max_concurrent} concurrent
→ Current: {active_count} downloading · {queued_count} in queue"""
