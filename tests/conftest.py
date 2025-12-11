"""
Shared pytest fixtures for Jellyfin Media Downloader tests.

This conftest.py provides fixtures WITHOUT importing any project modules.
Project modules are imported within tests using lazy imports to allow
environment setup to happen first.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, List, Any

import pytest
from tinydb import TinyDB
from tinydb.storages import MemoryStorage


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture
def temp_db():
    """In-memory TinyDB instance for testing."""
    db = TinyDB(storage=MemoryStorage)
    yield db
    db.close()


@pytest.fixture
def populated_db(temp_db):
    """TinyDB with pre-populated test data."""
    users_tbl = temp_db.table("users")
    stats_tbl = temp_db.table("stats")
    organized_tbl = temp_db.table("organized")
    
    # Add test users
    users_tbl.insert_multiple([
        {"id": 111111111},
        {"id": 222222222},
        {"id": 333333333},
    ])
    
    # Add organized entries
    organized_tbl.insert_multiple([
        {
            "path": "/data/jellyfin/Movies/Test Movie (2023)/Test Movie (2023) [1080p].mkv",
            "title": "Test Movie",
            "category": "movie",
            "year": "2023",
            "resolution": "1080p",
            "organized_by": 111111111,
            "timestamp": "2024-01-15T10:30:00",
            "method": "manual"
        },
        {
            "path": "/data/jellyfin/TV/Test Show/Season 01/Test Show - S01E01 [720p].mkv",
            "title": "Test Show",
            "category": "tv",
            "season": 1,
            "episode": 1,
            "resolution": "720p",
            "organized_by": 111111111,
            "timestamp": "2024-01-14T08:00:00",
            "method": "auto"
        },
    ])
    
    # Add stats
    stats_tbl.insert({
        "type": "global",
        "files_handled": 100,
        "successful_downloads": 95,
        "failed_downloads": 5,
        "total_data": 1024 * 1024 * 1024 * 50,
        "peak_concurrent": 3,
    })
    
    return temp_db


# ============================================================================
# Directory Fixtures
# ============================================================================

@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary media directory structure."""
    dirs = {
        "base": tmp_path / "jellyfin",
        "downloads": tmp_path / "jellyfin" / "Downloads",
        "movies": tmp_path / "jellyfin" / "Movies",
        "tv": tmp_path / "jellyfin" / "TV",
        "anime": tmp_path / "jellyfin" / "Anime",
        "music": tmp_path / "jellyfin" / "Music",
        "other": tmp_path / "jellyfin" / "Other",
    }
    
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    
    return dirs


@pytest.fixture
def sample_media_files(temp_dirs):
    """Create sample media files for testing."""
    downloads = temp_dirs["downloads"]
    
    files = [
        "The.Matrix.1999.1080p.BluRay.x264.mkv",
        "Inception.2010.720p.WEB-DL.mp4",
        "Breaking.Bad.S01E01.Pilot.1080p.HDTV.mkv",
        "Breaking.Bad.S01E02.720p.HDTV.mkv",
        "random_video.avi",
    ]
    
    created_files = []
    for f in files:
        file_path = downloads / f
        file_path.touch()
        file_path.write_bytes(b"0" * 1024)
        created_files.append(file_path)
    
    return created_files


# ============================================================================
# Sample Filename Fixtures
# ============================================================================

@pytest.fixture
def movie_filenames() -> List[str]:
    """Sample movie filenames for GuessIt testing."""
    return [
        "The.Matrix.1999.1080p.BluRay.x264.mkv",
        "Inception.2010.720p.WEB-DL.mp4",
        "Interstellar.2014.2160p.UHD.BluRay.mkv",
        "The Godfather (1972) [1080p].mkv",
        "Pulp.Fiction.1994.REMASTERED.1080p.BluRay.mkv",
    ]


@pytest.fixture
def tv_filenames() -> List[str]:
    """Sample TV show filenames for GuessIt testing."""
    return [
        "Breaking.Bad.S01E01.Pilot.1080p.HDTV.mkv",
        "Game.of.Thrones.S08E06.The.Iron.Throne.1080p.mkv",
        "The.Office.US.S03E12.720p.WEB.mkv",
    ]


@pytest.fixture
def anime_filenames() -> List[str]:
    """Sample anime filenames for GuessIt testing."""
    return [
        "[SubGroup] Attack on Titan - 01 [1080p].mkv",
        "[Fansub] Demon Slayer - S01E01 [720p].mkv",
        "My Hero Academia S06E01 1080p WEB.mkv",
    ]


