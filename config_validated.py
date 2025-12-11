"""
Validated Configuration - Pydantic BaseSettings

This module provides type-safe, validated configuration loading
with fail-fast behavior on missing or invalid values.

Usage:
    from config_validated import settings
    
    print(settings.api_id)
    print(settings.movies_dir)
"""
from pathlib import Path
from typing import List, Optional, Set
import mimetypes

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    """
    Bot configuration with validation.
    
    Loads from environment variables and .env file.
    Raises ValidationError on startup if required values are missing or invalid.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra env vars
    )
    
    # Required credentials
    api_id: int
    api_hash: str
    bot_token: str
    
    # Optional credentials
    tmdb_api_key: Optional[str] = None
    
    # Admin configuration
    admin_ids: List[int] = []
    
    # Directories
    base_dir: Path = Path("/data/jellyfin")
    download_dir: Optional[Path] = None
    movies_dir: Optional[Path] = None
    tv_dir: Optional[Path] = None
    anime_dir: Optional[Path] = None
    music_dir: Optional[Path] = None
    other_dir: Optional[Path] = None
    log_dir: Optional[Path] = None
    session_name: Optional[Path] = None
    db_file: str = "db.json"
    
    # Performance settings
    max_download_duration: int = 7200  # 2 hours
    max_concurrent_downloads: int = 3
    
    # Fuzzy matching thresholds
    low_confidence: float = 0.6
    high_confidence: float = 0.8
    
    @field_validator('admin_ids', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        """Parse comma-separated admin IDs string."""
        if isinstance(v, str):
            return [int(x) for x in v.split(',') if x.strip()]
        return v or []
    
    @field_validator('base_dir', 'download_dir', 'movies_dir', 'tv_dir', 
                     'anime_dir', 'music_dir', 'other_dir', 'log_dir', 'session_name',
                     mode='before')
    @classmethod
    def expand_path(cls, v):
        """Expand user home directory in paths."""
        if v is None:
            return None
        return Path(v).expanduser().resolve()
    
    @model_validator(mode='after')
    def set_default_directories(self):
        """Set default subdirectories based on base_dir."""
        if self.download_dir is None:
            self.download_dir = self.base_dir / "Downloads"
        if self.movies_dir is None:
            self.movies_dir = self.base_dir / "Movies"
        if self.tv_dir is None:
            self.tv_dir = self.base_dir / "TV"
        if self.anime_dir is None:
            self.anime_dir = self.base_dir / "Anime"
        if self.music_dir is None:
            self.music_dir = self.base_dir / "Music"
        if self.other_dir is None:
            self.other_dir = self.base_dir / "Other"
        if self.log_dir is None:
            self.log_dir = self.base_dir / "logs"
        if self.session_name is None:
            self.session_name = self.base_dir / "sessions" / "jellyfin"
        return self
    
    @property
    def db_path(self) -> Path:
        """Get full database path."""
        return self.base_dir / self.db_file


def get_media_extensions() -> Set[str]:
    """Get set of video file extensions from MIME types."""
    mimetypes.init()
    mimetypes.add_type('video/x-matroska', '.mkv', strict=False)
    
    combined_map = {}
    combined_map.update(mimetypes.types_map)
    combined_map.update(mimetypes.common_types)
    
    return {
        ext.lower()
        for ext, mime in combined_map.items()
        if mime and mime.startswith("video/")
    }


# Initialize settings (validates on import)
# If validation fails, raises pydantic.ValidationError with details
try:
    settings = BotSettings()
    MEDIA_EXTENSIONS = get_media_extensions()
except Exception as e:
    # Re-raise with helpful message
    raise SystemExit(f"Configuration error: {e}")


# Backwards-compatible exports
API_ID = settings.api_id
API_HASH = settings.api_hash
BOT_TOKEN = settings.bot_token
TMDB_API_KEY = settings.tmdb_api_key
ADMIN_IDS = settings.admin_ids

BASE_DIR = settings.base_dir
DOWNLOAD_DIR = settings.download_dir
MOVIES_DIR = settings.movies_dir
TV_DIR = settings.tv_dir
ANIME_DIR = settings.anime_dir
MUSIC_DIR = settings.music_dir
OTHER_DIR = settings.other_dir
LOG_DIR = settings.log_dir
SESSION_NAME = settings.session_name
DB_PATH = settings.db_path

MAX_DOWNLOAD_DURATION = settings.max_download_duration
LOW_CONFIDENCE = settings.low_confidence
HIGH_CONFIDENCE = settings.high_confidence
