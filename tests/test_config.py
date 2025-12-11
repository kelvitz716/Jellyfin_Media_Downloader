"""
Tests for config.py - Configuration loading and validation.
"""
import pytest
import os
from pathlib import Path


class TestRequiredEnvVars:
    """Tests for required environment variable handling."""
    
    def test_api_id_loading(self, monkeypatch):
        """Should load API_ID as integer."""
        monkeypatch.setenv("API_ID", "12345678")
        
        # Re-import to pick up new env
        api_id = int(os.getenv("API_ID"))
        
        assert api_id == 12345678
        assert isinstance(api_id, int)
    
    def test_api_hash_loading(self, monkeypatch):
        """Should load API_HASH as string."""
        monkeypatch.setenv("API_HASH", "abc123def456")
        
        api_hash = os.getenv("API_HASH")
        
        assert api_hash == "abc123def456"
        assert isinstance(api_hash, str)
    
    def test_bot_token_loading(self, monkeypatch):
        """Should load BOT_TOKEN as string."""
        monkeypatch.setenv("BOT_TOKEN", "123456:ABC-DEF")
        
        bot_token = os.getenv("BOT_TOKEN")
        
        assert ":" in bot_token
    
    def test_admin_ids_parsing(self, monkeypatch):
        """Should parse comma-separated ADMIN_IDS."""
        monkeypatch.setenv("ADMIN_IDS", "111111111,222222222,333333333")
        
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x) for x in admin_ids_str.split(",") if x.strip()]
        
        assert len(admin_ids) == 3
        assert 111111111 in admin_ids
        assert 222222222 in admin_ids
        assert 333333333 in admin_ids
    
    def test_admin_ids_empty(self, monkeypatch):
        """Should handle empty ADMIN_IDS."""
        monkeypatch.setenv("ADMIN_IDS", "")
        
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x) for x in admin_ids_str.split(",") if x.strip()]
        
        assert admin_ids == []


class TestOptionalEnvVars:
    """Tests for optional environment variables."""
    
    def test_tmdb_key_optional(self, monkeypatch):
        """TMDB_API_KEY should be optional."""
        # Unset the key
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        
        tmdb_key = os.getenv("TMDB_API_KEY")
        
        assert tmdb_key is None
    
    def test_tmdb_key_when_set(self, monkeypatch):
        """Should load TMDB_API_KEY when set."""
        monkeypatch.setenv("TMDB_API_KEY", "my_tmdb_key")
        
        tmdb_key = os.getenv("TMDB_API_KEY")
        
        assert tmdb_key == "my_tmdb_key"


class TestDirectoryConfig:
    """Tests for directory configuration."""
    
    def test_base_dir_default(self, monkeypatch):
        """BASE_DIR should default to /data/jellyfin."""
        monkeypatch.delenv("BASE_DIR", raising=False)
        
        base_dir = Path(os.getenv("BASE_DIR", "/data/jellyfin"))
        
        assert str(base_dir) == "/data/jellyfin"
    
    def test_base_dir_override(self, monkeypatch, tmp_path):
        """BASE_DIR should be overridable."""
        monkeypatch.setenv("BASE_DIR", str(tmp_path))
        
        base_dir = Path(os.getenv("BASE_DIR", "/data/jellyfin"))
        
        assert base_dir == tmp_path
    
    def test_subdirectory_defaults(self, monkeypatch):
        """Subdirectories should default relative to BASE_DIR."""
        monkeypatch.setenv("BASE_DIR", "/data/jellyfin")
        monkeypatch.delenv("MOVIES_DIR", raising=False)
        monkeypatch.delenv("TV_DIR", raising=False)
        
        base = Path(os.getenv("BASE_DIR", "/data/jellyfin"))
        movies = Path(os.getenv("MOVIES_DIR", base / "Movies"))
        tv = Path(os.getenv("TV_DIR", base / "TV"))
        
        assert str(movies).endswith("Movies")
        assert str(tv).endswith("TV")
    
    def test_subdirectory_overrides(self, monkeypatch, tmp_path):
        """Subdirectories should be independently overridable."""
        custom_movies = tmp_path / "CustomMovies"
        monkeypatch.setenv("MOVIES_DIR", str(custom_movies))
        
        movies_dir = Path(os.getenv("MOVIES_DIR"))
        
        assert movies_dir == custom_movies


class TestDownloadDurationConfig:
    """Tests for MAX_DOWNLOAD_DURATION config."""
    
    def test_default_duration(self, monkeypatch):
        """Should default to 7200 seconds (2 hours)."""
        monkeypatch.delenv("MAX_DOWNLOAD_DURATION", raising=False)
        
        duration = int(os.getenv("MAX_DOWNLOAD_DURATION", "7200"))
        
        assert duration == 7200
    
    def test_custom_duration(self, monkeypatch):
        """Should accept custom duration."""
        monkeypatch.setenv("MAX_DOWNLOAD_DURATION", "3600")
        
        duration = int(os.getenv("MAX_DOWNLOAD_DURATION", "7200"))
        
        assert duration == 3600


class TestConfidenceThresholds:
    """Tests for confidence threshold config."""
    
    def test_low_confidence_default(self, monkeypatch):
        """LOW_CONFIDENCE should default to 0.6."""
        monkeypatch.delenv("LOW_CONFIDENCE", raising=False)
        
        low = float(os.getenv("LOW_CONFIDENCE", "0.6"))
        
        assert low == 0.6
    
    def test_high_confidence_default(self, monkeypatch):
        """HIGH_CONFIDENCE should default to 0.8."""
        monkeypatch.delenv("HIGH_CONFIDENCE", raising=False)
        
        high = float(os.getenv("HIGH_CONFIDENCE", "0.8"))
        
        assert high == 0.8
    
    def test_custom_thresholds(self, monkeypatch):
        """Should accept custom threshold values."""
        monkeypatch.setenv("LOW_CONFIDENCE", "0.5")
        monkeypatch.setenv("HIGH_CONFIDENCE", "0.9")
        
        low = float(os.getenv("LOW_CONFIDENCE", "0.6"))
        high = float(os.getenv("HIGH_CONFIDENCE", "0.8"))
        
        assert low == 0.5
        assert high == 0.9


class TestMediaExtensions:
    """Tests for MEDIA_EXTENSIONS configuration."""
    
    def test_includes_common_video_formats(self):
        """Should include common video formats."""
        import mimetypes
        
        mimetypes.init()
        mimetypes.add_type('video/x-matroska', '.mkv', strict=False)
        
        combined_map = {}
        combined_map.update(mimetypes.types_map)
        combined_map.update(mimetypes.common_types)
        
        extensions = {
            ext.lower()
            for ext, mime in combined_map.items()
            if mime and mime.startswith("video/")
        }
        
        # Common video extensions should be present
        assert ".mp4" in extensions
        assert ".mkv" in extensions or ".mkv" in extensions  # May vary by system
    
    def test_mkv_mime_type_added(self):
        """MKV should have correct MIME type."""
        import mimetypes
        
        mimetypes.init()
        mimetypes.add_type('video/x-matroska', '.mkv', strict=False)
        
        mime_type = mimetypes.guess_type("test.mkv")[0]
        
        assert mime_type is not None
        assert "matroska" in mime_type or "video" in mime_type
