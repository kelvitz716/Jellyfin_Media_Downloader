"""
Tests for stats.py - BotStats tracking and persistence.
"""
import pytest
from datetime import datetime, timedelta


class TestBotStatsInit:
    """Tests for BotStats initialization."""
    
    def test_initial_values(self, fresh_stats):
        """Should initialize with zero counts."""
        assert fresh_stats.files_handled == 0
        assert fresh_stats.successful_downloads == 0
        assert fresh_stats.failed_downloads == 0
        assert fresh_stats.total_data == 0
        assert fresh_stats.peak_concurrent == 0
        assert fresh_stats.download_times == []
        assert fresh_stats.download_speeds == []
    
    def test_start_time_set(self, fresh_stats):
        """Should set start_time on initialization."""
        assert isinstance(fresh_stats.start_time, datetime)
        assert fresh_stats.start_time <= datetime.now()


class TestAddDownload:
    """Tests for add_download method."""
    
    def test_successful_download(self, fresh_stats):
        """Successful download should increment counters correctly."""
        size = 1024 * 1024 * 100  # 100 MB
        duration = 10.0  # seconds
        
        fresh_stats.add_download(size, duration, success=True)
        
        assert fresh_stats.files_handled == 1
        assert fresh_stats.successful_downloads == 1
        assert fresh_stats.failed_downloads == 0
        assert fresh_stats.total_data == size
        assert len(fresh_stats.download_times) == 1
        assert len(fresh_stats.download_speeds) == 1
    
    def test_failed_download(self, fresh_stats):
        """Failed download should only increment failed counter."""
        size = 1024 * 1024 * 100
        duration = 5.0
        
        fresh_stats.add_download(size, duration, success=False)
        
        assert fresh_stats.files_handled == 1
        assert fresh_stats.successful_downloads == 0
        assert fresh_stats.failed_downloads == 1
        assert fresh_stats.total_data == 0  # Data not counted for failures
        assert len(fresh_stats.download_times) == 0
        assert len(fresh_stats.download_speeds) == 0
    
    def test_multiple_downloads(self, fresh_stats):
        """Multiple downloads should accumulate correctly."""
        # Add 3 successful and 2 failed
        fresh_stats.add_download(100, 1.0, success=True)
        fresh_stats.add_download(200, 2.0, success=True)
        fresh_stats.add_download(300, 3.0, success=True)
        fresh_stats.add_download(100, 1.0, success=False)
        fresh_stats.add_download(200, 2.0, success=False)
        
        assert fresh_stats.files_handled == 5
        assert fresh_stats.successful_downloads == 3
        assert fresh_stats.failed_downloads == 2
        assert fresh_stats.total_data == 600  # Only successful
    
    def test_speed_calculation(self, fresh_stats):
        """Speed should be calculated as size/duration."""
        size = 1000
        duration = 10.0
        
        fresh_stats.add_download(size, duration, success=True)
        
        expected_speed = size / duration  # 100 bytes/sec
        assert fresh_stats.download_speeds[0] == expected_speed
    
    def test_zero_duration_handling(self, fresh_stats):
        """Zero duration should result in 0 speed (not division error)."""
        size = 1000
        duration = 0.0
        
        fresh_stats.add_download(size, duration, success=True)
        
        assert fresh_stats.download_speeds[0] == 0


class TestUpdatePeakConcurrent:
    """Tests for update_peak_concurrent method."""
    
    def test_updates_when_higher(self, fresh_stats):
        """Should update peak when current is higher."""
        fresh_stats.update_peak_concurrent(3)
        assert fresh_stats.peak_concurrent == 3
        
        fresh_stats.update_peak_concurrent(5)
        assert fresh_stats.peak_concurrent == 5
    
    def test_no_update_when_lower(self, fresh_stats):
        """Should not update peak when current is lower."""
        fresh_stats.update_peak_concurrent(5)
        fresh_stats.update_peak_concurrent(3)
        
        assert fresh_stats.peak_concurrent == 5
    
    def test_no_update_when_equal(self, fresh_stats):
        """Should not change when current equals peak."""
        fresh_stats.update_peak_concurrent(5)
        fresh_stats.update_peak_concurrent(5)
        
        assert fresh_stats.peak_concurrent == 5


class TestGetUptime:
    """Tests for get_uptime method."""
    
    def test_returns_timedelta(self, fresh_stats):
        """Should return a timedelta object."""
        uptime = fresh_stats.get_uptime()
        assert isinstance(uptime, timedelta)
    
    def test_uptime_is_positive(self, fresh_stats):
        """Uptime should be positive."""
        uptime = fresh_stats.get_uptime()
        assert uptime.total_seconds() >= 0


class TestGetAverageSpeed:
    """Tests for get_average_speed method."""
    
    def test_average_with_data(self, fresh_stats):
        """Should calculate correct average speed."""
        fresh_stats.add_download(1000, 10.0, success=True)  # 100 b/s
        fresh_stats.add_download(2000, 10.0, success=True)  # 200 b/s
        fresh_stats.add_download(3000, 10.0, success=True)  # 300 b/s
        
        avg = fresh_stats.get_average_speed()
        expected = (100 + 200 + 300) / 3
        
        assert avg == expected
    
    def test_average_empty(self, fresh_stats):
        """Should return 0 when no data."""
        avg = fresh_stats.get_average_speed()
        assert avg == 0


class TestGetAverageTime:
    """Tests for get_average_time method."""
    
    def test_average_with_data(self, fresh_stats):
        """Should calculate correct average time."""
        fresh_stats.add_download(100, 5.0, success=True)
        fresh_stats.add_download(100, 10.0, success=True)
        fresh_stats.add_download(100, 15.0, success=True)
        
        avg = fresh_stats.get_average_time()
        expected = (5.0 + 10.0 + 15.0) / 3
        
        assert avg == expected
    
    def test_average_empty(self, fresh_stats):
        """Should return 0 when no data."""
        avg = fresh_stats.get_average_time()
        assert avg == 0


class TestStatsPersistence:
    """Tests for stats loading and saving."""
    
    def test_save_format(self, temp_db):
        """Saved stats should have correct format."""
        from tinydb import where
        
        stats_tbl = temp_db.table("stats")
        
        # Simulate save
        doc = {
            "type": "global",
            "files_handled": 100,
            "successful_downloads": 95,
            "failed_downloads": 5,
            "total_data": 1024 * 1024 * 1024,
            "peak_concurrent": 3,
        }
        stats_tbl.upsert(doc, where('type') == 'global')
        
        saved = stats_tbl.get(where('type') == 'global')
        assert saved is not None
        assert saved["files_handled"] == 100
        assert saved["successful_downloads"] == 95
    
    def test_user_stats_format(self, temp_db):
        """User stats should use correct type format."""
        from tinydb import where
        
        stats_tbl = temp_db.table("stats")
        
        user_id = 111111111
        doc = {
            "type": f"user_{user_id}",
            "files_handled": 50,
            "successful_downloads": 48,
            "failed_downloads": 2,
        }
        stats_tbl.upsert(doc, where('type') == f'user_{user_id}')
        
        saved = stats_tbl.get(where('type') == f'user_{user_id}')
        assert saved is not None
        assert saved["files_handled"] == 50
