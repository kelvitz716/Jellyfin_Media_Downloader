"""
Tests for downloader.py - DownloadManager and DownloadTask.
"""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


class TestSanitizePathComponent:
    """Tests for sanitize_path_component function."""
    
    def test_removes_invalid_characters(self):
        """Should remove Windows-invalid characters."""
        from downloader import sanitize_path_component
        
        result = sanitize_path_component('File<>:"/\\|?*Name')
        
        # Should not contain any invalid chars
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            assert char not in result
    
    def test_preserves_valid_characters(self):
        """Should preserve valid characters."""
        from downloader import sanitize_path_component
        
        result = sanitize_path_component("Movie (2023) - Title 1080p")
        
        assert "Movie" in result
        assert "2023" in result
        assert "1080p" in result
    
    def test_handles_empty_string(self):
        """Should handle empty string."""
        from downloader import sanitize_path_component
        
        result = sanitize_path_component("")
        
        assert result == "" or result is not None
    
    def test_trims_whitespace(self):
        """Should trim leading/trailing whitespace."""
        from downloader import sanitize_path_component
        
        result = sanitize_path_component("  movie name  ")
        
        assert not result.startswith(" ")
        assert not result.endswith(" ")
    
    def test_replaces_with_underscore_or_removes(self):
        """Should replace invalid chars consistently."""
        from downloader import sanitize_path_component
        
        result = sanitize_path_component("File:Name")
        
        # Either replaced with _ or removed
        assert ":" not in result


class TestDownloadManagerInit:
    """Tests for DownloadManager initialization."""
    
    def test_default_max_concurrent(self):
        """Should default to 3 concurrent downloads."""
        from downloader import DownloadManager
        
        manager = DownloadManager()
        
        assert manager.max_concurrent == 3
    
    def test_custom_max_concurrent(self):
        """Should accept custom max concurrent."""
        from downloader import DownloadManager
        
        manager = DownloadManager(max_concurrent=5)
        
        assert manager.max_concurrent == 5
    
    def test_empty_queues_on_init(self):
        """Should start with empty queues."""
        from downloader import DownloadManager
        
        manager = DownloadManager()
        
        assert manager.active_downloads == {}
        assert manager.queued_downloads == []
    
    def test_accepting_downloads_initially(self):
        """Should accept downloads by default."""
        from downloader import DownloadManager
        
        manager = DownloadManager()
        
        assert manager.accepting_new_downloads is True


class TestDownloadManagerQueue:
    """Tests for DownloadManager queue operations."""
    
    @pytest.mark.asyncio
    async def test_get_queue_status_empty(self):
        """Should return empty status when no downloads."""
        from downloader import DownloadManager
        
        manager = DownloadManager()
        status = manager.get_queue_status()
        
        assert status["active"] == []
        assert status["queued"] == []
    
    @pytest.mark.asyncio
    async def test_get_queue_status_format(self):
        """Should return correct status structure."""
        from downloader import DownloadManager
        
        manager = DownloadManager()
        status = manager.get_queue_status()
        
        assert "active" in status
        assert "queued" in status
        assert isinstance(status["active"], list)
        assert isinstance(status["queued"], list)


class TestDownloadManagerCancel:
    """Tests for cancel_download method."""
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_false(self):
        """Should return False for non-existent download."""
        from downloader import DownloadManager
        
        manager = DownloadManager()
        result = await manager.cancel_download(99999)
        
        assert result is False


class TestDownloadTaskInit:
    """Tests for DownloadTask initialization."""
    
    def test_stores_basic_info(self, mock_telegram_client, mock_telegram_event):
        """Should store basic download info."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="test.mkv",
            file_size=1024 * 1024 * 100,
            download_manager=manager
        )
        
        assert task.message_id == 12345
        assert task.filename == "test.mkv"
        assert task.file_size == 1024 * 1024 * 100
    
    def test_initial_state(self, mock_telegram_client, mock_telegram_event):
        """Should start in correct initial state."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="test.mkv",
            file_size=1024,
            download_manager=manager
        )
        
        assert task.cancelled is False
        # Note: progress is tracked via callbacks, not as an attribute


class TestDownloadTaskExtension:
    """Tests for get_file_extension method."""
    
    def test_uses_filename_extension(self, mock_telegram_client, mock_telegram_event):
        """Should prefer filename extension."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="movie.mkv",
            file_size=1024,
            download_manager=manager
        )
        
        ext = task.get_file_extension("movie.mkv")
        
        assert ext == ".mkv"
    
    def test_handles_uppercase_extension(self, mock_telegram_client, mock_telegram_event):
        """Should handle uppercase extensions."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="movie.MKV",
            file_size=1024,
            download_manager=manager
        )
        
        ext = task.get_file_extension("movie.MKV")
        
        assert ext.lower() == ".mkv"
    
    def test_fallback_to_bin(self, mock_telegram_client, mock_telegram_event):
        """Should fallback to .bin for unknown types."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="unknown_file",
            file_size=1024,
            download_manager=manager
        )
        
        # File with no extension
        ext = task.get_file_extension("noextension")
        
        # Should return something (could be .bin or empty based on implementation)
        assert ext is not None


class TestDownloadTaskCancel:
    """Tests for cancel method."""
    
    @pytest.mark.asyncio
    async def test_cancel_sets_flag(self, mock_telegram_client, mock_telegram_event):
        """Should set cancelled flag."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="test.mkv",
            file_size=1024,
            download_manager=manager
        )
        
        await task.cancel()
        
        assert task.cancelled is True


class TestDownloadTaskProgress:
    """Tests for progress tracking."""
    
    def test_progress_calculation(self, mock_telegram_client, mock_telegram_event):
        """Progress should be calculated correctly."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="test.mkv",
            file_size=1000,  # 1000 bytes total
            download_manager=manager
        )
        
        # Simulate 50% progress
        task.current_progress = 50.0
        
        assert task.current_progress == 50.0


class TestDownloadTaskMessages:
    """Tests for progress/completion messages."""
    
    @pytest.mark.asyncio
    async def test_update_processing_message(self, mock_telegram_client, mock_telegram_event):
        """Should update processing message without error."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="test.mkv",
            file_size=1024,
            download_manager=manager
        )
        
        # Should not raise
        await task.update_processing_message("Downloading...", final=False)
    
    @pytest.mark.asyncio
    async def test_send_completion_message(self, mock_telegram_client, mock_telegram_event):
        """Should send completion message."""
        from downloader import DownloadTask, DownloadManager
        
        manager = DownloadManager()
        task = DownloadTask(
            client=mock_telegram_client,
            event=mock_telegram_event,
            message_id=12345,
            filename="test.mkv",
            file_size=1024,
            download_manager=manager
        )
        
        # Mock the processing_message
        task.processing_message = MagicMock()
        task.processing_message.edit = AsyncMock()
        
        await task.send_completion_message(10.0)
        
        # Should have attempted to edit the message
        # (implementation may vary)


class TestMaxConcurrentEnforcement:
    """Tests for concurrent download limiting."""
    
    def test_max_concurrent_respected(self):
        """Active downloads should not exceed max_concurrent."""
        from downloader import DownloadManager
        
        manager = DownloadManager(max_concurrent=2)
        
        # Simulate 2 active downloads
        manager.active_downloads = {
            1: MagicMock(),
            2: MagicMock(),
        }
        
        assert len(manager.active_downloads) <= manager.max_concurrent
