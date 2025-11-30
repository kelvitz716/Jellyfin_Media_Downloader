"""
Performance benchmarks for Jellyfin Media Downloader Bot.

Run with: python -m pytest tests/test_performance.py -v -s
"""
import asyncio
import time
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class TestStartupPerformance:
    """Test bot startup time and initialization."""
    
    def test_import_time(self):
        """Measure time to import main module."""
        start = time.perf_counter()
        
        # Import main module (triggers all module-level initialization)
        import main
        
        duration = time.perf_counter() - start
        
        print(f"\n📊 Import Time: {duration:.3f}s")
        print(f"   Target: < 0.5s")
        print(f"   Status: {'✅ PASS' if duration < 0.5 else '❌ SLOW'}")
        
        # Store for comparison
        with open('performance_baseline.txt', 'a') as f:
            f.write(f"{datetime.now()},import_time,{duration:.3f}\n")
    
    def test_database_initialization(self):
        """Measure database initialization time."""
        start = time.perf_counter()
        
        from database import db, users_tbl, stats_tbl, organized_tbl
        
        duration = time.perf_counter() - start
        
        print(f"\n📊 Database Init: {duration:.3f}s")
        print(f"   Target: < 0.1s")
        print(f"   Status: {'✅ PASS' if duration < 0.1 else '❌ SLOW'}")
        
        with open('performance_baseline.txt', 'a') as f:
            f.write(f"{datetime.now()},db_init,{duration:.3f}\n")
    
    def test_stats_loading(self):
        """Measure stats loading time."""
        from stats import BotStats
        
        start = time.perf_counter()
        
        # This triggers load_all()
        stats = BotStats.global_stats
        
        duration = time.perf_counter() - start
        
        print(f"\n📊 Stats Loading: {duration:.3f}s")
        print(f"   Target: < 0.05s")
        print(f"   Status: {'✅ PASS' if duration < 0.05 else '❌ SLOW'}")
        
        with open('performance_baseline.txt', 'a') as f:
            f.write(f"{datetime.now()},stats_load,{duration:.3f}\n")


class TestDatabasePerformance:
    """Test database operation performance."""
    
    @pytest.mark.asyncio
    async def test_load_active_users(self):
        """Measure user loading time."""
        from database import load_active_users
        
        # Warm up
        load_active_users()
        
        # Measure
        iterations = 100
        start = time.perf_counter()
        
        for _ in range(iterations):
            users = load_active_users()
        
        duration = time.perf_counter() - start
        avg = duration / iterations
        
        print(f"\n📊 Load Active Users ({iterations} iterations):")
        print(f"   Total: {duration:.3f}s")
        print(f"   Average: {avg*1000:.2f}ms")
        print(f"   Target: < 10ms")
        print(f"   Status: {'✅ PASS' if avg < 0.01 else '❌ SLOW'}")
        
        with open('performance_baseline.txt', 'a') as f:
            f.write(f"{datetime.now()},load_users_avg,{avg*1000:.2f}\n")
    
    @pytest.mark.asyncio
    async def test_save_active_users(self):
        """Measure user saving time."""
        from database import save_active_users
        
        test_users = {12345, 67890, 11111}
        
        # Warm up
        save_active_users(test_users)
        
        # Measure
        iterations = 50
        start = time.perf_counter()
        
        for _ in range(iterations):
            save_active_users(test_users)
        
        duration = time.perf_counter() - start
        avg = duration / iterations
        
        print(f"\n📊 Save Active Users ({iterations} iterations):")
        print(f"   Total: {duration:.3f}s")
        print(f"   Average: {avg*1000:.2f}ms")
        print(f"   Target: < 20ms")
        print(f"   Status: {'✅ PASS' if avg < 0.02 else '❌ SLOW'}")
        
        with open('performance_baseline.txt', 'a') as f:
            f.write(f"{datetime.now()},save_users_avg,{avg*1000:.2f}\n")
    
    @pytest.mark.asyncio
    async def test_concurrent_database_access(self):
        """Test if database operations block event loop."""
        from database import load_active_users
        
        async def db_operation():
            """Simulate database operation in thread."""
            return await asyncio.to_thread(load_active_users)
        
        # Run 10 concurrent operations
        start = time.perf_counter()
        
        results = await asyncio.gather(*[db_operation() for _ in range(10)])
        
        duration = time.perf_counter() - start
        
        print(f"\n📊 Concurrent DB Access (10 operations):")
        print(f"   Duration: {duration:.3f}s")
        print(f"   Target: < 0.2s (should be ~same as 1 operation)")
        print(f"   Status: {'✅ PASS' if duration < 0.2 else '❌ BLOCKING'}")
        
        with open('performance_baseline.txt', 'a') as f:
            f.write(f"{datetime.now()},concurrent_db,{duration:.3f}\n")


