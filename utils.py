import logging
import os
from pathlib import Path
from difflib import SequenceMatcher
from tenacity import retry, stop_after_attempt, wait_exponential
from config import ADMIN_IDS


logger = logging.getLogger(__name__)

def similarity(a: str, b: str) -> float:
    """Return a ratio [0.0–1.0] of how similar two strings are."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def create_dir_safely(path: Path):
    if not path.exists():
        logger.info(f"Creating directory: {path}")
    path.mkdir(parents=True, exist_ok=True)

def admin_only(func):
    """Decorator to restrict command to admins."""
    async def wrapper(event):
        if event.sender_id not in ADMIN_IDS:
            return await event.respond("⚠️ Permission denied.")
        return await func(event)
    return wrapper

def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename to prevent path traversal and filesystem issues.
    
    Security features:
    - Removes path separators (/, \)
    - Removes invalid characters for Windows/Linux
    - Handles Windows reserved names (CON, PRN, AUX, etc.)
    - Prevents empty filenames
    - Truncates to max filesystem length
    
    Args:
        filename: Original filename from user
        max_length: Maximum filename length (default 255 for most filesystems)
    
    Returns:
        Safe filename suitable for all platforms
    
    Examples:
        >>> sanitize_filename("../../../etc/passwd")
        'passwd'
        >>> sanitize_filename("file<>:test.mp4")
        'file___test.mp4'
        >>> sanitize_filename("CON.txt")
        '_CON.txt'
    """
    # Remove any path components - only keep the basename
    filename = os.path.basename(filename)
    
    # Replace path separators that might have been encoded
    filename = filename.replace('/', '_').replace('\\', '_')
    
    # Remove or replace invalid characters
    # Windows: < > : " / \ | ? * and control characters (0x00-0x1F)
    # Linux: only / and null byte, but we sanitize more for consistency
    invalid_chars = '<>:"|?*\x00'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove control characters (ASCII 0-31)
    filename = ''.join(char if ord(char) >= 32 else '_' for char in filename)
    
    # Handle Windows reserved names (case-insensitive)
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    name_without_ext = Path(filename).stem.upper()
    if name_without_ext in reserved_names:
        filename = f"_{filename}"
    
    # Remove leading/trailing spaces and dots (Windows doesn't allow these)
    filename = filename.strip('. ')
    
    # Truncate to max length while preserving extension
    if len(filename) > max_length:
        stem = Path(filename).stem
        ext = Path(filename).suffix
        max_stem_length = max_length - len(ext)
        if max_stem_length > 0:
            filename = stem[:max_stem_length] + ext
        else:
            # Extension itself is too long, just truncate everything
            filename = filename[:max_length]
    
    # Ensure not empty after sanitization
    if not filename or filename == '.':
        filename = 'unnamed_file'
    
    return filename

def validate_path_within_base(path: Path, base_dir: Path) -> bool:
    """
    Ensure path is within base directory (prevent path traversal).
    
    This prevents attacks where a malicious path tries to escape
    the intended directory using .. or absolute paths.
    
    Args:
        path: Path to validate
        base_dir: Base directory that should contain the path
    
    Returns:
        True if path is safely within base_dir, False otherwise
    
    Examples:
        >>> validate_path_within_base(Path("/data/downloads/file.mp4"), Path("/data/downloads"))
        True
        >>> validate_path_within_base(Path("/data/downloads/../../../etc/passwd"), Path("/data/downloads"))
        False
    """
    try:
        # Resolve both paths to absolute, canonical forms
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        
        # Check if path is relative to base
        resolved_path.relative_to(resolved_base)
        return True
    except ValueError:
        # relative_to() raises ValueError if path is not relative to base
        logger.warning(f"Path traversal attempt detected: {path} is outside {base_dir}")
        return False
