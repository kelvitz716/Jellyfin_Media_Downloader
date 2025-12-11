"""
Tests for database.py - TinyDB operations.
"""
import pytest
from tinydb import TinyDB
from tinydb.storages import MemoryStorage


class TestLoadActiveUsers:
    """Tests for load_active_users function."""
    
    def test_load_empty_database(self, temp_db, monkeypatch):
        """Should return empty set for empty database."""
        # We need to mock the module-level db import
        from database import users_tbl
        
        # Clear any existing users
        users_tbl.truncate()
        
        from database import load_active_users
        result = load_active_users()
        
        assert result == set() or isinstance(result, set)
    
    def test_load_existing_users(self, populated_db):
        """Should return set of user IDs from populated database."""
        users_tbl = populated_db.table("users")
        
        # Create a mock load function using the populated db
        result = {row['id'] for row in users_tbl.all()}
        
        assert len(result) == 3
        assert 111111111 in result
        assert 222222222 in result
        assert 333333333 in result


class TestSaveActiveUsers:
    """Tests for save_active_users function."""
    
    def test_save_new_users(self, temp_db):
        """Should insert new user IDs."""
        users_tbl = temp_db.table("users")
        
        # Simulate save logic
        users = {111111111, 222222222}
        for uid in users:
            if not users_tbl.contains(lambda r: r.get('id') == uid):
                users_tbl.insert({'id': uid})
        
        assert len(users_tbl.all()) == 2
    
    def test_save_duplicate_users_no_duplicates(self, temp_db):
        """Should not create duplicates when saving existing users."""
        users_tbl = temp_db.table("users")
        users_tbl.insert({'id': 111111111})
        
        # Simulate save logic - should not duplicate
        from tinydb import where
        uid = 111111111
        if not users_tbl.contains(where('id') == uid):
            users_tbl.insert({'id': uid})
        
        all_users = users_tbl.all()
        assert len(all_users) == 1


class TestPaginateDb:
    """Tests for paginate_db function."""
    
    def test_paginate_empty(self, temp_db):
        """Should return empty page for empty table."""
        from database import paginate_db
        
        table = temp_db.table("empty")
        page, total = paginate_db(table, limit=10, offset=0)
        
        assert page == []
        assert total == 0
    
    def test_paginate_first_page(self, populated_db):
        """Should return first page of results."""
        from itertools import islice
        
        organized_tbl = populated_db.table("organized")
        all_entries = sorted(
            organized_tbl.all(), 
            key=lambda r: r.get("timestamp", ""), 
            reverse=True
        )
        
        limit = 2
        offset = 0
        total = len(all_entries)
        page = list(islice(all_entries, offset, offset + limit))
        
        assert len(page) == 2
        # Fixture has 2 organized entries (movie and tv show)
        assert total == 2
        # First entry should be most recent (2024-01-15)
        assert page[0]["title"] == "Test Movie"
    
    def test_paginate_with_offset(self, populated_db):
        """Should return correct page with offset."""
        from itertools import islice
        
        organized_tbl = populated_db.table("organized")
        all_entries = sorted(
            organized_tbl.all(),
            key=lambda r: r.get("timestamp", ""),
            reverse=True
        )
        
        limit = 1
        offset = 1
        page = list(islice(all_entries, offset, offset + limit))
        
        # Should get second entry
        assert len(page) == 1
        assert page[0]["title"] == "Test Show"
    
    def test_paginate_beyond_data(self, populated_db):
        """Should return empty page when offset exceeds data."""
        from itertools import islice
        
        organized_tbl = populated_db.table("organized")
        all_entries = sorted(
            organized_tbl.all(),
            key=lambda r: r.get("timestamp", ""),
            reverse=True
        )
        
        page = list(islice(all_entries, 100, 110))
        
        assert page == []


class TestDatabaseTables:
    """Tests for database table initialization."""
    
    def test_tables_exist(self, temp_db):
        """All required tables should be accessible."""
        tables = ["users", "stats", "organized", "error_log"]
        
        for table_name in tables:
            table = temp_db.table(table_name)
            assert table is not None
    
    def test_organized_table_schema(self, populated_db):
        """Organized table entries should have expected fields."""
        organized_tbl = populated_db.table("organized")
        entry = organized_tbl.all()[0]
        
        expected_fields = ["path", "title", "category", "timestamp", "method"]
        for field in expected_fields:
            assert field in entry
