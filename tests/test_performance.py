"""
Performance and efficiency tests for Jellyfin Media Downloader.

These tests establish baseline performance metrics and ensure operations
complete within acceptable time limits.
"""
import pytest
import time
from pathlib import Path
from tinydb import TinyDB, where
from tinydb.storages import MemoryStorage


class TestSimilarityPerformance:
    """Performance tests for string similarity function."""
    
    def test_similarity_speed(self, benchmark):
        """Similarity function should be fast."""
        from utils import similarity
        
        result = benchmark(similarity, "Breaking Bad", "Breaking")
        
        assert 0 <= result <= 1
    
    def test_similarity_batch(self):
        """Should handle many comparisons quickly."""
        from utils import similarity
        
        titles = [f"Movie Title {i}" for i in range(100)]
        query = "Movie Title 50"
        
        start = time.perf_counter()
        
        for title in titles:
            similarity(query, title)
        
        elapsed = time.perf_counter() - start
        
        # 100 comparisons should take less than 100ms
        assert elapsed < 0.1, f"Similarity batch took {elapsed:.3f}s"
    
    def test_similarity_long_strings(self, benchmark):
        """Should handle long strings efficiently."""
        from utils import similarity
        
        long_a = "The " + "Very " * 100 + "Long Movie Title"
        long_b = "The " + "Very " * 100 + "Long Series Title"
        
        result = benchmark(similarity, long_a, long_b)
        
        assert 0 <= result <= 1


class TestDatabasePerformance:
    """Performance tests for TinyDB operations."""
    
    def test_insert_performance(self, benchmark, temp_db):
        """Single insert should be fast."""
        table = temp_db.table("test")
        
        def insert_one():
            table.insert({"name": "test", "value": 123})
        
        benchmark(insert_one)
    
    def test_batch_insert_performance(self, temp_db):
        """Batch insert should be efficient."""
        table = temp_db.table("batch")
        
        entries = [{"name": f"item_{i}", "value": i} for i in range(1000)]
        
        start = time.perf_counter()
        table.insert_multiple(entries)
        elapsed = time.perf_counter() - start
        
        # 1000 inserts should take less than 1 second in memory
        assert elapsed < 1.0, f"Batch insert took {elapsed:.3f}s"
        assert len(table.all()) == 1000
    
    def test_query_performance(self, large_db, benchmark):
        """Query should be reasonably fast even with many entries."""
        table = large_db.table("organized")
        
        def query_by_category():
            return table.search(where('category') == 'movie')
        
        result = benchmark(query_by_category)
        
        # Should find entries
        assert len(result) > 0
    
    def test_pagination_performance(self, large_db):
        """Pagination should be efficient."""
        from itertools import islice
        
        table = large_db.table("organized")
        
        start = time.perf_counter()
        
        # Paginate through all entries
        for offset in range(0, 1000, 100):
            all_entries = sorted(
                table.all(),
                key=lambda r: r.get("timestamp", ""),
                reverse=True
            )
            page = list(islice(all_entries, offset, offset + 100))
        
        elapsed = time.perf_counter() - start
        
        # Full pagination should take less than 2 seconds
        assert elapsed < 2.0, f"Pagination took {elapsed:.3f}s"
    
    def test_lambda_query_performance(self, large_db):
        """Lambda-based queries (slow pattern) should still complete."""
        table = large_db.table("organized")
        
        start = time.perf_counter()
        
        # This is the slow pattern used in is_already_organized
        result = table.get(lambda r: r.get("path", "").endswith("Movie500 [1080p].mkv"))
        
        elapsed = time.perf_counter() - start
        
        # Should complete (even if slow)
        assert elapsed < 1.0, f"Lambda query took {elapsed:.3f}s"


class TestFileScanningPerformance:
    """Performance tests for file system operations."""
    
    def test_scan_many_files(self, many_files, temp_dirs, monkeypatch):
        """Scanning many files should be efficient."""
        from organizer import InteractiveOrganizer
        
        monkeypatch.setattr("organizer.DOWNLOAD_DIR", temp_dirs["downloads"])
        monkeypatch.setattr("organizer.OTHER_DIR", temp_dirs["other"])
        monkeypatch.setattr("organizer.MEDIA_EXTENSIONS", {".mkv", ".mp4", ".avi"})
        
        org = InteractiveOrganizer()
        org.is_already_organized = lambda x: False  # Mock as not organized
        
        start = time.perf_counter()
        candidates = org.scan_for_candidates()
        elapsed = time.perf_counter() - start
        
        # 500 files should scan in less than 1 second
        assert elapsed < 1.0, f"File scanning took {elapsed:.3f}s"
        assert len(candidates) == 500
    
    def test_resolution_detection_batch(self, temp_dirs):
        """Resolution detection should be fast for many files."""
        from organizer import InteractiveOrganizer
        
        org = InteractiveOrganizer()
        
        # Create test files
        files = []
        for i in range(200):
            f = temp_dirs["downloads"] / f"Movie.{i}.1080p.mkv"
            f.touch()
            files.append(f)
        
        start = time.perf_counter()
        
        for f in files:
            org.detect_resolution(f)
        
        elapsed = time.perf_counter() - start
        
        # 200 resolution detections should take less than 100ms
        assert elapsed < 0.1, f"Resolution detection took {elapsed:.3f}s"


