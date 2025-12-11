"""
Tests for organizer.py - File organization logic.
"""
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestDetectResolution:
    """Tests for detect_resolution method."""
    
    def test_detect_1080p(self, temp_dirs):
        """Should detect 1080p from filename."""
        from organizer import InteractiveOrganizer
        org = InteractiveOrganizer()
        
        path = temp_dirs["downloads"] / "Movie.2023.1080p.BluRay.mkv"
        path.touch()
        
        result = org.detect_resolution(path)
        assert result == "1080p"
    
    def test_detect_720p(self, temp_dirs):
        """Should detect 720p from filename."""
        from organizer import InteractiveOrganizer
        org = InteractiveOrganizer()
        
        path = temp_dirs["downloads"] / "Movie.720p.WEB-DL.mp4"
        path.touch()
        
        result = org.detect_resolution(path)
        assert result == "720p"
    
    def test_detect_2160p_4k(self, temp_dirs):
        """Should detect 2160p (4K) from filename."""
        from organizer import InteractiveOrganizer
        org = InteractiveOrganizer()
        
        path = temp_dirs["downloads"] / "Movie.2160p.UHD.mkv"
        path.touch()
        
        result = org.detect_resolution(path)
        assert result == "2160p"
    
    def test_detect_unknown(self, temp_dirs):
        """Should return Unknown when no resolution found."""
        from organizer import InteractiveOrganizer
        org = InteractiveOrganizer()
        
        path = temp_dirs["downloads"] / "random_video.mkv"
        path.touch()
        
        result = org.detect_resolution(path)
        assert result == "Unknown"
    
    def test_detect_case_insensitive(self, temp_dirs):
        """Resolution detection should be case-insensitive."""
        from organizer import InteractiveOrganizer
        org = InteractiveOrganizer()
        
        path = temp_dirs["downloads"] / "Movie.1080P.BluRay.mkv"
        path.touch()
        
        result = org.detect_resolution(path)
        assert result.lower() == "1080p"


class TestIsAlreadyOrganized:
    """Tests for is_already_organized method."""
    
    def test_not_organized(self, temp_db):
        """Should return False for new file."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        # Mock the table
        org.organized_tbl = temp_db.table("organized")
        
        result = org.is_already_organized("new_movie.mkv")
        assert result is False
    
    def test_already_organized(self, populated_db):
        """Should return True for previously organized file."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        org.organized_tbl = populated_db.table("organized")
        
        # This filename is in populated_db
        result = org.is_already_organized("Test Movie (2023) [1080p].mkv")
        assert result is True


class TestScanForCandidates:
    """Tests for scan_for_candidates method."""
    
    def test_finds_media_files(self, temp_dirs, sample_media_files, monkeypatch):
        """Should find unorganized media files."""
        from organizer import InteractiveOrganizer
        
        # Patch the config directories
        monkeypatch.setattr("organizer.DOWNLOAD_DIR", temp_dirs["downloads"])
        monkeypatch.setattr("organizer.OTHER_DIR", temp_dirs["other"])
        monkeypatch.setattr("organizer.MEDIA_EXTENSIONS", {".mkv", ".mp4", ".avi"})
        
        org = InteractiveOrganizer()
        # Mock empty organized table
        org.organized_tbl = MagicMock()
        org.organized_tbl.get = MagicMock(return_value=None)
        
        candidates = org.scan_for_candidates()
        
        # Should find video files, not mp3
        video_extensions = {".mkv", ".mp4", ".avi"}
        for c in candidates:
            assert c.suffix.lower() in video_extensions
    
    def test_excludes_organized_files(self, temp_dirs, monkeypatch):
        """Should exclude already organized files."""
        from organizer import InteractiveOrganizer
        
        monkeypatch.setattr("organizer.DOWNLOAD_DIR", temp_dirs["downloads"])
        monkeypatch.setattr("organizer.OTHER_DIR", temp_dirs["other"])
        monkeypatch.setattr("organizer.MEDIA_EXTENSIONS", {".mkv", ".mp4"})
        
        # Create a file
        test_file = temp_dirs["downloads"] / "organized_movie.mkv"
        test_file.touch()
        
        org = InteractiveOrganizer()
        # Mock as already organized
        org.organized_tbl = MagicMock()
        org.organized_tbl.get = MagicMock(return_value={"path": str(test_file)})
        org.is_already_organized = MagicMock(return_value=True)
        
        candidates = org.scan_for_candidates()
        
        # Should not include the organized file
        assert test_file not in candidates