class TestMemoryUsage:
    """Test memory footprint."""
    
    def test_import_memory(self):
        """Measure memory usage after imports."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        
        # Import main module
        import main
        
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        mem_increase = mem_after - mem_before
        
        print(f"\n📊 Memory Usage:")
        print(f"   Before imports: {mem_before:.1f} MB")
        print(f"   After imports: {mem_after:.1f} MB")
        print(f"   Increase: {mem_increase:.1f} MB")
        print(f"   Target: < 50 MB increase")
        print(f"   Status: {'✅ PASS' if mem_increase < 50 else '⚠️ HIGH'}")
        
        with open('performance_baseline.txt', 'a') as f:
            f.write(f"{datetime.now()},memory_increase,{mem_increase:.1f}\n")


class TestModuleImportTimes:
    """Profile individual module import times."""
    
    def test_individual_imports(self):
        """Measure time for each major import."""
        imports_to_test = [
            ('asyncio', 'import asyncio'),
            ('aiohttp', 'import aiohttp'),
            ('telethon', 'from telethon import TelegramClient'),
            ('guessit', 'from guessit import guessit'),
            ('humanize', 'import humanize'),
            ('tinydb', 'from tinydb import TinyDB'),
        ]
        
        print(f"\n📊 Individual Import Times:")
        print(f"   {'Module':<15} {'Time':<10} {'Status'}")
        print(f"   {'-'*15} {'-'*10} {'-'*10}")
        
        results = []
        for name, import_stmt in imports_to_test:
            start = time.perf_counter()
            exec(import_stmt)
            duration = time.perf_counter() - start
            
            status = '✅' if duration < 0.1 else '⚠️' if duration < 0.2 else '❌'
            print(f"   {name:<15} {duration*1000:>8.1f}ms {status}")
            
            results.append((name, duration))
            
            with open('performance_baseline.txt', 'a') as f:
                f.write(f"{datetime.now()},import_{name},{duration*1000:.1f}\n")
        
        total = sum(d for _, d in results)
        print(f"\n   {'TOTAL':<15} {total*1000:>8.1f}ms")


def generate_performance_report():
    """Generate a summary report from baseline data."""
    if not os.path.exists('performance_baseline.txt'):
        print("No baseline data found. Run tests first.")
        return
    
    print("\n" + "="*60)
    print("PERFORMANCE BASELINE REPORT")
    print("="*60)
    
    # Read and parse data
    metrics = {}
    with open('performance_baseline.txt', 'r') as f:
        for line in f:
            if line.strip():
                timestamp, metric, value = line.strip().split(',')
                if metric not in metrics:
                    metrics[metric] = []
                metrics[metric].append(float(value))
    
    # Calculate averages
    print(f"\n{'Metric':<25} {'Avg':<12} {'Min':<12} {'Max':<12} {'Target':<12}")
    print("-" * 73)
    
    targets = {
        'import_time': 0.5,
        'db_init': 0.1,
        'stats_load': 0.05,
        'load_users_avg': 10,
        'save_users_avg': 20,
        'concurrent_db': 0.2,
        'memory_increase': 50,
    }
    
    for metric, values in sorted(metrics.items()):
        if not values:
            continue
        
        avg = sum(values) / len(values)
        min_val = min(values)
        max_val = max(values)
        target = targets.get(metric, 0)
        
        # Format based on metric type
        if 'avg' in metric:
            unit = 'ms'
            fmt = '.2f'
        elif 'memory' in metric:
            unit = 'MB'
            fmt = '.1f'
        else:
            unit = 's'
            fmt = '.3f'
        
        status = '✅' if avg <= target else '❌'
        
        print(f"{metric:<25} {avg:{fmt}}{unit:<8} {min_val:{fmt}}{unit:<8} "
              f"{max_val:{fmt}}{unit:<8} {target:{fmt}}{unit:<8} {status}")
    
    print("\n" + "="*60)


if __name__ == '__main__':
    # Clear previous baseline
    if os.path.exists('performance_baseline.txt'):
        os.remove('performance_baseline.txt')
    
    print("🚀 Running Performance Benchmarks...")
    print("="*60)
    
    # Run pytest
    pytest.main([__file__, '-v', '-s'])
    
    # Generate report
    print("\n")
    generate_performance_report()