class TestStatsPerformance:
    """Performance tests for stats operations."""
    
    def test_add_download_performance(self, benchmark, fresh_stats):
        """Adding downloads should be fast."""
        def add_one():
            fresh_stats.add_download(1024*1024, 1.0, success=True)
        
        benchmark(add_one)
    
    def test_stats_update_throughput(self, fresh_stats):
        """Should handle many stat updates quickly."""
        start = time.perf_counter()
        
        for i in range(10000):
            fresh_stats.add_download(1024 * i, 0.1 * (i % 100 + 1), success=True)
        
        elapsed = time.perf_counter() - start
        
        # 10000 updates should take less than 1 second
        assert elapsed < 1.0, f"Stats updates took {elapsed:.3f}s"
    
    def test_average_calculation_with_many_entries(self, fresh_stats):
        """Average calculations should be efficient with many entries."""
        # Add 10000 downloads
        for i in range(10000):
            fresh_stats.add_download(1024 * (i + 1), 0.1 * (i % 100 + 1), success=True)
        
        start = time.perf_counter()
        
        # Calculate averages 100 times
        for _ in range(100):
            fresh_stats.get_average_speed()
            fresh_stats.get_average_time()
        
        elapsed = time.perf_counter() - start
        
        # 200 calculations should be fast
        assert elapsed < 0.5, f"Average calculations took {elapsed:.3f}s"


class TestGuessItPerformance:
    """Performance tests for GuessIt parsing."""
    
    def test_guessit_parsing_speed(self, benchmark, movie_filenames):
        """GuessIt parsing should be reasonably fast."""
        from guessit import guessit
        
        def parse_all():
            return [guessit(fn) for fn in movie_filenames]
        
        result = benchmark(parse_all)
        
        assert len(result) == len(movie_filenames)
    
    def test_guessit_batch_parsing(self, movie_filenames, tv_filenames, anime_filenames):
        """Batch parsing should complete quickly."""
        from guessit import guessit
        
        all_filenames = movie_filenames + tv_filenames + anime_filenames
        
        start = time.perf_counter()
        
        for fn in all_filenames * 10:  # 150 parses
            guessit(fn)
        
        elapsed = time.perf_counter() - start
        
        # 150 parses should take less than 2 seconds
        assert elapsed < 2.0, f"Batch parsing took {elapsed:.3f}s"


class TestSanitizationPerformance:
    """Performance tests for path sanitization."""
    
    def test_sanitize_speed(self, benchmark):
        """Path sanitization should be fast."""
        from downloader import sanitize_path_component
        
        dirty = 'File<>:"/\\|?*Name with spaces (2023) [1080p]'
        
        result = benchmark(sanitize_path_component, dirty)
        
        assert result is not None
    
    def test_sanitize_batch(self):
        """Batch sanitization should be efficient."""
        from downloader import sanitize_path_component
        
        filenames = [
            f'Movie<{i}>:Title"/\\|?*[{i}].mkv'
            for i in range(1000)
        ]
        
        start = time.perf_counter()
        
        for fn in filenames:
            sanitize_path_component(fn)
        
        elapsed = time.perf_counter() - start
        
        # 1000 sanitizations should take less than 100ms
        assert elapsed < 0.1, f"Batch sanitization took {elapsed:.3f}s"


class TestMemoryEfficiency:
    """Tests for memory-related concerns."""
    
    def test_stats_list_growth(self, fresh_stats):
        """Stats lists should grow as expected (identifies memory issue)."""
        # This test documents the current behavior as a baseline
        # The improvement plan suggests using bounded deque
        
        initial_len = len(fresh_stats.download_times)
        
        for i in range(1000):
            fresh_stats.add_download(1024, 1.0, success=True)
        
        final_len = len(fresh_stats.download_times)
        
        # Current behavior: lists grow unbounded
        assert final_len == initial_len + 1000
        
        # NOTE: After implementing the improvement, this should be:
        # assert final_len <= MAX_SAMPLES
    
    def test_session_dict_cleanup_needed(self):
        """Document that session dicts need manual cleanup."""
        from collections import defaultdict
        
        # This mirrors the pattern in main.py
        sessions = defaultdict(dict)
        
        # Simulate creating sessions without cleanup
        for i in range(100):
            sessions[i] = {"data": f"user_{i}"}
        
        # Sessions persist (memory leak potential)
        assert len(sessions) == 100
        
        # NOTE: Current behavior - sessions not auto-expired
        # Improvement plan suggests implementing SessionManager with TTL
