import logging
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
