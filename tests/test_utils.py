"""
Tests for utils.py - Utility functions.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock


class TestSimilarity:
    """Tests for the similarity function."""
    
    def test_similarity_identical_strings(self):
        """Identical strings should return 1.0."""
        from utils import similarity
        assert similarity("hello", "hello") == 1.0
        assert similarity("The Matrix", "The Matrix") == 1.0
    
    def test_similarity_case_insensitive(self):
        """Similarity should be case-insensitive."""
        from utils import similarity
        assert similarity("Hello", "hello") == 1.0
        assert similarity("THE MATRIX", "the matrix") == 1.0
    
    def test_similarity_completely_different(self):
        """Completely different strings should return low ratio."""
        from utils import similarity
        result = similarity("abc", "xyz")
        assert result == 0.0
    
    def test_similarity_partial_match(self):
        """Partial matches should return intermediate values."""
        from utils import similarity
        result = similarity("Breaking Bad", "Breaking")
        assert 0.5 < result < 1.0
        
    def test_similarity_empty_strings(self):
        """Empty strings should return 1.0 (both empty = identical)."""
        from utils import similarity
        assert similarity("", "") == 1.0
    
    def test_similarity_one_empty(self):
        """One empty string should return 0.0."""
        from utils import similarity
        assert similarity("hello", "") == 0.0
        assert similarity("", "hello") == 0.0


class TestCreateDirSafely:
    """Tests for the create_dir_safely function."""
    
    def test_creates_single_directory(self, tmp_path):
        """Should create a single directory."""
        from utils import create_dir_safely
        
        new_dir = tmp_path / "new_folder"
        create_dir_safely(new_dir)
        
        assert new_dir.exists()
        assert new_dir.is_dir()
    
    def test_creates_nested_directories(self, tmp_path):
        """Should create nested directories."""
        from utils import create_dir_safely
        
        nested = tmp_path / "level1" / "level2" / "level3"
        create_dir_safely(nested)
        
        assert nested.exists()
        assert nested.is_dir()
    
    def test_existing_directory_no_error(self, tmp_path):
        """Should not raise error if directory already exists."""
        from utils import create_dir_safely
        
        existing = tmp_path / "existing"
        existing.mkdir()
        
        # Should not raise
        create_dir_safely(existing)
        assert existing.exists()


class TestAdminOnly:
    """Tests for the admin_only decorator."""
    
    @pytest.mark.asyncio
    async def test_admin_allowed(self, monkeypatch):
        """Admin users should be allowed."""
        # Mock ADMIN_IDS
        monkeypatch.setattr("utils.ADMIN_IDS", [111111111, 222222222])
        
        from utils import admin_only
        
        # Create mock function
        mock_func = AsyncMock(return_value="success")
        decorated = admin_only(mock_func)
        
        # Create mock event with admin sender
        event = MagicMock()
        event.sender_id = 111111111
        event.respond = AsyncMock()
        
        result = await decorated(event)
        
        mock_func.assert_called_once_with(event)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_non_admin_blocked(self, monkeypatch):
        """Non-admin users should be blocked."""
        monkeypatch.setattr("utils.ADMIN_IDS", [111111111])
        
        from utils import admin_only
        
        mock_func = AsyncMock(return_value="success")
        decorated = admin_only(mock_func)
        
        # Create mock event with non-admin sender
        event = MagicMock()
        event.sender_id = 999999999  # Not an admin
        event.respond = AsyncMock()
        
        await decorated(event)
        
        # Function should not be called
        mock_func.assert_not_called()
        # Should respond with permission denied
        event.respond.assert_called_once()
        assert "Permission denied" in str(event.respond.call_args)