# ============================================================================
# Mock TMDb Responses
# ============================================================================

@pytest.fixture
def mock_tmdb_movie_response() -> Dict[str, Any]:
    """Mock TMDb movie search response."""
    return {
        "page": 1,
        "results": [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-30",
            }
        ],
    }


@pytest.fixture
def mock_tmdb_tv_response() -> Dict[str, Any]:
    """Mock TMDb TV search response."""
    return {
        "page": 1,
        "results": [
            {
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
            }
        ],
    }


@pytest.fixture
def mock_tmdb_keywords_anime() -> Dict[str, Any]:
    """Mock TMDb keywords response containing anime."""
    return {
        "id": 12345,
        "keywords": [
            {"id": 1, "name": "anime"},
            {"id": 2, "name": "action"},
        ]
    }


# ============================================================================
# Mock Telegram Objects
# ============================================================================

@pytest.fixture
def mock_telegram_event():
    """Create a mock Telegram event."""
    event = MagicMock()
    event.sender_id = 111111111
    event.message = MagicMock()
    event.message.id = 12345
    event.message.media = None
    event.raw_text = ""
    event.respond = AsyncMock()
    event.reply = AsyncMock()
    event.answer = AsyncMock()
    event.edit = AsyncMock()
    return event


@pytest.fixture
def mock_telegram_client():
    """Create a mock Telegram client."""
    client = MagicMock()
    client.is_connected = MagicMock(return_value=True)
    client.download_media = AsyncMock()
    client.send_message = AsyncMock()
    return client


# ============================================================================
# Performance Testing Helpers
# ============================================================================

@pytest.fixture
def large_db(temp_db):
    """Create a TinyDB with many entries for performance testing."""
    organized_tbl = temp_db.table("organized")
    
    entries = []
    for i in range(1000):
        entries.append({
            "path": f"/data/jellyfin/Movies/Movie{i}/Movie{i} [1080p].mkv",
            "title": f"Movie {i}",
            "category": "movie",
            "year": str(2000 + (i % 24)),
            "resolution": "1080p",
            "organized_by": 111111111,
            "timestamp": f"2024-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00",
            "method": "auto" if i % 2 == 0 else "manual"
        })
    
    organized_tbl.insert_multiple(entries)
    return temp_db


@pytest.fixture
def many_files(temp_dirs):
    """Create many files for performance testing."""
    downloads = temp_dirs["downloads"]
    
    files = []
    for i in range(500):
        file_path = downloads / f"Movie.{i}.2023.1080p.mkv"
        file_path.touch()
        files.append(file_path)
    
    return files


# ============================================================================
# Stats Testing Fixtures
# ============================================================================

class MockBotStats:
    """Mock BotStats class for testing without importing the actual module."""
    
    def __init__(self):
        self.files_handled = 0
        self.successful_downloads = 0
        self.failed_downloads = 0
        self.total_data = 0
        self.peak_concurrent = 0
        self.download_times = []
        self.download_speeds = []
        self.start_time = datetime.now()
    
    def add_download(self, size: int, duration: float, success: bool = True):
        """Record a download."""
        self.files_handled += 1
        if success:
            self.successful_downloads += 1
            self.total_data += size
            self.download_times.append(duration)
            # Append 0 speed for zero duration, otherwise calculate
            if duration > 0:
                self.download_speeds.append(size / duration)
            else:
                self.download_speeds.append(0)
        else:
            self.failed_downloads += 1
    
    def update_peak_concurrent(self, current: int):
        """Update peak concurrent downloads."""
        if current > self.peak_concurrent:
            self.peak_concurrent = current
    
    def get_uptime(self):
        """Get uptime as timedelta."""
        from datetime import timedelta
        return datetime.now() - self.start_time
    
    def get_average_speed(self) -> float:
        """Get average download speed."""
        if not self.download_speeds:
            return 0.0
        return sum(self.download_speeds) / len(self.download_speeds)
    
    def get_average_time(self) -> float:
        """Get average download time."""
        if not self.download_times:
            return 0.0
        return sum(self.download_times) / len(self.download_times)


@pytest.fixture
def fresh_stats():
    """Create a fresh BotStats-like instance for testing."""
    return MockBotStats()
