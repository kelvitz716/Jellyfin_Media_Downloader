from pathlib import Path
from dotenv import load_dotenv
import mimetypes
import os
import logging

# Load environment variables
load_dotenv()

# --- Configuration & Constants ---

# Required environment variables
REQUIRED_ENV = {
    'API_ID': {'val': None, 'required': True},
    'API_HASH': {'val': None, 'required': True},
    'BOT_TOKEN': {'val': None, 'required': True},
    'TMDB_API_KEY': {'val': None, 'required': False},  # metadata optional
}

# Maximum download duration (seconds); default 2 hours
MAX_DOWNLOAD_DURATION = int(os.getenv("MAX_DOWNLOAD_DURATION", "7200"))

# Load and validate env vars
print("Loading environment variables...")
for name, meta in REQUIRED_ENV.items():
    val = os.getenv(name)
    meta['val'] = val
    if val:
        print(f"[OK] {name} found")
    elif meta['required']:
        print(f"[MISSING] {name} is missing!")

API_ID = int(REQUIRED_ENV['API_ID']['val']) if REQUIRED_ENV['API_ID']['val'] else None
API_HASH = REQUIRED_ENV['API_HASH']['val']
BOT_TOKEN = REQUIRED_ENV['BOT_TOKEN']['val']
TMDB_API_KEY = REQUIRED_ENV['TMDB_API_KEY']['val']
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Directories
BASE_DIR = Path(os.getenv("BASE_DIR", "/data/jellyfin")).expanduser().resolve()
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", BASE_DIR / "Downloads")).expanduser().resolve()
MOVIES_DIR = Path(os.getenv("MOVIES_DIR", BASE_DIR / "Movies")).expanduser().resolve()
TV_DIR = Path(os.getenv("TV_DIR", BASE_DIR / "TV")).expanduser().resolve()
ANIME_DIR = Path(os.getenv("ANIME_DIR", BASE_DIR / "Anime")).expanduser().resolve()
MUSIC_DIR = Path(os.getenv("MUSIC_DIR", BASE_DIR / "Music")).expanduser().resolve()
OTHER_DIR = Path(os.getenv("OTHER_DIR", BASE_DIR / "Other")).expanduser().resolve()
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR / "logs")).expanduser().resolve()
SESSION_NAME = Path(os.getenv("SESSION_NAME", BASE_DIR / "sessions/jellyfin")).expanduser().resolve()

# Filenames list file (used in /organize or similar handlers)
FILENAMES_FILE = Path(os.getenv("FILENAMES_FILE", BASE_DIR / "filenames.txt"))

# Database file (TinyDB)
DB_PATH = BASE_DIR / os.getenv("DB_FILE", "db.json")

# Override incorrect MIME-to-extension mapping
mimetypes.init()
mimetypes.add_type('video/x-matroska', '.mkv', strict=False)

# Merge the two dicts so we see both “official” and “common” mappings
combined_map = {}
combined_map.update(mimetypes.types_map)
combined_map.update(mimetypes.common_types)

# Now pick video/* extensions
MEDIA_EXTENSIONS = {
    ext.lower()
    for ext, mime in combined_map.items()
    if mime and mime.startswith("video/")
}

# Fuzzy-matching thresholds
LOW_CONFIDENCE = float(os.getenv("LOW_CONFIDENCE", "0.6"))   # below this → OTHER
HIGH_CONFIDENCE = float(os.getenv("HIGH_CONFIDENCE", "0.8"))  # at or above this → auto-rename