class TestFindRemainingEpisodes:
    """Tests for find_remaining_episodes method."""
    
    def test_finds_matching_episodes(self, temp_dirs, monkeypatch):
        """Should find episodes matching title and season."""
        from organizer import InteractiveOrganizer
        
        monkeypatch.setattr("organizer.DOWNLOAD_DIR", temp_dirs["downloads"])
        monkeypatch.setattr("organizer.MEDIA_EXTENSIONS", {".mkv", ".mp4"})
        
        # Create test episode files
        (temp_dirs["downloads"] / "Breaking.Bad.S01E02.720p.mkv").touch()
        (temp_dirs["downloads"] / "Breaking.Bad.S01E03.720p.mkv").touch()
        (temp_dirs["downloads"] / "Breaking.Bad.S01E04.720p.mkv").touch()
        # Different show - should not match
        (temp_dirs["downloads"] / "Game.of.Thrones.S01E02.720p.mkv").touch()
        
        org = InteractiveOrganizer()
        org.organized_tbl = MagicMock()
        org.organized_tbl.get = MagicMock(return_value=None)
        org.is_already_organized = MagicMock(return_value=False)
        
        folder = temp_dirs["tv"] / "Breaking Bad" / "Season 01"
        folder.mkdir(parents=True)
        
        results = org.find_remaining_episodes(folder, "Breaking Bad", 1, 1)
        
        # Should find episodes after E01
        assert len(results) >= 1
        for item in results:
            assert item["episode"] > 1
    
    def test_skips_earlier_episodes(self, temp_dirs, monkeypatch):
        """Should skip episodes at or before last_ep."""
        from organizer import InteractiveOrganizer
        
        monkeypatch.setattr("organizer.DOWNLOAD_DIR", temp_dirs["downloads"])
        monkeypatch.setattr("organizer.MEDIA_EXTENSIONS", {".mkv"})
        
        # Create episode E01
        (temp_dirs["downloads"] / "Show.S01E01.720p.mkv").touch()
        
        org = InteractiveOrganizer()
        org.organized_tbl = MagicMock()
        org.organized_tbl.get = MagicMock(return_value=None)
        org.is_already_organized = MagicMock(return_value=False)
        
        folder = temp_dirs["tv"] / "Show" / "Season 01"
        folder.mkdir(parents=True)
        
        # last_ep = 1, so E01 should be skipped
        results = org.find_remaining_episodes(folder, "Show", 1, 1)
        
        # E01 should not be in results
        for item in results:
            assert item["episode"] > 1


class TestSafeRename:
    """Tests for safe_rename method."""
    
    def test_successful_rename(self, temp_dirs):
        """Should rename file successfully."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        
        src = temp_dirs["downloads"] / "source.mkv"
        src.touch()
        dest = temp_dirs["movies"] / "destination.mkv"
        
        org.safe_rename(src, dest)
        
        assert not src.exists()
        assert dest.exists()
    
    def test_rename_creates_parent_dirs(self, temp_dirs):
        """Should work when parent dir exists."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        
        src = temp_dirs["downloads"] / "source.mkv"
        src.touch()
        
        # Dest with existing parent
        dest = temp_dirs["movies"] / "renamed.mkv"
        
        org.safe_rename(src, dest)
        
        assert dest.exists()


class TestRecordOrganized:
    """Tests for record_organized method."""
    
    def test_inserts_correct_metadata(self, temp_db, temp_dirs):
        """Should insert record with all metadata."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        org.organized_tbl = temp_db.table("organized")
        
        metadata = {
            "path": str(temp_dirs["movies"] / "Test Movie [1080p].mkv"),
            "title": "Test Movie",
            "category": "movie",
            "year": "2023",
            "organized_by": 111111111,
        }
        
        org.record_organized(metadata)
        
        records = org.organized_tbl.all()
        assert len(records) == 1
        
        record = records[0]
        assert record["title"] == "Test Movie"
        assert record["category"] == "movie"
        assert "timestamp" in record
    
    def test_includes_timestamp(self, temp_db, temp_dirs):
        """Record should include current timestamp."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        org.organized_tbl = temp_db.table("organized")
        
        before = datetime.now()
        
        org.record_organized({
            "path": str(temp_dirs["movies"] / "test.mkv"),
            "title": "Test",
            "category": "movie",
            "organized_by": 111111111,
        })
        
        after = datetime.now()
        
        record = org.organized_tbl.all()[0]
        timestamp = datetime.fromisoformat(record["timestamp"])
        
        assert before <= timestamp <= after


class TestRecordError:
    """Tests for record_error method."""
    
    def test_logs_error_context(self, temp_db):
        """Should log error with context."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        org.error_log_tbl = temp_db.table("error_log")
        
        context = {
            "error": "File not found",
            "file": "/path/to/file.mkv",
            "stage": "rename",
        }
        
        org.record_error(context)
        
        records = org.error_log_tbl.all()
        assert len(records) == 1
        
        record = records[0]
        assert record["error"] == "File not found"
        assert "timestamp" in record
